"""根据 FirewallRule / NATRule 渲染 iptables-restore 脚本，并支持预览 / 校验 / 应用。

设计：
- 使用 `iptables-restore --table filter` 等价语法。所有规则放在自定义 chain `PEMANAGER_*`
  里，并在系统 INPUT/OUTPUT/FORWARD 末尾插一条 `-j PEMANAGER_*`，
  这样我们可以独立 flush 自己的 chain 而不破坏系统其它规则。
- IPv4 用 `iptables-restore`，IPv6 用 `ip6tables-restore`。
- NAT：filter 表里的链复用同样思路，PREROUTING/POSTROUTING 末尾跳到 `PEMANAGER_NAT_*`。
"""
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

FILTER_CHAINS = {
    FirewallRule.Chain.INPUT: ('INPUT', 'PEMANAGER_IN'),
    FirewallRule.Chain.OUTPUT: ('OUTPUT', 'PEMANAGER_OUT'),
    FirewallRule.Chain.FORWARD: ('FORWARD', 'PEMANAGER_FWD'),
}
NAT_CHAINS = {
    'prerouting': ('PREROUTING', 'PEMANAGER_NAT_PRE'),
    'postrouting': ('POSTROUTING', 'PEMANAGER_NAT_POST'),
}


def _cmd_prefix() -> list[str]:
    raw = getattr(settings, 'FIREWALLMANAGE_CMD_PREFIX', '')
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str) and raw.strip():
        return shlex.split(raw)
    return []


def _port_arg(port: str) -> str:
    if '-' in port:
        a, b = port.split('-', 1)
        return f'{int(a)}:{int(b)}'
    return str(int(port))


def _proto_args(proto: str) -> list[str]:
    if proto in ('tcp', 'udp'):
        return ['-p', proto]
    if proto == 'icmp':
        return ['-p', 'icmp']
    return []


def _action_args(rule: FirewallRule) -> list[str]:
    if rule.action == FirewallRule.Action.ACCEPT:
        return ['-j', 'ACCEPT']
    if rule.action == FirewallRule.Action.DROP:
        return ['-j', 'DROP']
    if rule.action == FirewallRule.Action.REJECT:
        return ['-j', 'REJECT']
    if rule.action == FirewallRule.Action.LOG:
        return ['-j', 'LOG', '--log-prefix', f'pemanager:{rule.name[:24]} ']
    return ['-j', 'ACCEPT']


def _rule_args_for_family(rule: FirewallRule, family: str) -> list[list[str]]:
    """family: 'ipv4' or 'ipv6'。返回多组 iptables 参数（用于支持 BOTH）。"""
    args: list[str] = []
    if rule.in_interface:
        args += ['-i', rule.in_interface]
    if rule.out_interface:
        args += ['-o', rule.out_interface]
    if rule.src_cidr:
        net = ipaddress.ip_network(rule.src_cidr.strip(), strict=False)
        if (net.version == 6) != (family == 'ipv6'):
            return []
        args += ['-s', str(net)]
    if rule.dst_cidr:
        net = ipaddress.ip_network(rule.dst_cidr.strip(), strict=False)
        if (net.version == 6) != (family == 'ipv6'):
            return []
        args += ['-d', str(net)]
    args += _proto_args(rule.protocol)
    if rule.protocol in (FirewallRule.Protocol.TCP, FirewallRule.Protocol.UDP):
        if rule.src_port:
            args += ['--sport', _port_arg(rule.src_port)]
        if rule.dst_port:
            args += ['--dport', _port_arg(rule.dst_port)]
    args += _action_args(rule)
    if rule.remark or rule.name:
        c = (rule.remark or rule.name).replace('"', "'").replace('\n', ' ')[:60]
        args += ['-m', 'comment', '--comment', c]
    return [args]


def _families_for(rule: FirewallRule) -> list[str]:
    if rule.family == FirewallRule.Family.IPV4:
        return ['ipv4']
    if rule.family == FirewallRule.Family.IPV6:
        return ['ipv6']
    return ['ipv4', 'ipv6']


