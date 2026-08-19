"""classify_input node — tags the task with the small router model.

See docs/component-1 §4.1.
"""
from __future__ import annotations

import logging
import re

from langchain_core.messages import AIMessage

from core.parsing.router_parser import parse_task_classification
from core.prompts import PromptBank
from models.ollama_client import OllamaClient

log = logging.getLogger("don.classify")

# keyword heuristics when the router model misclassifies
_KEYWORD_OVERRIDES: dict[str, list[str]] = {
    "system": ["shell", "ffmpeg", "rename", "move", "delete", "copy", "mkdir",
                "chmod", "install", "unzip", "tar", "wget", "curl", "docker",
                "merge", "trim", "convert", "compress", "extract"],
    "coding": ["script", "python", "code", "program", "function", "class",
               "import", "debug", "git", "commit", "push", "pull"],
}


def _keyword_classify(user_input: str) -> str | None:
    """Heuristic fallback: scan for tool-related keywords."""
    words = set(re.findall(r"[a-z_]{3,}", user_input.lower()))
    best_type, best_count = None, 0
    for task_type, keywords in _KEYWORD_OVERRIDES.items():
        count = sum(1 for kw in keywords if kw in words)
        if count > best_count:
            best_type, best_count = task_type, count
    return best_type if best_count >= 2 else None


def classify_input(state: dict, client: OllamaClient, prompts: PromptBank) -> dict:
    """Set state.task_type (and normalize state.media)."""
    last_user = next(
        (m.content for m in reversed(state.get("messages", []))
         if getattr(m, "type", "") == "human"),
        "",
    )
    media = state.get("media") or {}

    task_type = "unknown"
    try:
        resp = client.invoke("router", prompts.build_classifier(last_user))
        classification = parse_task_classification(resp["content"])
        task_type = classification.task_type
        log.debug("classify=%s conf=%.2f", task_type, classification.confidence)
    except Exception as exc:  # noqa: BLE001
        log.error("classifier failed, defaulting to unknown: %s", exc)
        task_type = "unknown"

    # keyword fallback when router is too small to classify correctly
    if task_type == "unknown":
        kw_type = _keyword_classify(last_user)
        if kw_type:
            log.info("keyword fallback: unknown -> %s", kw_type)
            task_type = kw_type

    update = {"task_type": task_type}
    if media.get("type") == "image" or (media and isinstance(media, dict) and media.get("path")):
        update["task_type"] = "image_analysis" if media.get("type") == "image" else task_type
        update["media"] = media
    return update
