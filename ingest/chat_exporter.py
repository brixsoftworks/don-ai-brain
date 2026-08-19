"""ingest/chat_exporter.py — chat_log → RAG chunks / memory facts / training JSONL.

The nightly bridge between the chat_log table and the vector store.
Produces: RAG turn-pair chunks, memory facts (via extractor), and a
training JSONL for future LoRA fine-tuning.

See docs/component-7 §2.2.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.documents import Document

log = logging.getLogger("don.ingest.chat_exporter")

TRAINING_DIR = Path(__file__).resolve().parent.parent / "jarvishome" / "training"


def export_chat_turns(
    chat_log_rows: list[dict],
    thread_id: str,
) -> list[Document]:
    """Convert raw chat_log rows into turn-pair Documents for RAG.

    Each Document is a user+assistant pair (docs/component-8 §3).
    Tool-call turns keep a compact summary; tool outputs are excluded.
    """
    docs = []
    pending_user: dict | None = None

    for row in chat_log_rows:
        role = row.get("role", "")
        content = row.get("content", "")
        ts = row.get("ts", "")

        if role == "user":
            pending_user = {"content": content, "ts": ts}
        elif role == "assistant" and pending_user is not None:
            # build turn-pair chunk
            chunk_text = (
                f"user: {pending_user['content']}\n"
                f"assistant: {content}"
            )
            docs.append(Document(
                page_content=chunk_text,
                metadata={
                    "source": "chat",
                    "thread_id": thread_id,
                    "ts": pending_user["ts"],
                    "type": "chat",
                    "role": "turn_pair",
                },
            ))
            pending_user = None

    return docs


def export_training_jsonl(
    chat_log_rows: list[dict],
    output_path: Path | None = None,
) -> Path:
    """Write chat_log rows in LLaMA-Factory ShareGPT messages format.

    Format: {"messages": [{"role": "user", "content": ...},
                           {"role": "assistant", "content": ...}, ...]}
    """
    output_path = output_path or (TRAINING_DIR / "chat_export.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    messages = []
    for row in chat_log_rows:
        role = row.get("role", "user")
        content = row.get("content", "")
        if role in ("user", "assistant") and content.strip():
            messages.append({"role": role, "content": content})

    # write as single conversation for now (batch aggregation is a later step)
    with open(output_path, "a", encoding="utf-8") as fh:
        record = {"messages": messages}
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    log.info("wrote %d messages to %s", len(messages), output_path)
    return output_path


def export_memory_facts(
    chat_log_rows: list[dict],
    thread_id: str,
) -> list[dict]:
    """Extract turn pairs suitable for memory fact extraction.

    Returns raw turn-pair dicts; the FactExtractor (memory/extractor.py)
    handles the actual LLM extraction.
    """
    pairs = []
    pending_user: dict | None = None

    for row in chat_log_rows:
        role = row.get("role", "")
        content = row.get("content", "")
        ts = row.get("ts", "")

        if role == "user":
            pending_user = {"content": content, "ts": ts}
        elif role == "assistant" and pending_user is not None:
            pairs.append({
                "user": pending_user["content"],
                "assistant": content,
                "ts": pending_user["ts"],
                "thread_id": thread_id,
            })
            pending_user = None

    return pairs
