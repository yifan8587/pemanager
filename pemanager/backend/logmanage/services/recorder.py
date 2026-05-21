"""统一的日志写入入口；其他模块可调用 record(...) 写入 AppOperationLog。"""
from __future__ import annotations

from typing import Any

from logmanage.models import AppOperationLog


def record(
    *,
    app: str,
    summary: str,
    level: str = AppOperationLog.Level.INFO,
    category: str = '',
    actor: str = '',
    detail: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    target: str = '',
) -> AppOperationLog:
    return AppOperationLog.objects.create(
        app=app,
        summary=summary[:512],
        level=level,
        category=category[:64],
        actor=actor[:128],
        detail=detail or {},
        correlation_id=correlation_id or None,
        target=target[:255],
    )
