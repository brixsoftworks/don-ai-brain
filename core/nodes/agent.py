"""agent_loop node — ReAct planner driven by the routed department model.

Each cycle: BigTool retrieves relevant tools → department model either emits
native tool_calls (loop → guard → tool_node) or a final answer (→ responder).
Circuit breakers (MAX_ITERATIONS / MAX_TOKENS) force a summary.

See docs/component-1 §4.3, docs/component-6 §3.
"""
from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from core.prompts import PromptBank
from core.settings import Settings
from core.toolruntime.bigtool_retriever import BigToolRetriever
from models.ollama_client import OllamaClient

log = logging.getLogger("don.agent")


def _to_langchain(messages: list) -> list:
    out = []
    for m in messages:
        if isinstance(m, (HumanMessage, AIMessage, ToolMessage)):
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


def _extract_text_tool_calls(content: str, tool_blocks: list[dict]) -> list[dict]:
    """Parse tool calls embedded as JSON blocks in the response text.

    Models like qwen2.5 sometimes emit tool calls as:
      {"name": "shell", "arguments": {"command": "..."}}
    in the content text instead of using Ollama's native tool_calls format.
    """
    valid_names = {t["name"] for t in tool_blocks}
    calls = []

    # find balanced JSON objects using bracket counting
    for i, ch in enumerate(content):
        if ch != '{':
            continue
        depth = 0
        for j in range(i, len(content)):
            if content[j] == '{':
                depth += 1
            elif content[j] == '}':
                depth -= 1
                if depth == 0:
                    candidate = content[i:j + 1]
                    try:
                        obj = json.loads(candidate)
                    except (json.JSONDecodeError, ValueError):
                        break
                    name = obj.get("name", "")
                    if name in valid_names:
                        args = obj.get("arguments") or obj.get("args") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {"raw": args}
                        calls.append({
                            "name": name,
                            "args": args,
                            "id": f"text_call_{len(calls)}",
                            "type": "tool_call",
                        })
                    break

    return calls


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

    # Find the most recent REAL user message, skipping generic continuation prompts
    last_user = ""
    for m in reversed(state.get("messages", [])):
        if getattr(m, "type", "") == "human":
            if m.content not in ["Proceed.", "The tool above has been executed. If the user's task is NOT yet complete, call the next tool to continue. If the task IS complete, provide your final answer now."]:
                last_user = m.content
                break
    
    if not last_user:
        last_user = state.get("task_type", "")

    tool_blocks = bigtool.tool_injections(last_user)

    system = prompts.system_for(
        dept,
        user_name=user_name,
        device=state.get("device", "laptop"),
        memory_context=str(state.get("memory") or ""),
    )
    retrieval_ctx = state.get("retrieval_context") or ""
    tool_listing = "\n".join(
        f"- {t['name']} ({t['danger']}): {t['description']}" for t in tool_blocks
    )
    context_block = ""
    if retrieval_ctx.strip():
        context_block = (
            "\n\nRetrieved context (prefer this over guessing; if it doesn't "
            "answer the question, say so honestly):\n" + retrieval_ctx
        )
    system = type(system)(
        content=system.content
        + "\n\nAvailable tools for this task:\n" + tool_listing
        + context_block
        + "\n\nReply with a tool call if you need to act. Otherwise answer directly."
    )

    messages = [system] + _to_langchain(state.get("messages", []))
    if not messages or not isinstance(messages[-1], HumanMessage):
        messages.append(HumanMessage(content="Proceed."))

    # detect if we just got a tool result — allow the model to continue
    # chaining tools OR provide a final answer
    last_is_tool_result = False
    for m in reversed(messages[:-1]):  # skip our appended HumanMessage
        if isinstance(m, ToolMessage):
            last_is_tool_result = True
            break
        if isinstance(m, HumanMessage) and m.content != "Proceed.":
            break

    # DEBUG: show message types for troubleshooting
    msg_types = [type(m).__name__ + "(" + getattr(m, "type", "?") + ")" for m in messages[-5:]]
    log.info("agent messages (last 5): %s | last_is_tool_result=%s", msg_types, last_is_tool_result)

    if last_is_tool_result:
        # strip old AIMessages with tool_calls from history so the model
        # doesn't keep regenerating the same tool calls
        cleaned = []
        for m in messages:
            if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
                cleaned.append(AIMessage(content=m.content or "(tool calls executed)"))
            else:
                cleaned.append(m)
        messages = cleaned
        # instruct the model to either continue with next step or finalize
        messages[-1] = HumanMessage(
            content="The tool above has been executed. "
            "If the user's task is NOT yet complete, call the next tool to continue. "
            "If the task IS complete, provide your final answer now."
        )

    resp = client.invoke(
        dept,
        messages,
        tools=_build_ollama_tool_schemas(tool_blocks),
    )
    tokens_used += resp.get("prompt_eval_count", 0) + resp.get("eval_count", 0)

    tool_calls = _ollama_to_langchain_tool_calls(resp.get("tool_calls", []))
    content = resp.get("content", "").strip()

    # fallback: extract tool calls from content text when the model
    # outputs them as JSON blocks instead of native tool_calls
    if not tool_calls and content:
        tool_calls = _extract_text_tool_calls(content, tool_blocks)

    # fallback: detect bare tool names (e.g. model just says "sys_stats")
    if not tool_calls and content:
        stripped = content.strip().strip("`").strip()
        valid_names = {t["name"] for t in tool_blocks}
        if stripped in valid_names:
            tool_calls = [{
                "name": stripped,
                "args": {},
                "id": "bare_call_0",
                "type": "tool_call",
            }]
            content = ""  # clear content since it was just a tool name

    update: dict = {
        "iterations": iterations + 1,
        "tokens_used": tokens_used,
    }

    if tool_calls:
        log.info("agent emits %d tool call(s): %s", len(tool_calls), [c["name"] for c in tool_calls])
        update["messages"] = [AIMessage(content=content, tool_calls=tool_calls)]
    else:
        update["reply"] = content
        # Add a clean AIMessage (no tool_calls) so the guard/graph
        # sees this as the latest message and doesn't re-route to guard
        update["messages"] = [AIMessage(content=content)]

    if tokens_used >= settings.max_tokens_per_task:
        update["reply"] = (
            "I've hit my token budget for this task. "
            f"Summary of my best answer so far:\n{update.get('reply', content)}"
        )
    log.debug("agent step: iters=%d tokens=%d tools=%d", iterations + 1, tokens_used, len(tool_calls))
    return update
