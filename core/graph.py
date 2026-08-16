"""core/graph.py — the DON brain: nodes + wiring.

Flow: classify -> route -> agent_loop -> [guard when tools land] -> responder.
Supervisor pattern per docs/component-13 §4.
"""
from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from core.checkpointer import ChatLog
from core.nodes.agent import agent_loop
from core.nodes.classify import classify_input
from core.nodes.guard import guard
from core.nodes.respond import responder
from core.nodes.router import route_model
from core.prompts import PromptBank
from core.settings import Settings
from core.state import AgentState
from models.ollama_client import OllamaClient
from models.registry import ModelRegistry, load_registry
from models.router import ModelRouter


def build_graph(
    client: OllamaClient | None = None,
    prompts: PromptBank | None = None,
    chatlog: ChatLog | None = None,
    settings: Settings | None = None,
    registry: ModelRegistry | None = None,
):
    """Assemble the compiled StateGraph. Callables are wired via partials."""
    prompts = prompts or PromptBank()
    settings = settings or Settings()
    registry = registry or load_registry()
    client = client or OllamaClient(registry, host=settings.ollama_host,
                                    gen_timeout_s=settings.ollama_timeout_gen_seconds,
                                    connect_timeout_s=settings.ollama_timeout_connect_seconds)
    chatlog = chatlog or ChatLog()
    router = ModelRouter(registry)

    g = StateGraph(AgentState)

    g.add_node("classify", partial(classify_input, client=client, prompts=prompts))
    g.add_node("route", partial(route_model, router=router, client=client))
    g.add_node("agent", partial(agent_loop, client=client, prompts=prompts, settings=settings))
    g.add_node("guard", partial(guard, prompts=prompts))
    g.add_node("respond", partial(responder, chatlog=chatlog))

    g.add_edge(START, "classify")
    g.add_edge("classify", "route")
    g.add_edge("route", "agent")
    g.add_edge("agent", "guard")
    g.add_edge("guard", "respond")
    g.add_edge("respond", END)

    return g.compile()


def build_app(**kwargs):
    """Convenience: compile + optional on-boot model pull (first boot)."""
    graph = build_graph(**kwargs)
    return graph
