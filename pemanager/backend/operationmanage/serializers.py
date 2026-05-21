from rest_framework import serializers

from operationmanage.models import (
    InterfaceTrafficSample,
    LatencySample,
    MonitorTarget,
)


class MonitorTargetSerializer(serializers.ModelSerializer):
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
            'remark',
            'created_at',
            'updated_at',
            'last_sampled_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_sampled_at']


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
    count = serializers.IntegerField(required=False, default=5, min_value=1, max_value=64)
    source = serializers.CharField(required=False, allow_blank=True)


class ToolMtrSerializer(serializers.Serializer):
    address = serializers.CharField()
    count = serializers.IntegerField(required=False, default=5, min_value=1, max_value=30)
    source = serializers.CharField(required=False, allow_blank=True)


class TrafficSampleRequestSerializer(serializers.Serializer):
    interface = serializers.CharField()
    window_sec = serializers.FloatField(required=False, default=1.0, min_value=0.2, max_value=5.0)


class TrafficBatchRequestSerializer(serializers.Serializer):
    interfaces = serializers.ListField(child=serializers.CharField(), allow_empty=False)
