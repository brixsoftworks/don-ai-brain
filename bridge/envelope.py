"""bridge/envelope.py — message envelope (de)serialization.

Every transport (WS, REST, MQTT) speaks the same envelope
(docs/component-16 §2).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Envelope:
    type: str                                   # text|audio_in|audio_out|status|approval|event|ping
    device_id: str = ""
    thread_id: str = "default"
    payload: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: str) -> "Envelope":
        data = json.loads(raw)
        return cls(
            type=data.get("type", "text"),
            device_id=data.get("device_id", ""),
            thread_id=data.get("thread_id", "default"),
            payload=data.get("payload", {}),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


def text_envelope(device_id: str, thread_id: str, content: str) -> Envelope:
    return Envelope(type="text", device_id=device_id, thread_id=thread_id,
                    payload={"content": content})


def status_envelope(thread_id: str, status: str, detail: str = "") -> Envelope:
    return Envelope(type="status", thread_id=thread_id,
                    payload={"status": status, "detail": detail})


def approval_envelope(thread_id: str, actions: list[dict]) -> Envelope:
    return Envelope(type="approval", thread_id=thread_id, payload={"actions": actions})
