"""server/alerter.py — threshold events → device bridge notifications.

Monitors system health (storage, errors, task failures) and pushes alerts
to connected devices. See docs/component-16 §7.
"""
from __future__ import annotations

import logging
import psutil

from server.push import push_ntfy

log = logging.getLogger("don.server.alerter")

# alert thresholds
THRESHOLDS = {
    "disk_percent": 90,
    "ram_percent": 85,
    "error_rate": 0.3,  # 30% error rate triggers alert
}


class Alerter:
    """Monitor system health and push alerts to devices."""

    def __init__(self, ntfy_topic: str = "don-alerts"):
        self.ntfy_topic = ntfy_topic
        self._last_alerts: dict[str, float] = {}

    def check_system_health(self) -> list[dict]:
        """Run health checks. Returns list of triggered alerts."""
        alerts = []

        # disk usage
        disk = psutil.disk_usage("/")
        if disk.percent >= THRESHOLDS["disk_percent"]:
            alerts.append({
                "type": "disk_warning",
                "severity": "high",
                "message": f"Disk usage at {disk.percent}% — consider cleanup",
                "detail": f"{disk.free // (1024**3)}GB free of {disk.total // (1024**3)}GB",
            })

        # RAM usage
        ram = psutil.virtual_memory()
        if ram.percent >= THRESHOLDS["ram_percent"]:
            alerts.append({
                "type": "memory_warning",
                "severity": "high",
                "message": f"RAM usage at {ram.percent}% — models may be evicted",
                "detail": f"{ram.available // (1024**2)}MB available",
            })

        return alerts

    def push_alerts(self, alerts: list[dict]) -> None:
        """Push alerts to devices via ntfy."""
        if not alerts:
            return
        for alert in alerts:
            severity = alert.get("severity", "default")
            try:
                push_ntfy(
                    topic=self.ntfy_topic,
                    title=f"DON Alert [{alert.get('type', 'unknown')}]",
                    body=alert.get("message", "Unknown alert"),
                )
            except Exception as exc:  # noqa: BLE001
                log.error("failed to push alert: %s", exc)

    def run_checks(self) -> list[dict]:
        """Run all checks and push any triggered alerts."""
        alerts = self.check_system_health()
        if alerts:
            self.push_alerts(alerts)
            for a in alerts:
                log.warning("alert: %s — %s", a.get("type"), a.get("message"))
        return alerts
