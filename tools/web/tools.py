"""Web & information tools: search, weather, RSS.

See docs/component-5 §4 (Web & Information).
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def web_search(query: str) -> str:
    """Search the web using a real browser (Playwright) and return top results with snippets."""
    from tools.web.browser import _get_page
    
    try:
        import urllib.parse
        page = _get_page()
        # Direct URL navigation is much faster than filling forms
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        page.goto(search_url, wait_until="domcontentloaded")
        page.wait_for_selector(".result__snippet", timeout=5000)
        
        # Extract results using page evaluation
        results = page.eval_on_selector_all(".result", """
            elements => elements.slice(0, 6).map(el => {
                const title = el.querySelector('.result__title')?.innerText || '';
                const href = el.querySelector('.result__url')?.innerText || '';
                const body = el.querySelector('.result__snippet')?.innerText || '';
                return {title, href, body};
            })
        """)
        
        if not results:
            return "(no results)"
            
        lines = []
        for i, h in enumerate(results, 1):
            lines.append(f"{i}. {h.get('title', '')}\n   {h.get('href', '')}\n   {h.get('body', '')}")
        return "\\n".join(lines)
        
    except Exception as exc:
        return f"search failed: {exc}"


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


from tools.web.browser import BROWSER_TOOLS

TOOLS = [web_search, weather] + BROWSER_TOOLS
