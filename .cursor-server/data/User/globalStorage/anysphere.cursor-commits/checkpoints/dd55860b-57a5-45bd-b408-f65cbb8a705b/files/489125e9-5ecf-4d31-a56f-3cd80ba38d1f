"""根据 QoSPolicy/QoSRule 渲染 `tc` 命令组并执行。"""
from __future__ import annotations

import ipaddress
import shlex
from typing import Any, Literal

from django.conf import settings

from interfacemanage.services import subprocess_util
from qosmanage.models import QoSPolicy, QoSRule

Phase = Literal['preview', 'apply', 'clear']


def _cmd_prefix() -> list[str]:
    raw = getattr(settings, 'QOSMANAGE_CMD_PREFIX', '')
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str) and raw.strip():
        return shlex.split(raw)
    return []


def _quote_cmd(argv: list[str]) -> str:
    return ' '.join(shlex.quote(x) for x in argv)


def _root_handle() -> str:
    return '1:'


def _filter_protocol_for(rule: QoSRule) -> str:
    if rule.match_kind in (QoSRule.Match.SRC, QoSRule.Match.DST) and rule.match_value:
        try:
            net = ipaddress.ip_network(rule.match_value.strip(), strict=False)
            return 'ipv6' if net.version == 6 else 'ip'
        except ValueError:
            return 'ip'
    return 'ip'


def _u32_match(rule: QoSRule) -> list[str]:
    """构造 tc filter u32 match 片段。"""
    if rule.match_kind == QoSRule.Match.SRC and rule.match_value:
        net = ipaddress.ip_network(rule.match_value.strip(), strict=False)
        sel = 'src'
        return ['match', 'ip' if net.version == 4 else 'ip6', sel, str(net)]
    if rule.match_kind == QoSRule.Match.DST and rule.match_value:
        net = ipaddress.ip_network(rule.match_value.strip(), strict=False)
        sel = 'dst'
        return ['match', 'ip' if net.version == 4 else 'ip6', sel, str(net)]
    if rule.match_kind == QoSRule.Match.DSCP and rule.match_value:
        dscp = int(rule.match_value.strip(), 0) & 0x3F
        tos = (dscp << 2) & 0xFC
        return ['match', 'ip', 'tos', f'0x{tos:02x}', '0xfc']
    return ['match', 'u32', '0', '0']


def build_commands(policy: QoSPolicy) -> list[list[str]]:
    """返回 [ argv1, argv2, ... ]，每条独立执行；包含 root qdisc + classes + filters。"""
    iface = (policy.interface_name or '').strip()
    if not iface:
        return []

    cmds: list[list[str]] = []

    if policy.root_kind == QoSPolicy.RootKind.HTB:
        cmds.append(['tc', 'qdisc', 'add', 'dev', iface, 'root', 'handle', _root_handle(), 'htb', 'default', '10'])
        cmds.append(
            [
                'tc', 'class', 'add', 'dev', iface, 'parent', _root_handle(),
                'classid', '1:1',
                'htb',
                'rate', f'{policy.default_ceil_mbps}mbit',
                'ceil', f'{policy.default_ceil_mbps}mbit',
            ]
        )
        cmds.append(
            [
                'tc', 'class', 'add', 'dev', iface, 'parent', '1:1',
                'classid', '1:10',
                'htb',
                'rate', f'{policy.default_rate_mbps}mbit',
                'ceil', f'{policy.default_ceil_mbps}mbit',
            ]
        )
        cmds.append(
            ['tc', 'qdisc', 'add', 'dev', iface, 'parent', '1:10', 'handle', '10:', 'fq_codel']
        )

        for rule in policy.rules.all().order_by('priority', 'class_id'):
            cid = int(rule.class_id)
            classid = f'1:{cid}'
            cmds.append(
                [
                    'tc', 'class', 'add', 'dev', iface, 'parent', '1:1',
                    'classid', classid,
                    'htb',
                    'rate', f'{rule.rate_mbps}mbit',
                    'ceil', f'{rule.ceil_mbps}mbit',
                    'prio', str(rule.priority),
                ]
            )
            cmds.append(
                [
                    'tc', 'qdisc', 'add', 'dev', iface,
                    'parent', classid, 'handle', f'{cid}:', 'fq_codel',
                ]
            )
            proto = _filter_protocol_for(rule)
            f = [
                'tc', 'filter', 'add', 'dev', iface, 'protocol', proto,
                'parent', _root_handle(), 'prio', str(rule.priority), 'u32',
            ]
            f += _u32_match(rule)
            f += ['flowid', classid]
            cmds.append(f)

    elif policy.root_kind == QoSPolicy.RootKind.FQ_CODEL:
        cmds.append(['tc', 'qdisc', 'add', 'dev', iface, 'root', 'handle', _root_handle(), 'fq_codel'])

    elif policy.root_kind == QoSPolicy.RootKind.CAKE:
        rate = max(int(policy.default_ceil_mbps or 0), 1)
        cmds.append(
            [
                'tc', 'qdisc', 'add', 'dev', iface, 'root', 'handle', _root_handle(),
                'cake', 'bandwidth', f'{rate}mbit',
            ]
        )

    return cmds


