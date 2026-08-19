"""router_parser — parse router model output into TaskClassification.

Strict → lenient → retry → unknown. Never blocks the graph.

See docs/component-4 §5.
"""
from __future__ import annotations

import logging
from typing import Callable

from core.parsing.schemas import TaskClassification
from core.parsing.retry import parse_with_retry

log = logging.getLogger("don.parsing.router")


def _validate_task(data: dict) -> TaskClassification:
    return TaskClassification.model_validate(data)


def parse_task_classification(
    raw: str,
    retry_fn: Callable[[str], str | None] | None = None,
) -> TaskClassification:
    """Parse raw router output → TaskClassification. Guaranteed return."""
    result, ok = parse_with_retry(raw, _validate_task, retry_fn=retry_fn)
    if ok:
        return result
    log.warning("router parse fell back to unknown")
    return TaskClassification(task_type="unknown", confidence=0.0)
