from django.contrib import admin

from qosmanage.models import QoSPolicy, QoSRule


class QoSRuleInline(admin.TabularInline):
    model = QoSRule
    extra = 0


@admin.register(QoSPolicy)
class QoSPolicyAdmin(admin.ModelAdmin):
    list_display = ('name', 'interface_name', 'root_kind', 'enabled', 'updated_at')
    list_filter = ('root_kind', 'enabled', 'direction')
    search_fields = ('name', 'interface_name', 'remark')
    inlines = [QoSRuleInline]


@admin.register(QoSRule)
class QoSRuleAdmin(admin.ModelAdmin):
    list_display = ('policy', 'class_id', 'rate_mbps', 'ceil_mbps', 'priority', 'match_kind', 'match_value')
    list_filter = ('match_kind',)
    search_fields = ('match_value', 'remark')
