"""agent_loop node — the ReAct planner driven by the routed department model.

Foundation milestone: answer-only loop. Tool emission lands with the tools
layer (docs/component-5/6); the loop/breaker machinery is in place now.

See docs/component-1 §4.3 and §7 (circuit breakers).
"""
from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage

from core.prompts import PromptBank
from core.settings import Settings
from models.ollama_client import OllamaClient

log = logging.getLogger("don.agent")


def _to_langchain(messages: list) -> list:
    """Normalize plain dicts and legacy message objects into BaseMessages."""
    out = []
    for m in messages:
        if isinstance(m, (HumanMessage, AIMessage)):
            out.append(m)
        elif isinstance(m, dict):
            role = m.get("role", "user")
            content = m.get("content", "")
            out.append(HumanMessage(content=content) if role == "user" else AIMessage(content=content))
        else:
            out.append(m)
    return out


def agent_loop(
    state: dict,
    client: OllamaClient,
    prompts: PromptBank,
    settings: Settings,
    user_name: str = "Operator",
) -> dict:
    """One planning step: route model reads history and produces a reply.

    Returns partial state: appended assistant message, iteration/token counters,
    and (answer-only) a final reply.
    """
    dept = state.get("model_route", "main")
    iterations = state.get("iterations", 0)
    tokens_used = state.get("tokens_used", 0)

    if iterations >= settings.max_iterations:
        return {
            "reply": "I've hit my step limit for this task. Ask me to continue, operator.",
            "iterations": iterations,
        }

    system = prompts.system_for(
        dept,
        user_name=user_name,
        device=state.get("device", "laptop"),
        memory_context=str(state.get("memory") or ""),
    )

    history = _to_langchain(state.get("messages", []))
    messages = [system] + history
    if not history or not isinstance(history[-1], HumanMessage):
        messages.append(HumanMessage(content="Proceed."))

    resp = client.invoke(dept, [{"role": "system", "content": m.content} if m.type == "system" else {"role": "assistant" if m.type == "ai" else "user", "content": m.content} for m in messages])

    content = resp["content"]
    tokens_used += resp.get("prompt_eval_count", 0) + resp.get("eval_count", 0)

    update: dict = {
        "iterations": iterations + 1,
        "tokens_used": tokens_used,
        "reply": content,
    }

    if tokens_used >= settings.max_tokens_per_task:
        update["reply"] = (
            "I've hit my token budget for this task. "
            f"Summary of my best answer so far:\n{content}"
        )
    log.debug("agent step done: iters=%d tokens=%d", iterations + 1, tokens_used)
    return update
