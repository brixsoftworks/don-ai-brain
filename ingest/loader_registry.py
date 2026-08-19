"""ingest/loader_registry.py — extension → loader map.

Docling and MarkItDown are the heavy lifters; fallbacks for simple formats.
See docs/component-7 §3.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from langchain_core.documents import Document

from ingest.loaders import load_csv, load_json, load_text_file

log = logging.getLogger("don.ingest.registry")

# Type alias for loader functions
LoaderFn = Callable[[Path], list[Document]]

# Map of extension → loader function.
# Docling/MarkItDown loaders are optional (import guarded); fallback is load_text_file.
EXTENSION_MAP: dict[str, LoaderFn] = {}


def _register_builtins() -> None:
    """Register the fallback loaders that are always available."""
    EXTENSION_MAP.setdefault(".txt", load_text_file)
    EXTENSION_MAP.setdefault(".md", load_text_file)
    EXTENSION_MAP.setdefault(".log", load_text_file)
    EXTENSION_MAP.setdefault(".csv", load_csv)
    EXTENSION_MAP.setdefault(".json", load_json)


def _try_register_docling() -> None:
    """Try to register Docling-based loaders (heavy docs)."""
    try:
        from langchain_docling import DoclingLoader  # type: ignore[import-untyped]

        docling_exts = [".pdf", ".docx", ".pptx", ".xlsx", ".eml", ".msg",
                        ".epub", ".tex", ".html", ".htm"]
        for ext in docling_exts:
            EXTENSION_MAP[ext] = lambda p, _l=DoclingLoader: _wrap_docling(p, _l)
        log.info("Docling loaders registered for %d extensions", len(docling_exts))
    except ImportError:
        log.info("Docling not installed; falling back to text loader for heavy docs")
        for ext in [".pdf", ".docx", ".pptx", ".xlsx", ".eml", ".msg",
                    ".epub", ".tex", ".html", ".htm"]:
            EXTENSION_MAP.setdefault(ext, load_text_file)


def _wrap_docling(path: Path, loader_cls) -> list[Document]:
    """Wrap DoclingLoader (returns Document list) with error handling."""
    try:
        loader = loader_cls(str(path))
        docs = loader.load()
        for doc in docs:
            doc.metadata.setdefault("source", str(path))
            doc.metadata.setdefault("type", path.suffix.lstrip(".").lower())
        return docs
    except Exception as exc:  # noqa: BLE001
        log.error("Docling failed for %s: %s — falling back to text", path, exc)
        return load_text_file(path)


# --- initialization ---

_register_builtins()
_try_register_docling()


def get_loader(path: Path) -> LoaderFn:
    """Return the appropriate loader for a file path.

    Falls back to text loader for unknown extensions.
    """
    ext = path.suffix.lower()
    loader = EXTENSION_MAP.get(ext)
    if loader is None:
        log.debug("no loader for %s, using text fallback", ext)
        loader = load_text_file
    return loader


def supported_extensions() -> list[str]:
    """Return all registered extensions."""
    return sorted(EXTENSION_MAP.keys())
