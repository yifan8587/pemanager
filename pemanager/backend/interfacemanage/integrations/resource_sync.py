from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def on_resource_changed(event: dict[str, Any]) -> None:
    """
    供 resourcemanage 等在资源变更后回调。
    可在此触发接口侧配置同步（设备/主机 netplan、`wg` 等），按项目扩展。
    """
    logger.info('interfacemanage: resource sync event kind=%s', event.get('kind'))
