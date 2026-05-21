from django.urls import include, path
from rest_framework.routers import DefaultRouter

from logmanage import views

router = DefaultRouter()
router.register('app-logs', views.AppOperationLogViewSet, basename='app-log')

urlpatterns = [
    path('health/', views.health, name='health'),
    path('journal/query/', views.JournalQueryView.as_view(), name='journal-query'),
    path('journal/units/', views.JournalUnitsView.as_view(), name='journal-units'),
    path('', include(router.urls)),
]
