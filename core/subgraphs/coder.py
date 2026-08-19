"""core/subgraphs/coder.py — coding specialist sub-graph.

Runs with the coder model (qwen2.5-coder:7b) and narrowed tool set:
file_read, file_write, file_list, shell. Returns a single structured
result capped at 2 KB.

See docs/component-13 §3.
"""
from __future__ import annotations

import logging
from functools import partial

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from core.prompts import PromptBank
from core.settings import Settings
from core.toolruntime.bigtool_retriever import BigToolRetriever
from core.toolruntime.executor import ToolExecutor
from models.ollama_client import OllamaClient
from tools.registry import ToolRegistry

log = logging.getLogger("don.subgraph.coder")

RESULT_CAP = 2048

CODER_TOOLS = {"file_read", "file_write", "file_list", "shell"}


def _filter_registry(registry: ToolRegistry) -> ToolRegistry:
    """Return a new registry containing only coder-relevant tools."""
    for spec in registry.enabled_specs():
        if spec.name not in CODER_TOOLS:
            spec.enabled = False
    return registry


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


def coder_node(
    state: dict,
    client: OllamaClient,
    prompts: PromptBank,
    settings: Settings,
    bigtool: BigToolRetriever,
    *,
    max_iterations: int = 10,
) -> dict:
    """Run the coder specialist: prompt with narrowed tools, return result."""
    dept = "coder"
    user_query = state.get("specialist_query", "")
    iterations = 0

    system = prompts.system_for(
        dept,
        user_name=state.get("user_name", "Operator"),
        device=state.get("device", "laptop"),
        memory_context="",
    )
    system = type(system)(
        content=system.content
        + "\n\nYou are the coding specialist. Write production-quality code. "
        "Explain briefly. Never hallucinate APIs. Use your tools to read/write files."
    )

    messages = [system, HumanMessage(content=user_query)]

    while iterations < max_iterations:
        resp = client.invoke(dept, messages)
        content = resp.get("content", "").strip()
        tool_calls_raw = resp.get("tool_calls", [])

        if not tool_calls_raw:
            # final answer
            capped = content[:RESULT_CAP]
            return {"specialist_result": capped}

        # build tool call messages and continue loop
        ai_msg = AIMessage(content=content, tool_calls=[{
            "name": tc.get("function", {}).get("name", ""),
            "args": tc.get("function", {}).get("arguments", {}),
            "id": f"coder_call_{iterations}_{i}",
            "type": "tool_call",
        } for i, tc in enumerate(tool_calls_raw)])
        messages.append(ai_msg)

        # execute tools via bigtool (only coder tools available)
        tool_blocks = bigtool.tool_injections(user_query)
        tool_blocks = [t for t in tool_blocks if t["name"] in CODER_TOOLS]

        for tc_raw in tool_calls_raw:
            fn = tc_raw.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                import json
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            try:
                tool = bigtool._registry.get(name)
                result = tool.invoke(args)
                result_str = str(result)[:8192]
            except Exception as exc:
                result_str = f"error: {exc}"
            messages.append(HumanMessage(content=f"Tool {name} result: {result_str}"))

        iterations += 1

    return {"specialist_result": "Coder specialist hit iteration limit."}
