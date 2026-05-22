"""数据保留策略：动态覆盖一月前的明细。

策略：
- raw 样本（LatencySample / InterfaceTrafficSample）：保留 30 天。
- minute rollup（LatencyRollup / InterfaceTrafficRollup with bucket_kind='minute'）：保留 30 天。
- hour / day rollup：默认保留 365 天（足够给前端"按小时/按天/按月"查看一个月前的汇总，因为月维度直接用 day rollup 聚合得到）。

入口：
- `purge_now()`：被 scheduler 调用；返回各表删除行数。
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from operationmanage.models import (
    DiagnosticsJob,
    InterfaceTrafficRollup,
    InterfaceTrafficSample,
    LatencyRollup,
    LatencySample,
)

RAW_RETENTION_DAYS = 30          # raw 与 minute 都按 30 天保留
HOUR_RETENTION_DAYS = 365
DAY_RETENTION_DAYS = 365 * 3     # day 桶保留 3 年
JOB_RETENTION_DAYS = 14          # DiagnosticsJob（异步诊断任务）保留 14 天


def purge_now() -> dict[str, Any]:
    now = timezone.now()
    cutoffs = {
        'raw': now - timedelta(days=RAW_RETENTION_DAYS),
        'minute': now - timedelta(days=RAW_RETENTION_DAYS),
        'hour': now - timedelta(days=HOUR_RETENTION_DAYS),
        'day': now - timedelta(days=DAY_RETENTION_DAYS),
        'job': now - timedelta(days=JOB_RETENTION_DAYS),
    }
    out: dict[str, int] = {}
    out['latency_raw'] = LatencySample.objects.filter(ts__lt=cutoffs['raw']).delete()[0]
    out['traffic_raw'] = InterfaceTrafficSample.objects.filter(ts__lt=cutoffs['raw']).delete()[0]
    out['latency_minute'] = LatencyRollup.objects.filter(
        bucket_kind='minute', bucket_ts__lt=cutoffs['minute']
    ).delete()[0]
    out['traffic_minute'] = InterfaceTrafficRollup.objects.filter(
        bucket_kind='minute', bucket_ts__lt=cutoffs['minute']
    ).delete()[0]
    out['latency_hour'] = LatencyRollup.objects.filter(
        bucket_kind='hour', bucket_ts__lt=cutoffs['hour']
    ).delete()[0]
    out['traffic_hour'] = InterfaceTrafficRollup.objects.filter(
        bucket_kind='hour', bucket_ts__lt=cutoffs['hour']
    ).delete()[0]
    out['latency_day'] = LatencyRollup.objects.filter(
        bucket_kind='day', bucket_ts__lt=cutoffs['day']
    ).delete()[0]
    out['traffic_day'] = InterfaceTrafficRollup.objects.filter(
        bucket_kind='day', bucket_ts__lt=cutoffs['day']
    ).delete()[0]
    out['diagnostics_jobs'] = DiagnosticsJob.objects.filter(created_at__lt=cutoffs['job']).delete()[0]
    out['at'] = now.isoformat()
    return out
