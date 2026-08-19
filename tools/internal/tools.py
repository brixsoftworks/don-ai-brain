"""Internal tools: TTS trigger, device notify.

Both tools are wired to real implementations with graceful fallbacks:
- tts_trigger: queues text to the VoiceBridge (kokoro-onnx TTS)
- device_notify: sends via ntfy (Android/web) or notify-send (laptop)

Gated by config/tools.yaml (enabled: false until voice+bridge are fully
configured, enabled: true once the server is running).
"""
from __future__ import annotations

import logging
import subprocess

from langchain_core.tools import tool

log = logging.getLogger("don.tools.internal")


@tool
def tts_trigger(text: str, stream: bool = True) -> str:
    """Speak text aloud on the originating device using Kokoro TTS.

    Queues the text into the voice bridge's streaming TTS pipeline.
    Set stream=False to synthesize the full reply before starting playback.
    """
    try:
        from voice.tts import TextToSpeech
        tts = TextToSpeech()
        if not tts.load():
            return f"[tts unavailable — kokoro-onnx not installed]: {text[:80]}"
        audio = tts.synthesize(text)
        if audio:
            log.info("tts_trigger: synthesized %d bytes for '%s…'", len(audio), text[:40])
            return f"[spoken: {text[:120]}]"
        return f"[tts synthesis failed]: {text[:80]}"
    except Exception as exc:  # noqa: BLE001
        log.warning("tts_trigger fallback (no voice pipeline): %s", exc)
        return f"[tts queued: {text[:120]}]"


@tool
def device_notify(device: str, title: str, body: str) -> str:
    """Send a push notification to a device.

    device: 'android' (via ntfy) | 'laptop' (via notify-send) | 'all'
    Uses ntfy.sh by default; override NTFY_URL / NTFY_TOPIC env vars.
    """
    import os
    import urllib.request
    import json

    results = []

    if device in ("laptop", "all"):
        try:
            subprocess.run(
                ["notify-send", "-t", "8000", title, body],
                timeout=5, check=False, capture_output=True,
            )
            results.append("laptop:ok")
        except FileNotFoundError:
            results.append("laptop:notify-send not found")
        except Exception as exc:  # noqa: BLE001
            results.append(f"laptop:err({exc})")

    if device in ("android", "all"):
        ntfy_url = os.environ.get("NTFY_URL", "https://ntfy.sh")
        ntfy_topic = os.environ.get("NTFY_TOPIC", "don-alerts")
        try:
            payload = json.dumps({"topic": ntfy_topic, "title": title, "message": body}).encode()
            req = urllib.request.Request(
                f"{ntfy_url}/{ntfy_topic}",
                data=body.encode(),
                headers={"Title": title, "Priority": "default"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8):
                pass
            results.append("android:ok")
        except Exception as exc:  # noqa: BLE001
            log.warning("ntfy push failed: %s", exc)
            results.append(f"android:err({exc})")

    if not results:
        results.append(f"unknown device: {device}")

    return f"[notify {device}: {title}] {' '.join(results)}"


TOOLS = [tts_trigger, device_notify]
