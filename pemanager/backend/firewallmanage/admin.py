from django.contrib import admin

from firewallmanage.models import FirewallRule


@admin.register(FirewallRule)
class FirewallRuleAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'enabled',
        'chain',
        'action',
        'protocol',
        'family',
        'src_cidr',
        'dst_cidr',
        'priority',
        'updated_at',
    )
    list_filter = ('chain', 'action', 'protocol', 'family', 'enabled')
    search_fields = ('name', 'src_cidr', 'dst_cidr', 'remark')
    ordering = ('chain', 'priority', 'created_at')
