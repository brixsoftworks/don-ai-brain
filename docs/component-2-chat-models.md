# Component 2: Chat Models + Model Router

## 1. Overview

All intelligence is local via **Ollama** on the Oracle A1. Because 24 GB RAM cannot hold every model at once, a **router** decides which model handles each task, when it loads, and when it gets evicted.

Two cooperating pieces:
1. **Model registry** (`config/models.yaml` + `models/registry.py`) — the source of truth for every model's name, size, and behavior.
2. **Router node** (`models/router.py`) — maps `task_type` → model at runtime and orchestrates loading/fallback.

## 2. Model Registry

| Dept | Ollama model | RAM (Q4) | keep_alive | Est. speed (ARM) |
|---|---|---|---|---|
| router | qwen2.5:3b-instruct-q4_K_M | ~2.0 GB | -1 (always) | ~40–60 tok/s |
| main | qwen2.5:7b-instruct-q4_K_M | ~4.7 GB | -1 (always) | ~15–25 tok/s |
| coder | qwen2.5-coder:7b-instruct-q4_K_M | ~4.7 GB | 300 s | ~15–25 tok/s |
| reasoner | deepseek-r1:7b-instruct-q4_K_M | ~4.7 GB | 300 s | ~10–18 tok/s |
| vision | qwen2.5vl:7b-instruct-q4_K_M | ~4.7 GB | 300 s | ~10–18 tok/s |
| embeddings | qwen3-embedding:0.6b | ~0.64 GB | -1 | very fast |

### Why these models
- **qwen2.5 3B (router):** fast enough to be the always-on classifier and emergency fallback; tiny context cost.
- **qwen2.5 7B (main):** best general-purpose quality per GB on ARM for daily assistant work.
- **qwen2.5-coder 7B:** specialized for code generation/editing.
- **deepseek-r1 7B:** reasoning-heavy tasks (planning, math, analysis).
- **qwen2.5vl 7B:** image understanding (screen, camera, photos).
- **qwen3-embedding 0.6B:** best quality-per-RAM embedder for RAG/memory (Apache-2.0, 1024-dim, 32K ctx); nomic-embed-text kept as fallback (C9).

## 3. RAM Budget (the hard rule)

```
Total               24.0 GB
OS + system          ~2.5 GB
FastAPI + agent      ~1.0 GB
Vector DB + SQLite   ~0.5 GB
─────────────────────────────
Always resident: router(2.0) + main(4.7) + embeddings(0.64) ≈ 7.3 GB
Free for specialists        ≈ 13.0 GB  → exactly ONE specialist at a time
```

**Consequence:** specialist tasks are serialized. If a coding task is running while a vision request arrives, the vision model waits for the coder to idle out (or the task is queued). The router enforces this.

## 4. Router Logic

```
task_type  ──►  lookup  ──►  model dept
┌──────────────────────────────────────────────────────────────┐
│ quick_query, system, comms, knowledge, memory   → main       │
│ coding, debug, git, deploy                       → coder      │
│ complex_plan, math, deep_analysis, summary      → reasoner   │
│ image_analysis, screen_capture, camera_view      → vision     │
│ unknown                                           → main (default) │
└──────────────────────────────────────────────────────────────┘
```

### Runtime flow (`route_model` node)
1. Read `state.task_type`.
2. Lookup target dept in registry.
3. If target ≠ main: `ollama_client.load(target, keep_alive=300)` — ARM specialists take 5–20 s to first load; subsequent calls are instant.
4. If load fails/times out → **fallback chain**: target → main → router(3B). Never a silent failure.
5. Set `state.model_route`; agent_loop now uses that model.

### Temperature & behavior per dept
| Dept | temp | max_tokens | Notes |
|---|---|---|---|
| router | 0.0 | 2048 | deterministic classification |
| main | 0.7 | 4096 | conversational, a bit creative |
| coder | 0.2 | 8192 | precise, low hallucination |
| reasoner | 0.6 | 8192 | step-by-step reasoning |
| vision | 0.3 | 4096 | factual image description |
| embeddings | — | — | no generation |

