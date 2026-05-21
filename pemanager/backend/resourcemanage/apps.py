from django.apps import AppConfig


class ResourcemanageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'resourcemanage'
    verbose_name = '资源管理'

    def ready(self):
        import resourcemanage.signals  # noqa: F401
