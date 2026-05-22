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


DEFAULT_PING_PER_PACKET_WAIT_SEC = 3
DEFAULT_PING_INTERVAL_SEC = 1.0


def _expected_ping_runtime_sec(count: int, per_packet_wait_sec: int, interval_sec: float) -> float:
    """ping 真实耗时上界估计：前 (count-1) 个包按 interval 间隔发出，最后一个包等待 W。"""
    cnt = max(1, int(count))
    return max(0.0, (cnt - 1) * interval_sec) + max(1, int(per_packet_wait_sec))


def ping(
    address: str,
    *,
    count: int = 5,
    timeout: int | None = None,
    source: str | None = None,
    per_packet_wait_sec: int = DEFAULT_PING_PER_PACKET_WAIT_SEC,
    interval_sec: float = DEFAULT_PING_INTERVAL_SEC,
) -> dict[str, Any]:
    """运行系统 ping 并解析统计。

    特性：
    - per_packet_wait_sec：单包等待上限（-W），与 count 无关；默认 3s 适配大多数链路。
    - interval_sec：发包间隔（-i），默认 1s。
    - subprocess timeout：自动按 `(count-1)*interval + W + 3` 计算；如调用方显式传 timeout，
      取 `max(自动, 显式)` 以避免命令被 kill 导致 stdout 丢失从而误报 100% 丢包。
    - 对 IPv6 使用 `ping -6`（兼容老系统的 `ping6` 兜底）。
    - `loss_pct` 与 `packets_*` 仅在能解析到统计行时填写；解析失败时 loss_pct 留空，避免误报。
    """
    address = (address or '').strip()
    if not address:
        return {'ok': False, 'error': 'address 为空'}
    cnt = max(1, min(int(count), 200))
    per_w = max(1, int(per_packet_wait_sec))
    iv = max(0.2, float(interval_sec))

    is_v6 = ':' in address
    cmd: list[str] = ['ping', '-6' if is_v6 else '-4', '-n', '-q',
                      '-c', str(cnt), '-W', str(per_w), '-i', str(iv)]
    if source:
        cmd += ['-I', source]
    cmd.append(address)

    expected = _expected_ping_runtime_sec(cnt, per_w, iv)
    effective_timeout = int(max(timeout or 0, expected + 3, 6))

    res = subprocess_util.run(cmd, timeout=effective_timeout)
    # 老系统兼容：找不到 `ping -6`，退回 `ping6 ...`
    if is_v6 and res.exit_code == -1 and 'not found' in (res.stderr or '').lower():
        cmd_fallback = ['ping6', '-n', '-q', '-c', str(cnt), '-W', str(per_w), '-i', str(iv)]
        if source:
            cmd_fallback += ['-I', source]
        cmd_fallback.append(address)
        res = subprocess_util.run(cmd_fallback, timeout=effective_timeout)
        cmd = cmd_fallback

    out = res.stdout or ''
    timed_out = (res.exit_code == -1 and 'timeout' in (res.stderr or '').lower())
    sent = recv = 0
    loss_pct: float | None = None
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

    # 若 stdout 有统计但 loss 未被显式解析（极少见），从 sent/recv 反推
    if loss_pct is None and sent > 0:
        loss_pct = round(max(0.0, (sent - recv) / sent * 100.0), 3)

    error_text = ''
    diagnosis = ''
    if timed_out:
        error_text = f'ping 超时（subprocess timeout={effective_timeout}s）'
        diagnosis = 'subprocess_timeout'
    elif res.exit_code == -1:
        error_text = (res.stderr or '').strip() or 'ping 启动失败'
        diagnosis = 'binary_error'
    elif sent == 0 and recv == 0 and not out:
        error_text = (res.stderr or '').strip() or 'ping 无统计输出'
        diagnosis = 'no_output'
    elif sent > 0 and recv == 0:
        # 命令成功执行但 100% 丢包：通常是网络层问题，不是程序问题
        error_text = (
            f'目标无 ICMP 回应：{sent}/{sent} 全部丢包；'
            '可能原因：目标地址不响应、被中间链路过滤、源接口路由不通'
        )
        diagnosis = 'all_packets_lost'
    elif sent > 0 and recv < sent:
        diagnosis = 'partial_loss'
    elif sent > 0 and recv == sent:
        diagnosis = 'ok'

    # ok 判定：以"收到 >=1 个回包"为准；returncode 在部分丢包时 = 1 也视为 ok
    ok = recv > 0

    return {
        'ok': ok,
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
        'timed_out': timed_out,
        'subprocess_timeout_sec': effective_timeout,
        'error': error_text,
        'diagnosis': diagnosis,
    }


# ----- mtr -----

def mtr(address: str, *, count: int = 5, timeout: int | None = None, source: str | None = None) -> dict[str, Any]:
    address = (address or '').strip()
    if not address:
        return {'ok': False, 'error': 'address 为空'}
    cnt = max(1, min(int(count), 200))
    cmd = ['mtr', '-n', '-r', '-c', str(cnt), '--json']
    if source:
        cmd += ['-a', source]
    cmd += [address]
    # mtr 至少每个包等 1 秒发送，路径长时还会做多跳探测；按 count 估算 + 余量
    expected = max(8, cnt * 1.5 + 5)
    effective_timeout = int(max(timeout or 0, expected))
    res = subprocess_util.run(cmd, timeout=effective_timeout)
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


# ----- 一站式网络诊断 -----

