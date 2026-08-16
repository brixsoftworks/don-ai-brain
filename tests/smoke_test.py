"""Answer-only smoke test — no tools, plain reply through the whole graph."""
import sys

sys.path.insert(0, "/home/mullainathan/Documents/Coding/Projects/pa ai agent")

from langchain_core.messages import HumanMessage

from tests._helpers import temp_graph, thread_config


def main():
    graph, cleanup = temp_graph()
    try:
        print("graph compiled:", type(graph).__name__)
        out = graph.invoke(
            {
                "messages": [HumanMessage(content="Hello DON, say hi in one short line.")],
                "user_id": "pa",
                "device": "laptop",
                "iterations": 0,
                "tokens_used": 0,
            },
            thread_config("smoke"),
        )
        print("task_type:", out.get("task_type"))
        print("model_route:", out.get("model_route"))
        print("iterations:", out.get("iterations"))
        print("tokens_used:", out.get("tokens_used"))
        print("reply:", out.get("reply"))
    finally:
        cleanup()


if __name__ == "__main__":
    main()
