"""tools/screen/tools.py — full desktop automation: screenshot, mouse, keyboard, window control.

Wayland-native implementation for GNOME:
- XDG Desktop Portal for screenshots (works on Wayland)
- ydotool for mouse/keyboard input (works on Wayland via uinput)
- xdg-open for app launching (DE-agnostic)
- wl-clipboard for clipboard (Wayland-native)
- moondream vision model for screen reading
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from langchain_core.tools import tool

SCREENSHOT_DIR = Path(tempfile.gettempdir()) / "don_screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)


def _run(cmd: str, timeout: int = 10) -> str:
    """Run a shell command and return output."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode != 0 and err:
            return f"error: {err}"
        return out or "(ok)"
    except subprocess.TimeoutExpired:
        return "error: command timed out"
    except Exception as e:
        return f"error: {e}"


# ─── SCREENSHOT (XDG Desktop Portal — Wayland-native) ─────────────────

def _portal_screenshot(dst: str) -> bool:
    """Take a screenshot via XDG Desktop Portal and save to dst path.

    Returns True on success.
    """
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib

        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result = bus.call_sync(
            'org.freedesktop.portal.Desktop',
            '/org/freedesktop/portal/desktop',
            'org.freedesktop.portal.Screenshot',
            'Screenshot',
            GLib.Variant('(sa{sv})', ('', {'interactive': GLib.Variant('b', False)})),
            GLib.VariantType('(o)'),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        request_path = result.unpack()[0]

        loop = GLib.MainLoop()
        success = [False]

        def on_signal(conn, sender, path, interface, signal, params, user_data):
            if signal == 'Response':
                code, results = params.unpack()
                if code == 0 and 'uri' in results:
                    uri = results['uri']
                    if uri.startswith('file://'):
                        src = uri[7:]
                        subprocess.run(['cp', src, dst], check=True)
                        success[0] = True
                loop.quit()

        bus.signal_subscribe(
            'org.freedesktop.portal.Desktop',
            'org.freedesktop.portal.Request',
            'Response',
            request_path,
            None,
            Gio.DBusSignalFlags.NONE,
            on_signal,
            None,
        )
        GLib.timeout_add_seconds(10, loop.quit)
        loop.run()
        return success[0]
    except Exception:
        return False


def _screenshot_impl(region: str = "") -> str:
    """Internal screenshot implementation (no @tool decorator)."""
    ts = str(SCREENSHOT_DIR / f"screen_{Path(tempfile.mktemp()).name}.png")
    if region:
        parts = [int(x.strip()) for x in region.split(",")]
        if len(parts) == 4:
            x, y, w, h = parts
            full = str(SCREENSHOT_DIR / f"_full_{Path(tempfile.mktemp()).name}.png")
            ok = _portal_screenshot(full)
            if ok and os.path.exists(full):
                try:
                    from PIL import Image
                    img = Image.open(full)
                    cropped = img.crop((x, y, x + w, y + h))
                    cropped.save(ts)
                    os.unlink(full)
                    size_kb = os.path.getsize(ts) / 1024
                    return f"screenshot saved: {ts} ({size_kb:.0f} KB)"
                except Exception as e:
                    return f"crop failed: {e}"
            return "screenshot failed"
    else:
        ok = _portal_screenshot(ts)
        if ok and os.path.exists(ts):
            size_kb = os.path.getsize(ts) / 1024
            return f"screenshot saved: {ts} ({size_kb:.0f} KB)"
    return "screenshot failed"


@tool
def screenshot(region: str = "") -> str:
    """Take a screenshot of the full screen or a region.

    Args:
        region: optional region as "x,y,w,h" (e.g. "0,0,1920,1080"). Empty = full screen.
    Returns: path to the saved screenshot PNG.
    """
    return _screenshot_impl(region)


@tool
def screenshot_region(x: int, y: int, w: int, h: int) -> str:
    """Take a screenshot of a specific rectangular region.

    Args:
        x: left edge pixel coordinate.
        y: top edge pixel coordinate.
        w: width in pixels.
        h: height in pixels.
    Returns: path to the saved screenshot PNG.
    """
    return _screenshot_impl(f"{x},{y},{w},{h}")


@tool
def screenshot_window(window_title: str = "") -> str:
    """Take a screenshot of the full screen (Wayland doesn't support per-window capture).

    Args:
        window_title: ignored on Wayland — captures full screen.
    """
    return screenshot()


# ─── MOUSE (ydotool — Wayland-native via uinput) ──────────────────────

@tool
def mouse_click(x: int, y: int, button: str = "left") -> str:
    """Click at screen coordinates.

    Args:
        x: horizontal pixel coordinate.
        y: vertical pixel coordinate.
        button: mouse button — "left", "right", or "middle".
    """
    btn = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}.get(button, "0xC0")
    _run(f"ydotool mousemove --absolute -- {x} {y}")
    _run(f"ydotool click {btn}")
    return f"clicked ({button}) at ({x}, {y})"


