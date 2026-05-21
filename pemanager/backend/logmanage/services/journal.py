"""调用 journalctl 读取系统日志。"""
from __future__ import annotations

import json
import shlex
from typing import Any

from django.conf import settings

from interfacemanage.services import subprocess_util


def _cmd_prefix() -> list[str]:
    raw = getattr(settings, 'LOGMANAGE_JOURNAL_CMD_PREFIX', '')
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str) and raw.strip():
        return shlex.split(raw)
    return []


_ALLOWED_PRIORITIES = {'emerg', 'alert', 'crit', 'err', 'warning', 'notice', 'info', 'debug'}


def query(
    *,
    unit: str | None = None,
    since: str | None = None,
    until: str | None = None,
    grep: str | None = None,
    priority: str | None = None,
    lines: int = 200,
) -> dict[str, Any]:
    """执行 `journalctl --output=json` 并解析。"""
    if not getattr(settings, 'LOGMANAGE_JOURNAL_ENABLED', True):
        return {'ok': False, 'error': 'journalctl 查询已关闭', 'entries': []}

    if lines < 1:
        lines = 1
    lines = min(lines, 2000)

    argv = ['journalctl', '--no-pager', '--output=json', '-n', str(lines)]
    if unit:
        u = unit.strip()
        if u:
            argv += ['-u', u]
    if since:
        argv += ['--since', since]
    if until:
        argv += ['--until', until]
    if priority and priority.lower() in _ALLOWED_PRIORITIES:
        argv += ['-p', priority.lower()]
    if grep:
        argv += ['--grep', grep]

    timeout = int(getattr(settings, 'LOGMANAGE_JOURNAL_TIMEOUT', 12))
    res = subprocess_util.run(_cmd_prefix() + argv, timeout=timeout)
    if not res.ok and not res.stdout:
        return {
            'ok': False,
            'error': res.stderr or 'journalctl 调用失败',
            'exit_code': res.exit_code,
            'entries': [],
        }

    entries: list[dict[str, Any]] = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts_us = obj.get('__REALTIME_TIMESTAMP')
        try:
            ts_iso = (
                __import__('datetime').datetime.utcfromtimestamp(int(ts_us) / 1_000_000).isoformat()
                if ts_us
                else None
            )
        except (TypeError, ValueError):
            ts_iso = None
        entries.append(
            {
                'ts_iso_utc': ts_iso,
                'unit': obj.get('_SYSTEMD_UNIT') or obj.get('UNIT'),
                'priority': obj.get('PRIORITY'),
                'hostname': obj.get('_HOSTNAME'),
                'pid': obj.get('_PID'),
                'identifier': obj.get('SYSLOG_IDENTIFIER') or obj.get('_COMM'),
                'message': obj.get('MESSAGE'),
            }
        )
    return {
        'ok': True,
        'count': len(entries),
        'entries': entries,
        'argv': argv,
    }


def list_units(*, pattern: str | None = None, limit: int = 200) -> dict[str, Any]:
    argv = ['systemctl', 'list-units', '--type=service', '--all', '--no-legend', '--plain']
    if pattern:
        argv += [pattern]
    res = subprocess_util.run(_cmd_prefix() + argv, timeout=8)
    units: list[dict[str, Any]] = []
    for line in (res.stdout or '').splitlines()[:limit]:
        parts = line.split(None, 4)
        if len(parts) >= 4:
            units.append(
                {'unit': parts[0], 'load': parts[1], 'active': parts[2], 'sub': parts[3], 'desc': parts[4] if len(parts) > 4 else ''}
            )
    return {'ok': res.ok, 'count': len(units), 'units': units, 'stderr': res.stderr}
