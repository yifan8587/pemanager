"""运维管理：监控目标 + 采样表（延迟/丢包/抖动、接口流量）。"""
from __future__ import annotations

import uuid

from django.db import models


class MonitorTarget(models.Model):
    """ping / mtr 监控的目标地址。"""

    class Kind(models.TextChoices):
        PING = 'ping', 'Ping (ICMP)'
        MTR = 'mtr', 'MTR'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField('名称', max_length=128, unique=True)
    address = models.CharField('目标地址', max_length=255, help_text='IPv4/IPv6/主机名')
    kind = models.CharField('类型', max_length=16, choices=Kind.choices, default=Kind.PING, db_index=True)
    interval_sec = models.PositiveIntegerField('采样间隔(秒)', default=60)
    count = models.PositiveSmallIntegerField('单次报文数', default=5)
    source_interface = models.CharField('源接口(可选)', max_length=128, blank=True)
    enabled = models.BooleanField('启用', default=True, db_index=True)
    remark = models.CharField('备注', max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sampled_at = models.DateTimeField('最后采样', null=True, blank=True)

    class Meta:
        verbose_name = '监控目标'
        verbose_name_plural = verbose_name
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.address})'


class LatencySample(models.Model):
    """延迟/丢包/抖动样本（一次 ping/mtr 调用的统计结果）。"""

    id = models.BigAutoField(primary_key=True)
    target = models.ForeignKey(
        MonitorTarget,
        verbose_name='目标',
        on_delete=models.CASCADE,
        related_name='latency_samples',
    )
    ts = models.DateTimeField('时间', db_index=True)
    rtt_min_ms = models.FloatField('RTT min(ms)', null=True, blank=True)
    rtt_avg_ms = models.FloatField('RTT avg(ms)', null=True, blank=True)
    rtt_max_ms = models.FloatField('RTT max(ms)', null=True, blank=True)
    jitter_ms = models.FloatField('抖动(ms)', null=True, blank=True)
    loss_pct = models.FloatField('丢包率(%)', null=True, blank=True)
    packets_sent = models.PositiveIntegerField('发送', default=0)
    packets_recv = models.PositiveIntegerField('接收', default=0)
    ok = models.BooleanField('采样成功', default=True, db_index=True)
    detail = models.JSONField('明细', default=dict, blank=True)

    class Meta:
        verbose_name = '延迟样本'
        verbose_name_plural = verbose_name
        ordering = ['-ts']
        indexes = [
            models.Index(fields=['target', '-ts']),
        ]


