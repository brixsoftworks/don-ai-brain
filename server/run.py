"""server/run.py — launch the DON bridge.

Builds the graph with the real checkpointer + vectorstore, then serves
/ws, /api/v1 and /ui bound to config/bridge.yaml.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
import yaml

from core.checkpointer import ChatLog, open_checkpointer
from core.graph import build_graph
from memory.vectorstore import VectorStore
from server.app import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("don.run")


def build(home: str | None = None):
    from pathlib import Path

    home = Path(home or os.path.expanduser("~/jarvishome"))
    os.makedirs(home, exist_ok=True)
    graph = build_graph(
        vectorstore=VectorStore(path=home / "vectordb"),
        chatlog=ChatLog(home / "chat.db"),
        checkpointer=open_checkpointer(home / "checkpoints.db"),
    )
    return create_app(graph)


def main() -> None:
    parser = argparse.ArgumentParser(description="DON device bridge")
    parser.add_argument("--host", default=None, help="override bind host")
    parser.add_argument("--port", default=None, type=int, help="override bind port")
    parser.add_argument("--home", default=None, help="jarvishome dir override (tests)")
    args = parser.parse_args()

    cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "bridge.yaml")
    with open(cfg_path) as fh:
        cfg = yaml.safe_load(fh)

    app = build(args.home)
    host = args.host or cfg["bind_host"]
    port = args.port or int(cfg["port"])
    log.info("DON bridge on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