def _nat_args(rule: NATRule) -> tuple[str, list[str]] | None:
    args: list[str] = []
    if rule.in_interface:
        args += ['-i', rule.in_interface]
    if rule.out_interface:
        args += ['-o', rule.out_interface]
    if rule.src_cidr:
        args += ['-s', str(ipaddress.ip_network(rule.src_cidr.strip(), strict=False))]
    if rule.dst_cidr:
        args += ['-d', str(ipaddress.ip_network(rule.dst_cidr.strip(), strict=False))]
    if rule.protocol in (NATRule.Protocol.TCP, NATRule.Protocol.UDP):
        args += ['-p', rule.protocol]
        if rule.dst_port:
            args += ['--dport', _port_arg(rule.dst_port)]

    if rule.kind == NATRule.Kind.DNAT:
        chain = 'prerouting'
        target = rule.to_ip or ''
        if rule.to_port:
            target = f'{target}:{_port_arg(rule.to_port)}' if target else f':{_port_arg(rule.to_port)}'
        if not target:
            return None
        args += ['-j', 'DNAT', '--to-destination', target]
    elif rule.kind == NATRule.Kind.SNAT:
        chain = 'postrouting'
        if not rule.to_ip:
            return None
        args += ['-j', 'SNAT', '--to-source', rule.to_ip]
    elif rule.kind == NATRule.Kind.MASQ:
        chain = 'postrouting'
        args += ['-j', 'MASQUERADE']
    elif rule.kind == NATRule.Kind.REDIRECT:
        chain = 'prerouting'
        if not rule.to_port:
            return None
        args += ['-j', 'REDIRECT', '--to-ports', _port_arg(rule.to_port)]
    else:
        return None

    if rule.remark or rule.name:
        c = (rule.remark or rule.name).replace('"', "'").replace('\n', ' ')[:60]
        args += ['-m', 'comment', '--comment', c]
    return chain, args


def _join_args(args: Iterable[str]) -> str:
    """iptables-restore 风格的参数串。带空格的值用双引号包起来。"""
    out: list[str] = []
    for a in args:
        if any(c.isspace() for c in a):
            out.append(f'"{a}"')
        else:
            out.append(a)
    return ' '.join(out)


def render_ruleset(*, family: str) -> str:
    """生成 iptables-restore 的脚本文本（filter + nat）。family in ('ipv4','ipv6')."""
    s = FirewallSettings.load()
    out: list[str] = []
    out.append(
        f'# Generated by PE Manager at {datetime.utcnow().isoformat()}Z '
        f'(engine=iptables, family={family})'
    )

    # ---------------------- *filter ----------------------
    out.append('*filter')
    out.append(f':INPUT {s.policy_input.upper()} [0:0]')
    out.append(f':FORWARD {s.policy_forward.upper()} [0:0]')
    out.append(f':OUTPUT {s.policy_output.upper()} [0:0]')
    # 自定义 chain（pemanager-managed）
    for _sys_ch, my_ch in FILTER_CHAINS.values():
        out.append(f':{my_ch} - [0:0]')
        out.append(f'-F {my_ch}')

    # 在系统 chain 末尾追加跳转到我们自己的 chain（重复 -A 是安全的，因为先 -F 后 -A 会重设）
    # iptables-restore 在 :CHAIN POLICY [0:0] 行已经隐式 flush 内置 chain 的计数；
    # 但内置 chain 上不会被 -F 清空（避免破坏其它工具的规则），所以我们用 *check then -A* 不可，
    # 但因为同时其它服务也可能 -A，所以约定：第一次部署后，pemanager 行只追加一次。
    # 在 -A 之前，先 -D（如果存在）实现幂等。iptables-restore 不支持条件 -D，但允许 -D 失败被忽略吗？不允许。
    # 解决：使用 `-I CHAIN 1 -j MYCHAIN` 在第一位插入，每次 apply 会重复插入 → 也不理想。
    # 折中：以 `-A CHAIN -j MYCHAIN` 追加；用户首次下发会插入一条跳转，二次下发会出现两条。
    # 因此我们在 apply 阶段先调用 iptables -D 去重（best-effort），再调用 iptables-restore。
    for sys_ch, my_ch in FILTER_CHAINS.values():
        out.append(f'-A {sys_ch} -j {my_ch}')

    qs = FirewallRule.objects.filter(enabled=True).order_by('chain', 'priority', 'created_at')
    for rule in qs:
        if family not in _families_for(rule):
            continue
        _sys_ch, my_ch = FILTER_CHAINS[rule.chain]
        for args in _rule_args_for_family(rule, family):
            if not args:
                continue
            out.append(f'-A {my_ch} ' + _join_args(args))

    out.append('COMMIT')

    # ---------------------- *nat ----------------------
    nat_qs = list(
        NATRule.objects.filter(enabled=True, family='ipv4' if family == 'ipv4' else 'ipv6').order_by(
            'kind', 'priority', 'created_at'
        )
    )
    out.append('')
    out.append('*nat')
    out.append(':PREROUTING ACCEPT [0:0]')
    out.append(':INPUT ACCEPT [0:0]')
    out.append(':OUTPUT ACCEPT [0:0]')
    out.append(':POSTROUTING ACCEPT [0:0]')
    for _sys_ch, my_ch in NAT_CHAINS.values():
        out.append(f':{my_ch} - [0:0]')
        out.append(f'-F {my_ch}')
    for sys_ch, my_ch in NAT_CHAINS.values():
        out.append(f'-A {sys_ch} -j {my_ch}')

    for rule in nat_qs:
        pair = _nat_args(rule)
        if not pair:
            continue
        chain, args = pair
        _sys_ch, my_ch = NAT_CHAINS[chain]
        out.append(f'-A {my_ch} ' + _join_args(args))

    out.append('COMMIT')
    out.append('')
    return '\n'.join(out) + '\n'


