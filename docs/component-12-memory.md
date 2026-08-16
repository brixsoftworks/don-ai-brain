# Component 12: Memory / Checkpointing — What DON Remembers

## 1. Overview

DON has **three memory layers**, matching how people remember:

```
┌─ Short-term (working) ── LangGraph checkpointer (C1 §6)
│    • current & recent conversations, resumable across devices
│    • SQLite, per thread_id, 90-day retention
│
├─ Long-term (semantic) ── LangGraph store + langmem
│    • extracted facts, preferences, relationships (from C4 §7 + chat corpus)
│    • stored in vector collection `memory` (C10)
│    • user profile namespace → injected as {memory_context} (C3)
│
└─ Episodic (raw recall) ── vector collection `chat`
     • every turn pair, retrievable verbatim (C7 §2.2)
     • powers "what did I say last week"
```

## 2. Storage Stack (confirmed Aug 2026 research)

- **`langchain-ai/langmem`** — official LangChain memory layer, **confirmed best-in-class** for a LangGraph build (MIT, first-party, drops into our existing stack):
  - `create_manage_memory_tool` / `create_search_memory_tool` → DON manages memory **in the hot path** when it matters.
  - Background memory manager → auto-extract + consolidate + update.
  - ⚠️ PyPI release stalls at 0.0.30 despite active commits → **pin a git SHA**.
- **LangGraph `BaseStore`** (SqliteStore) as the fact/namespace store. **Caveat:** LangGraph's `BaseStore.search(query=...)` semantic vector backend exists only for `InMemoryStore`/`PostgresStore` — no SQLite vector backend. So semantic recall goes through the **ChromaDB `memory` collection via our own retrieval node** (C11 `search_memory`), while `BaseStore` holds structured facts/profile namespaces.
- Falls back cleanly to Chroma `memory` collection for vector recall (C11 uses `search_memory`).

## 3. Memory Facts

Schema (C4 §4):

```python
class MemoryFact(BaseModel):
    subject: str          # "user"
    predicate: str        # "prefers_tea_over_coffee"
    object_value: str     # "tea"
    category: Literal["preference", "fact", "relationship", "event"]
    confidence: float
```

- **Extraction:** post-reply background job (C4 §7) using the main model; also the chat_exporter's nightly pass (C7 §2.2).
- **Threshold:** confidence < 0.7 dropped; duplicates merged by predicate+object (LLM-assisted consolidation, batch).
- **Conflict:** new fact overwrites old only when new confidence ≥ old + 0.1; ties keep both with timestamps (temporal recall in C11).

## 4. User Profile (the {memory_context} injection)

- A dedicated store namespace `user/profile` holds the curated, high-confidence set: name, language, preferences, routines, relationships.
- Rebuilt nightly from memory facts (top-confidence per predicate), capped at **~300 tokens** so the C3 `{memory_context}` variable stays cheap.
- DON's persona rules say: use profile, never contradict a stated preference.

## 5. Lifecycle & Retention

| Layer | Retention | Pruning |
|---|---|---|
| Checkpointer (short-term) | 90 days | archive to `chat` collection, then delete from SQLite |
| `chat` episodic | 2 years | oldest turns downsampled (every Nth turn kept) |
| `memory` facts | indefinite | merge/decay: facts untouched 365 days lose confidence 0.05/mo |
| user profile | indefinite | rebuilt nightly, only high-confidence survives |

## 6. Background Memory Manager (langmem)

Runs as a low-priority task (thread pool, after-hours cron):
1. Pick new turns from `chat_log`.
2. Extract facts → validate → dedup → store.
3. Rebuild profile summary.
4. Handle "forget" requests (guard-approved destructive tool) — deletes across layers.

## 7. Memory Tools for DON

| Tool | Danger | Purpose |
|---|---|---|
| `remember` (manage_memory) | action | explicitly store a fact on request |
| `search_memory` (C11) | read | recall facts |
| `forget_memory` | destructive | delete a fact / thread (guard + confirm) |
| `set_preference` | action | record a preference into profile |

All wired through the guard (C1 §8) — memory writes are actions, so DON asks before storing anything non-obvious.

## 8. File Layout (Component 12)

```
memory/
├── store.py               # BaseStore init, namespaces, profile read/write
├── extractor.py           # background fact extraction + consolidation
├── profile.py             # user profile builder (nightly)
├── retention.py           # pruning/decay jobs
└── tools.py               # remember / search_memory / forget / set_preference
config/
└── memory.yaml            # thresholds, retention, profile token cap
tests/
└── bench_memory.py        # fact round-trip, dedup, conflict, profile cap
```

## 9. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Long-term engine | langmem + LangGraph BaseStore | Official, stack-native (C5a §8) |
| Facts | extraction threshold 0.7, LLM dedup | Quality over volume |
| Profile | nightly rebuild, 300-token cap | Cheap context, fresh |
| Retention | staged (90d/2y/indefinite) | Bounded storage |
| Memory tools | guard-approved actions | User control, C1 §8 |
| Conflict | confidence-gated overwrite | No silent data loss |
