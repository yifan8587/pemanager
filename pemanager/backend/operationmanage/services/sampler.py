"""一次性采样器：对所有启用的 MonitorTarget 执行 ping/mtr，并对接口做流量增量。"""
from __future__ import annotations

import time
from typing import Any

from django.utils import timezone

from operationmanage.models import (
    InterfaceTrafficSample,
    LatencySample,
    MonitorInterface,
    MonitorTarget,
)
from operationmanage.services import probes


def sample_one_target(target: MonitorTarget) -> LatencySample:
    if target.kind == MonitorTarget.Kind.MTR:
        r = probes.mtr(
            target.address,
            count=target.count,
            source=target.source_interface or None,
        )
        rtt_min = rtt_avg = rtt_max = None
        loss_pct = None
        if r.get('hops'):
            last = r['hops'][-1]
            rtt_avg = last.get('avg_ms')
            rtt_min = last.get('best_ms')
            rtt_max = last.get('worst_ms')
            loss_pct = last.get('loss_pct')
        sample = LatencySample.objects.create(
            target=target,
            ts=timezone.now(),
            rtt_min_ms=rtt_min,
            rtt_avg_ms=rtt_avg,
            rtt_max_ms=rtt_max,
            jitter_ms=None,
            loss_pct=loss_pct,
            packets_sent=target.count,
            packets_recv=target.count if rtt_avg is not None else 0,
            ok=bool(r.get('ok') and rtt_avg is not None),
            detail={'mtr_hops': r.get('hops'), 'stderr': r.get('stderr'), 'cmd': r.get('cmd')},
        )
    else:
        r = probes.ping(
            target.address,
            count=target.count,
            source=target.source_interface or None,
        )
        sample = LatencySample.objects.create(
            target=target,
            ts=timezone.now(),
            rtt_min_ms=r.get('rtt_min_ms'),
            rtt_avg_ms=r.get('rtt_avg_ms'),
            rtt_max_ms=r.get('rtt_max_ms'),
            jitter_ms=r.get('jitter_ms'),
            loss_pct=r.get('loss_pct'),
            packets_sent=int(r.get('packets_sent') or 0),
            packets_recv=int(r.get('packets_recv') or 0),
            ok=bool(r.get('ok')),
            detail={
                'cmd': r.get('cmd'),
                'exit_code': r.get('exit_code'),
                'stderr': (r.get('stderr') or '')[:1024],
                'stdout_tail': (r.get('stdout') or '')[-512:],
                'timed_out': r.get('timed_out'),
                'subprocess_timeout_sec': r.get('subprocess_timeout_sec'),
                'error': r.get('error'),
                'diagnosis': r.get('diagnosis'),
            },
        )
    target.last_sampled_at = timezone.now()
    target.save(update_fields=['last_sampled_at'])
    return sample


def sample_all_targets() -> dict[str, Any]:
    targets = list(MonitorTarget.objects.filter(enabled=True))
    out: list[dict[str, Any]] = []
    t0 = time.monotonic()
    for tgt in targets:
        try:
            s = sample_one_target(tgt)
            out.append({'target_id': str(tgt.id), 'name': tgt.name, 'ok': s.ok, 'rtt_avg_ms': s.rtt_avg_ms, 'loss_pct': s.loss_pct})
        except Exception as exc:  # noqa: BLE001
            out.append({'target_id': str(tgt.id), 'name': tgt.name, 'ok': False, 'error': str(exc)})
    return {'count': len(out), 'duration_ms': int((time.monotonic() - t0) * 1000), 'results': out}


def sample_interfaces(interfaces: list[str]) -> dict[str, Any]:
    """对一组接口分别做两次 /proc/net/dev 读取，记录 bps；落库为 InterfaceTrafficSample。"""
    results: list[dict[str, Any]] = []
    for ifname in interfaces:
        r = probes.traffic_live_window(ifname, window_sec=1.0)
        if not r.get('ok'):
            results.append({'interface': ifname, 'ok': False, 'error': r.get('error')})
            continue
        InterfaceTrafficSample.objects.create(
            interface_name=ifname,
            ts=timezone.now(),
            rx_bytes_total=r['rx_bytes_total'],
            tx_bytes_total=r['tx_bytes_total'],
            rx_packets_total=r['rx_packets_total'],
            tx_packets_total=r['tx_packets_total'],
            rx_bps=r['rx_bps'],
            tx_bps=r['tx_bps'],
            window_sec=r['window_sec'],
        )
        results.append({'interface': ifname, 'ok': True, 'rx_bps': r['rx_bps'], 'tx_bps': r['tx_bps']})
    return {'count': len(results), 'results': results}


# ---------- 单接口流量采样（scheduler 用，按 MonitorInterface 节拍调用） ----------

def sample_one_monitor_interface(mi: MonitorInterface) -> dict[str, Any]:
    r = probes.traffic_live_window(mi.interface_name, window_sec=1.0)
    if not r.get('ok'):
        return {'ok': False, 'interface': mi.interface_name, 'error': r.get('error')}
    InterfaceTrafficSample.objects.create(
        interface_name=mi.interface_name,
        ts=timezone.now(),
        rx_bytes_total=r['rx_bytes_total'],
        tx_bytes_total=r['tx_bytes_total'],
        rx_packets_total=r['rx_packets_total'],
        tx_packets_total=r['tx_packets_total'],
        rx_bps=r['rx_bps'],
        tx_bps=r['tx_bps'],
        window_sec=r['window_sec'],
    )
    mi.last_sampled_at = timezone.now()
    mi.save(update_fields=['last_sampled_at'])
    return {'ok': True, 'interface': mi.interface_name, 'rx_bps': r['rx_bps'], 'tx_bps': r['tx_bps']}
