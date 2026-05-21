from django.contrib import admin

from operationmanage.models import (
    InterfaceTrafficSample,
    LatencySample,
    MonitorTarget,
)


@admin.register(MonitorTarget)
class MonitorTargetAdmin(admin.ModelAdmin):
    list_display = ('name', 'address', 'kind', 'enabled', 'interval_sec', 'last_sampled_at')
    list_filter = ('kind', 'enabled')
    search_fields = ('name', 'address', 'remark')


@admin.register(LatencySample)
class LatencySampleAdmin(admin.ModelAdmin):
    list_display = ('ts', 'target', 'rtt_avg_ms', 'loss_pct', 'ok')
    list_filter = ('ok', 'target')
    date_hierarchy = 'ts'


@admin.register(InterfaceTrafficSample)
class InterfaceTrafficSampleAdmin(admin.ModelAdmin):
    list_display = ('ts', 'interface_name', 'rx_bps', 'tx_bps')
    list_filter = ('interface_name',)
    date_hierarchy = 'ts'
