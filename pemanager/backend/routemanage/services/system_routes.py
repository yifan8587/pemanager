"""解析 `ip -json route show` 供前端展示。"""
from __future__ import annotations

from typing import Any

from interfacemanage.services import iproute


def _norm_dst(v: Any) -> str:
    if v is None:
        return ''
    s = str(v).strip()
    return s


def _norm_gateway(v: Any) -> str | None:
    if v is None or v == '':
        return None
    return str(v).strip()


def _norm_int(v: Any) -> int | None:
    if v is None or v == '':
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def normalize_ip_route_rows(raw_routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in raw_routes:
        if not isinstance(r, dict):
            continue
        dst = _norm_dst(r.get('dst'))
        if not dst:
            continue
        row = {
            'dst': dst,
            'family': r.get('family'),
            'gateway': _norm_gateway(r.get('gateway')),
            'dev': (r.get('dev') or r.get('device') or '') or None,
            'prefsrc': _norm_gateway(r.get('prefsrc')),
            'metric': _norm_int(r.get('metric')),
            'table': _norm_int(r.get('table')) if r.get('table') is not None else None,
            'protocol': r.get('protocol'),
            'scope': r.get('scope'),
            'type': r.get('type'),
        }
        if row['table'] is None and r.get('table') not in (None, ''):
            row['table_label'] = str(r.get('table'))
        out.append(row)
    return out


def collect_system_routes() -> dict[str, Any]:
    snap = iproute.ip_route_show()
    routes = snap.get('routes') or []
    if not isinstance(routes, list):
        routes = []
    return {
        'ok': bool(snap.get('ok')),
        'exit_code': snap.get('exit_code'),
        'stderr': snap.get('stderr'),
        'routes': normalize_ip_route_rows(routes),
    }
