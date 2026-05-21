"""阻塞循环：以最小启用间隔为节拍，周期性采样。"""
from __future__ import annotations

import signal
import sys
import time

from django.core.management.base import BaseCommand

from operationmanage.models import MonitorTarget
from operationmanage.services import sampler


class Command(BaseCommand):
    help = '阻塞循环：按 MonitorTarget.interval_sec 节拍执行采样；可用 Ctrl-C 终止'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interfaces',
            default='',
            help='逗号分隔的接口名列表，每个节拍都做一次流量增量；默认空',
        )
        parser.add_argument(
            '--tick',
            type=int,
            default=30,
            help='循环最小节拍秒数（默认 30s）；实际触发以 interval_sec 倍数为准',
        )

    def handle(self, *_args, **options):
        ifaces = [s.strip() for s in (options.get('interfaces') or '').split(',') if s.strip()]
        tick = max(5, int(options.get('tick') or 30))
        stop = {'v': False}

        def _stop(_sig, _frm):
            stop['v'] = True

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        last_run: dict[str, float] = {}
        self.stdout.write(f'monitor_loop start (tick={tick}s, interfaces={ifaces})')
        while not stop['v']:
            now = time.time()
            due = []
            for t in MonitorTarget.objects.filter(enabled=True):
                key = str(t.id)
                last = last_run.get(key, 0)
                if now - last >= max(5, int(t.interval_sec)):
                    due.append(t)
                    last_run[key] = now
            for t in due:
                try:
                    sampler.sample_one_target(t)
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f'sample failed for {t.name}: {exc}')
            if ifaces:
                try:
                    sampler.sample_interfaces(ifaces)
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f'traffic sample failed: {exc}')
            for _ in range(tick):
                if stop['v']:
                    break
                time.sleep(1)
        self.stdout.write('monitor_loop stopped')
        sys.exit(0)
