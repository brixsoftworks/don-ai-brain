"""server/app.py — FastAPI hub: /ws, /api/v1, /ui mount.

Binds to the Tailscale interface only (config/bridge.yaml). Every live
envelope rides the WebSocket; short ops go over REST.
See docs/component-16.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bridge.envelope import Envelope, status_envelope
from server.api import build_router
from server.bridge import Bridge
from server.devices import DeviceInfo, DeviceRegistry
from server.ws import SessionManager

log = logging.getLogger("don.server")

UI_DIR = Path(__file__).resolve().parent.parent / "ui"


def create_app(graph=None, devices: DeviceRegistry | None = None):
    sessions = SessionManager()
    devices = devices or DeviceRegistry()
    bridge = Bridge(graph, sessions)

    app = FastAPI(title="DON bridge")
    app.state.sessions = sessions
    app.state.devices = devices
    app.state.bridge = bridge

    # ------------------------------------------------------------------ WS

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        device_id = ws.query_params.get("device_id", "unknown")
        sessions.connect(device_id, ws)
        devices.register(DeviceInfo(device_id=device_id, type=ws.query_params.get("type", "laptop")))
        try:
            while True:
                raw = await ws.receive_text()
                env = Envelope.from_json(raw)
                if env.type == "pong":
                    await ws.send_text(Envelope(type="pong", device_id=device_id,
                                                thread_id=env.thread_id).to_json())
                elif env.type == "text":
                    sessions.claim_thread(env.thread_id, device_id)
                    await sessions.async_send(device_id, status_envelope(env.thread_id, "listening").to_json())
                    result = await run_bridge(bridge.send_text, device_id, env.thread_id, env.payload.get("content", ""))
                    if result.get("reply"):
                        await sessions.async_send(device_id, Envelope(
                            type="text", device_id=device_id, thread_id=env.thread_id,
                            payload={"content": result["reply"], "final": True}).to_json())
        except WebSocketDisconnect:
            sessions.disconnect(device_id)
            devices.set_offline(device_id)
        except Exception as exc:  # noqa: BLE001
            log.error("ws error: %s", exc)
            sessions.disconnect(device_id)
            devices.set_offline(device_id)

    # ----------------------------------------------------------------- REST

    app.include_router(build_router(bridge, sessions, devices))

    # ------------------------------------------------------------------ UI

    @app.get("/")
    async def root():
        return FileResponse(UI_DIR / "index.html")

    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

    return app


async def run_bridge(fn, *args):
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(fn, *args)
