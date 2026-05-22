import logging
import os

from django.apps import AppConfig

log = logging.getLogger(__name__)


def _is_runserver_main() -> bool:
    """避免 runserver 的 autoreload 子进程重复启动调度器。"""
    return os.environ.get('RUN_MAIN', 'false') == 'true' or '--noreload' in (os.environ.get('DJANGO_RUNSERVER_FLAGS') or '')


class OperationmanageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'operationmanage'

    def ready(self):
        from django.conf import settings

        flag = str(getattr(settings, 'OPERATION_SCHEDULER_AUTOSTART', '0')).lower() in ('1', 'true', 'yes', 'on')
        if not flag:
            return
        try:
            from operationmanage.services import scheduler as _sched

            _sched.start()
            log.info('operationmanage scheduler auto-started')
        except Exception as exc:  # noqa: BLE001
            log.warning('operationmanage scheduler autostart failed: %s', exc)
