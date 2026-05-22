from django.db.models import Count, Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes as drf_permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accountmanage.permissions import IsAdmin, ReadOnlyForCustomer
from accountmanage.scoped_mixins import AdminOnlyMixin, CustomerScopedByCustomerFKMixin
from accountmanage.services.scope import scope_customer

from qosmanage.models import QoSPolicy, QoSRule
from qosmanage.serializers import QoSPolicySerializer, QoSRuleSerializer
from qosmanage.services import tc_writer

APP_NAME = 'qosmanage'


@api_view(['GET'])
@drf_permission_classes([AllowAny])
def health(_request):
    return Response({'app': APP_NAME, 'status': 'ok'})


class QoSPolicyViewSet(CustomerScopedByCustomerFKMixin, viewsets.ModelViewSet):
    serializer_class = QoSPolicySerializer
    customer_field = 'customer'

    def get_queryset(self):
        qs = (
            QoSPolicy.objects.prefetch_related('rules')
            .select_related('customer', 'linked_pool', 'linked_interface', 'synced_bandwidth_allocation')
            .all()
        )
        # 先按客户作用域裁剪
        cust = scope_customer(self.request.user)
        if cust is not None:
            qs = qs.filter(customer=cust)
        p = self.request.query_params
        if p.get('interface_name'):
            qs = qs.filter(interface_name=p['interface_name'])
        if p.get('customer'):
            qs = qs.filter(customer__code=p['customer'])
        if p.get('enabled') in ('1', 'true', 'yes'):
            qs = qs.filter(enabled=True)
        elif p.get('enabled') in ('0', 'false', 'no'):
            qs = qs.filter(enabled=False)
        if p.get('root_kind'):
            qs = qs.filter(root_kind=p['root_kind'])
        return qs

    @action(detail=True, methods=['get'], url_path='preview')
    def preview(self, request, pk=None):
        policy = self.get_object()
        return Response(tc_writer.render_preview(policy))

    @action(detail=True, methods=['post'], url_path='apply-system', permission_classes=[IsAuthenticated, IsAdmin])
    def apply_system(self, request, pk=None):
        policy = self.get_object()
        phase = request.data.get('phase') if isinstance(request.data, dict) else 'apply'
        if phase not in ('apply', 'clear', 'preview'):
            phase = 'apply'
        result = tc_writer.apply_policy(policy, phase=phase)
        code = status.HTTP_200_OK if result.get('ok') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)

    @action(detail=True, methods=['get'], url_path='show-system', permission_classes=[IsAuthenticated, IsAdmin])
    def show_system(self, request, pk=None):
        policy = self.get_object()
        return Response(tc_writer.show_tc(policy.interface_name))


class QoSRuleViewSet(AdminOnlyMixin, viewsets.ModelViewSet):
    queryset = QoSRule.objects.select_related('policy').all()
    serializer_class = QoSRuleSerializer


class QoSSummaryAPIView(APIView):
    """QoS 全局概览：策略数 / 启用数 / 关联客户 / 关联接口 / 总下行带宽。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        total = QoSPolicy.objects.count()
        enabled = QoSPolicy.objects.filter(enabled=True).count()
        by_kind = dict(
            QoSPolicy.objects.values('root_kind').annotate(c=Count('id')).values_list('root_kind', 'c')
        )
        ifaces = QoSPolicy.objects.values('interface_name').distinct().count()
        customers = (
            QoSPolicy.objects.filter(customer__isnull=False)
            .values('customer__code')
            .distinct()
            .count()
        )
        total_rate = (
            QoSPolicy.objects.filter(enabled=True).aggregate(s=Sum('rate_mbps')).get('s') or 0
        )
        # effective 在 Python 侧算（含 headroom），数据集很小，开销可忽略
        total_effective = sum(
            p.effective_rate_mbps for p in QoSPolicy.objects.filter(enabled=True)
        )
        by_pool = []
        for row in (
            QoSPolicy.objects.filter(linked_pool__isnull=False)
            .values('linked_pool__name')
            .annotate(c=Count('id'), s=Sum('rate_mbps'))
            .order_by('linked_pool__name')
        ):
            by_pool.append(
                {
                    'pool_name': row['linked_pool__name'],
                    'policies': int(row['c']),
                    'allocated_mbps': int(row['s'] or 0),
                }
            )
        return Response(
            {
                'total': total,
                'enabled': enabled,
                'disabled': total - enabled,
                'by_root_kind': by_kind,
                'interfaces': ifaces,
                'customers': customers,
                'total_rate_mbps': int(total_rate),
                'total_effective_mbps': int(total_effective),
                'by_pool': by_pool,
            }
        )
