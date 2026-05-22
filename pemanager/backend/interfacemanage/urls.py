from django.urls import include, path
from rest_framework.routers import DefaultRouter

from interfacemanage import views

db_router = DefaultRouter()
db_router.register('sync-runs', views.NetworkSyncRunViewSet, basename='iface-sync-run')
db_router.register('netplan-files', views.NetplanFileRecordViewSet, basename='iface-netplan-file')
db_router.register('interfaces', views.NetworkInterfaceRecordViewSet, basename='iface-db-interface')
db_router.register(
    'desired-tunnels',
    views.DesiredTunnelConfigViewSet,
    basename='iface-desired-tunnel',
)

urlpatterns = [
    path('health/', views.health, name='interfacemanage-health'),
    path('sources/netplan/', views.NetplanConfigView.as_view(), name='interfacemanage-netplan'),
    path('sources/kernel/', views.KernelStateView.as_view(), name='interfacemanage-kernel'),
    path('sources/wireguard/', views.WireGuardStateView.as_view(), name='interfacemanage-wireguard'),
    path('interfaces/', views.InterfaceInventoryView.as_view(), name='interfacemanage-interfaces'),
    path(
        'interfaces/export/',
        views.InterfaceExportView.as_view(),
        name='interfacemanage-interfaces-export',
    ),
    path(
        'interfaces/<str:ifname>/',
        views.InterfaceDetailView.as_view(),
        name='interfacemanage-interface-detail',
    ),
    path(
        'interfaces/<str:ifname>/preview-config/',
        views.InterfacePreviewConfigView.as_view(),
        name='interfacemanage-interface-preview-config',
    ),
    path(
        'interfaces/<str:ifname>/apply-config/',
        views.InterfaceApplyConfigView.as_view(),
        name='interfacemanage-interface-apply-config',
    ),
    path(
        'interfaces/<str:ifname>/remove-config/',
        views.InterfaceRemoveConfigView.as_view(),
        name='interfacemanage-interface-remove-config',
    ),
    path('db/sync/from-system/', views.SyncFromSystemView.as_view(), name='iface-db-sync-from-system'),
    path('db/drift/', views.NetworkDriftView.as_view(), name='iface-db-drift'),
    path('db/', include(db_router.urls)),
    path('tools/wg/genkey/', views.WireGuardGenKeyView.as_view(), name='iface-wg-genkey'),
    path('tools/wg/pubkey/', views.WireGuardPubKeyView.as_view(), name='iface-wg-pubkey'),
]
