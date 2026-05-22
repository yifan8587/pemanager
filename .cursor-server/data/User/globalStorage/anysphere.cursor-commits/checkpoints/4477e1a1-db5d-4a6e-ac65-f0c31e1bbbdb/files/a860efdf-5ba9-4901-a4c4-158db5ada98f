from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from firewallmanage.models import FirewallRule
from firewallmanage.serializers import FirewallRuleSerializer
from firewallmanage.services import nft_writer

APP_NAME = 'firewallmanage'


@api_view(['GET'])
def health(_request):
    return Response({'app': APP_NAME, 'status': 'ok'})


class FirewallRuleViewSet(viewsets.ModelViewSet):
    queryset = FirewallRule.objects.all().order_by('chain', 'priority', 'created_at')
    serializer_class = FirewallRuleSerializer


class RulesetPreviewView(APIView):
    """GET: 仅生成预览；不写盘、不调用 nft。"""

    def get(self, _request):
        return Response({'ok': True, 'ruleset': nft_writer.render_ruleset()})


class RulesetApplyView(APIView):
    """POST: { phase: preview | validate | apply | flush }"""

    def post(self, request):
        phase = request.data.get('phase', 'apply') if isinstance(request.data, dict) else 'apply'
        if phase not in ('preview', 'validate', 'apply', 'flush'):
            phase = 'apply'
        result = nft_writer.apply_ruleset(phase=phase)
        code = status.HTTP_200_OK if result.get('ok') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


class RulesetShowView(APIView):
    """GET: nft list table inet pemanager"""

    def get(self, _request):
        return Response(nft_writer.show_ruleset())
