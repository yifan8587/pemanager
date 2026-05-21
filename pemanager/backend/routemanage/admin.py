from django.contrib import admin

from routemanage.models import DesiredRouteConfig


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
