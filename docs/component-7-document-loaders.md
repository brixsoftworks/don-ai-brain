# Component 7: Document Loaders — Feeding DON Your World

## 1. Overview

Everything DON learns about comes through here: your **personal documents** (notes, PDFs, emails) and — critically — **every chat you've had with DON**. Component 7 loads and normalizes raw data into clean text; splitting/embedding/storage happen in Components 8–10. The loader layer never touches the vector store.

## 2. What Gets Ingested

### 2.1 Personal documents (knowledge base) — **Docling primary, MarkItDown fast-path**

Research (Aug 2026) confirmed **Docling** (`docling-project/docling`, MIT, **64.7k stars**, official arm64 + CPU support) as the best local doc→clean-text pipeline — layout/reading-order aware, best-in-class table extraction and scanned-doc OCR, native email/EPUB/LaTeX/images, and a first-party LangChain integration. **Microsoft MarkItDown** (MIT) is the fast light-weight path for clean digital Office/HTML files.

| Doc type | Loader | Notes |
|---|---|---|
| PDF (text) | **Docling** (via LangChain `DoclingLoader`) | layout + reading order; 2–4 GB peak RAM, tunable |
| PDF (scanned) | Docling OCR — **RapidOCR (PP-OCR v4/v5/v6, ONNX)** | preferred; Tesseract kept as fallback |
| DOCX / PPTX / XLSX | Docling (or MarkItDown fast-path) | clean digital → MarkItDown; complex/layout → Docling |
| MD / TXT / code | `TextLoader` / MarkItDown | — |
| HTML | MarkItDown / `BSHTMLLoader` | — |
| EML / MSG / MBOX | Docling (email) | — |
| EPUB / LaTeX | Docling | native |
| CSV / JSON / Notebook | `CSVLoader`, `JSONLoader`, `NotebookLoader` | — |
| Images / screenshots | `Qwen2.5-VL` vision pass | text-in-image → stored as text (on-demand only) |

**Tiered pipeline (ARM tuning):** try MarkItDown fast-path first for clean digital docs → if output looks broken (no tables, low heading ratio) fall back to Docling. ARM: `DOCLING_NUM_THREADS=4`, layout/ocr/table `batch_size=1–2`, `pypdfium2` backend, OCR disabled when text-layer exists.

### 2.2 Chat corpus (new — "train from my chats")
DON remembers and learns from every conversation:

```
chat_log table (add to Component 1 §6)
└── id, thread_id, ts, role, content, tool_calls, tool_results
        │
        ▼  nightly `chat_exporter.py`
        ├── 1. RAG chunks      → each turn + context → embeddings (C9)
        ├── 2. Memory facts    → memory extractor (C4 §7) → long-term store
        └── 3. Training JSONL  → {"messages":[...]} archive for future fine-tuning
```

- **Behavior today:** RAG over chats = DON genuinely recalls and adapts to how you talk (your phrasing, preferences, past requests).
- **Stretch goal (fine-tuning):** the JSONL corpus is *kept ready* for LoRA fine-tuning. On 24 GB ARM CPU that's impractical (days–weeks), so tuning runs later on a rented/borrowed GPU or cloud service — the corpus is the deliverable here, not the tuning run.

## 3. Loader Registry (don't reinvent)

`loader_registry.py` maps extension → loader. **Docling** and **MarkItDown** replace most hand-rolled loaders:

```python
EXTENSION_MAP = {
    # heavy/dirty docs → Docling (MIT, arm64): PDF, DOCX, PPTX, XLSX, EML, EPUB, images
    ".pdf": DoclingLoader,  ".docx": DoclingLoader, ".pptx": DoclingLoader,
    ".xlsx": DoclingLoader, ".eml": DoclingLoader, ".msg": DoclingLoader,
    ".epub": DoclingLoader, ".tex": DoclingLoader,
    # clean/lightweight → MarkItDown fast-path
    ".md": MarkItDownLoader, ".txt": MarkItDownLoader, ".html": MarkItDownLoader,
    ".htm": MarkItDownLoader,
    # langchain-community where it still fits
    ".csv": CSVLoader, ".json": JSONLoader, ".ipynb": NotebookLoader,
    # unknown/other → custom @tool extraction or skip with log
}
```

All loaders emit LangChain `Document` objects (`page_content` + `metadata`). Metadata is standardized at this layer: `{source, doc_id, type, ingested_at}` — everything downstream relies on it.

## 4. Ingestion Sources & Scheduling

| Source | Trigger | Notes |
|---|---|---|
| `~/jarvishome/notes/` + watched folders | **Watcher** (`watchfiles`, Rust, aarch64 wheels): new/changed file → ingest | real-time |
| `~/jarvishome/inbox/` (drops: email exports, downloads) | Watcher | same path |
| Full personal folder sweep | nightly cron | catch stragglers + re-OCR |
| Chat log export | nightly cron | incremental (new rows only) |
| Manual ("DON, read this file") | tool `ingest_file` | immediate, guard-approved |

## 5. Dedup & Idempotency

- Content-hash of normalized text stored in an `ingest_log` SQLite table.
- Re-ingest only when hash changes → update, never duplicate.
- `doc_id` = sha256(source_path) stable across runs (replaces rather than duplicates).
- Watcher debounces (2s) to avoid half-written files.

## 6. Pipeline Orchestration

```
watcher / cron / tool
        │
        ▼
pipeline.py: load → normalize → dedup ──► (Component 8: split)
                                          (Component 9: embed)
                                          (Component 10: store)
```

`pipeline.py` owns ordering and error handling: one bad file never blocks the batch (per-file try/except + skip log).

## 7. File Layout (Component 7)

```
ingest/
├── loader_registry.py   # extension → loader map + OCR fallback
├── loaders.py           # custom: OCR, email, vision-text extraction
├── chat_exporter.py     # chat_log → RAG chunks / facts / training JSONL
├── watcher.py           # watchfiles folder watch + debounce + dedup
├── pipeline.py          # orchestrates load → normalize → dedup → handoff
└── ingest_log.py        # content-hash dedup, SQLite
config/
└── ingest.yaml          # watched folders, schedules, OCR toggle
```

## 8. Security & Privacy

- Documents stay on the A1 (Tailscale-only access). Nothing is sent off-box.
- Emails/images only ingested from explicit watch folders or explicit requests — never scraped silently.
- Chat corpus contains personal data → same protection; fine-tuning JSONL stored locally, never uploaded.
- Docling/MarkItDown run fully local — no remote conversion calls.

## 9. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Loaders | **Docling** (MIT, 64.7k stars) + **MarkItDown** fast-path | Best local layout/table/OCR quality, official arm64 + LangChain support |
| Tiering | MarkItDown for clean digital, Docling fallback | Speed vs fidelity on ARM |
| Scanned PDFs | Docling RapidOCR (PP-OCR ONNX), Tesseract fallback | Local, ARM-friendly |
| Chat learning | RAG now + training JSONL for future tuning | Real learning today, tuning-ready |
| Chat storage | dedicated `chat_log` table | Clean training data source (C1 refinement) |
| Scheduling | watcher + nightly incremental | Fresh memory, bounded cost |
| Dedup | content-hash `ingest_log` | Never duplicate |
| Privacy | local-only, explicit folders | Personal data stays private |
