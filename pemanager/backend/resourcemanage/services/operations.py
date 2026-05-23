from __future__ import annotations

import ipaddress
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


def _sync_remove_routes_in_kernel(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """事务提交后调用：根据 _delete_linked_route_intents 的快照同步从内核删除路由。

    失败不会回滚 DB（DB 已是真理来源），但会把每步的 stderr 透传出去，便于排查。
    """
    if not snapshots:
        return []
    try:
        from routemanage.services.netplan_routes import kernel_remove_routes
        return kernel_remove_routes(snapshots)
    except Exception as e:  # noqa: BLE001
        return [{
            'ok': False,
            'argv': [],
            'stderr': f'内核同步删除失败: {e}',
            'benign': False,
        }]


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


def release_ip(*, address: str, actor: str = 'api') -> dict[str, Any]:
    """释放 IP：清空客户/接口绑定，删除关联路由意图，并同步从内核中删除对应路由。"""
    correlation_id = _cid()
    with transaction.atomic():
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

    kernel_steps = _sync_remove_routes_in_kernel(removed_routes)
    return {
        'address': address,
        'state': entry.state,
        'removed_routes': removed_routes,
        'kernel_steps': kernel_steps,
    }


def recycle_ip(*, address: str, reason: str = '', actor: str = 'api') -> dict[str, Any]:
    """
    将 IP 标记为「回收（不可分配）」。回收前必须释放：
      - 已分配/预留状态：先删除关联路由意图（DB + 内核），再清空 customer/interface_code，最后置为 recycled
      - 可用状态：直接置为 recycled
      - 已是 recycled：幂等返回
    回收后的 IP 不能再次被分配/预留，除非显式调用 restore_ip 重新启用为可用。
    """
    correlation_id = _cid()
    with transaction.atomic():
        entry = IPAddressEntry.objects.select_for_update().filter(address=address).first()
        if not entry:
            raise ValidationError(f'IP {address} 不存在')

        if entry.state == IPAddressEntry.State.RECYCLED:
            return {'address': address, 'state': entry.state, 'removed_routes': [], 'kernel_steps': []}

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

    kernel_steps = _sync_remove_routes_in_kernel(removed_routes)
    return {
        'address': address,
        'state': entry.state,
        'removed_routes': removed_routes,
        'kernel_steps': kernel_steps,
    }


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


# ============================================================
# IP 批量操作
# ============================================================

# 单次批量录入上限，防止滥用导致大事务/UI 卡死
_BULK_IP_CREATE_MAX = 1024
# 其他批量动作（分配/释放/回收）上限
_BULK_IP_ACTION_MAX = 512


def _expand_addresses(
    *,
    addresses: list[str] | None,
    start: str | None,
    end: str | None,
) -> list[str]:
    """把 addresses + (start,end) 展开为去重、有序的 IP 字符串列表。"""
    seen: set[str] = set()
    out: list[str] = []

    def _add(ip_str: str) -> None:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError as e:
            raise ValidationError(f'非法 IP {ip_str}: {e}') from e
        s = str(ip_obj)
        if s not in seen:
            seen.add(s)
            out.append(s)

    if start and end:
        try:
            a = ipaddress.ip_address(start)
            b = ipaddress.ip_address(end)
        except ValueError as e:
            raise ValidationError(f'非法起止 IP: {e}') from e
        if a.version != b.version:
            raise ValidationError('起始与结束 IP 版本不一致')
        if int(b) < int(a):
            raise ValidationError('结束 IP 必须 ≥ 起始 IP')
        span = int(b) - int(a) + 1
        if span > _BULK_IP_CREATE_MAX:
            raise ValidationError(
                f'起止区间共 {span} 个地址，超过单次最大值 {_BULK_IP_CREATE_MAX}'
            )
        cls = ipaddress.IPv4Address if a.version == 4 else ipaddress.IPv6Address
        for i in range(int(a), int(b) + 1):
            _add(str(cls(i)))
    elif start or end:
        raise ValidationError('start 与 end 必须同时提供')

    for s in addresses or []:
        if not s:
            continue
        _add(str(s).strip())

    return out


def bulk_create_ips(
    *,
    addresses: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    state: str = IPAddressEntry.State.AVAILABLE,
    subnet_label: str = '',
    actor: str = 'api',
) -> dict[str, Any]:
    """批量录入 IP：

    - 入参支持「起止区间 start~end」 或「显式 IP 列表 addresses」（可同时给出，合并去重）；
    - 已存在的地址按"skip"处理（不会修改其状态/绑定）；
    - 失败的地址会进入 errors，不会中断整体；
    - 仅允许初始状态为 available / reserved。
    """
    if state not in (
        IPAddressEntry.State.AVAILABLE,
        IPAddressEntry.State.RESERVED,
    ):
        raise ValidationError('批量录入仅允许初始状态为 available / reserved')

    items = _expand_addresses(addresses=addresses, start=start, end=end)
    if not items:
        raise ValidationError('未提供任何待录入 IP')
    if len(items) > _BULK_IP_CREATE_MAX:
        raise ValidationError(f'本次共 {len(items)} 条，超过单次最大值 {_BULK_IP_CREATE_MAX}')

    created: list[str] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    correlation_id = _cid()

    for addr in items:
        try:
            with transaction.atomic():
                exists = IPAddressEntry.objects.filter(address=addr).first()
                if exists:
                    skipped.append({'address': addr, 'reason': f'已存在（{exists.get_state_display()}）'})
                    continue
                entry = IPAddressEntry(
                    address=addr,
                    state=state,
                    subnet_label=subnet_label or '',
                )
                entry.full_clean()
                entry._skip_outbound = True  # noqa: SLF001
                entry.save()
                created.append(addr)
        except Exception as e:  # noqa: BLE001
            errors.append({'address': addr, 'error': str(e)})

    audit.log_action(
        ResourceAllocationLog.Action.IP_UPDATE,
        f'批量录入 IP：成功 {len(created)} / 跳过 {len(skipped)} / 失败 {len(errors)}',
        detail={
            'created': created,
            'skipped': skipped,
            'errors': errors,
            'state': state,
            'subnet_label': subnet_label,
        },
        actor=actor,
        correlation_id=correlation_id,
    )
    return {
        'ok': not errors,
        'total': len(items),
        'created': created,
        'skipped': skipped,
        'errors': errors,
    }


def _bulk_action_dispatch(
    addresses: list[str],
    action_fn,
    *,
    action_label: str,
    actor: str,
    extra_log: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一封装：对地址列表逐条执行 action_fn(address=...)，结果聚合。"""
    if not addresses:
        raise ValidationError('未提供任何待操作 IP')
    items = list({str(a).strip() for a in addresses if a})
    if not items:
        raise ValidationError('未提供任何有效 IP')
    if len(items) > _BULK_IP_ACTION_MAX:
        raise ValidationError(
            f'本次共 {len(items)} 条，超过单次最大值 {_BULK_IP_ACTION_MAX}'
        )

    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []

    for addr in sorted(items):
        try:
            with transaction.atomic():
                res = action_fn(addr)
            if isinstance(res, IPAddressEntry):
                succeeded.append({'address': addr, 'state': res.state})
            elif isinstance(res, dict):
                succeeded.append({'address': addr, **res})
            else:
                succeeded.append({'address': addr})
        except Exception as e:  # noqa: BLE001
            failed.append({'address': addr, 'error': str(e)})

    correlation_id = _cid()
    log_detail: dict[str, Any] = {
        'succeeded': succeeded,
        'failed': failed,
    }
    if extra_log:
        log_detail.update(extra_log)
    audit.log_action(
        ResourceAllocationLog.Action.IP_UPDATE,
        f'{action_label}：成功 {len(succeeded)} / 失败 {len(failed)}',
        detail=log_detail,
        actor=actor,
        correlation_id=correlation_id,
    )
    return {
        'ok': not failed,
        'total': len(items),
        'succeeded': succeeded,
        'failed': failed,
    }


def _materialize_route_template(
    template: dict[str, Any],
    address: str,
    fallback_ifname: str,
) -> dict[str, Any] | None:
    """将批量分配时的「路由模板」结合具体 IP，生成单条 allocate_ip_with_route 所需的 route 字典。

    - dest_cidr_mode = 'host'（默认）：自动用 `<address>/32`（IPv4）或 `<address>/128`（IPv6）
    - dest_cidr_mode = 'custom'：使用模板里的 dest_cidr（所有 IP 共用同一目标，少见但允许）
    - 其他字段（gateway/on_link/metric/route_table/netplan_device_class/remark）直接透传
    - interface_name 优先模板里的，否则回退 fallback_ifname
    """
    if not template:
        return None
    mode = (template.get('dest_cidr_mode') or 'host').lower()
    dest_cidr = (template.get('dest_cidr') or '').strip()
    if mode == 'host':
        try:
            ip_obj = ipaddress.ip_address(address)
            dest_cidr = f'{address}/32' if ip_obj.version == 4 else f'{address}/128'
        except Exception:
            dest_cidr = f'{address}/32'
    elif not dest_cidr:
        # custom 但没填 dest_cidr → 视为不创建路由
        return None

    ifn = (template.get('interface_name') or fallback_ifname or '').strip()
    return {
        'dest_cidr': dest_cidr,
        'interface_name': ifn,
        'gateway': template.get('gateway') or None,
        'on_link': bool(template.get('on_link') or False),
        'metric': template.get('metric'),
        'route_table': template.get('route_table'),
        'netplan_device_class': template.get('netplan_device_class') or '',
        'remark': template.get('remark') or '',
    }


def bulk_allocate_ips(
    *,
    addresses: list[str],
    customer: ResourceCustomer,
    interface_code: str = '',
    subnet_label: str = '',
    allow_from_reserved: bool = True,
    route_template: dict[str, Any] | None = None,
    apply_to_system: bool = False,
    persist_to_netplan: bool = False,
    actor: str = 'api',
) -> dict[str, Any]:
    """批量分配 IP 给客户（每条独立事务，失败不影响其他）。

    - 当传入 route_template 时，对每个 IP 同步创建一条路由意图（host /32 路由为默认）；
    - 当 apply_to_system=True 时，分配完成后用 `ip route replace` 即时下发新建的路由意图
      （仅对本次新建的 route_ids 选择性下发，**不影响其他路由**）；
    - 当 persist_to_netplan=True 时，在即时下发完成后追加 netplan 片段写入 + generate，
      使**重启后**仍保留本次新增的路由（不调用 netplan try）。
    """
    if not customer:
        raise ValidationError('必须指定 customer')
    if not addresses:
        raise ValidationError('未提供任何待操作 IP')
    items = list({str(a).strip() for a in addresses if a})
    if not items:
        raise ValidationError('未提供任何有效 IP')
    if len(items) > _BULK_IP_ACTION_MAX:
        raise ValidationError(
            f'本次共 {len(items)} 条，超过单次最大值 {_BULK_IP_ACTION_MAX}'
        )

    succeeded: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    route_ids: list[str] = []
    correlation_id = _cid()

    for addr in sorted(items):
        try:
            with transaction.atomic():
                rt = _materialize_route_template(route_template or {}, addr, interface_code or '') if route_template else None
                if rt:
                    res = allocate_ip_with_route(
                        address=addr,
                        customer=customer,
                        interface_code=interface_code or '',
                        subnet_label=subnet_label or '',
                        allow_from_reserved=allow_from_reserved,
                        actor=actor,
                        route=rt,
                    )
                    item: dict[str, Any] = {
                        'address': addr,
                        'state': res.get('state'),
                        'route_id': res.get('route_id'),
                    }
                    if res.get('route_id'):
                        route_ids.append(str(res['route_id']))
                else:
                    entry = allocate_ip(
                        address=addr,
                        customer=customer,
                        interface_code=interface_code or '',
                        subnet_label=subnet_label or '',
                        allow_from_reserved=allow_from_reserved,
                        actor=actor,
                    )
                    item = {'address': addr, 'state': entry.state}
            succeeded.append(item)
        except Exception as e:  # noqa: BLE001
            failed.append({'address': addr, 'error': str(e)})

    apply_result: dict[str, Any] | None = None
    if apply_to_system and route_ids:
        try:
            from routemanage.services.netplan_routes import apply_desired_routes_immediate
            apply_result = apply_desired_routes_immediate(
                route_ids, persist_to_netplan=bool(persist_to_netplan),
            )
        except Exception as e:  # noqa: BLE001
            apply_result = {'ok': False, 'error': str(e), 'steps': []}

    audit.log_action(
        ResourceAllocationLog.Action.IP_UPDATE,
        (
            f'批量分配 IP 给客户 {customer.code}：成功 {len(succeeded)} / 失败 {len(failed)} '
            f'/ 新增路由 {len(route_ids)}'
            + (
                '（已下发到系统'
                + ('+持久化 netplan' if persist_to_netplan else '')
                + '）'
                if apply_to_system and route_ids else ''
            )
        ),
        detail={
            'succeeded': succeeded,
            'failed': failed,
            'customer_code': customer.code,
            'interface_code': interface_code or '',
            'subnet_label': subnet_label or '',
            'route_template': route_template or None,
            'route_ids': route_ids,
            'apply_to_system': bool(apply_to_system),
            'persist_to_netplan': bool(persist_to_netplan),
            'apply_result': apply_result,
        },
        actor=actor,
        correlation_id=correlation_id,
    )
    return {
        'ok': not failed and (apply_result is None or bool(apply_result.get('ok', True))),
        'total': len(items),
        'succeeded': succeeded,
        'failed': failed,
        'route_ids': route_ids,
        'apply_result': apply_result,
    }


def _persist_routes_fragment_after_changes() -> dict[str, Any] | None:
    """在路由意图发生变化（删除/释放/回收）后，同步重写 netplan routes 片段并 generate。

    - 仅写 `/etc/netplan/99-pemanager-routes.yaml` + 执行 `netplan generate`；
    - 不执行 `netplan try/apply`，因此**不会**重启或抖动现有接口；
    - 失败时返回包含 error 的结构（调用方按需聚合到响应里）。
    """
    try:
        from routemanage.services.netplan_routes import _persist_routes_netplan_fragment_only
        return _persist_routes_netplan_fragment_only()
    except Exception as e:  # noqa: BLE001
        return {'ok': False, 'error': str(e), 'steps': []}


def bulk_release_ips(
    *,
    addresses: list[str],
    actor: str = 'api',
) -> dict[str, Any]:
    """批量释放 IP（清空客户/接口绑定，删除关联路由意图，并同步内核+netplan 持久化层）。"""

    def _do(addr: str):
        return release_ip(address=addr, actor=actor)

    res = _bulk_action_dispatch(
        addresses,
        _do,
        action_label='批量释放 IP',
        actor=actor,
    )
    # 任何成功释放都可能对应了已写入 netplan 片段的路由意图被删除，
    # 这里同步重写一次 netplan 片段（仅 generate，不 try/apply），
    # 确保**重启后**已删除的路由不会再被恢复。
    removed_total = sum(len((s or {}).get('removed_routes') or []) for s in res.get('succeeded') or [])
    if removed_total > 0:
        res['netplan_persist'] = _persist_routes_fragment_after_changes()
        res['removed_routes_total'] = removed_total
    return res


def bulk_recycle_ips(
    *,
    addresses: list[str],
    reason: str = '',
    actor: str = 'api',
) -> dict[str, Any]:
    """批量回收 IP（标记为 recycled，不可再分配；同步删除路由并刷新 netplan 持久化层）。"""

    def _do(addr: str):
        return recycle_ip(address=addr, reason=reason or '', actor=actor)

    res = _bulk_action_dispatch(
        addresses,
        _do,
        action_label='批量回收 IP',
        actor=actor,
        extra_log={'reason': reason or ''},
    )
    removed_total = sum(len((s or {}).get('removed_routes') or []) for s in res.get('succeeded') or [])
    if removed_total > 0:
        res['netplan_persist'] = _persist_routes_fragment_after_changes()
        res['removed_routes_total'] = removed_total
    return res
