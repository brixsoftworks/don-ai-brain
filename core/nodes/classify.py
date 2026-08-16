"""classify_input node — tags the task with the small router model.

See docs/component-1 §4.1.
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage

from core.prompts import PromptBank
from models.ollama_client import OllamaClient

log = logging.getLogger("don.classify")

VALID_TASK_TYPES = {
    "quick_query", "system", "comms", "knowledge", "coding",
    "complex_plan", "image_analysis", "unknown",
}


def _extract_json(text: str) -> dict | None:
    """Best-effort JSON extraction: strict -> fenced -> first brace pair."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def classify_input(state: dict, client: OllamaClient, prompts: PromptBank) -> dict:
    """Set state.task_type (and normalize state.media)."""
    last_user = next(
        (m.content for m in reversed(state.get("messages", []))
         if getattr(m, "type", "") == "human"),
        "",
    )
    media = state.get("media") or {}

    result = {
        "task_type": "unknown",
        "confidence": 0.0,
    }
    try:
        resp = client.invoke("router", prompts.build_classifier(last_user))
        parsed = _extract_json(resp["content"])
        if parsed and isinstance(parsed.get("task_type"), str):
            result["task_type"] = parsed["task_type"] if parsed["task_type"] in VALID_TASK_TYPES else "unknown"
            result["confidence"] = float(parsed.get("confidence", 0.0))
        log.debug("classify=%s conf=%.2f", result["task_type"], result["confidence"])
    except Exception as exc:  # noqa: BLE001
        log.error("classifier failed, defaulting to unknown: %s", exc)
        result["task_type"] = "unknown"

    update = {"task_type": result["task_type"]}
    if media.get("type") == "image" or (media and isinstance(media, dict) and media.get("path")):
        update["task_type"] = "image_analysis" if media.get("type") == "image" else result["task_type"]
        update["media"] = media
    return update
