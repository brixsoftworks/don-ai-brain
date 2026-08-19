"""core/subgraphs/vision.py — vision specialist sub-graph.

Runs with the vision model (qwen2.5vl:7b) for image analysis tasks.
Returns a structured description capped at 2 KB.

See docs/component-13 §3.
"""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage

from core.prompts import PromptBank
from models.ollama_client import OllamaClient

log = logging.getLogger("don.subgraph.vision")

RESULT_CAP = 2048


def vision_node(
    state: dict,
    client: OllamaClient,
    prompts: PromptBank,
    *,
    user_name: str = "Operator",
) -> dict:
    """Run the vision specialist: analyze an image and return description."""
    media = state.get("media", {})
    image_path = media.get("path") or media.get("hash", "")
    user_query = state.get("specialist_query", "Describe this image in detail.")

    system = prompts.system_for(
        "vision",
        user_name=user_name,
        device=state.get("device", "laptop"),
        memory_context="",
    )

    # build vision message with image
    messages = [HumanMessage(content=[
        {"type": "text", "text": user_query},
        {"type": "image_url", "image_url": {"url": f"file://{image_path}"}},
    ])]

    try:
        resp = client.invoke("vision", messages)
        content = resp.get("content", "").strip()[:RESULT_CAP]
        return {"specialist_result": content}
    except Exception as exc:  # noqa: BLE001
        log.error("vision specialist failed: %s", exc)
        return {"specialist_result": f"Vision analysis failed: {exc}"}
