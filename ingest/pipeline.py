"""ingest/pipeline.py — orchestrates load → normalize → dedup → split → embed → store.

One bad file never blocks the batch (per-file try/except + skip log).
See docs/component-7 §6.
"""
from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.documents import Document

from ingest.embedder import Embedder
from ingest.ingest_log import IngestLog
from ingest.loader_registry import get_loader
from ingest.splitters import split_documents
from memory.vectorstore import VectorStore

log = logging.getLogger("don.ingest.pipeline")


def _normalize_metadata(doc: Document, source_path: Path) -> Document:
    """Standardize metadata across all loaders."""
    doc.metadata.setdefault("source", str(source_path))
    doc.metadata.setdefault("type", source_path.suffix.lstrip(".").lower())
    doc.metadata.setdefault("doc_id", IngestLog.doc_id(str(source_path)))
    doc.metadata["ingested_at"] = doc.metadata.get("ingested_at", "")
    return doc


def ingest_file(
    path: Path,
    vectorstore: VectorStore,
    embedder: Embedder,
    ingest_log: IngestLog,
    collection: str = "knowledge",
    *,
    force: bool = False,
) -> int:
    """Ingest a single file: load → normalize → dedup → split → embed → store.

    Returns the number of chunks stored.
    """
    path = path.expanduser().resolve()
    if not path.exists():
        log.warning("file not found: %s", path)
        return 0

    # read and hash for dedup
    try:
        raw_text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        log.error("cannot read %s: %s", path, exc)
        return 0

    chash = IngestLog.content_hash(raw_text)
    if not force and not ingest_log.is_stale(str(path), chash):
        log.debug("skipping unchanged: %s", path.name)
        return 0

    # load
    loader = get_loader(path)
    try:
        docs = loader(path)
    except Exception as exc:  # noqa: BLE001
        log.error("loader failed for %s: %s", path, exc)
        return 0

    if not docs:
        log.warning("no documents from %s", path.name)
        return 0

    # normalize metadata
    docs = [_normalize_metadata(d, path) for d in docs]

    # split
    chunks = split_documents(docs, path_suffix=path.suffix)
    if not chunks:
        log.warning("no chunks from %s", path.name)
        return 0

    # embed
    texts = [c.page_content for c in chunks]
    vectors = embedder.embed(texts)

    # store
    ids = [f"{IngestLog.doc_id(str(path))}_{i}" for i in range(len(chunks))]
    metadatas = []
    for i, chunk in enumerate(chunks):
        meta = dict(chunk.metadata)
        meta["chunk_index"] = i
        meta["chunk_total"] = len(chunks)
        metadatas.append(meta)

    vectorstore.add(collection, ids, vectors, texts, metadatas)
    ingest_log.record(str(path), chash, chunk_count=len(chunks))
    log.info("ingested %s → %d chunks", path.name, len(chunks))
    return len(chunks)


def ingest_folder(
    folder: Path,
    vectorstore: VectorStore,
    embedder: Embedder,
    ingest_log: IngestLog,
    collection: str = "knowledge",
    *,
    recursive: bool = True,
) -> dict:
    """Ingest all supported files in a folder. Returns stats."""
    folder = folder.expanduser().resolve()
    if not folder.exists():
        log.warning("folder not found: %s", folder)
        return {"scanned": 0, "ingested": 0, "skipped": 0, "errors": 0}

    stats = {"scanned": 0, "ingested": 0, "skipped": 0, "errors": 0}
    pattern = "**/*" if recursive else "*"

    for path in sorted(folder.glob(pattern)):
        if not path.is_file():
            continue
        stats["scanned"] += 1
        try:
            n = ingest_file(path, vectorstore, embedder, ingest_log, collection)
            if n > 0:
                stats["ingested"] += 1
            else:
                stats["skipped"] += 1
        except Exception as exc:  # noqa: BLE001
            log.error("error ingesting %s: %s", path, exc)
            stats["errors"] += 1

    log.info("folder %s: %s", folder.name, stats)
    return stats
