"""根据 FirewallRule / NATRule 渲染 nftables 规则集，并支持预览 / 写入 / 应用。"""
from __future__ import annotations

import ipaddress
import os
import shlex
import tempfile
from datetime import datetime
from typing import Any, Iterable, Literal

from django.conf import settings

from firewallmanage.models import FirewallRule, FirewallSettings, NATRule
from interfacemanage.services import subprocess_util

Phase = Literal['preview', 'validate', 'apply', 'flush']

TABLE_NAME = 'pemanager'
NAT_TABLE_NAME = 'pemanager_nat'
CHAIN_HOOKS = {
    FirewallRule.Chain.INPUT: ('input', 'filter', 0),
    FirewallRule.Chain.OUTPUT: ('output', 'filter', 0),
    FirewallRule.Chain.FORWARD: ('forward', 'filter', 0),
}


def _cmd_prefix() -> list[str]:
    raw = getattr(settings, 'FIREWALLMANAGE_CMD_PREFIX', '')
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str) and raw.strip():
        return shlex.split(raw)
    return []


def _family_keyword(cidr: str) -> str:
    try:
        net = ipaddress.ip_network(cidr.strip(), strict=False)
        return 'ip6' if net.version == 6 else 'ip'
    except ValueError:
        return 'ip'


def _port_expr(port: str) -> str:
    if '-' in port:
        a, b = port.split('-', 1)
        return f'{int(a)}-{int(b)}'
    return str(int(port))


def _rule_lines_for_family(rule: FirewallRule, family: str) -> list[str]:
    """family: 'ip' or 'ip6'。"""
    parts: list[str] = []
    if rule.in_interface:
        parts.append(f'iifname "{rule.in_interface}"')
    if rule.out_interface:
        parts.append(f'oifname "{rule.out_interface}"')

    if rule.src_cidr:
        net = ipaddress.ip_network(rule.src_cidr.strip(), strict=False)
        if (net.version == 6) == (family == 'ip6'):
            parts.append(f'{family} saddr {net}')
        else:
            return []
    if rule.dst_cidr:
        net = ipaddress.ip_network(rule.dst_cidr.strip(), strict=False)
        if (net.version == 6) == (family == 'ip6'):
            parts.append(f'{family} daddr {net}')
        else:
            return []

    if rule.protocol == FirewallRule.Protocol.TCP:
        parts.append('tcp')
        if rule.src_port:
            parts.append(f'sport {_port_expr(rule.src_port)}')
        if rule.dst_port:
            parts.append(f'dport {_port_expr(rule.dst_port)}')
    elif rule.protocol == FirewallRule.Protocol.UDP:
        parts.append('udp')
        if rule.src_port:
            parts.append(f'sport {_port_expr(rule.src_port)}')
        if rule.dst_port:
            parts.append(f'dport {_port_expr(rule.dst_port)}')
    elif rule.protocol == FirewallRule.Protocol.ICMP:
        parts.append('icmpv6' if family == 'ip6' else 'icmp')

    if rule.action == FirewallRule.Action.ACCEPT:
        verdict = 'accept'
    elif rule.action == FirewallRule.Action.DROP:
        verdict = 'drop'
    elif rule.action == FirewallRule.Action.REJECT:
        verdict = 'reject'
    else:  # LOG => log + accept
        verdict = f'log prefix "pemanager:{rule.name[:24]}" accept'

    comment = ''
    if rule.remark or rule.name:
        c = (rule.remark or rule.name).replace('"', "'")[:60]
        comment = f' comment "{c}"'

    return [' '.join(parts + [verdict]).strip() + comment]


def _expand_rule_to_families(rule: FirewallRule) -> Iterable[tuple[str, str]]:
    """yield (family, line)"""
    targets: list[str] = []
    if rule.family == FirewallRule.Family.IPV4:
        targets = ['ip']
    elif rule.family == FirewallRule.Family.IPV6:
        targets = ['ip6']
    else:
        targets = ['ip', 'ip6']

    for fam in targets:
        for ln in _rule_lines_for_family(rule, fam):
            if ln:
                yield (fam, ln)


