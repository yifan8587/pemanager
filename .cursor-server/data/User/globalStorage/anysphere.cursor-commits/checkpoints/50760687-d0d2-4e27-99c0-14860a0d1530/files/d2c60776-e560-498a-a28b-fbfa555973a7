from django.urls import include, path
from rest_framework.routers import DefaultRouter

from routemanage import views

router = DefaultRouter()
router.register('desired-routes', views.DesiredRouteConfigViewSet, basename='route-desired')

urlpatterns = [
    path('health/', views.health, name='routemanage-health'),
    path('system-routes/', views.SystemRoutesView.as_view(), name='routemanage-system-routes'),
    path('ip-allocation-choices/', views.AllocatedIpChoicesView.as_view(), name='route-ip-choices'),
    path('', include(router.urls)),
]