@tool
def mouse_double_click(x: int, y: int) -> str:
    """Double-click at screen coordinates.

    Args:
        x: horizontal pixel coordinate.
        y: vertical pixel coordinate.
    """
    _run(f"ydotool mousemove --absolute -- {x} {y}")
    _run(f"ydotool click --next 0xC0")
    _run(f"ydotool click 0xC0")
    return f"double-clicked at ({x}, {y})"


@tool
def mouse_move(x: int, y: int) -> str:
    """Move the mouse cursor to screen coordinates without clicking.

    Args:
        x: horizontal pixel coordinate.
        y: vertical pixel coordinate.
    """
    _run(f"ydotool mousemove --absolute -- {x} {y}")
    return f"mouse moved to ({x}, {y})"


@tool
def mouse_drag(x1: int, y1: int, x2: int, y2: int) -> str:
    """Click and drag from one coordinate to another.

    Args:
        x1: start horizontal coordinate.
        y1: start vertical coordinate.
        x2: end horizontal coordinate.
        y2: end vertical coordinate.
    """
    _run(f"ydotool mousemove --absolute -- {x1} {y1}")
    _run(f"ydotool mousedown 0xC0")
    _run(f"ydotool mousemove --absolute -- {x2} {y2}")
    _run(f"ydotool mouseup 0xC0")
    return f"dragged from ({x1},{y1}) to ({x2},{y2})"


@tool
def scroll(direction: str = "down", amount: int = 5) -> str:
    """Scroll the mouse wheel.

    Args:
        direction: "up" or "down".
        amount: number of scroll clicks (5 = one notch).
    """
    # ydotool scroll: positive = down, negative = up
    delta = abs(amount) if direction == "down" else -abs(amount)
    _run(f"ydotool mousemove --wheel -- {delta} 0")
    return f"scrolled {direction} {amount} clicks"


# ─── KEYBOARD (ydotool — Wayland-native via uinput) ───────────────────

@tool
def type_text(text: str, delay_ms: int = 20) -> str:
    """Type text at the current cursor position.

    Args:
        text: the text to type.
        delay_ms: delay between keystrokes in milliseconds (default 20).
    """
    # ydotool type handles special characters better than raw keycodes
    _run(f"ydotool type -- '{text}'", timeout=30)
    return f"typed: {text[:80]}{'...' if len(text) > 80 else ''}"


@tool
def key_press(keys: str) -> str:
    """Press a key or key combination.

    Args:
        keys: key name with + separator (e.g. "Return", "ctrl+c", "alt+Tab", "ctrl+shift+t").
              Uses ydotool key names (evdev codes): https://github.com/ydotool/ydotool#key-list
              Common: Return, Tab, Escape, Space, BackSpace, Delete
              Modifiers: ctrl, alt, shift, meta/super
    """
    _run(f"ydotool key {keys}")
    return f"pressed: {keys}"


