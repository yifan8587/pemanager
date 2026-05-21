from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings


@dataclass
class CmdResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str


def subprocess_allowed() -> bool:
    return bool(getattr(settings, 'INTERFACEMANAGE_ALLOW_SUBPROCESS', False))


def command_timeout() -> int:
    return int(getattr(settings, 'INTERFACEMANAGE_COMMAND_TIMEOUT', 8))


def run(argv: list[str], *, timeout: int | None = None) -> CmdResult:
    if not subprocess_allowed():
        return CmdResult(ok=False, exit_code=-1, stdout='', stderr='subprocess disabled')

    import subprocess

    t = timeout if timeout is not None else command_timeout()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=t,
            check=False,
        )
        return CmdResult(
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=proc.stdout or '',
            stderr=proc.stderr or '',
        )
    except FileNotFoundError:
        return CmdResult(ok=False, exit_code=-1, stdout='', stderr=f'not found: {argv[0]}')
    except subprocess.TimeoutExpired:
        return CmdResult(ok=False, exit_code=-1, stdout='', stderr='timeout')
    except Exception as exc:  # noqa: BLE001
        return CmdResult(ok=False, exit_code=-1, stdout='', stderr=str(exc))
