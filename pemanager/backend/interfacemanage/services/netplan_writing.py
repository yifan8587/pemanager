"""
将 DesiredTunnelConfig 写入 netplan 片段并调用 netplan 校验与 try/apply。
GRE/VXLAN 由 netplan try 生效；WireGuard 由 python-wireguard 写入内核，并另写符合 netplan 语法的持久化片段。
"""
from __future__ import annotations

import copy
import os
import subprocess
from typing import Any

import yaml
from django.conf import settings

from interfacemanage.models import DesiredTunnelConfig
from interfacemanage.services import wireguard_apply


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


def build_netplan_tunnels_gre_vxlan() -> dict[str, Any]:
    """仅 GRE / VXLAN，供主 netplan 片段（避免把前端结构化的 WG 字段原样写入导致 netplan 不兼容）。"""
    tunnels: dict[str, Any] = {}
    for obj in DesiredTunnelConfig.objects.all().order_by('ifname'):
        if obj.kind == DesiredTunnelConfig.Kind.WIREGUARD:
            continue
        name = (obj.ifname or '').strip()
        if not name:
            continue
        spec = obj.spec or {}
        t = copy.deepcopy(spec.get('netplan_tunnel') or {})
        if not t:
            continue
        t.setdefault('mode', obj.kind)
        addr = t.get('addresses')
        if isinstance(addr, str) and addr.strip():
            t['addresses'] = [addr.strip()]
        elif isinstance(addr, list):
            t['addresses'] = [str(a).strip() for a in addr if str(a).strip()]
            if not t['addresses']:
                t.pop('addresses', None)
        tunnels[name] = t
    return {'version': 2, 'tunnels': tunnels}