@tool
def key_combo(keys: str) -> str:
    """Press a keyboard shortcut (same as key_press, for clarity).

    Args:
        keys: combo like "ctrl+c", "alt+F4", "ctrl+shift+n".
    """
    _run(f"ydotool key {keys}")
    return f"shortcut: {keys}"


# ─── WINDOW MANAGEMENT (GNOME Shell DBus + fallback) ───────────────────

@tool
def window_list() -> str:
    """List all open windows with their titles.

    Uses GNOME Shell DBus on Wayland. Falls back to wmctrl.
    """
    # Try GNOME Shell eval first
    result = _run(
        """gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell """
        """--method org.gnome.Shell.Eval '"""
        """JSON.stringify(global.get_window_actors().map((a,i) => ({"""
        """id: i, title: a.meta_window.get_title(), app: a.meta_window.get_wm_class(),"""
        """ focused: a.meta_window.has_focus(), minimized: a.meta_window.is_minimized(),"""
        """ x: a.meta_window.get_frame_rect().x, y: a.meta_window.get_frame_rect().y,"""
        """ w: a.meta_window.get_frame_rect().width, h: a.meta_window.get_frame_rect().height"""
        """})))'"""
    )
    if result and result.startswith("(true,"):
        import json
        try:
            json_str = result.split("', '")[0].split("',")[0].split("(true, '")[1]
            json_str = json_str.rstrip("')")
            windows = json.loads(json_str)
            lines = []
            for w in windows:
                if w.get("title"):
                    focus = " [FOCUSED]" if w.get("focused") else ""
                    mini = " [minimized]" if w.get("minimized") else ""
                    lines.append(
                        f"[{w['id']}] {w['title']} ({w.get('app', '?')}) "
                        f"at ({w['x']},{w['y']}) {w['w']}x{w['h']}{focus}{mini}"
                    )
            return "\n".join(lines) if lines else "no windows"
        except Exception:
            pass

    # Fallback: wmctrl
    raw = _run("wmctrl -l -G 2>/dev/null")
    if raw and raw != "(ok)" and "error" not in raw:
        return raw

    # Fallback: xdotool (XWayland only)
    wids = _run("xdotool search --name '' 2>/dev/null").strip().split("\n")
    lines = []
    for wid in wids[:20]:
        wid = wid.strip()
        if not wid:
            continue
        name = _run(f"xdotool getwindowname {wid}")
        if name and name != "(ok)":
            lines.append(f"[{wid}] {name}")
    return "\n".join(lines) if lines else "no windows found"


@tool
def window_focus(window_title: str) -> str:
    """Focus a window by partial title match.

    Args:
        window_title: partial or full window title to search for.
    """
    # Try wmctrl first
    result = _run(f"wmctrl -a '{window_title}' 2>/dev/null")
    if result == "(ok)" or "error" not in result:
        return f"focused window: {window_title}"

    # Fallback: xdotool
    wid = _run(f"xdotool search --name '{window_title}' 2>/dev/null | head -1")
    if wid and wid.strip().isdigit():
        _run(f"xdotool windowactivate {wid.strip()}")
        return f"focused window: {wid.strip()}"

    return f"window not found: {window_title}"


@tool
def window_move(window_title: str, x: int, y: int) -> str:
    """Move a window to specific coordinates.

    Args:
        window_title: partial window title to match.
        x: target x coordinate.
        y: target y coordinate.
    """
    wid = _run(f"wmctrl -l 2>/dev/null | grep -i '{window_title}' | head -1 | awk '{{print $1}}'")
    if wid and wid.strip():
        _run(f"wmctrl -i -r '{wid.strip()}' -e 0,{x},{y},-1,-1 2>/dev/null")
        return f"moved window to ({x}, {y})"
    return f"window not found: {window_title}"


