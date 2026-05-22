from django.urls import include, path
from rest_framework.routers import DefaultRouter

from firewallmanage import views

router = DefaultRouter()
router.register('rules', views.FirewallRuleViewSet, basename='fw-rule')
router.register('nat-rules', views.NATRuleViewSet, basename='fw-nat')

urlpatterns = [
    path('health/', views.health, name='health'),
    path('settings/', views.FirewallSettingsView.as_view(), name='fw-settings'),
    path('status/', views.StatusView.as_view(), name='fw-status'),
    path('control/', views.ControlView.as_view(), name='fw-control'),
    path('ruleset/preview/', views.RulesetPreviewView.as_view(), name='fw-ruleset-preview'),
    path('ruleset/apply/', views.RulesetApplyView.as_view(), name='fw-ruleset-apply'),
    path('ruleset/show/', views.RulesetShowView.as_view(), name='fw-ruleset-show'),
    path('', include(router.urls)),
]
