from rest_framework import serializers

from operationmanage.models import (
    DiagnosticsJob,
    InterfaceTrafficSample,
    LatencySample,
    MonitorInterface,
    MonitorTarget,
)
from resourcemanage.models import ResourceCustomer


class MonitorTargetSerializer(serializers.ModelSerializer):
    customer = serializers.SlugRelatedField(
        slug_field='code',
        queryset=ResourceCustomer.objects.all(),
        required=False,
        allow_null=True,
    )
    customer_code = serializers.CharField(source='customer.code', read_only=True, default=None)
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)

    class Meta:
        model = MonitorTarget
        fields = [
            'id',
            'name',
            'address',
            'kind',
            'interval_sec',
            'count',
            'source_interface',
            'enabled',
            'customer',
            'customer_code',
            'customer_name',
            'remark',
            'created_at',
            'updated_at',
            'last_sampled_at',
        ]
        read_only_fields = [
            'id', 'customer_code', 'customer_name',
            'created_at', 'updated_at', 'last_sampled_at',
        ]


class MonitorInterfaceSerializer(serializers.ModelSerializer):
    customer = serializers.SlugRelatedField(
        slug_field='code',
        queryset=ResourceCustomer.objects.all(),
        required=False,
        allow_null=True,
    )
    customer_code = serializers.CharField(source='customer.code', read_only=True, default=None)
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)

    class Meta:
        model = MonitorInterface
        fields = [
            'id',
            'interface_name',
            'enabled',
            'interval_sec',
            'customer',
            'customer_code',
            'customer_name',
            'remark',
            'created_at',
            'updated_at',
            'last_sampled_at',
        ]
        read_only_fields = [
            'id', 'customer_code', 'customer_name',
            'created_at', 'updated_at', 'last_sampled_at',
        ]


class LatencySampleSerializer(serializers.ModelSerializer):
    target_name = serializers.CharField(source='target.name', read_only=True)

    class Meta:
        model = LatencySample
        fields = [
            'id',
            'target',
            'target_name',
            'ts',
            'rtt_min_ms',
            'rtt_avg_ms',
            'rtt_max_ms',
            'jitter_ms',
            'loss_pct',
            'packets_sent',
            'packets_recv',
            'ok',
            'detail',
        ]
        read_only_fields = fields


class InterfaceTrafficSampleSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterfaceTrafficSample
        fields = [
            'id',
            'interface_name',
            'ts',
            'rx_bytes_total',
            'tx_bytes_total',
            'rx_packets_total',
            'tx_packets_total',
            'rx_bps',
            'tx_bps',
            'window_sec',
        ]
        read_only_fields = fields


class ToolPingSerializer(serializers.Serializer):
    address = serializers.CharField()
    # 上限放宽：异步任务允许更大批量；同步路径仍受 ASYNC_THRESHOLD 约束
    count = serializers.IntegerField(required=False, default=5, min_value=1, max_value=1000)
    source = serializers.CharField(required=False, allow_blank=True)
    # 强制异步；不传则按 count > ASYNC_THRESHOLD 自动判断
    async_run = serializers.BooleanField(required=False, default=None, allow_null=True)


class ToolMtrSerializer(serializers.Serializer):
    address = serializers.CharField()
    count = serializers.IntegerField(required=False, default=5, min_value=1, max_value=200)
    source = serializers.CharField(required=False, allow_blank=True)
    async_run = serializers.BooleanField(required=False, default=None, allow_null=True)


class DiagnosticsJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticsJob
        fields = [
            'id', 'kind', 'address', 'source', 'count',
            'status', 'started_at', 'finished_at', 'duration_ms',
            'result', 'error', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class TrafficSampleRequestSerializer(serializers.Serializer):
    interface = serializers.CharField()
    window_sec = serializers.FloatField(required=False, default=1.0, min_value=0.2, max_value=5.0)


class TrafficBatchRequestSerializer(serializers.Serializer):
    interfaces = serializers.ListField(child=serializers.CharField(), allow_empty=False)


class ToolDiagnoseSerializer(serializers.Serializer):
    address = serializers.CharField()
    source = serializers.CharField(required=False, allow_blank=True)
    ping_count = serializers.IntegerField(required=False, default=5, min_value=1, max_value=30)
    do_traceroute = serializers.BooleanField(required=False, default=False)
    traceroute_max_hops = serializers.IntegerField(required=False, default=10, min_value=1, max_value=30)
