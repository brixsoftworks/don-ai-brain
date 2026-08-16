"""Web & information tools: search, weather, RSS.

See docs/component-5 §4 (Web & Information).
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def web_search(query: str) -> str:
    """Search the web (DuckDuckGo, keyless) and return top results with snippets."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return "web_search unavailable: install with `pip install -e .[tools]`"
    try:
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=6))
    except Exception as exc:  # noqa: BLE001
        return f"search failed: {exc}"
    if not hits:
        return "(no results)"
    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(f"{i}. {h.get('title', '')}\n   {h.get('href', '')}\n   {h.get('body', '')}")
    return "\n".join(lines)


@tool
def weather(location: str) -> str:
    """Current weather for a location (keyless via wttr.in)."""
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"https://wttr.in/{location.replace(' ', '_')}?format=3", timeout=15
        ) as resp:
            return resp.read().decode().strip()
    except Exception as exc:  # noqa: BLE001
        return f"weather fetch failed: {exc}"
