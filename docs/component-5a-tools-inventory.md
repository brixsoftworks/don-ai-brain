# Component 5a: Tool Inventory — Best GitHub Sources Per Department

## 0. Strategy Update: MCP Is Now a First-Class Tier

Research shows the best-in-class tooling now ships as **MCP servers** (Home Assistant, Jellyfin, yt-dlp, search). LangGraph ingests these natively via `langchain-mcp-adapters` (`load_mcp_tools`), which converts MCP tools into LangChain `BaseTool`s — they drop straight into the ToolNode and BigTool registry.

**Final tier structure:**
| Tier | Source | Installed via |
|---|---|---|
| 1 | `langchain-community` bundled tools | `pip install langchain-community` |
| 2 | **Dedicated MCP servers (GitHub)** | `langchain-mcp-adapters` + the server's package |
| 3 | Specialized pip libs wrapped in thin `@tool` | `pip install <lib>` |
| 4 | Custom `@tool` (only when nothing fits) | our code |

The BigTool semantic-retrieval layer (Component 5 §3) stays unchanged — it works identically with MCP-derived tools.

---

## 1. System & Computer Use (Desktop Control)

**Goal (user requirement):** DON can open ANY app/software and drive it like a human — click any button, type text, read screens, control the mouse and keyboard. Tool must be free and GitHub-hosted.

| Tool | Source | License | What it gives DON | Where it runs |
|---|---|---|---|---|
| **opendesk** | `vitalops/opendesk` (GitHub + PyPI) | MIT, free | **Full computer use in one framework**: `app` (open/close/focus ANY app), `ui` (click/type by element NAME — no coordinates, no vision tokens), `mouse`, `keyboard`, `screenshot` (with numbered click-target boxes, Set-of-Marks), `ocr`, `clipboard`, `learn` (record a workflow once, replay anytime), `schedule` (run tasks on a timer), `audit`. **Has a native LangChain integration** (becomes `BaseTool`s directly), is an MCP server, and supports **remote machine control** over an encrypted WebSocket. macOS/Linux/Windows. | laptop client, driven remotely from the A1 |
| **agent-computer-use** | `kortix-ai/agent-computer-use` | MIT, free | Rust CLI, accessibility-tree based (AT-SPI2 on Linux, UIAutomation on Windows, AX on macOS) — **0 vision tokens**, deterministic clicks, works with local models. Precompiled binaries, no Rust toolchain needed. Fallback for anything opendesk misses. | laptop client (alt) |
| `ShellTool` | langchain-community | MIT | Terminal on the cloud server (heavily sandboxed) | cloud A1 |
| `PythonREPLTool` | langchain-community / langchain-experimental | MIT | Python eval in jail | cloud A1 |
| `FileManagementToolkit` | langchain-community | MIT | read/write/list/move/search | cloud A1 |
| `psutil` monitoring | custom `@tool` | — | CPU/RAM/disk/battery | cloud A1 |

**Decision — opendesk is the primary desktop-control tool** (decisive: native LangChain integration + remote machine control + click-by-element-name that a 7B local model can actually use). agent-computer-use stays as a zero-vision fallback for reliability. ShellTool + FileManagementToolkit cover the cloud server itself.

### How desktop control fits DON's architecture

```
CORE:  A1 server ── LangGraph agent loop (7B model)
         │  calls opendesk tools (app / ui / click / type / ...)
         ▼
LINK:  opendesk MCP/WS bridge ── encrypted, paired WebSocket ──► laptop
         │                                                   (screenshot, UI tree, mouse, keyboard)
         ▼
LAPTOP: opens/changes the target app, clicks buttons, types, OCRs — like a human
```

- opendesk **runs on the laptop** and is **driven remotely** from the A1 via `opendesk pair` / `opendesk serve` (mutually authenticated, X25519 + ChaCha20-Poly1305 encryption) — same tools, remote target. Registered in `tools/` via its LangChain integration / MCP adapter (C5 §2 tier-2, C6 §4).
- **7B-friendly:** the `ui` tool clicks by element name from the OS accessibility tree — no screenshots, no coordinate guessing (pure-vision clicking is unreliable on a 7B model). Vision/`screenshot`/`ocr` only when DON must read unusual screens, using the vision eye (C13 §3).
- **Safety:** desktop-control tools are `action`/`destructive` in `ToolSpec.danger` (C5 §6) → the guard (C1 §8) always shows an **"DON wants to control your desktop"** approval card with the full action before anything moves. Every action is auditable via opendesk's `audit` tool + our run log (C14).

---

## 2. Web & Information

