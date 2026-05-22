from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accountmanage.models import APIToken, LoginAttempt, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('PE Manager', {'fields': ('role', 'customer', 'phone', 'remark')}),
    )
    list_display = (
        'username', 'role', 'customer', 'is_active', 'is_superuser', 'last_login',
    )
    list_filter = ('role', 'is_active', 'is_superuser', 'customer')


@admin.register(APIToken)
class APITokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'prefix', 'scope', 'revoked', 'expires_at', 'last_used_at')
    list_filter = ('revoked', 'scope')
    search_fields = ('prefix', 'name', 'user__username')


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'username', 'success', 'ip', 'error')
    list_filter = ('success',)
    search_fields = ('username', 'ip')