def _binary(family: str) -> tuple[str, str]:
    if family == 'ipv6':
        return 'ip6tables', 'ip6tables-restore'
    return 'iptables', 'iptables-restore'


def _run(argv: list[str], *, stdin: str | None = None, timeout: int = 10):
    full = _cmd_prefix() + argv
    if stdin is None:
        return subprocess_util.run(full, timeout=timeout)
    # 需要 stdin 时直接用底层 subprocess（subprocess_util 不支持 stdin）
    import subprocess
    if not subprocess_util.subprocess_allowed():
        from interfacemanage.services.subprocess_util import CmdResult

        return CmdResult(ok=False, exit_code=-1, stdout='', stderr='subprocess disabled')
    try:
        proc = subprocess.run(
            full, input=stdin, capture_output=True, text=True, timeout=timeout, check=False
        )
        from interfacemanage.services.subprocess_util import CmdResult

        return CmdResult(
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=proc.stdout or '',
            stderr=proc.stderr or '',
        )
    except Exception as exc:  # noqa: BLE001
        from interfacemanage.services.subprocess_util import CmdResult

        return CmdResult(ok=False, exit_code=-1, stdout='', stderr=str(exc))


def _purge_existing_jumps(bin_name: str, steps: list[dict[str, Any]]) -> None:
    """幂等地把系统 chain 上指向我们自定义 chain 的 jump 全部删干净。"""
    for sys_ch, my_ch in list(FILTER_CHAINS.values()) + list(NAT_CHAINS.values()):
        for _ in range(10):  # 最多删 10 条防御
            extra = ['-t', 'nat'] if my_ch.startswith('PEMANAGER_NAT_') else []
            r = _run([bin_name, *extra, '-D', sys_ch, '-j', my_ch])
            if not r.ok:
                break
            steps.append(
                {'step': f'purge -D {sys_ch} -j {my_ch}', 'ok': True, 'cmd': f'{bin_name} {" ".join(extra)} -D {sys_ch} -j {my_ch}'}
            )


