# DON — Personal AI Assistant

Fully-local, JARVIS-style personal AI assistant ("Don"): voice-first,
multi-device, approval-gated. LangGraph + Ollama brain, FastAPI hub,
WebSocket/REST/MQTT device bridge, Flutter Android client.

> **Status: personal single-user system under active development.**
> This is one person's assistant, intentionally bespoke. See
> [Known limitations](#known-limitations) before trying to reuse it.

## What's inside

| Area | Tech |
|---|---|
| Brain | Python 3.11+, LangGraph/LangChain, Ollama (local LLMs), OpenRouter fallback |
| Hub | FastAPI (REST + WebSocket), SQLite, ChromaDB RAG, MCP tool loading |
| Transport | Tailscale mesh between devices; MQTT bridge for IoT; WS to mobile |
| Voice | whisper.cpp STT · Kokoro TTS · VAD · wake word (Vosk) |
| Mobile | Flutter Android app (`client/`, release APK via GitHub Actions) |
| Deploy | Dockerfile · cloud-init (Oracle A1) · `render.yaml` |

Component specs live in `docs/` (18 documents); runtime config is layered
YAML under `config/`.

## Known limitations

- **Single-user by design.** Persona, name and contact details are embedded
  in prompts/config. Generalizing into a product would require an identity
  layer that does not exist yet.
- **Social-media automation tools are ToS-violating.** The Instagram /
  WhatsApp CDP automation in `tools/` operates against those platforms'
  Terms of Service using browser automation. It exists for personal
  experimentation only — **do not build on, extend, or productionize these
  specific tools**, and do not ship them to anyone else.
- Repo hygiene: some scratch scripts and binaries at the root predate the
  current layout.
- Very young project: expect breaking changes across `core/`, `client/`,
  and `config/`.

## Setup

```bash
pip install -e ".[dev]"        # or: pip install -r requirements.txt (if present)
cp .env.example .env.local     # GEMINI_API_KEY / OPENROUTER_API_KEY (server-only)
python -m don                  # entrypoint per pyproject.toml
```

Secrets are read from environment variables only — never hardcode keys
(see `SECURITY_ACTION.md` for the rotation history).

## Security notes

- Approval gates: dangerous actions require explicit human confirmation.
- Tailscale-only exposure; no public ports by default.
- `.env*` files are gitignored; placeholders live in `.env.example`.
