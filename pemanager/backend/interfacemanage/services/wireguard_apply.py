"""
使用 python-wireguard（ctypes + 自带 py-wireguard.so）将 DesiredTunnelConfig 应用到本机。

同时将配置写成 wg-quick 格式：默认 /etc/wireguard/<接口名>.conf（可配置目录），
再调用 python-wireguard 建口并下发内核。

该库偏 C/S 模型：单对端且填写 endpoint 时走 Client；否则走 Server（可多 peer），
Server 模式下每个 peer 须在 allowed_ips 中给出对端隧道地址（首条用作库内「客户端 IP」）。

不负责 GRE/VXLAN；netplan 持久化片段仍由 netplan_writing 生成。
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


def apply_one_wireguard(obj: DesiredTunnelConfig) -> dict[str, Any]:
    """使用 python-wireguard 对单条意图建口、配密钥/对端、起接口。"""
    if not _wg_apply_enabled():
        return {'ifname': obj.ifname, 'ok': False, 'error': 'INTERFACEMANAGE_WG_APPLY_ENABLED 为 False'}

    if not python_wireguard_available():
        return {
            'ifname': obj.ifname,
            'ok': False,
            'error': (
                '无法加载 python-wireguard（须与运行 Django 的 Python 一致）。'
                '请执行：python -m pip install "python-wireguard>=0.2.2" 后重启服务；'
                '且系统需为 Linux x86_64 等该 wheel 自带 py-wireguard.so 支持的架构。'
            ),
        }

    from python_wireguard import Client, ClientConnection, Server, ServerConnection

    ifname = (obj.ifname or '').strip()
    if not _wg_conf_safe_ifname(ifname):
        return {
            'ifname': ifname,
            'ok': False,
            'error': '接口名仅允许字母、数字、下划线与连字符，与 /etc/wireguard/<接口名>.conf 命名一致',
        }
    t = _tunnel_from_obj(obj)
    keys = t.get('keys') or {}
    priv_raw = keys.get('private') if isinstance(keys, dict) else None
    if not priv_raw or not str(priv_raw).strip():
        return {'ifname': ifname, 'ok': False, 'error': '缺少 keys.private'}
    try:
        priv_key = _key_from_b64('私钥', str(priv_raw))
    except ValueError as exc:
        return {'ifname': ifname, 'ok': False, 'error': str(exc)}

    port = t.get('port')
    if port is None:
        port = t.get('listen_port')
    try:
        listen_port = int(port) if port is not None and port != '' else 51820
    except (TypeError, ValueError):
        listen_port = 51820

    addr_list: list[str] = []
    raw_addr = t.get('addresses')
    if isinstance(raw_addr, str) and raw_addr.strip():
        addr_list = [raw_addr.strip()]
    elif isinstance(raw_addr, list):
        addr_list = [str(a).strip() for a in raw_addr if str(a).strip()]
    if not addr_list:
        return {'ifname': ifname, 'ok': False, 'error': '缺少 addresses（本端 CIDR）'}

    peers_in = [p for p in (t.get('peers') or []) if isinstance(p, dict)]
    if not peers_in:
        return {'ifname': ifname, 'ok': False, 'error': '未配置任何 peer'}

    use_client = _should_use_client_mode(peers_in)

    conf_path = wireguard_conf_path(ifname)
    try:
        conf_body = render_wg_quick_conf(ifname, t)
        write_wireguard_conf_file(ifname, conf_body)
    except OSError as exc:
        return {
            'ifname': ifname,
            'ok': False,
            'error': f'写入 {conf_path} 失败: {exc}',
            'conf_path': conf_path,
        }
    except ValueError as exc:
        return {'ifname': ifname, 'ok': False, 'error': str(exc), 'conf_path': conf_path}

    try:
        _safe_delete_device(ifname)

        if use_client:
            p0 = peers_in[0]
            pub_raw = p0.get('public_key') or (p0.get('keys') or {}).get('public')
            if not pub_raw:
                return {'ifname': ifname, 'ok': False, 'error': 'peer 缺少 public_key'}
            pub_key = _key_from_b64('对端公钥', str(pub_raw))
            host, rport = parse_endpoint(p0.get('endpoint'))
            if not host or not rport:
                return {'ifname': ifname, 'ok': False, 'error': 'peer endpoint 无效'}
            cl = Client(ifname, priv_key, addr_list[0])
            cl.set_server(ServerConnection(pub_key, host, rport))
            cl.connect()
            if len(addr_list) > 1:
                _add_extra_addresses(ifname, addr_list[1:])
        else:
            srv = Server(ifname, priv_key, addr_list[0], listen_port)
            srv.enable()
            for p in peers_in:
                pub_raw = p.get('public_key') or (p.get('keys') or {}).get('public')
                if not pub_raw:
                    return {'ifname': ifname, 'ok': False, 'error': '某个 peer 缺少 public_key'}
                pub_key = _key_from_b64('对端公钥', str(pub_raw))
                tunnel_ip = _peer_tunnel_ip_for_server(p)
                srv.add_client(ClientConnection(pub_key, tunnel_ip))
            if len(addr_list) > 1:
                _add_extra_addresses(ifname, addr_list[1:])

        return {
            'ifname': ifname,
            'ok': True,
            'mode': 'client' if use_client else 'server',
            'conf_path': conf_path,
        }
    except Exception as exc:  # noqa: BLE001
        return {'ifname': ifname, 'ok': False, 'error': str(exc)}


def apply_all_desired_wireguard(
    tunnels: list[DesiredTunnelConfig],
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    wg_objs = [o for o in tunnels if o.kind == DesiredTunnelConfig.Kind.WIREGUARD]
    if not wg_objs:
        return {'ok': True, 'steps': steps, 'message': '无 WireGuard 意图'}

    all_ok = True
    for obj in wg_objs:
        r = apply_one_wireguard(obj)
        steps.append(r)
        if not r.get('ok'):
            all_ok = False
    result: dict[str, Any] = {'ok': all_ok, 'steps': steps}
    if (
        all_ok
        and wg_objs
        and bool(getattr(settings, 'INTERFACEMANAGE_WG_REMOVE_STALE_CONF', True))
    ):
        desired = {(o.ifname or '').strip() for o in wg_objs}
        stale = remove_stale_managed_wg_confs(desired)
        if stale:
            result['stale_wg_conf_removed'] = stale
    return result
