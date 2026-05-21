"""raw 样本 → minute/hour/day 汇总表。

策略：
- minute：从 raw 表（LatencySample / InterfaceTrafficSample）聚合写入；
- hour / day：从 minute 汇总向上聚合写入；
- 全部 upsert，重复触发幂等。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as _tz
from typing import Iterable

from django.db.models import Avg, Count, Max, Min, Q, Sum

from operationmanage.models import (
    InterfaceTrafficRollup,
    InterfaceTrafficSample,
    LatencyRollup,
    LatencySample,
    MonitorTarget,
)


# ---------- 桶起点工具 ----------

def floor_to_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def floor_to_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


_FLOOR = {
    'minute': floor_to_minute,
    'hour': floor_to_hour,
    'day': floor_to_day,
}

_STEP = {
    'minute': timedelta(minutes=1),
    'hour': timedelta(hours=1),
    'day': timedelta(days=1),
}


# ---------- 延迟：raw → minute ----------

def rollup_latency_minute_for_window(start_utc: datetime, end_utc: datetime) -> int:
    """对 [start, end) 内的全部 LatencySample，按 (target, minute) 聚合写入 minute rollup。"""
    qs = LatencySample.objects.filter(ts__gte=start_utc, ts__lt=end_utc).select_related('target')
    grouped: dict[tuple[str, datetime], list[LatencySample]] = {}
    for s in qs:
        key = (str(s.target_id), floor_to_minute(s.ts))
        grouped.setdefault(key, []).append(s)
    written = 0
    for (target_id, bucket_ts), items in grouped.items():
        rtt_avg_vals = [i.rtt_avg_ms for i in items if i.rtt_avg_ms is not None]
        rtt_min_vals = [i.rtt_min_ms for i in items if i.rtt_min_ms is not None]
        rtt_max_vals = [i.rtt_max_ms for i in items if i.rtt_max_ms is not None]
        jitter_vals = [i.jitter_ms for i in items if i.jitter_ms is not None]
        loss_vals = [i.loss_pct for i in items if i.loss_pct is not None]
        sent = sum(int(i.packets_sent or 0) for i in items)
        recv = sum(int(i.packets_recv or 0) for i in items)
        ok = sum(1 for i in items if i.ok)
        LatencyRollup.objects.update_or_create(
            target_id=target_id,
            bucket_kind=LatencyRollup.Bucket.MINUTE,
            bucket_ts=bucket_ts,
            defaults={
                'rtt_min_ms': min(rtt_min_vals) if rtt_min_vals else None,
                'rtt_max_ms': max(rtt_max_vals) if rtt_max_vals else None,
                'rtt_avg_ms': sum(rtt_avg_vals) / len(rtt_avg_vals) if rtt_avg_vals else None,
                'jitter_ms': sum(jitter_vals) / len(jitter_vals) if jitter_vals else None,
                'loss_pct': sum(loss_vals) / len(loss_vals) if loss_vals else None,
                'samples': len(items),
                'ok_samples': ok,
                'packets_sent': sent,
                'packets_recv': recv,
            },
        )
        written += 1
    return written


# ---------- 流量：raw → minute ----------

def rollup_traffic_minute_for_window(start_utc: datetime, end_utc: datetime) -> int:
    qs = InterfaceTrafficSample.objects.filter(ts__gte=start_utc, ts__lt=end_utc).order_by('ts')
    by_key: dict[tuple[str, datetime], list[InterfaceTrafficSample]] = {}
    for s in qs:
        key = (s.interface_name, floor_to_minute(s.ts))
        by_key.setdefault(key, []).append(s)
    written = 0
    for (iface, bucket_ts), items in by_key.items():
        rx_bps = [i.rx_bps for i in items if i.rx_bps is not None]
        tx_bps = [i.tx_bps for i in items if i.tx_bps is not None]
        items_sorted = sorted(items, key=lambda x: x.ts)
        first, last = items_sorted[0], items_sorted[-1]
        rx_delta = max(0, int(last.rx_bytes_total - first.rx_bytes_total))
        tx_delta = max(0, int(last.tx_bytes_total - first.tx_bytes_total))
        InterfaceTrafficRollup.objects.update_or_create(
            interface_name=iface,
            bucket_kind=InterfaceTrafficRollup.Bucket.MINUTE,
            bucket_ts=bucket_ts,
            defaults={
                'rx_bps_avg': sum(rx_bps) / len(rx_bps) if rx_bps else None,
                'rx_bps_max': max(rx_bps) if rx_bps else None,
                'tx_bps_avg': sum(tx_bps) / len(tx_bps) if tx_bps else None,
                'tx_bps_max': max(tx_bps) if tx_bps else None,
                'rx_bytes_delta': rx_delta,
                'tx_bytes_delta': tx_delta,
                'samples': len(items),
            },
        )
        written += 1
    return written


# ---------- minute → hour / day（两类指标通用） ----------

def _step(kind: str) -> timedelta:
    return _STEP[kind]


def _floor(kind: str, dt: datetime) -> datetime:
    return _FLOOR[kind](dt)


def rollup_latency_higher(*, target_kind: str, start_utc: datetime, end_utc: datetime) -> int:
    """target_kind = 'hour' | 'day'，源是 MINUTE rollup。"""
    assert target_kind in ('hour', 'day')
    src_kind = 'minute' if target_kind == 'hour' else 'hour'
    qs = LatencyRollup.objects.filter(
        bucket_kind=src_kind,
        bucket_ts__gte=_floor(target_kind, start_utc),
        bucket_ts__lt=_floor(target_kind, end_utc) + _step(target_kind),
    ).select_related('target')

    grouped: dict[tuple[str, datetime], list[LatencyRollup]] = {}
    for row in qs:
        key = (str(row.target_id), _floor(target_kind, row.bucket_ts))
        grouped.setdefault(key, []).append(row)

    written = 0
    for (target_id, bucket_ts), items in grouped.items():
        avg_vals = [i.rtt_avg_ms for i in items if i.rtt_avg_ms is not None]
        min_vals = [i.rtt_min_ms for i in items if i.rtt_min_ms is not None]
        max_vals = [i.rtt_max_ms for i in items if i.rtt_max_ms is not None]
        jit_vals = [i.jitter_ms for i in items if i.jitter_ms is not None]
        loss_vals = [i.loss_pct for i in items if i.loss_pct is not None]
        LatencyRollup.objects.update_or_create(
            target_id=target_id,
            bucket_kind=target_kind,
            bucket_ts=bucket_ts,
            defaults={
                'rtt_min_ms': min(min_vals) if min_vals else None,
                'rtt_max_ms': max(max_vals) if max_vals else None,
                'rtt_avg_ms': sum(avg_vals) / len(avg_vals) if avg_vals else None,
                'jitter_ms': sum(jit_vals) / len(jit_vals) if jit_vals else None,
                'loss_pct': sum(loss_vals) / len(loss_vals) if loss_vals else None,
                'samples': sum(int(i.samples or 0) for i in items),
                'ok_samples': sum(int(i.ok_samples or 0) for i in items),
                'packets_sent': sum(int(i.packets_sent or 0) for i in items),
                'packets_recv': sum(int(i.packets_recv or 0) for i in items),
            },
        )
        written += 1
    return written


def rollup_traffic_higher(*, target_kind: str, start_utc: datetime, end_utc: datetime) -> int:
    assert target_kind in ('hour', 'day')
    src_kind = 'minute' if target_kind == 'hour' else 'hour'
    qs = InterfaceTrafficRollup.objects.filter(
        bucket_kind=src_kind,
        bucket_ts__gte=_floor(target_kind, start_utc),
        bucket_ts__lt=_floor(target_kind, end_utc) + _step(target_kind),
    )
    grouped: dict[tuple[str, datetime], list[InterfaceTrafficRollup]] = {}
    for row in qs:
        key = (row.interface_name, _floor(target_kind, row.bucket_ts))
        grouped.setdefault(key, []).append(row)
    written = 0
    for (iface, bucket_ts), items in grouped.items():
        rx_avg_vals = [i.rx_bps_avg for i in items if i.rx_bps_avg is not None]
        tx_avg_vals = [i.tx_bps_avg for i in items if i.tx_bps_avg is not None]
        rx_max_vals = [i.rx_bps_max for i in items if i.rx_bps_max is not None]
        tx_max_vals = [i.tx_bps_max for i in items if i.tx_bps_max is not None]
        InterfaceTrafficRollup.objects.update_or_create(
            interface_name=iface,
            bucket_kind=target_kind,
            bucket_ts=bucket_ts,
            defaults={
                'rx_bps_avg': sum(rx_avg_vals) / len(rx_avg_vals) if rx_avg_vals else None,
                'tx_bps_avg': sum(tx_avg_vals) / len(tx_avg_vals) if tx_avg_vals else None,
                'rx_bps_max': max(rx_max_vals) if rx_max_vals else None,
                'tx_bps_max': max(tx_max_vals) if tx_max_vals else None,
                'rx_bytes_delta': sum(int(i.rx_bytes_delta or 0) for i in items),
                'tx_bytes_delta': sum(int(i.tx_bytes_delta or 0) for i in items),
                'samples': sum(int(i.samples or 0) for i in items),
            },
        )
        written += 1
    return written


# ---------- 高层入口 ----------

def rollup_just_finished_minute(now_utc: datetime) -> dict[str, int]:
    """聚合刚结束的那一分钟（避免数据还在写入的"当前"分钟）。"""
    minute_end = floor_to_minute(now_utc)
    minute_start = minute_end - _STEP['minute']
    lat = rollup_latency_minute_for_window(minute_start, minute_end)
    tr = rollup_traffic_minute_for_window(minute_start, minute_end)
    return {'latency': lat, 'traffic': tr, 'minute_start': minute_start, 'minute_end': minute_end}


def rollup_just_finished_hour(now_utc: datetime) -> dict[str, int]:
    hour_end = floor_to_hour(now_utc)
    hour_start = hour_end - _STEP['hour']
    lat = rollup_latency_higher(target_kind='hour', start_utc=hour_start, end_utc=hour_end)
    tr = rollup_traffic_higher(target_kind='hour', start_utc=hour_start, end_utc=hour_end)
    return {'latency': lat, 'traffic': tr, 'hour_start': hour_start, 'hour_end': hour_end}


def rollup_just_finished_day(now_utc: datetime) -> dict[str, int]:
    day_end = floor_to_day(now_utc)
    day_start = day_end - _STEP['day']
    lat = rollup_latency_higher(target_kind='day', start_utc=day_start, end_utc=day_end)
    tr = rollup_traffic_higher(target_kind='day', start_utc=day_start, end_utc=day_end)
    return {'latency': lat, 'traffic': tr, 'day_start': day_start, 'day_end': day_end}


def rollup_backfill(*, hours: int = 24) -> dict[str, int]:
    """回填：扫过去 `hours` 小时内的 raw → minute → hour → day。"""
    from django.utils import timezone

    now = timezone.now()
    start = now - timedelta(hours=max(1, hours))
    lat_min = rollup_latency_minute_for_window(start, now)
    tr_min = rollup_traffic_minute_for_window(start, now)
    lat_hr = rollup_latency_higher(target_kind='hour', start_utc=start, end_utc=now)
    tr_hr = rollup_traffic_higher(target_kind='hour', start_utc=start, end_utc=now)
    lat_day = rollup_latency_higher(target_kind='day', start_utc=start, end_utc=now)
    tr_day = rollup_traffic_higher(target_kind='day', start_utc=start, end_utc=now)
    return {
        'latency_minute': lat_min,
        'traffic_minute': tr_min,
        'latency_hour': lat_hr,
        'traffic_hour': tr_hr,
        'latency_day': lat_day,
        'traffic_day': tr_day,
    }
