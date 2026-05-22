from rest_framework import serializers

from interfacemanage.models import NetworkInterfaceRecord
from qosmanage.models import QoSPolicy, QoSRule
from resourcemanage.models import BandwidthPool, ResourceCustomer


class QoSRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = QoSRule
        fields = [
            'id',
            'policy',
            'class_id',
            'rate_mbps',
            'ceil_mbps',
            'priority',
            'match_kind',
            'match_value',
            'remark',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        obj = QoSRule(**validated_data)
        obj.full_clean()
        obj.save()
        return obj

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.full_clean()
        instance.save()
        return instance


class QoSPolicySerializer(serializers.ModelSerializer):
    customer = serializers.SlugRelatedField(
        slug_field='code',
        queryset=ResourceCustomer.objects.all(),
        allow_null=True,
        required=False,
    )
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)
    linked_pool = serializers.SlugRelatedField(
        slug_field='name',
        queryset=BandwidthPool.objects.all(),
        allow_null=True,
        required=False,
    )
    linked_pool_total_mbps = serializers.IntegerField(source='linked_pool.total_mbps', read_only=True, default=None)
    linked_interface = serializers.SlugRelatedField(
        slug_field='ifname',
        queryset=NetworkInterfaceRecord.objects.all(),
        allow_null=True,
        required=False,
    )
    interface_kind = serializers.CharField(source='linked_interface.kind', read_only=True, default=None)
    effective_rate_mbps = serializers.IntegerField(read_only=True)
    synced_bandwidth_allocation_id = serializers.IntegerField(
        source='synced_bandwidth_allocation.pk', read_only=True, default=None
    )

    class Meta:
        model = QoSPolicy
        fields = [
            'id',
            'name',
            'interface_name',
            'linked_interface',
            'interface_kind',
            'customer',
            'customer_name',
            'linked_pool',
            'linked_pool_total_mbps',
            'direction',
            'root_kind',
            'rate_mbps',
            'headroom_pct',
            'effective_rate_mbps',
            'burst_kb',
            'latency_ms',
            'enabled',
            'remark',
            'synced_bandwidth_allocation_id',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'effective_rate_mbps',
            'interface_kind',
            'customer_name',
            'linked_pool_total_mbps',
            'synced_bandwidth_allocation_id',
            'created_at',
            'updated_at',
        ]

    def create(self, validated_data):
        obj = QoSPolicy(**validated_data)
        obj.full_clean()
        obj.save()
        return obj

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.full_clean()
        instance.save()
        return instance
