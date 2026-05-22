"""防火墙配置模型：
- FirewallRule：过滤规则（filter chains: input/output/forward）
- NATRule    ：NAT 规则（dnat/snat/masquerade/redirect）
- FirewallSettings：单例，存引擎（nft/iptables）与默认策略
"""
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


def _validate_port(field_name: str, value: str) -> None:
    v = (value or '').strip()
    if not v:
        return
    parts = v.split('-')
    try:
        ports = [int(p) for p in parts]
        if any(p < 0 or p > 65535 for p in ports) or len(parts) > 2:
            raise ValueError('range')
    except ValueError as exc:
        raise ValidationError({field_name: f'端口非法: {v}'}) from exc


def _validate_ip(field_name: str, value: str, *, want_host: bool = False) -> None:
    v = (value or '').strip()
    if not v:
        return
    try:
        if want_host:
            ipaddress.ip_address(v)
        else:
            ipaddress.ip_network(v, strict=False)
    except ValueError as exc:
        raise ValidationError({field_name: f'非法 IP/CIDR: {exc}'}) from exc


class NATRule(models.Model):
    """NAT 规则：DNAT / SNAT / MASQUERADE / REDIRECT。

    映射关系（nftables 用法 vs iptables 用法）：
    - DNAT       (prerouting)  : 把命中流量目的改写为 `to_ip[:to_port]`
    - SNAT       (postrouting) : 把源改写为 `to_ip`（需要静态出口 IP）
    - MASQUERADE (postrouting) : 出接口动态源改写（推荐拨号 / DHCP 出口）
    - REDIRECT   (prerouting)  : 重定向到本机端口（透明代理）
    """

    class Kind(models.TextChoices):
        DNAT = 'dnat', 'DNAT (目标地址转换)'
        SNAT = 'snat', 'SNAT (源地址转换)'
        MASQ = 'masquerade', 'MASQUERADE (动态源 NAT)'
        REDIRECT = 'redirect', 'REDIRECT (重定向本机端口)'

    class Protocol(models.TextChoices):
        ANY = 'any', 'ANY'
        TCP = 'tcp', 'TCP'
        UDP = 'udp', 'UDP'

    class Family(models.TextChoices):
        IPV4 = 'ipv4', 'IPv4'
        IPV6 = 'ipv6', 'IPv6'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField('名称', max_length=128, unique=True)
    enabled = models.BooleanField('启用', default=True, db_index=True)
    kind = models.CharField('类型', max_length=16, choices=Kind.choices, db_index=True)
    family = models.CharField('协议族', max_length=8, choices=Family.choices, default=Family.IPV4)
    protocol = models.CharField('L4 协议', max_length=8, choices=Protocol.choices, default=Protocol.ANY)

    in_interface = models.CharField('入接口 (iifname)', max_length=128, blank=True)
    out_interface = models.CharField('出接口 (oifname)', max_length=128, blank=True)
    src_cidr = models.CharField('源 CIDR', max_length=128, blank=True)
    dst_cidr = models.CharField('目的 CIDR', max_length=128, blank=True)
    dst_port = models.CharField('目的端口', max_length=64, blank=True, help_text='单个端口或 1000-2000')

    to_ip = models.CharField('目标 IP', max_length=128, blank=True, help_text='DNAT/SNAT 必填')
    to_port = models.CharField('目标端口', max_length=64, blank=True, help_text='DNAT/REDIRECT 选填；端口或 1000-2000')

    priority = models.IntegerField('优先级', default=100, help_text='数值小者优先')
    remark = models.CharField('备注', max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'NAT 规则'
        verbose_name_plural = verbose_name
        ordering = ['kind', 'priority', 'created_at']

    def __str__(self):
        return f'{self.name} [{self.kind}]'

    def clean(self):
        super().clean()
        _validate_ip('src_cidr', self.src_cidr)
        _validate_ip('dst_cidr', self.dst_cidr)
        if self.to_ip:
            _validate_ip('to_ip', self.to_ip, want_host=True)
        _validate_port('dst_port', self.dst_port)
        _validate_port('to_port', self.to_port)
        if self.dst_port and self.protocol not in (self.Protocol.TCP, self.Protocol.UDP):
            raise ValidationError({'dst_port': '仅 TCP/UDP 可指定端口'})

        if self.kind == self.Kind.DNAT:
            if not (self.to_ip or self.to_port):
                raise ValidationError({'to_ip': 'DNAT 至少要指定 to_ip 或 to_port'})
        elif self.kind == self.Kind.SNAT:
            if not self.to_ip:
                raise ValidationError({'to_ip': 'SNAT 必须指定 to_ip'})
            if not self.out_interface:
                # 提示：通常需要 oif 配合，否则会作用于所有出口
                pass
        elif self.kind == self.Kind.MASQ:
            if not self.out_interface:
                raise ValidationError({'out_interface': 'MASQUERADE 必须指定出接口 (oifname)'})
        elif self.kind == self.Kind.REDIRECT:
            if not self.to_port:
                raise ValidationError({'to_port': 'REDIRECT 必须指定 to_port（本机端口）'})


class FirewallSettings(models.Model):
    """单例（pk=1）：保存当前使用的防火墙引擎与默认策略。"""

    class Engine(models.TextChoices):
        NFT = 'nft', 'nftables (nft)'
        IPTABLES = 'iptables', 'iptables (iptables-restore)'

    class Policy(models.TextChoices):
        ACCEPT = 'accept', 'ACCEPT'
        DROP = 'drop', 'DROP'

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    engine = models.CharField('引擎', max_length=16, choices=Engine.choices, default=Engine.NFT)
    policy_input = models.CharField('默认 input 策略', max_length=8, choices=Policy.choices, default=Policy.ACCEPT)
    policy_output = models.CharField('默认 output 策略', max_length=8, choices=Policy.choices, default=Policy.ACCEPT)
    policy_forward = models.CharField('默认 forward 策略', max_length=8, choices=Policy.choices, default=Policy.ACCEPT)
    last_apply_at = models.DateTimeField('最近下发时间', null=True, blank=True)
    last_apply_ok = models.BooleanField('最近下发是否成功', default=False)
    last_apply_summary = models.CharField('最近下发摘要', max_length=512, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '防火墙设置'
        verbose_name_plural = verbose_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> 'FirewallSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
