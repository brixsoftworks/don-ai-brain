"""guard node — human-in-the-loop approval before every tool call.

Interrupts once per batch; the payload lists each action with its danger
level. Resume value {"decisions": [bool, ...]} aligns with the tool_calls.
Rejected tools are recorded in state.cannot_use so the agent re-plans.

See docs/component-1 §8.
"""
from __future__ import annotations

import logging

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from core.prompts import PromptBank
from tools.registry import ToolRegistry

log = logging.getLogger("don.guard")

DANGER_LABEL = {"read": "INFO", "action": "ACTION", "destructive": "DESTRUCTIVE"}


def _pending_calls(state: dict) -> list[dict]:
    """Return tool_calls from the MOST RECENT AIMessage only.

    Scanning the full history causes re-approval loops because old AIMessages
    with tool_calls persist in state even after execution.
    """
    for m in reversed(state.get("messages", [])):
        if isinstance(m, AIMessage):
            if getattr(m, "tool_calls", None):
                return list(m.tool_calls)
            # found an AIMessage without tool_calls — stop scanning
            break
    return []


def _summary(args: dict, cap: int = 200) -> str:
    s = str(args)
    return s if len(s) <= cap else s[:cap] + "…"


def guard(state: dict, prompts: PromptBank, registry: ToolRegistry) -> dict:
    calls = _pending_calls(state)
    if not calls:
        return {"approved_calls": {}}

    # skip tool calls that were already processed (prevents re-approval loop)
    processed = set(state.get("processed_tool_calls", []))
    calls = [c for c in calls if c.get("id", "") not in processed]
    if not calls:
        return {"approved_calls": {}, "processed_tool_calls": sorted(processed)}

    actions = []
    for c in calls:
        try:
            spec = registry.get_spec(c["name"])
        except KeyError:
            spec = None
        actions.append({
            "tool": c["name"],
            "args": _summary(c.get("args", {})),
            "danger": spec.danger if spec else "action",
            "danger_label": DANGER_LABEL.get(spec.danger if spec else "action", "ACTION"),
            "reason": spec.description[:160] if spec else "unknown tool",
        })

    payload = {
        "type": "approval",
        "title": "DON wants to take action. Approve?",
        "actions": actions,
    }
    decision = interrupt(payload)

    if decision is True:
        decisions = [True] * len(calls)
    elif decision is False:
        decisions = [False] * len(calls)
    elif isinstance(decision, dict) and isinstance(decision.get("decisions"), list):
        decisions = decision["decisions"]
        decisions += [False] * (len(calls) - len(decisions))
    else:
        decisions = [False] * len(calls)

    approved: dict[str, bool] = {}
    rejected = list(state.get("cannot_use", []))
    newly_processed = set(state.get("processed_tool_calls", []))
    for call, ok in zip(calls, decisions):
        call_id = call.get("id", "")
        approved[call_id] = bool(ok)
        newly_processed.add(call_id)
        if not ok and call.get("name"):
            rejected.append(call["name"])
    log.info("guard: %d approved / %d rejected", sum(1 for d in decisions if d), sum(1 for d in decisions if not d))

    return {
        "approved_calls": approved,
        "cannot_use": sorted(set(rejected)),
        "processed_tool_calls": sorted(newly_processed),
    }
