"""防火墙服务状态探测与控制（systemctl + nft / iptables 版本）。"""
from __future__ import annotations

import shlex
from typing import Any

from django.conf import settings

from firewallmanage.models import FirewallRule, FirewallSettings, NATRule
from interfacemanage.services import subprocess_util


def _cmd_prefix() -> list[str]:
    raw = getattr(settings, 'FIREWALLMANAGE_CMD_PREFIX', '')
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str) and raw.strip():
        return shlex.split(raw)
    return []


def _systemctl(args: list[str]) -> dict[str, Any]:
    r = subprocess_util.run(_cmd_prefix() + ['systemctl', *args], timeout=8)
    return {'ok': r.ok, 'exit_code': r.exit_code, 'stdout': (r.stdout or '').strip(), 'stderr': r.stderr}


def _read_service(unit: str) -> dict[str, Any]:
    act = _systemctl(['is-active', unit])
    en = _systemctl(['is-enabled', unit])
    return {
        'unit': unit,
        'active': act['stdout'] == 'active',
        'active_state': act['stdout'] or act['stderr'].strip(),
        'enabled': en['stdout'] in ('enabled', 'alias', 'static'),
        'enabled_state': en['stdout'] or en['stderr'].strip(),
    }


def _bin_version(argv: list[str]) -> str:
    r = subprocess_util.run(argv, timeout=4)
    if r.ok:
        return (r.stdout or '').strip().splitlines()[0] if r.stdout else ''
    return ''


def status() -> dict[str, Any]:
    s = FirewallSettings.load()
    return {
        'engine': s.engine,
        'policies': {
            'input': s.policy_input,
            'output': s.policy_output,
            'forward': s.policy_forward,
        },
        'apply_enabled': bool(getattr(settings, 'FIREWALLMANAGE_APPLY_ENABLED', False)),
        'subprocess_enabled': subprocess_util.subprocess_allowed(),
        'last_apply_at': s.last_apply_at.isoformat() if s.last_apply_at else None,
        'last_apply_ok': bool(s.last_apply_ok),
        'last_apply_summary': s.last_apply_summary or '',
        'counts': {
            'filter_rules_total': FirewallRule.objects.count(),
            'filter_rules_enabled': FirewallRule.objects.filter(enabled=True).count(),
            'nat_rules_total': NATRule.objects.count(),
            'nat_rules_enabled': NATRule.objects.filter(enabled=True).count(),
        },
        'services': {
            'nftables': _read_service('nftables'),
            'netfilter-persistent': _read_service('netfilter-persistent'),
        },
        'bins': {
            'nft': _bin_version(['nft', '--version']),
            'iptables': _bin_version(['iptables', '--version']),
            'ip6tables': _bin_version(['ip6tables', '--version']),
        },
    }


ALLOWED_UNITS = {'nftables', 'netfilter-persistent'}
ALLOWED_ACTIONS = {'start', 'stop', 'restart', 'reload', 'enable', 'disable'}


def control(unit: str, action: str) -> dict[str, Any]:
    """systemctl <action> <unit>，仅允许白名单。"""
    if unit not in ALLOWED_UNITS:
        return {'ok': False, 'error': f'unit 不在白名单：{unit}', 'allowed': sorted(ALLOWED_UNITS)}
    if action not in ALLOWED_ACTIONS:
        return {'ok': False, 'error': f'action 不允许：{action}', 'allowed': sorted(ALLOWED_ACTIONS)}
    res = _systemctl([action, unit])
    post = _read_service(unit)
    return {'ok': res['ok'], 'action': action, 'unit': unit, 'result': res, 'service': post}
