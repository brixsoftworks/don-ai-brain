"""core/graph.py — the DON brain: nodes + wiring.

Loop: classify → route → [retrieve pre-fetch] → agent ⇄ guard ⇄ tool → respond.
Supervisor pattern per docs/component-13 §4; tool loop per component-1 §3–4.
Specialist sub-graphs (coder/vision/reasoner) per component-13 §3.
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
from core.nodes.retrieve import retrieve
from core.nodes.router import route_model
from core.nodes.toolnode import tool_node
from core.prompts import PromptBank
from core.settings import Settings
from core.state import AgentState
from core.subgraphs.coder import coder_node
from core.subgraphs.reasoner import reasoner_node
from core.subgraphs.vision import vision_node
from core.toolruntime.bigtool_retriever import BigToolRetriever
from core.toolruntime.executor import ToolExecutor
from ingest.embedder import Embedder
from memory.store import FactStore
from memory.tools import build_memory_tools
from memory.vectorstore import VectorStore
from models.ollama_client import OllamaClient
from models.registry import ModelRegistry, load_registry
from models.router import ModelRouter
from retrieval.retriever import Retriever
from retrieval.tools import build_retrieval_tools
from tools.registry import ToolRegistry

SPECIALIST_TASKS = {"coding", "image_analysis", "complex_plan"}


def _has_pending_calls(state: dict) -> bool:
    """Check only the MOST RECENT AIMessage for pending tool calls.

    Scanning the full history causes re-routing to guard after the agent
    already returned a final reply.
    """
    for m in reversed(state.get("messages", [])):
        if isinstance(m, AIMessage):
            return bool(getattr(m, "tool_calls", None))
    return False


def _route_specialist(state: dict) -> str:
    """Decide whether to go to a specialist sub-graph or directly to agent."""
    task = state.get("task_type", "unknown")
    specialist_map = {
        "coding": "coder_specialist",
        "image_analysis": "vision_specialist",
        "complex_plan": "reasoner_specialist",
    }
    if task in specialist_map:
        return specialist_map[task]
    return "agent"


def build_graph(
    client: OllamaClient | None = None,
    prompts: PromptBank | None = None,
    chatlog: ChatLog | None = None,
    settings: Settings | None = None,
    registry: ModelRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
    vectorstore: VectorStore | None = None,
    embedder: Embedder | None = None,
    retriever: Retriever | None = None,
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

    vectorstore = vectorstore or VectorStore()
    embedder = embedder or Embedder(client)
    facts = FactStore(vectorstore)
    retriever = retriever or Retriever(vectorstore, embedder)

    # register factory-built memory/retrieval tools, then let BigTool see them
    for t in build_memory_tools(facts, embedder):
        tool_registry.register(t, danger="action", source="custom:memory")
    for t in build_retrieval_tools(retriever, facts):
        tool_registry.register(t, danger="read", source="custom:retrieval")

    executor = ToolExecutor(pool_size=4, default_timeout=settings.tool_timeout_seconds)
    bigtool = BigToolRetriever(client, tool_registry, vs=vectorstore, embedder=embedder)
    router = ModelRouter(registry)

    g = StateGraph(AgentState)

    g.add_node("classify", partial(classify_input, client=client, prompts=prompts))
    g.add_node("route", partial(route_model, router=router, client=client))
    g.add_node("retrieve", partial(retrieve, retriever=retriever))
    g.add_node("agent", partial(agent_loop, client=client, prompts=prompts,
                                settings=settings, bigtool=bigtool))
    g.add_node("guard", partial(guard, prompts=prompts, registry=tool_registry))
    g.add_node("tool", partial(tool_node, registry=tool_registry, executor=executor,
                               timeout=settings.tool_timeout_seconds,
                               output_cap=settings.tool_output_cap_bytes))
    g.add_node("respond", partial(responder, chatlog=chatlog))

    # specialist sub-graphs (narrowed tool sets, capped results)
    g.add_node("coder_specialist", partial(
        coder_node, client=client, prompts=prompts, settings=settings, bigtool=bigtool,
    ))
    g.add_node("vision_specialist", partial(
        vision_node, client=client, prompts=prompts,
    ))
    g.add_node("reasoner_specialist", partial(
        reasoner_node, client=client, prompts=prompts,
    ))

    g.add_edge(START, "classify")
    g.add_edge("classify", "route")

    # route: retrieve for knowledge/memory tasks, specialist for coding/vision/reasoner, else agent
    g.add_conditional_edges(
        "route",
        lambda s: (
            "retrieve" if s.get("task_type") in ("knowledge", "memory")
            else _route_specialist(s)
        ),
        {
            "retrieve": "retrieve",
            "agent": "agent",
            "coder_specialist": "coder_specialist",
            "vision_specialist": "vision_specialist",
            "reasoner_specialist": "reasoner_specialist",
        },
    )

    g.add_edge("retrieve", "agent")
    g.add_edge("agent", "guard")
    g.add_conditional_edges(
        "guard",
        _has_pending_calls,
        {True: "tool", False: "respond"},
    )
    g.add_edge("tool", "agent")

    # specialists return a result → go to responder
    g.add_edge("coder_specialist", "respond")
    g.add_edge("vision_specialist", "respond")
    g.add_edge("reasoner_specialist", "respond")

    g.add_edge("respond", END)

    if checkpointer is None:
        checkpointer = open_checkpointer()
    return g.compile(checkpointer=checkpointer)


def build_app(**kwargs):
    """Convenience: compile with optional on-boot model pull (first boot)."""
    graph = build_graph(**kwargs)
    return graph
