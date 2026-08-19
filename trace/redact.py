"""trace/redact.py — redaction rules for trace logs.

Secrets, sensitive tool args, and long message bodies are truncated.
See docs/component-14 §2.
"""
from __future__ import annotations

import re
from typing import Any

# patterns that indicate secrets/sensitive data
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|credential|oauth)", re.IGNORECASE),
    re.compile(r"(?i)(authorization|bearer)\s*[:=]", re.IGNORECASE),
]

# tools whose args should be fully redacted
SENSITIVE_TOOLS = {"shell", "file_write", "mqtt_publish", "push_notify"}

MAX_BODY_CHARS = 500
MAX_ARG_CHARS = 200


def redact_value(value: Any) -> Any:
    """Redact a single value if it looks like a secret."""
    if isinstance(value, str):
        for pat in SECRET_PATTERNS:
            if pat.search(value):
                return "[REDACTED]"
        if len(value) > MAX_BODY_CHARS:
            return value[:MAX_BODY_CHARS] + f"...[truncated {len(value) - MAX_BODY_CHARS} chars]"
    return value


def redact_tool_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Redact tool arguments based on sensitivity."""
    if tool_name in SENSITIVE_TOOLS:
        return {"_redacted": f"args for {tool_name} hidden"}
    return {k: redact_value(v) for k, v in args.items()}


def redact_body(text: str) -> str:
    """Truncate long message bodies."""
    if not isinstance(text, str):
        text = str(text)
    if len(text) > MAX_BODY_CHARS:
        return text[:MAX_BODY_CHARS] + f"...[truncated {len(text) - MAX_BODY_CHARS} chars]"
    return text


def redact_run_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Redact an entire run metadata dict for safe logging."""
    redacted = {}
    for k, v in metadata.items():
        if isinstance(v, dict):
            if "tool_name" in v:
                v = {**v, "args": redact_tool_args(v.get("tool_name", ""), v.get("args", {}))}
            redacted[k] = redact_value(v)
        elif isinstance(v, str):
            redacted[k] = redact_body(v)
        else:
            redacted[k] = v
    return redacted
