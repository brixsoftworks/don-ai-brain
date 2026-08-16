"""retrieval/context.py — [CONTEXT] block formatting + token budget trimming.

See docs/component-11 §4.
"""
from __future__ import annotations

import re


def _tokens_estimate(text: str) -> int:
    """Rough token estimate (~4 chars/token), good enough for budgeting."""
    return max(1, len(text) // 4)


def format_block(source: str, meta: dict, doc: str) -> str:
    """One marked, cited context block."""
    header = f"from: {source}"
    if meta.get("ts"):
        header += f" ({meta['ts'][:10]})"
    if meta.get("thread_id"):
        header += f", thread {meta['thread_id']}"
    confidence = meta.get("confidence")
    low = ""
    if confidence is not None and float(confidence) < 0.5:
        low = " [low_confidence]"
    return f"[CONTEXT]\n{header}{low}\n{doc[:500]}\n[/CONTEXT]"


def trim_to_budget(blocks: list[str], budget_tokens: int = 800) -> list[str]:
    """Drop blocks from the end until under the token budget (keeps best first)."""
    kept = []
    used = 0
    for b in blocks:
        cost = _tokens_estimate(b)
        if used + cost > budget_tokens:
            break
        kept.append(b)
        used += cost
    return kept


def join_blocks(blocks: list[str]) -> str:
    return "\n".join(blocks)
