# Component 14: Callbacks / Tracing — Seeing What DON Did

## 1. Overview

Every run must be **auditable**: what model, what tools, what tokens, what breaks. **Arize Phoenix** (`arizephoenix/phoenix`, ~11k stars, Elastic-2.0 source-available **free** to self-host) is now the primary tracing + debug UI — a **single local process** (~1–2 GB RAM, SQLite backend, arm64 image) with **first-class LangGraph/LangChain tracing** via `openinference-instrumentation-langchain` (`register(auto_instrument=True)`): agent trees, node/tool/LLM spans, full I/O and token counts, plus evals and error drill-down for free. Fully local, no cloud.

The custom SQLite `RunLogger` is **kept as a cheap fallback + raw audit log** (redacted, batched), but the hand-built debug page is dropped — Phoenix's UI supersedes it.

```
agent run ──► OpenInference instrumentation (auto) ──► Arize Phoenix (local, SQLite)
      │                                                    │
      ▼                                                     ▼
trace.py (RunLogger) → run_log (SQLite)        debug UI at http://<a1>:6006
      │                                         (trace tree, tokens, errors, evals)
      ▼
kept as raw audit + daily rollups (retention rules below)
```

## 2. What We Trace (per run)

| Field | Source | Used for |
|---|---|---|
| `run_id`, `thread_id`, `device`, `user` | graph state | correlation |
| `task_type`, `model_route`, model used | classify/router | routing health |
| nodes visited + timings | LangGraph callbacks | where time went |
| tool calls: name, args (redacted), result summary, status | tool_node | audit + guard trail |
| token/iteration counters | state breakers (C1 §7) | budget usage |
| interrupts: payload, decision, latency | guard | approval audit |
| errors/exceptions | wrapper | reliability |

**Redaction:** secrets, full tool args for sensitive tools, and message bodies over 500 chars are truncated in logs (`trace.py` applies a redact list).

## 3. Callback Wiring

- **Primary: OpenInference auto-instrumentation** (`openinference-instrumentation-langchain` + `opentelemetry-exporter-otlp`) → Phoenix. Register once at process start — **zero changes to node code**.
- **Fallback/audit:** a custom `RunLogger` implementing LangGraph callback handlers is attached at graph compile time for the raw redacted `run_log`.
- Low overhead: async append to SQLite, batched writes (flush every 2s or 100 events), never blocks the graph.

## 4. Storage

- `run_log` SQLite table (same DB family as C1 §6 / C7 `chat_log`).
- Retention: raw runs 30 days; daily rollup keeps aggregate stats (avg latency, tool use counts, error rates) for 1 year.
- Rollup feeds the "how healthy is DON" checks (C16 deployment monitoring).

## 5. Debug UI (Phoenix)

- **Phoenix dashboard** at `http://<a1-tailscale-ip>:6006` (bound to Tailscale only): project/trace tree per run, node/tool/LLM spans with I/O + tokens, model latency, error drill-down, prompt playground, experiments/evals.
- Filter by device, task_type, status (via run metadata propagated into spans).
- Read-only for humans; authenticated via Tailscale (no public exposure).
- The custom SQLite debug page is **not built** — Phoenix covers it.

## 6. Failure Detection

- Per-run error rate and per-node error count tracked; repeated failures (same tool 3×, C6 §7) surface as warnings on the debug page.
- Silent-failure guard: a run that returns no reply in 10 min is flagged (feeds the alerter in C16).

## 7. File Layout (Component 14)

```
trace/
├── logger.py              # RunLogger callbacks (raw audit fallback), batched writes
├── phoenix.py             # OpenInference + OTLP wiring → Arize Phoenix
├── redact.py              # redaction rules (secrets, args, long bodies)
├── store.py               # run_log + rollup queries
config/
├── trace.yaml             # retention, redact list, batch settings
└── phoenix.yaml           # phoenix port, project names, eval config
tests/
└── bench_trace.py         # callback fires, redaction, rollup
```

Phoenix runs as a single systemd service (arm64 docker image or `pip install arize-phoenix`).

## 8. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Observability | **Arize Phoenix** (free, local, single process) | Native LangGraph tracing + evals, supersedes hand-built debug UI |
| License | Elastic-2.0 source-available (free self-host) | Acceptable; no cloud, no cost. Langfuse (MIT core) is the heavier alt (~6 containers) |
| Fallback | custom SQLite RunLogger (raw audit + rollups) | Redaction control + cheap retry path |
| Wiring | OpenInference auto-instrumentation | Zero node-code changes |
| Redaction | secrets + sensitive args truncated | Privacy in logs |
| Storage | Phoenix SQLite + run_log SQLite + daily rollup | Bounded, queryable |
| Failure signal | per-node/tool error stats | Feeds C16 alerts |
