from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from resourcemanage.models import (
    BandwidthAllocation,
    BandwidthPool,
    IPAddressEntry,
    ResourceCustomer,
    ResourceAllocationLog,
)
from resourcemanage.serializers import (
    BandwidthAllocationSerializer,
    BandwidthDeleteSerializer,
    BandwidthPoolSerializer,
    BandwidthUpsertSerializer,
    InboundSyncSerializer,
    IPAddressEntrySerializer,
    IPAllocateSerializer,
    IPReleaseSerializer,
    IPReserveSerializer,
    ResourceAllocationLogSerializer,
    ResourceCustomerSerializer,
)
from resourcemanage.services.inbound import apply_inbound_payload
from resourcemanage.services import operations

APP_NAME = 'resourcemanage'


@api_view(['GET'])
def health(_request):
    return Response({'app': APP_NAME, 'status': 'ok'})


class ResourceCustomerViewSet(viewsets.ModelViewSet):
    queryset = ResourceCustomer.objects.all().order_by('code')
    serializer_class = ResourceCustomerSerializer


class IPAddressEntryViewSet(viewsets.ModelViewSet):
    queryset = IPAddressEntry.objects.select_related('customer').all().order_by('address')
    serializer_class = IPAddressEntrySerializer

    @action(detail=False, methods=['post'], url_path='actions/reserve')
    def reserve(self, request):
        s = IPReserveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        cust = None
        if data.get('customer_code'):
            cust = ResourceCustomer.objects.filter(code=data['customer_code']).first()
            if not cust:
                raise DRFValidationError({'customer_code': '客户不存在'})
        try:
            entry = operations.reserve_ip(
                address=str(data['address']),
                customer=cust,
                interface_code=data.get('interface_code') or '',
                subnet_label=data.get('subnet_label') or '',
                actor=data.get('actor') or 'api',
            )
        except Exception as e:  # noqa: BLE001
            raise DRFValidationError(str(e)) from e
        return Response(IPAddressEntrySerializer(entry).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='actions/allocate')
    def allocate(self, request):
        s = IPAllocateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        cust = ResourceCustomer.objects.filter(code=data['customer_code']).first()
        if not cust:
            raise DRFValidationError({'customer_code': '客户不存在'})
        try:
            entry = operations.allocate_ip(
                address=str(data['address']),
                customer=cust,
                interface_code=data.get('interface_code') or '',
                subnet_label=data.get('subnet_label') or '',
                allow_from_reserved=data.get('allow_from_reserved', True),
                actor=data.get('actor') or 'api',
            )
        except Exception as e:  # noqa: BLE001
            raise DRFValidationError(str(e)) from e
        return Response(IPAddressEntrySerializer(entry).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='actions/release')
    def release(self, request):
        s = IPReleaseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        try:
            operations.release_ip(
                address=str(data['address']),
                actor=data.get('actor') or 'api',
            )
        except Exception as e:  # noqa: BLE001
            raise DRFValidationError(str(e)) from e
        return Response(status=status.HTTP_204_NO_CONTENT)


class BandwidthPoolViewSet(viewsets.ModelViewSet):
    queryset = BandwidthPool.objects.all().order_by('name')
    serializer_class = BandwidthPoolSerializer


class BandwidthAllocationViewSet(viewsets.ModelViewSet):
    queryset = BandwidthAllocation.objects.select_related('pool', 'customer').all()
    serializer_class = BandwidthAllocationSerializer

    @action(detail=False, methods=['post'], url_path='actions/upsert')
    def upsert(self, request):
        s = BandwidthUpsertSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        pool = BandwidthPool.objects.filter(name=data['pool_name']).first()
        if not pool:
            raise DRFValidationError({'pool_name': '带宽池不存在'})
        cust = None
        if data.get('customer_code'):
            cust = ResourceCustomer.objects.filter(code=data['customer_code']).first()
            if not cust:
                raise DRFValidationError({'customer_code': '客户不存在'})
        try:
            alloc = operations.upsert_bandwidth_allocation(
                pool=pool,
                interface_code=data['interface_code'],
                allocated_mbps=data['allocated_mbps'],
                customer=cust,
                remark=data.get('remark') or '',
                actor=data.get('actor') or 'api',
            )
        except Exception as e:  # noqa: BLE001
            raise DRFValidationError(str(e)) from e
        return Response(BandwidthAllocationSerializer(alloc).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='actions/delete-by-key')
    def delete_by_key(self, request):
        s = BandwidthDeleteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        pool = BandwidthPool.objects.filter(name=data['pool_name']).first()
        if not pool:
            raise DRFValidationError({'pool_name': '带宽池不存在'})
        try:
            operations.delete_bandwidth_allocation(
                pool=pool,
                interface_code=data['interface_code'],
                actor=data.get('actor') or 'api',
            )
        except Exception as e:  # noqa: BLE001
            raise DRFValidationError(str(e)) from e
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResourceAllocationLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ResourceAllocationLog.objects.all()
    serializer_class = ResourceAllocationLogSerializer


class ResourceSummaryAPIView(APIView):
    """当前 PE 资源概览：IP 状态分布、带宽池用量。"""

    def get(self, request):
        ip_rows = IPAddressEntry.objects.values('state').annotate(c=Count('id'))
        ip_stats = {row['state']: row['c'] for row in ip_rows}
        pools = []
        for p in BandwidthPool.objects.all().order_by('name'):
            pools.append(
                {
                    'id': p.pk,
                    'name': p.name,
                    'total_mbps': p.total_mbps,
                    'allocated_mbps': p.allocated_mbps(),
                    'remaining_mbps': p.remaining_mbps(),
                }
            )
        return Response({'ip_by_state': ip_stats, 'bandwidth_pools': pools})


class InboundSyncAPIView(APIView):
    """供其他应用在配置变更后回写资源"""

    def post(self, request):
        s = InboundSyncSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        payload = {
            'ip_updates': data.get('ip_updates') or [],
            'bandwidth_updates': data.get('bandwidth_updates') or [],
            'bandwidth_removals': data.get('bandwidth_removals') or [],
        }
        result = apply_inbound_payload(
            payload,
            source_app=data['source_app'],
            actor=data.get('actor') or 'sync',
        )
        return Response(result, status=status.HTTP_200_OK)
