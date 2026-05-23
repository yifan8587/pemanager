from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes as drf_permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accountmanage.permissions import IsAdmin, ReadOnlyForCustomer, CustomerScopedWritable
from accountmanage.scoped_mixins import AdminOnlyMixin
from accountmanage.services.scope import scope_interface_codes, scope_qs, is_admin

from resourcemanage.models import IPAddressEntry
from routemanage.models import DesiredRouteConfig, PolicyRouteRule
from routemanage.serializers import (
    DesiredRouteConfigSerializer,
    IPAddressEntryBriefSerializer,
    PolicyRouteRuleSerializer,
    import_routes_from_live_rows,
)
from routemanage.services import (
    iproute_writing,
    iprule_writing,
    netplan_routes,
    system_routes as system_routes_svc,
)

APP_NAME = 'routemanage'


@api_view(['GET'])
@drf_permission_classes([AllowAny])
def health(_request):
    return Response({'app': APP_NAME, 'status': 'ok'})


class SystemRoutesView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    """当前内核 IPv4/IPv6 路由表（`ip -json route show` 规范化结果）。
    支持 `?table=all` 或 `?table=<N>` 查看具体路由表。
    """

    def get(self, request):
        tbl = request.query_params.get('table') if hasattr(request, 'query_params') else None
        return Response(system_routes_svc.collect_system_routes(table=tbl))


class SystemRulesView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    """当前内核 ip rule 列表（`ip -json rule show` 规范化结果）。"""

    def get(self, request):
        fam = request.query_params.get('family') if hasattr(request, 'query_params') else None
        return Response(system_routes_svc.collect_system_rules(family=fam))


