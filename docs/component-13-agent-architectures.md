# Component 13: Agent Architectures — DON Assembled

## 1. Overview

Components 1–12 are the parts. Component 13 **wires them into the running agent**: the full main graph, the specialist sub-graphs (coding, vision), and the supervisor/resume patterns that hold it together. This is the blueprint `core/graph.py` implements.

## 2. The Main Graph (DON core)

```
                     ┌─────────────────────────────┐
  input ────────────►│  classify_input (3B router) │
 (voice/text/image/  └──────────────┬──────────────┘
  notif)                            │ task_type, media
                                    ▼
                     ┌─────────────────────────────┐
                     │  route_model (C2)           │───► specialist sub-graph
                     └──────────────┬──────────────┘      (below) if coder/vision
                                    ▼
                     ┌─────────────────────────────┐
                     │  retrieve (C11, optional)   │── pre-fetch context blocks
                     └──────────────┬──────────────┘
                                    ▼
                     ┌─────────────────────────────┐
   ┌───────────────►│  agent_loop (dept model)     │───┐
   │                └──────────────┬──────────────┘    │ final answer
   │                    │ emits tool_call            │  │
   │                    ▼                            │  ▼
   │       ┌─────────────────────────────┐   ┌──────────────────────┐
   │       │  guard / approve (C1 §8)    │   │  responder (C1 §4.6) │
   │       │  interrupt() if tool        │   │  TTS / notify / reply │
   │       └──────────────┬──────────────┘   └──────────────────────┘
   │               approved│                     ▲
   │                      ▼                      │
   │       ┌─────────────────────────────┐       │
   │       │  tool_node (C6)             │───────┘
   │       └─────────────────────────────┘  result → loop
   └────────────────────────────────────── (until answer / breakers)
```

**Edges (all conditional):**
- classify → route: always
- route → specialist subgraph (if `task_type` in {coding, image_analysis})
- agent_loop → guard (tool_call present) / responder (final answer)
- guard → tool_node (approved) / agent_loop (rejected → re-plan)
- tool_node → agent_loop (loop) — circuit breakers (C1 §7) terminate the loop

## 3. Specialist Sub-Graphs

Specialist models (coder, vision, reasoner) don't replace the core loop — they run as **contained sub-graphs** that the main graph calls and collects from:

```
MAIN agent_loop
   │ calls specialist (via a special tool: specialist_invoke)
   ▼
SPECIALIST SUB-GRAPH (runs with its own model + narrowed tools)
   │   e.g. CODING: coder model + {file_read, file_write, git, run_tests, github}
   │   e.g. VISION: vision model + {analyze_image, screen_read}
   │   guarded internally? no — parent guard already approved the invocation
   ▼
   returns a single structured result → injected as tool result in main loop
```

**Rules:**
- Specialists have **narrowed tool sets** (their own relevant tools only) — keeps their context focused.
- Specialists never emit user-facing messages directly; the main loop relays.
- One specialist active at a time (RAM rule, C2 §3) — the router enforces by model availability.
- Specialist result is capped (2 KB) before returning to main context.

## 4. Supervisor Pattern

- The **classifier + router act as a lightweight supervisor**: they decide model + sub-graph + priority.
- No heavyweight hierarchical supervisor (LangGraph supervisor package not needed at this scale) — the conditional edges ARE the supervision.
- Proactive tasks (C5 phase, scheduled briefings) enter the same graph at `classify_input` with `source=scheduler`, same guard rules apply.

## 5. Interrupt & Resume (human-in-the-loop recap)

- `interrupt()` pauses at the guard; checkpoint saved (C1 §6).
- Resume is exactly-once: approval returns the graph to the same point, no re-execution of prior nodes. **LangGraph 1.x:** use `stream_events(version="v3")` + `Command(resume=...)` for HITL.
- Cross-device: same `thread_id`, so a laptop-issued approval resumes an Android-started task (C1 §6).
- Timeout: an interrupt with no response for 24h is auto-resolved (not approved — dropped with a logged note to the user).
- **⚠️ Known issue (langgraph#6338):** verify interrupt/resume inside `create_agent` sub-agents before relying on it — use explicit `interrupt()` in the main graph for approvals.

## 6. Streaming & UX Integration

- `stream_mode="messages"` / custom: the responder streams tokens for TTS (C15) and live notification updates on Android/laptop.
- Tool progress (`"DON is checking the weather…"`) streams as status events on the device bridge — the user isn't left staring at silence during ARM-long tool calls.

## 7. File Layout (Component 13)

```
core/
├── graph.py              # main graph wiring (all nodes/edges)
├── subgraphs/
│   ├── coder.py          # coding specialist sub-graph
│   ├── vision.py         # vision specialist sub-graph
│   └── reasoner.py       # deep-reasoning sub-graph
└── supervisor.py         # classifier+router orchestration glue, task sources
tests/
└── bench_graph.py        # end-to-end runs per path type (C1 §3)
```

## 8. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Main loop | single graph, conditional edges | Matches scale; simple to debug |
| Specialists | sub-graphs, narrowed tools, parent-approved | Focused context, one-at-a-time RAM |
| Supervision | classifier+router as lightweight supervisor | No need for heavyweight supervisor |
| Interrupt resume | exactly-once, cross-device thread_id | Safety + UX |
| Interrupt timeout | 24h → auto-drop, logged | No orphaned approvals |
| Streaming | messages + status events | TTS + device UX |