class MonitorInterface(models.Model):
    """接口流量监控对象（哪些接口纳入周期性流量采样）。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    interface_name = models.CharField('接口', max_length=128, unique=True, db_index=True)
    enabled = models.BooleanField('启用', default=True, db_index=True)
    interval_sec = models.PositiveIntegerField('采样间隔(秒)', default=15)
    remark = models.CharField('备注', max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sampled_at = models.DateTimeField('最后采样', null=True, blank=True)

    class Meta:
        verbose_name = '接口流量监控对象'
        verbose_name_plural = verbose_name
        ordering = ['interface_name']

    def __str__(self):
        return f'monitor:{self.interface_name}'


class InterfaceTrafficSample(models.Model):
    """接口流量样本：用 /proc/net/dev 增量 + 时间窗计算 bps。"""

    id = models.BigAutoField(primary_key=True)
    interface_name = models.CharField('接口', max_length=128, db_index=True)
    ts = models.DateTimeField('时间', db_index=True)
    rx_bytes_total = models.BigIntegerField('累计 RX bytes', default=0)
    tx_bytes_total = models.BigIntegerField('累计 TX bytes', default=0)
    rx_packets_total = models.BigIntegerField('累计 RX 包', default=0)
    tx_packets_total = models.BigIntegerField('累计 TX 包', default=0)
    rx_bps = models.FloatField('RX bps（窗口）', null=True, blank=True)
    tx_bps = models.FloatField('TX bps（窗口）', null=True, blank=True)
    window_sec = models.FloatField('窗口(秒)', null=True, blank=True)

    class Meta:
        verbose_name = '接口流量样本'
        verbose_name_plural = verbose_name
        ordering = ['-ts']
        indexes = [
            models.Index(fields=['interface_name', '-ts']),
        ]


class _BucketChoices(models.TextChoices):
    MINUTE = 'minute', '分钟'
    HOUR = 'hour', '小时'
    DAY = 'day', '天'


class LatencyRollup(models.Model):
    """延迟/丢包按分钟/小时/天的聚合表（由调度器或管理命令生成）。"""

    Bucket = _BucketChoices

    id = models.BigAutoField(primary_key=True)
    target = models.ForeignKey(
        MonitorTarget,
        verbose_name='目标',
        on_delete=models.CASCADE,
        related_name='latency_rollups',
    )
    bucket_kind = models.CharField('粒度', max_length=8, choices=Bucket.choices, db_index=True)
    bucket_ts = models.DateTimeField('桶起点', db_index=True)
    rtt_min_ms = models.FloatField('RTT min(ms)', null=True, blank=True)
    rtt_avg_ms = models.FloatField('RTT avg(ms)', null=True, blank=True)
    rtt_max_ms = models.FloatField('RTT max(ms)', null=True, blank=True)
    jitter_ms = models.FloatField('抖动(ms)', null=True, blank=True)
    loss_pct = models.FloatField('丢包率(%)', null=True, blank=True)
    samples = models.PositiveIntegerField('样本数', default=0)
    ok_samples = models.PositiveIntegerField('成功样本', default=0)
    packets_sent = models.PositiveIntegerField('发送', default=0)
    packets_recv = models.PositiveIntegerField('接收', default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '延迟汇总'
        verbose_name_plural = verbose_name
        ordering = ['-bucket_ts']
        constraints = [
            models.UniqueConstraint(
                fields=['target', 'bucket_kind', 'bucket_ts'],
                name='uniq_latency_rollup_target_bucket',
            ),
        ]
        indexes = [
            models.Index(fields=['target', 'bucket_kind', '-bucket_ts']),
        ]

    def __str__(self):
        return f'{self.target.name} [{self.bucket_kind}] {self.bucket_ts}'


class InterfaceTrafficRollup(models.Model):
    """接口流量按分钟/小时/天的聚合表。"""

    Bucket = _BucketChoices

    id = models.BigAutoField(primary_key=True)
    interface_name = models.CharField('接口', max_length=128, db_index=True)
    bucket_kind = models.CharField('粒度', max_length=8, choices=Bucket.choices, db_index=True)
    bucket_ts = models.DateTimeField('桶起点', db_index=True)
    rx_bps_avg = models.FloatField('RX 平均 bps', null=True, blank=True)
    rx_bps_max = models.FloatField('RX 峰值 bps', null=True, blank=True)
    tx_bps_avg = models.FloatField('TX 平均 bps', null=True, blank=True)
    tx_bps_max = models.FloatField('TX 峰值 bps', null=True, blank=True)
    rx_bytes_delta = models.BigIntegerField('RX 增量 bytes', default=0)
    tx_bytes_delta = models.BigIntegerField('TX 增量 bytes', default=0)
    samples = models.PositiveIntegerField('样本数', default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '接口流量汇总'
        verbose_name_plural = verbose_name
        ordering = ['-bucket_ts']
        constraints = [
            models.UniqueConstraint(
                fields=['interface_name', 'bucket_kind', 'bucket_ts'],
                name='uniq_traffic_rollup_iface_bucket',
            ),
        ]
        indexes = [
            models.Index(fields=['interface_name', 'bucket_kind', '-bucket_ts']),
        ]

    def __str__(self):
        return f'{self.interface_name} [{self.bucket_kind}] {self.bucket_ts}'
