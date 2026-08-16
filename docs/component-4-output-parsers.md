# Component 4: Output Parsers — Machine-Validated Outputs

## 1. Overview

Local 7B models occasionally produce malformed output (broken JSON, extra text, missing commas). Component 4 makes every machine-read output **validated, typed, and recoverable**: parse → validate → retry → fallback. Nothing the graph consumes is trusted raw.

## 2. What Needs Parsing in JARVIS

| Output | Producer | Consumer | Schema |
|---|---|---|---|
| Task classification | router model | `route_model` node | `TaskClassification` |
| Tool calls | dept model in agent_loop | `guard` → `tool_node` | `ToolCall` |
| Tool arguments | dept model | tool dispatch | per-tool Pydantic schema |
| Memory facts | memory extractor (bg) | long-term store | `MemoryFact` |
| Final answers | dept model | user | plain text (no parse) |

## 3. The Parser Stack

```
core/parsing/
├── __init__.py
├── schemas.py              # Pydantic models (single source of truth)
├── router_parser.py        # lenient JSON → TaskClassification
├── tool_call_parser.py     # native Ollama tool calls OR JSON fallback
├── tool_args.py            # validates args against each tool's schema
├── memory_parser.py        # conversation → MemoryFact list
└── retry.py                # parse → retry(1) → fallback logic
```

## 4. schemas.py (Pydantic)

```python
from typing import Any, Literal
from pydantic import BaseModel, Field

class TaskClassification(BaseModel):
    task_type: Literal["quick_query", "system", "comms", "knowledge",
                       "coding", "complex_plan", "image_analysis", "unknown"]
    confidence: float = Field(ge=0, le=1)

class ToolCall(BaseModel):
    tool: str
    args: dict[str, Any]

class MemoryFact(BaseModel):
    subject: str                     # e.g. "user"
    predicate: str                   # e.g. "prefers_tea_over_coffee"
    object_value: str                # e.g. "tea"
    category: Literal["preference", "fact", "relationship", "event"]
    confidence: float
```

These schemas are the single source of truth — tools, parser tests, and the graph all import from `schemas.py`.

## 5. Router Parsing (strict → lenient)

1. **Strict path:** `json.loads` raw output → `TaskClassification`.
2. **Lenient fallback:** regex-extract the first `{...}` block → repair common issues (trailing commas, unquoted keys, single quotes) → validate.
3. Both fail → one **retry** with a corrected instruction appended.
4. Retry fails → `unknown` with confidence 0. Graph still proceeds via the main model. **Never blocks.**

```
raw text ──► json.loads ──succeeds──► TaskClassification
              │ fails
              ▼
        regex {..} + repair ──succeeds──► TaskClassification
              │ fails
              ▼
        retry(1) with hint ──succeeds──► TaskClassification
              │ fails
              ▼
        TaskClassification(task_type="unknown", confidence=0.0)
```

## 6. Tool-Call Parsing (hybrid)

### Preferred: native Ollama function calling
- qwen2.5 models support the `tools` param → Ollama returns structured `tool_calls`.
- Zero parsing; arguments arrive pre-typed in JSON.
- Used automatically whenever the active model supports it.

### Fallback: JSON-mode
- The agent is prompted to emit a single `ToolCall` JSON block.
- Same lenient parser (Section 5 pipeline) validates it.

### Argument validation (mandatory in both paths)
- `tool_args.py` validates args against the tool's own Pydantic schema (Component 5 defines one per tool).
- Invalid args → clean error back to the agent: `"tool weather.forecast: argument 'city' expected str, got int"`.
- Agent re-plans without crashing the loop.

## 7. Memory Extraction (background, post-response)

- Runs **after** the reply is delivered — never blocks the user.
- Uses the main model + `MemoryFact` schema to extract durable facts from the conversation.
- Facts below confidence 0.7 are dropped; duplicates merged in Component 12.
- Triggered asynchronously (task queue), one per conversation turn at most.

## 8. Retry Policy

- **Exactly one retry** per parse before falling back (keeps ARM latency bounded).
- Retry appends a corrective instruction (e.g. "output valid JSON only").
- Never loops, never blocks: every parser has a guaranteed fallback value.

## 9. File Layout (Component 4)

```
core/parsing/
├── __init__.py
├── schemas.py
├── router_parser.py
├── tool_call_parser.py
├── tool_args.py
├── memory_parser.py
└── retry.py
tests/
└── bench_parsers.py    # malformed-input torture tests for every parser
```

`tests/bench_parsers.py` feeds each parser a battery of malformed samples (truncated JSON, extra prose, unquoted keys, wrong types) and asserts the fallback path resolves.

## 10. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Validation | Pydantic everywhere | Typed, auto-documented schemas |
| Router parsing | strict → lenient → retry → unknown | Never blocks the graph |
| Tool calls | hybrid: native Ollama + JSON fallback | Best of both; resilience |
| Args validation | per-tool Pydantic schema | Clean errors, agent re-plans |
| Retries | exactly 1 | ARM latency budget |
| Memory extraction | post-reply background | No user-facing latency |
