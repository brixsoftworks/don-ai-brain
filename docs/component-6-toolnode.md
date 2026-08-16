# Component 6: ToolNode / Tool Calling — Executing Approved Tools

## 1. Overview

Component 5 defined *what* tools exist. Component 6 defines **how they execute inside the graph**: the `ToolNode`, the retrieval that feeds tools to DON, argument validation, execution safety (timeouts, output caps), and error semantics — so a crashing tool can never crash the agent loop.

```
agent_loop emits tool_call
        │
        ▼
   guard / approve (Component 1 §8)  ── rejected → re-plan
        │ approved
        ▼
   ToolNode (this component)
   ├─ validate args (Component 4 tool_args)
   ├─ execute in thread pool with timeout
   ├─ cap output size
   └─ wrap success/error as ToolMessage
        │
        ▼
   back to agent_loop (result in state.tool_results)
```

## 2. ToolNode Setup

- Built on `langgraph.prebuilt.ToolNode` (bundled with langgraph) — dispatches by tool name, returns `ToolMessage`s.
- Wrapped by our `core/nodes/toolnode.py` to add: timeout enforcement, output capping, and error normalization (all transparent to the graph).
- Optional `ValidationNode` (also in `langgraph.prebuilt`) runs the per-tool Pydantic schema before execution — gives clean arg errors without executing.

## 3. BigTool Retrieval Node

- Runs **before the agent_loop each iteration** (not just once): the task may drift mid-loop.
- `bigtool_retriever.py` calls the semantic store with the current query → returns 5–10 tool IDs → their schemas are injected into DON's context.
- If retrieval is ambiguous, DON also gets the `search_tools()` meta-tool to find more by name/keyword.
- Cheap (embedding call, ~10ms) — no perceptible ARM cost.
- **⚠️ Maintenance caveat (Aug 2026 research):** `langgraph-bigtool` is functional but stale (no activity since mid-2025) and LangGraph's `BaseStore.search(query=...)` has **no SQLite vector backend**. Plan a **thin drop-in replacement**: a custom `bigtool_retriever.py` doing embedding (`qwen3-embedding:0.6b`) → **ChromaDB `tools` collection** (already our stack, C10) → top-N tool IDs. Same interface, one module swap later.

```
state.messages[-1] → embed → BigTool store → top tools → context
```

## 4. MCP Tool Dispatch

- MCP servers (ha-mcp, jellyfin-mcp) are loaded at **startup** via `langchain-mcp-adapters.load_mcp_tools()` → converted to `BaseTool`s → registered like any other tool.
- **stdio servers are spawned lazily** (first use) and kept alive for reuse; killed after idle (same keep_alive philosophy as models). HTTP MCP servers connect directly.
- Every MCP tool's annotations (`readOnlyHint`, `destructiveHint`) map into `ToolSpec.danger` at registration — the guard trusts no raw annotation, it re-derives danger from our own table.

## 5. Execution Safety

| Guarantee | Default | Where |
|---|---|---|
| Per-tool timeout | 60 s | `config/tool_runtime.yaml`; hard-kill via `concurrent.futures` |
| Output cap | 8 KB | truncated with `…[truncated N chars]` marker |
| Threading | thread pool (max 4) | sync tools (shell, MQTT) never block the async graph |
| Error wrapping | `{status: error, message, stderr}` | tool exceptions → ToolMessage, never a graph crash |
| Token accounting | tool results count toward `tokens_used` | feeds the 30k task budget |

**Kill semantics:** tool runs in an executor `Future`; on timeout the future is cancelled; a best-effort process kill is issued for shell/python tools (Popen group), and the agent receives `"tool timed out after 60s"` and must re-plan or give up.

## 6. Result & Error Semantics (rules for DON)

1. **Success** → clean result string fed back to agent_loop.
2. **Invalid args** → `"argument X: expected <type>, got <type>"`; agent re-calls correctly (never crashes).
3. **Tool exception** → error summary; agent re-plans or reports honestly (persona rule: never invent results).
4. **Timeout** → same as (3) with explicit timeout note.
5. **Missing tool** (retrieval gave a stale ID) → `"tool not found; search_tools() for alternatives"`.

**Retry policy:** no automatic retries of tools (cost), except transient network tools (1 retry with 2s backoff) — configured per-tool in `config/tools.yaml`.

## 7. Circuit Breaker Interaction

- Tool execution counts against `iterations` and `tokens_used` (both breakers from Component 1 §7 still apply — a tool-heavy runaway can't exceed them).
- A tool that fails 3× consecutively is **temporarily disabled** for the rest of the conversation (added to `state.tool_blacklist`), forcing DON to use alternatives.

## 8. File Layout (Component 6)

```
core/
├── nodes/
│   └── toolnode.py            # ToolNode wrapper: validation, timeout, caps
└── toolruntime/
    ├── executor.py            # thread pool, Future kills, process-group kill
    ├── result.py              # truncation, error normalization, ToolMessage builder
    ├── bigtool_retriever.py   # BigTool semantic retrieval node
    └── mcp_bridge.py          # MCP server lifecycle + load_mcp_tools
config/
└── tool_runtime.yaml          # timeouts, output caps, thread pool size
```

Wiring into `core/graph.py`: `tool_node` replaces the earlier `tool_node` placeholder (Component 1 §4.5); `bigtool_retriever` is an edge-run before each `agent_loop` entry.

## 9. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Base node | `ToolNode` + optional `ValidationNode` (prebuilt) | Don't reinvent; official |
| Retrieval timing | before each agent_loop iteration | Task drift during loops |
| MCP lifecycle | lazy spawn, idle kill | Save RAM/CPU on A1 |
| Danger mapping | our `ToolSpec.danger` table, annotations only as hint | Guard owns safety |
| Timeout | 60s + process-group kill | No hung tools |
| Output cap | 8 KB default | Protect 7B context |
| No auto-retry | network tools only, 1 retry | Cost control |
| Consecutive failures | blacklist for conversation | Force alternatives |
