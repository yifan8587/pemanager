from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from resourcemanage.models import (
    BandwidthAllocation,
    BandwidthPool,
    IPAddressEntry,
    ResourceCustomer,
    ResourceAllocationLog,
)
from resourcemanage.services import audit, outbound


def _cid() -> uuid.UUID:
    return uuid.uuid4()


@transaction.atomic
def reserve_ip(
    *,
    address: str,
    customer: ResourceCustomer | None = None,
    interface_code: str = '',
    subnet_label: str = '',
    actor: str = 'api',
) -> IPAddressEntry:
    correlation_id = _cid()
    entry = IPAddressEntry.objects.select_for_update().filter(address=address).first()
    if not entry:
        entry = IPAddressEntry(
            address=address,
            state=IPAddressEntry.State.RESERVED,
            subnet_label=subnet_label,
            customer=customer,
            interface_code=interface_code or '',
        )
    else:
        if entry.state != IPAddressEntry.State.AVAILABLE:
            raise ValidationError(f'IP {address} 非可用状态，无法预留')
        entry.state = IPAddressEntry.State.RESERVED
        entry.customer = customer
        entry.interface_code = interface_code or ''
        if subnet_label:
            entry.subnet_label = subnet_label

    entry.full_clean()
    entry._skip_outbound = True  # noqa: SLF001
    entry.save()

    audit.log_action(
        ResourceAllocationLog.Action.IP_RESERVE,
        f'预留 IP {address}',
        detail={'entry_id': entry.pk},
        actor=actor,
        correlation_id=correlation_id,
    )
    outbound.schedule_outbound_ip(
        ip_pk=entry.pk,
        reason='ip_reserve',
        actor=actor,
        correlation_id=correlation_id,
        log_action_name=ResourceAllocationLog.Action.SYNC_OUTBOUND,
    )
    return entry


@transaction.atomic
def allocate_ip(
    *,
    address: str,
    customer: ResourceCustomer,
    interface_code: str = '',
    subnet_label: str = '',
    allow_from_reserved: bool = True,
    actor: str = 'api',
) -> IPAddressEntry:
    correlation_id = _cid()
    entry = IPAddressEntry.objects.select_for_update().filter(address=address).first()
    if not entry:
        entry = IPAddressEntry(
            address=address,
            state=IPAddressEntry.State.ALLOCATED,
            subnet_label=subnet_label,
            customer=customer,
            interface_code=interface_code or '',
        )
        entry.full_clean()
        entry._skip_outbound = True  # noqa: SLF001
        entry.save()
    else:
        valid_states = {IPAddressEntry.State.AVAILABLE}
        if allow_from_reserved:
            valid_states.add(IPAddressEntry.State.RESERVED)
        if entry.state not in valid_states:
            raise ValidationError(f'IP {address} 当前状态不允许分配')
        entry.state = IPAddressEntry.State.ALLOCATED
        entry.customer = customer
        entry.interface_code = interface_code or ''
        if subnet_label:
            entry.subnet_label = subnet_label
        entry.full_clean()
        entry._skip_outbound = True  # noqa: SLF001
        entry.save()

    audit.log_action(
        ResourceAllocationLog.Action.IP_ALLOCATE,
        f'分配 IP {address} 给客户 {customer.code}',
        detail={'entry_id': entry.pk, 'interface_code': interface_code},
        actor=actor,
        correlation_id=correlation_id,
    )
    outbound.schedule_outbound_ip(
        ip_pk=entry.pk,
        reason='ip_allocate',
        actor=actor,
        correlation_id=correlation_id,
        log_action_name=ResourceAllocationLog.Action.SYNC_OUTBOUND,
    )
    return entry


@transaction.atomic
def release_ip(*, address: str, actor: str = 'api') -> None:
    correlation_id = _cid()
    entry = IPAddressEntry.objects.select_for_update().filter(address=address).first()
    if not entry:
        raise ValidationError(f'IP {address} 不存在')

    before = {
        'state': entry.state,
        'customer_id': entry.customer_id,
        'interface_code': entry.interface_code,
    }
    entry.state = IPAddressEntry.State.AVAILABLE
    entry.customer = None
    entry.interface_code = ''
    entry.full_clean()
    entry._skip_outbound = True  # noqa: SLF001
    entry.save()

    audit.log_action(
        ResourceAllocationLog.Action.IP_RELEASE,
        f'释放 IP {address}',
        detail={'before': before},
        actor=actor,
        correlation_id=correlation_id,
    )
    outbound.schedule_outbound_ip(
        ip_pk=entry.pk,
        reason='ip_release',
        actor=actor,
        correlation_id=correlation_id,
        log_action_name=ResourceAllocationLog.Action.SYNC_OUTBOUND,
    )


@transaction.atomic
def upsert_bandwidth_allocation(
    *,
    pool: BandwidthPool,
    interface_code: str,
    allocated_mbps: int,
    customer: ResourceCustomer | None = None,
    remark: str = '',
    actor: str = 'api',
) -> BandwidthAllocation:
    correlation_id = _cid()
    alloc = (
        BandwidthAllocation.objects.select_for_update()
        .filter(pool=pool, interface_code=interface_code)
        .first()
    )
    is_create = alloc is None
    if is_create:
        alloc = BandwidthAllocation(
            pool=pool,
            interface_code=interface_code,
            allocated_mbps=int(allocated_mbps),
            customer=customer,
            remark=remark,
        )
    else:
        alloc.allocated_mbps = int(allocated_mbps)
        alloc.customer = customer
        if remark:
            alloc.remark = remark

    alloc.full_clean()
    alloc._skip_outbound = True  # noqa: SLF001
    alloc.save()

    audit.log_action(
        ResourceAllocationLog.Action.BW_CREATE
        if is_create
        else ResourceAllocationLog.Action.BW_UPDATE,
        f'带宽 {"创建" if is_create else "更新"} {pool.name}/{interface_code}: {allocated_mbps}Mbps',
        detail={'allocation_id': alloc.pk},
        actor=actor,
        correlation_id=correlation_id,
    )
    outbound.schedule_outbound_bandwidth(
        alloc_pk=alloc.pk,
        reason='bw_create' if is_create else 'bw_update',
        actor=actor,
        correlation_id=correlation_id,
        log_action_name=ResourceAllocationLog.Action.SYNC_OUTBOUND,
    )
    return alloc


@transaction.atomic
def delete_bandwidth_allocation(
    *,
    pool: BandwidthPool,
    interface_code: str,
    actor: str = 'api',
) -> None:
    correlation_id = _cid()
    alloc = (
        BandwidthAllocation.objects.select_for_update()
        .filter(pool=pool, interface_code=interface_code)
        .first()
    )
    if not alloc:
        return
    snap: dict[str, Any] = {
        'pool_name': pool.name,
        'interface_code': interface_code,
        'allocated_mbps': alloc.allocated_mbps,
        'customer_code': alloc.customer.code if alloc.customer_id else None,
    }
    alloc._skip_outbound = True  # noqa: SLF001
    alloc.delete()

    audit.log_action(
        ResourceAllocationLog.Action.BW_DELETE,
        f'删除带宽分配 {pool.name}/{interface_code}',
        detail={'removed': snap},
        actor=actor,
        correlation_id=correlation_id,
    )
    outbound.schedule_outbound_bandwidth(
        alloc_pk=None,
        reason='bw_delete',
        actor=actor,
        correlation_id=correlation_id,
        log_action_name=ResourceAllocationLog.Action.SYNC_OUTBOUND,
        deleted_snapshot=snap,
    )
