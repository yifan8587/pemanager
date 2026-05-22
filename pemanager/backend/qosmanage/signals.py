"""QoS 模型信号：策略保存/删除时联动资源管理 BandwidthAllocation。"""
from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from qosmanage.models import QoSPolicy
from qosmanage.services import sync_resource

log = logging.getLogger(__name__)


@receiver(post_save, sender=QoSPolicy)
def _qos_policy_post_save(sender, instance: QoSPolicy, created: bool, **kwargs):
    if getattr(instance, '_skip_resource_sync', False):
        return
    try:
        sync_resource.sync_policy_to_resource(instance)
    except Exception:  # noqa: BLE001
        log.exception('QoS 策略 %s 同步到 BandwidthAllocation 失败', instance.name)
        raise


@receiver(post_delete, sender=QoSPolicy)
def _qos_policy_post_delete(sender, instance: QoSPolicy, **kwargs):
    try:
        sync_resource.delete_policy_from_resource(instance)
    except Exception:  # noqa: BLE001  # 删除阶段失败不抛
        log.exception('QoS 策略 %s 删除时清理 BandwidthAllocation 失败', instance.name)
