"""AgentState — the shared brain-slate that flows through the graph.

See docs/component-1 §5.
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    # --- conversation ---
    messages: Annotated[list, add_messages]  # full history, appended by reducers
    # --- context ---
    user_id: str                             # single-user "pa", schema multi-user ready
    device: str                              # "android" | "laptop"
    media: dict                              # {type, path/hash, caption?}
    timestamp: str                           # ISO time of input
    # --- routing ---
    task_type: str                           # set by classify_input
    model_route: str                         # set by route_model
    # --- execution ---
    tool_results: list                       # outputs fed back to LLM
    tool_blacklist: list                     # tools disabled this conversation
    approved_calls: dict                     # {tool_call_id: bool} from guard
    cannot_use: list                         # tools the operator rejected (re-plan)
    pending_action: dict                     # {tool, args, reason} for guard
    iterations: int                          # loop counter (circuit breaker)
    tokens_used: int                         # token budget counter
    # --- memory ---
    memory: dict                             # facts pulled from long-term store
    retrieval_context: str                   # pre-fetched [CONTEXT] blocks
    # --- output ---
    reply: str                               # final response for responder
