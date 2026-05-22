from datetime import datetime

from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from operationmanage.models import (
    InterfaceTrafficSample,
    LatencySample,
    MonitorTarget,
)
from operationmanage.serializers import (
    InterfaceTrafficSampleSerializer,
    LatencySampleSerializer,
    MonitorTargetSerializer,
    ToolMtrSerializer,
    ToolPingSerializer,
    TrafficBatchRequestSerializer,
    TrafficSampleRequestSerializer,
)
from operationmanage.services import aggregate, probes, sampler

APP_NAME = 'operationmanage'


@api_view(['GET'])
def health(_request):
    return Response({'app': APP_NAME, 'status': 'ok'})


# ---------- 工具：ping / mtr / traffic ----------


class ToolPingView(APIView):
    def post(self, request):
        s = ToolPingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        out = probes.ping(
            v['address'],
            count=v.get('count') or 5,
            source=(v.get('source') or '').strip() or None,
        )
        return Response(out)


class ToolMtrView(APIView):
    def post(self, request):
        s = ToolMtrSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        out = probes.mtr(
            v['address'],
            count=v.get('count') or 5,
            source=(v.get('source') or '').strip() or None,
        )
        return Response(out)


class ToolTrafficLiveView(APIView):
    """前端轮询使用：单接口窗口 bps（替代 nload 的可视）。"""

    def post(self, request):
        s = TrafficSampleRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        out = probes.traffic_live_window(v['interface'], window_sec=float(v.get('window_sec') or 1.0))
        return Response(out)


class ToolTrafficBatchView(APIView):
    """一次给多接口的累计字节 + bps 增量快照（落库）。"""

    def post(self, request):
        s = TrafficBatchRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(sampler.sample_interfaces(s.validated_data['interfaces']))


class ToolTrafficSnapshotView(APIView):
    """GET: /proc/net/dev 全量累计快照（不落库）。"""

    def get(self, _request):
        return Response(probes.proc_net_dev_all())


# ---------- 监控目标 CRUD ----------


class MonitorTargetViewSet(viewsets.ModelViewSet):
    queryset = MonitorTarget.objects.all().order_by('name')
    serializer_class = MonitorTargetSerializer

    @action(detail=True, methods=['post'], url_path='sample-now')
    def sample_now(self, request, pk=None):
        target = self.get_object()
        try:
            s = sampler.sample_one_target(target)
        except Exception as exc:  # noqa: BLE001
            return Response({'ok': False, 'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LatencySampleSerializer(s).data)

    @action(detail=True, methods=['get'], url_path='series')
    def series(self, request, pk=None):
        """按 bucket=hour|day|month 聚合延迟样本。"""
        target = self.get_object()
        p = request.query_params
        bucket = p.get('bucket') or 'hour'
        qs = target.latency_samples.all()
        since = parse_datetime(p.get('since') or '') if p.get('since') else None
        until = parse_datetime(p.get('until') or '') if p.get('until') else None
        if since:
            qs = qs.filter(ts__gte=since)
        if until:
            qs = qs.filter(ts__lt=until)
        try:
            limit = int(p.get('limit') or 1000)
        except ValueError:
            limit = 1000
        series = aggregate.latency_series(qs, bucket=bucket)
        if len(series) > limit:
            series = series[-limit:]
        return Response({'target': target.name, 'bucket': bucket, 'points': series})


# ---------- 样本只读 ----------


class LatencySampleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LatencySample.objects.select_related('target').all()
    serializer_class = LatencySampleSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        tid = p.get('target')
        if tid:
            qs = qs.filter(target_id=tid)
        if p.get('since'):
            qs = qs.filter(ts__gte=p['since'])
        if p.get('until'):
            qs = qs.filter(ts__lt=p['until'])
        try:
            limit = int(p.get('limit') or 500)
        except ValueError:
            limit = 500
        return qs.order_by('-ts')[:limit]


class InterfaceTrafficSampleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = InterfaceTrafficSample.objects.all()
    serializer_class = InterfaceTrafficSampleSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        ifn = p.get('interface')
        if ifn:
            qs = qs.filter(interface_name=ifn)
        if p.get('since'):
            qs = qs.filter(ts__gte=p['since'])
        if p.get('until'):
            qs = qs.filter(ts__lt=p['until'])
        try:
            limit = int(p.get('limit') or 500)
        except ValueError:
            limit = 500
        return qs.order_by('-ts')[:limit]


class InterfaceTrafficSeriesView(APIView):
    """GET: ?interface=eth0&bucket=hour|day|month&since=&until="""

    def get(self, request):
        p = request.query_params
        ifn = p.get('interface')
        if not ifn:
            return Response({'detail': '缺少 interface'}, status=status.HTTP_400_BAD_REQUEST)
        bucket = p.get('bucket') or 'hour'
        qs = InterfaceTrafficSample.objects.filter(interface_name=ifn)
        if p.get('since'):
            qs = qs.filter(ts__gte=p['since'])
        if p.get('until'):
            qs = qs.filter(ts__lt=p['until'])
        return Response(
            {
                'interface': ifn,
                'bucket': bucket,
                'points': aggregate.traffic_series(qs, bucket=bucket),
            }
        )


# ---------- 触发采样 ----------


class SampleAllNowView(APIView):
    """POST: 立即对所有启用 target 做一轮采样；可附 ?interfaces=eth0,wg0 同步采流量。"""

    def post(self, request):
        ifs_param = request.data.get('interfaces') if isinstance(request.data, dict) else None
        if isinstance(ifs_param, str):
            ifs = [s.strip() for s in ifs_param.split(',') if s.strip()]
        elif isinstance(ifs_param, list):
            ifs = [str(s).strip() for s in ifs_param if str(s).strip()]
        else:
            ifs = []
        out = {'latency': sampler.sample_all_targets()}
        if ifs:
            out['traffic'] = sampler.sample_interfaces(ifs)
        return Response(out)
