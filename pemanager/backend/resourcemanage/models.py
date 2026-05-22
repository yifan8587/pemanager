import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum


class ResourceCustomer(models.Model):
    """客户（资源分配对象）"""

    code = models.SlugField('客户编码', max_length=64, unique=True, db_index=True)
    name = models.CharField('名称', max_length=128)
    remark = models.CharField('备注', max_length=512, blank=True)
    is_active = models.BooleanField('启用', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '客户'
        verbose_name_plural = verbose_name
        ordering = ['code']

    def __str__(self):
        return f'{self.code} ({self.name})'


class IPAddressEntry(models.Model):
    """IP 地址表：可用 / 预留 / 已分配及与客户、接口的关联"""

    class State(models.TextChoices):
        AVAILABLE = 'available', '可用'
        RESERVED = 'reserved', '预留'
        ALLOCATED = 'allocated', '已分配'
        RECYCLED = 'recycled', '回收（不可分配）'

    address = models.GenericIPAddressField('IP 地址', unique=True, db_index=True)
    state = models.CharField(
        '状态',
        max_length=16,
        choices=State.choices,
        default=State.AVAILABLE,
        db_index=True,
    )
    subnet_label = models.CharField(
        '网段/分组标签',
        max_length=128,
        blank=True,
        help_text='用于标识地址段或 VLAN 等，便于过滤',
    )
    customer = models.ForeignKey(
        ResourceCustomer,
        verbose_name='客户',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ip_addresses',
    )
    interface_code = models.CharField(
        '接口标识',
        max_length=128,
        blank=True,
        db_index=True,
        help_text='与 interfacemanage 等模块约定的接口编码，便于同步下发',
    )
    extra = models.JSONField('扩展信息', default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'IP 地址'
        verbose_name_plural = verbose_name
        ordering = ['address']

    def __str__(self):
        return f'{self.address} ({self.get_state_display()})'

    def clean(self):
        super().clean()
        if self.state in (self.State.AVAILABLE, self.State.RECYCLED):
            if self.customer_id or self.interface_code:
                raise ValidationError(f'状态为「{self.get_state_display()}」时不能绑定客户或接口')
        if self.state == self.State.ALLOCATED and not self.customer_id:
            raise ValidationError('「已分配」状态必须指定客户')


class BandwidthPool(models.Model):
    """总带宽池"""

    name = models.CharField('名称', max_length=64, unique=True)
    total_mbps = models.PositiveIntegerField('总带宽(Mbps)')
    remark = models.CharField('备注', max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '带宽池'
        verbose_name_plural = verbose_name
        ordering = ['name']

    def __str__(self):
        return self.name

    def allocated_mbps(self) -> int:
        agg = self.allocations.aggregate(s=Sum('allocated_mbps'))
        return int(agg['s'] or 0)

    def remaining_mbps(self) -> int:
        return max(0, int(self.total_mbps) - self.allocated_mbps())


class BandwidthAllocation(models.Model):
    """带宽分配到客户与接口"""

    pool = models.ForeignKey(
        BandwidthPool,
        verbose_name='带宽池',
        on_delete=models.CASCADE,
        related_name='allocations',
    )
    customer = models.ForeignKey(
        ResourceCustomer,
        verbose_name='客户',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='bandwidth_allocations',
    )
    interface_code = models.CharField(
        '接口标识',
        max_length=128,
        db_index=True,
        help_text='与业务模块约定的接口编码',
    )
    allocated_mbps = models.PositiveIntegerField('分配带宽(Mbps)')
    remark = models.CharField('备注', max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '带宽分配'
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=['pool', 'interface_code'],
                name='uniq_bandwidth_pool_interface',
            ),
        ]
        ordering = ['pool', 'interface_code']

    def __str__(self):
        return f'{self.pool.name}/{self.interface_code}: {self.allocated_mbps}Mbps'

    def clean(self):
        super().clean()
        if not self.interface_code:
            raise ValidationError('接口标识不能为空')
        exclude_qs = BandwidthAllocation.objects.filter(
            pool_id=self.pool_id,
            interface_code=self.interface_code,
        )
        if self.pk:
            exclude_qs = exclude_qs.exclude(pk=self.pk)
        others = exclude_qs.aggregate(s=Sum('allocated_mbps'))
        others_sum = int(others['s'] or 0)
        cap = int(self.pool.total_mbps)
        if others_sum + int(self.allocated_mbps) > cap:
            raise ValidationError(
                f'带宽池 "{self.pool.name}" 超额：已分配 {others_sum}Mbps，'
                f'本次 {self.allocated_mbps}Mbps，超过总量 {cap}Mbps'
            )


class ResourceAllocationLog(models.Model):
    """IP/带宽 分配、变更、同步等操作记录"""

    class Action(models.TextChoices):
        IP_RESERVE = 'ip_reserve', 'IP 预留'
        IP_ALLOCATE = 'ip_allocate', 'IP 分配'
        IP_RELEASE = 'ip_release', 'IP 释放'
        IP_UPDATE = 'ip_update', 'IP 变更'
        BW_CREATE = 'bw_create', '带宽分配创建'
        BW_UPDATE = 'bw_update', '带宽分配变更'
        BW_DELETE = 'bw_delete', '带宽分配删除'
        SYNC_OUTBOUND = 'sync_outbound', '同步下发(资源→其他应用)'
        SYNC_INBOUND = 'sync_inbound', '同步回写(其他应用→资源)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField('时间', db_index=True, auto_now_add=True)
    action = models.CharField('操作', max_length=32, choices=Action.choices, db_index=True)
    actor = models.CharField('操作者', max_length=128, blank=True, help_text='用户名或 system / api')
    summary = models.CharField('摘要', max_length=512)
    detail = models.JSONField('明细', default=dict, blank=True)
    correlation_id = models.UUIDField('关联追踪', null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = '资源操作日志'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.created_at} {self.get_action_display()}: {self.summary}'
