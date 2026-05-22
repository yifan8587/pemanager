"""Viewset 作用域复用 mixin。

设计：
- `AdminOnlyMixin`：要求 admin（防火墙、操作工具、监控管理、日志中心 等）。
- `CustomerScopedByCustomerFKMixin`：按 user.customer 过滤 queryset 的 `customer` 外键；
  客户角色只读，admin 可写。
- `CustomerScopedByInterfaceMixin`：按 user 的"接口名集合"过滤指定字段（默认 `interface_name`）；
  客户角色只读，admin 可写。

注意：所有 mixin 都需要放在父类列表的最前面（在 `viewsets.ModelViewSet` 之前），
让 `get_queryset` / `permission_classes` 生效。
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated

from accountmanage.permissions import IsAdmin, ReadOnlyForCustomer
from accountmanage.services.scope import scope_customer, scope_interface_codes


class AdminOnlyMixin:
    permission_classes = [IsAuthenticated, IsAdmin]


class CustomerScopedByCustomerFKMixin:
    """通过 user.customer 过滤 queryset 上的某个客户外键。"""

    permission_classes = [IsAuthenticated, ReadOnlyForCustomer]
    customer_field = 'customer'

    def get_queryset(self):
        qs = super().get_queryset()
        cust = scope_customer(self.request.user)
        if cust is None:
            return qs
        return qs.filter(**{self.customer_field: cust})


class CustomerScopedByInterfaceMixin:
    """通过 user 的可见接口集合，过滤 queryset 上的某个接口名字段（默认 `interface_name`）。"""

    permission_classes = [IsAuthenticated, ReadOnlyForCustomer]
    interface_field = 'interface_name'

    def get_queryset(self):
        qs = super().get_queryset()
        codes = scope_interface_codes(self.request.user)
        if codes is None:
            return qs
        if not codes:
            return qs.none()
        return qs.filter(**{f'{self.interface_field}__in': list(codes)})
