"""retry — parse → retry(1) → fallback logic.

Exactly one retry per parse before falling back. Retry appends a corrective
instruction. Never loops, never blocks — every path has a guaranteed result.

See docs/component-4 §8.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

log = logging.getLogger("don.parsing.retry")

REPAIR_HINT = (
    "Output must be valid JSON only. No extra text, no markdown fences. "
    "Fix: no trailing commas, no unquoted keys, use double quotes."
)
RETRY_HINT = (
    "Your previous output was not valid JSON. "
    "Respond with ONLY a JSON object. No explanation, no markdown."
)


def _repair_json(text: str) -> dict | None:
    """Best-effort repair of common JSON issues from 7B models."""
    # extract first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    # strip trailing commas before } or ]
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    # single quotes → double quotes (only if no double quotes present)
    if '"' not in candidate:
        candidate = candidate.replace("'", '"')
    # unquoted keys: word before colon
    candidate = re.sub(r'(?<={|,)\s*(\w+)\s*:', r' "\1":', candidate)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def parse_with_retry(
    raw: str,
    validate: Callable[[dict], Any],
    *,
    retry_hint: str = RETRY_HINT,
    repair_fn: Callable[[str], dict | None] | None = None,
    retry_fn: Callable[[str], str | None] | None = None,
) -> tuple[Any, bool]:
    """Parse raw model output with the full strict→lenient→retry→fallback pipeline.

    Args:
        raw: raw model output text.
        validate: callable that takes a dict and returns the validated model
            (raises on invalid).
        repair_fn: optional custom lenient parser (default: _repair_json).
        retry_fn: optional callable that re-prompts the model and returns new raw
            text. If None, no retry is attempted.

    Returns:
        (result, parsed_ok) — parsed_ok is True when a real parse succeeded
        (not a fallback).
    """
    repair_fn = repair_fn or _repair_json

    # 1. strict path
    try:
        data = json.loads(raw)
        return validate(data), True
    except (json.JSONDecodeError, Exception):
        pass

    # 2. lenient repair
    repaired = repair_fn(raw)
    if repaired is not None:
        try:
            return validate(repaired), True
        except Exception:
            pass

    # 3. retry with hint
    if retry_fn is not None:
        retry_raw = retry_fn(retry_hint)
        if retry_raw:
            # strict
            try:
                data = json.loads(retry_raw)
                return validate(data), True
            except (json.JSONDecodeError, Exception):
                pass
            # lenient on retry
            repaired = repair_fn(retry_raw)
            if repaired is not None:
                try:
                    return validate(repaired), True
                except Exception:
                    pass

    # 4. fallback — caller decides what to return
    log.warning("parse failed, returning fallback")
    return None, False
