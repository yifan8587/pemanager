"""
将 DesiredRouteConfig 写入 netplan 路由片段并执行 netplan generate / netplan try。
复用 interfacemanage 的 netplan 命令前缀、子进程与超时策略。

注意：netplan 对 /etc/netplan/*.yaml 做的是「逐文件解析 + 校验 + 合并」。
某些 section 在「逐文件」阶段就有必填字段，例如 `tunnels.<if>` 必须带 `mode`。
因此把 routes 单独写到独立片段时，**必须把该接口最小可校验的规格一并写入**，
否则即便其他文件已定义 `mode: gre`，本文件仍会被拒绝。
"""
from __future__ import annotations

import copy
from typing import Any, Literal

import yaml
from django.conf import settings

from interfacemanage.models import DesiredTunnelConfig
from interfacemanage.services import netplan as netplan_loader
from interfacemanage.services.netplan_writing import _run, _write_netplan_file
from routemanage.models import DesiredRouteConfig

ApplyPhase = Literal['full', 'validate', 'try']

# tunnels 段最少需要的字段集合（按 mode 分桶）
_TUNNEL_MIN_FIELDS: dict[str, frozenset[str]] = {
    'gre': frozenset({'mode', 'local', 'remote'}),
    'gretap': frozenset({'mode', 'local', 'remote'}),
    'ip6gre': frozenset({'mode', 'local', 'remote'}),
    'ip6gretap': frozenset({'mode', 'local', 'remote'}),
    'sit': frozenset({'mode', 'local', 'remote'}),
    'ipip': frozenset({'mode', 'local', 'remote'}),
    'ip6ip6': frozenset({'mode', 'local', 'remote'}),
    'vxlan': frozenset({'mode', 'id'}),
    'wireguard': frozenset({'mode', 'keys'}),
}

_TUNNEL_FIELD_WHITELIST: frozenset[str] = frozenset(
    {
        'mode',
        'local',
        'remote',
        'addresses',
        'mtu',
        'ttl',
        'mark',
        'port',
        'id',
        'key',
        'input-key',
        'output-key',
        'keys',
        'peers',
        'listen-port',
        'listen_port',
        'renderer',
    }
)


def _tunnel_spec_from_db(ifname: str) -> dict[str, Any] | None:
    """从 DesiredTunnelConfig 读取非 WG 隧道的最小 netplan 规格。"""
    obj = DesiredTunnelConfig.objects.filter(ifname=ifname).first()
    if obj is None:
        return None
    if obj.kind == DesiredTunnelConfig.Kind.WIREGUARD:
        return None
    spec = (obj.spec or {}).get('netplan_tunnel') or {}
    return copy.deepcopy(spec) if isinstance(spec, dict) else None


def _is_wireguard_ifname(ifname: str) -> bool:
    return DesiredTunnelConfig.objects.filter(
        ifname=ifname, kind=DesiredTunnelConfig.Kind.WIREGUARD
    ).exists()


def _tunnel_spec_from_live(ifname: str) -> dict[str, Any] | None:
    """回退：从当前 /etc/netplan 读取该接口的 tunnels 段。"""
    try:
        bundle = netplan_loader.load_netplan()
    except Exception:
        return None
    merged = (bundle.get('merged_network') or {}).get('tunnels') or {}
    if not isinstance(merged, dict):
        return None
    s = merged.get(ifname)
    if isinstance(s, dict):
        return copy.deepcopy(s)
    return None


def _minimal_tunnel_spec(ifname: str) -> dict[str, Any] | None:
    """为 tunnels.<ifname> 寻找一份「可通过 netplan 校验」的最小规格。"""
    spec = _tunnel_spec_from_db(ifname) or _tunnel_spec_from_live(ifname)
    if not isinstance(spec, dict) or not spec:
        return None
    out: dict[str, Any] = {}
    for k, v in spec.items():
        if k in _TUNNEL_FIELD_WHITELIST and v not in (None, '', [], {}):
            out[k] = v
    mode = str(out.get('mode') or '').lower()
    required = _TUNNEL_MIN_FIELDS.get(mode)
    if not mode or not required:
        return None
    if not required.issubset(out.keys()):
        return None
    return out


