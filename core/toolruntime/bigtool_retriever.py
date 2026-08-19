"""BigTool retriever — semantic tool selection on the Chroma `tools` collection.

Runs before each agent_loop iteration: embeds the query with the embeddings
model, searches the `tools` collection (seeded at startup from the registry),
and returns the top-N tool names. Keyword scoring is a fallback when the
store or embedder is unavailable. Drop-in replacement for langgraph-bigtool.

See docs/component-6 §3.
"""
from __future__ import annotations

import logging
import re

from ingest.embedder import Embedder
from memory.vectorstore import VectorStore
from tools.registry import ToolRegistry

log = logging.getLogger("don.bigtool")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(x * x for x in b) ** 0.5 or 1.0
    return dot / (na * nb)


class BigToolRetriever:
    def __init__(
        self,
        client,
        registry: ToolRegistry,
        vs: VectorStore | None = None,
        embedder: Embedder | None = None,
        k: int = 15,
    ):
        self.client = client
        self.registry = registry
        self.vs = vs
        self.embedder = embedder
        self.k = k
        self._seeded = False

    # ---------------------------------------------------------------- seed

    def seed(self) -> None:
        """Embed every enabled tool description into the Chroma `tools` collection."""
        if self.vs is None or self.embedder is None:
            log.info("bigtool: no vector store provided — keyword-only mode")
            self._seeded = True
            return
        specs = self.registry.enabled_specs()
        if self.vs.count("tools") >= len(specs):
            self._seeded = True
            return
        docs = [f"{s.name}: {s.description}" for s in specs]
        try:
            vectors = self.embedder.embed(docs)
        except Exception as exc:  # noqa: BLE001
            log.warning("bigtool seed embed failed: %s", exc)
            self._seeded = True
            return
        rows = []
        for spec, vec in zip(specs, vectors):
            rows.append({
                "id": spec.name,
                "vector": vec,
                "doc": f"{spec.name}: {spec.description}",
                "meta": {"source": spec.source, "danger": spec.danger},
            })
        self.vs.upsert_big("tools", rows)
        self._seeded = True
        log.info("bigtool seeded: %d tools", len(specs))

    # -------------------------------------------------------------- retrieve

    @staticmethod
    def _keywords(query: str) -> set[str]:
        return {w for w in re.findall(r"[a-z_]{3,}", query.lower()) if len(w) > 3}

    def _keyword_score(self, name: str, desc: str, keywords: set[str]) -> float:
        hay = (name + " " + desc).lower()
        return sum(1 for kw in keywords if kw in hay)

    def retrieve(self, query: str, k: int | None = None) -> list[str]:
        """Top-k tool names for the query (semantic search + keyword fallback)."""
        k = k or self.k
        if not self._seeded:
            self.seed()
        keywords = self._keywords(query)

        # Always include tools explicitly named in the query
        all_names = {s.name for s in self.registry.enabled_specs()}
        explicit = [n for n in all_names if n in query.lower()]
        remaining_k = k - len(explicit)

        semantic: list[str] = []
        if self.vs is not None and self.embedder is not None:
            try:
                qvec = self.embedder.embed_query(query)
                hits = self.vs.search("tools", qvec, k=remaining_k * 2)
                if hits:
                    boosted = sorted(
                        hits,
                        key=lambda h: h["score"] + 0.15 * self._keyword_score(h["id"], "", keywords),
                        reverse=True,
                    )
                    semantic = [h["id"] for h in boosted[:remaining_k] if h["id"] not in explicit]
            except Exception as exc:  # noqa: BLE001
                log.warning("bigtool search failed, keyword fallback: %s", exc)
        else:
            specs = self.registry.enabled_specs()
            scored = sorted(
                specs,
                key=lambda s: self._keyword_score(s.name, s.description, keywords),
                reverse=True,
            )
            semantic = [s.name for s in scored[:remaining_k] if s.name not in explicit]

        # Always inject essential primitives to ensure agent doesn't get stuck without them
        base_tools = {
            "screen_vision", "mouse_click", "type_text", "open_url", "key_press",
            "browser_start", "browser_execute", "browser_close", "web_search",
            "file_write", "file_read", "search_memory"
        }
        final_list = explicit + semantic
        for base in base_tools:
            if base in all_names and base not in final_list:
                final_list.append(base)

        return final_list

    def tool_injections(self, query: str, k: int | None = None) -> list[dict]:
        """Tool metadata blocks to inject into the agent prompt."""
        names = self.retrieve(query, k)
        blocks = []
        for name in names:
            spec = self.registry.get_spec(name)
            if isinstance(spec.args_schema, dict):
                schema = spec.args_schema
            else:
                schema = spec.args_schema.model_json_schema() if spec.args_schema else {}
            blocks.append({
                "name": spec.name,
                "description": spec.description,
                "args_schema": schema,
                "danger": spec.danger,
            })
        return blocks
