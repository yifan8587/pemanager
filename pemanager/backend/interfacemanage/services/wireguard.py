from __future__ import annotations

from typing import Any

from interfacemanage.services import subprocess_util


def wg_show_interfaces() -> dict[str, Any]:
    res = subprocess_util.run(['wg', 'show', 'interfaces'])
    if not res.ok:
        return {'ok': False, 'exit_code': res.exit_code, 'stderr': res.stderr, 'interfaces': []}
    names = [x.strip() for x in res.stdout.splitlines() if x.strip()]
    return {'ok': True, 'exit_code': res.exit_code, 'stderr': res.stderr, 'interfaces': names}


def wg_show_dump(ifname: str) -> dict[str, Any]:
    res = subprocess_util.run(['wg', 'show', ifname, 'dump'])
    if not res.ok:
        return {'ok': False, 'ifname': ifname, 'stderr': res.stderr, 'device': None, 'peers': []}
    return {'ok': True, 'ifname': ifname, **parse_wg_dump(res.stdout)}


def parse_wg_dump(raw: str) -> dict[str, Any]:
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return {'device': None, 'peers': []}

    dev_fields = lines[0].split('\t')
    device = {
        'private_key': dev_fields[0] if len(dev_fields) > 0 else None,
        'public_key': dev_fields[1] if len(dev_fields) > 1 else None,
        'listen_port': dev_fields[2] if len(dev_fields) > 2 else None,
        'fwmark': dev_fields[3] if len(dev_fields) > 3 else None,
    }

    peers: list[dict[str, Any]] = []
    for ln in lines[1:]:
        f = ln.split('\t')
        if len(f) < 8:
            peers.append({'raw': ln})
            continue
        peers.append(
            {
                'public_key': f[0],
                'preshared_key': f[1],
                'endpoint': f[2],
                'allowed_ips': f[3],
                'latest_handshake': f[4],
                'transfer_rx': f[5],
                'transfer_tx': f[6],
                'persistent_keepalive': f[7],
            }
        )

    return {'device': device, 'peers': peers}


def redact_dump(d: dict[str, Any]) -> dict[str, Any]:
    """隐藏私钥 / PSK，便于对外展示。"""
    import copy

    out = copy.deepcopy(d)
    dev = out.get('device')
    if isinstance(dev, dict):
        pk = dev.get('private_key')
        if pk and str(pk).lower() not in ('(none)', 'none'):
            dev['private_key'] = '***'
    for p in out.get('peers') or []:
        if isinstance(p, dict):
            psk = p.get('preshared_key')
            if psk and str(psk).lower() not in ('(none)', 'none'):
                p['preshared_key'] = '***'
    return out


def collect_wireguard_overview(*, mask: bool = True) -> dict[str, Any]:
    iface_res = wg_show_interfaces()
    if not iface_res['ok']:
        return {'ok': False, 'stderr': iface_res.get('stderr'), 'interfaces': {}}

    out: dict[str, Any] = {}
    for name in iface_res.get('interfaces') or []:
        d = wg_show_dump(name)
        if mask and d.get('ok'):
            d = redact_dump(d)
        out[name] = d
    return {'ok': True, 'interfaces': out}
