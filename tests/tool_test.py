"""Tool-path smoke test — DON requests a tool, we simulate operator approval,
and verify the tool executes and the loop returns a final answer.

Usage: python3 tests/tool_test.py [approve|reject] "task text"
"""
import sys

sys.path.insert(0, "/home/mullainathan/Documents/Coding/Projects/pa ai agent")

from langgraph.types import Command
from langchain_core.messages import HumanMessage

from tests._helpers import temp_graph, thread_config


def run(task: str, decision: bool = True, max_resumes: int = 4):
    graph, cleanup = temp_graph()
    try:
        config = thread_config("tooltest")
        state = {
            "messages": [HumanMessage(content=task)],
            "user_id": "pa",
            "device": "laptop",
            "iterations": 0,
            "tokens_used": 0,
        }
        result = graph.invoke(state, config)
        resume_count = 0
        while result and "__interrupt__" in result and resume_count < max_resumes:
            resume_count += 1
            print(f"  [pause {resume_count} — {result['__interrupt__'][0].value.get('title')}]", flush=True)
            result = graph.invoke(Command(resume=True if decision else False), config)
        print("task_type :", result.get("task_type"))
        print("iterations:", result.get("iterations"))
        print("tokens    :", result.get("tokens_used"))
        print("reply     :", (result.get("reply") or "")[:400])
        print("tools ran :", [r for r in result.get("tool_results", [])])
        return result
    finally:
        cleanup()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "approve"
    task = " ".join(sys.argv[2:]) or "Check the system stats (CPU, RAM, disk) and report them."
    run(task, decision=(mode == "approve"))
