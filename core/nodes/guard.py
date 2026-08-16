"""guard node — human-in-the-loop approval before every tool action.

Foundation milestone: no tools registered yet, so the guard is a pass-through
that is ready for the tools layer (docs/component-1 §8, docs/component-6).
"""
from __future__ import annotations

from langgraph.types import interrupt

from core.prompts import PromptBank


def guard(state: dict, prompts: PromptBank) -> dict:
    """If a tool action is pending, pause for operator approval."""
    action = state.get("pending_action")
    if not action:
        return {"pending_action": {}}

    approval = prompts.build_approval(
        tool=action.get("tool", "?"),
        args=str(action.get("args", "{}")),
        reason=str(action.get("reason", "")),
    )
    decision = interrupt({"type": "approval", "payload": approval})
    approved = bool(decision is True or (isinstance(decision, dict) and decision.get("decision") == "approve"))
    return {"pending_action": {**action, "approved": approved}}
