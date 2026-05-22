"""
WireGuard 密钥工具：生成密钥对、由私钥派生公钥。
优先使用 python-wireguard；不可用时回退到 `wg genkey` / `wg pubkey` 命令。
"""
from __future__ import annotations

import re
import subprocess
from typing import Any

from django.conf import settings

_B64_RE = re.compile(r'^[A-Za-z0-9+/]{43}=$')


def _allow_subprocess() -> bool:
    return bool(getattr(settings, 'INTERFACEMANAGE_ALLOW_SUBPROCESS', False))


def _command_timeout() -> int:
    return int(getattr(settings, 'INTERFACEMANAGE_COMMAND_TIMEOUT', 8))


def _run_with_stdin(argv: list[str], stdin_text: str | None = None) -> dict[str, Any]:
    if not _allow_subprocess():
        return {'ok': False, 'exit_code': -1, 'stdout': '', 'stderr': 'subprocess disabled'}
    try:
        proc = subprocess.run(
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=_command_timeout(),
            check=False,
        )
        return {
            'ok': proc.returncode == 0,
            'exit_code': proc.returncode,
            'stdout': proc.stdout or '',
            'stderr': proc.stderr or '',
        }
    except FileNotFoundError:
        return {'ok': False, 'exit_code': -1, 'stdout': '', 'stderr': f'not found: {argv[0]}'}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'exit_code': -1, 'stdout': '', 'stderr': 'timeout'}
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'exit_code': -1, 'stdout': '', 'stderr': str(exc)}


def _try_python_wireguard_keypair() -> tuple[str, str] | None:
    try:
        from python_wireguard import Key  # type: ignore
    except Exception:
        return None
    try:
        priv, pub = Key.key_pair()
        return str(priv).strip(), str(pub).strip()
    except Exception:
        return None


def _try_python_wireguard_pubkey(private_b64: str) -> str | None:
    try:
        from python_wireguard import Key  # type: ignore
    except Exception:
        return None
    try:
        k = Key(private_b64)
        pub = k.public_key()
        return str(pub).strip()
    except Exception:
        return None


def generate_keypair() -> dict[str, Any]:
    """生成 WireGuard 私钥 + 对应公钥。"""
    pair = _try_python_wireguard_keypair()
    if pair:
        priv, pub = pair
        return {'ok': True, 'private': priv, 'public': pub, 'source': 'python-wireguard'}

    gen = _run_with_stdin(['wg', 'genkey'])
    if not gen['ok']:
        return {
            'ok': False,
            'error': 'wg genkey 失败（请确认已安装 wireguard-tools 或 python-wireguard）',
            'stderr': gen['stderr'],
        }
    priv = gen['stdout'].strip()
    pub_res = _run_with_stdin(['wg', 'pubkey'], stdin_text=priv + '\n')
    if not pub_res['ok']:
        return {'ok': False, 'error': 'wg pubkey 失败', 'stderr': pub_res['stderr'], 'private': priv}
    return {
        'ok': True,
        'private': priv,
        'public': pub_res['stdout'].strip(),
        'source': 'wg-cli',
    }


def derive_public(private_b64: str) -> dict[str, Any]:
    t = (private_b64 or '').strip()
    if not _B64_RE.match(t):
        return {'ok': False, 'error': '私钥格式无效（应为 44 字符 base64）'}

    pub = _try_python_wireguard_pubkey(t)
    if pub:
        return {'ok': True, 'private': t, 'public': pub, 'source': 'python-wireguard'}

    res = _run_with_stdin(['wg', 'pubkey'], stdin_text=t + '\n')
    if not res['ok']:
        return {'ok': False, 'error': 'wg pubkey 失败', 'stderr': res['stderr']}
    return {'ok': True, 'private': t, 'public': res['stdout'].strip(), 'source': 'wg-cli'}
