"""权限类：
- `IsAdmin`：只允许 admin / superuser。
- `IsOperator`：admin + operator。
- `IsAdminOrScopedReadOnly`：admin 全开；其他认证用户只允许只读（GET/HEAD/OPTIONS）。
- `ReadOnlyForCustomer`：客户角色禁止写，其它角色读写交由后续权限/视图层决定。
"""
from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from accountmanage.services import scope as scope_svc


class IsAdmin(BasePermission):
    message = '需要管理员权限'

    def has_permission(self, request, view):
        return scope_svc.is_admin(request.user)


class IsOperator(BasePermission):
    message = '需要运维或管理员权限'

    def has_permission(self, request, view):
        return scope_svc.is_operator(request.user)


class IsAdminOrScopedReadOnly(BasePermission):
    """admin 全权；其他认证用户只读。客户用户由 viewset 的 get_queryset 自行作用域过滤。"""

    message = '权限不足'

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if scope_svc.is_admin(u):
            return True
        return request.method in SAFE_METHODS


class ReadOnlyForCustomer(BasePermission):
    """客户角色禁止写；admin/operator 不受限。"""

    message = '客户账号仅可只读'

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if scope_svc.is_admin(u) or scope_svc.is_operator(u):
            return True
        return request.method in SAFE_METHODS


class CustomerScopedWritable(BasePermission):
    """允许客户在自己作用域内 CRUD 与下发；admin / operator 不受限。

    - 任何已认证用户的请求都允许进入 ViewSet（GET / POST / PUT / PATCH / DELETE
      及 @action 写操作）；
    - 客户能"看到/写到"的资源边界，由各 ViewSet 的 `get_queryset()` 用
      `scope_qs(..., customer_field=...)` 强制；
    - 该权限本身不阻止动作，但会拒绝未认证用户。

    适用场景：客户允许自助维护自己客户名下的接口意图 / 路由意图 / 策略路由 / 监控目标，
    并允许对其触发下发 / 立即采样等动作。
    """

    message = '需要登录后才能操作'

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated)
