"""引导：保证至少存在一个 admin 账号，避免首次部署"门都进不去"。

可通过环境变量自定义：
- PEMANAGER_ADMIN_USERNAME (默认 admin)
- PEMANAGER_ADMIN_PASSWORD (默认 admin123，强烈建议首次登录后立刻修改)
- PEMANAGER_ADMIN_EMAIL    (默认 admin@pemanager.local)
"""
from __future__ import annotations

import os


def ensure_default_admin() -> None:
    # 延迟导入，避免 apps 未就绪时报错
    from django.db.utils import OperationalError, ProgrammingError

    from accountmanage.models import User

    try:
        exists = User.objects.filter(is_superuser=True).exists() or User.objects.filter(
            role=User.Role.ADMIN
        ).exists()
    except (OperationalError, ProgrammingError):
        # 首次 migrate 之前会发生
        return
    if exists:
        return
    username = os.environ.get('PEMANAGER_ADMIN_USERNAME', 'admin')
    password = os.environ.get('PEMANAGER_ADMIN_PASSWORD', 'admin123')
    email = os.environ.get('PEMANAGER_ADMIN_EMAIL', 'admin@pemanager.local')
    u = User.objects.create(
        username=username,
        email=email,
        role=User.Role.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    u.set_password(password)
    u.save()
