from rest_framework import filters, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from logmanage.models import AppOperationLog
from logmanage.serializers import AppOperationLogSerializer
from logmanage.services import journal

APP_NAME = 'logmanage'


@api_view(['GET'])
def health(_request):
    return Response({'app': APP_NAME, 'status': 'ok'})


class AppOperationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """应用操作日志：只读 + 过滤。"""

    queryset = AppOperationLog.objects.all()
    serializer_class = AppOperationLogSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['summary', 'app', 'category', 'actor', 'target']
    ordering_fields = ['created_at', 'level', 'app']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        for f in ('app', 'category', 'level', 'actor', 'target'):
            v = params.get(f)
            if v:
                qs = qs.filter(**{f: v})
        if params.get('since'):
            qs = qs.filter(created_at__gte=params['since'])
        if params.get('until'):
            qs = qs.filter(created_at__lt=params['until'])
        return qs


class JournalQueryView(APIView):
    """GET: journalctl 包装查询。"""

    def get(self, request):
        p = request.query_params
        try:
            lines = int(p.get('lines') or 200)
        except ValueError:
            lines = 200
        return Response(
            journal.query(
                unit=p.get('unit'),
                since=p.get('since'),
                until=p.get('until'),
                grep=p.get('grep'),
                priority=p.get('priority'),
                lines=lines,
            )
        )


class JournalUnitsView(APIView):
    """GET: 列举可选的 systemd 单元（service）。"""

    def get(self, request):
        return Response(journal.list_units(pattern=request.query_params.get('pattern')))
