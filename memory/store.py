"""memory/store.py — fact store (Chroma `memory`) + user profile.

Facts carry metadata: subject, predicate, object_value, category, confidence,
ts. The user profile is a curated, ~300-token summary rebuilt from the
highest-confidence facts (docs/component-12 §4).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from memory.vectorstore import VectorStore

HOME = Path.home() / "jarvishome"
PROFILE_FILE = HOME / "profile.json"

CATEGORIES = ("preference", "fact", "relationship", "event")


class MemoryFact(BaseModel):
    subject: str = "user"
    predicate: str
    object_value: str
    category: Literal["preference", "fact", "relationship", "event"] = "fact"
    confidence: float = 1.0


class FactStore:
    def __init__(self, vs: VectorStore, profile_file: Path = PROFILE_FILE):
        self.vs = vs
        self.profile_file = profile_file

    # ----------------------------------------------------------------- facts

    def add_fact(self, fact: MemoryFact, embed_fn, overwrite_threshold: float = 0.1) -> bool:
        """Store a fact; confidence-gated overwrite (docs/component-12 §3).

        `embed_fn(texts) -> list[vectors]` is the embedder used for the
        fact document.
        """
        now = datetime.now(timezone.utc).isoformat()
        existing = self._find(fact.predicate, fact.object_value)
        if existing:
            old_conf = float(existing["meta"].get("confidence", 0.0))
            if fact.confidence < old_conf + overwrite_threshold:
                return False
            self.vs.delete("memory", {"$and": [
                {"predicate": fact.predicate}, {"object_value": fact.object_value},
            ]})
        doc = f"{fact.subject} {fact.predicate} {fact.object_value}"
        vector = embed_fn([doc])[0]
        fid = f"{fact.subject}:{fact.predicate}:{fact.object_value}:{now}"
        self.vs.add(
            "memory",
            ids=[fid],
            vectors=[vector],
            documents=[doc],
            metadatas=[{
                "subject": fact.subject,
                "predicate": fact.predicate,
                "object_value": fact.object_value,
                "category": fact.category,
                "confidence": fact.confidence,
                "ts": now,
            }],
        )
        return True

    def _find(self, predicate: str, object_value: str) -> dict | None:
        coll = self.vs.collections["memory"]
        try:
            res = coll.get(where={"$and": [
                {"predicate": predicate}, {"object_value": object_value},
            ]}, limit=1)
        except Exception:
            return None
        ids = res.get("ids") or []
        if not ids:
            return None
        return {"id": ids[0], "meta": (res.get("metadatas") or [{}])[0]}

    def search(self, query_vector: list[float], k: int = 4, category: str | None = None) -> list[dict]:
        """Semantic fact recall against the memory collection (query pre-embedded)."""
        filters = {"category": category} if category else None
        return self.vs.search("memory", query_vector, k=k, filters=filters)

    def forget(self, fact_id: str | None = None, predicate: str | None = None) -> int:
        if fact_id:
            coll = self.vs.collections["memory"]
            coll.delete(ids=[fact_id])
            return 1
        if predicate:
            return self.vs.delete("memory", {"predicate": predicate})
        return 0

    # ---------------------------------------------------------------- profile

    def build_profile(self, token_cap: int = 300) -> str:
        """Rebuild the {memory_context} string from top-confidence facts."""
        coll = self.vs.collections["memory"]
        try:
            res = coll.get(limit=100)
        except Exception:
            return ""
        metas = res.get("metadatas") or []
        facts = sorted(metas, key=lambda m: float(m.get("confidence", 0.0)), reverse=True)
        lines = []
        used = 0
        for m in facts:
            line = f"- {m.get('subject', 'user')} {m.get('predicate')} {m.get('object_value')}"
            if used + len(line) > token_cap * 4:
                break
            lines.append(line)
            used += len(line)
        text = "\n".join(lines)
        self.profile_file.write_text(json.dumps(
            {"built_at": datetime.now(timezone.utc).isoformat(), "profile": text}, indent=2
        ))
        return text
