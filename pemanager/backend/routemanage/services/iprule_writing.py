"""
策略路由（ip rule）下发：维护内核 ip rule 列表与 PolicyRouteRule 意图的对账与下发。

实现策略：
- 不写 netplan（netplan routing-policy 只能挂在某个设备上，且字段受限）；
- 通过 `ip rule add/del` 直接操作内核；
- pemanager 仅清理优先级落在 PEMANAGER_OWNED_PRIO_RANGE 内的旧规则，避免误删系统/其他模块写入的规则；
- 提供 preview / apply / clear 三阶段；
- 同步过程中按 priority 升序 add（priority 缺省由内核分配）。
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Literal

from django.conf import settings

from interfacemanage.services.netplan_writing import _run as _elevated_run

from routemanage.models import PolicyRouteRule

ApplyPhase = Literal['full', 'preview']

DEFAULT_OWNED_RANGE = (10000, 19999)


def _owned_range() -> tuple[int, int]:
    rng = getattr(settings, 'ROUTEMANAGE_IPRULE_OWNED_PRIO_RANGE', None)
    if not isinstance(rng, (list, tuple)) or len(rng) != 2:
        return DEFAULT_OWNED_RANGE
    try:
        lo, hi = int(rng[0]), int(rng[1])
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi
    except (TypeError, ValueError):
        return DEFAULT_OWNED_RANGE


def _rule_to_args(rule: PolicyRouteRule) -> list[str]:
    """将 PolicyRouteRule 转换为 `ip [-4|-6] rule add <args>` 的尾部参数。"""
    args: list[str] = []
    if rule.priority is not None:
        args += ['priority', str(int(rule.priority))]
    if rule.invert:
        args += ['not']
    if (rule.from_cidr or '').strip():
        args += ['from', rule.from_cidr.strip()]
    else:
        args += ['from', 'all']
    if (rule.to_cidr or '').strip():
        args += ['to', rule.to_cidr.strip()]
    if (rule.iif or '').strip():
        args += ['iif', rule.iif.strip()]
    if (rule.oif or '').strip():
        args += ['oif', rule.oif.strip()]
    if (rule.fwmark or '').strip():
        args += ['fwmark', rule.fwmark.strip()]
    if (rule.tos or '').strip():
        args += ['tos', rule.tos.strip()]
    if rule.suppress_prefixlength is not None:
        args += ['suppress_prefixlength', str(int(rule.suppress_prefixlength))]

    if rule.action == PolicyRouteRule.Action.LOOKUP:
        args += ['lookup', str(int(rule.table_id))]
    elif rule.action == PolicyRouteRule.Action.NAT:
        args += ['nat', str(rule.nat_target)]
    elif rule.action == PolicyRouteRule.Action.BLACKHOLE:
        args += ['blackhole']
    elif rule.action == PolicyRouteRule.Action.UNREACHABLE:
        args += ['unreachable']
    elif rule.action == PolicyRouteRule.Action.PROHIBIT:
        args += ['prohibit']
    return args


def _family_flag(family: str) -> str:
    return '-6' if family == PolicyRouteRule.Family.INET6 else '-4'


def render_ip_rule_commands(rules: Iterable[PolicyRouteRule]) -> list[str]:
    out: list[str] = []
    for r in rules:
        if not r.enabled:
            continue
        argv = ['ip', _family_flag(r.family), 'rule', 'add', *_rule_to_args(r)]
        out.append(' '.join(argv))
    return out


def preview_policy_rules() -> dict[str, Any]:
    qs = PolicyRouteRule.objects.all().order_by('priority', 'id')
    cmds = render_ip_rule_commands(qs)
    lo, hi = _owned_range()
    return {
        'ok': True,
        'commands': cmds,
        'count': len(cmds),
        'owned_range': [lo, hi],
        'hint': (
            f'下发前会清理 priority 落在 [{lo}, {hi}] 范围内的旧规则；'
            '建议把 PE Manager 受控规则的 priority 设置在该范围内。'
        ),
    }


def _list_current_rules() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for family_flag in ('-4', '-6'):
        res = _elevated_run(['ip', '-json', family_flag, 'rule', 'show'])
        if not res.ok:
            continue
        try:
            data = json.loads(res.stdout or '[]')
        except json.JSONDecodeError:
            continue
        for row in data if isinstance(data, list) else []:
            if not isinstance(row, dict):
                continue
            row['_family_flag'] = family_flag
            out.append(row)
    return out


def _flush_owned_range() -> list[dict[str, Any]]:
    lo, hi = _owned_range()
    steps: list[dict[str, Any]] = []
    for row in _list_current_rules():
        prio = row.get('priority')
        try:
            prio_i = int(prio)
        except (TypeError, ValueError):
            continue
        if prio_i < lo or prio_i > hi:
            continue
        fam = row.get('_family_flag') or '-4'
        res = _elevated_run(['ip', fam, 'rule', 'del', 'priority', str(prio_i)], timeout_kind='apply')
        steps.append(
            {
                'step': 'rule del',
                'priority': prio_i,
                'family': fam,
                'ok': res.ok,
                'stderr': res.stderr,
            }
        )
    return steps


def apply_policy_rules(
    *,
    phase: ApplyPhase | str = 'full',
    ids: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """
    下发策略路由（ip rule）。

    参数：
      phase: preview | full
      ids:   若提供，则只下发选中的 rule id；并只 flush 这些 rule 当前的 priority 值，
             不影响 owned-range 中其它规则；这样可避免一次操作清掉/重建全部 ip rule，
             造成与之耦合的业务路由短时不可用。
    """
    if not getattr(settings, 'ROUTEMANAGE_IPRULE_WRITE_ENABLED', False):
        return {'ok': False, 'error': '策略路由下发已关闭（settings.ROUTEMANAGE_IPRULE_WRITE_ENABLED）'}

    phase_l = (phase or 'full').lower()
    if phase_l == 'preview':
        return preview_policy_rules()

    qs = PolicyRouteRule.objects.all().order_by('priority', 'id')
    selected_ids: set[str] | None = None
    if ids is not None:
        selected_ids = {str(i) for i in ids}
        if not selected_ids:
            return {'ok': True, 'steps': [], 'message': '选中集合为空'}
        qs = qs.filter(id__in=selected_ids)

    steps: list[dict[str, Any]] = []

    if selected_ids is None:
        flush_steps = _flush_owned_range()
    else:
        # 选择性下发：只删除选中 rule 当前持有的 priority，避免误删 owned-range 中其它规则
        flush_steps = []
        for r in qs:
            if r.priority is None:
                continue
            fam = _family_flag(r.family)
            res = _elevated_run(
                ['ip', fam, 'rule', 'del', 'priority', str(int(r.priority))],
                timeout_kind='apply',
            )
            flush_steps.append({
                'step': 'rule del (selective)',
                'priority': int(r.priority),
                'family': fam,
                'rule_id': str(r.id),
                'ok': res.ok,
                'stderr': res.stderr,
            })
    steps.extend(flush_steps)

    add_count = 0
    failed: list[dict[str, Any]] = []
    for r in qs:
        if not r.enabled:
            continue
        argv = ['ip', _family_flag(r.family), 'rule', 'add', *_rule_to_args(r)]
        res = _elevated_run(argv, timeout_kind='apply')
        ok = res.ok
        steps.append(
            {
                'step': 'rule add',
                'argv': argv,
                'rule_id': str(r.id),
                'priority': r.priority,
                'ok': ok,
                'stderr': res.stderr,
            }
        )
        if ok:
            add_count += 1
        else:
            failed.append({'rule_id': str(r.id), 'stderr': res.stderr})

    return {
        'ok': not failed,
        'phase': phase_l,
        'added': add_count,
        'flushed': len([s for s in flush_steps if s.get('ok')]),
        'failed': failed,
        'steps': steps,
        'selective': selected_ids is not None,
    }
