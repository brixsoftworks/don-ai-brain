"""tool_call_parser — parse agent output into ParsedToolCall list.

Handles both native Ollama function-calling (preferred, already structured)
and JSON-mode fallback (lenient parse pipeline).

See docs/component-4 §6.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from core.parsing.schemas import ParsedToolCall
from core.parsing.retry import parse_with_retry, _repair_json

log = logging.getLogger("don.parsing.tool_call")


def _validate_tool_call(data: dict) -> ParsedToolCall:
    return ParsedToolCall.model_validate(data)


def parse_ollama_tool_calls(raw_calls: list[dict]) -> list[ParsedToolCall]:
    """Convert native Ollama tool_calls (already structured) to ParsedToolCall.

    This is the preferred path — zero parsing needed.
    """
    out = []
    for call in raw_calls:
        fn = call.get("function", {})
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"raw": args}
        out.append(ParsedToolCall(
            tool=fn.get("name", ""),
            args=args if isinstance(args, dict) else {"raw": str(args)},
        ))
    return out


def parse_tool_call_json(
    raw: str,
    retry_fn: Callable[[str], str | None] | None = None,
) -> list[ParsedToolCall]:
    """Parse a JSON-mode tool call string → list of ParsedToolCall.

    Handles: single object, array of objects, or JSON embedded in prose.
    Returns empty list on complete failure (never raises).
    """
    raw = raw.strip()
    if not raw:
        return []

    # try the full parse pipeline
    def _validate(data: dict) -> ParsedToolCall:
        return ParsedToolCall.model_validate(data)

    # single object
    result, ok = parse_with_retry(raw, _validate, retry_fn=retry_fn)
    if ok and result is not None:
        return [result]

    # try parsing as array
    try:
        arr = json.loads(raw)
        if isinstance(arr, list):
            return [ParsedToolCall.model_validate(item) for item in arr if isinstance(item, dict)]
    except (json.JSONDecodeError, Exception):
        pass

    # try repair on array
    repaired = _repair_json(raw)
    if repaired is not None:
        try:
            if isinstance(repaired, list):
                return [ParsedToolCall.model_validate(item) for item in repaired if isinstance(item, dict)]
            return [ParsedToolCall.model_validate(repaired)]
        except Exception:
            pass

    log.warning("tool call parse failed completely")
    return []


def merge_native_and_json(
    native_calls: list[dict],
    raw_json: str | None,
) -> list[ParsedToolCall]:
    """Merge native Ollama calls with any JSON fallback content.

    Native takes precedence. JSON fallback only used when native is empty.
    """
    if native_calls:
        return parse_ollama_tool_calls(native_calls)
    if raw_json:
        return parse_tool_call_json(raw_json)
    return []
