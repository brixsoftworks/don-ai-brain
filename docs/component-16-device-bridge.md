# Component 16: Device Bridge — Android + Laptop ↔ the A1 Brain

## 1. Overview

The final transport layer: how clients talk to the brain. **WebSocket** for bidirectional streaming (voice + events), **REST** for short ops, **MQTT** for events/IoT. Everything rides **Tailscale** — no public ports, devices authenticated by the mesh.

```
ANDROID / LAPTOP                     CLOUD A1 (tailscale IP only)
  ├─ WebSocket ── audio in/out ──────► FastAPI hub (server/)
  ├─ WebSocket ── events/status ─────► /ws sessions
  ├─ REST ─────── messages/approvals ► /api/v1
  └─ MQTT ─────── device events ─────► MQTT broker
                              │
        scheduler/alerter ────┘  (proactive DON feeds the bridge)
```

## 2. Transport Roles

| Transport | Use | Why |
|---|---|---|
| WebSocket (`/ws`) | streaming audio, live transcript, status events, wake triggers | bidirectional, low-latency |
| REST (`/api/v1`) | send message, list conversations, device status, approval answers | simple request/response |
| MQTT | IoT events, presence heartbeats, push fallback | pub/sub decoupling |

**Message envelope (all transports):**
```json
{
  "type": "text" | "audio_in" | "audio_out" | "status" | "approval" | "event" | "ping",
  "device_id": "android-01",
  "thread_id": "…",
  "payload": {}
}
```

## 3. Device Registry & Presence

- `devices` SQLite table: `device_id`, `type` (android|laptop), `capabilities` (mic, speaker, camera, screen), `push_channel`, `last_seen`, `online`.
- **Heartbeat** every 30 s over WS; presence drives routing (below).
- Registration is automatic on first connect (device introduces itself).

## 4. Cross-Device Conversation Sync

- Same `thread_id` everywhere (C1 §6) → **device switch = seamless resume**.
- **Thread ownership:** the last device to wake/hold a thread becomes its active listener; a wake on another device re-targets the conversation (latest state loaded from the checkpointer).
- Proactive notifications route to the **best device**: online + last-active first; push fallback when offline.

## 5. Approvals Across Devices

- Guard interrupt (C1 §8) → device bridge pushes an **approval card** to the active device (WS) or push notification (offline).
- Answer (`approve`/`reject`) comes back over WS or REST → resumes the exact checkpoint (C13 §5).
- Offline timeouts as specced in C13 §5 (24h auto-drop, logged).

## 6. Push Notifications

- **Online path:** WS event → client shows notification natively.
- **Offline path:** MQTT→ push. Android: `ntfy` (self-hostable) or FCM. Laptop: `notify-send`/ntfy.
- Notifications carry actions: reply, approve, dismiss (native action buttons where supported).

## 7. Proactive DON (scheduler/alerter)

- `APScheduler` (pin `apscheduler<4`, 4.x still alpha; use `AsyncIOScheduler`) runs cron jobs defined in `config/schedule.yaml` (daily briefings, reminders, recurring tasks).
- Each fired job enters the main graph at `classify_input` with `source=scheduler` (C13 §4) — same guard rules apply.
- Alerter: threshold events (e.g. storage low, task failed) → device bridge event → notification + optional overlay appearance.

## 8. Security (Tailscale-only)

- A1 binds the hub to the **Tailscale interface only** (`0.0.0.0` never).
- Device auth: Tailscale mesh identity + per-device token in the envelope (`X-Device-Token` for REST, first-frame for WS).
- MQTT with credentials; broker bound to tailscale IP.
- TLS via Tailscale's automatic certs where feasible; wireguard already encrypts the mesh.

## 9. File Layout (Component 16)

```
server/
├── app.py                 # FastAPI app: /ws, /api/v1, /ui mount
├── ws.py                  # WebSocket session manager (device ↔ thread)
├── api.py                 # REST routes
├── devices.py             # device registry + presence
├── push.py                # ntfy/FCM/notify-send adapters
├── scheduler.py           # APScheduler jobs → graph entry
└── alerter.py             # threshold events → bridge
bridge/
├── mqtt_bridge.py         # MQTT pub/sub → graph events
└── envelope.py            # message envelope (de)serialization
config/
├── schedule.yaml          # proactive jobs
└── bridge.yaml            # ports, heartbeat, push channels
```

## 10. Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Primary transport | WebSocket | Streaming audio + events, low latency |
| IoT/events | MQTT | Decoupled, standard |
| Security | Tailscale-only bind, device tokens | No public surface |
| Conversation sync | shared thread_id + ownership | Seamless switch |
| Approvals | WS card / push fallback | Works online + offline |
| Proactive | APScheduler into same graph | Same guard rules |
| Presence | 30s heartbeat | Routes notifications smartly |
