# Component 1: LangGraph — The Brain

## 1. Overview

JARVIS is orchestrated by **LangGraph**, a stateful graph framework for agent loops. Instead of one-shot chains, every interaction flows through a persistent graph where:

- All context lives in a shared **state object** passed node→node.
- Each node performs one job (classify, route, plan, act, guard, respond).
- Edges (including **conditional edges**) decide what happens next.
- An **SQLite checkpointer** snapshots every step, so conversations survive reboots and resume across devices.

### Deployment context
| Item | Value |
|---|---|
| Host | Oracle Cloud A1 (4 ARM OCPUs, 24 GB RAM) |
| Models | 100% local via Ollama (no cloud LLM APIs) |
| Clients | Android phone + laptop, thin clients over Tailscale |
| Users | Single user (schema is multi-user ready) |
| Safety | Interrupt/approval before EVERY tool action |

## 2. Core LangGraph Concepts Used

| Concept | Role in JARVIS |
|---|---|
| `StateGraph` | Defines the whole agent as nodes + edges |
| `State` (TypedDict) | Shared brain-slate passed through the graph |
| Reducers | How state merges on update (e.g. `add_messages`) |
| Nodes | One function per step (classify, route, agent, guard, tool, respond) |
| Conditional edges | Router branches on `task_type` / `model_route` |
| `ToolNode` | Executes approved tools inside the agent loop |
| `Command` | Programmatic node→node routing (graph stay/end) |
| `Checkpointer` | SQLite snapshot per `thread_id` (persistence) |
| `interrupt()` | Pause graph for human approval before tool execution |

## 3. JARVIS Graph Design

```
                 ┌──────────────────────┐
  INPUT ─────────►│    classify_input    │  (device, media, task_kind)
  (voice/text/    └──────────┬───────────┘
   image/notif)              │ sets state.task_type, state.media
                             ▼
                 ┌──────────────────────┐
                 │     route_model      │  (maps task_type → model dept,
                 └──────────┬───────────┘   loads specialist via Ollama)
                            │
                            ▼
                 ┌──────────────────────┐        ┌─────────────────┐
   ┌────────────►│     agent_loop       │───────►│    tool_node    │
   │             │  (planner LLM picks  │        └────────┬────────┘
   │             │   next tool or final │                 │
   │             │   answer)            │◄────────────────┘
   │             └──────────┬───────────┘   results appended to state
   │          loop while tool calls remain
   │                        │
   │                        ▼
   │             ┌──────────────────────┐
   │             │   guard / approve    │──interrupt() before every tool──►
   │             │  (human-in-the-loop) │   notify device → wait for reply
   │             └──────────┬───────────┘   approved ? proceed : re-plan
   │                        │
   │                        ▼
   │             ┌──────────────────────┐
   │             │      responder       │──► TTS / notify / action result
   │             └──────────────────────┘
   │                        │
   └────────────────────────┘   final answer → graph END
```

**Path types:**
1. **Simple answer** (no tools): `classify → route → agent_loop → responder → END`
2. **Tool task**: `classify → route → agent_loop ⇄ guard ⇄ tool_node (loop) → responder`
3. **Image task**: `classify (detects image) → route_model(vision) → vision pre-node → agent_loop → ...`
4. **Complex plan**: routed to `reasoner` model, then agent_loop executes steps

## 4. Node Specifications

### 4.1 classify_input
- **Inputs:** raw user message, `device`, `media` (image/audio/file), `user_id`
- **Logic:** uses the small router model (3B) to tag the task: quick_query / system / comms / knowledge / coding / complex_plan / image_analysis / unknown
- **Outputs:** `state.task_type`, `state.media` normalized
- **Model:** `qwen2.5:3b-instruct-q4_K_M` (always resident)

### 4.2 route_model
- **Inputs:** `state.task_type`
- **Logic:** lookup table (Component 2) → department model; ensures the specialist is loaded (Ollama keep_alive), falls back to `main` on failure
- **Outputs:** `state.model_route` (which dept model drives agent_loop)

### 4.3 agent_loop
- **Inputs:** `state.messages`, `state.model_route`, `state.tool_results`
- **Logic:** ReAct-style: the department LLM reads conversation + tool results and either (a) emits a tool call, or (b) emits a final answer. Runs in a loop; each cycle increments `state.iteration_count` and `state.tokens_used`.
- **Loop termination:**
  - LLM answers without a tool call → exit to responder
  - Tool returns `FINAL` signal → exit to responder
  - Circuit breakers hit (Section 7) → forced summary → responder

### 4.4 guard (approval)
- **Inputs:** proposed tool call from agent_loop
- **Logic:**
  1. Serialize proposed action (tool name + args, human-readable).
  2. `interrupt(payload)` → graph pauses, checkpoint saved.
  3. Device notified: "JARVIS wants to: <action>. Approve?"
  4. Resume with `Approved` → tool_node executes.
     Resume with `Rejected` → agent re-plans (excludes that action).