def apply_ruleset(*, phase: Phase = 'apply') -> dict[str, Any]:
    if phase == 'preview':
        return {
            'ok': True,
            'phase': phase,
            'engine': 'iptables',
            'ruleset': render_ruleset(family='ipv4'),
            'ruleset_ipv6': render_ruleset(family='ipv6'),
        }

    if not getattr(settings, 'FIREWALLMANAGE_APPLY_ENABLED', False):
        return {
            'ok': False,
            'error': '防火墙下发已关闭（settings.FIREWALLMANAGE_APPLY_ENABLED）',
            'hint': '请设置 FIREWALLMANAGE_APPLY_ENABLED=1 并重启后端',
            'engine': 'iptables',
            'steps': [],
            'ruleset': render_ruleset(family='ipv4'),
            'ruleset_ipv6': render_ruleset(family='ipv6'),
        }

    steps: list[dict[str, Any]] = []
    rs4 = render_ruleset(family='ipv4')
    rs6 = render_ruleset(family='ipv6')

    if phase == 'flush':
        for bin_name in ('iptables', 'ip6tables'):
            _purge_existing_jumps(bin_name, steps)
            for table in ('filter', 'nat'):
                for sys_ch, my_ch in (FILTER_CHAINS.values() if table == 'filter' else NAT_CHAINS.values()):
                    r = _run([bin_name, '-t', table, '-F', my_ch])
                    steps.append(
                        {
                            'step': f'{bin_name} -t {table} -F {my_ch}',
                            'ok': r.ok or 'No chain' in (r.stderr or ''),
                            'stderr': r.stderr,
                        }
                    )
                    r = _run([bin_name, '-t', table, '-X', my_ch])
                    steps.append(
                        {
                            'step': f'{bin_name} -t {table} -X {my_ch}',
                            'ok': r.ok or 'No chain' in (r.stderr or ''),
                            'stderr': r.stderr,
                        }
                    )
        return {'ok': all(s['ok'] for s in steps), 'phase': 'flush', 'engine': 'iptables', 'steps': steps}

    for family, rs in (('ipv4', rs4), ('ipv6', rs6)):
        bin_name, restore_bin = _binary(family)
        # 校验
        chk = _run([restore_bin, '--test'], stdin=rs)
        steps.append(
            {
                'step': f'{restore_bin} --test ({family})',
                'ok': chk.ok,
                'stderr': chk.stderr,
                'stdout': chk.stdout,
            }
        )
        if not chk.ok:
            _record_last(False, f'{restore_bin} --test 失败: {chk.stderr[:200]}')
            return {
                'ok': False,
                'error': f'{restore_bin} --test 失败 ({family})',
                'engine': 'iptables',
                'steps': steps,
                'ruleset': rs4,
                'ruleset_ipv6': rs6,
            }

    if phase == 'validate':
        return {
            'ok': True,
            'phase': 'validate',
            'engine': 'iptables',
            'steps': steps,
            'ruleset': rs4,
            'ruleset_ipv6': rs6,
        }

    # 真正下发：先清除系统 chain 上重复的跳转，再 restore
    for family, rs in (('ipv4', rs4), ('ipv6', rs6)):
        bin_name, restore_bin = _binary(family)
        _purge_existing_jumps(bin_name, steps)
        # restore 不要 --noflush：让自定义 chain 内规则全量替换；系统 chain 上的其它规则保留
        app = _run([restore_bin], stdin=rs)
        steps.append(
            {
                'step': f'{restore_bin} ({family})',
                'ok': app.ok,
                'stderr': app.stderr,
                'stdout': app.stdout,
            }
        )
        if not app.ok:
            _record_last(False, f'{restore_bin} 应用失败: {app.stderr[:200]}')
            return {
                'ok': False,
                'error': f'{restore_bin} 应用失败 ({family})',
                'engine': 'iptables',
                'steps': steps,
                'ruleset': rs4,
                'ruleset_ipv6': rs6,
            }

    _record_last(True, f'apply ok (ipv4={len(rs4)}B, ipv6={len(rs6)}B)')
    return {
        'ok': True,
        'phase': 'apply',
        'engine': 'iptables',
        'steps': steps,
        'ruleset': rs4,
        'ruleset_ipv6': rs6,
    }


def show_ruleset() -> dict[str, Any]:
    out: dict[str, Any] = {'engine': 'iptables', 'tables': {}}
    for family in ('ipv4', 'ipv6'):
        bin_name, _ = _binary(family)
        for table in ('filter', 'nat'):
            r = _run([bin_name, '-t', table, '-S'])
            out['tables'][f'{bin_name} -t {table}'] = {
                'ok': r.ok,
                'exit_code': r.exit_code,
                'stderr': r.stderr,
                'stdout': r.stdout,
            }
    out['ok'] = any(v['ok'] for v in out['tables'].values())
    return out


def _record_last(ok: bool, summary: str) -> None:
    from django.utils import timezone

    s = FirewallSettings.load()
    s.last_apply_at = timezone.now()
    s.last_apply_ok = bool(ok)
    s.last_apply_summary = summary[:512]
    s.save(update_fields=['last_apply_at', 'last_apply_ok', 'last_apply_summary'])
