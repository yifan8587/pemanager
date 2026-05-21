from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from qosmanage.models import QoSPolicy, QoSRule
from qosmanage.serializers import QoSPolicySerializer, QoSRuleSerializer
from qosmanage.services import tc_writer

APP_NAME = 'qosmanage'


@api_view(['GET'])
def health(_request):
    return Response({'app': APP_NAME, 'status': 'ok'})


class QoSPolicyViewSet(viewsets.ModelViewSet):
    queryset = QoSPolicy.objects.prefetch_related('rules').all()
    serializer_class = QoSPolicySerializer

    @action(detail=True, methods=['get'], url_path='preview')
    def preview(self, request, pk=None):
        policy = self.get_object()
        return Response(tc_writer.render_preview(policy))

    @action(detail=True, methods=['post'], url_path='apply-system')
    def apply_system(self, request, pk=None):
        policy = self.get_object()
        phase = request.data.get('phase') if isinstance(request.data, dict) else 'apply'
        if phase not in ('apply', 'clear', 'preview'):
            phase = 'apply'
        result = tc_writer.apply_policy(policy, phase=phase)
        code = status.HTTP_200_OK if result.get('ok') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)

    @action(detail=True, methods=['get'], url_path='show-system')
    def show_system(self, request, pk=None):
        policy = self.get_object()
        return Response(tc_writer.show_tc(policy.interface_name))


class QoSRuleViewSet(viewsets.ModelViewSet):
    queryset = QoSRule.objects.select_related('policy').all()
    serializer_class = QoSRuleSerializer
