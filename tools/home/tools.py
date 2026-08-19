"""tools/home/tools.py — home automation: MQTT publish/subscribe.

Home Assistant integration via ha-mcp (MCP adapter) is the primary path.
MQTT provides generic device control as a fallback/complement.
See docs/component-5 §6.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from langchain_core.tools import tool

log = logging.getLogger("don.tools.home")


@tool
def mqtt_publish(
    topic: str,
    payload: str,
    qos: int = 0,
    retain: bool = False,
) -> str:
    """Publish a message to an MQTT broker.

    Args:
        topic: MQTT topic (e.g. 'home/lights/bedroom').
        payload: message payload (string or JSON).
        qos: quality of service (0, 1, or 2).
        retain: whether to retain the message on the broker.
    """
    try:
        import paho.mqtt.publish as publish

        broker = os.environ.get("MQTT_BROKER", "localhost")
        port = int(os.environ.get("MQTT_PORT", "1883"))
        auth = None
        username = os.environ.get("MQTT_USERNAME")
        password = os.environ.get("MQTT_PASSWORD")
        if username:
            auth = {"username": username, "password": password or ""}

        publish.single(
            topic, payload, hostname=broker, port=port,
            qos=qos, retain=retain, auth=auth,
        )
        return f"[mqtt published to {topic}]"
    except ImportError:
        return "[mqtt: paho-mqtt not installed. pip install paho-mqtt]"
    except Exception as exc:  # noqa: BLE001
        log.error("mqtt_publish failed: %s", exc)
        return f"[mqtt error: {exc}]"


@tool
def mqtt_subscribe(
    topic: str,
    timeout_seconds: int = 10,
    max_messages: int = 1,
) -> str:
    """Subscribe to an MQTT topic and read messages.

    Args:
        topic: MQTT topic to subscribe to.
        timeout_seconds: how long to wait for messages.
        max_messages: maximum messages to collect.
    """
    try:
        import paho.mqtt.client as mqtt_client

        broker = os.environ.get("MQTT_BROKER", "localhost")
        port = int(os.environ.get("MQTT_PORT", "1883"))
        messages = []

        client = mqtt_client.Client()
        username = os.environ.get("MQTT_USERNAME")
        if username:
            client.username_pw_set(username, os.environ.get("MQTT_PASSWORD", ""))

        def on_message(client, userdata, msg):
            messages.append({"topic": msg.topic, "payload": msg.payload.decode("utf-8", errors="replace")})
            if len(messages) >= max_messages:
                client.disconnect()

        client.on_message = on_message
        client.connect(broker, port)
        client.subscribe(topic)
        client.loop_forever(timeout=timeout_seconds)
        client.disconnect()

        if messages:
            return json.dumps(messages, indent=2)
        return f"[no messages received on {topic} within {timeout_seconds}s]"
    except ImportError:
        return "[mqtt: paho-mqtt not installed]"
    except Exception as exc:  # noqa: BLE001
        log.error("mqtt_subscribe failed: %s", exc)
        return f"[mqtt error: {exc}]"


TOOLS = [mqtt_publish, mqtt_subscribe]