@tool
def window_resize(window_title: str, w: int, h: int) -> str:
    """Resize a window.

    Args:
        window_title: partial window title to match.
        w: new width in pixels.
        h: new height in pixels.
    """
    wid = _run(f"wmctrl -l 2>/dev/null | grep -i '{window_title}' | head -1 | awk '{{print $1}}'")
    if wid and wid.strip():
        _run(f"wmctrl -i -r '{wid.strip()}' -e 0,-1,-1,{w},{h} 2>/dev/null")
        return f"resized to {w}x{h}"
    return f"window not found: {window_title}"


@tool
def window_close(window_title: str) -> str:
    """Close a window by title.

    Args:
        window_title: partial window title to match.
    """
    wid = _run(f"wmctrl -l 2>/dev/null | grep -i '{window_title}' | head -1 | awk '{{print $1}}'")
    if wid and wid.strip():
        _run(f"wmctrl -i -r '{wid.strip()}' -c 2>/dev/null")
        return f"closed window: {window_title}"
    return f"window not found: {window_title}"


# ─── APPLICATION LAUNCHING ───────────────────────────────────────────

@tool
def open_url(url: str) -> str:
    """Open a URL in the default browser.

    Args:
        url: the URL to open (e.g. "https://gmail.com").
    """
    _run(f"nohup xdg-open '{url}' &>/dev/null &")
    return f"opened: {url}"


@tool
def open_app(app_name: str) -> str:
    """Launch an application by name.

    Args:
        app_name: application name or .desktop file (e.g. "firefox", "google-chrome", "code").
    """
    _run(f"nohup {app_name} &>/dev/null &")
    return f"launched: {app_name}"


@tool
def open_file(file_path: str) -> str:
    """Open a file with its default application.

    Args:
        file_path: path to the file to open.
    """
    p = Path(file_path).expanduser().resolve()
    _run(f"nohup xdg-open '{p}' &>/dev/null &")
    return f"opened: {p}"


# ─── CLIPBOARD (wl-clipboard — Wayland-native) ────────────────────────

@tool
def clipboard_copy(text: str) -> str:
    """Copy text to the system clipboard.

    Args:
        text: text to copy.
    """
    proc = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
    proc.communicate(text.encode())
    return f"copied to clipboard: {text[:80]}{'...' if len(text) > 80 else ''}"


@tool
def clipboard_paste() -> str:
    """Paste text from the system clipboard (read-only)."""
    return _run("wl-paste 2>/dev/null")


# ─── SCREEN VISION (screenshot + moondream describe) ──────────────────