def _nat_chain_lines(rule: NATRule) -> tuple[str, str] | None:
    """返回 (chain_name, line)；ip 或 ip6 表（按 family）。"""
    fam = 'ip' if rule.family == NATRule.Family.IPV4 else 'ip6'
    parts: list[str] = []
    if rule.in_interface:
        parts.append(f'iifname "{rule.in_interface}"')
    if rule.out_interface:
        parts.append(f'oifname "{rule.out_interface}"')
    if rule.src_cidr:
        parts.append(f'{fam} saddr {ipaddress.ip_network(rule.src_cidr.strip(), strict=False)}')
    if rule.dst_cidr:
        parts.append(f'{fam} daddr {ipaddress.ip_network(rule.dst_cidr.strip(), strict=False)}')
    if rule.protocol in (NATRule.Protocol.TCP, NATRule.Protocol.UDP):
        parts.append(rule.protocol)
        if rule.dst_port:
            parts.append(f'dport {_port_expr(rule.dst_port)}')

    if rule.kind == NATRule.Kind.DNAT:
        chain = 'prerouting'
        target = rule.to_ip or ''
        if rule.to_port:
            target += f':{_port_expr(rule.to_port)}' if target else f':{_port_expr(rule.to_port)}'
        if not target:
            return None
        verdict = f'dnat to {target}' if rule.to_ip else f'dnat to :{_port_expr(rule.to_port)}'
    elif rule.kind == NATRule.Kind.SNAT:
        chain = 'postrouting'
        if not rule.to_ip:
            return None
        verdict = f'snat to {rule.to_ip}'
    elif rule.kind == NATRule.Kind.MASQ:
        chain = 'postrouting'
        verdict = 'masquerade'
    elif rule.kind == NATRule.Kind.REDIRECT:
        chain = 'prerouting'
        if not rule.to_port:
            return None
        verdict = f'redirect to :{_port_expr(rule.to_port)}'
    else:
        return None

    if rule.remark or rule.name:
        c = (rule.remark or rule.name).replace('"', "'")[:60]
        verdict = f'{verdict} comment "{c}"'

    return chain, ' '.join(parts + [verdict]).strip()


def _policy(p: str) -> str:
    return 'drop' if p == 'drop' else 'accept'


def render_ruleset() -> str:
    """构造 inet pemanager 过滤表 + ip/ip6 pemanager_nat 表 + 已启用规则。"""
    s = FirewallSettings.load()
    out: list[str] = []
    out.append(f'# Generated by PE Manager at {datetime.utcnow().isoformat()}Z (engine=nft)')
    out.append(f'# default policies: input={s.policy_input} output={s.policy_output} forward={s.policy_forward}')

    # filter 表
    out.append(f'table inet {TABLE_NAME} {{')
    out.append(
        f'  chain input    {{ type filter hook input    priority 0; policy {_policy(s.policy_input)}; }}'
    )
    out.append(
        f'  chain output   {{ type filter hook output   priority 0; policy {_policy(s.policy_output)}; }}'
    )
    out.append(
        f'  chain forward  {{ type filter hook forward  priority 0; policy {_policy(s.policy_forward)}; }}'
    )
    out.append('}')

    # NAT 表（v4 + v6 分别建，nftables 的 NAT chain 不能在 inet 家族）
    has_v4 = NATRule.objects.filter(enabled=True, family=NATRule.Family.IPV4).exists()
    has_v6 = NATRule.objects.filter(enabled=True, family=NATRule.Family.IPV6).exists()
    if has_v4:
        out.append(f'table ip {NAT_TABLE_NAME} {{')
        out.append('  chain prerouting  { type nat hook prerouting  priority -100; policy accept; }')
        out.append('  chain postrouting { type nat hook postrouting priority  100; policy accept; }')
        out.append('}')
    if has_v6:
        out.append(f'table ip6 {NAT_TABLE_NAME} {{')
        out.append('  chain prerouting  { type nat hook prerouting  priority -100; policy accept; }')
        out.append('  chain postrouting { type nat hook postrouting priority  100; policy accept; }')
        out.append('}')

    # 过滤规则
    chain_to_lines: dict[str, list[str]] = {'input': [], 'output': [], 'forward': []}
    for rule in FirewallRule.objects.filter(enabled=True).order_by('chain', 'priority', 'created_at'):
        for _fam, ln in _expand_rule_to_families(rule):
            chain_to_lines[rule.chain].append(ln)

    out.append('')
    out.append(f'flush chain inet {TABLE_NAME} input')
    out.append(f'flush chain inet {TABLE_NAME} output')
    out.append(f'flush chain inet {TABLE_NAME} forward')
    if has_v4:
        out.append(f'flush chain ip {NAT_TABLE_NAME} prerouting')
        out.append(f'flush chain ip {NAT_TABLE_NAME} postrouting')
    if has_v6:
        out.append(f'flush chain ip6 {NAT_TABLE_NAME} prerouting')
        out.append(f'flush chain ip6 {NAT_TABLE_NAME} postrouting')

    for chain in ('input', 'output', 'forward'):
        for ln in chain_to_lines[chain]:
            out.append(f'add rule inet {TABLE_NAME} {chain} {ln}')

    for nat in NATRule.objects.filter(enabled=True).order_by('kind', 'priority', 'created_at'):
        pair = _nat_chain_lines(nat)
        if not pair:
            continue
        chain, line = pair
        fam = 'ip' if nat.family == NATRule.Family.IPV4 else 'ip6'
        out.append(f'add rule {fam} {NAT_TABLE_NAME} {chain} {line}')

    return '\n'.join(out) + '\n'