def render_preview(policy: QoSPolicy) -> dict[str, Any]:
    cmds = build_commands(policy)
    return {
        'ok': True,
        'interface': policy.interface_name,
        'commands': [_quote_cmd(c) for c in cmds],
        'clear_commands': [_quote_cmd(c) for c in build_clear_commands(policy.interface_name)],
    }


def build_clear_commands(interface_name: str) -> list[list[str]]:
    iface = (interface_name or '').strip()
    if not iface:
        return []
    return [['tc', 'qdisc', 'del', 'dev', iface, 'root']]


def _run_with_prefix(argv: list[str], *, timeout: int | None = None):
    full = _cmd_prefix() + argv
    return subprocess_util.run(full, timeout=timeout)


def apply_policy(policy: QoSPolicy, *, phase: Phase = 'apply') -> dict[str, Any]:
    """先尝试清理已有 root qdisc，再按 commands 顺序执行。"""
    if not getattr(settings, 'QOSMANAGE_APPLY_ENABLED', False):
        return {'ok': False, 'error': 'QoS 下发已关闭（settings.QOSMANAGE_APPLY_ENABLED）', 'steps': []}

    iface = (policy.interface_name or '').strip()
    if not iface:
        return {'ok': False, 'error': '策略缺少接口名', 'steps': []}

    steps: list[dict[str, Any]] = []
    timeout = int(getattr(settings, 'QOSMANAGE_CMD_TIMEOUT', 10))

    if phase == 'preview':
        return render_preview(policy)

    for clear in build_clear_commands(iface):
        res = _run_with_prefix(clear, timeout=timeout)
        steps.append(
            {
                'step': 'clear',
                'cmd': _quote_cmd(clear),
                'ok': res.ok,
                'exit_code': res.exit_code,
                'stderr': res.stderr,
                'stdout': res.stdout,
            }
        )

    if phase == 'clear':
        return {'ok': True, 'phase': 'clear', 'steps': steps}

    for argv in build_commands(policy):
        res = _run_with_prefix(argv, timeout=timeout)
        steps.append(
            {
                'step': 'apply',
                'cmd': _quote_cmd(argv),
                'ok': res.ok,
                'exit_code': res.exit_code,
                'stderr': res.stderr,
                'stdout': res.stdout,
            }
        )
        if not res.ok:
            return {
                'ok': False,
                'error': f'命令失败：{_quote_cmd(argv)} -> {res.stderr or res.stdout}',
                'steps': steps,
                'commands': [_quote_cmd(c) for c in build_commands(policy)],
            }
    return {
        'ok': True,
        'phase': phase,
        'steps': steps,
        'commands': [_quote_cmd(c) for c in build_commands(policy)],
    }


def show_tc(interface_name: str) -> dict[str, Any]:
    """读取 `tc -s qdisc/class/filter show dev <iface>` 文本。"""
    iface = (interface_name or '').strip()
    if not iface:
        return {'ok': False, 'error': '缺少接口名'}
    out: dict[str, Any] = {'ok': True, 'interface': iface}
    for kind in ('qdisc', 'class', 'filter'):
        res = subprocess_util.run(['tc', '-s', kind, 'show', 'dev', iface])
        out[kind] = {
            'ok': res.ok,
            'exit_code': res.exit_code,
            'stderr': res.stderr,
            'stdout': res.stdout,
        }
    return out
