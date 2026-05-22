from django.urls import include, path
from rest_framework.routers import DefaultRouter

from operationmanage import views

router = DefaultRouter()
router.register('monitor-targets', views.MonitorTargetViewSet, basename='monitor-target')
router.register('latency-samples', views.LatencySampleViewSet, basename='latency-sample')
router.register('traffic-samples', views.InterfaceTrafficSampleViewSet, basename='traffic-sample')

urlpatterns = [
    path('health/', views.health, name='health'),
    path('tools/ping/', views.ToolPingView.as_view(), name='tool-ping'),
    path('tools/mtr/', views.ToolMtrView.as_view(), name='tool-mtr'),
    path('tools/traffic/live/', views.ToolTrafficLiveView.as_view(), name='tool-traffic-live'),
    path('tools/traffic/batch/', views.ToolTrafficBatchView.as_view(), name='tool-traffic-batch'),
    path('tools/traffic/snapshot/', views.ToolTrafficSnapshotView.as_view(), name='tool-traffic-snapshot'),
    path('traffic-series/', views.InterfaceTrafficSeriesView.as_view(), name='traffic-series'),
    path('sample-now/', views.SampleAllNowView.as_view(), name='sample-now'),
    path('', include(router.urls)),
]
