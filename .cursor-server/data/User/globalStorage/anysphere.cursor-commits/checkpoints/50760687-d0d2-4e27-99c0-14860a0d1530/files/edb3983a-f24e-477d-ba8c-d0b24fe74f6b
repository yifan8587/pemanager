import ipaddress
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
