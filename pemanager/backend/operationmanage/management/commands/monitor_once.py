"""一次性采样：对所有启用的 MonitorTarget 调用 ping/mtr，对指定接口做流量增量。"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from operationmanage.services import sampler


class Command(BaseCommand):
    help = '执行一次监控采样（ping/mtr + 接口流量增量）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interfaces',
            default='',
            help='逗号分隔的接口名列表，将采样这些接口的 /proc/net/dev 增量；默认空',
        )

    def handle(self, *_args, **options):
        ifaces = [s.strip() for s in (options.get('interfaces') or '').split(',') if s.strip()]
        out = {'latency': sampler.sample_all_targets()}
        if ifaces:
            out['traffic'] = sampler.sample_interfaces(ifaces)
        self.stdout.write(json.dumps(out, ensure_ascii=False, indent=2, default=str))
