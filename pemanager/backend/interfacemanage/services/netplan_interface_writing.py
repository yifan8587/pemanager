"""
将单个接口的「接口配置」写入到 pemanager 管辖的 netplan 文件 ——
`/etc/netplan/90-pemanager-iface-<ifname>.yaml`，然后调用 netplan generate + netplan try 下发。
成功后由调用方触发 sync_network_state_from_system() 回写数据库。

支持的 kind:
  - ether/ethernet → ethernets
  - bridge        → bridges
  - bond          → bonds
  - vlan          → vlans
  - gre/vxlan     → tunnels
（wireguard 已由 DesiredTunnelConfig 与 wireguard_apply 处理，本服务拒绝处理。）
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Any

import yaml
from django.conf import settings


_KIND_SECTION = {
    'ether': 'ethernets',
    'ethernet': 'ethernets',
    'bridge': 'bridges',
    'bond': 'bonds',
    'vlan': 'vlans',
    'gre': 'tunnels',
    'gretap': 'tunnels',
    'vxlan': 'tunnels',
    'ip6gre': 'tunnels',
    'geneve': 'tunnels',
}

_SAFE_IFNAME = re.compile(r'^[A-Za-z0-9._@:-]{1,64}$')

# Netplan 通用允许字段（按 kind 过滤后写入；未列入的字段会被忽略，避免误写底层字段）
_COMMON_FIELDS = {
    'renderer', 'addresses', 'mtu', 'dhcp4', 'dhcp6', 'gateway4', 'gateway6',
    'optional', 'nameservers', 'routes', 'macaddress',
}
_EXTRA_BY_SECTION: dict[str, set[str]] = {
    'ethernets': set(),
    'bridges': {'interfaces', 'parameters'},
    'bonds': {'interfaces', 'parameters'},
    'vlans': {'id', 'link'},
    'tunnels': {'mode', 'local', 'remote', 'key', 'ttl', 'mark', 'port', 'id'},
}


class _CmdResult:
    __slots__ = ('ok', 'returncode', 'stdout', 'stderr')

    def __init__(self, ok: bool, returncode: int, stdout: str, stderr: str):
        self.ok = ok
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _cmd_prefix() -> list[str]:
    prefix = getattr(settings, 'INTERFACEMANAGE_NETPLAN_CMD_PREFIX', None) or []
    return [str(x) for x in prefix]


def _timeout(kind: str) -> int:
    if kind == 'apply':
        return int(getattr(settings, 'INTERFACEMANAGE_NETPLAN_APPLY_TIMEOUT', 180))
    return int(getattr(settings, 'INTERFACEMANAGE_COMMAND_TIMEOUT', 30))


def _run(argv: list[str], *, input_text: str | None = None, timeout_kind: str = 'apply') -> _CmdResult:
    if not getattr(settings, 'INTERFACEMANAGE_ALLOW_SUBPROCESS', False):
        return _CmdResult(False, -1, '', 'subprocess disabled (INTERFACEMANAGE_ALLOW_SUBPROCESS)')
    cmd = _cmd_prefix() + argv
    t = _timeout(timeout_kind)
    try:
        proc = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=t,
            check=False,
        )
        return _CmdResult(
            proc.returncode == 0,
            proc.returncode,
            proc.stdout or '',
            proc.stderr or '',
        )
    except subprocess.TimeoutExpired:
        return _CmdResult(False, -1, '', f'timeout ({t}s): {" ".join(cmd)}')
    except FileNotFoundError:
        return _CmdResult(False, -1, '', f'command not found: {cmd[0] if cmd else argv[0]}')
    except Exception as exc:  # noqa: BLE001
        return _CmdResult(False, -1, '', str(exc))


def _section_for_kind(kind: str) -> str | None:
    return _KIND_SECTION.get((kind or '').strip().lower())


def _managed_file_path(ifname: str) -> str:
    template = str(
        getattr(
            settings,
            'INTERFACEMANAGE_NETPLAN_IFACE_FILE_TEMPLATE',
            '/etc/netplan/90-pemanager-iface-{ifname}.yaml',
        )
    )
    return template.format(ifname=ifname)


def _filter_spec(section: str, spec: dict[str, Any]) -> dict[str, Any]:
    allowed = _COMMON_FIELDS | _EXTRA_BY_SECTION.get(section, set())
    out: dict[str, Any] = {}
    for k, v in (spec or {}).items():
        if k in allowed and v not in (None, '', [], {}):
            out[k] = v

    if section == 'tunnels':
        if 'mode' not in out and spec.get('mode'):
            out['mode'] = spec['mode']

    if section in ('bridges', 'bonds'):
        ifs = out.get('interfaces') or []
        out['interfaces'] = [str(x) for x in ifs if x]

    if 'addresses' in out:
        addrs = out['addresses']
        if isinstance(addrs, str):
            addrs = [addrs]
        out['addresses'] = [str(a).strip() for a in addrs if str(a).strip()]
        if not out['addresses']:
            out.pop('addresses', None)

    if 'nameservers' in out:
        ns = out['nameservers']
        if isinstance(ns, list):
            out['nameservers'] = {'addresses': [str(x) for x in ns if x]}
        elif isinstance(ns, dict):
            cleaned = {}
            if ns.get('addresses'):
                cleaned['addresses'] = [str(x) for x in ns['addresses'] if x]
            if ns.get('search'):
                cleaned['search'] = [str(x) for x in ns['search'] if x]
            if cleaned:
                out['nameservers'] = cleaned
            else:
                out.pop('nameservers', None)

    if 'routes' in out:
        out['routes'] = [
            {k2: v2 for k2, v2 in r.items() if v2 not in (None, '')}
            for r in out['routes']
            if isinstance(r, dict) and r.get('to')
        ]
        if not out['routes']:
            out.pop('routes', None)

    return out


def render_yaml(*, ifname: str, kind: str, spec: dict[str, Any]) -> dict[str, Any]:
    """生成单接口 netplan YAML（不写盘），便于前端 preview。"""
    if not _SAFE_IFNAME.match(ifname or ''):
        return {'ok': False, 'error': f'非法接口名: {ifname}'}
    section = _section_for_kind(kind)
    if not section:
        return {
            'ok': False,
            'error': f'不支持以 netplan 编辑的接口类型: {kind}（WireGuard 请前往 隧道接口配置）',
        }
    filtered = _filter_spec(section, spec or {})
    body = {
        'network': {
            'version': 2,
            section: {ifname: filtered},
        }
    }
    text = yaml.safe_dump(body, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return {
        'ok': True,
        'section': section,
        'filtered_spec': filtered,
        'yaml': text,
        'path': _managed_file_path(ifname),
    }


def _write_file(path: str, header: str, body: str) -> None:
    os.makedirs(os.path.dirname(path) or '.', mode=0o755, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(header)
        fh.write(body)
        if not body.endswith('\n'):
            fh.write('\n')


def apply_interface_netplan(*, ifname: str, kind: str, spec: dict[str, Any]) -> dict[str, Any]:
    """写盘 + netplan generate + netplan try。"""
    if not getattr(settings, 'INTERFACEMANAGE_NETPLAN_WRITE_ENABLED', False):
        return {
            'ok': False,
            'error': '写入 netplan 已关闭（settings.INTERFACEMANAGE_NETPLAN_WRITE_ENABLED）',
            'steps': [],
        }

    prev = render_yaml(ifname=ifname, kind=kind, spec=spec)
    if not prev.get('ok'):
        return {**prev, 'steps': []}

    path = prev['path']
    body = prev['yaml']
    steps: list[dict[str, Any]] = []

    header = f'# Generated by PE Manager — interface {ifname} ({prev["section"]})\n'
    try:
        _write_file(path, header, body)
        steps.append({'step': f'write {path}', 'path': path, 'ok': True})
    except OSError as exc:
        steps.append({'step': f'write {path}', 'path': path, 'ok': False, 'stderr': str(exc)})
        return {'ok': False, 'error': f'写入 {path} 失败: {exc}', 'steps': steps, 'yaml_preview': body}

    gen = _run(['netplan', 'generate'], timeout_kind='apply')
    steps.append(
        {
            'step': 'netplan generate',
            'ok': gen.ok,
            'returncode': gen.returncode,
            'stderr': gen.stderr,
            'stdout': gen.stdout,
        }
    )
    if not gen.ok:
        return {'ok': False, 'error': 'netplan generate 失败', 'steps': steps, 'yaml_preview': body}

    try_timeout = int(getattr(settings, 'INTERFACEMANAGE_NETPLAN_TRY_TIMEOUT', 120))
    try_timeout = max(10, min(try_timeout, 600))
    try_res = _run(
        ['netplan', 'try', '--timeout', str(try_timeout)],
        input_text='\n',
        timeout_kind='apply',
    )
    steps.append(
        {
            'step': 'netplan try',
            'ok': try_res.ok,
            'returncode': try_res.returncode,
            'stderr': try_res.stderr,
            'stdout': try_res.stdout,
            'timeout_sec': try_timeout,
        }
    )
    if not try_res.ok:
        return {
            'ok': False,
            'error': 'netplan try 失败或超时；配置未确认为长期生效（netplan 已尝试回滚）',
            'steps': steps,
            'yaml_preview': body,
        }

    return {
        'ok': True,
        'steps': steps,
        'yaml_preview': body,
        'path': path,
        'section': prev['section'],
    }


def remove_interface_netplan(*, ifname: str) -> dict[str, Any]:
    """删除 pemanager 为该接口托管的 netplan 文件，并触发一次 generate + try。"""
    if not getattr(settings, 'INTERFACEMANAGE_NETPLAN_WRITE_ENABLED', False):
        return {'ok': False, 'error': '写入 netplan 已关闭', 'steps': []}
    if not _SAFE_IFNAME.match(ifname or ''):
        return {'ok': False, 'error': f'非法接口名: {ifname}', 'steps': []}

    path = _managed_file_path(ifname)
    steps: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            os.remove(path)
            steps.append({'step': f'remove {path}', 'ok': True})
        else:
            steps.append({'step': f'remove {path}', 'ok': True, 'note': '文件不存在'})
    except OSError as exc:
        steps.append({'step': f'remove {path}', 'ok': False, 'stderr': str(exc)})
        return {'ok': False, 'error': f'删除 {path} 失败: {exc}', 'steps': steps}

    gen = _run(['netplan', 'generate'], timeout_kind='apply')
    steps.append({'step': 'netplan generate', 'ok': gen.ok, 'stderr': gen.stderr, 'stdout': gen.stdout})
    if not gen.ok:
        return {'ok': False, 'error': 'netplan generate 失败', 'steps': steps}

    try_timeout = int(getattr(settings, 'INTERFACEMANAGE_NETPLAN_TRY_TIMEOUT', 120))
    try_res = _run(['netplan', 'try', '--timeout', str(try_timeout)], input_text='\n', timeout_kind='apply')
    steps.append({'step': 'netplan try', 'ok': try_res.ok, 'stderr': try_res.stderr, 'stdout': try_res.stdout})
    if not try_res.ok:
        return {'ok': False, 'error': 'netplan try 失败或超时', 'steps': steps}

    return {'ok': True, 'steps': steps}
