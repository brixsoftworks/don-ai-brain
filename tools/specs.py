"""ToolSpec — uniform metadata for every DON tool.

See docs/component-5 §5.
"""
from __future__ import annotations

from typing import Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict


class ToolSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    args_schema: type[BaseModel] | None = None
    danger: Literal["read", "action", "destructive"] = "read"
    source: str = "custom"
    enabled: bool = True
    tool: BaseTool | None = None
