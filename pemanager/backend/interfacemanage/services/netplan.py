from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings


def _netplan_dirs() -> list[Path]:
    dirs = getattr(settings, 'INTERFACEMANAGE_NETPLAN_DIRS', ['/etc/netplan'])
    out: list[Path] = []
    for d in dirs:
        p = Path(d)
        if p.is_dir():
            out.append(p)
    return out


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    for key, val in b.items():
        if key in a and isinstance(a[key], dict) and isinstance(val, dict):
            _deep_merge(a[key], val)
        else:
            a[key] = val
    return a


def load_netplan() -> dict[str, Any]:
    """读取 netplan YAML：按文件列出解析结果，并给出浅层合并后的 network 树。"""
    files: dict[str, Any] = {}
    merged_network: dict[str, Any] = {}
    errors: list[dict[str, str]] = []

    for base in _netplan_dirs():
        for path in sorted(base.glob('*.yaml')) + sorted(base.glob('*.yml')):
            rel = str(path)
            try:
                text = path.read_text(encoding='utf-8')
            except OSError as exc:
                errors.append({'file': rel, 'error': str(exc)})
                continue
            try:
                data = yaml.safe_load(text) or {}
            except yaml.YAMLError as exc:
                errors.append({'file': rel, 'error': f'YAML error: {exc}'})
                continue
            files[rel] = data
            net = data.get('network')
            if isinstance(net, dict):
                _deep_merge(merged_network, net)

    return {
        'netplan_version': merged_network.get('version'),
        'merged_network': merged_network,
        'files': files,
        'errors': errors,
        'summary': {
            'file_count': len(files),
            'sections': sorted(k for k in merged_network.keys() if k != 'version'),
        },
    }


def netplan_as_json(netplan: dict[str, Any]) -> str:
    return json.dumps(netplan, ensure_ascii=False, indent=2, default=str)


def index_netplan_interfaces(merged_network: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """将 netplan 各段落按接口名索引，便于与内核 ifname 对齐。"""
    out: dict[str, dict[str, Any]] = {}
    if not merged_network:
        return out

    section_map = {
        'ethernets': 'ethernet',
        'wifis': 'wifi',
        'bridges': 'bridge',
        'bonds': 'bond',
        'vlans': 'vlan',
        'tunnels': 'tunnel',
        'vrfs': 'vrf',
    }

    for section, kind in section_map.items():
        block = merged_network.get(section)
        if not isinstance(block, dict):
            continue
        for ifname, spec in block.items():
            if not isinstance(spec, dict):
                continue
            entry = {'section': section, 'kind': kind, 'spec': spec}
            if ifname in out:
                entry['note'] = 'duplicate name in netplan;后者覆盖展示'
            out[ifname] = entry
    return out
