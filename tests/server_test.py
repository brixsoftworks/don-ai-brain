"""End-to-end server test: REST messages, approval bridge, WS, UI mount."""
import sys

sys.path.insert(0, "/home/mullainathan/Documents/Coding/Projects/pa ai agent")

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from server.app import create_app
from server.devices import DeviceRegistry
from tests._helpers import temp_graph


def make_app(tmp: Path):
    graph, cleanup = temp_graph()
    devices = DeviceRegistry(tmp / "devices.db")
    app = create_app(graph, devices=devices)
    return app, cleanup


def test_server_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        app, cleanup = make_app(Path(d))
        try:
            client = TestClient(app)
            assert client.get("/api/v1/health").json() == {"status": "ok"}
            assert "DON" in client.get("/").text
            assert client.get("/ui/app.js").status_code == 200

            r = client.post("/api/v1/messages",
                            json={"device_id": "testdev", "thread_id": "t1", "content": "Hi DON, one short line."})
            body = r.json()
            assert body["status"] == "done", body
            assert body["reply"]

            devs = client.get("/api/v1/devices").json()["devices"]
            assert any(d["device_id"] == "testdev" for d in devs)
        finally:
            cleanup()


def test_approval_bridge():
    with tempfile.TemporaryDirectory() as d:
        app, cleanup = make_app(Path(d))
        try:
            client = TestClient(app)
            r = client.post("/api/v1/messages",
                            json={"device_id": "testdev", "thread_id": "t2",
                                  "content": "You MUST call the sys_stats tool to check CPU usage, then report it."})
            body = r.json()
            if body["status"] == "awaiting_approval":
                assert body["actions"]
                for _ in range(15):
                    r = client.post("/api/v1/approval", json={"thread_id": "t2", "decision": True})
                    if r.json()["status"] == "done":
                        break
                assert r.json()["status"] == "done", r.json()
            assert body["status"] in ("done", "awaiting_approval")
        finally:
            cleanup()


def test_ws_text():
    with tempfile.TemporaryDirectory() as d:
        app, cleanup = make_app(Path(d))
        try:
            client = TestClient(app)
            import json
            with client.websocket_connect("/ws?device_id=wsdev&type=laptop") as ws:
                ws.send_json({"type": "text", "device_id": "wsdev", "thread_id": "t3",
                              "payload": {"content": "Hi, one short line."}})
                saw_reply = False
                for _ in range(10):
                    msg = json.loads(ws.receive_text())
                    if msg["type"] == "text" and msg["payload"].get("final"):
                        saw_reply = True
                        break
                assert saw_reply
        finally:
            cleanup()


if __name__ == "__main__":
    ok = True
    for fn in (test_server_roundtrip, test_approval_bridge, test_ws_text):
        try:
            fn()
            print(f"{fn.__name__}: PASS")
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            print(f"{fn.__name__}: FAIL ({exc})")
            ok = False
    sys.exit(0 if ok else 1)
