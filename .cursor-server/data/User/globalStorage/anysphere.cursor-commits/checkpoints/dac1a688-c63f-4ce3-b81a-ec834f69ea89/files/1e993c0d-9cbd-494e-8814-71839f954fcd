"""
URL configuration for config project.
"""
from django.contrib import admin
from django.urls import include, path

from config import views as config_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/csrf/', config_views.csrf_bootstrap, name='api-csrf-bootstrap'),
    path('api/interfacemanage/', include('interfacemanage.urls')),
    path('api/resourcemanage/', include('resourcemanage.urls')),
    path('api/routemanage/', include('routemanage.urls')),
    path('api/qosmanage/', include('qosmanage.urls')),
    path('api/firewallmanage/', include('firewallmanage.urls')),
    path('api/operationmanage/', include('operationmanage.urls')),
    path('api/logmanage/', include('logmanage.urls')),
]
