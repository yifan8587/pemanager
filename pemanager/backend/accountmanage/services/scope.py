"""客户作用域工具：把"当前用户能看到哪些客户/接口名"集中起来，便于各 viewset 复用。"""
from __future__ import annotations

from typing import Iterable

from django.db.models import Q

from resourcemanage.models import IPAddressEntry, ResourceCustomer


def is_admin(user) -> bool:
    return bool(user and user.is_authenticated and getattr(user, 'is_admin_role', False))


def is_operator(user) -> bool:
    return bool(user and user.is_authenticated and getattr(user, 'is_operator_role', False))


def scope_customer(user) -> ResourceCustomer | None:
    """返回该用户绑定的客户；管理员/运维返回 None（表示无作用域限制）。"""
    if not (user and user.is_authenticated):
        return None
    if getattr(user, 'is_admin_role', False) or getattr(user, 'is_operator_role', False):
        return None
    cust = getattr(user, 'customer', None)
    return cust if cust else None


def scope_interface_codes(user) -> set[str] | None:
    """返回该用户能访问的接口标识集合；None 表示无限制（admin/operator）。

    客户能访问的接口 = 该客户在 IPAddressEntry 中所有非空的 `interface_code` 的去重集合，
    并叠加：BandwidthAllocation 中该客户的 `interface_code`、QoSPolicy 中绑定该客户的 `interface_name`。
    """
    cust = scope_customer(user)
    if cust is None and (is_admin(user) or is_operator(user)):
        return None
    if cust is None:
        # 未绑定客户的非 admin 用户：视为没有任何接口
        return set()

    codes: set[str] = set()
    # 1) IP 表
    for ic in IPAddressEntry.objects.filter(customer=cust).exclude(interface_code='').values_list(
        'interface_code', flat=True
    ):
        if ic:
            codes.add(ic.strip())

    # 2) 带宽分配
    try:
        from resourcemanage.models import BandwidthAllocation

        for ic in BandwidthAllocation.objects.filter(customer=cust).exclude(interface_code='').values_list(
            'interface_code', flat=True
        ):
            if ic:
                codes.add(ic.strip())
    except Exception:  # noqa: BLE001
        pass

    # 3) QoS 策略
    try:
        from qosmanage.models import QoSPolicy

        for nm in QoSPolicy.objects.filter(customer=cust).exclude(interface_name='').values_list(
            'interface_name', flat=True
        ):
            if nm:
                codes.add(nm.strip())
    except Exception:  # noqa: BLE001
        pass

    return codes


def filter_by_interface_codes(qs, field: str, codes: Iterable[str] | None):
    """通用：把 queryset 按"接口字段属于该集合"过滤；codes=None 表示无限制。"""
    if codes is None:
        return qs
    return qs.filter(**{f'{field}__in': list(codes)})


def scope_qs(qs, user, *, customer_field: str | None = 'customer', interface_field: str | None = None):
    """统一作用域过滤：客户用户可见 = ( customer FK 命中 ) OR ( interface 字段在 scope_interface_codes 内 )。

    用法：
        qs = scope_qs(qs, request.user, customer_field='customer', interface_field='ifname')

    - admin / operator → 不过滤；
    - 未绑定客户的非 admin → 空集；
    - 已绑定客户：customer_field 直接命中的，或 interface_field ∈ codes 的；
      任一为空表示不参与该方向的命中。
    """
    if is_admin(user) or is_operator(user):
        return qs
    cust = scope_customer(user)
    if cust is None:
        return qs.none()

    conds = Q(pk__in=[])  # 起始永假，便于后面 OR
    matched = False
    if customer_field:
        conds = conds | Q(**{customer_field: cust})
        matched = True
    if interface_field:
        codes = scope_interface_codes(user) or set()
        if codes:
            conds = conds | Q(**{f'{interface_field}__in': list(codes)})
            matched = True
    if not matched:
        return qs.none()
    return qs.filter(conds).distinct()
