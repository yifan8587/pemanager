"""日志管理：应用级操作日志（通用入口）。"""
from __future__ import annotations

import uuid

from django.db import models


class AppOperationLog(models.Model):
    """跨模块的通用操作日志条目；各应用可通过 services.record(...) 写入。"""

    class Level(models.TextChoices):
        DEBUG = 'debug', 'DEBUG'
        INFO = 'info', 'INFO'
        WARNING = 'warning', 'WARNING'
        ERROR = 'error', 'ERROR'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField('时间', auto_now_add=True, db_index=True)
    app = models.CharField('应用', max_length=64, db_index=True)
    category = models.CharField('类别', max_length=64, db_index=True, blank=True)
    level = models.CharField('级别', max_length=16, choices=Level.choices, default=Level.INFO, db_index=True)
    actor = models.CharField('操作者', max_length=128, blank=True)
    summary = models.CharField('摘要', max_length=512)
    detail = models.JSONField('明细', default=dict, blank=True)
    correlation_id = models.UUIDField('关联追踪', null=True, blank=True, db_index=True)
    target = models.CharField('对象标识', max_length=255, blank=True, db_index=True)

    class Meta:
        verbose_name = '应用操作日志'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M:%S} [{self.app}] {self.summary}'
