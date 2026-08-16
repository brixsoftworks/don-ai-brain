"""Memory & personal tools: long-term memory, notes vault, todo list.

Backed by a simple JSON/SQLite store for the foundation; the vector-store
backing lands with components 9–12.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tools import tool

HOME = Path.home() / "jarvishome"
MEMORY_FILE = HOME / "memory.json"
TODO_DB = HOME / "todo.db"

MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_memory() -> list[dict]:
    if not MEMORY_FILE.exists():
        return []
    try:
        return json.loads(MEMORY_FILE.read_text())
    except json.JSONDecodeError:
        return []


def _save_memory(items: list[dict]) -> None:
    MEMORY_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False))


@tool
def memory_write(fact: str) -> str:
    """Permanently store a personal fact about the user (e.g. 'user dislikes cilantro')."""
    items = _load_memory()
    items.append({"fact": fact, "ts": datetime.now(timezone.utc).isoformat()})
    _save_memory(items)
    return f"remembered: {fact}"


@tool
def memory_search(topic: str) -> str:
    """Search stored personal facts by keyword/topic."""
    items = _load_memory()
    hits = [m for m in items if topic.lower() in m["fact"].lower()]
    if not hits:
        return "(no matching memories)"
    return "\n".join(f"- {m['fact']}" for m in hits[-10:])


NOTES_FILE = HOME / "notes" / "notes.md"


@tool
def note_capture(note: str) -> str:
    """Append a note to the personal notes vault (~/jarvishome/notes/notes.md)."""
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(NOTES_FILE, "a") as fh:
        fh.write(f"- {datetime.now().strftime('%Y-%m-%d %H:%M')}: {note}\n")
    return "note saved"


def _todo_conn() -> sqlite3.Connection:
    TODO_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(TODO_DB))
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS todo (id INTEGER PRIMARY KEY, item TEXT NOT NULL, done INTEGER DEFAULT 0);"
    )
    return conn


@tool
def todo_add(item: str) -> str:
    """Add a task to the todo list."""
    conn = _todo_conn()
    conn.execute("INSERT INTO todo (item) VALUES (?)", (item,))
    conn.commit()
    conn.close()
    return f"added: {item}"


@tool
def todo_list() -> str:
    """List todo items, pending ones first."""
    conn = _todo_conn()
    rows = conn.execute("SELECT id, item, done FROM todo ORDER BY done, id").fetchall()
    conn.close()
    if not rows:
        return "(empty todo list)"
    return "\n".join(f"{r[1]} {'[done]' if r[2] else '[pending]'} (id {r[0]})" for r in rows)


@tool
def todo_done(task_id: int) -> str:
    """Mark a todo item done by its id."""
    conn = _todo_conn()
    cur = conn.execute("UPDATE todo SET done = 1 WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return f"done {task_id}" if cur.rowcount else f"no todo with id {task_id}"
