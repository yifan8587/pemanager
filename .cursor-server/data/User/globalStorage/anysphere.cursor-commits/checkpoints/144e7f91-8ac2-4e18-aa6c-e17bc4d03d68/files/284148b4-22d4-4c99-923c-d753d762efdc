from rest_framework import serializers

from resourcemanage.models import (
    BandwidthAllocation,
    BandwidthPool,
    IPAddressEntry,
    ResourceCustomer,
    ResourceAllocationLog,
)


class ResourceCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceCustomer
        fields = ['id', 'code', 'name', 'remark', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class IPAddressEntrySerializer(serializers.ModelSerializer):
    customer_code = serializers.CharField(source='customer.code', read_only=True)

    class Meta:
        model = IPAddressEntry
        fields = [
            'id',
            'address',
            'state',
            'subnet_label',
            'customer',
            'customer_code',
            'interface_code',
            'extra',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BandwidthPoolSerializer(serializers.ModelSerializer):
    allocated_mbps = serializers.SerializerMethodField()
    remaining_mbps = serializers.SerializerMethodField()

    class Meta:
        model = BandwidthPool
        fields = [
            'id',
            'name',
            'total_mbps',
            'remark',
            'allocated_mbps',
            'remaining_mbps',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_allocated_mbps(self, obj):
        return obj.allocated_mbps()

    def get_remaining_mbps(self, obj):
        return obj.remaining_mbps()


class BandwidthAllocationSerializer(serializers.ModelSerializer):
    pool_name = serializers.CharField(source='pool.name', read_only=True)
    customer_code = serializers.CharField(source='customer.code', read_only=True)

    class Meta:
        model = BandwidthAllocation
        fields = [
            'id',
            'pool',
            'pool_name',
            'customer',
            'customer_code',
            'interface_code',
            'allocated_mbps',
            'remark',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ResourceAllocationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceAllocationLog
        fields = [
            'id',
            'created_at',
            'action',
            'actor',
            'summary',
            'detail',
            'correlation_id',
        ]
        read_only_fields = fields


class IPReserveSerializer(serializers.Serializer):
    address = serializers.IPAddressField()
    customer_code = serializers.SlugField(required=False, allow_blank=True)
    interface_code = serializers.CharField(required=False, allow_blank=True, default='')
    subnet_label = serializers.CharField(required=False, allow_blank=True, default='')
    actor = serializers.CharField(required=False, default='api')


class IPAllocateSerializer(serializers.Serializer):
    address = serializers.IPAddressField()
    customer_code = serializers.SlugField()
    interface_code = serializers.CharField(required=False, allow_blank=True, default='')
    subnet_label = serializers.CharField(required=False, allow_blank=True, default='')
    allow_from_reserved = serializers.BooleanField(default=True)
    actor = serializers.CharField(required=False, default='api')


class IPReleaseSerializer(serializers.Serializer):
    address = serializers.IPAddressField()
    actor = serializers.CharField(required=False, default='api')


class BandwidthUpsertSerializer(serializers.Serializer):
    pool_name = serializers.CharField()
    interface_code = serializers.CharField()
    allocated_mbps = serializers.IntegerField(min_value=1)
    customer_code = serializers.SlugField(required=False, allow_blank=True)
    remark = serializers.CharField(required=False, allow_blank=True, default='')
    actor = serializers.CharField(required=False, default='api')


class BandwidthDeleteSerializer(serializers.Serializer):
    pool_name = serializers.CharField()
    interface_code = serializers.CharField()
    actor = serializers.CharField(required=False, default='api')


class InboundSyncSerializer(serializers.Serializer):
    source_app = serializers.CharField()
    actor = serializers.CharField(required=False, default='sync')
    ip_updates = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    bandwidth_updates = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    bandwidth_removals = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
