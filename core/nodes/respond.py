"""responder node — final formatting + chat_log persistence (training source).

See docs/component-1 §4.4 and §6.1.
"""
from __future__ import annotations

import logging

from core.checkpointer import ChatLog
from langchain_core.messages import AIMessage

log = logging.getLogger("don.respond")


def responder(state: dict, chatlog: ChatLog) -> dict:
    thread_id = state.get("thread_id", "default")
    reply = state.get("reply") or "I have nothing to add, operator."

    try:
        chatlog.append(thread_id=thread_id, role="assistant", content=reply)
    except Exception as exc:  # noqa: BLE001
        log.error("chat_log append failed: %s", exc)

    return {"reply": reply, "messages": [AIMessage(content=reply)]}