class DesiredRouteConfigViewSet(viewsets.ModelViewSet):
    """
    静态路由意图：CRUD + 分类下发。
    - apply-system: 非 WireGuard 接口路由 → netplan
    - apply-wireguard: WireGuard 接口路由 → ip route 直接下发，并写入 routable.d 持久化脚本

    客户作用域：按 user 可见接口名集合过滤；只读；下发动作仅 admin。
    """

    queryset = DesiredRouteConfig.objects.select_related(
        'ip_allocation',
        'ip_allocation__customer',
        'linked_interface',
        'customer',
    ).all()
    serializer_class = DesiredRouteConfigSerializer
    permission_classes = [IsAuthenticated, CustomerScopedWritable]

    def get_queryset(self):
        qs = super().get_queryset()
        return scope_qs(
            qs, self.request.user,
            customer_field='customer',
            interface_field='interface_name',
        )

    def _filter_ids_by_scope(self, request, ids):
        if ids is None:
            if is_admin(request.user):
                return None
            return list(self.get_queryset().values_list('id', flat=True))
        id_set = {str(i) for i in ids}
        allowed = {str(x) for x in self.get_queryset().values_list('id', flat=True)}
        return list(id_set & allowed)

    @action(detail=False, methods=['get'], url_path='preview-yaml')
    def preview_yaml(self, _request):
        """非 WG 静态路由的 netplan 片段预览（不写磁盘）。"""
        return Response(netplan_routes.preview_desired_routes_yaml())

    @action(detail=False, methods=['post'], url_path='apply-system')
    def apply_system(self, request):
        """
        分阶段下发（仅非 WG 接口）：
        - 不传 ids：全量重写 netplan fragment + netplan generate + netplan try
        - 传 ids: 仅对选中的非 WG 路由用 `ip route replace` 即时下发，不动 netplan
        - phase: validate | try | full（仅在全量模式下生效）
        """
        body = request.data if isinstance(request.data, dict) else {}
        phase = body.get('phase', 'full') if isinstance(body, dict) else 'full'
        if not isinstance(phase, str):
            phase = 'full'
        raw_ids = body.get('ids')
        ids = self._filter_ids_by_scope(request, raw_ids)
        if raw_ids is not None and ids is not None and not ids:
            return Response({'ok': False, 'error': '无可下发的路由（选中集合为空或越权）'},
                            status=status.HTTP_400_BAD_REQUEST)
        result = netplan_routes.apply_desired_routes_netplan(phase=phase, ids=ids)
        code = status.HTTP_200_OK if result.get('ok') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)

    @action(detail=False, methods=['get'], url_path='preview-wireguard')
    def preview_wireguard(self, _request):
        """WG 路由：每个 WG 接口对应的 conf 路径与即将注入的 PostUp/PostDown 块。"""
        return Response(iproute_writing.preview_wg_routes())

    @action(detail=False, methods=['post'], url_path='apply-wireguard')
    def apply_wireguard(self, request):
        """下发 WG 路由：

        body:
          - ids: 可选 list[str]；只对选中路由所属的 WG 接口执行 reconcile + wg-quick down/up，
            避免一次性重启全部 WG 接口。
        若不传 ids：admin 走全量；客户走"自己作用域内全部"。
        """
        body = request.data if isinstance(request.data, dict) else {}
        raw_ids = body.get('ids')
        ids = self._filter_ids_by_scope(request, raw_ids)
        if raw_ids is not None and ids is not None and not ids:
            return Response({'ok': False, 'error': '无可下发的路由（选中集合为空或越权）'},
                            status=status.HTTP_400_BAD_REQUEST)
        result = iproute_writing.apply_wg_routes(ids=ids)
        code = status.HTTP_200_OK if result.get('ok') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)

    @action(detail=False, methods=['post'], url_path='import-from-system', permission_classes=[IsAuthenticated, IsAdmin])
    def import_from_system(self, request):
        """将前端选中的内核路由快照批量转为路由意图（依赖已同步的接口库以推断 netplan 设备类）。"""
        routes = request.data.get('routes')
        if routes is None:
            return Response({'detail': '缺少 routes 列表'}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(routes, list):
            return Response({'detail': 'routes 须为列表'}, status=status.HTTP_400_BAD_REQUEST)
        payload = import_routes_from_live_rows(routes)
        return Response(payload, status=status.HTTP_200_OK)


class PolicyRouteRuleViewSet(viewsets.ModelViewSet):
    """策略路由意图：CRUD + ip rule 下发与预览。

    可见性：按 customer FK ∪ iif 接口码命中过滤；客户可在自己作用域内 CRUD 与下发。
    """

    queryset = PolicyRouteRule.objects.select_related('customer').all()
    serializer_class = PolicyRouteRuleSerializer
    permission_classes = [IsAuthenticated, CustomerScopedWritable]

    def get_queryset(self):
        return scope_qs(
            super().get_queryset(), self.request.user,
            customer_field='customer',
            interface_field='iif',
        )

    def _filter_ids_by_scope(self, request, ids):
        if ids is None:
            if is_admin(request.user):
                return None
            return list(self.get_queryset().values_list('id', flat=True))
        id_set = {str(i) for i in ids}
        allowed = {str(x) for x in self.get_queryset().values_list('id', flat=True)}
        return list(id_set & allowed)

    @action(detail=False, methods=['get'], url_path='preview')
    def preview(self, _request):
        return Response(iprule_writing.preview_policy_rules())

    @action(detail=False, methods=['post'], url_path='apply-system')
    def apply_system(self, request):
        """下发策略路由。

        body:
          - phase: preview | full（默认 full）
          - ids:   可选 list[str]，仅下发选中规则，且只 flush 这些规则对应 priority，
                   避免清空整个 owned-range 影响其它规则
        """
        body = request.data if isinstance(request.data, dict) else {}
        phase = body.get('phase', 'full') if isinstance(body, dict) else 'full'
        if not isinstance(phase, str):
            phase = 'full'
        raw_ids = body.get('ids')
        ids = self._filter_ids_by_scope(request, raw_ids)
        if raw_ids is not None and ids is not None and not ids:
            return Response({'ok': False, 'error': '无可下发的策略（选中集合为空或越权）'},
                            status=status.HTTP_400_BAD_REQUEST)
        result = iprule_writing.apply_policy_rules(phase=phase, ids=ids)
        code = status.HTTP_200_OK if result.get('ok') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


class AllocatedIpChoicesView(APIView):
    """已分配/预留 IP 列表，用于与路由意图关联。"""

    def get(self, _request):
        qs = (
            IPAddressEntry.objects.filter(
                state__in=[
                    IPAddressEntry.State.ALLOCATED,
                    IPAddressEntry.State.RESERVED,
                ]
            )
            .select_related('customer')
            .order_by('address')
        )
        return Response(IPAddressEntryBriefSerializer(qs, many=True).data)
