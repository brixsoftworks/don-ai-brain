"""retrieval/tools.py — user-facing retrieval tools (docs/component-11 §5).

Built by factory over the live Retriever + FactStore.
"""
from __future__ import annotations

from langchain_core.tools import tool

from memory.store import FactStore
from retrieval.retriever import Retriever


def build_retrieval_tools(retriever: Retriever, facts: FactStore | None = None):
    @tool
    def search_notes(query: str, doc_type: str | None = None) -> str:
        """Search your own documents and notes. Optional doc_type filter (email, pdf, md, note)."""
        filters = {"type": doc_type} if doc_type else None
        blocks = retriever.blocks("knowledge", query, k=4, filters=filters)
        return "\n".join(blocks) or "(no matching documents)"

    @tool
    def search_memory(query: str) -> str:
        """Recall what you said or did before — past conversations and stored facts."""
        chat_blocks = retriever.blocks("chat", query, k=2)
        mem_blocks = []
        if facts is not None:
            try:
                qvec = retriever.embedder.embed_query(query)
                for h in facts.search(qvec, k=2):
                    m = h["meta"]
                    mem_blocks.append(
                        f"[CONTEXT]\nfrom: memory\n- {m.get('subject')} {m.get('predicate')} {m.get('object_value')} "
                        f"[{m.get('category')}]\n[/CONTEXT]"
                    )
            except Exception:
                pass
        blocks = chat_blocks + mem_blocks
        return "\n".join(blocks) or "(no matching memories)"

    return [search_notes, search_memory]
