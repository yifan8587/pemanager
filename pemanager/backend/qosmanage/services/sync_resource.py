"""
QoS ↔ 资源管理（BandwidthAllocation）联动。

设计：
- QoSPolicy 可选 linked_pool。当存在 linked_pool 时：
  - 保存策略 → upsert 一条 BandwidthAllocation
    (pool=linked_pool, interface_code=interface_name) 为 default_ceil_mbps
    并把 QoSPolicy.synced_bandwidth_allocation 指向它（便于反向清理）。
  - 切换 / 取消 linked_pool 时：删除原同步出来的 BandwidthAllocation。
- 策略删除时：删除自身同步出来的 BandwidthAllocation。
- 失败时（如池超额），抛出 ValidationError，让 ViewSet 把错误返给前端，
  策略本身的保存事务会回滚（保持数据一致）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from resourcemanage.models import BandwidthAllocation

if TYPE_CHECKING:
    from qosmanage.models import QoSPolicy


def _upsert_allocation(policy: 'QoSPolicy') -> BandwidthAllocation:
    pool = policy.linked_pool
    iface = (policy.interface_name or '').strip()
    if not pool or not iface:
        raise ValidationError('需要同时指定 linked_pool 与 interface_name')

    mbps = int(policy.effective_rate_mbps)
    if mbps <= 0:
        raise ValidationError({'rate_mbps': 'QoS 策略带宽必须 > 0'})

    alloc = (
        BandwidthAllocation.objects.select_for_update()
        .filter(pool=pool, interface_code=iface)
        .first()
    )
    if not alloc:
        alloc = BandwidthAllocation(
            pool=pool,
            interface_code=iface,
            allocated_mbps=mbps,
            customer=policy.customer,
            remark=f'auto: QoS策略 {policy.name}',
        )
    else:
        alloc.allocated_mbps = mbps
        alloc.customer = policy.customer
        if not alloc.remark.startswith('auto: QoS策略'):
            alloc.remark = f'auto: QoS策略 {policy.name}'

    alloc.full_clean()
    alloc._skip_outbound = True  # noqa: SLF001
    alloc.save()
    return alloc


def _delete_managed_allocation(policy: 'QoSPolicy', *, persist_policy: bool = True) -> bool:
    """删除策略当前 synced_bandwidth_allocation 指向的记录。
    persist_policy=False 用于 post_delete 阶段：policy 已经在销毁，不能再 .save()。
    """
    alloc = policy.synced_bandwidth_allocation
    if not alloc:
        return False
    try:
        alloc._skip_outbound = True  # noqa: SLF001
        alloc.delete()
    except BandwidthAllocation.DoesNotExist:  # pragma: no cover
        pass
    policy.synced_bandwidth_allocation = None
    if persist_policy:
        policy.save(update_fields=['synced_bandwidth_allocation'])
    return True


@transaction.atomic
def sync_policy_to_resource(policy: 'QoSPolicy') -> dict:
    """
    根据当前 policy 的 linked_pool 状态进行同步：
    - 关联池存在    → upsert BandwidthAllocation，并更新 synced_bandwidth_allocation 指针
    - 未关联池      → 删除上一轮同步出来的 BandwidthAllocation
    - 关联池发生变化 → 旧的删除，新的 upsert
    """
    prev = policy.synced_bandwidth_allocation
    # 关联池为空：清理上次的同步产物
    if not policy.linked_pool_id:
        if prev:
            prev._skip_outbound = True  # noqa: SLF001
            prev.delete()
            policy.synced_bandwidth_allocation = None
            policy.save(update_fields=['synced_bandwidth_allocation'])
        return {'action': 'unlinked', 'removed': bool(prev)}

    # 关联池变化时，先删旧的（避免脏数据残留）
    if prev and (prev.pool_id != policy.linked_pool_id or prev.interface_code != (policy.interface_name or '').strip()):
        prev._skip_outbound = True  # noqa: SLF001
        prev.delete()
        policy.synced_bandwidth_allocation = None

    alloc = _upsert_allocation(policy)
    if policy.synced_bandwidth_allocation_id != alloc.pk:
        policy.synced_bandwidth_allocation = alloc
        policy.save(update_fields=['synced_bandwidth_allocation'])
    return {
        'action': 'upserted',
        'pool': policy.linked_pool.name,
        'interface_code': alloc.interface_code,
        'allocated_mbps': alloc.allocated_mbps,
        'allocation_id': alloc.pk,
    }


@transaction.atomic
def delete_policy_from_resource(policy: 'QoSPolicy') -> bool:
    """策略删除时清理其同步出来的 BandwidthAllocation（不会再 .save 已删除的 policy）。"""
    return _delete_managed_allocation(policy, persist_policy=False)
