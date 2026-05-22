from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from accountmanage import views

router = DefaultRouter()
router.register('users', views.UserViewSet, basename='user')
router.register('api-tokens', views.APITokenViewSet, basename='api-token')
router.register('login-attempts', views.LoginAttemptViewSet, basename='login-attempt')


urlpatterns = [
    path('health/', views.health, name='accountmanage-health'),
    path('auth/login/', views.LoginView.as_view(), name='auth-login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/verify/', TokenVerifyView.as_view(), name='auth-verify'),
    path('auth/logout/', views.LogoutView.as_view(), name='auth-logout'),
    path('auth/me/', views.MeView.as_view(), name='auth-me'),
    path('auth/change-password/', views.ChangePasswordView.as_view(), name='auth-change-password'),
    path('', include(router.urls)),
]