- **Model:** none (deterministic)

### 4.5 tool_node
- **Inputs:** approved tool name + arguments
- **Logic:** dispatches to the tool module (Component 5), validates output, appends result to `state.tool_results` with a per-tool token guard.
- **Outputs:** tool result dict (or error) → back to agent_loop

### 4.6 responder
- **Inputs:** final agent message + context (device, media)
- **Logic:** formats reply for the originating device; triggers TTS for voice, notification for push; writes memory notes (Component 12).
- **Outputs:** response delivered; graph END

## 5. State Schema (AgentState)

```python
from typing import Annotated, Any, TypedDict
from langgraph.graph.message import add_messages

class AgentState(TypedDict, total=False):
    # --- conversation ---
    messages: Annotated[list, add_messages]   # full history, appended by reducers
    # --- context ---
    user_id: str                              # "pa" (single-user, schema ready)
    device: str                               # "android" | "laptop"
    media: dict                               # {type, path/hash, caption?}
    timestamp: str                            # ISO time of input
    # --- routing ---
    task_type: str                            # set by classify_input
    model_route: str                          # set by route_model
    # --- execution ---
    tool_results: list                        # outputs fed back to LLM
    pending_action: dict                      # {tool, args, reason} for guard
    iterations: int                           # loop counter (circuit breaker)
    tokens_used: int                          # token budget counter
    # --- memory ---
    memory: dict                              # facts pulled from long-term store
    # --- output ---
    reply: str                                # final response for responder
```

## 6. Checkpointer & Persistence

- **Engine:** SQLite (via `langgraph.checkpoint.sqlite`)
- **Key:** `thread_id` = conversation id (e.g. UUID created on first message)
- **Behaviour:**
  - Every node transition is snapshotted → full crash recovery.
  - Android ↔ laptop switching = same `thread_id` → seamless resume.
  - Interrupt pauses save the graph mid-flight → approval resumes exactly where it paused, even after a server reboot.
- **Pruning:** conversations older than 90 days archived to long-term store
  (Component 12) to keep the DB small.

### 6.1 chat_log table (training-data source)

In addition to the checkpointer (internal graph state), every user/agent turn is
appended to a clean `chat_log` table:

```
chat_log(id, thread_id, ts, role, content, tool_calls, tool_results)
```

This is what feeds "DON learns from my chats" (Component 7 §2.2) — RAG chunks,
memory extraction, and the future fine-tuning corpus. The checkpointer is for
resuming graphs; `chat_log` is for learning from history.

## 7. Loop Control — Free-Tier Circuit Breakers

ARM inference is slow (~15–25 tok/s for 7B), so runaway loops burn hours.

| Breaker | Value | Behaviour |
|---|---|---|
| `MAX_ITERATIONS` | 15 | Hard stop → forced answer with partial results |
| `MAX_TOKENS_PER_TASK` | 30,000 | Budget counter → on breach, summarize + answer |
| Tool timeout | 60 s | Hung tool killed, error fed back to agent |
| Idle unload | keep_alive=300 s | Specialists evicted automatically |

Both limits live in `config/` — tunable without code changes.

## 8. Approval Flow (ask before EVERYTHING)

```
agent_loop emits: tool_call(name=rm, args={path: "~/report.docx"})
        │
        ▼
   guard serializes: "JARVIS wants to: delete file ~/report.docx"
        │
        ▼
   interrupt() ──► checkpoint saved ──► push to device: "Approve?"
        │                                    │
        │◄────────── "Approved" ─────────────┘
        ▼                                    │
   tool_node runs rm                         ▼
        │                          "Rejected" ──► agent re-plans
        ▼                                    (state: cannot_use=[rm])
   result → agent_loop → responder
```

- **Plain replies (no tool call) never interrupt** — only actions pause.
- Approval is per-invocation, never blanket (fully compliant with "ask before everything").

## 9. File Layout

```
core/
├── state.py            # AgentState schema + reducers
├── graph.py            # StateGraph wiring, edges, node registration
├── checkpointer.py     # SQLite checkpoint setup
├── prompts.py          # system prompts per department model
└── nodes/
    ├── classify.py     # classify_input node
    ├── router.py       # route_model node (delegates to models/router.py)
    ├── agent.py        # agent_loop planner node
    ├── guard.py        # approval/interrupt node
    └── respond.py      # responder node
```

## 10. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Framework | LangGraph | Stateful loops, interrupts, checkpoints built-in |
| Users | Single (schema ready for multi) | Simpler now, no rewrite later |
| Loop depth | Adaptive, cap 15 / 30k tokens | Max capability within free-tier compute |
| Approval | Interrupt before every tool | User preference: full control |
| Persistence | SQLite checkpointer | Zero extra infra, survives reboots |
| Cross-device | Same thread_id everywhere | Seamless Android ↔ laptop handoff |