@tool
def screen_vision(question: str = "What do you see on screen?") -> str:
    """Take a screenshot and describe what's on screen using vision analysis.

    Args:
        question: what to look for on screen (e.g. "Where is the search box?", "What apps are open?").
    Returns: description of the screen contents.
    """
    ts = str(SCREENSHOT_DIR / f"vision_{Path(tempfile.mktemp()).name}.png")
    ok = _portal_screenshot(ts)
    if not ok or not os.path.exists(ts):
        return "screenshot failed"

    with open(ts, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    try:
        import ollama
        client = ollama.Client()
        resp = client.chat(
            model="moondream:latest",
            messages=[{
                "role": "user",
                "content": question,
                "images": [img_b64],
            }],
        )
        return resp.get("message", {}).get("content", "(no description)")
    except Exception as e:
        return f"vision analysis failed: {e}"


@tool
def screen_find_and_click(element_description: str) -> str:
    """Take a screenshot, find a UI element by description, and click on it.

    Combines screenshot + vision + click in one step. Use this instead of
    chaining screen_vision and mouse_click separately.

    Args:
        element_description: what to find and click (e.g. "Compose button", "search box", "send button").
    """
    ts = str(SCREENSHOT_DIR / f"find_{Path(tempfile.mktemp()).name}.png")
    ok = _portal_screenshot(ts)
    if not ok or not os.path.exists(ts):
        return "screenshot failed"

    with open(ts, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    try:
        import ollama
        client = ollama.Client()
        resp = client.chat(
            model="moondream:latest",
            messages=[{
                "role": "user",
                "content": (
                    f"Find the '{element_description}' on this screen. "
                    f"Return ONLY two numbers: the x and y pixel coordinates of the CENTER of that element, "
                    f"separated by a comma. No other text. Example: 450, 300"
                ),
                "images": [img_b64],
            }],
        )
        vision_text = resp.get("message", {}).get("content", "").strip()

        # Parse coordinates from vision response
        import re
        nums = re.findall(r'\d+', vision_text)
        if len(nums) >= 2:
            # Vision model coordinates are in screenshot space (portal resolution)
            # Need to scale to display space (ydotool uses physical coords)
            sx = int(nums[0])
            sy = int(nums[1])

            # Get display size to compute scale factor
            try:
                xr = _run("xrandr --query 2>/dev/null | grep 'eDP-1 connected' | grep -oP '\\d+x\\d+' | head -1")
                if 'x' in xr:
                    dw, dh = [int(v) for v in xr.split('x')]
                else:
                    dw, dh = 3840, 2400  # fallback
            except Exception:
                dw, dh = 3840, 2400

            # Get screenshot size
            from PIL import Image
            with Image.open(ts) as img:
                sw, sh = img.size

            # Scale coordinates
            scale_x = dw / sw if sw > 0 else 1.5
            scale_y = dh / sh if sh > 0 else 1.5
            click_x = int(sx * scale_x)
            click_y = int(sy * scale_y)

            # Click
            _run(f"ydotool mousemove --absolute -- {click_x} {click_y}")
            time.sleep(0.2)
            _run(f"ydotool click 0xC0")
            return (
                f"Found '{element_description}' at vision coords ({sx},{sy}) "
                f"→ screen coords ({click_x},{click_y}). Clicked."
            )
        else:
            return f"Could not parse coordinates from vision: {vision_text}"
    except Exception as e:
        return f"find_and_click failed: {e}"


@tool
def screen_type_and_submit(text: str) -> str:
    """Type text at the current cursor position and press Enter.

    Args:
        text: the text to type.
    """
    _run(f"ydotool type -- '{text}'", timeout=30)
    time.sleep(0.2)
    _run("ydotool key Return")
    return f"typed and submitted: {text[:80]}{'...' if len(text) > 80 else ''}"


@tool
def screen_tab_and_type(text: str) -> str:
    """Press Tab to move to the next field, then type text.

    Args:
        text: the text to type in the next field.
    """
    _run("ydotool key Tab")
    time.sleep(0.3)
    _run(f"ydotool type -- '{text}'", timeout=30)
    return f"tabbed and typed: {text[:80]}{'...' if len(text) > 80 else ''}"


@tool
def screen_uitars(instruction: str, max_loops: int = 10) -> str:
    """Use UI-TARS vision agent to perform a screen task autonomously.
    Takes screenshots, analyzes them with a vision model, and performs
    mouse/keyboard actions to complete the task.

    Args:
        instruction: natural language task (e.g. "click the Send button", "open Firefox and go to google.com").
        max_loops: max number of screenshot→act cycles (default 10, max 20).
    Returns: summary of actions taken.
    """
    from tools.screen.uitars_agent import run_task
    max_loops = min(max_loops, 20)
    ok = run_task(instruction, max_loops=max_loops)
    return f"UI-TARS completed: {instruction}" if ok else f"UI-TARS stopped after {max_loops} loops: {instruction}"


TOOLS = [
    screenshot, screenshot_region, screenshot_window,
    mouse_click, mouse_double_click, mouse_move, mouse_drag,
    scroll,
    type_text, key_press, key_combo,
    window_list, window_focus, window_move, window_resize, window_close,
    open_url, open_app, open_file,
    clipboard_copy, clipboard_paste,
    screen_vision, screen_find_and_click, screen_type_and_submit, screen_tab_and_type,
    screen_uitars,
]
