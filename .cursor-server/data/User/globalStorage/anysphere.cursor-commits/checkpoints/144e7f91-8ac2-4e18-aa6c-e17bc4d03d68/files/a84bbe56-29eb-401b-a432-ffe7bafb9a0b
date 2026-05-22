from django.urls import include, path
from rest_framework.routers import DefaultRouter

from resourcemanage import views

router = DefaultRouter()
router.register('customers', views.ResourceCustomerViewSet, basename='resource-customer')
router.register('ip-addresses', views.IPAddressEntryViewSet, basename='ip-address')
router.register('bandwidth-pools', views.BandwidthPoolViewSet, basename='bandwidth-pool')
router.register(
    'bandwidth-allocations',
    views.BandwidthAllocationViewSet,
    basename='bandwidth-allocation',
)
router.register('allocation-logs', views.ResourceAllocationLogViewSet, basename='allocation-log')

urlpatterns = [
    path('health/', views.health, name='health'),
    path('summary/', views.ResourceSummaryAPIView.as_view(), name='resource-summary'),
    path('sync/inbound/', views.InboundSyncAPIView.as_view(), name='resource-sync-inbound'),
    path('', include(router.urls)),
]
