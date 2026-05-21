from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 各业务应用可实现模块 `<app>.integrations.resource_sync`，提供 on_resource_changed(event)
_APP_HOOKS: tuple[str, ...] = (
    'interfacemanage',
    'routemanage',
    'qosmanage',
    'firewallmanage',
    'operationmanage',
    'logmanage',
)


def notify_all(event: dict[str, Any]) -> None:
    """将资源变更事件通知各应用（存在钩子则调用，不存在则跳过）。"""
    for app_label in _APP_HOOKS:
        module_path = f'{app_label}.integrations.resource_sync'
        try:
            mod = importlib.import_module(module_path)
        except ImportError:
            continue
        handler = getattr(mod, 'on_resource_changed', None)
        if not callable(handler):
            continue
        try:
            handler(event)
        except Exception:  # noqa: BLE001 — 一个应用失败不影响其余
            logger.exception('资源同步钩子执行失败: %s', module_path)
