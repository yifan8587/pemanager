"""QoS 配置意图模型：基于 Linux tc（HTB / fq_codel / cake）。"""
from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models


class QoSPolicy(models.Model):
    """一条策略 = 绑定到某接口（出向）的根 qdisc + 一组分类规则。"""

    class Direction(models.TextChoices):
        EGRESS = 'egress', '出向 (egress)'
        INGRESS = 'ingress', '入向 (ingress / IFB)'

    class RootKind(models.TextChoices):
        HTB = 'htb', 'HTB (分级限速)'
        FQ_CODEL = 'fq_codel', 'fq_codel (公平队列)'
        CAKE = 'cake', 'CAKE (智能调度)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField('名称', max_length=128, unique=True)
    interface_name = models.CharField('接口名', max_length=128, db_index=True, help_text='Linux ifname (eth0, wg0...)')
    direction = models.CharField('方向', max_length=16, choices=Direction.choices, default=Direction.EGRESS)
    root_kind = models.CharField('根 qdisc', max_length=16, choices=RootKind.choices, default=RootKind.HTB)
    default_rate_mbps = models.PositiveIntegerField('默认带宽(Mbps)', default=100)
    default_ceil_mbps = models.PositiveIntegerField('默认峰值(Mbps)', default=100)
    enabled = models.BooleanField('启用', default=True, db_index=True)
    remark = models.CharField('备注', max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'QoS 策略'
        verbose_name_plural = verbose_name
        ordering = ['interface_name', 'name']

    def __str__(self):
        return f'{self.name} @{self.interface_name} ({self.get_root_kind_display()})'

    def clean(self):
        super().clean()
        if self.default_ceil_mbps and self.default_ceil_mbps < self.default_rate_mbps:
            raise ValidationError({'default_ceil_mbps': '峰值带宽不能小于默认带宽'})


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