## 5. config/models.yaml

```yaml
router:
  name: qwen2.5:3b-instruct-q4_K_M
  keep_alive: -1
  temperature: 0.0
  max_tokens: 2048
  fallback: []

main:
  name: qwen2.5:7b-instruct-q4_K_M
  keep_alive: -1
  temperature: 0.7
  max_tokens: 4096
  fallback: [router]

coder:
  name: qwen2.5-coder:7b-instruct-q4_K_M
  keep_alive: 300
  temperature: 0.2
  max_tokens: 8192
  fallback: [main, router]

reasoner:
  name: deepseek-r1:7b-instruct-q4_K_M
  keep_alive: 300
  temperature: 0.6
  max_tokens: 8192
  fallback: [main, router]

vision:
  name: qwen2.5vl:7b-instruct-q4_K_M
  keep_alive: 300
  temperature: 0.3
  max_tokens: 4096
  fallback: [main, router]

embeddings:
  name: qwen3-embedding:0.6b
  keep_alive: -1
  temperature: 0
  max_tokens: null
  fallback: [nomic-embed-text]
```

## 6. models/ollama_client.py — design

| Function | Responsibility |
|---|---|
| `invoke(dept, messages, images=None)` | Call Ollama with dept params; enforce timeout |
| `load(dept)` | Set keep_alive, warm the model, return load time |
| `embed(texts)` | Embeddings via qwen3-embedding (fallback nomic) for Components 9–11 |
| `health()` | Poll Ollama `/api/ps` → resident model map |
| `_fallback_chain(dept, err)` | Walk `fallback` list, return working model |

**Error handling:**
- Model not found → auto-pull from registry with a startup check (`ollama pull` during first boot only).
- OOM risk → router refuses to load a second specialist while one is resident (serialize tasks); logs eviction timer.
- Timeouts → per-call `OLLAMA_TIMEOUT` (60 s gen, 30 s connect).

## 7. models/router.py — design

- `route_task(task_type) -> DeptName` : pure lookup (Section 4 table)
- `attach_router_state(state)` : sets `state.model_route`
- Exposes a `task_type → model` mapping loaded from `models.yaml` so it stays config-driven.

## 8. models/registry.py — design

- Loads `config/models.yaml` into `ModelSpec` dataclasses.
- Validates names against Ollama at startup (`ollama list`).
- `get(dept) -> ModelSpec`, `default()` -> main, `fallback_for(dept)`.
- Central import — every component asks the registry for models, never hardcodes names.

## 9. Verification Harness — tests/bench_models.py

- Sends 2–3 sample prompts per department; logs per-call: latency, tokens, output length, correctness pass/fail.
- Measures specialist eviction timing (idle 300 s → unload confirmed via `/api/ps`).
- Confirms fallback triggers by simulating a stopped model.
- Output: table + pass/fail summary. Runtime ≈ 5 min on A1.

## 10. File Layout (Component 2)

```
models/
├── registry.py        # ModelSpec dataclasses + yaml loader
├── router.py          # task_type → dept → model decision
└── ollama_client.py   # invoke/load/embed/health + fallback chain
config/
└── models.yaml        # every model, all knobs, no code
tests/
└── bench_models.py    # latency + fallback verification
```

## 11. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| All-local models | Ollama on A1 | No API cost; privacy; 24/7 availability |
| Router model | qwen2.5 3B | Fast, tiny, doubles as fallback |
| Main worker | qwen2.5 7B | Best ARM quality-per-GB for general tasks |
| Specialists | coder/reasoner/vision 7B | Department-tuned quality |
| Embeddings | qwen3-embedding:0.6b | Apache-2.0, 1024-dim, 32K ctx; best quality-per-RAM (C9) |
| Eviction | keep_alive=300 s | Predictable RAM; idle unload |
| One-specialist rule | enforced by router | Only 13 GB headroom |
| Fallback chain | dept → main → router | Never a silent failure |
| Config-driven | models.yaml | Tune models without touching code |
