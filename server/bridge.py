"""server/bridge.py — graph execution bridged to devices.

Runs a message through the graph; when the guard interrupts for approval,
pushes an approval card over WS and parks the checkpoint; a device answer
resumes exactly where the graph paused (docs/component-16 §5).
"""
from __future__ import annotations

import json
import logging
import threading

from langgraph.types import Command

from bridge.envelope import Envelope, approval_envelope, status_envelope, text_envelope
from server.ws import SessionManager

log = logging.getLogger("don.bridge")


class Bridge:
    def __init__(self, graph, sessions: SessionManager):
        self.graph = graph
        self.sessions = sessions
        self._lock = threading.Lock()
        self._pending: dict[str, dict] = {}   # thread_id -> run config

    # ------------------------------------------------------------ status push

    def _status(self, thread_id: str, status: str, detail: str = "") -> None:
        self.sessions.send_to_thread(thread_id, status_envelope(thread_id, status, detail).to_json())

    # ------------------------------------------------------------ graph runs

    def send_text(self, device_id: str, thread_id: str, content: str) -> dict:
        """Enter a user message; returns {status, reply?, thread_id}."""
        from langchain_core.messages import HumanMessage

        config = {"configurable": {"thread_id": thread_id}}
        with self._lock:
            self._status(thread_id, "thinking")
            result = self.graph.invoke(
                {
                    "messages": [HumanMessage(content=content)],
                    "user_id": "pa",
                    "device": "laptop",
                    "iterations": 0,
                    "tokens_used": 0,
                },
                config,
            )
            return self._finish(thread_id, config, result)

    def _finish(self, thread_id: str, config: dict, result: dict) -> dict:
        """Continue stepping the graph until a reply or an approval pause."""
        if not result:
            return {"status": "error", "thread_id": thread_id}
        if "__interrupt__" in result:
            self._pending[thread_id] = config
            actions = self._collect_actions(result["__interrupt__"])
            self.sessions.send_to_thread(thread_id, approval_envelope(thread_id, actions).to_json())
            self._status(thread_id, "awaiting-approval")
            return {"status": "awaiting_approval", "thread_id": thread_id, "actions": actions}
        self._status(thread_id, "done")
        return {"status": "done", "thread_id": thread_id, "reply": result.get("reply")}

    def answer_approval(self, thread_id: str, decision: bool) -> dict:
        """Resume a parked run with the operator's decision."""
        with self._lock:
            config = self._pending.pop(thread_id, None)
            if config is None:
                return {"status": "no_pending_approval", "thread_id": thread_id}
            self._status(thread_id, "thinking")
            result = self.graph.invoke(Command(resume=decision), config)
            return self._finish(thread_id, config, result)

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _collect_actions(interrupts: list) -> list[dict]:
        actions = []
        for it in interrupts:
            value = getattr(it, "value", it)
            if isinstance(value, dict):
                actions.extend(value.get("actions", []))
        return actions
