"""memory/extractor.py — background fact extraction from chat_log turns.

Nightly/offline pass: read unprocessed turns, ask the main model to extract
MemoryFacts (JSON), validate, dedup, and store (docs/component-12 §6).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from memory.store import FactStore, MemoryFact
from models.ollama_client import OllamaClient

log = logging.getLogger("don.memory.extractor")

EXTRACT_PROMPT = (
    "Extract durable personal facts about the user from this conversation. "
    'Return STRICT JSON only: a JSON array of objects with keys '
    '"predicate", "object_value", "category" (preference|fact|relationship|event), '
    '"confidence" (0-1). Only include facts that are clearly stated and useful '
    "to remember long-term. Skip transient chatter. No commentary.\n\n"
    "Conversation:\n{turns}"
)

CONFIDENCE_THRESHOLD = 0.7


class FactExtractor:
    def __init__(self, client: OllamaClient, facts: FactStore, chat_db: Path,
                 processed_db: Path | None = None):
        self.client = client
        self.facts = facts
        self.chat_db = Path(chat_db)
        self.processed_db = Path(processed_db or self.chat_db)
        self._init_marker()

    def _init_marker(self) -> None:
        conn = sqlite3.connect(str(self.processed_db))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS extract_marker (last_id INTEGER NOT NULL)"
        )
        conn.execute("INSERT OR IGNORE INTO extract_marker (last_id) VALUES (0)")
        conn.commit()
        conn.close()

    def _last_processed(self) -> int:
        conn = sqlite3.connect(str(self.processed_db))
        row = conn.execute("SELECT last_id FROM extract_marker").fetchone()
        conn.close()
        return row[0] if row else 0

    def _mark(self, last_id: int) -> None:
        conn = sqlite3.connect(str(self.processed_db))
        conn.execute("UPDATE extract_marker SET last_id = ?", (last_id,))
        conn.commit()
        conn.close()

    def _unprocessed_turns(self, limit: int = 40) -> list[dict]:
        last = self._last_processed()
        conn = sqlite3.connect(str(self.chat_db))
        rows = conn.execute(
            "SELECT id, ts, role, content FROM chat_log WHERE id > ? ORDER BY id LIMIT ?",
            (last, limit),
        ).fetchall()
        conn.close()
        return [{"id": r[0], "ts": r[1], "role": r[2], "content": r[3]} for r in rows]

    def run(self, batch_limit: int = 40) -> int:
        """Process new turns, extract facts, return count stored. Idempotent."""
        turns = self._unprocessed_turns(batch_limit)
        if not turns:
            return 0
        text = "\n".join(
            f"{t['ts'][:16]} {t['role']}: {t['content']}" for t in turns
        )
        try:
            resp = self.client.invoke("main", [
                {"role": "user", "content": EXTRACT_PROMPT.format(turns=text[:8000])}
            ])
            payload = self._parse_json(resp["content"])
        except Exception as exc:  # noqa: BLE001
            log.error("fact extraction failed: %s", exc)
            self._mark(turns[-1]["id"])
            return 0

        stored = 0
        for item in payload:
            try:
                fact = MemoryFact(**item)
            except Exception:
                continue
            if fact.confidence < CONFIDENCE_THRESHOLD:
                continue
            if self.facts.add_fact(fact, self._embed):
                stored += 1
        self._mark(turns[-1]["id"])
        log.info("memory extractor: %d/%d facts stored", stored, len(payload))
        return stored

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self.client.embed(texts)

    @staticmethod
    def _parse_json(text: str) -> list:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return []
        return []
