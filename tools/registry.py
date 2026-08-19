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
    # comms
    "push_notify": "tools.comms.tools",
    "email_send": "tools.comms.tools",
    "email_search": "tools.comms.tools",
    "calendar_list": "tools.comms.tools",
    # coding
    "github_list_repos": "tools.coding.tools",
    "github_get_file": "tools.coding.tools",
    "github_create_issue": "tools.coding.tools",
    # home
    "mqtt_publish": "tools.home.tools",
    "mqtt_subscribe": "tools.home.tools",
    # media
    "yt_download": "tools.media.tools",
    "yt_info": "tools.media.tools",
    "rss_read": "tools.media.tools",
    # screen control
    "screenshot": "tools.screen.tools",
    "screenshot_region": "tools.screen.tools",
    "screenshot_window": "tools.screen.tools",
    "mouse_click": "tools.screen.tools",
    "mouse_double_click": "tools.screen.tools",
    "mouse_move": "tools.screen.tools",
    "mouse_drag": "tools.screen.tools",
    "scroll": "tools.screen.tools",
    "type_text": "tools.screen.tools",
    "key_press": "tools.screen.tools",
    "key_combo": "tools.screen.tools",
    "window_list": "tools.screen.tools",
    "window_focus": "tools.screen.tools",
    "window_move": "tools.screen.tools",
    "window_resize": "tools.screen.tools",
    "window_close": "tools.screen.tools",
    "open_url": "tools.screen.tools",
    "open_app": "tools.screen.tools",
    "open_file": "tools.screen.tools",
    "clipboard_copy": "tools.screen.tools",
    "clipboard_paste": "tools.screen.tools",
    "screen_vision": "tools.screen.tools",
    "screen_find_and_click": "tools.screen.tools",
    "screen_type_and_submit": "tools.screen.tools",
    "screen_tab_and_type": "tools.screen.tools",
    "screen_uitars": "tools.screen.tools",
    # screen automation (high-level workflows)
    "screen_compose_email": "tools.screen.automation",
    "screen_fill_form": "tools.screen.automation",
    "screen_navigate_and_act": "tools.screen.automation",
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
    "push_notify": "action",
    "email_send": "action",
    "email_search": "read",
    "calendar_list": "read",
    "github_list_repos": "read",
    "github_get_file": "read",
    "github_create_issue": "action",
    "mqtt_publish": "action",
    "mqtt_subscribe": "read",
    "yt_download": "action",
    "yt_info": "read",
    "rss_read": "read",
    # screen control
    "screenshot": "read",
    "screenshot_region": "read",
    "screenshot_window": "read",
    "mouse_click": "action",
    "mouse_double_click": "action",
    "mouse_move": "action",
    "mouse_drag": "action",
    "scroll": "action",
    "type_text": "destructive",
    "key_press": "destructive",
    "key_combo": "destructive",
    "window_list": "read",
    "window_focus": "action",
    "window_move": "action",
    "window_resize": "action",
    "window_close": "action",
    "open_url": "action",
    "open_app": "action",
    "open_file": "action",
    "clipboard_copy": "action",
    "clipboard_paste": "read",
    "screen_vision": "read",
    "screen_find_and_click": "action",
    "screen_type_and_submit": "destructive",
    "screen_tab_and_type": "destructive",
    # screen automation
    "screen_compose_email": "action",
    "screen_fill_form": "action",
    "screen_navigate_and_act": "action",
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
    "push_notify": "custom:ntfy",
    "email_send": "custom:google-api",
    "email_search": "custom:google-api",
    "calendar_list": "custom:google-api",
    "github_list_repos": "custom:pygithub",
    "github_get_file": "custom:pygithub",
    "github_create_issue": "custom:pygithub",
    "mqtt_publish": "custom:paho-mqtt",
    "mqtt_subscribe": "custom:paho-mqtt",
    "yt_download": "custom:yt-dlp",
    "yt_info": "custom:yt-dlp",
    "rss_read": "custom:feedparser",
    # screen control
    "screenshot": "custom:maim",
    "screenshot_region": "custom:maim",
    "screenshot_window": "custom:maim",
    "mouse_click": "custom:xdotool",
    "mouse_double_click": "custom:xdotool",
    "mouse_move": "custom:xdotool",
    "mouse_drag": "custom:xdotool",
    "scroll": "custom:xdotool",
    "type_text": "custom:xdotool",
    "key_press": "custom:xdotool",
    "key_combo": "custom:xdotool",
    "window_list": "custom:wmctrl",
    "window_focus": "custom:xdotool",
    "window_move": "custom:xdotool",
    "window_resize": "custom:xdotool",
    "window_close": "custom:xdotool",
    "open_url": "custom:xdg-open",
    "open_app": "custom:xdg-open",
    "open_file": "custom:xdg-open",
    "clipboard_copy": "custom:xclip",
    "clipboard_paste": "custom:xclip",
    "screen_vision": "custom:moondream",
    "screen_find_and_click": "custom:screen-automation",
    "screen_type_and_submit": "custom:screen-automation",
    "screen_tab_and_type": "custom:screen-automation",
    # screen automation
    "screen_compose_email": "custom:screen-automation",
    "screen_fill_form": "custom:screen-automation",
    "screen_navigate_and_act": "custom:screen-automation",
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

        # Dynamically load MCP tools
        try:
            from tools.mcp_loader import load_github_mcp_tools
            for t in load_github_mcp_tools():
                loaded[t.name] = t
                DEFAULT_DANGER[t.name] = "action"  # assume MCP tools are actionable
                SOURCES[t.name] = "mcp:github"
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger("don.tools.registry").error("Failed to load MCP tools: %s", exc)

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
