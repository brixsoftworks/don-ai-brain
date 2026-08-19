"""core/subgraphs/reasoner.py — deep-reasoning specialist sub-graph.

Runs with the reasoner model (deepseek-r1:7b) for complex planning,
math, and deep analysis tasks. Returns step-by-step reasoning capped at 2 KB.

See docs/component-13 §3.
"""
from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage

from core.prompts import PromptBank
from models.ollama_client import OllamaClient

log = logging.getLogger("don.subgraph.reasoner")

RESULT_CAP = 2048


def reasoner_node(
    state: dict,
    client: OllamaClient,
    prompts: PromptBank,
    *,
    user_name: str = "Operator",
) -> dict:
    """Run the reasoner specialist: step-by-step deep analysis."""
    user_query = state.get("specialist_query", "")

    system = prompts.system_for(
        "reasoner",
        user_name=user_name,
        device=state.get("device", "laptop"),
        memory_context=str(state.get("memory") or ""),
    )
    system = type(system)(
        content=system.content
        + "\n\nThink step by step. Show your reasoning clearly, then conclude. "
        "Use tools if needed for data access."
    )

    messages = [system, HumanMessage(content=user_query)]

    try:
        resp = client.invoke("reasoner", messages)
        content = resp.get("content", "").strip()[:RESULT_CAP]
        return {"specialist_result": content}
    except Exception as exc:  # noqa: BLE001
        log.error("reasoner specialist failed: %s", exc)
        return {"specialist_result": f"Reasoning failed: {exc}"}
