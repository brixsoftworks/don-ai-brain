"""Model router — maps task_type -> department -> model at runtime.

See docs/component-2 §4 and docs/component-13 §4 (supervisor pattern).
"""
from __future__ import annotations

import logging

from models.registry import ModelRegistry

log = logging.getLogger("don.router")


class ModelRouter:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    def route_task(self, task_type: str) -> str:
        """task_type -> model department name (defaults to main)."""
        return self.registry.route_task(task_type)

    def attach_route(self, state: dict) -> dict:
        """Set state.model_route based on state.task_type."""
        dept = self.route_task(state.get("task_type", "unknown"))
        state = dict(state)
        state["model_route"] = dept
        log.debug("routed task_type=%r -> dept=%s", state.get("task_type"), dept)
        return state
