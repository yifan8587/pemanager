from django.apps import AppConfig


class QosmanageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'qosmanage'

    def ready(self):
        # 注册 QoS 策略 ↔ 资源管理 BandwidthAllocation 联动信号
        from qosmanage import signals  # noqa: F401
