from django.core.management.base import BaseCommand

from interfacemanage.services.db_sync import sync_network_state_from_system


class Command(BaseCommand):
    help = '从系统采集 netplan / ip / wg，将网络配置镜像写入数据库'

    def handle(self, *args, **options):
        run = sync_network_state_from_system()
        if run.success:
            self.stdout.write(self.style.SUCCESS(f'同步成功: {run.stats}'))
        else:
            self.stdout.write(self.style.ERROR(f'同步失败: {run.error_message}'))
