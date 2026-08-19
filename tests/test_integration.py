"""tests/test_integration.py — integration tests for DON.

Covers:
1. Tool registry: every tool module exports TOOLS list
2. Graph compiles with real VectorStore + SQLite checkpointer
3. Graph invocation with mock OllamaClient returns a reply
4. Server create_app boots and health endpoint responds
5. WebSocket ping/pong handshake

Run with:
    python3 tests/test_integration.py -v
or:
    python3 -m pytest tests/test_integration.py -v
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DON_MODELS_YAML", str(PROJECT_ROOT / "config/models.override.yaml"))

from langchain_core.messages import HumanMessage


class TestToolsExports(unittest.TestCase):
    """Every tool module in the registry must export a TOOLS list."""

    TOOL_MODULES = [
        "tools.system.tools",
        "tools.web.tools",
        "tools.internal.tools",
    ]

    def test_tools_list_exported(self):
        for mod_name in self.TOOL_MODULES:
            with self.subTest(module=mod_name):
                mod = importlib.import_module(mod_name)
                self.assertTrue(
                    hasattr(mod, "TOOLS"),
                    f"{mod_name} must export a TOOLS list",
                )
                self.assertIsInstance(mod.TOOLS, list)
                self.assertGreater(len(mod.TOOLS), 0, f"{mod_name}.TOOLS is empty")

    def test_screen_tools_exported(self):
        mod = importlib.import_module("tools.screen.tools")
        self.assertTrue(hasattr(mod, "TOOLS"))
        self.assertIsInstance(mod.TOOLS, list)

    def test_registry_loads_all_tools(self):
        from tools.registry import ToolRegistry
        registry = ToolRegistry()
        # At least 40 tools should be registered
        self.assertGreater(len(registry.names()), 40)

    def test_registry_enabled_tools(self):
        from tools.registry import ToolRegistry
        registry = ToolRegistry()
        enabled = registry.enabled_names()
        # Core tools must always be enabled
        for t in ["sys_stats", "shell", "file_read", "file_write", "web_search", "weather"]:
            self.assertIn(t, enabled, f"{t} should be enabled by default")


class TestGraphCompile(unittest.TestCase):
    """Graph must compile with real storage components."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="don-int-"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_graph_compiles(self):
        from core.graph import build_graph
        from core.checkpointer import ChatLog, open_checkpointer
        from memory.vectorstore import VectorStore

        graph = build_graph(
            vectorstore=VectorStore(path=self.tmp / "vdb"),
            chatlog=ChatLog(self.tmp / "chat.db"),
            checkpointer=open_checkpointer(self.tmp / "cp.db"),
        )
        self.assertIsNotNone(graph)

    def test_graph_invoke_with_mock_ollama(self):
        """Run the full graph with a mocked Ollama so no LLM is needed."""
        from core.graph import build_graph
        from core.checkpointer import ChatLog, open_checkpointer
        from memory.vectorstore import VectorStore

        graph = build_graph(
            vectorstore=VectorStore(path=self.tmp / "vdb2"),
            chatlog=ChatLog(self.tmp / "chat2.db"),
            checkpointer=open_checkpointer(self.tmp / "cp2.db"),
        )

        # Patch OllamaClient.invoke to return a canned response
        mock_resp_router = {"content": '{"task_type": "quick_query", "confidence": 0.95}', "tool_calls": []}
        mock_resp_agent  = {"content": "2 + 2 = 4", "tool_calls": [], "prompt_eval_count": 10, "eval_count": 5}

        call_count = {"n": 0}

        def fake_invoke(self_inner, model_key, messages, **kwargs):
            call_count["n"] += 1
            # First call is the router classifier, subsequent are the agent
            if call_count["n"] <= 1:
                return mock_resp_router
            return mock_resp_agent

        with patch("models.ollama_client.OllamaClient.invoke", fake_invoke):
            config = {"configurable": {"thread_id": "int-test-001"}}
            result = graph.invoke(
                {
                    "messages": [HumanMessage(content="What is 2 + 2?")],
                    "user_id": "test",
                    "device": "laptop",
                    "iterations": 0,
                    "tokens_used": 0,
                },
                config,
            )
        self.assertIn("reply", result)
        self.assertIsInstance(result["reply"], str)
        self.assertGreater(len(result["reply"]), 0)


class TestServerApp(unittest.TestCase):
    """Server create_app must boot; REST endpoints must respond."""

    def test_create_app_boots(self):
        from server.app import create_app
        app = create_app(graph=None)
        self.assertIsNotNone(app)

    def test_health_endpoint(self):
        from fastapi.testclient import TestClient
        from server.app import create_app
        app = create_app(graph=None)
        client = TestClient(app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")

    def test_devices_endpoint(self):
        from fastapi.testclient import TestClient
        from server.app import create_app
        app = create_app(graph=None)
        client = TestClient(app)
        resp = client.get("/api/v1/devices")
        self.assertEqual(resp.status_code, 200)

    def test_ws_ping_pong(self):
        from fastapi.testclient import TestClient
        from server.app import create_app
        app = create_app(graph=None)
        client = TestClient(app)
        with client.websocket_connect("/ws?device_id=test-dev&type=laptop") as ws:
            ws.send_text(json.dumps({
                "type": "ping",
                "device_id": "test-dev",
                "thread_id": "t1",
                "payload": {},
            }))
            data = json.loads(ws.receive_text())
            self.assertEqual(data["type"], "pong")


class TestBridgeEnvelope(unittest.TestCase):
    """Envelope serialisation round-trips."""

    def test_envelope_roundtrip(self):
        from bridge.envelope import Envelope
        env = Envelope(type="text", device_id="dev-1", thread_id="t1", payload={"content": "hello"})
        dumped = env.to_json()
        loaded = Envelope.from_json(dumped)
        self.assertEqual(loaded.type, "text")
        self.assertEqual(loaded.payload["content"], "hello")

    def test_status_envelope(self):
        from bridge.envelope import status_envelope
        env = status_envelope("t1", "thinking")
        self.assertEqual(env.type, "status")

    def test_approval_envelope(self):
        from bridge.envelope import approval_envelope
        env = approval_envelope("t1", [{"tool": "shell", "danger": "destructive"}])
        self.assertEqual(env.type, "approval")
        self.assertIn("actions", env.payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
