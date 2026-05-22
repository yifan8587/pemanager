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
        if entry.state == IPAddressEntry.State.RECYCLED:
            raise ValidationError(f'IP {address} 已被回收（不可分配），如需重新启用请先「恢复」为可用状态')
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
        if entry.state == IPAddressEntry.State.RECYCLED:
            raise ValidationError(
                f'IP {address} 已被回收（不可分配）；如需重新启用请先在 IP 地址列表中执行「恢复」操作'
            )
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


def _delete_linked_route_intents(entry: IPAddressEntry) -> list[dict[str, Any]]:
    """删除 routemanage 中所有与该 IP 关联的 DesiredRouteConfig；返回被删除快照供审计。"""
    # lazy import 避免应用启动期循环依赖
    try:
        from routemanage.models import DesiredRouteConfig
    except Exception:  # noqa: BLE001
        return []
    removed: list[dict[str, Any]] = []
    qs = DesiredRouteConfig.objects.filter(ip_allocation_id=entry.pk).select_for_update()
    for r in qs:
        removed.append(
            {
                'id': str(r.id),
                'interface_name': r.interface_name,
                'dest_cidr': r.dest_cidr,
                'gateway': str(r.gateway) if r.gateway else None,
                'route_table': r.route_table,
            }
        )
    qs.delete()
    return removed


