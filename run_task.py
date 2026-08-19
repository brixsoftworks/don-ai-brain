#!/usr/bin/env python3
"""Run a task through DON's graph — lets the agent do the work.

Usage: python3 run_task.py "your task here"
"""
import sys
import os
import json
import shutil
import tempfile
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("DON_MODELS_YAML", str(Path(__file__).resolve().parent / "config" / "models.override.yaml"))

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from core.graph import build_graph
from core.checkpointer import ChatLog, open_checkpointer
from memory.vectorstore import VectorStore


def main():
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "Find all video files in ~/Downloads, trim each one to exactly 5 seconds "
        "using ffmpeg, and merge them all into a single output video called "
        "~/Downloads/don_merged_timeline.mp4. Use the shell tool."
    )

    print(f"\n{'='*60}")
    print(f" DON TASK: {task}")
    print(f"{'='*60}\n")

    # build a hermetic graph with temp storage
    tmp = Path(tempfile.mkdtemp(prefix="don-run-"))
    vs = VectorStore(path=tmp / "vectordb")
    chatlog = ChatLog(tmp / "chat.db")
    checkpointer = open_checkpointer(tmp / "checkpoints.db")

    graph = build_graph(
        vectorstore=vs,
        chatlog=chatlog,
        checkpointer=checkpointer,
    )

    thread_id = "task-run-001"
    config = {"configurable": {"thread_id": thread_id}}

    # --- step 1: inject the user message ---
    print(f"\n[1/5] Sending task to DON...")
    result = graph.invoke(
        {
            "messages": [HumanMessage(content=task)],
            "user_id": "pa",
            "device": "laptop",
            "iterations": 0,
            "tokens_used": 0,
        },
        config,
    )
    print(f"  task_type={result.get('task_type')} model_route={result.get('model_route')} reply={str(result.get('reply',''))[:100]}")

    # --- step 2: handle the loop (auto-approve tool calls) ---
    step = 2
    max_steps = 20
    while step < max_steps:
        if not result:
            print(f"[!] Empty result from graph")
            break

        # check for approval interrupt
        if "__interrupt__" in result:
            print(f"\n[{step}/{max_steps}] DON requests approval for:")
            for it in result["__interrupt__"]:
                value = getattr(it, "value", it)
                if isinstance(value, dict):
                    for action in value.get("actions", []):
                        tool = action.get("tool", "?")
                        args = action.get("args", {})
                        danger = action.get("danger", "action")
                        print(f"  [{danger}] {tool}({json.dumps(args, default=str)[:200]})")

            # AUTO-APPROVE for this demo
            print(f"  → Auto-approving...")
            result = graph.invoke(Command(resume=True), config)
            step += 1
            continue

        # check for final reply
        reply = result.get("reply")
        if reply:
            print(f"\n{'='*60}")
            print(f" DON's REPLY:")
            print(f"{'='*60}")
            print(reply)
            print(f"{'='*60}")
            break

        # check for pending tool calls (non-interrupt path)
        msgs = result.get("messages", [])
        if msgs:
            last = msgs[-1]
            if hasattr(last, "tool_calls") and last.tool_calls:
                # tool calls present but no interrupt — shouldn't happen
                # with guard, but handle gracefully
                print(f"  [{step}] Tool calls pending (no interrupt)")
                break

        # if we got here with no reply and no interrupt, step again
        print(f"  [{step}] Stepping graph... task_type={result.get('task_type')} route={result.get('model_route')}")
        result = graph.invoke(None, config)
        step += 1

    # --- cleanup ---
    chatlog.close()
    checkpointer.conn.close()
    shutil.rmtree(tmp, ignore_errors=True)
    print("\nDone.")


if __name__ == "__main__":
    main()