def render_gre_vxlan_fragment_yaml() -> str:
    frag = {'network': build_netplan_tunnels_gre_vxlan()}
    return yaml.safe_dump(
        frag,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


def _write_netplan_file(path: str, header: str, body: str) -> dict[str, Any]:
    os.makedirs(os.path.dirname(path) or '.', mode=0o755, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(header)
        fh.write(body)
        if not body.endswith('\n'):
            fh.write('\n')
    return {'path': path, 'ok': True}


def render_empty_wireguard_stub_yaml() -> str:
    return yaml.safe_dump(
        {'network': {'version': 2, 'tunnels': {}}},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


def apply_desired_tunnels_netplan(
    *,
    ids: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """
    隧道意图统一下发：
      A. GRE / VXLAN：写 netplan 片段 → netplan generate → netplan try
      B. WireGuard ：清空遗留 netplan 持久化文件（避免 systemd-networkd 与 wg-quick 并发管理同一接口），
                     然后 `wg-quick down/up` 重建接口（wireguard_apply.apply_all_desired_wireguard）。
                     conf 由 PE Manager 完整渲染，路由块由 routemanage 注入；
                     `wg show <if>` 在下发完成后即与 conf 一致。

    参数：
      ids:
        若为 None（默认）：全量下发（含 GRE/VXLAN netplan generate+try、WG 全部重启）。
        若给定列表：
          - 选中集合中若包含 GRE/VXLAN：仍写完整 fragment 并 generate + try（netplan 设计无法
            部分下发，但 netplan try 仅 reload 差异接口，不会重启已经正常的其他接口）；
          - 选中集合中若仅包含 WireGuard：跳过 netplan generate/try，只对选中 WG 接口
            执行 `wg-quick down/up`，避免一次性中断所有 WG 业务；
          - 选中集合为空：直接返回。
    """
    if not getattr(settings, 'INTERFACEMANAGE_NETPLAN_WRITE_ENABLED', False):
        return {
            'ok': False,
            'error': '写入 netplan 已关闭（settings.INTERFACEMANAGE_NETPLAN_WRITE_ENABLED）',
            'steps': [],
        }

    qs = list(DesiredTunnelConfig.objects.all().order_by('ifname'))
    selected_ids: set[str] | None = None
    if ids is not None:
        selected_ids = {str(i) for i in ids}
        if not selected_ids:
            return {'ok': True, 'steps': [], 'message': '选中集合为空，未执行下发'}
    sel_kinds = (
        {o.kind for o in qs if str(o.id) in selected_ids} if selected_ids is not None else None
    )
    only_wg = (
        sel_kinds is not None and sel_kinds.issubset({DesiredTunnelConfig.Kind.WIREGUARD})
    )

    # 校验仅校验"参与本次下发"的接口，避免历史脏数据阻塞
    qs_for_validate = qs if selected_ids is None else [o for o in qs if str(o.id) in selected_ids]
    for obj in qs_for_validate:
        spec = obj.spec or {}
        t = spec.get('netplan_tunnel') or {}
        addrs = t.get('addresses')
        ok_addr = False
        if isinstance(addrs, str) and addrs.strip():
            ok_addr = True
        elif isinstance(addrs, list) and any(str(a).strip() for a in addrs):
            ok_addr = True
        if not ok_addr:
            return {
                'ok': False,
                'error': f'隧道 {obj.ifname} 缺少本端地址/掩码（addresses，CIDR 如 10.0.0.1/24）',
                'steps': [],
            }

    # 选中集合仅含 WireGuard 时，跳过 netplan generate/try，避免不必要的影响面
    if only_wg:
        steps: list[dict[str, Any]] = [{
            'step': 'skip-netplan',
            'reason': '本次仅下发 WireGuard 接口，跳过 GRE/VXLAN netplan generate+try',
        }]
        wg_live = wireguard_apply.apply_all_desired_wireguard(qs, ids=selected_ids)
        steps.append({'step': 'wg-quick apply', **wg_live})
        return {
            'ok': bool(wg_live.get('ok')),
            'steps': steps,
            'selected_ids': sorted(selected_ids or []),
        }

    path = str(
        getattr(settings, 'INTERFACEMANAGE_NETPLAN_FRAGMENT_FILE', '/etc/netplan/99-pemanager-tunnels.yaml')
    )
    wg_path = str(
        getattr(
            settings,
            'INTERFACEMANAGE_NETPLAN_WG_FRAGMENT_FILE',
            '/etc/netplan/99-pemanager-wireguard.yaml',
        )
    )
    steps: list[dict[str, Any]] = []

    try:
        body_gv = render_gre_vxlan_fragment_yaml()
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': f'生成 GRE/VXLAN YAML 失败: {exc}', 'steps': steps}

    # 清空遗留 WG 持久化 netplan（写入空 stub），让 netplan 不再管理 WG 接口
    stub = render_empty_wireguard_stub_yaml()
    writes: list[tuple[str, str, str]] = [
        (wg_path, '# Generated by PE Manager — wireguard handled by wg-quick (no netplan persistence)\n', stub),
        (path, '# Generated by PE Manager — gre/vxlan tunnels\n', body_gv),
    ]
    for fpath, header, content in writes:
        try:
            _write_netplan_file(fpath, header, content)
            steps.append({'step': f'write {fpath}', 'path': fpath, 'ok': True})
        except OSError as exc:
            steps.append({'step': f'write {fpath}', 'path': fpath, 'ok': False, 'stderr': str(exc)})
            return {'ok': False, 'error': f'写入 {fpath} 失败: {exc}', 'steps': steps, 'yaml_preview': content}

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
        return {
            'ok': False,
            'error': 'netplan generate 失败',
            'steps': steps,
            'yaml_preview': body_gv,
        }

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
            'error': 'netplan try 失败或超时；配置未确认为长期生效，已尝试回滚（以 netplan 行为为准）',
            'steps': steps,
            'yaml_preview': body_gv,
        }

    # WireGuard：交给 wg-quick（写 conf → wg-quick down/up），不再写 netplan 持久化片段
    wg_live = wireguard_apply.apply_all_desired_wireguard(qs, ids=selected_ids)
    steps.append({'step': 'wg-quick apply', **wg_live})
    if not wg_live.get('ok'):
        return {
            'ok': False,
            'error': 'WireGuard 下发失败（详见 steps 中 wg-quick apply）',
            'steps': steps,
            'yaml_preview': body_gv,
        }

    return {
        'ok': True,
        'steps': steps,
        'yaml_preview': body_gv,
    }
