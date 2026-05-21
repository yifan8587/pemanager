from __future__ import annotations

from typing import Any

from interfacemanage.services.netplan import index_netplan_interfaces


def _flags_up(flags: Any) -> bool | None:
    if not isinstance(flags, list):
        return None
    return 'UP' in flags


def _classify_kind(link: dict[str, Any]) -> str:
    linkinfo = link.get('linkinfo') or {}
    if isinstance(linkinfo, dict):
        kind = linkinfo.get('info_kind')
        if kind:
            return str(kind)
    lt = link.get('link_type')
    if lt:
        return str(lt)
    if link.get('link_netnsid') is not None:
        return 'netns'
    return 'ethernet'


def _tunnel_mode_from_netplan(spec: dict[str, Any]) -> str | None:
    mode = spec.get('mode')
    if isinstance(mode, str):
        return mode
    return None


def unify_interfaces(
    *,
    netplan_bundle: dict[str, Any],
    kernel: dict[str, Any],
    wireguard: dict[str, Any],
) -> list[dict[str, Any]]:
    merged = netplan_bundle.get('merged_network') or {}
    np_idx = index_netplan_interfaces(merged if isinstance(merged, dict) else {})

    links = (kernel.get('link') or {}).get('links') or []
    if not isinstance(links, list):
        links = []

    addrs_by_if = kernel.get('addresses_by_ifname') or {}

    wg_ifaces = {}
    if wireguard.get('ok') and isinstance(wireguard.get('interfaces'), dict):
        wg_ifaces = wireguard['interfaces']

    tunnel_parsed = ((kernel.get('tunnel_show') or {}).get('parsed')) or []
    tunnel_by_name = {
        str(row['ifname']): row for row in tunnel_parsed if isinstance(row, dict) and row.get('ifname')
    }

    rows: list[dict[str, Any]] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        name = link.get('ifname')
        if not name:
            continue
        name = str(name)
        kind = _classify_kind(link)
        np = np_idx.get(name)

        np_kind = None
        tunnel_mode_np = None
        if np:
            np_kind = np.get('kind')
            tunnel_mode_np = _tunnel_mode_from_netplan(np.get('spec') or {})

        addr_entries = addrs_by_if.get(name) or []

        wg_detail = wg_ifaces.get(name) if kind == 'wireguard' else None

        tunnel_line = tunnel_by_name.get(name)

        rows.append(
            {
                'ifname': name,
                'ifindex': link.get('ifindex'),
                'kind': kind,
                'kind_source': 'kernel',
                'admin_up': _flags_up(link.get('flags')),
                'operstate': link.get('operstate'),
                'mtu': link.get('mtu'),
                'mac': link.get('address'),
                'qdisc': link.get('qdisc'),
                'group': link.get('group'),
                'link_type': link.get('link_type'),
                'linkinfo': link.get('linkinfo'),
                'addresses': addr_entries,
                'netplan': np,
                'netplan_kind': np_kind,
                'netplan_tunnel_mode': tunnel_mode_np,
                'wireguard': wg_detail if isinstance(wg_detail, dict) else None,
                'ip_tunnel_show': tunnel_line,
            }
        )

    rows.sort(key=lambda r: (r.get('ifindex') is None, r.get('ifindex') or 0, r['ifname']))
    return rows


def summarize_by_kind(rows: list[dict[str, Any]]) -> dict[str, int]:
    stats: dict[str, int] = {}
    for r in rows:
        k = str(r.get('kind') or 'unknown')
        stats[k] = stats.get(k, 0) + 1
    return dict(sorted(stats.items(), key=lambda x: x[0]))
