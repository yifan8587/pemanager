"""ping / mtr / 接口流量采样实现。"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from interfacemanage.services import subprocess_util

# ----- ping -----

_PING_STATS_RE = re.compile(
    r'(\d+)\s+packets transmitted,\s*(\d+)\s+(?:packets\s+)?received',
    re.IGNORECASE,
)
_PING_LOSS_RE = re.compile(r'(\d+(?:\.\d+)?)\%\s*packet loss', re.IGNORECASE)
_PING_RTT_RE = re.compile(
    r'(?:rtt|round-trip)\s+min/avg/max(?:/m[a-z]+)?\s*=\s*([\d\.]+)/([\d\.]+)/([\d\.]+)(?:/([\d\.]+))?',
    re.IGNORECASE,
)


def ping(address: str, *, count: int = 5, timeout: int = 10, source: str | None = None) -> dict[str, Any]:
    address = (address or '').strip()
    if not address:
        return {'ok': False, 'error': 'address 为空'}
    cnt = max(1, min(int(count), 64))
    is_v6 = ':' in address
    cmd = ['ping6'] if is_v6 else ['ping']
    cmd += ['-n', '-q', '-c', str(cnt), '-W', str(max(1, timeout // cnt))]
    if source:
        cmd += ['-I', source]
    cmd += [address]

    res = subprocess_util.run(cmd, timeout=timeout + 2)
    out = res.stdout or ''
    sent = recv = 0
    loss_pct = 100.0
    rtt_min = rtt_avg = rtt_max = jitter = None
    m = _PING_STATS_RE.search(out)
    if m:
        sent = int(m.group(1))
        recv = int(m.group(2))
    m = _PING_LOSS_RE.search(out)
    if m:
        loss_pct = float(m.group(1))
    m = _PING_RTT_RE.search(out)
    if m:
        rtt_min = float(m.group(1))
        rtt_avg = float(m.group(2))
        rtt_max = float(m.group(3))
        jitter = float(m.group(4)) if m.group(4) else None
    return {
        'ok': res.ok and recv > 0,
        'cmd': ' '.join(cmd),
        'exit_code': res.exit_code,
        'stderr': res.stderr,
        'stdout': out,
        'packets_sent': sent,
        'packets_recv': recv,
        'loss_pct': loss_pct,
        'rtt_min_ms': rtt_min,
        'rtt_avg_ms': rtt_avg,
        'rtt_max_ms': rtt_max,
        'jitter_ms': jitter,
    }


# ----- mtr -----

def mtr(address: str, *, count: int = 5, timeout: int = 15, source: str | None = None) -> dict[str, Any]:
    address = (address or '').strip()
    if not address:
        return {'ok': False, 'error': 'address 为空'}
    cnt = max(1, min(int(count), 30))
    cmd = ['mtr', '-n', '-r', '-c', str(cnt), '--json']
    if source:
        cmd += ['-a', source]
    cmd += [address]
    res = subprocess_util.run(cmd, timeout=timeout + 4)
    hops: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    if res.ok and res.stdout:
        try:
            data = json.loads(res.stdout)
            report = data.get('report') or {}
            for h in report.get('hubs') or []:
                hops.append(
                    {
                        'count': h.get('count'),
                        'host': h.get('host'),
                        'loss_pct': h.get('Loss%'),
                        'snt': h.get('Snt'),
                        'last_ms': h.get('Last'),
                        'avg_ms': h.get('Avg'),
                        'best_ms': h.get('Best'),
                        'worst_ms': h.get('Wrst'),
                        'stdev_ms': h.get('StDev'),
                    }
                )
            if hops:
                last = hops[-1]
                summary = {
                    'last_hop_host': last.get('host'),
                    'last_hop_avg_ms': last.get('avg_ms'),
                    'last_hop_loss_pct': last.get('loss_pct'),
                }
        except json.JSONDecodeError:
            pass
    return {
        'ok': res.ok,
        'cmd': ' '.join(cmd),
        'exit_code': res.exit_code,
        'stderr': res.stderr,
        'hops': hops,
        'summary': summary,
        'raw': res.stdout if not hops else '',
    }


# ----- /proc/net/dev 流量快照 -----

_PROC_NET_DEV = '/proc/net/dev'


def _read_proc_net_dev() -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    try:
        with open(_PROC_NET_DEV, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i < 2:
                    continue
                if ':' not in line:
                    continue
                name, rest = line.split(':', 1)
                name = name.strip()
                parts = rest.split()
                if len(parts) < 16:
                    continue
                rx_bytes, rx_pkts = int(parts[0]), int(parts[1])
                tx_bytes, tx_pkts = int(parts[8]), int(parts[9])
                out[name] = {
                    'rx_bytes': rx_bytes,
                    'rx_packets': rx_pkts,
                    'tx_bytes': tx_bytes,
                    'tx_packets': tx_pkts,
                }
    except OSError as exc:
        out['__error__'] = {'rx_bytes': -1, 'rx_packets': -1, 'tx_bytes': -1, 'tx_packets': -1, 'err': str(exc)}  # type: ignore[dict-item]
    return out


def proc_net_dev_all() -> dict[str, Any]:
    return {'snapshot': _read_proc_net_dev(), 'ts_epoch': time.time()}


def traffic_delta_from(
    interface_name: str,
    *,
    prev_snapshot: dict[str, int] | None,
    prev_ts: float | None,
) -> dict[str, Any]:
    """基于调用方提供的上次快照计算增量；不在内部 sleep。"""
    iface = (interface_name or '').strip()
    if not iface:
        return {'ok': False, 'error': '缺少接口名'}
    cur = _read_proc_net_dev().get(iface)
    cur_ts = time.time()
    if not cur:
        return {'ok': False, 'error': f'接口 {iface} 未出现在 /proc/net/dev'}
    if not prev_snapshot or prev_ts is None:
        return {
            'ok': True,
            'baseline_only': True,
            'interface': iface,
            'rx_bytes_total': cur['rx_bytes'],
            'tx_bytes_total': cur['tx_bytes'],
            'rx_packets_total': cur['rx_packets'],
            'tx_packets_total': cur['tx_packets'],
            'rx_bps': None,
            'tx_bps': None,
            'window_sec': None,
            'current_snapshot': cur,
            'current_ts': cur_ts,
        }
    dt = max(cur_ts - prev_ts, 1e-3)
    rx_bytes_delta = max(0, cur['rx_bytes'] - prev_snapshot.get('rx_bytes', cur['rx_bytes']))
    tx_bytes_delta = max(0, cur['tx_bytes'] - prev_snapshot.get('tx_bytes', cur['tx_bytes']))
    return {
        'ok': True,
        'baseline_only': False,
        'interface': iface,
        'rx_bytes_total': cur['rx_bytes'],
        'tx_bytes_total': cur['tx_bytes'],
        'rx_packets_total': cur['rx_packets'],
        'tx_packets_total': cur['tx_packets'],
        'rx_bytes_delta': rx_bytes_delta,
        'tx_bytes_delta': tx_bytes_delta,
        'rx_bps': rx_bytes_delta * 8 / dt,
        'tx_bps': tx_bytes_delta * 8 / dt,
        'window_sec': dt,
        'current_snapshot': cur,
        'current_ts': cur_ts,
    }


def traffic_live_window(interface_name: str, *, window_sec: float = 1.0) -> dict[str, Any]:
    """同进程内做两次 /proc/net/dev 读取，返回 window 内 bps。"""
    iface = (interface_name or '').strip()
    if not iface:
        return {'ok': False, 'error': '缺少接口名'}
    s1 = _read_proc_net_dev().get(iface)
    if not s1:
        return {'ok': False, 'error': f'接口 {iface} 未在 /proc/net/dev 中'}
    t1 = time.time()
    time.sleep(max(0.2, float(window_sec)))
    s2 = _read_proc_net_dev().get(iface)
    t2 = time.time()
    if not s2:
        return {'ok': False, 'error': f'接口 {iface} 在第二次采样消失'}
    dt = max(t2 - t1, 1e-3)
    rx_bps = max(0.0, (s2['rx_bytes'] - s1['rx_bytes']) * 8 / dt)
    tx_bps = max(0.0, (s2['tx_bytes'] - s1['tx_bytes']) * 8 / dt)
    return {
        'ok': True,
        'interface': iface,
        'window_sec': dt,
        'rx_bytes_total': s2['rx_bytes'],
        'tx_bytes_total': s2['tx_bytes'],
        'rx_packets_total': s2['rx_packets'],
        'tx_packets_total': s2['tx_packets'],
        'rx_bps': rx_bps,
        'tx_bps': tx_bps,
    }