_IP_ROUTE_GET_RE = re.compile(
    r'^(?P<dst>\S+)\s+(?:via\s+(?P<gw>\S+)\s+)?dev\s+(?P<dev>\S+)(?:\s+src\s+(?P<src>\S+))?',
)


def _parse_ip_route_get(out: str) -> dict[str, str]:
    """解析 `ip route get <addr>` 第一行，提取 via / dev / src。"""
    for line in (out or '').splitlines():
        line = line.strip()
        if not line:
            continue
        m = _IP_ROUTE_GET_RE.match(line)
        if m:
            return {
                'dst': m.group('dst') or '',
                'via': m.group('gw') or '',
                'dev': m.group('dev') or '',
                'src': m.group('src') or '',
            }
    return {}


def network_diagnose(
    address: str,
    *,
    source: str | None = None,
    ping_count: int = 5,
    do_traceroute: bool = False,
    traceroute_max_hops: int = 10,
) -> dict[str, Any]:
    """一次跑完：ip route get / 推断源 IP / ping / 可选 traceroute。

    设计目标：让用户在前端"诊断"按钮一键拿到全部排错信息。
    """
    address = (address or '').strip()
    if not address:
        return {'ok': False, 'error': 'address 为空'}
    is_v6 = ':' in address

    # 1) ip route get
    route_cmd = ['ip', '-6', 'route', 'get', address] if is_v6 else ['ip', '-4', 'route', 'get', address]
    route_res = subprocess_util.run(route_cmd, timeout=5)
    route_info = _parse_ip_route_get(route_res.stdout)

    # 2) ping
    ping_res = ping(address, count=ping_count, source=source or None)

    # 3) traceroute（可选；默认关闭以免太慢）
    trace_block: dict[str, Any] | None = None
    if do_traceroute:
        trace_cmd = ['traceroute', '-n', '-w', '2', '-q', '1', '-m', str(max(1, int(traceroute_max_hops)))]
        if is_v6:
            trace_cmd.append('-6')
        if source:
            trace_cmd += ['-s', source] if not source.startswith('eth') else ['-i', source]
        trace_cmd.append(address)
        trace_res = subprocess_util.run(trace_cmd, timeout=max(15, traceroute_max_hops * 4))
        trace_block = {
            'cmd': ' '.join(trace_cmd),
            'exit_code': trace_res.exit_code,
            'stdout': trace_res.stdout,
            'stderr': trace_res.stderr,
        }

    return {
        'ok': bool(ping_res.get('ok')),
        'address': address,
        'source_input': source or '',
        'route': {
            'cmd': ' '.join(route_cmd),
            'parsed': route_info,
            'stdout': route_res.stdout,
            'stderr': route_res.stderr,
            'exit_code': route_res.exit_code,
        },
        'ping': ping_res,
        'traceroute': trace_block,
        'summary': _diagnose_summary(ping_res, route_info),
    }


def _diagnose_summary(ping_res: dict[str, Any], route_info: dict[str, str]) -> dict[str, Any]:
    """根据 ping 与 route 结果生成"用户友好的"摘要文本和建议。"""
    diag = ping_res.get('diagnosis') or ''
    recv = int(ping_res.get('packets_recv') or 0)
    sent = int(ping_res.get('packets_sent') or 0)
    loss = ping_res.get('loss_pct')
    avg = ping_res.get('rtt_avg_ms')
    via = route_info.get('via') or '(直连，无网关)'
    dev = route_info.get('dev') or '(未知接口)'
    src = route_info.get('src') or '(未确定源 IP)'

    if diag == 'ok':
        title = '链路正常'
        detail = f'{recv}/{sent} 回包，avg={avg} ms；路径：dev={dev} via={via} src={src}'
        hint = ''
    elif diag == 'partial_loss':
        title = f'有丢包：{recv}/{sent} 回包，loss={loss}%'
        detail = f'路径：dev={dev} via={via} src={src}'
        hint = '可重新采样几次确认；如长期存在丢包，检查上游/中间链路。'
    elif diag == 'all_packets_lost':
        title = '目标 100% 无回应'
        detail = f'命令执行成功，但 {sent}/{sent} 全丢包。路径：dev={dev} via={via} src={src}'
        hint = (
            '常见原因：① 目标地址本身禁 ICMP（试 8.8.8.8）；'
            '② 中间链路过滤 ICMP；'
            '③ 源接口路由不通；'
            '④ 出口防火墙拦截。'
            '可在终端跑 `ping -4 -c 5 ' + (ping_res.get("cmd", "").split(" ")[-1]) + '` 复现。'
        )
    elif diag == 'subprocess_timeout':
        title = 'ping 超时'
        detail = f'subprocess 超时 {ping_res.get("subprocess_timeout_sec")}s 被强杀'
        hint = '减小 count，或检查目标是否长时间无回应。'
    elif diag == 'binary_error':
        title = 'ping 启动失败'
        detail = ping_res.get('stderr') or ping_res.get('error') or ''
        hint = '检查 ping 是否安装、是否有 CAP_NET_RAW 能力（getcap /usr/bin/ping）。'
    elif diag == 'no_output':
        title = 'ping 无输出'
        detail = ping_res.get('stderr') or ''
        hint = '可能是 DNS 解析失败或 host 不可达。'
    else:
        title = '未知状态'
        detail = ping_res.get('error') or ''
        hint = ''

    return {'title': title, 'detail': detail, 'hint': hint, 'diagnosis': diag}
