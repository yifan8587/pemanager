import ipaddress

from rest_framework import serializers

from interfacemanage.models import (
    DesiredTunnelConfig,
    NetplanFileRecord,
    NetworkInterfaceRecord,
    NetworkSyncRun,
)
from resourcemanage.models import ResourceCustomer


class NetworkSyncRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkSyncRun
        fields = [
            'id',
            'started_at',
            'finished_at',
            'success',
            'error_message',
            'stats',
        ]
        read_only_fields = fields


class NetplanFileRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetplanFileRecord
        fields = [
            'id',
            'path',
            'file_sha256',
            'size_bytes',
            'mtime_epoch',
            'raw_yaml',
            'parsed',
            'parse_error',
            'last_run',
            'updated_at',
        ]
        read_only_fields = fields


class NetplanFileRecordBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetplanFileRecord
        fields = [
            'id',
            'path',
            'file_sha256',
            'size_bytes',
            'mtime_epoch',
            'parse_error',
            'last_run',
            'updated_at',
        ]
        read_only_fields = fields


class NetworkInterfaceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkInterfaceRecord
        fields = [
            'ifname',
            'ifindex',
            'kind',
            'admin_up',
            'operstate',
            'mtu',
            'mac',
            'addresses',
            'linkinfo',
            'netplan',
            'wireguard',
            'ip_tunnel_show',
            'unified',
            'content_sha256',
            'last_run',
            'first_seen_at',
            'last_seen_at',
        ]
        read_only_fields = fields


class DesiredTunnelConfigSerializer(serializers.ModelSerializer):
    # customer 用 slug=code，便于前端直接传客户编码；同时只读返回客户名
    customer = serializers.SlugRelatedField(
        slug_field='code',
        queryset=ResourceCustomer.objects.all(),
        required=False,
        allow_null=True,
    )
    customer_code = serializers.CharField(source='customer.code', read_only=True, default=None)
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)

    # 派生字段：从 spec 抽取，便于前端 UI 联动（按客户选接口、自动建议下一跳）
    local_addresses = serializers.SerializerMethodField(read_only=True)
    peer_ip = serializers.SerializerMethodField(read_only=True)
    peer_endpoint = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DesiredTunnelConfig
        fields = [
            'id',
            'kind',
            'ifname',
            'spec',
            'customer',
            'customer_code',
            'customer_name',
            'local_addresses',
            'peer_ip',
            'peer_endpoint',
            'remark',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'customer_code',
            'customer_name',
            'local_addresses',
            'peer_ip',
            'peer_endpoint',
        ]

    # ---- 派生字段实现 ----
    @staticmethod
    def _addrs(obj) -> list[str]:
        spec = obj.spec or {}
        t = spec.get('netplan_tunnel') or {}
        a = t.get('addresses')
        if isinstance(a, str):
            return [a.strip()] if a.strip() else []
        if isinstance(a, list):
            return [str(x).strip() for x in a if str(x).strip()]
        return []

    def get_local_addresses(self, obj) -> list[str]:
        return self._addrs(obj)

    def get_peer_ip(self, obj):
        """对 /30 或 /31 这类 PtP 子网，从本端 addresses 推断对端 IP（作为路由 via 的建议值）。

        - /31：两端就是 net[0] 与 net[1]
        - /30：两个 host 互算
        - 其他掩码：不建议（返回 None）
        """
        addrs = self._addrs(obj)
        if not addrs:
            return None
        try:
            iface = ipaddress.ip_interface(addrs[0])
        except Exception:
            return None
        net = iface.network
        local = iface.ip
        try:
            if net.prefixlen in (31, 127):
                cands = [net[0], net[1]]
            elif net.prefixlen in (30, 126):
                cands = list(net.hosts())
            else:
                return None
        except Exception:
            return None
        for c in cands:
            if c != local:
                return str(c)
        return None

    def get_peer_endpoint(self, obj):
        """对端"外部 endpoint"：GRE/VXLAN 的 remote 公网 IP；WG 的 peers[0].endpoint。"""
        spec = obj.spec or {}
        t = spec.get('netplan_tunnel') or {}
        if obj.kind == DesiredTunnelConfig.Kind.WIREGUARD:
            peers = t.get('peers') or []
            if peers and isinstance(peers, list):
                ep = peers[0].get('endpoint') if isinstance(peers[0], dict) else None
                return ep or None
            return None
        return t.get('remote') or None
