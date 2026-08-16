"""Smoke test — runs one input through the whole graph with the dev override."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import HumanMessage

from core.checkpointer import ChatLog
from core.graph import build_graph
from core.settings import Settings


def main():
    db_path = tempfile.mktemp(suffix=".db")
    settings = Settings()

    graph = build_graph(settings=settings, chatlog=ChatLog(db_path))
    print("graph compiled:", type(graph).__name__)

    out = graph.invoke(
        {
            "messages": [HumanMessage(content="Hello DON, say hi in one short line.")],
            "user_id": "pa",
            "device": "laptop",
            "iterations": 0,
            "tokens_used": 0,
        }
    )
    print("task_type:", out.get("task_type"))
    print("model_route:", out.get("model_route"))
    print("iterations:", out.get("iterations"))
    print("tokens_used:", out.get("tokens_used"))
    print("reply:", out.get("reply"))


if __name__ == "__main__":
    main()
