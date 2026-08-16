"""ingest/embedder.py — batch embedder + per-chunk-hash cache.

Wraps models/ollama_client (the low-level primitive) with batching, caching,
and model-awareness. Queries get the Qwen `Instruct:` prefix; documents embed
as plain text. See docs/component-9.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from pathlib import Path

import yaml

from models.ollama_client import OllamaClient

log = logging.getLogger("don.embedder")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG = CONFIG_DIR / "embed.yaml"

EMPTY_HASH = hashlib.sha256(b"").hexdigest()


class Embedder:
    def __init__(self, client: OllamaClient, config_path: Path | None = None,
                 cache_db: Path | str | None = None):
        self.client = client
        self.config = self._load_config(config_path or DEFAULT_CONFIG)
        self.cache_db = Path(cache_db or Path(self.config["cache_db"]).expanduser())
        self.cache_db.parent.mkdir(parents=True, exist_ok=True)
        self._init_cache()

    @staticmethod
    def _load_config(path: Path) -> dict:
        with open(path) as fh:
            return yaml.safe_load(fh) or {}

    # ----------------------------------------------------------------- cache

    def _init_cache(self) -> None:
        conn = sqlite3.connect(str(self.cache_db))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS embed_cache ("
            "chunk_hash TEXT PRIMARY KEY, model TEXT, vector BLOB)"
        )
        conn.commit()
        conn.close()

    def _cache_get(self, chunk_hash: str) -> list[float] | None:
        conn = sqlite3.connect(str(self.cache_db))
        row = conn.execute(
            "SELECT vector FROM embed_cache WHERE chunk_hash = ? AND model = ?",
            (chunk_hash, self.config["model"]),
        ).fetchone()
        conn.close()
        if not row:
            return None
        import pickle
        return pickle.loads(row[0])

    def _cache_put(self, chunk_hash: str, vector: list[float]) -> None:
        import pickle
        conn = sqlite3.connect(str(self.cache_db))
        conn.execute(
            "INSERT OR REPLACE INTO embed_cache (chunk_hash, model, vector) VALUES (?, ?, ?)",
            (chunk_hash, self.config["model"], pickle.dumps(vector)),
        )
        conn.commit()
        conn.close()

    # ---------------------------------------------------------------- public

    @staticmethod
    def chunk_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch embed documents (cached). Skips empty strings."""
        missing_idx = []
        missing = []
        vectors: dict[int, list[float]] = {}

        for i, text in enumerate(texts):
            if not text.strip():
                log.warning("skipping empty chunk")
                continue
            h = self.chunk_hash(text)
            cached = self._cache_get(h)
            if cached is not None:
                vectors[i] = cached
            else:
                missing_idx.append(i)
                missing.append((h, text))

        for start in range(0, len(missing), self.config["batch_size"]):
            batch = missing[start : start + self.config["batch_size"]]
            try:
                batch_vecs = self.client.embed([t for _, t in batch])
            except Exception as exc:  # noqa: BLE001
                log.error("embed batch failed: %s", exc)
                raise
            for (h, _), vec in zip(batch, batch_vecs):
                self._cache_put(h, vec)
                vectors[missing_idx[missing.index((h, _))]] = vec

        return [vectors[i] for i in range(len(texts)) if i in vectors]

    def embed_query(self, text: str) -> list[float]:
        """Query embedding with the Qwen instruction prefix."""
        prefixed = self.config["query_prefix"] + text
        return self.client.embed([prefixed])[0]

    def dims(self) -> int:
        return self.config["dims"]
