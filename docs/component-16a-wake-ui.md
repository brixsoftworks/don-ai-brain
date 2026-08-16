# Component 16a: Wake UI — DON Appears on the Screen

## 1. Overview

When DON wakes, a **full-screen overlay UI** appears across the device screen — the JARVIS hologram moment. It shows live audio, transcript, status, and DON's emblem, then fades when the conversation ends. **One UI codebase** served by the A1; laptop and Android just render it.

```
wake word / hotkey / tap
        │
        ▼
device opens overlay → connects to A1 /ws (thread) 
        │
        ├── mic → audio_in stream
        ├── status events (listening/thinking/speaking/…)
        ├── live transcript (user + DON, streaming)
        └── audio_out stream → waveform viz
        │
        ▼
idle 30s → overlay fades → device returns to normal UI
```

## 2. Overlay Layout (what's on screen)

```
┌───────────────────────────────────────────────────────┐
│                                                       │
│                 ◇  DON EMBLEM (glow, idle/active)     │
│                                                       │
│      ──●─────●──●────●──●────   live audio waveform   │
│                                                       │
│   user: "what's the weather?"                         │
│   DON:  "Rain, operator. I'd pack an umbrella…"       │
│                         (streaming transcript)        │
│                                                       │
│   [ listening ] [ thinking ] [ speaking ] [ ⛔tool ]   │
│                         status chip + model indicator │
└───────────────────────────────────────────────────────┘
```

| Element | Content | Live updates |
|---|---|---|
| Emblem | DON glyph (C3 persona color: deep red/black) | glow pulses when speaking |
| Waveform | mic + TTS audio levels | real-time (Web Audio) |
| Transcript | user turns + DON turns | token/streamed text |
| Status chip | listening / thinking / speaking / tool | from WS status events |
| Tool line | "DON is checking the weather…" | from tool events (C13 §6) |
| Model chip | router/main/coder/vision | debug hint, toggleable |

## 3. States & Appearance

| State | Overlay behavior |
|---|---|
| `idle` | hidden (normal screen) |
| `listening` | fade-in, waveform on mic, emblem dim |
| `thinking` | emblem glow, "…" animation, waveform off |
| `speaking` | waveform on TTS, transcript streaming, emblem pulses |
| `awaiting-approval` | approval card slides in (C16 §5) |
| `ending` | fade-out, return to prior app |

Transitions are CSS animations (no JS animation loop churn — cheap on any device).

## 4. Tech Choice (single codebase)

```
A1 serves:  /ui  (static HTML/CSS/JS, no framework)
                │
   laptop ── fullscreen browser window (or tiny Electron shell)
   android ── PWA in fullscreen / WebView overlay activity
```

- **Why web:** one UI, styled with CSS, updated without app re-deploys; both clients just open a URL over Tailscale.
- WebSocket to `/ws` for all live data; `navigator.mediaDevices` for mic capture (permission prompt once).
- Laptop trigger: hotkey (e.g. Super+Space) + wake word launches the window. Android trigger: wake word + PWA fullscreen.
- **No Electron dependency required** — the OS browser window in fullscreen mode is sufficient (Electron optional later for true click-through/transparency).

## 5. Accessibility & Constraints

- Dark theme (DON persona), minimal motion-averse fallback (`prefers-reduced-motion`).
- Text ≥ 16 px; keyboard dismissible (Esc ends session).
- Overlay never steals focus unless listening; a session survives accidental Esc (re-opens via hotkey).
- Battery-friendly: static canvas, no animations when idle; mic only open while listening.

## 6. File Layout (Component 16a)

```
ui/
├── index.html             # overlay page
├── style.css              # personas, states, transitions
├── app.js                 # WS client, mic/audio, transcript, state machine
├── emblem.svg             # DON emblem
└── launch/
    ├── laptop.sh          # opens fullscreen browser / electron shell
    └── android/           # PWA manifest + service worker (wake trigger)
```

`server/app.py` mounts `/ui` as static files (C16 §9) — one endpoint serves every device.

## 7. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| UI tech | single web overlay (/ui) | One codebase, both devices, no re-deploys |
| Laptop render | fullscreen browser window | No Electron needed initially |
| Android render | PWA / WebView fullscreen | Wake-word launchable |
| Live data | WebSocket status + transcript + audio | Same hub as C16 |
| Styling | CSS-only animations | Cheap on all devices |
| End of session | 30s idle → fade | Returns screen to normal |
