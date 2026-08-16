"""server/devices.py — device registry + presence.

SQLite `devices` table; automatic registration on first connect;
30s heartbeat updates presence. Drives notification routing.
See docs/component-16 §3.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

DEFAULT_DB = Path(__file__).resolve().parent.parent / "jarvishome" / "devices.db"

CAPABILITIES = ("mic", "speaker", "camera", "screen")


class DeviceInfo(BaseModel):
    device_id: str
    type: str = "laptop"
    capabilities: list[str] = []
    push_channel: str = ""


class DeviceRegistry:
    def __init__(self, db_path: Path | str = DEFAULT_DB):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            capabilities TEXT NOT NULL DEFAULT '[]',
            push_channel TEXT NOT NULL DEFAULT '',
            last_seen TEXT NOT NULL,
            online INTEGER NOT NULL DEFAULT 0
        );
        """)

    def register(self, info: DeviceInfo) -> None:
        self.conn.execute(
            "INSERT INTO devices (device_id, type, capabilities, push_channel, last_seen, online) "
            "VALUES (?, ?, ?, ?, ?, 1) "
            "ON CONFLICT(device_id) DO UPDATE SET "
            "type=excluded.type, capabilities=excluded.capabilities, "
            "push_channel=excluded.push_channel, last_seen=excluded.last_seen, online=1",
            (info.device_id, info.type, ",".join(info.capabilities), info.push_channel,
             datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def heartbeat(self, device_id: str) -> None:
        self.conn.execute(
            "UPDATE devices SET last_seen = ?, online = 1 WHERE device_id = ?",
            (datetime.now(timezone.utc).isoformat(), device_id),
        )
        self.conn.commit()

    def set_offline(self, device_id: str) -> None:
        self.conn.execute("UPDATE devices SET online = 0 WHERE device_id = ?", (device_id,))
        self.conn.commit()

    def best_device(self) -> str | None:
        """Online + last-active first; fallback to any device (push)."""
        row = self.conn.execute(
            "SELECT device_id FROM devices ORDER BY online DESC, last_seen DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def list_devices(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM devices ORDER BY online DESC, last_seen DESC").fetchall()
        cols = [d[1] for d in self.conn.execute("PRAGMA table_info(devices)")]
        return [dict(zip(cols, r)) for r in rows]
