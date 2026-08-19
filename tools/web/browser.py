"""DOM-based Browser Automation using Playwright.

This allows the agent to control a browser via code without needing vision/screenshots.
"""
import textwrap
from pathlib import Path
from langchain_core.tools import tool

_PLAYWRIGHT_INSTANCE = None
_BROWSER_CONTEXT = None
_CURRENT_PAGE = None

def _get_page():
    global _PLAYWRIGHT_INSTANCE, _BROWSER_CONTEXT, _CURRENT_PAGE
    if _CURRENT_PAGE is not None and not _CURRENT_PAGE.is_closed():
        return _CURRENT_PAGE
    
    from playwright.sync_api import sync_playwright
    
    if _PLAYWRIGHT_INSTANCE is None:
        _PLAYWRIGHT_INSTANCE = sync_playwright().start()
        
    try:
        import requests
        resp = requests.get("http://localhost:9222/json/version", timeout=1)
        if resp.status_code == 200:
            _BROWSER_CONTEXT = _PLAYWRIGHT_INSTANCE.chromium.connect_over_cdp("http://localhost:9222")
            if len(_BROWSER_CONTEXT.pages) > 0:
                _CURRENT_PAGE = _BROWSER_CONTEXT.pages[0]
            else:
                _CURRENT_PAGE = _BROWSER_CONTEXT.new_page()
            return _CURRENT_PAGE
    except Exception:
        pass
        
    profile_dir = Path.home() / "jarvishome" / ".browser_profiles" / "whatsapp"
    profile_dir.parent.mkdir(parents=True, exist_ok=True)
    
    _BROWSER_CONTEXT = _PLAYWRIGHT_INSTANCE.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        channel="chrome",
        headless=False,
        no_viewport=True,
    )
    if len(_BROWSER_CONTEXT.pages) > 0:
        _CURRENT_PAGE = _BROWSER_CONTEXT.pages[0]
    else:
        _CURRENT_PAGE = _BROWSER_CONTEXT.new_page()
    return _CURRENT_PAGE

def _extract_dom(page):
    """Returns a simplified text representation of the DOM with element IDs."""
    script = """
    () => {
        let idCounter = 1;
        const result = [];
        const processNode = (node, depth) => {
            if (node.nodeType === Node.TEXT_NODE) {
                const text = node.textContent.trim();
                if (text) {
                    result.push('  '.repeat(depth) + text);
                }
                return;
            }
            if (node.nodeType !== Node.ELEMENT_NODE) return;
            
            // Skip hidden elements and script/style tags
            const style = window.getComputedStyle(node);
            if (style.display === 'none' || style.visibility === 'hidden') return;
            if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG'].includes(node.tagName)) return;
            
            const isInteractive = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(node.tagName) || 
                                   node.onclick != null || 
                                   node.getAttribute('role') === 'button' ||
                                   node.getAttribute('contenteditable') === 'true';
            
            let line = '  '.repeat(depth) + `<${node.tagName.toLowerCase()}`;
            
            if (isInteractive) {
                const eid = `el-${idCounter++}`;
                node.setAttribute('data-don-id', eid);
                line += ` don-id="${eid}"`;
            }
            
            // Include important attributes
            for (const attr of ['id', 'name', 'title', 'placeholder', 'value', 'href', 'aria-label', 'role']) {
                const val = node.getAttribute(attr);
                if (val) line += ` ${attr}="${val}"`;
            }
            line += '>';
            result.push(line);
            
            for (const child of node.childNodes) {
                processNode(child, depth + 1);
            }
        };
        processNode(document.body, 0);
        return result.join('\\n');
    }
    """
    return page.evaluate(script)

@tool
def browser_start(url: str) -> str:
    """Launch the browser (if not already running) and navigate to a URL. 
    
    Returns a simplified DOM structure. Interactive elements will have a `don-id="el-N"` attribute.
    """
    try:
        page = _get_page()
        page.goto(url, wait_until="networkidle")
        dom = _extract_dom(page)
        return dom[:10000] + ("\n... [DOM TRUNCATED]" if len(dom) > 10000 else "")
    except Exception as e:
        return f"Error: {e}"

@tool
def browser_execute(python_script: str) -> str:
    """Execute a Playwright python script on the current page to perform actions.
    
    The script has access to a 'page' variable (the Playwright Page object).
    Use 'data-don-id' to select interactive elements from the DOM provided by browser_start.
    
    Example:
        page.locator('[data-don-id="el-5"]').click()
        page.locator('[data-don-id="el-6"]').fill("Hello")
        page.keyboard.press("Enter")
        page.wait_for_timeout(1000)
        
    Returns the simplified DOM after execution.
    """
    try:
        page = _get_page()
        
        # Strip markdown code blocks if the agent includes them
        if python_script.startswith("```"):
            lines = python_script.strip().split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            python_script = "\n".join(lines)
            
        local_env = {"page": page}
        exec(textwrap.dedent(python_script), {}, local_env)
        
        # Give UI time to settle after actions
        page.wait_for_timeout(1000)
        
        dom = _extract_dom(page)
        return dom[:10000] + ("\n... [DOM TRUNCATED]" if len(dom) > 10000 else "")
    except Exception as e:
        return f"Script execution failed: {e}"

@tool
def browser_close() -> str:
    """Close the browser and save profile state."""
    global _PLAYWRIGHT_INSTANCE, _BROWSER_CONTEXT, _CURRENT_PAGE
    try:
        if _BROWSER_CONTEXT:
            _BROWSER_CONTEXT.close()
        if _PLAYWRIGHT_INSTANCE:
            _PLAYWRIGHT_INSTANCE.stop()
        _PLAYWRIGHT_INSTANCE = None
        _BROWSER_CONTEXT = None
        _CURRENT_PAGE = None
        return "Browser closed."
    except Exception as e:
        return f"Error: {e}"

BROWSER_TOOLS = [browser_start, browser_execute, browser_close]
