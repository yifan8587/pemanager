"""按 FirewallSettings.engine 路由到 nft_writer / iptables_writer。"""
from __future__ import annotations

from typing import Any, Literal

from firewallmanage.models import FirewallSettings
from firewallmanage.services import iptables_writer, nft_writer

Phase = Literal['preview', 'validate', 'apply', 'flush']


def _writer():
    s = FirewallSettings.load()
    return iptables_writer if s.engine == FirewallSettings.Engine.IPTABLES else nft_writer


def render_ruleset() -> dict[str, Any]:
    s = FirewallSettings.load()
    if s.engine == FirewallSettings.Engine.IPTABLES:
        return {
            'engine': 'iptables',
            'ruleset': iptables_writer.render_ruleset(family='ipv4'),
            'ruleset_ipv6': iptables_writer.render_ruleset(family='ipv6'),
        }
    return {'engine': 'nft', 'ruleset': nft_writer.render_ruleset()}


def apply_ruleset(*, phase: Phase = 'apply') -> dict[str, Any]:
    return _writer().apply_ruleset(phase=phase)


def show_ruleset() -> dict[str, Any]:
    return _writer().show_ruleset()
