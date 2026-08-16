"""retrieve node — automatic pre-fetch for knowledge/memory tasks.

Runs between route and agent when the classifier tagged the task
knowledge/memory: one cheap search fills state.retrieval_context so DON
starts with relevant context (docs/component-11 §2).
"""
from __future__ import annotations

import logging

from retrieval.retriever import Retriever

log = logging.getLogger("don.retrieve")

# task_type -> collections to pre-fetch (docs/component-11 §2)
PREFETCH_MAP = {
    "knowledge": ["knowledge"],
    "memory": ["chat", "memory"],
}


def retrieve(state: dict, retriever: Retriever) -> dict:
    task = state.get("task_type", "unknown")
    collections = PREFETCH_MAP.get(task, [])
    if not collections:
        return {"retrieval_context": ""}
    last_user = next(
        (m.content for m in reversed(state.get("messages", []))
         if getattr(m, "type", "") == "human"),
        "",
    )
    context = retriever.context(collections, last_user, k=2)
    log.info("pre-fetched %d chars from %s for task=%s", len(context), collections, task)
    return {"retrieval_context": context}
