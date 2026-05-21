from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from resourcemanage.models import IPAddressEntry
from routemanage.models import DesiredRouteConfig
from routemanage.serializers import (
    DesiredRouteConfigSerializer,
    IPAddressEntryBriefSerializer,
    import_routes_from_live_rows,
)
from routemanage.services import netplan_routes
from routemanage.services.system_routes import collect_system_routes

APP_NAME = 'routemanage'


@api_view(['GET'])
def health(_request):
    return Response({'app': APP_NAME, 'status': 'ok'})


class SystemRoutesView(APIView):
    """当前内核 IPv4/IPv6 路由表（`ip -json route show` 规范化结果）。"""

    def get(self, _request):
        return Response(collect_system_routes())


class DesiredRouteConfigViewSet(viewsets.ModelViewSet):
    """静态路由意图：CRUD + 下发到 netplan 并 netplan try。"""

    queryset = DesiredRouteConfig.objects.select_related(
        'ip_allocation',
        'ip_allocation__customer',
        'linked_interface',
    ).all()
    serializer_class = DesiredRouteConfigSerializer

    @action(detail=False, methods=['get'], url_path='preview-yaml')
    def preview_yaml(self, _request):
        """仅预览将要生成的 netplan 片段（不写磁盘）。"""
        return Response(netplan_routes.preview_desired_routes_yaml())

    @action(detail=False, methods=['post'], url_path='apply-system')
    def apply_system(self, request):
        """
        分阶段下发：
        - phase=validate: 写入片段 + netplan generate
        - phase=try: 仅 netplan try（需先执行 validate 写入当前意图）
        - phase=full: 写入 + generate + try（默认）
        """
        phase = request.data.get('phase', 'full') if isinstance(getattr(request, 'data', None), dict) else 'full'
        if not isinstance(phase, str):
            phase = 'full'
        result = netplan_routes.apply_desired_routes_netplan(phase=phase)
        code = status.HTTP_200_OK if result.get('ok') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)

    @action(detail=False, methods=['post'], url_path='import-from-system')
    def import_from_system(self, request):
        """将前端选中的内核路由快照批量转为路由意图（依赖已同步的接口库以推断 netplan 设备类）。"""
        routes = request.data.get('routes')
        if routes is None:
            return Response({'detail': '缺少 routes 列表'}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(routes, list):
            return Response({'detail': 'routes 须为列表'}, status=status.HTTP_400_BAD_REQUEST)
        payload = import_routes_from_live_rows(routes)
        return Response(payload, status=status.HTTP_200_OK)


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
