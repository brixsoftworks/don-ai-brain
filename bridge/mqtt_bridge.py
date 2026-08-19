"""bridge/mqtt_bridge.py — MQTT pub/sub → graph events.

Connects MQTT broker to the DON graph for IoT events and device control.
See docs/component-16 §2.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Callable

log = logging.getLogger("don.bridge.mqtt")


class MQTTBridge:
    """MQTT pub/sub bridge for IoT events and device communication.

    Receives messages on subscribed topics and forwards them to the
    DON graph as events.
    """

    def __init__(
        self,
        broker: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        self.broker = broker or os.environ.get("MQTT_BROKER", "localhost")
        self.port = port or int(os.environ.get("MQTT_PORT", "1883"))
        self.username = username or os.environ.get("MQTT_USERNAME")
        self.password = password or os.environ.get("MQTT_PASSWORD")
        self._client = None
        self._subscriptions: dict[str, Callable] = {}
        self._running = False

    def connect(self) -> bool:
        """Connect to the MQTT broker."""
        try:
            import paho.mqtt.client as mqtt

            self._client = mqtt.Client()
            if self.username:
                self._client.username_pw_set(self.username, self.password)

            self._client.on_connect = self._on_connect
            self._client.on_message = self._on_message

            self._client.connect(self.broker, self.port)
            self._running = True
            log.info("mqtt connected to %s:%d", self.broker, self.port)
            return True
        except ImportError:
            log.warning("paho-mqtt not installed")
            return False
        except Exception as exc:  # noqa: BLE001
            log.error("mqtt connect failed: %s", exc)
            return False

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            log.info("mqtt connected (rc=%d)", rc)
            for topic in self._subscriptions:
                client.subscribe(topic)
                log.info("mqtt subscribed to %s", topic)
        else:
            log.error("mqtt connect failed rc=%d", rc)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = msg.payload.decode("utf-8", errors="replace")

        handler = self._subscriptions.get(topic)
        if handler:
            try:
                handler(topic, payload)
            except Exception as exc:  # noqa: BLE001
                log.error("mqtt handler error for %s: %s", topic, exc)

    def subscribe(self, topic: str, handler: Callable[[str, any], None]) -> None:
        """Subscribe to a topic with a callback handler."""
        self._subscriptions[topic] = handler
        if self._client and self._running:
            self._client.subscribe(topic)

    def publish(self, topic: str, payload: str | dict, qos: int = 0) -> bool:
        """Publish a message to a topic."""
        if not self._client:
            return False
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        try:
            self._client.publish(topic, payload, qos=qos)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("mqtt publish failed: %s", exc)
            return False

    def start(self) -> None:
        """Start the MQTT client loop in a background thread."""
        if self._client and self._running:
            self._client.loop_start()

    def stop(self) -> None:
        """Stop the MQTT client loop."""
        self._running = False
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    def run_forever(self) -> None:
        """Block and run the MQTT loop (foreground)."""
        if self._client:
            self._client.loop_forever()
