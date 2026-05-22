"""QoS 配置意图模型：基于 Linux tc。单接口限速 + 冗余度，两种模板：
- HTB 单类限速（HTB rate=ceil + 子 fq_codel）  推荐：限速 + 抗拥塞
- TBF  纯硬限速（Token Bucket Filter）         简洁：单条命令
"""
from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models

from interfacemanage.models import NetworkInterfaceRecord
from resourcemanage.models import BandwidthAllocation, BandwidthPool, ResourceCustomer


class QoSPolicy(models.Model):
    """
    一条 QoS 策略 = 接口的总限速。可关联客户与资源管理中的「带宽池」；
    保存后会自动 upsert 一条 BandwidthAllocation
    （pool, interface_name）= effective_rate_mbps，使资源管理 / 接口管理实时可见限速值。
    """

    class Direction(models.TextChoices):
        EGRESS = 'egress', '出向 (egress)'
        INGRESS = 'ingress', '入向 (ingress / IFB)'

    class RootKind(models.TextChoices):
        HTB_SINGLE = 'htb', 'HTB 单类限速 (推荐：HTB+fq_codel)'
        TBF = 'tbf', 'TBF 极简硬限速 (Token Bucket)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField('名称', max_length=128, unique=True)
    interface_name = models.CharField('接口名', max_length=128, db_index=True, help_text='Linux ifname (eth0, wg0...)')
    linked_interface = models.ForeignKey(
        NetworkInterfaceRecord,
        verbose_name='关联接口记录',
        to_field='ifname',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='qos_policies',
        help_text='可选，绑定接口数据库镜像（与 interface_name 自动保持一致）',
    )
    customer = models.ForeignKey(
        ResourceCustomer,
        verbose_name='所属客户',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='qos_policies',
        help_text='可选，QoS 策略归属的客户；用于资源管理 / 接口详情联动展示',
    )
    linked_pool = models.ForeignKey(
        BandwidthPool,
        verbose_name='关联带宽池',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='qos_policies',
        help_text=(
            '可选；若指定，保存策略时会自动在该池中 upsert 一条 BandwidthAllocation'
            '（pool, interface_name）= default_ceil_mbps，使资源管理实时可见'
        ),
    )
    direction = models.CharField('方向', max_length=16, choices=Direction.choices, default=Direction.EGRESS)
    root_kind = models.CharField(
        '限速模板', max_length=16, choices=RootKind.choices, default=RootKind.HTB_SINGLE
    )

    # 用户配置的限速值
    rate_mbps = models.PositiveIntegerField(
        '限速 (Mbps)', default=10, help_text='接口总限速；保存后会同步到资源管理的带宽分配'
    )
    headroom_pct = models.PositiveSmallIntegerField(
        '冗余度 (%)',
        default=0,
        help_text='为应对突发与协议开销，从限速中预留的百分比；实际下发 = rate × (100 - headroom) / 100',
    )

    # TBF 参数
    burst_kb = models.PositiveSmallIntegerField(
        'TBF burst (KB)', default=32, help_text='TBF 令牌桶大小，太小会卡顿；约为速率的 1/100 ~ 1/50'
    )
    latency_ms = models.PositiveSmallIntegerField(
        'TBF 最大延迟 (ms)', default=50, help_text='TBF 队列里超过该延迟的包将被丢弃'
    )

    # 保留旧字段，兼容老数据（前端不再展示）
    default_rate_mbps = models.PositiveIntegerField('保留: default_rate_mbps', default=10)
    default_ceil_mbps = models.PositiveIntegerField('保留: default_ceil_mbps', default=10)

    enabled = models.BooleanField('启用', default=True, db_index=True)
    remark = models.CharField('备注', max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 同步联动的副产物，便于反向清理（不暴露给前端编辑）
    synced_bandwidth_allocation = models.ForeignKey(
        BandwidthAllocation,
        verbose_name='已同步的带宽分配',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='qos_origin',
        help_text='由 QoS 同步逻辑写入；策略删除时一并清理',
    )

    class Meta:
        verbose_name = 'QoS 策略'
        verbose_name_plural = verbose_name
        ordering = ['interface_name', 'name']

    def __str__(self):
        return f'{self.name} @{self.interface_name} ({self.get_root_kind_display()})'

    @property
    def effective_rate_mbps(self) -> int:
        """实际下发带宽（应用冗余度后）。最小 1 Mbps，避免 tc 拒绝。"""
        r = int(self.rate_mbps or 0)
        h = max(0, min(99, int(self.headroom_pct or 0)))
        eff = (r * (100 - h)) // 100
        return max(1, eff)

    def clean(self):
        super().clean()
        if self.rate_mbps is None or int(self.rate_mbps) <= 0:
            raise ValidationError({'rate_mbps': '限速必须 > 0 Mbps'})
        if self.headroom_pct is not None and not (0 <= int(self.headroom_pct) <= 99):
            raise ValidationError({'headroom_pct': '冗余度需在 0-99'})
        if self.root_kind == self.RootKind.TBF and int(self.burst_kb or 0) <= 0:
            raise ValidationError({'burst_kb': 'TBF burst 必须 > 0 KB'})
        # interface_name 与 linked_interface 保持一致
        if self.linked_interface_id and not (self.interface_name or '').strip():
            self.interface_name = self.linked_interface.ifname
        if self.linked_interface_id and self.linked_interface.ifname != self.interface_name:
            self.interface_name = self.linked_interface.ifname
        # 兼容字段：让旧字段始终与新字段一致
        self.default_rate_mbps = self.effective_rate_mbps
        self.default_ceil_mbps = self.effective_rate_mbps


class QoSRule(models.Model):
    """HTB 类规则（仅在 root_kind=htb 下生效）。"""

    class Match(models.TextChoices):
        SRC = 'src', '源 CIDR'
        DST = 'dst', '目的 CIDR'
        DSCP = 'dscp', 'DSCP'
        ANY = 'any', '任意'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy = models.ForeignKey(
        QoSPolicy,
        verbose_name='策略',
        on_delete=models.CASCADE,
        related_name='rules',
    )
    class_id = models.PositiveSmallIntegerField(
        '类 ID (minor)',
        help_text='HTB 类的 minor 号（>=10 推荐），同策略内唯一',
    )
    rate_mbps = models.PositiveIntegerField('保证带宽(Mbps)')
    ceil_mbps = models.PositiveIntegerField('峰值带宽(Mbps)')
    priority = models.PositiveSmallIntegerField('优先级 (1-7)', default=4)
    match_kind = models.CharField('匹配字段', max_length=8, choices=Match.choices, default=Match.DST)
    match_value = models.CharField('匹配值', max_length=128, blank=True, help_text='CIDR 或 DSCP，留空=any')
    remark = models.CharField('备注', max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'QoS 规则 (HTB 类)'
        verbose_name_plural = verbose_name
        ordering = ['policy', 'priority', 'class_id']
        constraints = [
            models.UniqueConstraint(fields=['policy', 'class_id'], name='uniq_qos_policy_classid'),
        ]

    def __str__(self):
        return f'{self.policy.name} class:{self.class_id} {self.match_kind}={self.match_value or "any"}'

    def clean(self):
        super().clean()
        if self.class_id < 10:
            raise ValidationError({'class_id': 'class_id 推荐 >=10'})
        if self.priority < 1 or self.priority > 7:
            raise ValidationError({'priority': '优先级须在 1-7'})
        if self.ceil_mbps < self.rate_mbps:
            raise ValidationError({'ceil_mbps': '峰值不能小于保证'})
        if self.match_kind in (self.Match.SRC, self.Match.DST) and self.match_value:
            import ipaddress
            try:
                ipaddress.ip_network(self.match_value.strip(), strict=False)
            except ValueError as exc:
                raise ValidationError({'match_value': f'CIDR 非法: {exc}'}) from exc
        if self.match_kind == self.Match.DSCP and self.match_value:
            v = self.match_value.strip()
            try:
                iv = int(v, 0)
                if iv < 0 or iv > 63:
                    raise ValueError('out of range')
            except ValueError as exc:
                raise ValidationError({'match_value': f'DSCP 须为 0-63 的整数: {exc}'}) from exc
