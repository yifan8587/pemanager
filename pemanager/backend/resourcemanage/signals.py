from django.db import transaction
from django.dispatch import receiver
from django.db.models.signals import post_delete, post_save

from resourcemanage.models import BandwidthAllocation, IPAddressEntry, ResourceAllocationLog
from resourcemanage.services import outbound


@receiver(post_save, sender=IPAddressEntry)
def ip_entry_saved(sender, instance, **kwargs):
    if getattr(instance, '_skip_outbound', False):
        return

    def _run():
        outbound.schedule_outbound_ip(
            ip_pk=instance.pk,
            reason='model_save',
            actor='django_admin',
            correlation_id=None,
            log_action_name=ResourceAllocationLog.Action.SYNC_OUTBOUND,
        )

    transaction.on_commit(_run)


@receiver(post_save, sender=BandwidthAllocation)
def bandwidth_saved(sender, instance, **kwargs):
    if getattr(instance, '_skip_outbound', False):
        return

    def _run():
        outbound.schedule_outbound_bandwidth(
            alloc_pk=instance.pk,
            reason='model_save',
            actor='django_admin',
            correlation_id=None,
            log_action_name=ResourceAllocationLog.Action.SYNC_OUTBOUND,
        )

    transaction.on_commit(_run)


@receiver(post_delete, sender=BandwidthAllocation)
def bandwidth_deleted(sender, instance, **kwargs):
    if getattr(instance, '_skip_outbound', False):
        return
    snap = {
        'pool_name': instance.pool.name,
        'interface_code': instance.interface_code,
        'allocated_mbps': instance.allocated_mbps,
        'customer_code': instance.customer.code if instance.customer_id else None,
    }

    def _run():
        outbound.schedule_outbound_bandwidth(
            alloc_pk=None,
            reason='model_delete',
            actor='django_admin',
            correlation_id=None,
            log_action_name=ResourceAllocationLog.Action.SYNC_OUTBOUND,
            deleted_snapshot=snap,
        )

    transaction.on_commit(_run)