def build_route_network() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    按 netplan 设备类与接口名聚合 routes，并在 tunnels 段补齐必填规格。
    返回 (network_dict, skipped_warnings)；skipped_warnings 是因为缺失上下文而被跳过的接口列表。

    注意：本函数**仅处理非 WireGuard 接口**的路由；WG 接口的路由通过 `ip route` 单独下发，
    避免把 WG 私钥（keys.private）冗余写入 routemanage 片段。
    """
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    pending_tunnels: set[str] = set()
    warnings: list[dict[str, Any]] = []

    for obj in DesiredRouteConfig.objects.all().order_by('interface_name', 'dest_cidr', 'id'):
        dclass = obj.netplan_device_class
        ifname = (obj.interface_name or '').strip()
        if not ifname:
            continue
        if _is_wireguard_ifname(ifname):
            warnings.append(
                {
                    'ifname': ifname,
                    'section': 'wireguard',
                    'reason': (
                        '该接口为 WireGuard，已从 netplan 路由片段中排除；'
                        '请在「路由配置 → 下发 WireGuard 路由」中以 `ip route` 单独下发。'
                    ),
                }
            )
            continue
        dest = (obj.dest_cidr or '').strip()
        if not dest:
            continue
        if dclass not in grouped:
            grouped[dclass] = {}
        if ifname not in grouped[dclass]:
            grouped[dclass][ifname] = {'routes': []}

        entry: dict[str, Any] = {'to': dest}
        if obj.gateway:
            entry['via'] = str(obj.gateway)
        if obj.on_link:
            entry['on-link'] = True
        if obj.metric is not None:
            entry['metric'] = int(obj.metric)
        if obj.route_table is not None:
            entry['table'] = int(obj.route_table)
        grouped[dclass][ifname]['routes'].append(entry)
        if dclass == DesiredRouteConfig.NetplanDeviceClass.TUNNELS:
            pending_tunnels.add(ifname)

    tunnels_block = grouped.get(DesiredRouteConfig.NetplanDeviceClass.TUNNELS) or {}
    for ifname in list(pending_tunnels):
        base = _minimal_tunnel_spec(ifname)
        if not base:
            warnings.append(
                {
                    'ifname': ifname,
                    'section': 'tunnels',
                    'reason': (
                        '未找到该隧道接口的完整规格（DesiredTunnelConfig / 已生效 netplan 均无），'
                        '为避免写入会被 netplan 拒绝的不完整片段，已跳过其路由。'
                        '请先在「隧道接口配置」中创建/下发该接口，再下发路由。'
                    ),
                }
            )
            tunnels_block.pop(ifname, None)
            continue
        existing = tunnels_block.get(ifname) or {}
        merged_entry = {**base, **existing}
        tunnels_block[ifname] = merged_entry

    network: dict[str, Any] = {'version': 2}
    for dclass, devices in grouped.items():
        if dclass == DesiredRouteConfig.NetplanDeviceClass.TUNNELS:
            devices = {k: v for k, v in (tunnels_block or {}).items() if v}
        if devices:
            network[dclass] = devices
    return network, warnings


def render_route_fragment_yaml() -> tuple[str, list[dict[str, Any]]]:
    network, warnings = build_route_network()
    body = yaml.safe_dump(
        {'network': network},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return body, warnings


def preview_desired_routes_yaml() -> dict[str, Any]:
    """仅生成将要写入片段的 YAML，不写磁盘、不调用 netplan。"""
    try:
        body, warnings = render_route_fragment_yaml()
        return {'ok': True, 'yaml': body, 'warnings': warnings}
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': f'生成路由 YAML 失败: {exc}'}


def apply_desired_routes_immediate(ids: list[str] | set[str]) -> dict[str, Any]:
    """
    选择性下发：仅对给定 id 集合中的非 WG 路由意图用 `ip route replace` 直接下发到内核，
    不写入 netplan fragment、不执行 netplan generate / try，因此完全不影响其它接口与路由。

    持久化由后续的全量 `apply_desired_routes_netplan(phase='full')` 处理。
    """
    from routemanage.models import DesiredRouteConfig
    from interfacemanage.models import DesiredTunnelConfig

    id_set = {str(i) for i in (ids or [])}
    if not id_set:
        return {'ok': True, 'steps': [], 'message': '选中集合为空'}
    qs = list(DesiredRouteConfig.objects.filter(id__in=id_set).order_by('interface_name', 'dest_cidr', 'id'))
    wg_set = set(
        DesiredTunnelConfig.objects.filter(kind=DesiredTunnelConfig.Kind.WIREGUARD).values_list('ifname', flat=True)
    )
    steps: list[dict[str, Any]] = []
    applied: list[str] = []
    failed: list[dict[str, Any]] = []
    for r in qs:
        ifn = (r.interface_name or '').strip()
        if ifn in wg_set:
            steps.append({
                'step': 'skip',
                'id': str(r.id),
                'reason': f'接口 {ifn} 为 WireGuard，请通过「下发 WireGuard 路由」入口',
            })
            continue
        # 选择 -4 / -6
        try:
            import ipaddress as _ip
            if (r.dest_cidr or '').strip().lower() == 'default':
                fam = '-4'
            else:
                net = _ip.ip_network(r.dest_cidr, strict=False)
                fam = '-6' if net.version == 6 else '-4'
        except Exception:
            fam = '-4'
        argv = ['ip', fam, 'route', 'replace', r.dest_cidr]
        if r.gateway:
            argv += ['via', str(r.gateway)]
        argv += ['dev', ifn]
        if r.metric is not None:
            argv += ['metric', str(int(r.metric))]
        if r.route_table is not None:
            argv += ['table', str(int(r.route_table))]
        res = _run(argv, timeout_kind='apply')
        steps.append({
            'step': 'ip route replace',
            'id': str(r.id),
            'argv': argv,
            'ok': res.ok,
            'stderr': res.stderr,
        })
        if res.ok:
            applied.append(str(r.id))
        else:
            failed.append({'id': str(r.id), 'argv': argv, 'stderr': res.stderr})
    return {
        'ok': not failed,
        'applied': applied,
        'failed': failed,
        'steps': steps,
        'note': '本次仅对选中路由用 ip route replace 即时下发；如需持久化请执行全量下发',
    }


def apply_desired_routes_netplan(
    *,
    phase: ApplyPhase | str = 'full',
    ids: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """
    phase:
    - validate: 写入片段 + netplan generate（校验合并配置）
    - try: 仅 netplan try（依赖磁盘上已是上一轮 validate 写入的片段）
    - full: 写入 + generate + try

    ids:
    - 若提供（非 None），改走 `apply_desired_routes_immediate(ids)`：
      仅对选中条目执行 `ip route replace` 即时生效；不动 netplan，不影响其它路由。
    - 若为 None：维持原有的全量 netplan generate+try（持久化）。
    """
    if ids is not None:
        return apply_desired_routes_immediate(ids)
    phase_l = (phase or 'full').lower()
    if phase_l not in {'full', 'validate', 'try'}:
        return {'ok': False, 'error': f'未知 phase: {phase!r}，可选 full / validate / try', 'steps': []}

    if not getattr(settings, 'ROUTEMANAGE_NETPLAN_WRITE_ENABLED', False):
        return {
            'ok': False,
            'error': '路由 netplan 写入已关闭（settings.ROUTEMANAGE_NETPLAN_WRITE_ENABLED）',
            'steps': [],
        }

    path = str(
        getattr(
            settings,
            'ROUTEMANAGE_NETPLAN_FRAGMENT_FILE',
            '/etc/netplan/99-pemanager-routes.yaml',
        )
    )
    steps: list[dict[str, Any]] = []
    body = ''
    warnings: list[dict[str, Any]] = []

    try:
        body, warnings = render_route_fragment_yaml()
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': f'生成路由 YAML 失败: {exc}', 'steps': steps}

    if warnings:
        steps.append({'step': 'preflight', 'ok': True, 'warnings': warnings})

    if phase_l in {'full', 'validate'}:
        try:
            _write_netplan_file(
                path,
                '# Generated by PE Manager — desired static routes\n',
                body,
            )
            steps.append({'step': 'write routes fragment', 'path': path, 'ok': True})
        except OSError as exc:
            steps.append({'step': 'write routes fragment', 'path': path, 'ok': False, 'stderr': str(exc)})
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
            return {
                'ok': False,
                'error': 'netplan generate 失败',
                'steps': steps,
                'yaml_preview': body,
            }

        if phase_l == 'validate':
            return {
                'ok': True,
                'phase': 'validate',
                'steps': steps,
                'yaml_preview': body,
                'warnings': warnings,
            }

    try_timeout = int(getattr(settings, 'ROUTEMANAGE_NETPLAN_TRY_TIMEOUT', 120))
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

    if try_res.ok:
        return {
            'ok': True,
            'phase': phase_l,
            'steps': steps,
            'yaml_preview': body,
            'warnings': warnings,
        }

    return {
        'ok': False,
        'error': 'netplan try 失败或超时；已尝试回滚（以 netplan 行为为准）',
        'steps': steps,
        'yaml_preview': body,
        'warnings': warnings,
    }
