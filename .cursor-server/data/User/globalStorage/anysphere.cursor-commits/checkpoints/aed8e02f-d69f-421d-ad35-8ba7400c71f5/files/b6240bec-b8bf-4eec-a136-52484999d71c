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
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = IPAddressEntry
        fields = [
            'id',
            'address',
            'state',
            'subnet_label',
            'customer',
            'customer_code',
            'customer_name',
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
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = BandwidthAllocation
        fields = [
            'id',
            'pool',
            'pool_name',
            'customer',
            'customer_code',
            'customer_name',
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


class IPRecycleSerializer(serializers.Serializer):
    address = serializers.IPAddressField()
    reason = serializers.CharField(required=False, allow_blank=True, default='')
    actor = serializers.CharField(required=False, default='api')


class IPRestoreSerializer(serializers.Serializer):
    address = serializers.IPAddressField()
    actor = serializers.CharField(required=False, default='api')


class _RouteIntentSerializer(serializers.Serializer):
    """allocate-with-route 时附带的路由意图（全部可选；缺 dest_cidr 时不创建路由）。"""

    dest_cidr = serializers.CharField(required=False, allow_blank=True, default='')
    gateway = serializers.IPAddressField(required=False, allow_null=True, allow_blank=False)
    on_link = serializers.BooleanField(required=False, default=False)
    metric = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    route_table = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    netplan_device_class = serializers.CharField(required=False, allow_blank=True)
    interface_name = serializers.CharField(required=False, allow_blank=True)
    remark = serializers.CharField(required=False, allow_blank=True, default='')


class IPAllocateWithRouteSerializer(IPAllocateSerializer):
    route = _RouteIntentSerializer(required=False)


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