| Tool | Source | Stars | Why |
|---|---|---|---|
| DuckDuckGo search | langchain-community | — | Free, keyless, headless (already chosen) |
| **crawl4ai** | `unclecode/crawl4ai` | **78,000+** | Best-in-class LLM-ready crawler: clean Markdown, JS rendering, async, Apache-2.0. Replaces trafilatura for page extraction. |
| **searchts** | `capad-xyz/searchts` | — | Keyless read/search/transcribe with anti-bot escalation ladder (curl_cffi → Jina → stealth browser) + multi-engine rank fusion + MCP server, ~80 tokens/call. **Phase-2 upgrade over bare DDG** (confirmed best fit for a 7B model in Aug 2026 research) |
| god-search | `crackion-com/god-search` | — | Keyless 7-engine search (Google/Bing/DDG/Brave/Reddit/GitHub/Wikipedia), MCP+HTTP+CLI. Backup option |
| Wikipedia | langchain-community | — | Free reference |
| Weather | wttr.in wrapped | — | Keyless |
| RSS (news/podcasts) | `feedparser` | — | Keyless aggregation |

**Decision:** DuckDuckGo (search, keep) + **crawl4ai** (extraction). **searchts** as the phase-2 upgrade if DDG rate-limits become annoying (its anti-bot escalation + MCP server suit a local 7B assistant).

---

## 3. Voice (STT / TTS / Wake — cross-cutting, planned here)

| Tool | Source | Why |
|---|---|---|
| **Kokoro-82M** (via `kokoro-onnx`) | `hexgrad/Kokoro-82M` + `thewh1teagle/kokoro-onnx` | Natural-sounding TTS, 82M params, Apache-2.0, ~300 MB, CPU in ~2s load, **sentence-level streaming** (`create_stream`). Deep male voices + speed 0.85–0.90 = DON's villain timbre. |
| **whisper.cpp** (`small`) | `ggml-org/whisper.cpp` | **Best ARM CPU STT** — handwritten NEON SIMD, single C++ binary, ~460 MB, MIT. Replaces faster-whisper on aarch64 (CTranslate2 wheels unreliable, slower on CPU). |
| **Heed** | `AndreiBulzan/heed-wakeword` | Custom "Hey DON" wake word trained in **seconds** (web UI/CLI), 108 KB model, Apache-2.0, 1–15 ms inference. Replaces openWakeWord (training broken on py3.12+). Backup: `livekit/livekit-wakeword`. |
| Silero VAD v6.2 | `snakers4/silero-vad` | Voice activity detection, ~2 MB, <1 ms/chunk, barge-in — still the standard |
| Piper | `OHF-Voice/piper1-gpl` | Fallback TTS only |
| Moonshine v2 | `moonshine-ai/moonshine` | Upgrade path: 200M streaming STT (MIT) if latency needs improving |
| sherpa-onnx | `k2-fsa/sherpa-onnx` | All-in-one VAD+STT+TTS harness (aarch64 builds) — fallback harness only |

**Decision:** Kokoro-onnx (primary TTS) + whisper.cpp small (STT) + Heed (wake) + Silero (VAD). This **updates** the earlier faster-whisper/openWakeWord picks — Component 15 (Voice) is fully specced on this stack.

