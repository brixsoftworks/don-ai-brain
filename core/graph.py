"""core/graph.py — the DON brain: nodes + wiring.

Loop: classify → route → agent ⇄ guard ⇄ tool_node → respond.
Supervisor pattern per docs/component-13 §4; tool loop per component-1 §3–4.
"""
from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph
from langchain_core.messages import AIMessage

from core.checkpointer import ChatLog, open_checkpointer
from core.nodes.agent import agent_loop
from core.nodes.classify import classify_input
from core.nodes.guard import guard
from core.nodes.respond import responder
from core.nodes.router import route_model
from core.nodes.toolnode import tool_node
from core.prompts import PromptBank
from core.settings import Settings
from core.state import AgentState
from core.toolruntime.bigtool_retriever import BigToolRetriever
from core.toolruntime.executor import ToolExecutor
from models.ollama_client import OllamaClient
from models.registry import ModelRegistry, load_registry
from models.router import ModelRouter
from tools.registry import ToolRegistry


def _has_pending_calls(state: dict) -> bool:
    for m in reversed(state.get("messages", [])):
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            return bool(m.tool_calls)
    return False


def build_graph(
    client: OllamaClient | None = None,
    prompts: PromptBank | None = None,
    chatlog: ChatLog | None = None,
    settings: Settings | None = None,
    registry: ModelRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
    checkpointer=None,
):
    """Assemble the compiled StateGraph. Callables are wired via partials."""
    prompts = prompts or PromptBank()
    settings = settings or Settings()
    registry = registry or load_registry()
    client = client or OllamaClient(registry, host=settings.ollama_host,
                                    gen_timeout_s=settings.ollama_timeout_gen_seconds,
                                    connect_timeout_s=settings.ollama_timeout_connect_seconds)
    chatlog = chatlog or ChatLog()
    tool_registry = tool_registry or ToolRegistry()
    executor = ToolExecutor(
        pool_size=4, default_timeout=settings.tool_timeout_seconds
    )
    bigtool = BigToolRetriever(client, tool_registry)
    router = ModelRouter(registry)

    g = StateGraph(AgentState)

    g.add_node("classify", partial(classify_input, client=client, prompts=prompts))
    g.add_node("route", partial(route_model, router=router, client=client))
    g.add_node("agent", partial(agent_loop, client=client, prompts=prompts,
                                settings=settings, bigtool=bigtool))
    g.add_node("guard", partial(guard, prompts=prompts, registry=tool_registry))
    g.add_node("tool", partial(tool_node, registry=tool_registry, executor=executor,
                               timeout=settings.tool_timeout_seconds,
                               output_cap=settings.tool_output_cap_bytes))
    g.add_node("respond", partial(responder, chatlog=chatlog))

    g.add_edge(START, "classify")
    g.add_edge("classify", "route")
    g.add_edge("route", "agent")
    g.add_edge("agent", "guard")
    g.add_conditional_edges(
        "guard",
        _has_pending_calls,
        {True: "tool", False: "respond"},
    )
    g.add_edge("tool", "agent")
    g.add_edge("respond", END)

    if checkpointer is None:
        checkpointer = open_checkpointer()
    return g.compile(checkpointer=checkpointer)


def build_app(**kwargs):
    """Convenience: compile with optional on-boot model pull (first boot)."""
    graph = build_graph(**kwargs)
    return graph
