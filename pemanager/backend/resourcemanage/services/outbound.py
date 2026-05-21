from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from resourcemanage.integrations.dispatchers import notify_all
from resourcemanage.models import BandwidthAllocation, IPAddressEntry
from resourcemanage.services import audit

logger = logging.getLogger(__name__)


def _snapshot_ip(entry: IPAddressEntry | None) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        'id': entry.pk,
        'address': str(entry.address),
        'state': entry.state,
        'subnet_label': entry.subnet_label,
        'customer_id': entry.customer_id,
        'customer_code': entry.customer.code if entry.customer_id else None,
        'interface_code': entry.interface_code,
        'extra': entry.extra,
    }


def _snapshot_bw(row: BandwidthAllocation | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        'id': row.pk,
        'pool_id': row.pool_id,
        'pool_name': row.pool.name,
        'customer_id': row.customer_id,
        'customer_code': row.customer.code if row.customer_id else None,
        'interface_code': row.interface_code,
        'allocated_mbps': row.allocated_mbps,
    }


def schedule_outbound_ip(
    *,
    ip_pk: int,
    reason: str,
    actor: str,
    correlation_id,
    log_action_name: str,
) -> None:
    """在事务提交后将 IP 相关变更推送给各应用并记同步日志。"""

    def _run():
        entry = IPAddressEntry.objects.select_related('customer').filter(pk=ip_pk).first()
        event = {
            'kind': 'ip',
            'reason': reason,
            'snapshot': _snapshot_ip(entry),
        }
        try:
            notify_all(event)
            audit.log_action(
                log_action_name,
                f'IP 变更已触发下发: {reason}',
                detail={'event': event},
                actor=actor,
                correlation_id=correlation_id,
            )
        except Exception:
            logger.exception('资源外向同步失败(ip): pk=%s', ip_pk)

    transaction.on_commit(_run)


def schedule_outbound_bandwidth(
    *,
    alloc_pk: int | None,
    reason: str,
    actor: str,
    correlation_id,
    log_action_name: str,
    deleted_snapshot: dict[str, Any] | None = None,
) -> None:
    """带宽分配创建/更新/删除后的下发调度。"""

    def _run():
        row = None
        if alloc_pk is not None:
            row = (
                BandwidthAllocation.objects.select_related('pool', 'customer')
                .filter(pk=alloc_pk)
                .first()
            )
        snapshot = _snapshot_bw(row) if row is not None else deleted_snapshot
        event = {
            'kind': 'bandwidth',
            'reason': reason,
            'snapshot': snapshot,
        }
        try:
            notify_all(event)
            audit.log_action(
                log_action_name,
                f'带宽变更已触发下发: {reason}',
                detail={'event': event},
                actor=actor,
                correlation_id=correlation_id,
            )
        except Exception:
            logger.exception('资源外向同步失败(bandwidth): pk=%s', alloc_pk)

    transaction.on_commit(_run)
