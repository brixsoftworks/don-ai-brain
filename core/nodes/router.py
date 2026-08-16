"""route_model node — task_type -> department model, loads specialists.

See docs/component-1 §4.2.
"""
from __future__ import annotations

import logging

from models.ollama_client import OllamaClient
from models.router import ModelRouter

log = logging.getLogger("don.route")


def route_model(state: dict, router: ModelRouter, client: OllamaClient) -> dict:
    dept = router.route_task(state.get("task_type", "unknown"))
    if dept != "main":
        load_s = client.load(dept)
        log.info("loaded specialist dept=%s in %.1fs", dept, load_s)
    return {"model_route": dept}
