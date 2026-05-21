from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction

from resourcemanage.models import (
    BandwidthAllocation,
    BandwidthPool,
    IPAddressEntry,
    ResourceCustomer,
    ResourceAllocationLog,
)
from resourcemanage.services import audit


def apply_inbound_payload(
    payload: dict[str, Any],
    *,
    source_app: str,
    actor: str = 'sync',
) -> dict[str, Any]:
    """
    其他应用将配置变更同步回资源侧。
    期望结构示例::
        {
          "ip_updates": [{"address": "...", "state": "allocated", "customer_code": "...", "interface_code": "..."}],
          "bandwidth_updates": [{"pool_name": "...", "interface_code": "...", "allocated_mbps": 100, "customer_code": "..."}],
          "bandwidth_removals": [{"pool_name": "...", "interface_code": "..."}],
        }
    """
    correlation_id = uuid.uuid4()
    results: dict[str, Any] = {'ip': [], 'bandwidth': [], 'correlation_id': str(correlation_id)}

    with transaction.atomic():
        for item in payload.get('ip_updates') or []:
            results['ip'].append(
                _apply_single_ip_update(item, source_app=source_app, correlation_id=correlation_id)
            )

        for item in payload.get('bandwidth_updates') or []:
            results['bandwidth'].append(
                _apply_single_bandwidth_update(
                    item, source_app=source_app, correlation_id=correlation_id, actor=actor
                )
            )

        for item in payload.get('bandwidth_removals') or []:
            results['bandwidth'].append(
                _apply_bandwidth_removal(
                    item, source_app=source_app, correlation_id=correlation_id, actor=actor
                )
            )

        audit.log_action(
            ResourceAllocationLog.Action.SYNC_INBOUND,
            f'自 {source_app} 同步回写资源',
            detail={'payload': payload, 'results': results},
            actor=actor,
            correlation_id=correlation_id,
        )

    return results


def _get_customer(code: str | None) -> ResourceCustomer | None:
    if not code:
        return None
    return ResourceCustomer.objects.filter(code=code, is_active=True).first()


def _apply_single_ip_update(
    item: dict[str, Any],
    *,
    source_app: str,
    correlation_id: uuid.UUID,
) -> dict[str, Any]:
    address = item.get('address')
    if not address:
        return {'ok': False, 'error': '缺少 address'}

    entry, _created = IPAddressEntry.objects.get_or_create(
        address=address,
        defaults={
            'state': IPAddressEntry.State.AVAILABLE,
            'subnet_label': item.get('subnet_label', ''),
        },
    )
    before = {
        'state': entry.state,
        'customer_id': entry.customer_id,
        'interface_code': entry.interface_code,
    }

    state = item.get('state')
    if state:
        entry.state = state
    customer = _get_customer(item.get('customer_code'))
    if 'customer_code' in item:
        entry.customer = customer
    if 'interface_code' in item:
        entry.interface_code = item.get('interface_code') or ''
    if 'subnet_label' in item:
        entry.subnet_label = item.get('subnet_label') or ''
    if 'extra' in item and isinstance(item['extra'], dict):
        merged = {**(entry.extra or {}), **item['extra']}
        entry.extra = merged

    entry.full_clean()
    entry._skip_outbound = True  # type: ignore[attr-defined]
    entry.save()

    audit.log_action(
        ResourceAllocationLog.Action.IP_UPDATE,
        f'[{source_app}] IP 同步: {address}',
        detail={'before': before, 'after': item, 'entry_id': entry.pk},
        actor=source_app,
        correlation_id=correlation_id,
    )
    return {'ok': True, 'id': entry.pk, 'address': str(entry.address)}


def _apply_single_bandwidth_update(
    item: dict[str, Any],
    *,
    source_app: str,
    correlation_id: uuid.UUID,
    actor: str,
) -> dict[str, Any]:
    pool_name = item.get('pool_name')
    iface = item.get('interface_code')
    mbps = item.get('allocated_mbps')
    if not pool_name or not iface or mbps is None:
        return {'ok': False, 'error': 'pool_name、interface_code、allocated_mbps 为必填'}

    pool = BandwidthPool.objects.filter(name=pool_name).first()
    if not pool:
        return {'ok': False, 'error': f'带宽池不存在: {pool_name}'}

    customer = _get_customer(item.get('customer_code'))
    alloc, _created = BandwidthAllocation.objects.get_or_create(
        pool=pool,
        interface_code=iface,
        defaults={
            'allocated_mbps': int(mbps),
            'customer': customer,
            'remark': item.get('remark', ''),
        },
    )
    if not _created:
        alloc.allocated_mbps = int(mbps)
        alloc.customer = customer
        if 'remark' in item:
            alloc.remark = item.get('remark') or ''

    alloc.full_clean()
    alloc._skip_outbound = True  # type: ignore[attr-defined]
    alloc.save()

    audit.log_action(
        ResourceAllocationLog.Action.BW_UPDATE,
        f'[{source_app}] 带宽同步: {pool_name}/{iface}',
        detail={'item': item, 'allocation_id': alloc.pk},
        actor=actor,
        correlation_id=correlation_id,
    )
    return {'ok': True, 'id': alloc.pk}


def _apply_bandwidth_removal(
    item: dict[str, Any],
    *,
    source_app: str,
    correlation_id: uuid.UUID,
    actor: str,
) -> dict[str, Any]:
    pool_name = item.get('pool_name')
    iface = item.get('interface_code')
    if not pool_name or not iface:
        return {'ok': False, 'error': 'pool_name、interface_code 为必填'}
    pool = BandwidthPool.objects.filter(name=pool_name).first()
    if not pool:
        return {'ok': False, 'error': f'带宽池不存在: {pool_name}'}
    qs = BandwidthAllocation.objects.filter(pool=pool, interface_code=iface)
    deleted = 0
    for alloc in list(qs):
        alloc._skip_outbound = True  # noqa: SLF001
        alloc.delete()
        deleted += 1
    audit.log_action(
        ResourceAllocationLog.Action.BW_DELETE,
        f'[{source_app}] 带宽记录同步删除: {pool_name}/{iface}',
        detail={'item': item, 'deleted': deleted},
        actor=actor,
        correlation_id=correlation_id,
    )
    return {'ok': True, 'deleted': deleted}
