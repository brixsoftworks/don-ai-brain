# Component 8: Text Splitters — Cutting Content for Retrieval

## 1. Overview

Component 7 produces raw text. Component 8 cuts it into **chunks** — the retrieval units that get embedded (C9) and stored (C10). Chunking is the single biggest quality lever in RAG: too big → fuzzy retrieval + wasted 7B context; too small → lost meaning. We use a **per-doc-type splitter registry** (from `langchain-text-splitters`, don't reinvent) plus a chat-specific strategy.

## 2. Splitter Registry (per document type)

| Doc type | Splitter | Chunk | Overlap | Why |
|---|---|---|---|---|
| Default (txt, pdf, docx, email) | `RecursiveCharacterTextSplitter` | 1000 chars | 150 | Best general-purpose; respects paragraphs/sentences |
| Markdown notes | `MarkdownHeaderTextSplitter` + recursive fallback | header-aware, then 800/100 | Section titles survive as chunk context |
| Code | `TokenTextSplitter` (or language-aware via tree-sitter later) | ~500 tokens | 50 | Semantic units in code; 7B reads better |
| HTML | `HTMLHeaderTextSplitter` | header-aware | 100 | Headings preserved |
| CSV / JSON | row/record-level splitter (custom) | one row/record per chunk | 0 | Queries target records, not prose |
| Images/OCR text | recursive | 1000/150 | same as default |
| **Chat turns** | see §3 | — | — | special-cased |

## 3. Chat Turn Chunking (the learning path)

Chats are NOT split like documents — each turn is already a semantic unit.

```
turn:  user: "remind me to buy tea on friday"
       don:  "Noted, operator. Chai it is. — I'll remind you Friday morning."
       │
       ▼
chunk = user+don pair (≤ 500 tokens, truncated)
metadata = {thread_id, ts, turn_id, role}
```

- **One chunk per turn pair** (user + DON's reply) so retrieval returns complete Q/A context.
- Long replies truncated at 500 tokens (never mid-sentence — sentence-boundary cut).
- Tool-call turns additionally keep a compact `{tool, args}` summary line in the chunk so DON can recall "what did I do then".
- Multi-line tool outputs are **excluded** from chunks (they'd pollute semantic space); only the tool *action* is kept.

## 4. Metadata Inheritance

Every chunk inherits standardized metadata from Component 7:

```
{source, doc_id, type, ingested_at} + {chunk_index, chunk_total}
```

For chat chunks: `{thread_id, ts, turn_id}` added. The retriever (C11) filters on this (e.g. "recall my chats from last week", "only from my thesis PDF").

## 5. Size Tuning Notes (ARM budget)

- `qwen3-embedding:0.6b` context is 32K tokens — no chunk will approach this; 1000 chars ≈ ~250 tokens is comfortably inside.
- Embedding cost: ~1 embed call per chunk; a 10 MB doc ≈ ~10k chunks worst case — nightly batches only, never on the interactive path.
- These values live in `config/split.yaml` — retune without code.

## 6. Validation & Tests

`tests/bench_splitters.py` asserts, on sample docs per type:
- No chunk exceeds configured max (byte + token estimate).
- No content lost or duplicated (reconstruction test: concat ≈ source, modulo whitespace).
- Metadata present on every chunk.
- Chat chunks are exactly one turn pair.

## 7. File Layout (Component 8)

```
ingest/
├── splitters.py          # splitter factory per doc type (+ chat turn splitter)
config/
└── split.yaml            # per-type chunk size/overlap
tests/
└── bench_splitters.py    # validity + reconstruction tests
```

`pipeline.py` (C7) calls `splitters.py` after dedup, before handing chunks to the embedder (C9).

## 8. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Default splitter | RecursiveCharacter 1000/150 | Best general quality |
| Markdown | Header-aware | Section context preserved |
| Code | Token-based | Semantic units |
| Chat | One turn-pair per chunk | Complete Q/A for retrieval |
| Tool outputs | excluded from chunks | Avoid semantic pollution |
| Values in YAML | `config/split.yaml` | Tune without code |
| Embedding batch | nightly only | ARM cost |
