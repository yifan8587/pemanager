from django.contrib import admin

from logmanage.models import AppOperationLog


@admin.register(AppOperationLog)
class AppOperationLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'app', 'category', 'level', 'actor', 'summary')
    list_filter = ('app', 'level', 'category')
    search_fields = ('summary', 'actor', 'target')
    readonly_fields = ('id', 'created_at')
    ordering = ('-created_at',)
