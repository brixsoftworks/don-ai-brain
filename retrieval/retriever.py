"""retrieval/retriever.py — query cleanup → embed → search → context blocks.

Rule-based query normalization (no interactive LLM rewrite, per docs/component-11 §3),
then per-collection search through the vector store, formatted as budgeted
[CONTEXT] blocks.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from ingest.embedder import Embedder
from memory.vectorstore import VectorStore
from retrieval.context import format_block, join_blocks, trim_to_budget

log = logging.getLogger("don.retriever")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG = CONFIG_DIR / "retrieval.yaml"

FILLER = re.compile(
    r"\b(what|who|where|when|why|how|did|does|do|the|a|an|of|for|and|or|me|my|we|about|say|said|i|you|is|was|were)\b",
    re.IGNORECASE,
)


def clean_query(raw: str) -> str:
    """Light rule-based cleanup: strip filler, keep entities and time hints."""
    q = re.sub(r"[^\w\s]", " ", raw)
    q = FILLER.sub(" ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q or raw


class Retriever:
    def __init__(self, vs: VectorStore, embedder: Embedder, config_path: Path | None = None):
        self.vs = vs
        self.embedder = embedder
        with open(config_path or DEFAULT_CONFIG) as fh:
            self.config = yaml.safe_load(fh) or {}

    def search(self, collection: str, query: str, k: int | None = None,
               filters: dict | None = None) -> list[dict]:
        """Search one collection; returns scored hits [{id, doc, meta, score}]."""
        k = k or self.config.get("default_k", 4)
        try:
            qvec = self.embedder.embed_query(clean_query(query))
            hits = self.vs.search(collection, qvec, k=k, filters=filters)
        except Exception as exc:  # noqa: BLE001
            log.warning("retrieval search failed (%s): %s", collection, exc)
            return []
        return hits

    def blocks(self, collection: str, query: str, k: int | None = None,
               filters: dict | None = None, budget_tokens: int | None = None) -> list[str]:
        """Search + format + budget-trim into [CONTEXT] blocks."""
        budget_tokens = budget_tokens or self.config.get("budget_tokens", 800)
        hits = self.search(collection, query, k=k, filters=filters)
        blocks = [format_block(collection, {**h["meta"], "confidence": h["score"]}, h["doc"]) for h in hits]
        return trim_to_budget(blocks, budget_tokens)

    def context(self, collections: list[str], query: str, k: int = 2,
                budget_tokens: int | None = None) -> str:
        """Multi-collection pre-fetch → one budgeted context string."""
        budget_tokens = budget_tokens or self.config.get("budget_tokens", 800)
        all_blocks: list[str] = []
        for c in collections:
            all_blocks += self.blocks(c, query, k=k, budget_tokens=budget_tokens)
        return join_blocks(trim_to_budget(all_blocks, budget_tokens))
