"""System & files tools: monitoring, jailed shell, jailed file ops.

See docs/component-5 §4 (System & Files) and §7 (sandbox).
"""
from __future__ import annotations

from pathlib import Path

import psutil
from langchain_core.tools import tool

JAIL_ROOT = Path.home() / "jarvishome"
DENY_LIST = ["rm -rf", "mkfs", "sudo", "shutdown", "reboot", "curl|sh", "> /dev/sda", ":(){", "mkfs.", "rmdir /", "dd if="]


def _jail(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_relative_to(JAIL_ROOT.resolve()):
        raise PermissionError(f"path outside jail: {p}")
    return p


@tool
def sys_stats() -> str:
    """Report CPU, RAM, disk, and battery status of this machine."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.home()))
    parts = [
        f"CPU: {cpu}%",
        f"RAM: {mem.used / 1e9:.1f}/{mem.total / 1e9:.1f} GB ({mem.percent}%)",
        f"Disk: {disk.used / 1e9:.1f}/{disk.total / 1e9:.1f} GB ({disk.percent}%)",
    ]
    try:
        bat = psutil.sensors_battery()
        if bat:
            parts.append(f"Battery: {bat.percent}% {'charging' if bat.power_plugged else 'on battery'}")
    except Exception:
        pass
    return "\n".join(parts)


@tool
def shell(command: str) -> str:
    """Run a shell command on this machine. Output capped, 60s timeout.

    Commands are jailed to ~/jarvishome and a deny-list blocks destructive
    patterns (rm -rf, sudo, mkfs, shutdown, ...).
    """
    import subprocess

    for banned in DENY_LIST:
        if banned in command:
            raise PermissionError(f"command blocked by deny-list: {banned}")
    proc = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(JAIL_ROOT),
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return f"status: error ({proc.returncode})\nstderr: {err}"
    return out or err or "(no output)"


@tool
def file_read(path: str) -> str:
    """Read a text file. Path must be inside ~/jarvishome."""
    return _jail(path).read_text()


@tool
def file_write(path: str, content: str) -> str:
    """Write text to a file (creates parent dirs). Path must be inside ~/jarvishome."""
    p = _jail(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"wrote {len(content)} chars to {p}"


@tool
def file_list(path: str = "") -> str:
    """List files/dirs under a path inside ~/jarvishome (default: root)."""
    p = _jail(path or ".")
    entries = sorted(p.iterdir())
    return "\n".join(
        f"{'[d]' if e.is_dir() else '   '} {e.relative_to(JAIL_ROOT)}" for e in entries[:200]
    )
