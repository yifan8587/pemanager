"""防火墙配置模型：以 nftables (inet 家族) 表 `pemanager` 为容器。"""
from __future__ import annotations

import ipaddress
import uuid

from django.core.exceptions import ValidationError
from django.db import models


class FirewallRule(models.Model):
    class Chain(models.TextChoices):
        INPUT = 'input', 'INPUT (本机入向)'
        OUTPUT = 'output', 'OUTPUT (本机出向)'
        FORWARD = 'forward', 'FORWARD (转发)'

    class Action(models.TextChoices):
        ACCEPT = 'accept', 'ACCEPT'
        DROP = 'drop', 'DROP'
        REJECT = 'reject', 'REJECT'
        LOG = 'log', 'LOG (记录后默认 accept)'

    class Protocol(models.TextChoices):
        ANY = 'any', 'ANY'
        TCP = 'tcp', 'TCP'
        UDP = 'udp', 'UDP'
        ICMP = 'icmp', 'ICMP/ICMPv6'

    class Family(models.TextChoices):
        IPV4 = 'ipv4', 'IPv4'
        IPV6 = 'ipv6', 'IPv6'
        BOTH = 'both', 'IPv4 + IPv6'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField('名称', max_length=128, unique=True)
    enabled = models.BooleanField('启用', default=True, db_index=True)
    chain = models.CharField('链', max_length=16, choices=Chain.choices, db_index=True)
    action = models.CharField('动作', max_length=16, choices=Action.choices, default=Action.ACCEPT)
    family = models.CharField('协议族', max_length=8, choices=Family.choices, default=Family.BOTH)
    protocol = models.CharField('L4 协议', max_length=8, choices=Protocol.choices, default=Protocol.ANY)
    src_cidr = models.CharField('源 CIDR', max_length=128, blank=True)
    dst_cidr = models.CharField('目的 CIDR', max_length=128, blank=True)
    src_port = models.CharField('源端口', max_length=64, blank=True, help_text='单个端口/区间(如 22 或 1000-2000)')
    dst_port = models.CharField('目的端口', max_length=64, blank=True)
    in_interface = models.CharField('入接口', max_length=128, blank=True)
    out_interface = models.CharField('出接口', max_length=128, blank=True)
    priority = models.IntegerField(
        '优先级',
        default=100,
        help_text='数值小者优先；同链内按 (priority, created_at) 排序生成规则',
    )
    remark = models.CharField('备注', max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '防火墙规则'
        verbose_name_plural = verbose_name
        ordering = ['chain', 'priority', 'created_at']

    def __str__(self):
        return f'{self.name} [{self.chain}/{self.action}]'

    def clean(self):
        super().clean()
        for field in ('src_cidr', 'dst_cidr'):
            v = (getattr(self, field) or '').strip()
            if v:
                try:
                    ipaddress.ip_network(v, strict=False)
                except ValueError as exc:
                    raise ValidationError({field: f'非法 CIDR: {exc}'}) from exc
        for field in ('src_port', 'dst_port'):
            v = (getattr(self, field) or '').strip()
            if not v:
                continue
            if self.protocol not in (self.Protocol.TCP, self.Protocol.UDP):
                raise ValidationError({field: '仅 TCP/UDP 可指定端口'})
            parts = v.split('-')
            try:
                ports = [int(p) for p in parts]
                if any(p < 0 or p > 65535 for p in ports) or len(parts) > 2:
                    raise ValueError('range')
            except ValueError as exc:
                raise ValidationError({field: f'端口非法: {v}'}) from exc
