from django.urls import include, path
from rest_framework.routers import DefaultRouter

from routemanage import views

router = DefaultRouter()
router.register('desired-routes', views.DesiredRouteConfigViewSet, basename='route-desired')
router.register('policy-rules', views.PolicyRouteRuleViewSet, basename='route-policy-rule')

urlpatterns = [
    path('health/', views.health, name='routemanage-health'),
    path('system-routes/', views.SystemRoutesView.as_view(), name='routemanage-system-routes'),
    path('system-rules/', views.SystemRulesView.as_view(), name='routemanage-system-rules'),
    path('ip-allocation-choices/', views.AllocatedIpChoicesView.as_view(), name='route-ip-choices'),
    path('', include(router.urls)),
]