def _run_nft(args: list[str], *, timeout: int = 10):
    return subprocess_util.run(_cmd_prefix() + ['nft'] + args, timeout=timeout)


def _write_temp_ruleset(text: str) -> str:
    fd, path = tempfile.mkstemp(prefix='pemanager-fw-', suffix='.nft')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


def apply_ruleset(*, phase: Phase = 'apply') -> dict[str, Any]:
    if phase == 'preview':
        return {'ok': True, 'phase': phase, 'engine': 'nft', 'ruleset': render_ruleset()}

    if not getattr(settings, 'FIREWALLMANAGE_APPLY_ENABLED', False):
        return {
            'ok': False,
            'error': '防火墙下发已关闭（settings.FIREWALLMANAGE_APPLY_ENABLED）',
            'hint': '请设置 FIREWALLMANAGE_APPLY_ENABLED=1 并重启后端',
            'engine': 'nft',
            'steps': [],
            'ruleset': render_ruleset(),
        }

    ruleset = render_ruleset()
    steps: list[dict[str, Any]] = []

    if phase == 'flush':
        for ch in ('input', 'output', 'forward'):
            r = _run_nft(['flush', 'chain', 'inet', TABLE_NAME, ch])
            steps.append({'step': f'flush inet {ch}', 'ok': r.ok, 'stderr': r.stderr, 'stdout': r.stdout})
        for fam in ('ip', 'ip6'):
            for ch in ('prerouting', 'postrouting'):
                r = _run_nft(['flush', 'chain', fam, NAT_TABLE_NAME, ch])
                # NAT 表可能不存在；视为幂等
                ok = r.ok or 'No such file or directory' in (r.stderr or '')
                steps.append(
                    {'step': f'flush {fam} {ch}', 'ok': ok, 'stderr': r.stderr, 'stdout': r.stdout}
                )
        return {'ok': all(s['ok'] for s in steps), 'phase': 'flush', 'engine': 'nft', 'steps': steps}

    tmp_path = _write_temp_ruleset(ruleset)
    steps.append({'step': 'write ruleset', 'ok': True, 'path': tmp_path})

    chk = _run_nft(['-c', '-f', tmp_path])
    steps.append({'step': 'nft -c (check)', 'ok': chk.ok, 'stderr': chk.stderr, 'stdout': chk.stdout})
    if not chk.ok:
        _record_last('nft', False, f'nft -c 校验失败: {chk.stderr[:200]}')
        return {
            'ok': False,
            'error': 'nft -c 校验失败',
            'hint': '请检查上方 ruleset 与生成命令；可点「现状」查看真实表',
            'engine': 'nft',
            'steps': steps,
            'ruleset': ruleset,
        }

    if phase == 'validate':
        return {'ok': True, 'phase': 'validate', 'engine': 'nft', 'steps': steps, 'ruleset': ruleset}

    app = _run_nft(['-f', tmp_path])
    steps.append({'step': 'nft -f (apply)', 'ok': app.ok, 'stderr': app.stderr, 'stdout': app.stdout})
    if not app.ok:
        _record_last('nft', False, f'nft -f 应用失败: {app.stderr[:200]}')
        return {
            'ok': False,
            'error': 'nft -f 应用失败',
            'engine': 'nft',
            'steps': steps,
            'ruleset': ruleset,
        }

    _record_last('nft', True, f'apply ok ({len(ruleset)} bytes)')
    return {'ok': True, 'phase': 'apply', 'engine': 'nft', 'steps': steps, 'ruleset': ruleset}


def show_ruleset() -> dict[str, Any]:
    out: dict[str, Any] = {'engine': 'nft', 'tables': {}}
    for fam, table in (('inet', TABLE_NAME), ('ip', NAT_TABLE_NAME), ('ip6', NAT_TABLE_NAME)):
        r = _run_nft(['list', 'table', fam, table])
        out['tables'][f'{fam} {table}'] = {
            'ok': r.ok,
            'exit_code': r.exit_code,
            'stderr': r.stderr,
            'stdout': r.stdout,
        }
    out['ok'] = any(v['ok'] for v in out['tables'].values())
    return out


def _record_last(engine: str, ok: bool, summary: str) -> None:
    from django.utils import timezone

    s = FirewallSettings.load()
    s.engine = engine if engine in (s.Engine.NFT, s.Engine.IPTABLES) else s.engine
    s.last_apply_at = timezone.now()
    s.last_apply_ok = bool(ok)
    s.last_apply_summary = summary[:512]
    s.save(update_fields=['last_apply_at', 'last_apply_ok', 'last_apply_summary'])
