# Component 11: Retrievers — How DON Looks Things Up

## 1. Overview

Component 10 stores vectors. Component 11 defines **how DON actually retrieves** — when, what query, which collection, how many results, and how results get injected into the agent loop without bloating the 7B context.

```
user: "what did I say about tea last week?"
   │
   ▼  classify_input → task_type=memory/knowledge
   ▼  agent_loop decides: use search tool
retriever.py → embed query → search(collection, k=4, filters)
   │
   ▼
   context block injected into DON's prompt (marked, cited)
   ▼
   DON answers from context + persona
```

## 2. Retrieval Node (in-graph)

- `core/nodes/retrieve.py` — runs when DON calls the `search_memory` / `search_notes` tools (both `read`-danger level, guard-approved like any tool).
- Also runs **automatically** (background pre-fetch) when the classifier tags a task `knowledge`/`memory` — one cheap search before the agent loop so DON starts with relevant context, no extra tool round-trip.

| Trigger | Collection | Query |
|---|---|---|
| "search my notes/docs/thesis" | `knowledge` | user query, + `type` filter if stated |
| "what did I say / we talked about" | `chat` | user query, + `thread_id`/`ts` filter if stated |
| automatic pre-fetch (task=knowledge) | `knowledge` | user query, k=2 |
| automatic pre-fetch (task=memory) | `chat` + `memory` | user query, k=2 each |
| explicit "remember X" | `memory` | full request |

## 3. Query Rewriting (7B-aware)

The embedded query is the raw user turn, lightly normalized:
- Strip conversational filler; keep named entities and time hints ("last week" → not resolved here, but kept for the `ts` filter when the user asks for a window).
- **No LLM query rewrite on the interactive path** (extra 7B call = seconds on ARM). Rule-based cleanup only.
- Optional nightly job can expand/rewrite hot queries offline and re-embed — deferred, cheap to add later.

## 4. Result Injection & Context Budget

Every retrieved chunk is formatted as a marked context block:

```
[CONTEXT]
from: chat (2026-08-10, thread abc)
user: "remind me to buy tea on friday"
DON: "Noted, operator. Chai it is..."
[/CONTEXT]
```

- **Budget:** retrieval context capped at **800 tokens/task** (≈ 4–6 chunks) — hard ceiling in state; trimming happens before injection, never mid-loop.
- Blocks are injected after the system prompt, before the conversation; DON is instructed (C3) to prefer context over guessing and to never claim context it doesn't have.
- Filters enforced by the store layer (C10 §3) — DON can't bypass scoping by wording alone.

## 5. Retrieval Tools (user-facing)

Registered in `tools/memory/` (already in C5 §4):

| Tool | Description | Collection(s) | Danger |
|---|---|---|---|
| `search_notes` | "search my documents" | knowledge | read |
| `search_memory` | "what did I say / do / prefer" | chat + memory | read |
| `search_tools` | BigTool meta-search (C6 §3) | tools | read |

All return the same `[CONTEXT]`-style structured text; DON renders it conversationally.

## 6. Failure Semantics

- **No results** → DON says so honestly; persona rule (never invent) enforced by prompt.
- **Low confidence** → store returns scores; results below a threshold are tagged `low_confidence` and DON is told, not asked to guess.
- **Store down/error** → tool returns clean error; agent loop continues without context (degraded, never crashed).

## 7. File Layout (Component 11)

```
core/
├── nodes/
│   └── retrieve.py          # retrieval node (pre-fetch + tool-backed)
retrieval/
├── retriever.py             # query cleanup → embed → search → format blocks
├── context.py               # budget cap, trimming, block formatting
└── tools.py                 # search_notes / search_memory (BaseTool defs)
config/
└── retrieval.yaml           # k defaults, token budget, thresholds
tests/
└── bench_retriever.py       # scoped-query + budget tests
```

## 8. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Retrieval node | pre-fetch on knowledge/memory tasks + tool-backed | Speed without extra round-trips |
| Query rewrite | rule-based, no interactive LLM rewrite | Seconds saved on ARM |
| Context budget | 800 tokens/task hard cap | Protect 7B context |
| Scoping | metadata filters, store-enforced | DON can't out-shout filters |
| Failure | honest "no results" + low-confidence tags | No hallucination |
| k default | 4 (knowledge), 2+2 (chat+memory pre-fetch) | Balance recall/cost |
