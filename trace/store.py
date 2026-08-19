"""trace/store.py — run_log SQLite table + rollup queries.

Raw runs stored 30 days; daily rollups keep aggregate stats for 1 year.
See docs/component-14 §4.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "jarvishome" / "trace.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS run_log (
    run_id TEXT PRIMARY KEY,
    thread_id TEXT,
    ts TEXT NOT NULL,
    device TEXT,
    user TEXT,
    task_type TEXT,
    model_route TEXT,
    model_used TEXT,
    nodes_visited TEXT,
    tool_calls TEXT,
    tokens_used INTEGER DEFAULT 0,
    iterations INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok',
    error TEXT,
    duration_ms REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_run_log_thread ON run_log(thread_id, ts);
CREATE INDEX IF NOT EXISTS idx_run_log_ts ON run_log(ts);

CREATE TABLE IF NOT EXISTS daily_rollup (
    date TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL,
    PRIMARY KEY (date, metric)
);
"""


class RunStore:
    """SQLite-backed run log and daily rollup storage."""

    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.executescript(SCHEMA)

    def log_run(self, run_id: str, thread_id: str, **kwargs) -> None:
        """Insert or replace a run record."""
        ts = kwargs.get("ts", datetime.now(timezone.utc).isoformat())
        tool_calls = kwargs.get("tool_calls")
        if isinstance(tool_calls, list):
            tool_calls = json.dumps(tool_calls)

        nodes_visited = kwargs.get("nodes_visited")
        if isinstance(nodes_visited, list):
            nodes_visited = json.dumps(nodes_visited)

        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO run_log"
                " (run_id, thread_id, ts, device, user, task_type, model_route,"
                "  model_used, nodes_visited, tool_calls, tokens_used, iterations,"
                "  status, error, duration_ms)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id, thread_id, ts,
                    kwargs.get("device"), kwargs.get("user"),
                    kwargs.get("task_type"), kwargs.get("model_route"),
                    kwargs.get("model_used"), nodes_visited, tool_calls,
                    kwargs.get("tokens_used", 0), kwargs.get("iterations", 0),
                    kwargs.get("status", "ok"), kwargs.get("error"),
                    kwargs.get("duration_ms", 0),
                ),
            )
            self.conn.commit()

    def recent_runs(self, limit: int = 50) -> list[dict]:
        """Fetch recent runs."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM run_log ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        cols = [d[0] for d in self.conn.execute("PRAGMA table_info(run_log)").fetchall()]
        return [dict(zip([c[1] for c in self.conn.execute("PRAGMA table_info(run_log)").fetchall()], r)) for r in rows]

    def prune(self, days: int = 30) -> int:
        """Delete runs older than `days`."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            cur = self.conn.execute("DELETE FROM run_log WHERE ts < ?", (cutoff,))
            self.conn.commit()
        return cur.rowcount

    def daily_rollup(self, date_str: str | None = None) -> dict:
        """Compute daily aggregate stats."""
        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day_start = date_str + "T00:00:00"
        day_end = date_str + "T23:59:59"

        with self._lock:
            rows = self.conn.execute(
                "SELECT COUNT(*), AVG(duration_ms), AVG(tokens_used),"
                " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END)"
                " FROM run_log WHERE ts BETWEEN ? AND ?",
                (day_start, day_end),
            ).fetchone()

        total = rows[0] or 0
        avg_ms = rows[1] or 0
        avg_tokens = rows[2] or 0
        errors = rows[3] or 0

        metrics = {
            "total_runs": total,
            "avg_duration_ms": round(avg_ms, 1),
            "avg_tokens": round(avg_tokens, 1),
            "error_count": errors,
            "error_rate": round(errors / total, 3) if total else 0,
        }

        # persist rollup
        with self._lock:
            for metric, value in metrics.items():
                self.conn.execute(
                    "INSERT OR REPLACE INTO daily_rollup (date, metric, value) VALUES (?, ?, ?)",
                    (date_str, metric, value),
                )
            self.conn.commit()

        return metrics

    def close(self) -> None:
        self.conn.close()
