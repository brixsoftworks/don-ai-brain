"""Tool registry — collects every tool, applies config/tools.yaml gating.

Every tool module exports `TOOLS` (a list of langchain BaseTool). The
registry imports them all, applies enable/danger overrides from
config/tools.yaml, and exposes the enabled set for the ToolNode and the
BigTool retriever.

See docs/component-5 §5.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import yaml
from langchain_core.tools import BaseTool

from tools.specs import ToolSpec

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_TOOLS_YAML = CONFIG_DIR / "tools.yaml"

TOOL_MODULES: dict[str, str] = {
    "sys_stats": "tools.system.tools",
    "shell": "tools.system.tools",
    "file_read": "tools.system.tools",
    "file_write": "tools.system.tools",
    "file_list": "tools.system.tools",
    "web_search": "tools.web.tools",
    "weather": "tools.web.tools",
    "note_capture": "tools.memory.tools",
    "todo_add": "tools.memory.tools",
    "todo_list": "tools.memory.tools",
    "todo_done": "tools.memory.tools",
    "tts_trigger": "tools.internal.tools",
    "device_notify": "tools.internal.tools",
}

# Factory-built tools registered at app wiring time (memory/, retrieval/).
FACTORY_TOOLS: dict[str, dict] = {
    "remember": {"danger": "action", "source": "custom:memory"},
    "set_preference": {"danger": "action", "source": "custom:memory"},
    "search_memory": {"danger": "read", "source": "custom:memory"},
    "forget_memory": {"danger": "destructive", "source": "custom:memory"},
    "search_notes": {"danger": "read", "source": "custom:retrieval"},
}

DEFAULT_DANGER: dict[str, str] = {
    "sys_stats": "read",
    "shell": "destructive",
    "file_read": "read",
    "file_write": "action",
    "file_list": "read",
    "web_search": "read",
    "weather": "read",
    "note_capture": "action",
    "todo_add": "action",
    "todo_list": "read",
    "todo_done": "action",
    "tts_trigger": "action",
    "device_notify": "action",
}

SOURCES: dict[str, str] = {
    "sys_stats": "custom:psutil",
    "shell": "langchain-community",
    "file_read": "custom",
    "file_write": "custom",
    "file_list": "custom",
    "web_search": "langchain-community:duckduckgo",
    "weather": "custom:wttr.in",
    "note_capture": "custom",
    "todo_add": "custom",
    "todo_list": "custom",
    "todo_done": "custom",
    "tts_trigger": "custom",
    "device_notify": "custom",
}


class ToolConfigError(RuntimeError):
    pass


class ToolRegistry:
    def __init__(self, tools_yaml: Path = DEFAULT_TOOLS_YAML):
        self.config = self._load_config(tools_yaml)
        self._tools: dict[str, BaseTool] = {}
        self._specs: dict[str, ToolSpec] = {}
        self._collect()

    @staticmethod
    def _load_config(path: Path) -> dict:
        if not path.exists():
            raise ToolConfigError(f"tools.yaml not found: {path}")
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
        return data

    def _collect(self) -> None:
        loaded: dict[str, BaseTool] = {}
        modules = {mod for mod in TOOL_MODULES.values()}
        for mod_name in modules:
            mod = importlib.import_module(mod_name)
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, BaseTool) and not getattr(obj, "name", "").startswith("_"):
                    loaded[obj.name] = obj

        cfg_tools = self.config.get("tools", {})
        for name, tool in loaded.items():
            cfg = cfg_tools.get(name, {})
            danger = cfg.get("danger", DEFAULT_DANGER.get(name, "read"))
            enabled = bool(cfg.get("enabled", True))
            self._tools[name] = tool
            self._specs[name] = ToolSpec(
                name=name,
                description=tool.description,
                args_schema=getattr(tool, "args_schema", None),
                danger=danger,
                source=SOURCES.get(name, "custom"),
                enabled=enabled,
                tool=tool,
            )

    # ---------------------------------------------------------------- queries

    def register(self, tool: BaseTool, *, danger: str = "read", source: str = "custom") -> None:
        """Register a factory-built tool (created at app wiring time)."""
        name = tool.name
        cfg = self.config.get("tools", {}).get(name, {})
        effective_danger = cfg.get("danger", danger)
        enabled = bool(cfg.get("enabled", True))
        self._tools[name] = tool
        self._specs[name] = ToolSpec(
            name=name,
            description=tool.description,
            args_schema=getattr(tool, "args_schema", None),
            danger=effective_danger,
            source=source,
            enabled=enabled,
            tool=tool,
        )

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def enabled_specs(self) -> list[ToolSpec]:
        return [s for s in self._specs.values() if s.enabled]

    def enabled_tools(self) -> list[BaseTool]:
        return [self._tools[s.name] for s in self.enabled_specs()]

    def get(self, name: str) -> BaseTool:
        return self._tools[name]

    def get_spec(self, name: str) -> ToolSpec:
        return self._specs[name]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def enabled_names(self) -> list[str]:
        return [s.name for s in self.enabled_specs()]


def load_registry() -> ToolRegistry:
    return ToolRegistry()
