from django.contrib import admin

from routemanage.models import DesiredRouteConfig, PolicyRouteRule


@admin.register(DesiredRouteConfig)
class DesiredRouteConfigAdmin(admin.ModelAdmin):
    list_display = [
        'interface_name',
        'netplan_device_class',
        'linked_interface',
        'dest_cidr',
        'gateway',
        'metric',
        'route_table',
        'ip_allocation',
        'remark',
        'updated_at',
    ]
    list_filter = ['netplan_device_class']
    search_fields = ['interface_name', 'dest_cidr', 'remark']
    autocomplete_fields = ['ip_allocation', 'linked_interface']
    ordering = ['interface_name', 'dest_cidr']


@admin.register(PolicyRouteRule)
class PolicyRouteRuleAdmin(admin.ModelAdmin):
    list_display = [
        'priority',
        'name',
        'family',
        'from_cidr',
        'to_cidr',
        'iif',
        'oif',
        'fwmark',
        'action',
        'table_id',
        'enabled',
        'updated_at',
    ]
    list_filter = ['family', 'action', 'enabled']
    search_fields = ['name', 'from_cidr', 'to_cidr', 'iif', 'oif', 'remark']
    ordering = ['priority']
