"""Tool result normalization: truncation, error wrapping, ToolMessage builder.

See docs/component-6 §5–6.
"""
from __future__ import annotations

import json
import traceback

from langchain_core.messages import ToolMessage


def truncate(text: str, cap: int = 8192) -> str:
    if len(text) <= cap:
        return text
    return text[:cap] + f"\n…[truncated {len(text) - cap} chars]"


def error_result(exc: BaseException, *, tool: str, timeout: bool = False) -> str:
    cause = "tool timed out" if timeout else f"{type(exc).__name__}: {exc}"
    summary = traceback.format_exception(exc) if not timeout else []
    detail = f"{cause}\n{summary[-1] if summary else ''}"
    return json.dumps({"status": "error", "message": cause, "detail": detail[:1000]}, ensure_ascii=False)


def build_tool_message(name: str, tool_call_id: str, content: str, *, cap: int = 8192) -> ToolMessage:
    return ToolMessage(name=name, tool_call_id=tool_call_id, content=truncate(content, cap))
