"""
将 DesiredTunnelConfig（WireGuard 类型）渲染为 wg-quick 配置文件
（默认 /etc/wireguard/<接口名>.conf）并通过 `wg-quick down/up` 重建接口生效。

设计原则：
- 单一事实源：`/etc/wireguard/<if>.conf` 由 PE Manager 完整渲染并打上 `# PE Manager managed` 标记；
  内核中 `wg show <if>` 的输出与 conf 严格一致；
- 路由意图（routemanage）通过 PostUp/PostDown 注入到同一 conf 的 [Interface] 段内，
  wg-quick down/up 会自动执行；
- 不再用 python-wireguard 直接 setlink，也不再向 netplan 写 WG 持久化片段
  （避免 systemd-networkd 与 wg-quick 同时管理同一接口造成冲突）。

不负责 GRE/VXLAN；GRE/VXLAN 仍由 netplan_writing 生成 netplan 片段并 try。
"""
from __future__ import annotations

import ipaddress
import os
import re
from typing import Any

from django.conf import settings

from interfacemanage.models import DesiredTunnelConfig

WG_CONF_MANAGED_MARKER = '# PE Manager managed'


def _wg_apply_enabled() -> bool:
    explicit = getattr(settings, 'INTERFACEMANAGE_WG_APPLY_ENABLED', None)
    if explicit is not None:
        return bool(explicit)
    return bool(getattr(settings, 'INTERFACEMANAGE_WG_PYROUTE2_ENABLED', True))


def python_wireguard_available() -> bool:
    """保留以便其他模块/历史调用路径继续工作（如 keypair 生成）。"""
    try:
        from python_wireguard import Client, Key, Server  # noqa: F401
        from python_wireguard import delete_device  # noqa: F401

        return True
    except Exception:
        return False


def parse_endpoint(endpoint: str | None) -> tuple[str | None, int | None]:
    """host:port、IPv6 的 [addr]:port → (addr, port)。"""
    if not endpoint or not str(endpoint).strip():
        return None, None
    s = str(endpoint).strip()
    if s.startswith('['):
        end = s.find(']', 1)
        if end != -1 and len(s) > end + 1 and s[end + 1] == ':':
            port_s = s[end + 2 :]
            if port_s.isdigit():
                return s[1:end], int(port_s)
        return None, None
    if ':' in s:
        host, _, port_s = s.rpartition(':')
        if host and port_s.isdigit():
            return host, int(port_s)
    return None, None


def tunnel_dict_to_netplan_wireguard(t: dict[str, Any]) -> dict[str, Any]:
    """
    将前端/数据库存储的 netplan_tunnel 结构转为 netplan 文档中的字段名。
    """
    out: dict[str, Any] = {'mode': 'wireguard'}
    addr = t.get('addresses')
    if isinstance(addr, str) and addr.strip():
        out['addresses'] = [addr.strip()]
    elif isinstance(addr, list):
        out['addresses'] = [str(a).strip() for a in addr if str(a).strip()]
    keys = t.get('keys') or {}
    priv = keys.get('private') if isinstance(keys, dict) else None
    if priv:
        out['keys'] = {'private': str(priv).strip()}
    port = t.get('port')
    if port is None:
        port = t.get('listen_port')
    if port is not None and port != '':
        try:
            out['port'] = int(port)
        except (TypeError, ValueError):
            pass
    if t.get('mark') is not None and t.get('mark') != '':
        try:
            out['mark'] = int(t['mark'])
        except (TypeError, ValueError):
            pass

    peers_in = t.get('peers') or []
    peers_out: list[dict[str, Any]] = []
    for p in peers_in:
        if not isinstance(p, dict):
            continue
        pub = p.get('public_key') or (p.get('keys') or {}).get('public')
        if not pub:
            continue
        peer_yaml: dict[str, Any] = {'keys': {'public': str(pub).strip()}}
        psk = p.get('preshared_key') or (p.get('keys') or {}).get('shared')
        if psk:
            peer_yaml['keys']['shared'] = str(psk).strip()
        ep = p.get('endpoint')
        if ep:
            peer_yaml['endpoint'] = str(ep).strip()
        allowed = p.get('allowed_ips')
        if isinstance(allowed, str) and allowed.strip():
            peer_yaml['allowed-ips'] = [x.strip() for x in allowed.replace(',', ' ').split() if x.strip()]
        elif isinstance(allowed, list) and allowed:
            peer_yaml['allowed-ips'] = [str(x).strip() for x in allowed if str(x).strip()]
        ka = p.get('persistent_keepalive')
        if ka is None:
            ka = p.get('keepalive')
        if ka is not None and ka != '':
            try:
                peer_yaml['keepalive'] = int(ka)
            except (TypeError, ValueError):
                pass
        peers_out.append(peer_yaml)
    if peers_out:
        out['peers'] = peers_out
    return out


