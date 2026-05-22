from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _on_post_migrate(sender, **kwargs):
    if getattr(sender, 'name', '') != 'accountmanage':
        return
    try:
        from accountmanage.services.bootstrap import ensure_default_admin

        ensure_default_admin()
    except Exception:  # noqa: BLE001
        pass


class AccountmanageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accountmanage'
    verbose_name = '账号与权限'

    def ready(self):
        # 通过 post_migrate 信号自举默认 admin，避免 ready() 阶段查询数据库的警告。
        post_migrate.connect(_on_post_migrate, sender=self)
