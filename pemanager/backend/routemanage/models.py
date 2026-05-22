import ipaddress
import re
import uuid

from django.core.exceptions import ValidationError
from django.db import models

from interfacemanage.models import NetworkInterfaceRecord
from resourcemanage.models import IPAddressEntry


class DesiredRouteConfig(models.Model):
    """
    待下发到本机的静态路由意图；写入 netplan 片段（按接口归类）后执行 netplan generate / netplan try。
    """

    class NetplanDeviceClass(models.TextChoices):
        ETHERNETS = 'ethernets', '物理网卡 (ethernets)'
        TUNNELS = 'tunnels', '隧道 (tunnels)'
        BRIDGES = 'bridges', '桥 (bridges)'
        VLANS = 'vlans', 'VLAN (vlans)'
        BONDS = 'bonds', '绑定 (bonds)'
        WIFIS = 'wifis', '无线 (wifis)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    interface_name = models.CharField(
        '接口名',
        max_length=128,
        db_index=True,
        help_text='Linux 接口名，对应 netplan 设备名（如 eth0、wg01）',
    )
    netplan_device_class = models.CharField(
        'netplan 设备类型',
        max_length=32,
        choices=NetplanDeviceClass.choices,
        default=NetplanDeviceClass.ETHERNETS,
        db_index=True,
        help_text='路由挂载到哪一类设备键下，须与实际 netplan 定义一致以便合并',
    )
    dest_cidr = models.CharField(
        '目标',
        max_length=128,
        help_text='CIDR（如 192.168.0.0/24）或 netplan 关键字 default',
    )
    gateway = models.GenericIPAddressField(
        '下一跳 (via)',
        null=True,
        blank=True,
        unpack_ipv4=True,
    )
    on_link = models.BooleanField(
        'on-link',
        default=False,
        help_text='无网关的直连路由时使用（equivalent to on-link: true）',
    )
    metric = models.PositiveIntegerField('metric', null=True, blank=True)
    route_table = models.PositiveIntegerField('路由表 table', null=True, blank=True)
    linked_interface = models.ForeignKey(
        NetworkInterfaceRecord,
        to_field='ifname',
        verbose_name='关联接口记录',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='desired_route_configs',
        help_text='可选：与「接口数据库镜像」对齐；保存时可由此自动带出接口名与 netplan 设备类',
    )
    ip_allocation = models.ForeignKey(
        IPAddressEntry,
        verbose_name='关联 IP 分配',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='route_intents',
        help_text='可选，绑定资源管理中已分配/预留的 IP，用于与接口标识对齐校验',
    )
    customer = models.ForeignKey(
        'resourcemanage.ResourceCustomer',
        verbose_name='关联客户',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='desired_route_configs',
        help_text='仅用于业务关联与权限作用域，不会写入 netplan / ip route / wg-quick 等系统配置文件',
    )
    remark = models.CharField('备注', max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '路由意图配置'
        verbose_name_plural = verbose_name
        ordering = ['interface_name', 'dest_cidr', 'id']

    def __str__(self):
        return f'{self.interface_name} → {self.dest_cidr}'

    def clean(self):
        super().clean()
        dest = (self.dest_cidr or '').strip()
        if not dest:
            raise ValidationError({'dest_cidr': '目标不能为空'})
        if dest.lower() != 'default':
            try:
                ipaddress.ip_network(dest, strict=False)
            except ValueError as exc:
                raise ValidationError({'dest_cidr': f'不是合法 CIDR: {exc}'}) from exc

        if self.on_link and self.gateway:
            raise ValidationError('on-link 与网关 (via) 不宜同时配置')

        if not self.on_link and not self.gateway and dest.lower() not in {'default', '::/0', '0.0.0.0/0'}:
            # 非默认路由通常需要 via 或显式 on-link
            pass  # 允许用户仅填目标（内核可能视为 on-link），不在此强行约束

        if self.ip_allocation_id:
            alloc = self.ip_allocation
            if alloc.state not in (
                IPAddressEntry.State.ALLOCATED,
                IPAddressEntry.State.RESERVED,
            ):
                raise ValidationError(
                    {'ip_allocation': '关联 IP 须为「已分配」或「预留」状态'}
                )
            if (alloc.interface_code or '').strip() and (
                alloc.interface_code.strip() != (self.interface_name or '').strip()
            ):
                raise ValidationError(
                    {
                        'ip_allocation': (
                            f'该 IP 记录的接口标识为 {alloc.interface_code!r}，'
                            f'与路由接口名 {self.interface_name!r} 不一致'
                        )
                    }
                )

        if self.linked_interface_id:
            if (self.interface_name or '').strip() != str(self.linked_interface_id).strip():
                raise ValidationError(
                    {
                        'linked_interface': (
                            '关联接口记录与接口名不一致；请重新选择关联接口或清空关联后再改接口名。'
                        )
                    }
                )


_FWMARK_RE = re.compile(r'^\s*0x[0-9a-fA-F]+|\d+(?:/0x[0-9a-fA-F]+|/\d+)?\s*$')


class PolicyRouteRule(models.Model):
    """
    策略路由（ip rule）意图：维护 `ip rule add/del` 等价配置。
    应用方式：通过 `ip rule` 直接下发到内核（不走 netplan，避免与 routing-policy 段冲突）。
    可选 priority；priority 留空时由内核选择，但建议显式给出以避免重复与覆盖。
    """

    class Family(models.TextChoices):
        INET = 'inet', 'IPv4 (inet)'
        INET6 = 'inet6', 'IPv6 (inet6)'

    class Action(models.TextChoices):
        LOOKUP = 'lookup', '查表 lookup <table>'
        BLACKHOLE = 'blackhole', '丢弃 blackhole'
        UNREACHABLE = 'unreachable', '不可达 unreachable'
        PROHIBIT = 'prohibit', '禁止 prohibit'
        NAT = 'nat', 'NAT'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField('名称', max_length=128, blank=True, help_text='可选，便于识别')
    priority = models.PositiveIntegerField(
        '优先级 priority',
        null=True,
        blank=True,
        db_index=True,
        help_text='ip rule priority；建议 10000-19999（pemanager 受控段）',
    )
    family = models.CharField(
        '地址族', max_length=8, choices=Family.choices, default=Family.INET, db_index=True
    )

    invert = models.BooleanField('not (取反)', default=False)
    from_cidr = models.CharField('源 (from)', max_length=128, blank=True)
    to_cidr = models.CharField('目的 (to)', max_length=128, blank=True)
    iif = models.CharField('入接口 iif', max_length=128, blank=True)
    oif = models.CharField('出接口 oif', max_length=128, blank=True)
    fwmark = models.CharField(
        'fwmark', max_length=64, blank=True, help_text='例如 0x1 或 1/0xff'
    )
    tos = models.CharField('tos', max_length=16, blank=True)
    suppress_prefixlength = models.PositiveIntegerField(
        'suppress_prefixlength', null=True, blank=True
    )

    action = models.CharField(
        '动作', max_length=16, choices=Action.choices, default=Action.LOOKUP
    )
    table_id = models.PositiveIntegerField(
        '路由表 table', null=True, blank=True, help_text='action=lookup 时必填；可填表 ID'
    )
    nat_target = models.GenericIPAddressField('NAT 目标', null=True, blank=True, unpack_ipv4=True)

    enabled = models.BooleanField('启用', default=True, db_index=True)
    customer = models.ForeignKey(
        'resourcemanage.ResourceCustomer',
        verbose_name='关联客户',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='policy_route_rules',
        help_text='仅用于业务关联与权限作用域，不会写入 ip rule 等系统配置文件',
    )
    remark = models.CharField('备注', max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '策略路由意图'
        verbose_name_plural = verbose_name
        ordering = ['priority', 'id']
        indexes = [
            models.Index(fields=['family', 'priority']),
        ]

    def __str__(self):
        prio = f'#{self.priority} ' if self.priority is not None else ''
        return f'{prio}{self.family} from {self.from_cidr or "all"} → {self.summarize_action()}'

    def summarize_action(self) -> str:
        if self.action == self.Action.LOOKUP:
            return f'lookup {self.table_id if self.table_id is not None else "(?)"}'
        if self.action == self.Action.NAT:
            return f'nat {self.nat_target or "(?)"}'
        return self.action

    def clean(self):
        super().clean()
        for label, val in [('from_cidr', self.from_cidr), ('to_cidr', self.to_cidr)]:
            t = (val or '').strip()
            if not t:
                continue
            try:
                ipaddress.ip_network(t, strict=False)
            except ValueError as exc:
                raise ValidationError({label: f'不是合法 CIDR: {exc}'}) from exc

        if (self.fwmark or '').strip():
            if not _FWMARK_RE.match(self.fwmark):
                raise ValidationError({'fwmark': '格式应为 N 或 0xHEX 或 N/0xMASK'})

        if self.action == self.Action.LOOKUP and self.table_id is None:
            raise ValidationError({'table_id': 'action=lookup 时必须填路由表 ID'})
        if self.action == self.Action.NAT and not self.nat_target:
            raise ValidationError({'nat_target': 'action=nat 时必须填 NAT 目标'})

        if not any(
            [
                (self.from_cidr or '').strip(),
                (self.to_cidr or '').strip(),
                (self.iif or '').strip(),
                (self.oif or '').strip(),
                (self.fwmark or '').strip(),
                self.suppress_prefixlength is not None,
            ]
        ):
            raise ValidationError(
                '至少需要一个匹配条件（from/to/iif/oif/fwmark/suppress_prefixlength）'
            )