def build_wireguard_tunnels_netplan() -> dict[str, Any]:
    """供写入 99-pemanager-wireguard.yaml 的 tunnels 字典（字段符合 netplan）。"""
    tunnels: dict[str, Any] = {}
    for obj in DesiredTunnelConfig.objects.all().order_by('ifname'):
        if obj.kind != DesiredTunnelConfig.Kind.WIREGUARD:
            continue
        name = (obj.ifname or '').strip()
        if not name:
            continue
        spec = obj.spec or {}
        raw = spec.get('netplan_tunnel') or {}
        if not raw:
            continue
        tunnels[name] = tunnel_dict_to_netplan_wireguard(raw)
    return tunnels


def render_wireguard_netplan_yaml() -> str:
    import yaml

    frag = {'network': {'version': 2, 'tunnels': build_wireguard_tunnels_netplan()}}
    return yaml.safe_dump(
        frag,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


def _tunnel_from_obj(obj: DesiredTunnelConfig) -> dict[str, Any]:
    spec = obj.spec or {}
    return spec.get('netplan_tunnel') or {}


def _key_from_b64(label: str, raw: str) -> Any:
    from python_wireguard import Key

    t = str(raw).strip()
    if len(t) != 44:
        raise ValueError(f'{label} 须为 44 字符 WireGuard base64 密钥')
    return Key(t)


def _allowed_ips_list(p: dict[str, Any]) -> list[str]:
    allowed = p.get('allowed_ips')
    if isinstance(allowed, str) and allowed.strip():
        return [x.strip() for x in allowed.replace(',', ' ').split() if x.strip()]
    if isinstance(allowed, list):
        return [str(x).strip() for x in allowed if str(x).strip()]
    return []


def _peer_tunnel_ip_for_server(p: dict[str, Any]) -> str:
    ips = _allowed_ips_list(p)
    if not ips:
        raise ValueError(
            '「服务端」模式下每个 peer 必须配置 allowed_ips；python-wireguard 使用首条作为对端隧道地址'
        )
    first = ips[0]
    if first in ('0.0.0.0/0', '::/0'):
        raise ValueError(
            '「服务端」模式下 allowed_ips 不能仅为全网段；请写明对端隧道地址（例如 10.0.0.2/32）'
        )
    return first


def _should_use_client_mode(peers: list[dict[str, Any]]) -> bool:
    if len(peers) != 1:
        return False
    host, port = parse_endpoint(peers[0].get('endpoint'))
    return bool(host and port)


def _safe_delete_device(ifname: str) -> None:
    from python_wireguard import delete_device

    try:
        delete_device(ifname)
    except Exception:
        pass


def _add_extra_addresses(ifname: str, cidrs: list[str]) -> None:
    for cidr in cidrs:
        os.system(f'ip addr add dev {ifname} {cidr} 2>/dev/null')


def _wg_conf_safe_ifname(name: str) -> bool:
    return bool(name and re.match(r'^[A-Za-z0-9_-]+$', name))


_WG_KEY_RE = re.compile(r'^[A-Za-z0-9+/]{43}=$')


def _wg_derive_public_from_private(priv: str) -> str | None:
    """优先用系统 `wg pubkey`（更可靠且与内核一致）派生公钥；失败回退 python-wireguard。"""
    import subprocess

    s = (priv or '').strip()
    if not s:
        return None
    try:
        res = subprocess.run(
            ['wg', 'pubkey'],
            input=s + '\n',
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    try:
        from python_wireguard import Key

        k = Key(s)
        return str(k.public_key()) if hasattr(k, 'public_key') else None
    except Exception:  # noqa: BLE001
        return None


def _validate_wg_intent(ifname: str, t: dict[str, Any]) -> str | None:
    """
    渲染 conf 之前的语义校验。常见的"看似下发成功但 wg show 不一致"原因：
    - peer.public_key 与本端公钥相同 → 内核静默拒绝该 peer
    - 公钥/私钥不是合法 WG base64（44 字符）
    - 多个 peer 公钥重复
    - keys.public 与 keys.private 派生不一致（多半是录入错位）
    返回 None 表示校验通过；否则返回明确的错误描述。
    """
    keys = t.get('keys') or {}
    if not isinstance(keys, dict):
        return 'keys 字段必须是对象 {private, public}'
    priv = (keys.get('private') or '').strip()
    if not priv:
        return '缺少 keys.private（本端私钥）'
    if not _WG_KEY_RE.match(priv):
        return 'keys.private 不是合法的 WireGuard base64 密钥（应为 43 字符 base64 + "="）'

    declared_pub = (keys.get('public') or '').strip()
    derived_pub = _wg_derive_public_from_private(priv)
    if declared_pub and not _WG_KEY_RE.match(declared_pub):
        return 'keys.public 不是合法的 WireGuard base64 密钥'
    if declared_pub and derived_pub and declared_pub != derived_pub:
        return (
            'keys.public 与 keys.private 派生出的公钥不一致：'
            f'声明={declared_pub}；实际派生={derived_pub}。'
            '请点「由私钥推导」按钮重新填写本端公钥'
        )
    local_pub = derived_pub or declared_pub
    if not local_pub:
        return '无法确定本端公钥；请检查 keys.public 是否填写，或确认系统已安装 wireguard-tools (`wg pubkey`)'

    peers = [p for p in (t.get('peers') or []) if isinstance(p, dict)]
    if not peers:
        return '未配置任何 peer'

    seen: set[str] = set()
    for i, p in enumerate(peers, 1):
        pub = (p.get('public_key') or (p.get('keys') or {}).get('public') or '').strip()
        if not pub:
            return f'peer #{i} 缺少 public_key'
        if not _WG_KEY_RE.match(pub):
            return f'peer #{i} public_key 不是合法的 WireGuard base64 密钥'
        if pub == local_pub:
            return (
                f'peer #{i} public_key 与本端公钥相同（{pub}）。'
                '对端公钥应来自对端主机，不能填入本端自身公钥；'
                '内核会静默丢弃同公钥的 peer，导致 `wg show` 看不到该 peer'
            )
        if pub in seen:
            return f'存在重复的 peer public_key：{pub}'
        seen.add(pub)
        ep = p.get('endpoint')
        if ep and str(ep).strip():
            host, port = parse_endpoint(str(ep))
            if not host or not port:
                return f'peer #{i} endpoint 格式无效（应为 host:port 或 [ipv6]:port）：{ep}'

    return None


def _parse_wg_show_dump(text: str) -> dict[str, Any]:
    """
    解析 `wg show <if> dump` 输出：
    第一行  ：<private> <public> <listen_port> <fwmark>
    其余行  ：<public> <preshared> <endpoint> <allowed_ips> <latest_handshake> <rx> <tx> <persistent_keepalive>
    """
    out: dict[str, Any] = {'public_key': None, 'listen_port': None, 'peers': []}
    if not text:
        return out
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return out
    head = lines[0].split('\t')
    if len(head) >= 3:
        out['public_key'] = head[1] or None
        try:
            out['listen_port'] = int(head[2])
        except (TypeError, ValueError):
            out['listen_port'] = None
    for ln in lines[1:]:
        parts = ln.split('\t')
        if not parts:
            continue
        out['peers'].append(
            {
                'public_key': parts[0] if len(parts) > 0 else None,
                'endpoint': parts[2] if len(parts) > 2 and parts[2] != '(none)' else None,
                'allowed_ips': parts[3] if len(parts) > 3 else None,
            }
        )
    return out


def _check_kernel_consistency(ifname: str, t: dict[str, Any]) -> dict[str, Any]:
    """`wg show <if> dump` 与意图比对，返回 {ok, kernel, diff}。"""
    res = _wg_quick_run(['wg', 'show', ifname, 'dump'])
    if not res['ok']:
        return {'ok': False, 'error': res.get('stderr') or '无法执行 wg show', 'argv': res['argv']}
    kernel = _parse_wg_show_dump(res.get('stdout') or '')

    want_port = t.get('listen_port')
    if want_port is None:
        want_port = t.get('port')
    try:
        want_port = int(want_port) if want_port not in (None, '') else None
    except (TypeError, ValueError):
        want_port = None

    want_peer_pubs: list[str] = []
    for p in t.get('peers') or []:
        if not isinstance(p, dict):
            continue
        pub = (p.get('public_key') or (p.get('keys') or {}).get('public') or '').strip()
        if pub:
            want_peer_pubs.append(pub)
    kernel_peer_pubs = [p['public_key'] for p in kernel['peers'] if p.get('public_key')]

    diff: dict[str, Any] = {}
    if want_port is not None and kernel['listen_port'] != want_port:
        diff['listen_port'] = {'want': want_port, 'kernel': kernel['listen_port']}
    missing = sorted(set(want_peer_pubs) - set(kernel_peer_pubs))
    extra = sorted(set(kernel_peer_pubs) - set(want_peer_pubs))
    if missing:
        diff['missing_peers'] = missing
    if extra:
        diff['extra_peers'] = extra
    return {'ok': not diff, 'kernel': kernel, 'diff': diff or None}


def _format_wg_endpoint_for_conf(host: str, port: int) -> str:
    try:
        ipaddress.IPv6Address(host)
        return f'[{host}]:{port}'
    except ValueError:
        return f'{host}:{port}'


def render_wg_quick_conf(ifname: str, t: dict[str, Any]) -> str:
    """wg-quick 格式的 .conf，与 netplan_tunnel 载荷一致。"""
    lines: list[str] = [WG_CONF_MANAGED_MARKER, f'# Interface: {ifname}', '']
    keys = t.get('keys') or {}
    priv = keys.get('private') if isinstance(keys, dict) else None
    if not priv or not str(priv).strip():
        raise ValueError('缺少 keys.private，无法写入 .conf')

    lines.append('[Interface]')
    lines.append(f"PrivateKey = {str(priv).strip()}")

    raw_addr = t.get('addresses')
    addr_list: list[str] = []
    if isinstance(raw_addr, str) and raw_addr.strip():
        addr_list = [raw_addr.strip()]
    elif isinstance(raw_addr, list):
        addr_list = [str(a).strip() for a in raw_addr if str(a).strip()]
    for a in addr_list:
        lines.append(f'Address = {a}')

    port = t.get('listen_port')
    if port is None:
        port = t.get('port')
    if port is not None and str(port).strip() != '':
        try:
            lines.append(f'ListenPort = {int(port)}')
        except (TypeError, ValueError):
            pass

    fw = t.get('fwmark') if t.get('fwmark') is not None else t.get('mark')
    if fw is not None and str(fw).strip() != '':
        try:
            lines.append(f'FwMark = {int(fw)}')
        except (TypeError, ValueError):
            pass

    peers_in = [p for p in (t.get('peers') or []) if isinstance(p, dict)]
    for p in peers_in:
        pub = p.get('public_key') or (p.get('keys') or {}).get('public')
        if not pub:
            continue
        lines.append('')
        lines.append('[Peer]')
        lines.append(f"PublicKey = {str(pub).strip()}")
        psk = p.get('preshared_key') or (p.get('keys') or {}).get('shared')
        if psk and str(psk).strip():
            lines.append(f"PresharedKey = {str(psk).strip()}")
        ep = p.get('endpoint')
        if ep and str(ep).strip():
            host, pport = parse_endpoint(ep)
            if host and pport:
                lines.append(f'Endpoint = {_format_wg_endpoint_for_conf(host, pport)}')
        allowed = _allowed_ips_list(p)
        if allowed:
            lines.append(f"AllowedIPs = {', '.join(allowed)}")
        ka = p.get('persistent_keepalive')
        if ka is None:
            ka = p.get('keepalive')
        if ka is not None and str(ka).strip() != '':
            try:
                lines.append(f'PersistentKeepalive = {int(ka)}')
            except (TypeError, ValueError):
                pass

    lines.append('')
    return '\n'.join(lines)


def wireguard_conf_path(ifname: str) -> str:
    d = str(getattr(settings, 'INTERFACEMANAGE_WG_CONFIG_DIR', '/etc/wireguard'))
    return os.path.join(d, f'{ifname}.conf')


def write_wireguard_conf_file(ifname: str, body: str) -> str:
    path = wireguard_conf_path(ifname)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, mode=0o755, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(body)
        if not body.endswith('\n'):
            fh.write('\n')
    return path


def remove_stale_managed_wg_confs(desired_ifnames: set[str]) -> list[dict[str, Any]]:
    """删除目录中带 PE Manager 标记、且接口名不在 desired_ifnames 中的 *.conf。"""
    dir_path = str(getattr(settings, 'INTERFACEMANAGE_WG_CONFIG_DIR', '/etc/wireguard'))
    out: list[dict[str, Any]] = []
    if not os.path.isdir(dir_path):
        return out
    try:
        names = os.listdir(dir_path)
    except OSError as exc:
        return [{'ok': False, 'error': str(exc)}]
    for fn in names:
        if not fn.endswith('.conf'):
            continue
        base = fn[:-5]
        if base in desired_ifnames:
            continue
        path = os.path.join(dir_path, fn)
        try:
            with open(path, encoding='utf-8') as fh:
                first = fh.readline().strip()
            if first != WG_CONF_MANAGED_MARKER:
                continue
            os.unlink(path)
            out.append({'path': path, 'removed': True, 'ok': True})
        except OSError as exc:
            out.append({'path': path, 'removed': False, 'ok': False, 'error': str(exc)})
    return out


def _wg_quick_run(argv: list[str]) -> dict[str, Any]:
    """复用 netplan_writing._run 的子进程封装（统一前缀/超时/开关）。"""
    # lazy import 防止循环依赖
    from interfacemanage.services.netplan_writing import _run as _elevated_run

    res = _elevated_run(argv, timeout_kind='apply')
    return {
        'argv': argv,
        'ok': res.ok,
        'returncode': res.returncode,
        'stdout': res.stdout,
        'stderr': res.stderr,
    }


def apply_one_wireguard(obj: DesiredTunnelConfig) -> dict[str, Any]:
    """
    单条 WireGuard 意图的下发：
      1) 渲染 wg-quick conf 并写入 /etc/wireguard/<if>.conf
      2) 让 routemanage 注入 PostUp/PostDown 路由块（如有）
      3) `wg-quick down <if>`（失败回退 `ip link delete dev <if>`）
      4) `wg-quick up <if>`
    成功后 `wg show <if>` 必然与 conf 一致。
    """
    if not _wg_apply_enabled():
        return {'ifname': obj.ifname, 'ok': False, 'error': 'INTERFACEMANAGE_WG_APPLY_ENABLED 为 False'}

    ifname = (obj.ifname or '').strip()
    if not _wg_conf_safe_ifname(ifname):
        return {
            'ifname': ifname,
            'ok': False,
            'error': '接口名仅允许字母、数字、下划线与连字符（须与 /etc/wireguard/<接口名>.conf 一致）',
        }

    t = _tunnel_from_obj(obj)

    addr_list: list[str] = []
    raw_addr = t.get('addresses')
    if isinstance(raw_addr, str) and raw_addr.strip():
        addr_list = [raw_addr.strip()]
    elif isinstance(raw_addr, list):
        addr_list = [str(a).strip() for a in raw_addr if str(a).strip()]
    if not addr_list:
        return {'ifname': ifname, 'ok': False, 'error': '缺少 addresses（本端 CIDR）'}

    # 语义校验：私钥/公钥格式、本端公钥 vs 私钥派生、peer 公钥不能与本端公钥相同等
    sem_err = _validate_wg_intent(ifname, t)
    if sem_err:
        return {
            'ifname': ifname,
            'ok': False,
            'error': sem_err,
            'hint': '请在「隧道接口配置」中修正后再下发；这是配置数据错误，wg-quick 会写成功但 wg show 不会出现该 peer',
        }

    steps: list[dict[str, Any]] = []
    conf_path = wireguard_conf_path(ifname)
    try:
        conf_body = render_wg_quick_conf(ifname, t)
        write_wireguard_conf_file(ifname, conf_body)
        steps.append({'step': 'write wg-quick conf', 'path': conf_path, 'ok': True})
    except OSError as exc:
        steps.append({'step': 'write wg-quick conf', 'path': conf_path, 'ok': False, 'stderr': str(exc)})
        return {
            'ifname': ifname,
            'ok': False,
            'error': f'写入 {conf_path} 失败: {exc}',
            'conf_path': conf_path,
            'steps': steps,
        }
    except ValueError as exc:
        steps.append({'step': 'render wg-quick conf', 'ok': False, 'stderr': str(exc)})
        return {'ifname': ifname, 'ok': False, 'error': str(exc), 'conf_path': conf_path, 'steps': steps}

    # routemanage 注入 PostUp/PostDown 路由块
    try:
        from routemanage.services.iproute_writing import reconcile_wg_conf_routes

        recon = reconcile_wg_conf_routes(ifname)
        steps.append(
            {
                'step': 'inject managed routes (routemanage)',
                'ok': bool(recon.get('ok')),
                'route_count': recon.get('count', 0),
                'stderr': recon.get('error') or '',
            }
        )
    except Exception as exc:  # noqa: BLE001
        # 不阻塞接口拉起；用户可在「路由 → 下发 WireGuard 路由」中重试
        steps.append({'step': 'inject managed routes (routemanage)', 'ok': False, 'stderr': str(exc)})

    # wg-quick down（容错：可能此前接口不存在或未由 wg-quick 创建）
    down = _wg_quick_run(['wg-quick', 'down', ifname])
    steps.append({'step': 'wg-quick down', **down, 'fatal': False})
    if not down['ok']:
        link_del = _wg_quick_run(['ip', 'link', 'delete', 'dev', ifname])
        steps.append({'step': 'ip link delete (fallback)', **link_del, 'fatal': False})

    # wg-quick up
    up = _wg_quick_run(['wg-quick', 'up', ifname])
    steps.append({'step': 'wg-quick up', **up})
    if not up['ok']:
        return {
            'ifname': ifname,
            'ok': False,
            'error': f'wg-quick up 失败: {up.get("stderr") or up.get("stdout") or ""}',
            'conf_path': conf_path,
            'steps': steps,
        }

    # 内核回读校验：保证 wg show 与意图一致（防止历史脏数据/竞争状态）
    consistency = _check_kernel_consistency(ifname, t)
    steps.append({'step': 'kernel consistency check', **consistency})
    if not consistency.get('ok'):
        return {
            'ifname': ifname,
            'ok': False,
            'error': '下发完成但 `wg show` 与意图不一致；详见 steps.kernel consistency check.diff',
            'conf_path': conf_path,
            'steps': steps,
            'kernel': consistency.get('kernel'),
            'diff': consistency.get('diff'),
        }

    return {
        'ifname': ifname,
        'ok': True,
        'mode': 'wg-quick',
        'conf_path': conf_path,
        'steps': steps,
        'kernel': consistency.get('kernel'),
    }


def apply_all_desired_wireguard(
    tunnels: list[DesiredTunnelConfig],
    *,
    ids: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """
    对传入的隧道集合中的 WireGuard 接口逐一执行 `wg-quick down/up`。

    参数：
      ids: 若提供，则只对其 id 在集合中的 WireGuard 接口下发，避免一次性重启全部 WG，
           造成无关业务中断；为 None 表示全量下发。
    """
    steps: list[dict[str, Any]] = []
    wg_objs = [o for o in tunnels if o.kind == DesiredTunnelConfig.Kind.WIREGUARD]
    if ids is not None:
        id_set = {str(i) for i in ids}
        skipped = [o for o in wg_objs if str(o.id) not in id_set]
        wg_objs = [o for o in wg_objs if str(o.id) in id_set]
        for o in skipped:
            steps.append({
                'step': 'skip',
                'ifname': o.ifname,
                'reason': '本次为选择性下发，未在选中集合内',
            })
    if not wg_objs:
        return {'ok': True, 'steps': steps, 'message': '无 WireGuard 意图（或选中集合为空）'}

    all_ok = True
    for obj in wg_objs:
        r = apply_one_wireguard(obj)
        steps.append(r)
        if not r.get('ok'):
            all_ok = False
    result: dict[str, Any] = {'ok': all_ok, 'steps': steps}
    # 选择性下发时，禁止清理"未选中"的 conf，以免误删
    if (
        all_ok
        and wg_objs
        and ids is None
        and bool(getattr(settings, 'INTERFACEMANAGE_WG_REMOVE_STALE_CONF', True))
    ):
        desired = {(o.ifname or '').strip() for o in wg_objs}
        stale = remove_stale_managed_wg_confs(desired)
        if stale:
            result['stale_wg_conf_removed'] = stale
    return result
