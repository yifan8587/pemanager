from __future__ import annotations

import uuid
from typing import Any

from resourcemanage.models import ResourceAllocationLog


def log_action(
    action: str,
    summary: str,
    *,
    detail: dict[str, Any] | None = None,
    actor: str = 'system',
    correlation_id: uuid.UUID | None = None,
) -> ResourceAllocationLog:
    return ResourceAllocationLog.objects.create(
        action=action,
        summary=summary,
        detail=detail or {},
        actor=actor,
        correlation_id=correlation_id,
    )
