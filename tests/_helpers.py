"""Shared test helpers: hermetic graph with temp storage."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.checkpointer import ChatLog, open_checkpointer
from memory.vectorstore import VectorStore


def temp_graph(**kwargs):
    import shutil
    from pathlib import Path

    from core.graph import build_graph

    tmp = Path(tempfile.mkdtemp(prefix="don-test-"))
    vs = VectorStore(path=tmp / "vectordb")
    checkpointer = open_checkpointer(tmp / "checkpoints.db")
    chatlog = ChatLog(tmp / "chat.db")

    def _cleanup():
        shutil.rmtree(tmp, ignore_errors=True)

    graph = build_graph(
        vectorstore=vs,
        chatlog=chatlog,
        checkpointer=checkpointer,
        **kwargs,
    )
    return graph, _cleanup


def thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}
