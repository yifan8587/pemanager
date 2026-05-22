"""解析 `ip -json route show` 与 `ip -json rule show` 供前端展示。"""
from __future__ import annotations

import json
from typing import Any

from interfacemanage.services import iproute, subprocess_util


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


def collect_system_routes(*, table: str | None = None) -> dict[str, Any]:
    """读取内核路由表。table='all' 时读取所有路由表（含 local/main/<custom>）。"""
    if table and table.lower() not in {'', 'main'}:
        res = subprocess_util.run(['ip', '-json', 'route', 'show', 'table', table])
        ok = res.ok
        routes_raw = []
        if ok:
            try:
                parsed = json.loads(res.stdout or '[]')
                routes_raw = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                ok = False
        return {
            'ok': ok,
            'exit_code': res.exit_code,
            'stderr': res.stderr,
            'table': table,
            'routes': normalize_ip_route_rows(routes_raw),
        }

    snap = iproute.ip_route_show()
    routes = snap.get('routes') or []
    if not isinstance(routes, list):
        routes = []
    return {
        'ok': bool(snap.get('ok')),
        'exit_code': snap.get('exit_code'),
        'stderr': snap.get('stderr'),
        'table': table or 'main',
        'routes': normalize_ip_route_rows(routes),
    }


def _norm_rule_row(r: dict[str, Any]) -> dict[str, Any]:
    """归一化 `ip -json rule show` 的字段。"""
    if not isinstance(r, dict):
        return {}
    out = {
        'priority': _norm_int(r.get('priority')),
        'family': r.get('family') or ('inet6' if (r.get('protocol') == 'ipv6') else 'inet'),
        'from': r.get('src') or r.get('from'),
        'to': r.get('dst') or r.get('to'),
        'iif': r.get('iif'),
        'oif': r.get('oif'),
        'fwmark': r.get('fwmark'),
        'tos': r.get('tos'),
        'table': r.get('table'),
        'protocol': r.get('protocol'),
        'action': r.get('action') or ('lookup' if r.get('table') else None),
        'invert': bool(r.get('not')),
        'suppress_prefixlength': _norm_int(r.get('suppress_prefixlength')),
    }
    return out


def collect_system_rules(*, family: str | None = None) -> dict[str, Any]:
    """读取内核 ip rule 列表；family 可选 inet | inet6 | None(都返回)。"""
    out: list[dict[str, Any]] = []
    stderr_join: list[str] = []
    ok_join = True
    families = ['inet', 'inet6'] if not family else [family]
    for fam in families:
        argv = ['ip', '-json']
        if fam == 'inet6':
            argv.append('-6')
        elif fam == 'inet':
            argv.append('-4')
        argv += ['rule', 'show']
        res = subprocess_util.run(argv)
        if not res.ok:
            ok_join = False
            stderr_join.append(res.stderr)
            continue
        try:
            data = json.loads(res.stdout or '[]')
        except json.JSONDecodeError as exc:
            ok_join = False
            stderr_join.append(f'json decode failed for {fam}: {exc}')
            continue
        for row in data if isinstance(data, list) else []:
            n = _norm_rule_row(row)
            n['family'] = fam
            out.append(n)
    out.sort(key=lambda r: (r.get('family') or '', r.get('priority') if r.get('priority') is not None else -1))
    return {
        'ok': ok_join,
        'stderr': '\n'.join(s for s in stderr_join if s),
        'rules': out,
    }
