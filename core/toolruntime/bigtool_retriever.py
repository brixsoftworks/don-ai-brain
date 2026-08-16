"""BigTool retriever — semantic tool selection, drop-in for langgraph-bigtool.

Runs before each agent_loop iteration: embeds the current query with the
embeddings model and scores all registered tool descriptions by cosine
similarity, returning the top-N tool names whose schemas get injected into
DON's context.

Interface: `retrieve(query, k) -> list[str]` — a later swap can back this
with ChromaDB (docs/component-10) without touching callers.

See docs/component-6 §3.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

from models.ollama_client import OllamaClient
from tools.registry import ToolRegistry

log = logging.getLogger("don.bigtool")

KEYWORD_BONUS = 1.0


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(x * x for x in b) ** 0.5 or 1.0
    return dot / (na * nb)


class BigToolRetriever:
    def __init__(
        self,
        client: OllamaClient,
        registry: ToolRegistry,
        k: int = 6,
        embed_batch_size: int = 8,
    ):
        self.client = client
        self.registry = registry
        self.k = k
        self.embed_batch_size = embed_batch_size
        self.specs = registry.enabled_specs()
        self.embeddings: dict[str, list[float]] = {}
        self._index_built = False

    # ---------------------------------------------------------------- index

    def build_index(self) -> None:
        """Embed every enabled tool description once at startup."""
        texts = []
        for spec in self.specs:
            texts.append(f"{spec.name}: {spec.description}")
        for i in range(0, len(texts), self.embed_batch_size):
            batch = texts[i : i + self.embed_batch_size]
            try:
                vecs = self.client.embed(batch)
                for spec, vec in zip(self.specs[i : i + self.embed_batch_size], vecs):
                    self.embeddings[spec.name] = vec
            except Exception as exc:  # noqa: BLE001
                log.warning("embedding batch %d failed: %s", i // self.embed_batch_size, exc)
        self._index_built = bool(self.embeddings)
        log.info("bigtool index built: %d tools embedded", len(self.embeddings))

    # -------------------------------------------------------------- retrieve

    @staticmethod
    def _keywords(query: str) -> set[str]:
        return {w for w in re.findall(r"[a-z_]{3,}", query.lower()) if len(w) > 3}

    def _keyword_score(self, name: str, desc: str, keywords: set[str]) -> float:
        haystack = (name + " " + desc).lower()
        return KEYWORD_BONUS * sum(1 for k in keywords if k in haystack)

    def retrieve(self, query: str, k: int | None = None) -> list[str]:
        """Top-k tool names for the query (semantic + keyword boost)."""
        k = k or self.k
        if not self._index_built:
            self.build_index()
        keywords = self._keywords(query)

        if self.embeddings:
            try:
                qvec = self.client.embed_query(query)
            except Exception as exc:  # noqa: BLE001
                log.warning("embed_query failed, keyword-only fallback: %s", exc)
                qvec = None
            if qvec is not None:
                scored = [
                    (_cosine(qvec, self.embeddings[s.name])
                     + self._keyword_score(s.name, s.description, keywords) * 0.15, s.name)
                    for s in self.specs
                ]
                scored.sort(key=lambda x: x[0], reverse=True)
                return [name for _, name in scored[:k]]

        scored = [
            (self._keyword_score(s.name, s.description, keywords), s.name)
            for s in self.specs
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [name for _, name in scored[:k]]

    def tool_injections(self, query: str, k: int | None = None) -> list[dict]:
        """Tool metadata blocks to inject into the agent prompt."""
        names = self.retrieve(query, k)
        blocks = []
        for name in names:
            spec = self.registry.get_spec(name)
            schema = spec.args_schema.schema() if spec.args_schema else {}
            blocks.append({
                "name": spec.name,
                "description": spec.description,
                "args_schema": schema,
                "danger": spec.danger,
            })
        return blocks
