"""server/ws.py — WebSocket session manager (device ↔ thread).

Routes live events to the right device. Thread ownership: the last device
active on a thread becomes its listener (docs/component-16 §4).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger("don.ws")


class SessionManager:
    def __init__(self):
        self._conns: dict[str, Any] = {}        # device_id -> WebSocket
        self._thread_owner: dict[str, str] = {} # thread_id -> device_id
        self._loop: asyncio.AbstractEventLoop | None = None

    def connect(self, device_id: str, ws) -> None:
        self._conns[device_id] = ws
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        log.info("device online: %s", device_id)

    def disconnect(self, device_id: str) -> None:
        self._conns.pop(device_id, None)
        for tid, owner in list(self._thread_owner.items()):
            if owner == device_id:
                self._thread_owner.pop(tid, None)
        log.info("device offline: %s", device_id)

    def claim_thread(self, thread_id: str, device_id: str) -> None:
        self._thread_owner[thread_id] = device_id

    def is_online(self, device_id: str) -> bool:
        return device_id in self._conns

    async def async_send(self, device_id: str, text: str) -> bool:
        ws = self._conns.get(device_id)
        if ws is None:
            return False
        try:
            await ws.send_text(text)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("ws send failed to %s: %s", device_id, exc)
            return False

    def send_to(self, device_id: str, text: str) -> bool:
        """Thread-safe best-effort send from any thread."""
        ws = self._conns.get(device_id)
        if ws is None or self._loop is None or self._loop.is_closed():
            return False
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(text), self._loop)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("ws send failed to %s: %s", device_id, exc)
            return False

    def send_to_thread(self, thread_id: str, text: str) -> bool:
        """Send to the thread's owner device; fall back to any online device."""
        owner = self._thread_owner.get(thread_id)
        if owner and self.is_online(owner):
            return self.send_to(owner, text)
        for dev in list(self._conns):
            if self.send_to(dev, text):
                return True
        return False
