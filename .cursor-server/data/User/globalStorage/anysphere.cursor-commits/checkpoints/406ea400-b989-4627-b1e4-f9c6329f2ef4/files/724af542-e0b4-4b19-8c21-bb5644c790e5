from __future__ import annotations

import uuid

from django.db import models


class NetworkSyncRun(models.Model):
    """一次「系统 → 数据库」全量对齐任务。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    started_at = models.DateTimeField('开始时间', auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField('结束时间', null=True, blank=True)
    success = models.BooleanField('成功', default=False, db_index=True)
    error_message = models.TextField('错误信息', blank=True)
    stats = models.JSONField('统计', default=dict, blank=True)

    class Meta:
        verbose_name = '网络配置同步任务'
        verbose_name_plural = verbose_name
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.started_at} ok={self.success}'


class NetplanFileRecord(models.Model):
    """Netplan 单文件的磁盘镜像（内容与解析结果），用于与 /etc/netplan 一致。"""

    path = models.CharField('文件路径', max_length=512, unique=True, db_index=True)
    file_sha256 = models.CharField('文件 SHA-256', max_length=64, db_index=True)
    size_bytes = models.PositiveIntegerField('字节数', default=0)
    mtime_epoch = models.FloatField('mtime(秒)', null=True, blank=True)
    raw_yaml = models.TextField('原始 YAML', blank=True)
    parsed = models.JSONField('解析结果', default=dict, blank=True)
    parse_error = models.TextField('解析错误', blank=True)
    last_run = models.ForeignKey(
        NetworkSyncRun,
        verbose_name='最近同步任务',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='netplan_files',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Netplan 文件快照'
        verbose_name_plural = verbose_name
        ordering = ['path']

    def __str__(self):
        return self.path


class NetworkInterfaceRecord(models.Model):
    """内核 + netplan + WireGuard 合并后的接口主数据，与实时 `unify` 输出一致。"""

    ifname = models.CharField('接口名', max_length=128, unique=True, db_index=True)
    ifindex = models.PositiveIntegerField('ifindex', null=True, blank=True, db_index=True)
    kind = models.CharField('类型', max_length=64, db_index=True)
    admin_up = models.BooleanField('管理 UP', null=True, blank=True)
    operstate = models.CharField('运行状态', max_length=32, blank=True)
    mtu = models.PositiveIntegerField('MTU', null=True, blank=True)
    mac = models.CharField('MAC', max_length=64, blank=True)
    addresses = models.JSONField('地址(ip -json addr 子树)', default=list, blank=True)
    linkinfo = models.JSONField('linkinfo', default=dict, blank=True)
    netplan = models.JSONField('Netplan 对齐信息', null=True, blank=True)
    wireguard = models.JSONField('WireGuard 快照', null=True, blank=True)
    ip_tunnel_show = models.JSONField('ip tunnel show 解析', null=True, blank=True)
    unified = models.JSONField('合并行(完整)', default=dict, blank=True)
    content_sha256 = models.CharField('内容校验', max_length=64, db_index=True)
    last_run = models.ForeignKey(
        NetworkSyncRun,
        verbose_name='最近同步任务',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='interfaces',
    )
    first_seen_at = models.DateTimeField('首次出现', auto_now_add=True)
    last_seen_at = models.DateTimeField('最近见到', auto_now=True)

    class Meta:
        verbose_name = '网络接口记录'
        verbose_name_plural = verbose_name
        ordering = ['ifindex', 'ifname']

    def __str__(self):
        return f'{self.ifname} ({self.kind})'


class DesiredTunnelConfig(models.Model):
    """前端录入、待落地到主机的隧道类接口意图（GRE / VXLAN / WireGuard），持久化在后端。"""

    class Kind(models.TextChoices):
        GRE = 'gre', 'GRE'
        VXLAN = 'vxlan', 'VXLAN'
        WIREGUARD = 'wireguard', 'WireGuard'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField('类型', max_length=32, choices=Kind.choices, db_index=True)
    ifname = models.CharField('接口名', max_length=128, unique=True, db_index=True)
    spec = models.JSONField('配置载荷', default=dict, blank=True, help_text='与 netplan / wg 对齐的结构化字段')
    remark = models.CharField('备注', max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '隧道接口意图配置'
        verbose_name_plural = verbose_name
        ordering = ['kind', 'ifname']

    def __str__(self):
        return f'{self.ifname} ({self.get_kind_display()})'
