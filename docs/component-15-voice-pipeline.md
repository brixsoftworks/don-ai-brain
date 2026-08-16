# Component 15: Voice Pipeline — The JARVIS Talking Experience

## 1. Overview

Voice is just another input/output channel into the same graph — DON speaks with a **villainous calm** (Kokoro TTS), hears with **whisper.cpp**, wakes on a custom **"Hey DON"** wake word (Heed), and supports barge-in. Architecture reference studied: `InterGenJLU/jarvis` (streaming sentence pipeline) and `Sycatle/local-jarvis` (wake/STT/TTS as swappable layers).

```
 mic ─► wake word (Heed) ─► VAD ─► streaming STT (whisper.cpp)
                                             │ transcript
                                             ▼
                                   ┌───────────────┐
                                   │  the main graph  │  (same as text input)
                                   └───────┬───────┘
                                           │ reply text
                                           ▼
                              sentence splitter → Kokoro TTS → speaker
                                           ▲
                              barge-in (VAD) cancels remaining speech
```

## 2. Stack (locked in C5a §3, upgraded Aug 2026)

| Piece | Tool | Notes |
|---|---|---|
| Wake word | **`AndreiBulzan/heed-wakeword`** (Apache-2.0) | **Custom "Hey DON" trained in seconds** (web UI/CLI); tiny 108 KB model, 1–15 ms inference, ONNX everywhere. Replaces openWakeWord (its training pipeline is broken on modern Python). Backup: `livekit/livekit-wakeword` (conv-attention, 100× fewer false positives) |
| VAD | Silero VAD v6.2 (MIT) | ~2 MB, <1 ms/chunk, 6000+ languages, barge-in detection — still the standard |
| STT | **`ggml-org/whisper.cpp` `small`** (MIT) | **Best ARM CPU** (handwritten NEON SIMD, single C++ binary, ~460 MB). Replaces faster-whisper (CTranslate2 wheels are unreliable on aarch64 and slower on CPU). Upgrade path: **Moonshine v2** (200M, MIT, native streaming) if latency needs improving |
| TTS | **Kokoro-82M** via **`thewh1teagle/kokoro-onnx`** (MIT) | 82M params, Apache-2.0, ~300 MB, natural voice; `create_stream()` gives sentence-level streaming; deep male voices (`am_eric`/`am_onyx`/`am_adam`) at speed 0.85–0.90 = DON's low calm villain timbre. Piper (GPL fork) = fast fallback |
| Streaming | sentence-by-sentence | first audio before full reply generated |
| All-in-one alt | **`k2-fsa/sherpa-onnx`** (Apache-2.0, aarch64 builds) | Bundles VAD+STT+TTS(+Kokoro)+KWS in one binary — keep as a fallback harness if per-component glue ever hurts |

**Memory budget (all resident):** Kokoro ~300 MB + whisper.cpp small ~500 MB + Silero ~5 MB + Heed <1 MB ≈ **~0.9 GB total** — fits the C2 budget comfortably.

## 3. Where Voice Runs

```
ANDROID / LAPTOP (client)          CLOUD A1 (brain)
  wake word (Heed) + VAD           STT: whisper.cpp (small, resident)
  mic capture ───────────────────► TTS: Kokoro (kokoro-onnx, resident)
  audio streaming (WebSocket)      sentence splitter
  speaker playback ◄────────────── audio chunks streamed back
```

- **Wake word runs on the client** (Heed, near-zero latency, phone can trigger even when screen off). Voice data streams to the A1 for STT — model stays resident there (fits the ~0.9 GB voice budget above).
- Optional fully-offline edge STT/TTS later; not needed now.

## 4. STT Flow

1. Wake (Heed) → VAD confirms speech start → stream audio frames (16 kHz PCM) over the device bridge.
2. A1 runs `whisper.cpp` streaming/segmented transcription (single binary, `-t 4` threads).
3. Transcript pushed into the graph as a normal message (`source=voice`).
4. VAD silence > 600 ms = end of utterance → finalize transcription, run graph.

**Latency budget (ARM):** wake ≈ instant (Heed <15 ms), STT ≈ 0.3–0.5 s, graph ≈ model-dependent, first TTS audio ≈ 0.5–1.5 s after reply start. Target end-to-end ≈ 3–6 s on A1 — the "feels live" threshold.

## 5. TTS Flow (streaming, DON's voice)

1. Reply text arrives from responder.
2. **Sentence splitter** (regex + punctuation, respects code/URL blocks) yields sentences.
3. Each sentence → Kokoro → audio chunk; chunks sent to client as they finish (streamed).
4. Client queues + plays gapless (single persistent player on device).
5. **Barge-in:** Silero VAD on the client detects user speech → sends cancel → A1 aborts remaining generation → next wake re-arms.

## 6. Voice Tools Inside the Graph

| Tool | Danger | Purpose |
|---|---|---|
| `tts_speak(text, stream=True)` | action | explicit "say this out loud" (also used for proactive alerts) |
| `voice_record(duration)` | action | capture a voice note → transcribe → store |
| `voice_state(mute/unmute)` | action | toggle voice responses on a device |

The responder calls `tts_speak` automatically when the originating input was voice (context from state) — DON answers audibly by default.

## 7. Voice Identity & Persona

- Kokoro (via kokoro-onnx) supports **voice blending** — a low, calm, measured timbre (`am_eric`/`am_onyx` base, speed 0.85–0.90) tuned for DON's villain persona (config in `voice/voice.yaml`).
- Speaking rules in the C3 prompt: short sentences, deliberate pacing, dry wit — readable aloud, not walls of text.

## 8. File Layout (Component 15)

```
voice/
├── wake.py              # Heed wake-word engine (custom "Hey DON" ONNX)
├── vad.py               # Silero VAD v6.2 wrapper (start/end/barge-in)
├── stt.py               # whisper.cpp transcription (streaming, small model)
├── tts.py               # Kokoro synthesis via kokoro-onnx + Piper fallback
├── stream.py            # sentence splitter + chunk queue + cancel
└── bridge.py            # device bridge integration (audio in/out)
config/
└── voice.yaml           # wake model, whisper size, voice blend, latencies
tests/
└── bench_voice.py       # STT accuracy sample, TTS latency, barge-in
```

## 9. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Wake word | Heed, custom "Hey DON", on-device | Apache-2.0, trains in seconds, 108 KB, <15 ms (openWakeWord training broken on py3.12+) |
| STT | whisper.cpp `small` on A1 | Best ARM CPU perf (NEON SIMD), single binary; Moonshine v2 upgrade path |
| TTS | Kokoro-82M (kokoro-onnx) primary, Piper fallback | Natural voice, CPU-cheap, sentence streaming (C5a) |
| Streaming | sentence-by-sentence | "Live" feel on slow ARM LLM |
| Barge-in | Silero VAD on client → cancel | Natural interruption |
| Voice = channel | same graph, `source=voice` | No separate voice agent |
| Responder | auto `tts_speak` when input was voice | Speaks by default, no command needed |
