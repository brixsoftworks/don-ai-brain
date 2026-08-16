"""server/api.py — REST routes for the device bridge (docs/component-16 §9)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from bridge.envelope import Envelope, status_envelope
from server.devices import DeviceInfo
from server.ws import SessionManager


class MessageIn(BaseModel):
    device_id: str = "unknown"
    thread_id: str = "default"
    content: str


class ApprovalIn(BaseModel):
    thread_id: str
    decision: bool


def build_router(bridge, sessions: SessionManager, devices):
    router = APIRouter(prefix="/api/v1")

    @router.post("/messages")
    async def send_message(m: MessageIn):
        sessions.claim_thread(m.thread_id, m.device_id)
        devices.register(DeviceInfo(device_id=m.device_id, type=m.device_id.split("-")[0]))
        await sessions.async_send(m.device_id, status_envelope(m.thread_id, "listening").to_json())
        result = await run_in_threadpool(bridge.send_text, m.device_id, m.thread_id, m.content)
        if result.get("reply"):
            await sessions.async_send(m.device_id, Envelope(
                type="text", device_id=m.device_id, thread_id=m.thread_id,
                payload={"content": result["reply"], "final": True}).to_json())
        return result

    @router.post("/approval")
    async def approval(a: ApprovalIn):
        return await run_in_threadpool(bridge.answer_approval, a.thread_id, a.decision)

    @router.get("/devices")
    async def list_devices():
        return {"devices": devices.list_devices()}

    @router.get("/health")
    async def health():
        return {"status": "ok"}

    return router
