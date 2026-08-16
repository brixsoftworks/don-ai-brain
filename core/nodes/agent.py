"""agent_loop node — ReAct planner driven by the routed department model.

Each cycle: BigTool retrieves relevant tools → department model either emits
native tool_calls (loop → guard → tool_node) or a final answer (→ responder).
Circuit breakers (MAX_ITERATIONS / MAX_TOKENS) force a summary.

See docs/component-1 §4.3, docs/component-6 §3.
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from core.prompts import PromptBank
from core.settings import Settings
from core.toolruntime.bigtool_retriever import BigToolRetriever
from models.ollama_client import OllamaClient

log = logging.getLogger("don.agent")


def _to_langchain(messages: list) -> list:
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


def _ollama_to_langchain_tool_calls(ollama_calls: list) -> list[dict]:
    """Convert ollama's tool_calls to LangChain AIMessage.tool_calls."""
    out = []
    for i, call in enumerate(ollama_calls):
        fn = call.get("function", {})
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"raw": args}
        out.append({
            "name": fn.get("name", ""),
            "args": args or {},
            "id": f"call_{i}",
            "type": "tool_call",
        })
    return out


def _build_ollama_tool_schemas(tool_blocks: list[dict]) -> list[dict]:
    schemas = []
    for t in tool_blocks:
        params = t.get("args_schema") or {"type": "object", "properties": {}}
        schemas.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": params,
            },
        })
    return schemas


def agent_loop(
    state: dict,
    client: OllamaClient,
    prompts: PromptBank,
    settings: Settings,
    bigtool: BigToolRetriever,
    user_name: str = "Operator",
) -> dict:
    """One planning step. Returns partial state (see module docstring)."""
    dept = state.get("model_route", "main")
    iterations = state.get("iterations", 0)
    tokens_used = state.get("tokens_used", 0)

    if iterations >= settings.max_iterations:
        return {
            "reply": "I've hit my step limit for this task. Ask me to continue, operator.",
            "iterations": iterations,
        }

    last_user = next(
        (m.content for m in reversed(state.get("messages", []))
         if getattr(m, "type", "") == "human"),
        "",
    )
    tool_blocks = bigtool.tool_injections(last_user or str(state.get("task_type", "")))

    system = prompts.system_for(
        dept,
        user_name=user_name,
        device=state.get("device", "laptop"),
        memory_context=str(state.get("memory") or ""),
    )
    tool_listing = "\n".join(
        f"- {t['name']} ({t['danger']}): {t['description']}" for t in tool_blocks
    )
    system = type(system)(
        content=system.content
        + "\n\nAvailable tools for this task:\n" + tool_listing
        + "\n\nReply with a tool call if you need to act. Otherwise answer directly."
    )

    messages = [system] + _to_langchain(state.get("messages", []))
    if not messages or not isinstance(messages[-1], HumanMessage):
        messages.append(HumanMessage(content="Proceed."))

    resp = client.invoke(
        dept,
        messages,
        tools=_build_ollama_tool_schemas(tool_blocks),
    )
    tokens_used += resp.get("prompt_eval_count", 0) + resp.get("eval_count", 0)

    tool_calls = _ollama_to_langchain_tool_calls(resp.get("tool_calls", []))
    content = resp.get("content", "").strip()

    update: dict = {
        "iterations": iterations + 1,
        "tokens_used": tokens_used,
    }

    if tool_calls:
        log.info("agent emits %d tool call(s): %s", len(tool_calls), [c["name"] for c in tool_calls])
        update["messages"] = [AIMessage(content=content, tool_calls=tool_calls)]
    else:
        update["reply"] = content

    if tokens_used >= settings.max_tokens_per_task:
        update["reply"] = (
            "I've hit my token budget for this task. "
            f"Summary of my best answer so far:\n{update.get('reply', content)}"
        )
    log.debug("agent step: iters=%d tokens=%d tools=%d", iterations + 1, tokens_used, len(tool_calls))
    return update
