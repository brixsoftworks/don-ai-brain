"""memory/vectorstore.py — the ONLY module that touches Chroma.

Docs/component-10 §3: everything else goes through this access layer.

Collections: knowledge (docs), chat (conversations), memory (facts), tools.
"""
from __future__ import annotations

import logging
from pathlib import Path

import chromadb
import yaml
from chromadb.config import Settings as ChromaSettings

log = logging.getLogger("don.vectorstore")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG = CONFIG_DIR / "vectorstore.yaml"

COLLECTIONS = ("knowledge", "chat", "memory", "tools")


class VectorStoreError(RuntimeError):
    pass


class VectorStore:
    def __init__(self, path: Path | str | None = None, config_path: Path | None = None):
        self.config = self._load_config(config_path or DEFAULT_CONFIG)
        path = Path(path or Path(self.config["path"]).expanduser())
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collections = {}
        for name in COLLECTIONS:
            cfg = self.config["collections"][name]
            self.collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": cfg["metric"]},
            )

    @staticmethod
    def _load_config(path: Path) -> dict:
        with open(path) as fh:
            return yaml.safe_load(fh) or {}

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _check_dims(vectors: list[list[float]], expected: int) -> None:
        bad = [v for v in vectors if len(v) != expected]
        if bad:
            raise VectorStoreError(
                f"dimension guard: {len(bad)} vector(s) not {expected}-dim"
            )

    # ---------------------------------------------------------------- public

    def add(self, collection: str, ids: list[str], vectors: list[list[float]],
            documents: list[str], metadatas: list[dict] | None = None) -> int:
        """Batch upsert. Same id twice → overwritten (count unchanged)."""
        cfg = self.config["collections"][collection]
        self._check_dims(vectors, cfg["dim"])
        coll = self.collections[collection]
        coll.upsert(ids=ids, embeddings=vectors, documents=documents, metadatas=metadatas)
        return len(ids)

    def search(self, collection: str, query_vector: list[float], k: int = 4,
               filters: dict | None = None, threshold: float | None = None) -> list[dict]:
        """Similarity + optional metadata filter. Returns [{id, doc, meta, score}]."""
        where = filters if filters else None
        res = self.collections[collection].query(
            query_embeddings=[query_vector],
            n_results=max(1, k),
            where=where,
        )
        out = []
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for i, cid in enumerate(ids):
            score = 1.0 - dists[i]  # cosine: distance -> similarity
            if threshold is not None and score < threshold:
                continue
            out.append({"id": cid, "doc": docs[i], "meta": metas[i] or {}, "score": score})
        return out

    def delete(self, collection: str, where: dict) -> int:
        """Delete by metadata filter (e.g. {"doc_id": ...})."""
        coll = self.collections[collection]
        result = coll.delete(where=where)
        return result if isinstance(result, int) else 0

    def count(self, collection: str) -> int:
        return self.collections[collection].count()

    def upsert_big(self, collection: str, rows: list[dict], k: int = 4) -> None:
        """Idempotent batch helper for {id, vector, doc, meta} rows."""
        self.add(
            collection,
            ids=[r["id"] for r in rows],
            vectors=[r["vector"] for r in rows],
            documents=[r["doc"] for r in rows],
            metadatas=[r.get("meta") for r in rows],
        )


def load_vectorstore(path: Path | str | None = None) -> VectorStore:
    return VectorStore(path=path)
