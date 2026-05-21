"""把 LatencySample / InterfaceTrafficSample 按 hour / day / month 聚合。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from django.db.models import Avg, Count, Max, Min, QuerySet, Sum
from django.db.models.functions import (
    TruncDay,
    TruncHour,
    TruncMonth,
)


_BUCKET_MAP = {
    'hour': TruncHour,
    'day': TruncDay,
    'month': TruncMonth,
}


def parse_bucket(name: str | None) -> str:
    n = (name or 'hour').lower()
    if n not in _BUCKET_MAP:
        return 'hour'
    return n


def _annotate_bucket(qs: QuerySet, bucket: str):
    trunc = _BUCKET_MAP[bucket]
    return qs.annotate(bucket=trunc('ts'))


def latency_series(qs: QuerySet, *, bucket: str = 'hour') -> list[dict[str, Any]]:
    bucket = parse_bucket(bucket)
    agg = (
        _annotate_bucket(qs, bucket)
        .values('bucket')
        .annotate(
            rtt_avg_ms=Avg('rtt_avg_ms'),
            rtt_min_ms=Min('rtt_min_ms'),
            rtt_max_ms=Max('rtt_max_ms'),
            jitter_ms=Avg('jitter_ms'),
            loss_pct=Avg('loss_pct'),
            samples=Count('id'),
            packets_sent=Sum('packets_sent'),
            packets_recv=Sum('packets_recv'),
        )
        .order_by('bucket')
    )
    return [_serialize_bucket(row) for row in agg]


def traffic_series(qs: QuerySet, *, bucket: str = 'hour') -> list[dict[str, Any]]:
    bucket = parse_bucket(bucket)
    agg = (
        _annotate_bucket(qs, bucket)
        .values('bucket')
        .annotate(
            rx_bps_avg=Avg('rx_bps'),
            tx_bps_avg=Avg('tx_bps'),
            rx_bps_max=Max('rx_bps'),
            tx_bps_max=Max('tx_bps'),
            samples=Count('id'),
        )
        .order_by('bucket')
    )
    return [_serialize_bucket(row) for row in agg]


def _serialize_bucket(row: dict[str, Any]) -> dict[str, Any]:
    bucket: datetime | None = row.get('bucket')
    if bucket is not None and bucket.tzinfo is None:
        bucket = bucket.replace(tzinfo=timezone.utc)
    out = dict(row)
    out['bucket'] = bucket.isoformat() if bucket else None
    return out
