# Component 10: Vector Stores — Where Vectors Live

## 1. Overview

Vectors from Component 9 are persisted in **ChromaDB** (local, file-based, zero extra services, ARM-friendly — fits the free-tier budget). One Chroma instance, **multiple collections** so retrieval can be scoped by namespace. The vector store is also the backbone of DON's memory (C12) and BigTool's tool registry (C5 §3). **ChromaDB v1.x (2026) rebuilt its core in Rust ≈ 4× faster** embedded mode; confirmed as the best local store at this scale (LanceDB kept as the scale-out/hybrid-search upgrade path if ever needed).

```
ChromaDB (single instance, on-disk at ~/jarvishome/vectordb)
├── knowledge      → your documents (C7)
├── chat           → all conversations (C7 §2.2)
├── memory         → extracted facts / preferences (C12)
└── tools          → BigTool tool metadata (C5)
```

## 2. Collection Layout

| Collection | Content | Key metadata filters | RAG budget (RAM) |
|---|---|---|---|
| `knowledge` | docs: notes, pdfs, emails | `type`, `doc_id`, `source` | main |
| `chat` | turn pairs | `thread_id`, `ts`, `turn_id` | main |
| `memory` | facts/preferences | `category`, `subject` | main |
| `tools` | BigTool specs | `source`, `danger` | BigTool-owned |

Each collection: **1024-dim**, cosine, single embedding model (Component 9 guarantees).

## 3. Access Layer

`memory/vectorstore.py` is the ONLY module that touches Chroma — everything else goes through it:

```python
class VectorStore:
    def add(collection, chunks, vectors, metadata)      # batch upsert
    def search(collection, query_vector, k, filters)    # similarity + metadata filter
    def delete(collection, where)                       # by doc_id / thread_id
    def count(collection)                               # monitoring
```

- Metadata filters power scoped queries: "recall my chats from last week" → `chat` + `ts` range; "only my thesis" → `knowledge` + `doc_id`.
- **k (top-k) default 4** for the agent prompt budget; adjustable per task.

## 4. Persistence & Recovery

- On-disk Chroma (no separate DB server). Backed up nightly with the rest of `~/jarvishome` (rsync snapshot to object storage — free-tier 200 GB block storage + 10 TB egress).
- Collection swap on re-embed (C9 §5): new collection → alias switch → archive old.
- Corruption safety: Chroma's sqlite-backed index is snapshotted pre-backup; restore = replace directory + restart.

## 5. Resource Budget (RAM/CPU)

- Chroma in-process (no HTTP server) ≈ **~300–500 MB** — inside the C2 §3 budget (vector DB + SQLite ≈ 0.5 GB).
- Queries are fast (<50 ms) and lazy-loaded; only the active collection stays warm in memory.
- Writes happen in nightly batches — never on the interactive path.

## 6. Testing

`tests/bench_vectorstore.py`:
- round-trip: add → search returns the right chunk for a paraphrase query;
- filter correctness: `type=email` excludes non-email hits;
- idempotent upsert: same `doc_id` twice → count unchanged;
- dimension guard: non-1024 vectors rejected.

## 7. File Layout (Component 10)

```
memory/
├── vectorstore.py        # Chroma access layer (single touchpoint)
config/
└── vectorstore.yaml      # path, collections, default k, cosine
tests/
└── bench_vectorstore.py  # round-trip, filters, idempotency, dims
```

## 8. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Engine | ChromaDB v1.x (in-process, on-disk, Rust core) | Zero services, ARM-friendly, free, ~4× faster |
| Collections | knowledge / chat / memory / tools | Scoped retrieval |
| Access | single `vectorstore.py` wrapper | No raw Chroma elsewhere |
| Filters | metadata-based | Scope queries cheaply |
| k default | 4 | 7B context budget |
| Backup | nightly rsync snapshot | 200 GB free storage |
| Re-embed | atomic collection swap | Safe model changes |
