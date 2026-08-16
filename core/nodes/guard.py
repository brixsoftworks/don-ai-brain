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
    for m in reversed(state.get("messages", [])):
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            return list(m.tool_calls)
    return []


def _summary(args: dict, cap: int = 200) -> str:
    s = str(args)
    return s if len(s) <= cap else s[:cap] + "…"


def guard(state: dict, prompts: PromptBank, registry: ToolRegistry) -> dict:
    calls = _pending_calls(state)
    if not calls:
        return {"approved_calls": {}}

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
    for call, ok in zip(calls, decisions):
        approved[call.get("id", "")] = bool(ok)
        if not ok and call.get("name"):
            rejected.append(call["name"])
    log.info("guard: %d approved / %d rejected", sum(1 for d in decisions if d), sum(1 for d in decisions if not d))

    return {"approved_calls": approved, "cannot_use": sorted(set(rejected))}
