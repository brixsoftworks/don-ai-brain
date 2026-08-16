"""SQLite checkpointer + chat_log persistence.

See docs/component-1 §6 (checkpointer) and §6.1 (chat_log table).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

DEFAULT_DB = Path(__file__).resolve().parent.parent / "jarvishome" / "don.db"


def open_checkpointer(db_path: Path = DEFAULT_DB):
    """Open (create if needed) the SQLite checkpointer in a context manager."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn)


class ChatLog:
    """Clean, append-only log of every user/agent turn — the training-data source.

    Feeds RAG over chats, memory extraction, and the future LoRA fine-tune
    corpus (docs/component-7 §2.2).
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS chat_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id TEXT NOT NULL,
        ts TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        tool_calls TEXT,
        tool_results TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_chat_log_thread ON chat_log(thread_id, ts);
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB):
        db_path = Path(db_path)
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.executescript(self.SCHEMA)

    def append(self, *, thread_id: str, role: str, content: str,
               tool_calls: str | None = None, tool_results: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO chat_log (thread_id, ts, role, content, tool_calls, tool_results)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (thread_id, datetime.now(timezone.utc).isoformat(), role, content, tool_calls, tool_results),
        )
        self.conn.commit()
        return cur.lastrowid

    def iter_thread(self, thread_id: str, limit: int = 500):
        rows = self.conn.execute(
            "SELECT ts, role, content FROM chat_log WHERE thread_id = ? ORDER BY id LIMIT ?",
            (thread_id, limit),
        ).fetchall()
        return [{"ts": r[0], "role": r[1], "content": r[2]} for r in rows]

    def close(self) -> None:
        self.conn.close()