@transaction.atomic
def release_ip(*, address: str, actor: str = 'api') -> dict[str, Any]:
    correlation_id = _cid()
    entry = IPAddressEntry.objects.select_for_update().filter(address=address).first()
    if not entry:
        raise ValidationError(f'IP {address} 不存在')

    before = {
        'state': entry.state,
        'customer_id': entry.customer_id,
        'interface_code': entry.interface_code,
    }
    removed_routes = _delete_linked_route_intents(entry)

    entry.state = IPAddressEntry.State.AVAILABLE
    entry.customer = None
    entry.interface_code = ''
    entry.full_clean()
    entry._skip_outbound = True  # noqa: SLF001
    entry.save()

    audit.log_action(
        ResourceAllocationLog.Action.IP_RELEASE,
        f'释放 IP {address}（同时删除 {len(removed_routes)} 条关联路由意图）',
        detail={'before': before, 'removed_routes': removed_routes},
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
    return {'address': address, 'state': entry.state, 'removed_routes': removed_routes}


@transaction.atomic
def recycle_ip(*, address: str, reason: str = '', actor: str = 'api') -> dict[str, Any]:
    """
    将 IP 标记为「回收（不可分配）」。回收前必须释放：
      - 已分配/预留状态：先删除关联路由意图，再清空 customer/interface_code，最后置为 recycled
      - 可用状态：直接置为 recycled
      - 已是 recycled：幂等返回
    回收后的 IP 不能再次被分配/预留，除非显式调用 restore_ip 重新启用为可用。
    """
    correlation_id = _cid()
    entry = IPAddressEntry.objects.select_for_update().filter(address=address).first()
    if not entry:
        raise ValidationError(f'IP {address} 不存在')

    if entry.state == IPAddressEntry.State.RECYCLED:
        return {'address': address, 'state': entry.state, 'removed_routes': []}

    before = {
        'state': entry.state,
        'customer_id': entry.customer_id,
        'interface_code': entry.interface_code,
    }
    removed_routes = _delete_linked_route_intents(entry)

    entry.state = IPAddressEntry.State.RECYCLED
    entry.customer = None
    entry.interface_code = ''
    if reason:
        extra = dict(entry.extra or {})
        extra['recycle_reason'] = reason
        entry.extra = extra
    entry.full_clean()
    entry._skip_outbound = True  # noqa: SLF001
    entry.save()

    audit.log_action(
        ResourceAllocationLog.Action.IP_UPDATE,
        f'回收 IP {address}（删除 {len(removed_routes)} 条关联路由意图）',
        detail={'before': before, 'removed_routes': removed_routes, 'reason': reason or ''},
        actor=actor,
        correlation_id=correlation_id,
    )
    outbound.schedule_outbound_ip(
        ip_pk=entry.pk,
        reason='ip_recycle',
        actor=actor,
        correlation_id=correlation_id,
        log_action_name=ResourceAllocationLog.Action.SYNC_OUTBOUND,
    )
    return {'address': address, 'state': entry.state, 'removed_routes': removed_routes}


@transaction.atomic
def restore_ip(*, address: str, actor: str = 'api') -> IPAddressEntry:
    """把回收态 IP 恢复为可用（管理员操作；不会重新绑定客户/接口）。"""
    correlation_id = _cid()
    entry = IPAddressEntry.objects.select_for_update().filter(address=address).first()
    if not entry:
        raise ValidationError(f'IP {address} 不存在')
    if entry.state != IPAddressEntry.State.RECYCLED:
        raise ValidationError(f'IP {address} 当前状态为 {entry.get_state_display()}，无需恢复')
    entry.state = IPAddressEntry.State.AVAILABLE
    entry.customer = None
    entry.interface_code = ''
    extra = dict(entry.extra or {})
    extra.pop('recycle_reason', None)
    entry.extra = extra
    entry.full_clean()
    entry._skip_outbound = True  # noqa: SLF001
    entry.save()

    audit.log_action(
        ResourceAllocationLog.Action.IP_UPDATE,
        f'恢复 IP {address} 为可用',
        detail={'entry_id': entry.pk},
        actor=actor,
        correlation_id=correlation_id,
    )
    return entry


@transaction.atomic
def allocate_ip_with_route(
    *,
    address: str,
    customer: ResourceCustomer,
    interface_code: str = '',
    subnet_label: str = '',
    allow_from_reserved: bool = True,
    actor: str = 'api',
    route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    IP 分配 + 同步创建路由意图。
    route 参数（全部可选）：
      - dest_cidr        : 必填（创建路由时）
      - gateway          : 可选
      - on_link          : 可选（默认 False）
      - metric / route_table
      - netplan_device_class
      - interface_name   : 缺省取 interface_code
      - remark
    若 route 为 None 或缺少 dest_cidr，则只做 IP 分配（行为同 allocate_ip）。
    """
    entry = allocate_ip(
        address=address,
        customer=customer,
        interface_code=interface_code,
        subnet_label=subnet_label,
        allow_from_reserved=allow_from_reserved,
        actor=actor,
    )

    created_route_id: str | None = None
    if route and (route.get('dest_cidr') or '').strip():
        from routemanage.models import DesiredRouteConfig

        ifn = (route.get('interface_name') or interface_code or '').strip()
        if not ifn:
            raise ValidationError('创建关联路由时必须提供 interface_name 或 IP 的 interface_code')

        gw = route.get('gateway') or None
        on_link = bool(route.get('on_link'))
        dest_cidr = str(route['dest_cidr']).strip()
        netplan_class = (
            route.get('netplan_device_class')
            or DesiredRouteConfig.NetplanDeviceClass.ETHERNETS
        )
        rec = DesiredRouteConfig(
            interface_name=ifn,
            netplan_device_class=netplan_class,
            dest_cidr=dest_cidr,
            gateway=gw,
            on_link=on_link,
            metric=route.get('metric'),
            route_table=route.get('route_table'),
            ip_allocation=entry,
            remark=(route.get('remark') or '')[:512],
        )
        rec.full_clean()
        rec.save()
        created_route_id = str(rec.id)

        audit.log_action(
            ResourceAllocationLog.Action.IP_UPDATE,
            f'IP {address} 分配时联动创建路由意图 {ifn} → {dest_cidr}',
            detail={'route_id': created_route_id, 'ip': address, 'customer': customer.code},
            actor=actor,
        )

    return {
        'address': address,
        'state': entry.state,
        'customer_code': customer.code,
        'interface_code': entry.interface_code,
        'route_id': created_route_id,
    }


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
