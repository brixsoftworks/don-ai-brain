"""Pydantic schemas — single source of truth for every parsed output.

See docs/component-4 §4.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskClassification(BaseModel):
    task_type: Literal[
        "quick_query", "system", "comms", "knowledge",
        "coding", "complex_plan", "image_analysis", "unknown",
    ]
    confidence: float = Field(ge=0, le=1, default=0.0)


class ParsedToolCall(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class MemoryFact(BaseModel):
    subject: str
    predicate: str
    object_value: str
    category: Literal["preference", "fact", "relationship", "event"]
    confidence: float = Field(ge=0, le=1)
