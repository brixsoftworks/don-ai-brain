"""ingest/ingest_log.py — content-hash dedup, SQLite.

Every ingested file's normalized-text hash is stored. Re-ingest only when
the hash changes. See docs/component-7 §5.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "jarvishome" / "ingest.db"


class IngestLog:
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS ingest_log (
        doc_id TEXT PRIMARY KEY,
        source_path TEXT,
        content_hash TEXT NOT NULL,
        ingested_at TEXT NOT NULL,
        chunk_count INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_ingest_source ON ingest_log(source_path);
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.executescript(self.SCHEMA)

    @staticmethod
    def content_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def doc_id(source_path: str) -> str:
        return hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:16]

    def is_stale(self, source_path: str, content_hash: str) -> bool:
        """Return True if file needs (re-)ingestion."""
        did = self.doc_id(source_path)
        with self._lock:
            row = self.conn.execute(
                "SELECT content_hash FROM ingest_log WHERE doc_id = ?", (did,)
            ).fetchone()
        if row is None:
            return True
        return row[0] != content_hash

    def record(self, source_path: str, content_hash: str, chunk_count: int = 0) -> None:
        did = self.doc_id(source_path)
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO ingest_log"
                " (doc_id, source_path, content_hash, ingested_at, chunk_count)"
                " VALUES (?, ?, ?, ?, ?)",
                (did, source_path, content_hash,
                 datetime.now(timezone.utc).isoformat(), chunk_count),
            )
            self.conn.commit()

    def stats(self) -> dict:
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) FROM ingest_log").fetchone()
        return {"total_documents": row[0] if row else 0}

    def close(self) -> None:
        self.conn.close()
