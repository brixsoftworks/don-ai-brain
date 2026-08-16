"""memory/tools.py — DON's memory tools (docs/component-12 §7).

Built by factory so they close over the live FactStore + Embedder.
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

from ingest.embedder import Embedder
from memory.store import FactStore, MemoryFact

log = logging.getLogger("don.memory.tools")


def build_memory_tools(facts: FactStore, embedder: Embedder):
    def _embed(texts: list[str]) -> list[list[float]]:
        return embedder.embed(texts)

    @tool
    def remember(fact: str) -> str:
        """Explicitly store a durable personal fact about the user (e.g. 'user prefers chai over coffee')."""
        f = MemoryFact(predicate="is", object_value=fact, category="fact", confidence=0.9)
        try:
            ok = facts.add_fact(f, _embed)
        except Exception as exc:  # noqa: BLE001
            return f"remember failed: {exc}"
        return f"remembered: {fact}" if ok else "already known"

    @tool
    def set_preference(preference: str) -> str:
        """Record a user preference into the long-term profile."""
        f = MemoryFact(predicate="prefers", object_value=preference, category="preference", confidence=1.0)
        try:
            ok = facts.add_fact(f, _embed)
        except Exception as exc:  # noqa: BLE001
            return f"set_preference failed: {exc}"
        return f"preference recorded: {preference}"

    @tool
    def search_memory(query: str) -> str:
        """Recall stored facts about the user (preferences, relationships, history)."""
        try:
            qvec = embedder.embed_query(query)
            hits = facts.search(qvec, k=4)
        except Exception as exc:  # noqa: BLE001
            return f"search_memory failed: {exc}"
        if not hits:
            return "(no matching memories)"
        blocks = []
        for h in hits:
            m = h["meta"]
            conf = float(m.get("confidence", 0.0))
            blocks.append(
                f"- {m.get('subject', 'user')} {m.get('predicate')} {m.get('object_value')} "
                f"[{m.get('category')}, conf {conf:.2f}]"
            )
        return "\n".join(blocks)

    @tool
    def forget_memory(subject: str, predicate: str = "") -> str:
        """Delete stored facts about a subject (or a specific predicate). Guard + confirm required."""
        deleted = facts.forget(predicate=predicate or None) if predicate else 0
        if deleted:
            return f"forgot {deleted} fact(s)"
        return f"no facts matching subject={subject} predicate={predicate or '*'}"

    return [remember, set_preference, search_memory, forget_memory]
