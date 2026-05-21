from django.urls import include, path
from rest_framework.routers import DefaultRouter

from qosmanage import views

router = DefaultRouter()
router.register('policies', views.QoSPolicyViewSet, basename='qos-policy')
router.register('rules', views.QoSRuleViewSet, basename='qos-rule')

urlpatterns = [
    path('health/', views.health, name='health'),
    path('', include(router.urls)),
]
