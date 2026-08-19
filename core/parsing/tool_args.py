"""tool_args — validate tool arguments against per-tool Pydantic schemas.

Invalid args → clean error string back to the agent; never crashes the loop.

See docs/component-4 §6 (argument validation).
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

log = logging.getLogger("don.parsing.tool_args")


def validate_tool_args(
    tool_name: str,
    args: dict[str, Any],
    schema: type[BaseModel] | None,
) -> tuple[dict[str, Any], str | None]:
    """Validate args against the tool's Pydantic schema.

    Returns:
        (validated_args, error_msg) — error_msg is None on success.
    """
    if schema is None:
        return args, None

    try:
        validated = schema(**args)
        return validated.model_dump(), None
    except ValidationError as exc:
        error_msg = f"tool {tool_name}: {exc.error_count()} argument error(s)"
        for err in exc.errors():
            loc = " → ".join(str(l) for l in err.get("loc", []))
            error_msg += f"\n  - {loc}: {err.get('msg', 'invalid')}"
        log.warning("arg validation failed for %s: %s", tool_name, error_msg)
        return args, error_msg
    except Exception as exc:  # noqa: BLE001
        error_msg = f"tool {tool_name}: unexpected validation error: {exc}"
        log.error(error_msg)
        return args, error_msg