**Architecture references (study, don't copy):**
- `InterGenJLU/jarvis` — streaming LLM→sentence→TTS pipeline, router design, local-everything.
- `Sycatle/local-jarvis` — Rust daemon pattern, D-Bus, skills-as-tool-calls.
- `openocto-dev/openocto` — persona system, push-to-talk, local STT/TTS.
- `openclaw/openclaw` (MIT, ~386k stars) — full personal-assistant agent; local-LLM capable. Reference for voice/agent UX only; we keep our own LangGraph build.

---

## 4. Communication

| Tool | Source | Notes |
|---|---|---|
| Gmail read/send | Google `google-api-python-client` (official) | OAuth `client.json`; enabled later |
| Google Calendar | same official client | Same OAuth flow |
| Telegram bot | custom `@tool` over `python-telegram-bot` | Free reach-back channel; most reliable |
| Push notifications | custom `@tool` via MQTT/ntfy | To Android |
| HA notifications | via ha-mcp (below) | Notify via Home Assistant |

---

## 5. Coding & Data

| Tool | Source | Notes |
|---|---|---|
| GitHub | langchain-community `GitHubToolkit` (pygithub) | PAT, minimal scopes |
| SQL | langchain-community `SQLDatabaseToolkit` | read-only user |
| Python REPL | `PythonREPLTool` | sandboxed |
| JSON tools | langchain-community | get value / list keys |

---

## 6. Home & IoT

| Tool | Source | Stars | Why |
|---|---|---|---|
| **ha-mcp** | `homeassistant-ai/ha-mcp` | **4,400+** | 88 tools (control, automations, dashboards, cameras, history). **Search-based tool-discovery mode built for local/small models** — critical for qwen-7B context. |
| robbrad/homeassistant-mcp | `robbrad/homeassistant-mcp` | 102 | 40 tools, BM25 discovery, lighter alt |
| MQTT | `paho-mqtt` wrapped | — | Generic device control / Android bridge |

**Decision:** **ha-mcp** via MCP adapter with its search-discovery mode (`ENABLE_TOOL_SEARCH=true`). Requires a Home Assistant instance (home LAN) + long-lived token.

---

## 7. Media & Entertainment

| Tool | Source | Stars | Why |
|---|---|---|---|
| **yt-dlp** | `yt-dlp/yt-dlp` | 90,000+ | Keyless downloads, 1000+ sites |
| **jellyfin-mcp** | `jaredtrent/jellyfin-mcp` | 26 | 31 tools: search library, **control playback on any device**, playlists, subtitles, metadata. Multi-arch ARM64 docker image. |
| feedparser | `kurtmckee/feedparser` | — | Podcasts/news RSS |
| MPD | `python-mpd2` | — | Local music playback on the A1 |

**Decision:** Jellyfin (if a home Jellyfin server exists) via its MCP server, else yt-dlp + MPD + feedparser. Playback targets Android/laptop via the device bridge.

---

## 8. Memory & Personal

| Tool | Source | Stars | Why |
|---|---|---|---|
| **langmem** | `langchain-ai/langmem` | 1,600+ | **Official LangChain memory layer**, native LangGraph store integration, background memory manager. Matches our stack exactly. |
| mem0 | `mem0ai/mem0` | **63,000+** | Most popular universal memory layer; has LangGraph guide; hybrid semantic+BM25+entity retrieval |
| mempalace | `MemPalace/mempalace` | 58,000+ | Best-benchmarked raw retrieval (96.6% R@5), ChromaDB default, fully local |

**Decision (deferred to Component 12, but leaning):** `langmem` + LangGraph's own `BaseStore` because it removes a separate dependency and is the natural fit for a pure-LangGraph build. mem0/mempalace are strong alternatives if benchmarks matter more than stack cohesion.

### 8.1 Learning from chats (user requirement)

DON learns from every conversation via the `chat_log` pipeline (Component 7 §2.2):
1. **RAG** over chat history — recalls your phrasing, preferences, past requests (works today).
2. **Memory facts** — extracted into the long-term store by the background extractor.
3. **Training JSONL** — archived in **LLaMA-Factory's ShareGPT `messages` format** (OpenAI-style, chat-template safe) for a future LoRA fine-tune on a rented GPU (not practical on A1 CPU).

**Fine-tune prep pipeline (2026, all ARM-safe prep steps):** raw `chat_log` → clean/dedup with HuggingFace `datasets` (+ optional `distilabel` quality gates) → write OpenAI-style `messages` JSONL matching LLaMA-Factory `dataset_info.json` → train with **LLaMA-Factory** or **Unsloth** on the rented GPU → export LoRA → merge to GGUF → drop into Ollama on the A1.

Fine-tuning is a later-phase deliverable; the corpus and RAG behavior are built now.

---

## 9. Security

| Tool | Source | Notes |
|---|---|---|
| Secrets | `python-dotenv` + `keyring` | Keys never in code/prompts |
| Sandboxing | opendesk sandbox + ShellTool deny-list + jailed roots | Component 5 §7 stays |
| MCP gating | MCP tool annotations (`readOnlyHint`, `destructiveHint`) | Mapped into `ToolSpec.danger` |

---

## Integration Map: MCP Servers → ToolNode

```
MCP server (stdio/HTTP)            e.g. ha-mcp, jellyfin-mcp
        │
langchain-mcp-adapters.load_mcp_tools()   ── converts to BaseTool
        │
tools/registry.py  ── reads annotations → ToolSpec.danger
        │
BigTool store  ── semantic retrieval at runtime
        │
ToolNode (Component 6) executes after guard approval
```

## Install Plan Update

```
pip install langchain-mcp-adapters mcp
pip install opendesk[core,mcp,remote]     # desktop control (C5a §1) — laptop install, driven from A1
pip install crawl4ai                       # replaces trafilatura
pip install kokoro kokoro-onnx             # TTS (Component 15)
pip install heed-wakeword                  # wake word (Component 15)
# STT: whisper.cpp prebuilt binary (linux aarch64) — not pip
pip install python-telegram-bot paho-mqtt feedparser yt-dlp python-mpd2
pip install docling markitdown             # document ingestion (Component 7)
# MCP servers are pip/git packages: ha-mcp (custom component or pip), jellyfin-mcp (docker)
```

**Resource note:** MCP servers run as separate processes. On the A1 keep them stdio + lazy (spawned only when a relevant tool is first called). Jellyfin itself runs at home, not on the A1.

## Decision Log (additions to Component 5)

| Decision | Choice | Rationale |
|---|---|---|
| MCP tier | `langchain-mcp-adapters` | Best tools ship as MCP; native LangGraph support |
| Desktop control | opendesk (MIT) + agent-computer-use fallback | User-required "open & control any app"; LangChain-native, remote-driven, 7B-friendly click-by-name |
| Web extraction | crawl4ai (78k stars) | Best-in-class LLM-ready output |
| Home Assistant | ha-mcp with search-discovery | Built for small/local models |
| Media server | jellyfin-mcp + yt-dlp | Full control + downloads, keyless |
| Memory | langmem (leaning, deferred to C12) | Native LangGraph fit |
| TTS | Kokoro via kokoro-onnx (over Piper) | Better voice, sentence streaming, same CPU cost |
| STT | whisper.cpp small (over faster-whisper) | Best ARM CPU perf, single binary, MIT |
| Wake word | Heed (over openWakeWord) | Trains "Hey DON" in seconds, 108 KB, Apache-2.0 |
