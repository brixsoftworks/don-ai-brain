"""memory_parser — extract MemoryFact list from conversation text.

Runs post-reply (background) using the main model; facts below 0.7
confidence are dropped. See docs/component-4 §7.
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from core.parsing.schemas import MemoryFact
from core.parsing.retry import parse_with_retry, _repair_json

log = logging.getLogger("don.parsing.memory")


def _validate_facts(data: dict) -> list[MemoryFact]:
    """Validate a dict containing a 'facts' list."""
    facts_raw = data.get("facts", [])
    if not isinstance(facts_raw, list):
        return []
    return [
        MemoryFact.model_validate(f)
        for f in facts_raw
        if isinstance(f, dict)
    ]


def parse_memory_facts(
    raw: str,
    confidence_threshold: float = 0.7,
    retry_fn: Callable[[str], str | None] | None = None,
) -> list[MemoryFact]:
    """Parse LLM output → list of MemoryFact. Drops low-confidence entries.

    Expected LLM output format:
        {"facts": [{"subject": ..., "predicate": ..., "object_value": ...,
                     "category": ..., "confidence": ...}, ...]}
    """
    raw = raw.strip()
    if not raw:
        return []

    def _validate(data: dict) -> list[MemoryFact]:
        return _validate_facts(data)

    result, ok = parse_with_retry(raw, _validate, retry_fn=retry_fn)
    if ok and result is not None:
        filtered = [f for f in result if f.confidence >= confidence_threshold]
        log.info("parsed %d facts, kept %d (threshold %.2f)", len(result), len(filtered), confidence_threshold)
        return filtered

    # try array directly (some models omit the wrapper)
    try:
        arr = json.loads(raw)
        if isinstance(arr, list):
            facts = [MemoryFact.model_validate(f) for f in arr if isinstance(f, dict)]
            return [f for f in facts if f.confidence >= confidence_threshold]
    except (json.JSONDecodeError, Exception):
        pass

    log.warning("memory fact parse failed")
    return []
