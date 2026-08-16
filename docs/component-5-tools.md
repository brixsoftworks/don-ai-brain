# Component 5: Tools — DON's Capability Layer

## 1. Overview

Every capability DON has is a **tool**. Strategy: **don't hand-roll what exists**. We source battle-tested tools from `langchain-community` (the official community integration package), dedicated **MCP servers** (ingested via `langchain-mcp-adapters`), and specialized pip libraries, writing thin `@tool` wrappers only where nothing ready-made fits.

**Per-department GitHub picks are detailed in [`component-5a-tools-inventory.md`](./component-5a-tools-inventory.md)** — highlights: opendesk (desktop control), crawl4ai (web extraction), ha-mcp (Home Assistant), jellyfin-mcp (media), Kokoro (TTS).

Because DON will hold 50+ tools and runs on a 7B local model (context can't fit every tool schema), we use **`langgraph-bigtool`** — LangChain's semantic tool-retrieval layer — so DON loads only the tools relevant to the current task.

## 2. Tool Acquisition Strategy (3 tiers)

| Tier | Source | Examples |
|---|---|---|
| **1. Bundled** | `langchain-community` (pip, MIT, official) | DuckDuckGo, Wikipedia, ShellTool, GitHub, SQLDatabase, Requests, PythonREPL |
| **2. MCP servers** | Dedicated GitHub projects via `langchain-mcp-adapters` | ha-mcp (Home Assistant), jellyfin-mcp (media), yt-dlp MCP |
| **3. Specialized pip libs** | Battle-tested packages, wrapped in thin `@tool` | `crawl4ai` (web extract), `yt-dlp` (media), `feedparser` (podcasts), `python-mpd2` (music), Kokoro (TTS) |
| **4. Custom `@tool`** | Only when nothing fits | Device bridge (MQTT→Android), TTS trigger, memory write, approval payload |

## 3. Tool Scale: langgraph-bigtool

- **Why:** qwen2.5-7B has ~32K context. 50+ tool schemas would eat it all.
- **How:** every tool's metadata (name, description, schema) is stored in LangGraph's long-term `store`. At each agent step, BigTool does **semantic search** to retrieve the 5–10 most relevant tools and injects only those into DON's context.
- **Fallback:** if retrieval is ambiguous, DON gets the top-scoring tools + a `search_tools()` meta-tool to find more by name/keyword.
- **Config:** tool registry seeded at startup; descriptions optimized for retrieval (tier-1 requirement for every tool).
- **⚠️ Maintenance:** `langgraph-bigtool` is functional but unmaintained (C6 §3) — designed behind a single module (`tools/registry.py` + BigTool store) so it can swap to a ChromaDB-`tools`-collection retriever (C10) with minimal change.

```
50+ tools registered in store
        │
   agent_loop asks: "retrieve tools for 'delete file report.docx'"
        │
        ▼
bigtool semantic search → [file_delete, shell_exec, ...] → injected into context
```

## 4. Capability Inventory (by category, with source)

### System & Files
| Tool | Source | Notes |
|---|---|---|
| `shell` (ShellTool) | langchain-community | Terminals; heavily sandboxed (Section 7) |
| `python_repl` (PythonREPLTool) | langchain-community / langchain-experimental | Python eval in jail |
| file management (read/write/list/move/search) | `FileManagementToolkit` | Root dir jailed to `~/jarvishome` |
| process/system monitoring | custom `@tool` | CPU/RAM/disk/battery via `psutil` |
| **desktop control — open ANY app, click, type, control** | **`opendesk` (MIT, GitHub)** | `app` open/close/focus + `ui` click-by-name + `mouse`/`keyboard` + `screenshot` (Set-of-Marks) + `ocr` + `clipboard` + `learn`/`schedule` + `audit`; native LangChain integration; driven remotely from A1 over encrypted paired WebSocket (C5a §1) |
| clipboard | opendesk `clipboard` | read/write (replaces wl-clipboard case) |
| screenshot / screen read | opendesk `screenshot` + vision eye | for vision dept (laptop client) |

### Web & Information
| Tool | Source | Notes |
|---|---|---|
| web search | `DuckDuckGoSearchRun` (langchain-community) | Free, keyless; **`searchts`** (capad-xyz/searchts, MIT) upgrade path with anti-bot escalation + multi-engine fusion if DDG rate-limits |
| web page extraction | **`crawl4ai`** (pip, Apache-2.0, 78k stars) | Best-in-class LLM-ready Markdown; replaces trafilatura |
| wikipedia | `WikipediaQueryRun` (langchain-community) | Free reference |
| weather | `OpenWeatherMapQueryRun` or custom (wttr.in) | wttr.in = keyless |
| news/podcasts | `feedparser` (pip) wrapped | RSS aggregation |
| arxiv/pubmed | langchain-community | Research |

### Communication
| Tool | Source | Notes |
|---|---|---|
| email read/send | `GmailToolkit` (langchain-community) | Needs Google OAuth client.json (later phase) |
| calendar | `GoogleCalendarToolkit` (langchain-community) | Same OAuth |
| messaging (Telegram) | custom `@tool` | Self-bot — free, reliable reach-back |
| push notifications | custom `@tool` | MQTT → Android notify |

### Coding & Data
| Tool | Source | Notes |
|---|---|---|
| GitHub (repo ops) | `GitHubToolkit` (langchain-community) | PAT scoped to user repos |
| SQL query | `SQLDatabaseToolkit` (langchain-community) | Read-only user by default |
| JSON tools | langchain-community | get value / list keys |
| code REPL | `PythonREPLTool` | sandboxed |

### Home & IoT
| Tool | Source | Notes |
|---|---|---|
| Home Assistant (88 tools) | `homeassistant-ai/ha-mcp` via MCP adapter | Search-discovery mode (built for local models); needs HA instance + token |
| MQTT publish/subscribe | `paho-mqtt` wrapped in `@tool` | Generic device control + Android bridge |

### Media & Entertainment
| Tool | Source | Notes |
|---|---|---|
| YouTube/downloads | `yt-dlp` (pip) wrapped | Keyless, handles 1000+ sites |
| Media server control | `jaredtrent/jellyfin-mcp` via MCP adapter | Search, playback control, playlists, subtitles |
| Podcasts/news | `feedparser` (pip) wrapped | RSS aggregation |
| music playback (local) | `python-mpd2` wrapped | MPD server on A1 playing local library |

### Memory & Personal (used by Components 9–12)
| Tool | Source | Notes |
|---|---|---|
| long-term memory write/search | custom `@tool` | wraps vector store (Chroma) |
| note capture | custom `@tool` | append to notes vault |
| task/todo list | custom `@tool` | simple SQLite todo table |

### Custom/Internal
| Tool | Source | Notes |
|---|---|---|
| device bridge (send to Android/laptop) | custom `@tool` | MQTT/WebSocket dispatch |
| TTS trigger | custom `@tool` | voice reply via Kokoro |
| approval payload (human ask) | custom `@tool` | for guard node / Agent Inbox |

## 5. Tool Registration & Registry

Every tool gets a uniform `ToolSpec`:

```python
class ToolSpec(BaseModel):
    name: str
    description: str          # retrieval-optimized (tier-1 priority)
    args_schema: type[BaseModel]  # per-tool Pydantic schema (Component 4)
    danger: Literal["read", "action", "destructive"]
    source: str               # "langchain-community" | "pip:<lib>" | "custom"
    enabled: bool
```

- `tools/registry.py` collects all specs → seeds the BigTool store at startup.
- `enabled: false` = tool registered but not exposed (feature gating).
- Enabled via config `config/tools.yaml` — no code edits.

## 6. Guard Integration (danger levels)

The guard (Component 1) uses `ToolSpec.danger` to shape approvals:

| Level | Examples | Approval UX |
|---|---|---|
| `read` | web search, wikipedia, file read, weather | Interrupt with short summary ("DON wants to search the web for X") |
| `action` | send email, write file, MQTT publish, TTS | Interrupt with full args preview |
| `destructive` | delete file, git reset --hard, shell with rm/sudo, DB write | Interrupt + red warning + explicit confirm phrase |

User chose **ask-before-everything**, so all three interrupt — the level just changes how alarming the prompt is.

## 7. Security Sandbox

- **ShellTool:** `DENY_LIST` (rm -rf /, mkfs, sudo, shutdown, mkdir /, curl|sh...), working-dir jail, 60 s timeout, max output 8 KB.
- **PythonREPL:** jailed directory, no network by default, timeout, output cap.
- **FileManagementToolkit:** root pinned to `~/jarvishome`; outside → denied.
- **Secrets:** API keys/OAuth in `config/.env`; never in prompts or tool descriptions.
- **DB tools:** read-only DB user, `SELECT` only.
- **GitHub PAT:** minimal scopes, single user.
- **Ollama side:** no `--api` exposure on public interface (Tailscale only).

## 8. File Layout

```
tools/
├── __init__.py
├── registry.py          # ToolSpec collection + BigTool store seeding
├── specs.py             # ToolSpec model
├── system/              # shell, python_repl, files, monitoring, clipboard, screenshot
├── web/                 # ddg_search, crawl4ai, wikipedia, weather, rss
├── comms/               # gmail, calendar, telegram, push_notify
├── coding/              # github, sql, json
├── home/                # home_assistant, mqtt
├── media/               # yt_dlp, mpd, media_bridge
├── memory/              # memory_write, notes, todo
└── internal/            # device_bridge, tts_trigger, approval
config/
└── tools.yaml           # enable/disable, danger overrides, sandbox params
```

## 9. Install Plan (ARM-compatible, all pip)

```
pip install langchain langchain-community langgraph langgraph-bigtool
pip install langchain-mcp-adapters mcp
pip install pydantic pydantic-settings pyyaml
pip install duckduckgo-search crawl4ai wikipedia-api feedparser
pip install yt-dlp python-mpd2 paho-mqtt icalendar
pip install psutil wl-clipboard          # (wl-clipboard is apt, for laptop)
pip install opendesk[core,mcp,remote]    # desktop control (C5a §1) — runs on laptop, driven from A1
pip install docling markitdown           # document ingestion (Component 7, MIT, arm64)
pip install chromadb                    # vector store (Component 10, v1.x Rust core)
pip install pygithub sqlalchemy
# voice (Component 15): kokoro-onnx + whisper.cpp (binary) + heed-wakeword
# MCP servers (pip or git): ha-mcp, jellyfin-mcp (docker/arm64)
```

OAuth-dependent tools (gmail/calendar) install a `google-api-python-client` extra and stay `enabled: false` until credentials are set.

## 10. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Don't reinvent | `langchain-community` + MCP servers + pip libs, thin wrappers only | Battle-tested, maintained |
| Scale | `langgraph-bigtool` semantic retrieval | 50+ tools can't fit 7B context |
| Web search | DuckDuckGo | Free, keyless, headless |
| Web extraction | crawl4ai (78k stars) | Best-in-class LLM-ready output |
| Media | yt-dlp + jellyfin-mcp + MPD + feedparser | Keyless, free-tier friendly |
| Home | ha-mcp (MCP, search-discovery mode) | Built for small/local models |
| Desktop control | opendesk (MIT) — `app`/`ui`/`mouse`/`keyboard`/`ocr`/`learn` | User-required "open & control any app"; LangChain-native, 7B-friendly click-by-name |
| TTS | Kokoro primary, Piper fallback | Better voice, same CPU cost (C15) |
| Danger levels | read / action / destructive | Guard shapes approval UX |
| Sandboxing | jail dirs, deny-list, read-only DB | Personal data stays protected |
| Config-gated | `config/tools.yaml` | Enable tools without code |

> Detailed per-department GitHub picks: [`component-5a-tools-inventory.md`](./component-5a-tools-inventory.md)
