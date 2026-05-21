from django.contrib import admin

from resourcemanage.models import (
    BandwidthAllocation,
    BandwidthPool,
    IPAddressEntry,
    ResourceCustomer,
    ResourceAllocationLog,
)


@admin.register(ResourceCustomer)
class ResourceCustomerAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active', 'updated_at')
    search_fields = ('code', 'name')


@admin.register(IPAddressEntry)
class IPAddressEntryAdmin(admin.ModelAdmin):
    list_display = ('address', 'state', 'subnet_label', 'customer', 'interface_code', 'updated_at')
    list_filter = ('state', 'subnet_label')
    search_fields = ('address', 'interface_code', 'customer__code')


@admin.register(BandwidthPool)
class BandwidthPoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'total_mbps', 'updated_at')


@admin.register(BandwidthAllocation)
class BandwidthAllocationAdmin(admin.ModelAdmin):
    list_display = ('pool', 'interface_code', 'allocated_mbps', 'customer', 'updated_at')
    list_filter = ('pool',)
    search_fields = ('interface_code', 'customer__code')


@admin.register(ResourceAllocationLog)
class ResourceAllocationLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'actor', 'summary')
    list_filter = ('action',)
    search_fields = ('summary', 'actor', 'id')
    readonly_fields = ('id', 'created_at', 'action', 'actor', 'summary', 'detail', 'correlation_id')
