"""ingest/splitters.py — splitter factory per doc type (+ chat turn splitter).

Per-doc-type registry from langchain-text-splitters. Chat turns are special:
one user+assistant pair per chunk. See docs/component-8.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml
from langchain_core.documents import Document
from langchain_text_splitters import (
    HTMLHeaderTextSplitter,
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
    TokenTextSplitter,
)

HAS_TOKEN_SPLITTER = True

log = logging.getLogger("don.ingest.splitters")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG = CONFIG_DIR / "split.yaml"


def _load_config(path: Path | None = None) -> dict:
    path = path or DEFAULT_CONFIG
    if not path.exists():
        return {}
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


class SplitterFactory:
    """Create the appropriate text splitter per document type."""

    def __init__(self, config_path: Path | None = None):
        self.config = _load_config(config_path)
        self._splitters = self._build_all()

    def _cfg(self, doc_type: str) -> dict:
        return self.config.get("splitters", {}).get(doc_type, self.config.get("splitters", {}).get("default", {}))

    def _build_all(self) -> dict:
        splitters = {}
        default = self._cfg("default")

        # default recursive
        splitters["default"] = RecursiveCharacterTextSplitter(
            chunk_size=default.get("chunk_size", 1000),
            chunk_overlap=default.get("chunk_overlap", 150),
            length_function=len,
        )

        # markdown header-aware
        md_cfg = self._cfg("markdown")
        headers = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]
        splitters["markdown"] = {
            "header": MarkdownHeaderTextSplitter(headers_to_split_on=headers),
            "recursive": RecursiveCharacterTextSplitter(
                chunk_size=md_cfg.get("chunk_size", 800),
                chunk_overlap=md_cfg.get("chunk_overlap", 100),
            ),
        }

        # code: token-based
        code_cfg = self._cfg("code")
        splitters["code"] = TokenTextSplitter(
            chunk_size=code_cfg.get("chunk_size", 500),
            chunk_overlap=code_cfg.get("chunk_overlap", 50),
        )

        # HTML header-aware
        html_headers = [
            ("h1", "Header 1"),
            ("h2", "Header 2"),
            ("h3", "Header 3"),
        ]
        splitters["html"] = {
            "header": HTMLHeaderTextSplitter(headers_to_split_on=html_headers),
            "recursive": RecursiveCharacterTextSplitter(
                chunk_size=default.get("chunk_size", 1000),
                chunk_overlap=default.get("chunk_overlap", 150),
            ),
        }

        return splitters

    def get(self, doc_type: str):
        """Return the splitter(s) for a document type."""
        return self._splitters.get(doc_type, self._splitters["default"])


def _split_chat_turns(doc: Document, max_reply_tokens: int = 500) -> list[Document]:
    """Split a chat document into turn-pair chunks.

    Each chunk = one user message + one assistant reply.
    Tool outputs are excluded; tool calls kept as compact summary.
    """
    text = doc.page_content
    chunks = []

    # split on turn boundaries
    turns = re.split(r'\n(?=(?:user|assistant|human|ai):)', text)
    pending_user = None

    for turn in turns:
        turn = turn.strip()
        if not turn:
            continue

        if re.match(r'^(user|human):', turn, re.IGNORECASE):
            content = re.sub(r'^(user|human):\s*', '', turn, flags=re.IGNORECASE)
            pending_user = content
        elif re.match(r'^(assistant|ai):', turn, re.IGNORECASE):
            content = re.sub(r'^(assistant|ai):\s*', '', turn, flags=re.IGNORECASE)
            if pending_user is not None:
                pair_text = f"user: {pending_user}\nassistant: {content}"
                meta = dict(doc.metadata)
                meta["role"] = "turn_pair"
                chunks.append(Document(page_content=pair_text, metadata=meta))
                pending_user = None

    return chunks if chunks else [doc]


def split_documents(
    docs: list[Document],
    doc_type: str | None = None,
    path_suffix: str | None = None,
    config_path: Path | None = None,
) -> list[Document]:
    """Split documents into chunks based on type.

    Args:
        docs: loaded Document list.
        doc_type: explicit type override (e.g. 'chat', 'code', 'markdown').
        path_suffix: file extension used for auto-detection (e.g. '.py').
        config_path: optional override for split.yaml.
    """
    factory = SplitterFactory(config_path)
    chunks = []

    # auto-detect doc type from extension
    if doc_type is None and path_suffix:
        ext = path_suffix.lower().lstrip(".")
        type_map = {
            "py": "code", "js": "code", "ts": "code", "go": "code",
            "rs": "code", "java": "code", "c": "code", "cpp": "code",
            "rb": "code", "sh": "code", "bash": "code",
            "md": "markdown", "markdown": "markdown",
            "html": "html", "htm": "html",
            "csv": "csv", "json": "json",
        }
        doc_type = type_map.get(ext, "default")

    doc_type = doc_type or "default"

    for doc in docs:
        try:
            if doc_type == "chat":
                sub_chunks = _split_chat_turns(doc)
            elif doc_type == "markdown":
                splitter_cfg = factory.get("markdown")
                header_splitter = splitter_cfg["header"]
                recursive = splitter_cfg["recursive"]
                sub_chunks = header_splitter.split_text(doc.page_content)
                sub_chunks = recursive.split_documents(sub_chunks)
            elif doc_type == "html":
                splitter_cfg = factory.get("html")
                header_splitter = splitter_cfg["header"]
                recursive = splitter_cfg["recursive"]
                sub_chunks = header_splitter.split_text(doc.page_content)
                sub_chunks = recursive.split_documents(sub_chunks)
            else:
                splitter = factory.get(doc_type)
                if hasattr(splitter, "split_documents"):
                    sub_chunks = splitter.split_documents([doc])
                else:
                    texts = splitter.split_text(doc.page_content)
                    sub_chunks = [Document(page_content=t, metadata=dict(doc.metadata)) for t in texts]

            # propagate metadata
            for chunk in sub_chunks:
                for k, v in doc.metadata.items():
                    chunk.metadata.setdefault(k, v)

            chunks.extend(sub_chunks)
        except Exception as exc:  # noqa: BLE001
            log.error("split failed for a document: %s", exc)

    return chunks
