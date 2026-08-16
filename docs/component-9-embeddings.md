# Component 9: Embeddings — Vectorizing Content

## 1. Overview

Chunks from Component 8 become **vectors** here so retrieval (C10/C11) can find them semantically. Model: **`qwen3-embedding:0.6b`** (Apache-2.0, 1024-dim with Matryoshka MRL, **32K-token context**, ~0.64 GB, always resident) — a real quality upgrade over the earlier `nomic-embed-text` pick (~+2 MTEB points, 32K vs 8K context so long chunks embed without truncation) at a tiny RAM cost. **`nomic-embed-text` stays as a fallback** (2.5× faster indexing if throughput ever matters more than quality). The same embedder is used for chunks *and* queries — one vector space, consistent similarity.

**Qwen instruction prefix (required):** documents embed as plain text; queries must be prefixed `"Instruct: Given a document query, retrieve the most relevant chunk.\nQuery: <q>"` — wired into the embedder wrapper.

```
chunks ──► embedder.py ──► [vectors] ──► vector store (C10)
query  ──► embedder.py ──► [vector]  ──► retriever (C11)
```

## 2. Calling Ollama

- Use `langchain_ollama.OllamaEmbeddings` against the native Ollama endpoint (not the OpenAI shim) — fewer moving parts, matches our `ollama_client`.
- **Batch input:** Ollama's `/api/embed` accepts multiple texts per call — one request for up to `batch_size` chunks cuts HTTP + pre/post overhead massively on ARM.
- Wrapped by `ingest/embedder.py` (the Component 2 `ollama_client.embed` is the low-level primitive; embedder adds batching, caching, model-awareness).

## 3. Batching Policy

| Setting | Value | Why |
|---|---|---|
| Batch size | 32 | Balances throughput vs single-request memory |
| Concurrency | 1 | CPU-bound on 4 ARM cores; no parallel benefit, avoids RAM spikes |
| Expected throughput | ~1–2k chunks/min | nightly batch is fine; never on interactive path |
| Empty-text guard | skip + log | empty chunks would poison the collection |

## 4. Embedding Cache & Idempotency

- C7 already dedups by content hash at ingest; embedder adds a **per-chunk-hash → vector** cache (SQLite `embed_cache`).
- A chunk whose hash exists is skipped — re-runs of a nightly sweep cost ~0.
- Invalidation: cache entries store the embedding model name; if the model changes, the cache is versioned and re-embeds transparently.

## 5. Model-Change Handling (re-embedding)

- Every vector's metadata carries `embed_model: qwen3-embedding:0.6b`.
- If we ever swap embedders, a **background re-embed job** rebuilds the collection: load docs → re-split → re-embed → swap collection atomically (new collection name, then alias switch).
- Old collection archived, not deleted immediately (rollback safety).

## 6. Dimension & Consistency Guarantees

- `qwen3-embedding:0.6b` = **1024 dims** (MRL down to 64); Chroma collection created with matching dimension at first ingest.
- Cosine similarity everywhere (normalize at write time).
- `tests/bench_embed.py` asserts: output shape = (n, 1024), norm ≈ 1.0, and query-vs-chunk consistency (embedding the same text twice yields near-identical vectors).

## 7. File Layout (Component 9)

```
ingest/
├── embedder.py           # batch embedder + cache + model-awareness
config/
└── embed.yaml            # model, dims, batch_size, concurrency
tests/
└── bench_embed.py        # shape, norm, latency, cache-hit checks
```

`pipeline.py` (C7) calls `embedder.py` after `splitters.py` (C8), then hands vectors to the store (C10).

## 8. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Model | **qwen3-embedding:0.6b** (1024d, 32K ctx), nomic-embed-text fallback | Apache-2.0, best quality-per-RAM on ARM |
| Query prefix | Qwen `Instruct:` format | Required for correct retrieval scores |
| Transport | `langchain_ollama.OllamaEmbeddings`, native endpoint | Matches stack |
| Batching | 32/batch, concurrency 1 | ARM throughput without spikes |
| Cache | per-chunk-hash SQLite | Nightly sweeps cost ~0 |
| Re-embed | versioned by model, atomic collection swap | Safe embedder changes |
| Consistency | cosine + 1024-dim enforced | Retrieval quality |
