"""ingest/loaders.py — custom loaders: OCR, email, vision-text extraction.

Thin wrappers for edge cases not covered by Docling/MarkItDown.
See docs/component-7 §2.
"""
from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.documents import Document

log = logging.getLogger("don.ingest.loaders")


def load_text_file(path: Path) -> list[Document]:
    """Fallback: read any text file as a single Document."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return [Document(
            page_content=text,
            metadata={
                "source": str(path),
                "type": path.suffix.lstrip(".").lower(),
            },
        )]
    except Exception as exc:  # noqa: BLE001
        log.error("failed to load %s: %s", path, exc)
        return []


def load_csv(path: Path) -> list[Document]:
    """Load CSV — one Document per row."""
    import csv
    docs = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for i, row in enumerate(reader):
                content = "\n".join(f"{k}: {v}" for k, v in row.items() if v)
                docs.append(Document(
                    page_content=content,
                    metadata={
                        "source": str(path),
                        "type": "csv",
                        "row_index": i,
                    },
                ))
    except Exception as exc:  # noqa: BLE001
        log.error("failed to load CSV %s: %s", path, exc)
    return docs


def load_json(path: Path) -> list[Document]:
    """Load JSON — one Document per top-level record."""
    import json
    docs = []
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        records = data if isinstance(data, list) else [data]
        for i, rec in enumerate(records):
            if isinstance(rec, dict):
                content = json.dumps(rec, indent=2, ensure_ascii=False)
            else:
                content = str(rec)
            docs.append(Document(
                page_content=content,
                metadata={
                    "source": str(path),
                    "type": "json",
                    "record_index": i,
                },
            ))
    except Exception as exc:  # noqa: BLE001
        log.error("failed to load JSON %s: %s", path, exc)
    return docs
