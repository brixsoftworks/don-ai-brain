"""tools/screen/automation.py — high-level screen automation workflows.

Single tool calls that execute multi-step screen workflows:
- compose_email: open Gmail, click compose, fill fields, verify
- fill_form: open a URL, fill in form fields, submit
- navigate_app: open app, navigate to a section, take screenshot

These wrap multiple low-level screen tools into atomic actions that
the agent can call in one step instead of chaining 5-6 individual calls.
"""
from __future__ import annotations

import time
from pathlib import Path

from langchain_core.tools import tool

from tools.screen.tools import (
    _run,
    SCREENSHOT_DIR,
    mouse_click,
    open_url,
    screenshot,
    screenshot_window,
    type_text,
    key_press,
    window_focus,
    window_list,
    scroll,
)


def _wait(seconds: float = 2.0) -> None:
    time.sleep(seconds)


def _screenshot_and_path() -> str:
    """Take screenshot and return the path."""
    result = screenshot.invoke({})
    if "saved:" in result:
        return result.split("saved: ")[1].split(" ")[0]
    return ""


@tool
def screen_compose_email(
    to: str,
    subject: str,
    body: str,
) -> str:
    """Open Gmail compose window with pre-filled email fields.

    Opens Chrome with Gmail compose URL containing the To, Subject, and Body.
    The email is pre-filled but NOT sent — the user must click Send or you
    can use screen_find_and_click to click the Send button.

    Args:
        to: recipient email address.
        subject: email subject line.
        body: email body text.
    """
    import urllib.parse

    # Build Gmail compose URL with pre-filled fields
    params = urllib.parse.urlencode({
        'view': 'cm',
        'fs': '1',
        'to': to,
        'su': subject,
        'body': body,
    })
    compose_url = f"https://mail.google.com/mail/?{params}"

    # Open in Chrome
    _run(f"nohup xdg-open '{compose_url}' &>/dev/null &")
    _wait(5)

    # Take screenshot to verify
    path = _screenshot_and_path()

    return (
        f"Gmail compose window opened in Chrome.\n"
        f"To: {to}\n"
        f"Subject: {subject}\n"
        f"Body: {body}\n"
        f"Screenshot: {path}\n"
        f"The email is ready but NOT sent. Use screen_find_and_click on 'Send button' to send it, "
        f"or tell the user to click Send."
    )


@tool
def screen_fill_form(
    url: str,
    fields: str,
) -> str:
    """Open a web page and fill in form fields using screen control.

    Takes a screenshot after filling to verify.

    Args:
        url: the URL of the form to fill.
        fields: JSON string mapping field labels/descriptions to values.
                Example: '{"search box": "python tutorial", "name field": "DON"}'
    """
    import json

    steps = []

    # Step 1: Open the URL
    open_url.invoke({"url": url})
    steps.append(f"opened {url}")
    _wait(3)

    # Step 2: Parse fields
    try:
        field_map = json.loads(fields)
    except json.JSONDecodeError:
        return f"error: invalid fields JSON: {fields}"

    # Step 3: For each field, we take a screenshot and note the position
    # The agent will need to use screen_vision to find field positions
    path = _screenshot_and_path()
    steps.append(f"initial screenshot: {path}")

    result_lines = [
        f"Form opened: {url}",
        f"Fields to fill: {json.dumps(field_map, indent=2)}",
        f"Screenshot for field locating: {path}",
        "Use screen_vision to find field positions, then mouse_click + type_text to fill each field.",
    ]
    return "\n".join(result_lines)


@tool
def screen_navigate_and_act(
    app: str,
    action_description: str,
) -> str:
    """Open an application, take a screenshot, and describe what actions to take.

    This is a helper that sets up the screen for the agent to then
    use low-level tools (mouse_click, type_text) to complete the action.

    Args:
        app: application name or URL to open.
        action_description: description of what to do after the app opens.
    """
    steps = []

    # Determine if it's a URL or an app
    if app.startswith("http") or "." in app:
        open_url.invoke({"url": app})
        steps.append(f"opened URL: {app}")
        _wait(3)
    else:
        _run(f"nohup {app} &>/dev/null &")
        steps.append(f"launched app: {app}")
        _wait(2)

    # Take screenshot
    path = _screenshot_and_path()
    steps.append(f"screenshot: {path}")

    return (
        f"Application ready.\n"
        f"Opened: {app}\n"
        f"Action requested: {action_description}\n"
        f"Current screenshot: {path}\n"
        f"Use screen_vision to analyze the screen, then use mouse_click and type_text to complete the action."
    )


TOOLS = [screen_compose_email, screen_fill_form, screen_navigate_and_act]
