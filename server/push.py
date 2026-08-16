"""server/push.py — push notification adapters (docs/component-16 §6).

Online path is the WS session; offline path falls back here.
"""
from __future__ import annotations

import logging
import subprocess
import urllib.request

log = logging.getLogger("don.push")


def push_ntfy(topic: str, title: str, body: str, ntfy_url: str = "https://ntfy.sh") -> bool:
    try:
        req = urllib.request.Request(
            f"{ntfy_url}/{topic}",
            data=body.encode(),
            headers={"Title": title, "Priority": "default"},
        )
        with urllib.request.urlopen(req, timeout=10):
            return True
    except Exception as exc:  # noqa: BLE001
        log.warning("ntfy push failed: %s", exc)
        return False


def push_notify_send(title: str, body: str) -> bool:
    try:
        subprocess.run(["notify-send", title, body], timeout=5, check=False)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("notify-send failed: %s", exc)
        return False


def notify(device: dict, cfg: dict, title: str, body: str) -> bool:
    """Route a notification to a device based on its push_channel."""
    channel = (device.get("push_channel") or "").lower()
    push = cfg.get("push", {})
    if "ntfy" in channel or channel == "android":
        return push_ntfy(push.get("ntfy_topic", "don-alerts"), title, body,
                         push.get("ntfy_url", "https://ntfy.sh"))
    return push_notify_send(title, body)
