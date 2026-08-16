"""Tool-path smoke test — DON requests a tool, we simulate operator approval,
and verify the tool executes and the loop returns a final answer.

Usage: python3 tests/tool_test.py [approve|reject] "task text"
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.types import Command
from langchain_core.messages import HumanMessage

from core.checkpointer import ChatLog
from core.graph import build_graph
from core.settings import Settings


def run(task: str, decision: bool = True):
    db = tempfile.mktemp(suffix=".db")
    graph = build_graph(settings=Settings(), chatlog=ChatLog(db))
    config = {"configurable": {"thread_id": "tooltest"}}

    state = {
        "messages": [HumanMessage(content=task)],
        "user_id": "pa",
        "device": "laptop",
        "iterations": 0,
        "tokens_used": 0,
    }
    result = graph.invoke(state, config)
    resume_count = 0
    while result and "__interrupt__" in result and resume_count < 8:
        resume_count += 1
        for it in result["__interrupt__"]:
            print(f"  [pause {resume_count} — {it.value.get('title', 'approval')}]", flush=True)
        print("  [resuming with", "APPROVE" if decision else "REJECT", "]", flush=True)
        result = graph.invoke(Command(resume=True if decision else False), config)
    if resume_count == 8 and "__interrupt__" in result:
        print("  [test cap reached — stopping]", flush=True)

    print("task_type :", result.get("task_type"))
    print("iterations:", result.get("iterations"))
    print("tokens    :", result.get("tokens_used"))
    print("reply     :", (result.get("reply") or "")[:400])
    return result


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "approve"
    task = " ".join(sys.argv[2:]) or "Check the system stats (CPU, RAM, disk) and report them."
    run(task, decision=(mode == "approve"))
