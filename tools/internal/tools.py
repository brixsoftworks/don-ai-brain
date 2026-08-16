"""Internal tools: TTS trigger, device notify.

Stubs for now — wired into the graph but gated `enabled: false` in
config/tools.yaml until the voice pipeline (C15) and device bridge (C16)
land.
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def tts_trigger(text: str) -> str:
    """Speak text aloud on the originating device (voice reply)."""
    return f"[tts queued: {text[:120]}]"


@tool
def device_notify(device: str, title: str, body: str) -> str:
    """Send a push notification to a device (android | laptop)."""
    return f"[notify {device}: {title}] {body[:120]}"
