from __future__ import annotations

import json
import re
from typing import Any

from interfacemanage.services import subprocess_util


def _parse_ip_json(stdout: str) -> list[dict[str, Any]] | dict[str, Any] | None:
    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def ip_link_show() -> dict[str, Any]:
    res = subprocess_util.run(['ip', '-json', 'link', 'show'])
    data = _parse_ip_json(res.stdout) if res.ok else None
    return {
        'ok': res.ok,
        'exit_code': res.exit_code,
        'stderr': res.stderr,
        'links': data if isinstance(data, list) else [],
    }


def ip_addr_show() -> dict[str, Any]:
    res = subprocess_util.run(['ip', '-json', 'addr', 'show'])
    data = _parse_ip_json(res.stdout) if res.ok else None
    return {
        'ok': res.ok,
        'exit_code': res.exit_code,
        'stderr': res.stderr,
        'addresses': data if isinstance(data, list) else [],
    }


def ip_route_show() -> dict[str, Any]:
    res = subprocess_util.run(['ip', '-json', 'route', 'show'])
    data = _parse_ip_json(res.stdout) if res.ok else None
    return {
        'ok': res.ok,
        'exit_code': res.exit_code,
        'stderr': res.stderr,
        'routes': data if isinstance(data, list) else [],
    }


def ip_tunnel_show_text() -> dict[str, Any]:
    """`ip tunnel show` 文本输出（GRE/IPIP/SIT 等），兼容无 JSON 子命令的环境。"""
    res = subprocess_util.run(['ip', 'tunnel', 'show'])
    return {
        'ok': res.ok,
        'exit_code': res.exit_code,
        'stderr': res.stderr,
        'raw': res.stdout,
    }


_TUNNEL_LINE = re.compile(
    r'^(?P<name>[^:]+):\s*(?P<mode>[^\s/]+)/(?:ipv6\s+)?(?P<rest>.*)$'
)


def parse_tunnel_show(raw: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _TUNNEL_LINE.match(line)
        if not m:
            rows.append({'raw': line})
            continue
        rows.append(
            {
                'ifname': m.group('name').strip(),
                'mode': m.group('mode').strip(),
                'details': m.group('rest').strip(),
            }
        )
    return rows


def ip_link_show_filtered(link_type: str) -> dict[str, Any]:
    """例如 type vxlan / gre / gretap ..."""
    res = subprocess_util.run(['ip', '-json', 'link', 'show', 'type', link_type])
    data = _parse_ip_json(res.stdout) if res.ok else None
    return {
        'type': link_type,
        'ok': res.ok,
        'exit_code': res.exit_code,
        'stderr': res.stderr,
        'links': data if isinstance(data, list) else [],
    }


def collect_kernel_snapshot() -> dict[str, Any]:
    link = ip_link_show()
    addr = ip_addr_show()
    route = ip_route_show()
    tunnel_raw = ip_tunnel_show_text()
    tunnels_parsed = parse_tunnel_show(tunnel_raw['raw']) if tunnel_raw.get('ok') else []

    typed: dict[str, Any] = {}
    for t in ('vxlan', 'gre', 'gretap', 'ip6gre', 'geneve', 'bridge', 'bond', 'vlan'):
        typed[t] = ip_link_show_filtered(t)

    addrs_by_if: dict[str, list[dict[str, Any]]] = {}
    for item in addr.get('addresses') or []:
        if not isinstance(item, dict):
            continue
        name = item.get('ifname')
        if not name:
            continue
        addrs_by_if.setdefault(str(name), []).append(item)

    return {
        'link': link,
        'address': addr,
        'route': route,
        'tunnel_show': {**tunnel_raw, 'parsed': tunnels_parsed},
        'typed_links': typed,
        'addresses_by_ifname': addrs_by_if,
    }
