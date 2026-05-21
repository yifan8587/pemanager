from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from interfacemanage.models import NetplanFileRecord, NetworkInterfaceRecord, NetworkSyncRun
from interfacemanage.services import iproute, netplan, unify, wireguard


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode('utf-8')
    return _sha256_bytes(payload)


def _netplan_dirs_paths() -> list[Path]:
    dirs = getattr(settings, 'INTERFACEMANAGE_NETPLAN_DIRS', ['/etc/netplan'])
    out: list[Path] = []
    for d in dirs:
        p = Path(d)
        if p.is_dir():
            out.append(p)
    return out


def _persist_netplan_files(run: NetworkSyncRun) -> tuple[int, set[str]]:
    """扫描 netplan 目录，写入 NetplanFileRecord；返回 (写入条数, 路径集合)。"""
    seen: set[str] = set()
    count = 0
    for base in _netplan_dirs_paths():
        for path in sorted(base.glob('*.yaml')) + sorted(base.glob('*.yml')):
            rel = str(path)
            seen.add(rel)
            try:
                raw = path.read_bytes()
            except OSError as exc:
                NetplanFileRecord.objects.update_or_create(
                    path=rel,
                    defaults={
                        'file_sha256': '',
                        'size_bytes': 0,
                        'mtime_epoch': None,
                        'raw_yaml': '',
                        'parsed': {},
                        'parse_error': str(exc),
                        'last_run': run,
                    },
                )
                count += 1
                continue

            stat = path.stat()
            sha = _sha256_bytes(raw)
            text = raw.decode('utf-8', errors='replace')
            parsed: dict[str, Any] = {}
            err = ''
            try:
                import yaml

                parsed = yaml.safe_load(text) or {}
                if not isinstance(parsed, dict):
                    parsed = {'_raw_type': str(type(parsed).__name__)}
            except Exception as exc:  # noqa: BLE001
                err = f'YAML error: {exc}'
                parsed = {}

            NetplanFileRecord.objects.update_or_create(
                path=rel,
                defaults={
                    'file_sha256': sha,
                    'size_bytes': len(raw),
                    'mtime_epoch': float(stat.st_mtime),
                    'raw_yaml': text,
                    'parsed': parsed,
                    'parse_error': err,
                    'last_run': run,
                },
            )
            count += 1
    return count, seen


def sync_network_state_from_system() -> NetworkSyncRun:
    """
    从系统采集 netplan / ip / wg，与 unify 结果对齐写入数据库。
    - 接口：与当前 `ip link` 中出现的 ifname 集完全一致（多余行删除）。
    - Netplan 文件表：与当前扫描到的路径集完全一致（多余行删除）。
    """
    run = NetworkSyncRun.objects.create(success=False, stats={})
    t0 = time.monotonic()
    try:
        with transaction.atomic():
            np_bundle = netplan.load_netplan()
            kernel = iproute.collect_kernel_snapshot()
            mask_wg = not bool(
                getattr(settings, 'INTERFACEMANAGE_STORE_WG_SECRETS', False)
            )
            wg = wireguard.collect_wireguard_overview(mask=mask_wg)
            rows = unify.unify_interfaces(
                netplan_bundle=np_bundle, kernel=kernel, wireguard=wg
            )

            np_count, paths_seen = _persist_netplan_files(run)
            NetplanFileRecord.objects.exclude(path__in=paths_seen).delete()

            alive: set[str] = set()
            if_rows = 0
            for row in rows:
                name = str(row.get('ifname') or '')
                if not name:
                    continue
                alive.add(name)
                digest = _sha256_json(row)
                NetworkInterfaceRecord.objects.update_or_create(
                    ifname=name,
                    defaults={
                        'ifindex': row.get('ifindex'),
                        'kind': str(row.get('kind') or ''),
                        'admin_up': row.get('admin_up'),
                        'operstate': str(row.get('operstate') or ''),
                        'mtu': row.get('mtu'),
                        'mac': str(row.get('mac') or '') or '',
                        'addresses': row.get('addresses') or [],
                        'linkinfo': row.get('linkinfo') or {},
                        'netplan': row.get('netplan'),
                        'wireguard': row.get('wireguard'),
                        'ip_tunnel_show': row.get('ip_tunnel_show'),
                        'unified': row,
                        'content_sha256': digest,
                        'last_run': run,
                    },
                )
                if_rows += 1

            NetworkInterfaceRecord.objects.exclude(ifname__in=alive).delete()

        ms = int((time.monotonic() - t0) * 1000)
        run.success = True
        run.error_message = ''
        run.stats = {
            'duration_ms': ms,
            'interfaces': if_rows,
            'netplan_files': np_count,
            'netplan_parse_errors': len(np_bundle.get('errors') or []),
            'kernel_link_ok': (kernel.get('link') or {}).get('ok'),
            'wireguard_ok': wg.get('ok'),
            'mask_wireguard': mask_wg,
        }
    except Exception as exc:  # noqa: BLE001
        run.success = False
        run.error_message = str(exc)
        run.stats = {'duration_ms': int((time.monotonic() - t0) * 1000)}
    finally:
        run.finished_at = timezone.now()
        run.save(
            update_fields=[
                'finished_at',
                'success',
                'error_message',
                'stats',
            ]
        )
    return run


def compute_live_drifts() -> dict[str, Any]:
    """
    不写入数据库，计算当前系统与已持久化记录的差异（按 content_sha256）。
    """
    np_bundle = netplan.load_netplan()
    kernel = iproute.collect_kernel_snapshot()
    mask_wg = not bool(getattr(settings, 'INTERFACEMANAGE_STORE_WG_SECRETS', False))
    wg = wireguard.collect_wireguard_overview(mask=mask_wg)
    rows = unify.unify_interfaces(netplan_bundle=np_bundle, kernel=kernel, wireguard=wg)

    live: dict[str, str] = {}
    for row in rows:
        name = str(row.get('ifname') or '')
        if not name:
            continue
        live[name] = _sha256_json(row)

    db_map = dict(
        NetworkInterfaceRecord.objects.values_list('ifname', 'content_sha256')
    )

    missing_in_db = sorted(set(live.keys()) - set(db_map.keys()))
    stale = sorted(set(db_map.keys()) - set(live.keys()))
    changed = sorted(n for n in live if n in db_map and db_map[n] != live[n])
    ok = not (missing_in_db or stale or changed)

    return {
        'in_sync': ok,
        'missing_in_db': missing_in_db,
        'removed_on_system': stale,
        'changed': changed,
        'totals': {
            'live': len(live),
            'db': len(db_map),
        },
    }
