#!/usr/bin/env python3
"""UI-TARS agent for DON — uses Wayland screenshot/input + Ollama UI-TARS model."""
import base64, json, os, re, subprocess, sys, time
from pathlib import Path
from PIL import Image

SCREENSHOT_DIR = Path("/tmp/don_screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    except: return ""

def screenshot():
    ts = str(SCREENSHOT_DIR / f"uitars_{int(time.time()*1000)}.png")
    # Reuse DON's portal screenshot
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from tools.screen.tools import _portal_screenshot
        ok = _portal_screenshot(ts)
    except Exception:
        ok = False

    if not ok or not os.path.exists(ts):
        return None, 2560, 1600, 1.5

    img = Image.open(ts)
    w, h = img.size
    # Resize to max 1280 wide for speed
    if w > 1280:
        ratio = 1280 / w
        img = img.resize((1280, int(h * ratio)), Image.LANCZOS)
    img.save(ts, optimize=True, quality=85)

    with open(ts, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    scale = 3840 / w if w > 0 else 1.5
    os.unlink(ts)
    return b64, w, h, scale

def execute_action(action_type, start_box, end_box=None, content=None, key=None, direction=None, screen_w=2560, screen_h=1600, scale=1.5):
    def parse_box(box):
        if not box: return None
        nums = re.findall(r'[\d.]+', box)
        if len(nums) >= 4:
            x1, y1, x2, y2 = [float(n) for n in nums[:4]]
            cx = ((x1 + x2) / 2 / 1000) * screen_w * scale
            cy = ((y1 + y2) / 2 / 1000) * screen_h * scale
            return int(cx), int(cy)
        return None

    if action_type == "finished":
        return True

    coords = parse_box(start_box) if start_box else None

    if action_type == "click" and coords:
        run(f"ydotool mousemove --absolute -- {coords[0]} {coords[1]}")
        time.sleep(0.05)
        run("ydotool click 0xC0")
    elif action_type == "left_double" and coords:
        run(f"ydotool mousemove --absolute -- {coords[0]} {coords[1]}")
        time.sleep(0.05)
        run("ydotool click --next 0xC0")
        run("ydotool click 0xC0")
    elif action_type == "right_single" and coords:
        run(f"ydotool mousemove --absolute -- {coords[0]} {coords[1]}")
        time.sleep(0.05)
        run("ydotool click 0xC1")
    elif action_type == "type" and content:
        text = content.replace("\\n", "\n").replace("\n", " ")
        run(f"ydotool type -- '{text}'", timeout=30)
    elif action_type == "hotkey" and key:
        run(f"ydotool key {key}")
    elif action_type == "scroll":
        if coords:
            run(f"ydotool mousemove --absolute -- {coords[0]} {coords[1]}")
            time.sleep(0.05)
        d = direction or "down"
        delta = 10 if d == "down" else -10 if d == "up" else 10 if d == "right" else -10
        run(f"ydotool mousemove --wheel -- {delta} 0")
    elif action_type == "drag":
        end_coords = parse_box(end_box) if end_box else None
        if coords and end_coords:
            run(f"ydotool mousemove --absolute -- {coords[0]} {coords[1]}")
            time.sleep(0.05)
            run("ydotool mousedown 0xC0")
            time.sleep(0.05)
            run(f"ydotool mousemove --absolute -- {end_coords[0]} {end_coords[1]}")
            time.sleep(0.05)
            run("ydotool mouseup 0xC0")

    time.sleep(0.3)
    return False

def parse_response(text):
    """Parse UI-TARS format: Thought: ... Action: action_type(params)"""
    thought = ""
    action_type = ""
    start_box = None
    end_box = None
    content = None
    key = None
    direction = None

    # Extract thought
    m = re.search(r'Thought:\s*(.+?)(?:Action:|$)', text, re.DOTALL)
    if m: thought = m.group(1).strip()

    # Extract last Action line (model sometimes outputs multiple)
    actions = re.findall(r'Action:\s*(\w+)\((.+?)\)', text, re.DOTALL)
    if actions:
        action_type, params_str = actions[-1]

        for param_m in re.finditer(r'(\w+)=["\'](.+?)["\']', params_str):
            k, v = param_m.group(1), param_m.group(2)
            if k == "start_box": start_box = v
            elif k == "end_box": end_box = v
            elif k == "content": content = v
            elif k == "key": key = v
            elif k == "direction": direction = v
    else:
        for act in ["finished", "wait", "call_user"]:
            if re.search(r'\b' + act + r'\b', text):
                action_type = act
                break

    return thought, action_type, start_box, end_box, content, key, direction

def run_task(instruction, max_loops=15, model="ui-tars:2b"):
    import ollama

    SYSTEM_PROMPT = """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

## Output Format
Thought: ...
Action: ...

## Action Space
click(start_box='[x1, y1, x2, y2]')
left_double(start_box='[x1, y1, x2, y2]')
right_single(start_box='[x1, y1, x2, y2]')
drag(start_box='[x1, y1, x2, y2]', end_box='[x3, y3, x4, y4]')
hotkey(key='')
type(content='')
scroll(start_box='[x1, y1, x2, y2]', direction='down')
wait()
finished()

Coordinates are normalized 0-1000 (left=0, right=1000, top=0, bottom=1000).
"""

    client = ollama.Client()
    start_time = time.time()

    for i in range(max_loops):
        elapsed = time.time() - start_time
        if elapsed > 60:
            print(f"[TIMEOUT] {elapsed:.1f}s elapsed, stopping")
            break

        # Take screenshot
        b64, sw, sh, scale = screenshot()
        if not b64:
            print(f"[Loop {i}] Screenshot failed")
            break

        # Call model with raw API for better control
        user_msg = f"User Instruction: {instruction}"
        t0 = time.time()
        resp = client.generate(
            model=model,
            prompt=SYSTEM_PROMPT + user_msg,
            images=[b64],
            options={"temperature": 0.6, "num_predict": 512}
        )
        model_time = time.time() - t0

        reply = resp.response if hasattr(resp, 'response') else resp.get("response", "")
        print(f"[Loop {i}] Model: {model_time:.1f}s | {reply[:120]}")

        # Parse response
        thought, action_type, start_box, end_box, content, key, direction = parse_response(reply)

        if not action_type:
            print(f"[Loop {i}] No action parsed, retrying...")
            continue

        # Execute action
        done = execute_action(action_type, start_box, end_box, content, key, direction,
                             screen_w=sw or 2560, screen_h=sh or 1600, scale=scale or 1.5)

        total = time.time() - start_time
        print(f"[Loop {i}] Action: {action_type} | Total: {total:.1f}s")

        if done or action_type == "finished":
            print(f"[DONE] Task completed in {total:.1f}s")
            return True

    total = time.time() - start_time
    print(f"[DONE] Stopped after {total:.1f}s")
    return False

if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "click the Firefox icon"
    model = sys.argv[2] if len(sys.argv) > 2 else "ui-tars:2b"
    print(f"Task: {task}")
    print(f"Model: {model}")
    run_task(task, model=model)
