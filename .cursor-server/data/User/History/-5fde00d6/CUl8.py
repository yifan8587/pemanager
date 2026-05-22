from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from firewallmanage.models import FirewallRule, FirewallSettings, NATRule
from firewallmanage.serializers import (
    FirewallRuleSerializer,
    FirewallSettingsSerializer,
    NATRuleSerializer,
)
from firewallmanage.services import engine as fw_engine
from firewallmanage.services import runtime as fw_runtime

APP_NAME = 'firewallmanage'


@api_view(['GET'])
def health(_request):
    return Response({'app': APP_NAME, 'status': 'ok'})


class FirewallRuleViewSet(viewsets.ModelViewSet):
    queryset = FirewallRule.objects.all().order_by('chain', 'priority', 'created_at')
    serializer_class = FirewallRuleSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get('chain'):
            qs = qs.filter(chain=p['chain'])
        if p.get('action'):
            qs = qs.filter(action=p['action'])
        if p.get('enabled') in ('1', 'true', 'yes'):
            qs = qs.filter(enabled=True)
        elif p.get('enabled') in ('0', 'false', 'no'):
            qs = qs.filter(enabled=False)
        return qs


class NATRuleViewSet(viewsets.ModelViewSet):
    queryset = NATRule.objects.all().order_by('kind', 'priority', 'created_at')
    serializer_class = NATRuleSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get('kind'):
            qs = qs.filter(kind=p['kind'])
        if p.get('enabled') in ('1', 'true', 'yes'):
            qs = qs.filter(enabled=True)
        elif p.get('enabled') in ('0', 'false', 'no'):
            qs = qs.filter(enabled=False)
        return qs


class FirewallSettingsView(APIView):
    """GET / PATCH 单例。"""

    def get(self, _request):
        return Response(FirewallSettingsSerializer(FirewallSettings.load()).data)

    def patch(self, request):
        obj = FirewallSettings.load()
        ser = FirewallSettingsSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class StatusView(APIView):
    def get(self, _request):
        return Response(fw_runtime.status())


class ControlView(APIView):
    """POST { unit: 'nftables', action: 'start|stop|enable|disable|restart|reload' }"""

    def post(self, request):
        unit = (request.data or {}).get('unit', 'nftables')
        action = (request.data or {}).get('action', 'restart')
        result = fw_runtime.control(unit, action)
        code = status.HTTP_200_OK if result.get('ok') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


class RulesetPreviewView(APIView):
    """GET: 仅生成预览（按当前引擎）。"""

    def get(self, _request):
        return Response({'ok': True, **fw_engine.render_ruleset()})


class RulesetApplyView(APIView):
    """POST: { phase: preview | validate | apply | flush }"""

    def post(self, request):
        phase = request.data.get('phase', 'apply') if isinstance(request.data, dict) else 'apply'
        if phase not in ('preview', 'validate', 'apply', 'flush'):
            phase = 'apply'
        result = fw_engine.apply_ruleset(phase=phase)
        code = status.HTTP_200_OK if result.get('ok') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


class RulesetShowView(APIView):
    """GET: 列出当前引擎的真实表（nft list / iptables -S）。"""

    def get(self, _request):
        return Response(fw_engine.show_ruleset())
