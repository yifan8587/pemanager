"""将内核 linkinfo 类型 / netplan section 映射到 DesiredRouteConfig.netplan_device_class。"""
from __future__ import annotations

from routemanage.models import DesiredRouteConfig


def kind_to_netplan_device_class(kind: str) -> str:
    k = (kind or '').strip().lower()
    if not k:
        return DesiredRouteConfig.NetplanDeviceClass.ETHERNETS

    tunnel_kinds = frozenset(
        {
            'wireguard',
            'vxlan',
            'gre',
            'gretap',
            'erspan',
            'ip6gre',
            'ip6gretap',
            'ip_gre',
            'ipip',
            'sit',
            'ip6tnl',
            'vti',
            'vti6',
            'tunnel',
            'geneve',
        }
    )
    if k in tunnel_kinds:
        return DesiredRouteConfig.NetplanDeviceClass.TUNNELS
    if k in {'bridge'}:
        return DesiredRouteConfig.NetplanDeviceClass.BRIDGES
    if k in {'bond'}:
        return DesiredRouteConfig.NetplanDeviceClass.BONDS
    if k in {'vlan', 'macvlan', 'ipvlan'}:
        return DesiredRouteConfig.NetplanDeviceClass.VLANS
    if k in {'wlan', 'wifi'}:
        return DesiredRouteConfig.NetplanDeviceClass.WIFIS

    return DesiredRouteConfig.NetplanDeviceClass.ETHERNETS


def infer_netplan_device_class_for_interface(*, netplan_row: dict | None, kernel_kind: str) -> str:
    """优先使用 netplan 索引中的 section，其次按内核 kind 推断。"""
    if isinstance(netplan_row, dict):
        sec = netplan_row.get('section')
        if isinstance(sec, str) and sec:
            choices = {c.value for c in DesiredRouteConfig.NetplanDeviceClass}
            if sec in choices:
                return sec
    return kind_to_netplan_device_class(kernel_kind)
