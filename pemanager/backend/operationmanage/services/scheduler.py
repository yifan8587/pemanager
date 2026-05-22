"""进程内常驻调度器：周期性执行采样 / minute・hour・day rollup / retention。

设计：
- 单例（_SCHED 全局），在 Django 进程内开 1 个 daemon 线程，节拍 TICK_SEC 默认 5 秒。
- 每个 tick 内：
    a) 拉所有启用的 MonitorTarget（ping/mtr），到点的执行采样；
    b) 拉所有启用的 MonitorInterface，到点的执行流量增量采样；
    c) 当跨过整分钟时，触发 minute rollup（latency + traffic）；
    d) 当跨过整小时时，触发 hour rollup；
    e) 当跨过整天时，触发 day rollup + retention。
- 启动/停止：start() / stop() / status() / restart()。
- 错误隔离：单个 target/interface 失败不中断节拍；最近 N 条错误存内存供 UI 展示。

说明：开发用 runserver --noreload，生产用 gunicorn worker 数为 1 时最稳。
gunicorn 多 worker 会导致每个 worker 都跑一份调度器；如需严控可只在 master 或加分布式锁，本项目按
"单实例 PE 控制器" 假设不考虑多 worker 的并发。
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timezone as _tz
from typing import Any

from django.db import close_old_connections
from django.utils import timezone

from operationmanage.models import MonitorInterface, MonitorTarget
from operationmanage.services import retention, rollup, sampler

log = logging.getLogger(__name__)

TICK_SEC = 5
ERROR_RING_SIZE = 50
RETENTION_INTERVAL_SEC = 6 * 3600  # 每 6 小时跑一次清理（也会在跨天时跑一次）


class _Scheduler:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()
        # 运行状态
        self.started_at: datetime | None = None
        self.last_tick_at: datetime | None = None
        self.tick_count: int = 0
        self.due_target_count: int = 0
        self.due_iface_count: int = 0
        self.last_minute_rollup_at: datetime | None = None
        self.last_hour_rollup_at: datetime | None = None
        self.last_day_rollup_at: datetime | None = None
        self.last_retention_at: datetime | None = None
        self.last_retention_summary: dict[str, Any] | None = None
        self.errors = deque(maxlen=ERROR_RING_SIZE)
        # 触发节拍记账（避免一分钟跑两次 rollup）
        self._last_minute_bucket: datetime | None = None
        self._last_hour_bucket: datetime | None = None
        self._last_day_bucket: datetime | None = None
        # target / interface 触发节流
        self._last_run_target: dict[str, float] = {}
        self._last_run_iface: dict[str, float] = {}

    # ---------- 控制 ----------

    def is_running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive())

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return {'ok': True, 'already_running': True, **self._status_unlocked()}
            self._stop_evt.clear()
            self.started_at = timezone.now()
            self.tick_count = 0
            self._thread = threading.Thread(target=self._run, name='ops-scheduler', daemon=True)
            self._thread.start()
        return {'ok': True, 'started': True, **self.status()}

    def stop(self, *, timeout: float = 6.0) -> dict[str, Any]:
        with self._lock:
            th = self._thread
            self._stop_evt.set()
        if th and th.is_alive():
            th.join(timeout=timeout)
        with self._lock:
            self._thread = None
        return {'ok': True, 'stopped': True, **self.status()}

    def restart(self) -> dict[str, Any]:
        self.stop()
        return self.start()

    # ---------- 状态 ----------

    def _status_unlocked(self) -> dict[str, Any]:
        return {
            'running': bool(self._thread and self._thread.is_alive()),
            'tick_sec': TICK_SEC,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'last_tick_at': self.last_tick_at.isoformat() if self.last_tick_at else None,
            'tick_count': self.tick_count,
            'due_target_count': self.due_target_count,
            'due_iface_count': self.due_iface_count,
            'last_minute_rollup_at': self.last_minute_rollup_at.isoformat() if self.last_minute_rollup_at else None,
            'last_hour_rollup_at': self.last_hour_rollup_at.isoformat() if self.last_hour_rollup_at else None,
            'last_day_rollup_at': self.last_day_rollup_at.isoformat() if self.last_day_rollup_at else None,
            'last_retention_at': self.last_retention_at.isoformat() if self.last_retention_at else None,
            'last_retention_summary': self.last_retention_summary,
            'errors': list(self.errors)[-10:],
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_unlocked()

    # ---------- 主循环 ----------

    def _run(self) -> None:
        log.info('ops-scheduler started (tick=%ss)', TICK_SEC)
        try:
            while not self._stop_evt.is_set():
                tick_started = time.monotonic()
                try:
                    self._tick_once()
                except Exception as exc:  # noqa: BLE001
                    self._push_error(f'tick fatal: {exc}', traceback.format_exc())
                finally:
                    close_old_connections()
                elapsed = time.monotonic() - tick_started
                sleep_for = max(0.5, TICK_SEC - elapsed)
                if self._stop_evt.wait(sleep_for):
                    break
        finally:
            log.info('ops-scheduler stopped')

    def _tick_once(self) -> None:
        now = timezone.now()
        self.last_tick_at = now
        self.tick_count += 1

        self._sample_due_targets(now)
        self._sample_due_interfaces(now)
        self._maybe_run_rollups(now)
        self._maybe_run_retention(now)

    # ---------- 单元 ----------

    def _sample_due_targets(self, now: datetime) -> None:
        due: list[MonitorTarget] = []
        now_mono = time.monotonic()
        for t in MonitorTarget.objects.filter(enabled=True):
            key = str(t.id)
            interval = max(5, int(t.interval_sec or 60))
            last = self._last_run_target.get(key, 0.0)
            if now_mono - last >= interval:
                due.append(t)
                self._last_run_target[key] = now_mono
        self.due_target_count = len(due)
        for t in due:
            try:
                sampler.sample_one_target(t)
            except Exception as exc:  # noqa: BLE001
                self._push_error(f'target {t.name} sample failed: {exc}')

    def _sample_due_interfaces(self, now: datetime) -> None:
        due: list[MonitorInterface] = []
        now_mono = time.monotonic()
        for mi in MonitorInterface.objects.filter(enabled=True):
            key = str(mi.id)
            interval = max(5, int(mi.interval_sec or 15))
            last = self._last_run_iface.get(key, 0.0)
            if now_mono - last >= interval:
                due.append(mi)
                self._last_run_iface[key] = now_mono
        self.due_iface_count = len(due)
        for mi in due:
            try:
                sampler.sample_one_monitor_interface(mi)
            except Exception as exc:  # noqa: BLE001
                self._push_error(f'iface {mi.interface_name} sample failed: {exc}')

    def _maybe_run_rollups(self, now: datetime) -> None:
        cur_minute = now.replace(second=0, microsecond=0)
        if self._last_minute_bucket is None or cur_minute > self._last_minute_bucket:
            # 翻"刚结束的"那一分钟（cur_minute 是当前未结束的分钟起点，rollup 已结束的）
            try:
                rollup.rollup_just_finished_minute(now)
                self.last_minute_rollup_at = now
            except Exception as exc:  # noqa: BLE001
                self._push_error(f'minute rollup failed: {exc}')
            self._last_minute_bucket = cur_minute

        cur_hour = now.replace(minute=0, second=0, microsecond=0)
        if self._last_hour_bucket is None or cur_hour > self._last_hour_bucket:
            try:
                rollup.rollup_just_finished_hour(now)
                self.last_hour_rollup_at = now
            except Exception as exc:  # noqa: BLE001
                self._push_error(f'hour rollup failed: {exc}')
            self._last_hour_bucket = cur_hour

        cur_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self._last_day_bucket is None or cur_day > self._last_day_bucket:
            try:
                rollup.rollup_just_finished_day(now)
                self.last_day_rollup_at = now
            except Exception as exc:  # noqa: BLE001
                self._push_error(f'day rollup failed: {exc}')
            self._last_day_bucket = cur_day
            # 跨天 → 触发一次清理
            self._do_retention(now)

    def _maybe_run_retention(self, now: datetime) -> None:
        if (
            self.last_retention_at is None
            or (now - self.last_retention_at).total_seconds() > RETENTION_INTERVAL_SEC
        ):
            self._do_retention(now)

    def _do_retention(self, now: datetime) -> None:
        try:
            summary = retention.purge_now()
            self.last_retention_at = now
            self.last_retention_summary = summary
        except Exception as exc:  # noqa: BLE001
            self._push_error(f'retention failed: {exc}')

    # ---------- 错误 ----------

    def _push_error(self, msg: str, tb: str = '') -> None:
        self.errors.append({'at': timezone.now().isoformat(), 'msg': msg, 'tb': tb[:1024]})
        log.warning('ops-scheduler: %s', msg)


# 单例
_SCHED: _Scheduler | None = None
_SCHED_LOCK = threading.Lock()


def get_scheduler() -> _Scheduler:
    global _SCHED
    if _SCHED is None:
        with _SCHED_LOCK:
            if _SCHED is None:
                _SCHED = _Scheduler()
    return _SCHED


def start() -> dict[str, Any]:
    return get_scheduler().start()


def stop() -> dict[str, Any]:
    return get_scheduler().stop()


def status() -> dict[str, Any]:
    return get_scheduler().status()


def restart() -> dict[str, Any]:
    return get_scheduler().restart()
