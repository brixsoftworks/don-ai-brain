"""trace/logger.py — RunLogger: custom SQLite audit fallback.

Implements LangGraph callback handlers for raw redacted run logging.
Batched writes (flush every 2s or 100 events), never blocks the graph.
See docs/component-14 §3.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from trace.redact import redact_run_metadata
from trace.store import RunStore

log = logging.getLogger("don.trace.logger")


class RunLogger:
    """Batched run logger that writes to SQLite.

    Collects events in memory and flushes periodically. Implements a
    minimal callback interface compatible with LangGraph's callback protocol.
    """

    def __init__(self, store: RunStore | None = None, flush_interval: float = 2.0,
                 flush_size: int = 100):
        self.store = store or RunStore()
        self.flush_interval = flush_interval
        self.flush_size = flush_size
        self._buffer: list[dict] = []
        self._lock = threading.Lock()
        self._current_run: dict[str, Any] = {}
        self._start_time: float = 0

        # start background flush thread
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def on_run_start(self, run_id: str | None = None, **kwargs) -> str:
        """Mark run start. Returns run_id."""
        run_id = run_id or str(uuid.uuid4())[:8]
        self._start_time = time.monotonic()
        self._current_run = {
            "run_id": run_id,
            "thread_id": kwargs.get("thread_id", "unknown"),
            "device": kwargs.get("device"),
            "user": kwargs.get("user"),
            "task_type": kwargs.get("task_type"),
            "model_route": kwargs.get("model_route"),
            "nodes_visited": [],
            "tool_calls": [],
        }
        return run_id

    def on_node_end(self, node_name: str, **kwargs) -> None:
        """Record a node visit."""
        self._current_run.setdefault("nodes_visited", []).append(node_name)

    def on_tool_call(self, tool_name: str, args: dict, status: str = "ok", **kwargs) -> None:
        """Record a tool call."""
        self._current_run.setdefault("tool_calls", []).append({
            "tool": tool_name,
            "status": status,
        })

    def on_run_end(self, run_id: str | None = None, **kwargs) -> None:
        """Flush the current run to the store."""
        duration_ms = (time.monotonic() - self._start_time) * 1000 if self._start_time else 0
        run_data = {
            **self._current_run,
            "run_id": run_id or self._current_run.get("run_id", "unknown"),
            "tokens_used": kwargs.get("tokens_used", 0),
            "iterations": kwargs.get("iterations", 0),
            "status": kwargs.get("status", "ok"),
            "error": kwargs.get("error"),
            "duration_ms": round(duration_ms, 1),
        }

        # redact before storing
        redacted = redact_run_metadata(run_data)

        with self._lock:
            self._buffer.append(redacted)
            if len(self._buffer) >= self.flush_size:
                self._flush()

        self._current_run = {}
        self._start_time = 0

    def _flush(self) -> None:
        """Write buffered runs to store. Must hold _lock."""
        if not self._buffer:
            return
        batch = self._buffer[:]
        self._buffer.clear()
        for run in batch:
            try:
                self.store.log_run(**run)
            except Exception as exc:  # noqa: BLE001
                log.error("failed to log run %s: %s", run.get("run_id"), exc)

    def _flush_loop(self) -> None:
        """Background thread: flush buffer periodically."""
        while True:
            time.sleep(self.flush_interval)
            with self._lock:
                self._flush()

    def flush(self) -> None:
        """Manual flush (e.g. on shutdown)."""
        with self._lock:
            self._flush()

    def close(self) -> None:
        """Flush and close."""
        self.flush()
        self.store.close()
