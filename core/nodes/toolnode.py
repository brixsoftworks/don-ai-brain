"""tool_node — execute approved tool calls with validation, timeout, caps.

Replaces the ToolNode placeholder (docs/component-1 §4.5). Adds to the
prebuilt ToolNode: per-tool Pydantic validation, executor timeouts, output
capping, and a per-conversation blacklist after 3 consecutive failures.

See docs/component-6.
"""
from __future__ import annotations

import logging
from concurrent.futures import TimeoutError as _TimeoutError

from langchain_core.messages import AIMessage

from core.toolruntime.executor import ToolExecutor
from core.toolruntime.result import build_tool_message, error_result
from tools.registry import ToolRegistry

log = logging.getLogger("don.toolnode")

BLACKLIST_AFTER = 3


def _extract_tool_calls(messages: list) -> list[dict]:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            return list(m.tool_calls)
    return []


def tool_node(
    state: dict,
    registry: ToolRegistry,
    executor: ToolExecutor,
    *,
    timeout: float = 60.0,
    output_cap: int = 8192,
    blacklist_after: int = BLACKLIST_AFTER,
) -> dict:
    """Execute each pending tool call from the last AIMessage.

    Guard runs first (approval), so this node only sees approved calls.
    Returns appended ToolMessages, tool_results, and blacklist updates.
    """
    calls = _extract_tool_calls(state.get("messages", []))
    if not calls:
        return {"tool_results": []}

    approved_calls = state.get("approved_calls", {})

    tool_messages = []
    results = list(state.get("tool_results", []))
    blacklist = set(state.get("tool_blacklist", []))

    for call in calls:
        name = call["name"]
        args = call.get("args", {})
        call_id = call.get("id", "")

        if approved_calls.get(call_id) is False or name in state.get("cannot_use", []):
            content = (
                f"Action rejected by the operator (tool: {name}). "
                "Do not retry this action. Re-plan or ask the operator."
            )
            tool_messages.append(build_tool_message(name, call_id, content, cap=output_cap))
            results.append({"tool": name, "status": "rejected"})
            continue

        if name in blacklist:
            content = f"tool {name} is disabled this conversation (repeated failures)"
            tool_messages.append(build_tool_message(name, call_id, content, cap=output_cap))
            results.append({"tool": name, "status": "blacklisted"})
            continue

        try:
            tool = registry.get(name)
        except KeyError:
            content = f"tool not found: {name}; try search_tools() for alternatives"
            tool_messages.append(build_tool_message(name, call_id, content, cap=output_cap))
            results.append({"tool": name, "status": "not_found"})
            continue

        # 1. validate args against the tool's Pydantic schema
        spec = registry.get_spec(name)
        if spec.args_schema is not None:
            try:
                validated = spec.args_schema(**args)
                args = validated.model_dump()
            except Exception as exc:  # noqa: BLE001
                content = f"invalid arguments for {name}: {exc}"
                tool_messages.append(build_tool_message(name, call_id, content, cap=output_cap))
                results.append({"tool": name, "status": "invalid_args", "error": str(exc)})
                continue

        # 2. execute with timeout
        try:
            raw = executor.run_sync(tool.invoke, args, timeout=timeout)
        except _TimeoutError:
            content = error_result(TimeoutError(), tool=name, timeout=True)
            tool_messages.append(build_tool_message(name, call_id, content, cap=output_cap))
            results.append({"tool": name, "status": "timeout"})
            continue
        except Exception as exc:  # noqa: BLE001
            content = error_result(exc, tool=name)
            tool_messages.append(build_tool_message(name, call_id, content, cap=output_cap))
            results.append({"tool": name, "status": "error", "error": str(exc)})
            continue

        tool_messages.append(build_tool_message(name, call_id, raw, cap=output_cap))
        results.append({"tool": name, "status": "ok"})

    # blacklist bookkeeping: count consecutive errors per tool
    fails = {r["tool"] for r in results if r.get("status") in ("error", "timeout")}
    for f in fails:
        state.setdefault("_tool_fail_count", {})
        state["_tool_fail_count"][f] = state["_tool_fail_count"].get(f, 0) + 1
        if state["_tool_fail_count"][f] >= blacklist_after:
            blacklist.add(f)
            log.warning("tool %s blacklisted for this conversation", f)

    return {
        "messages": tool_messages,
        "tool_results": results,
        "tool_blacklist": sorted(blacklist),
    }
