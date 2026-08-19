"""tools/comms/tools.py — communication tools: push notifications, email (stub).

Email requires Google OAuth (enabled later). Push uses ntfy/MQTT.
See docs/component-5 §4.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import httpx
from langchain_core.tools import tool

log = logging.getLogger("don.tools.comms")

NTFY_BASE_URL = "https://ntfy.sh"


@tool
def push_notify(
    topic: str,
    message: str,
    title: str = "DON",
    priority: str = "default",
    tags: str = "",
) -> str:
    """Send a push notification via ntfy.sh to a topic.

    Args:
        topic: ntfy topic name (device/channel).
        message: notification body text.
        title: notification title (default: DON).
        priority: notification priority (min, low, default, high, urgent).
        tags: comma-separated emoji tags (e.g. 'robot,warning').
    """
    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = tags
    try:
        resp = httpx.post(
            f"{NTFY_BASE_URL}/{topic}",
            content=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            return f"[notify sent to {topic}]"
        return f"[notify failed: HTTP {resp.status_code}]"
    except Exception as exc:  # noqa: BLE001
        log.error("push_notify failed: %s", exc)
        return f"[notify error: {exc}]"


@tool
def email_send(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
) -> str:
    """Send an email (requires Google OAuth — currently stubbed).

    Args:
        to: recipient email address.
        subject: email subject line.
        body: email body text.
        cc: optional CC addresses.
    """
    return (
        "[email_send is not yet configured. "
        "Set up Google OAuth in config/.env to enable.]"
    )


@tool
def email_search(
    query: str,
    max_results: int = 5,
) -> str:
    """Search emails (requires Google OAuth — currently stubbed).

    Args:
        query: search query (e.g. 'from:mom subject:recipe').
        max_results: maximum results to return.
    """
    return (
        "[email_search is not yet configured. "
        "Set up Google OAuth in config/.env to enable.]"
    )


@tool
def calendar_list(
    date: str = "",
    max_events: int = 5,
) -> str:
    """List upcoming calendar events (requires Google OAuth — currently stubbed).

    Args:
        date: date to check (YYYY-MM-DD format, default: today).
        max_events: maximum events to return.
    """
    return (
        "[calendar_list is not yet configured. "
        "Set up Google OAuth in config/.env to enable.]"
    )


TOOLS = [push_notify, email_send, email_search, calendar_list]
