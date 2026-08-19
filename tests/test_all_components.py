#!/usr/bin/env python3
"""tests/test_all_components.py — comprehensive test of all new modules.

Tests every component built in this session against the docs specs.
Runs without Ollama (mocked) or external services.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def ok(label, detail=""):
    global PASS
    PASS += 1
    print(f"  \033[32m✓\033[0m {label}" + (f" — {detail}" if detail else ""))


def fail(label, detail=""):
    global FAIL
    FAIL += 1
    print(f"  \033[31m✗\033[0m {label}" + (f" — {detail}" if detail else ""))


def section(title):
    print(f"\n{'='*60}\n {title}\n{'='*60}")


# ─── C4: Output Parsers ───────────────────────────────────────────
section("C4: Output Parsers")

from core.parsing.schemas import TaskClassification, ParsedToolCall, MemoryFact
from core.parsing.router_parser import parse_task_classification
from core.parsing.tool_call_parser import parse_ollama_tool_calls, parse_tool_call_json
from core.parsing.tool_args import validate_tool_args
from core.parsing.memory_parser import parse_memory_facts
from core.parsing.retry import parse_with_retry, _repair_json

# schemas
try:
    tc = TaskClassification(task_type="coding", confidence=0.95)
    assert tc.task_type == "coding"
    ok("TaskClassification schema")
except Exception as e:
    fail("TaskClassification schema", str(e))

try:
    tc = TaskClassification(task_type="invalid_type", confidence=0.5)
    fail("TaskClassification rejects invalid type (should have raised)")
except Exception:
    ok("TaskClassification rejects invalid type")

try:
    m = MemoryFact(subject="user", predicate="likes_tea", object_value="tea",
                   category="preference", confidence=0.9)
    assert m.confidence == 0.9
    ok("MemoryFact schema")
except Exception as e:
    fail("MemoryFact schema", str(e))

# router parser
try:
    r = parse_task_classification('{"task_type": "coding", "confidence": 0.9}')
    assert r.task_type == "coding"
    ok("router parser: strict JSON")
except Exception as e:
    fail("router parser: strict JSON", str(e))

try:
    r = parse_task_classification('Here is the result: {"task_type": "system", "confidence": 0.8} done')
    assert r.task_type == "system"
    ok("router parser: lenient JSON in prose")
except Exception as e:
    fail("router parser: lenient JSON in prose", str(e))

try:
    r = parse_task_classification("totally not json at all")
    assert r.task_type == "unknown"
    ok("router parser: fallback to unknown")
except Exception as e:
    fail("router parser: fallback to unknown", str(e))

# tool call parser
try:
    calls = [{"function": {"name": "shell", "arguments": {"command": "ls"}}}]
    parsed = parse_ollama_tool_calls(calls)
    assert len(parsed) == 1
    assert parsed[0].tool == "shell"
    ok("tool call parser: native Ollama calls")
except Exception as e:
    fail("tool call parser: native Ollama calls", str(e))

try:
    parsed = parse_tool_call_json('{"tool": "web_search", "args": {"query": "test"}}')
    assert len(parsed) == 1
    assert parsed[0].tool == "web_search"
    ok("tool call parser: JSON fallback")
except Exception as e:
    fail("tool call parser: JSON fallback", str(e))

# tool args validation
try:
    from pydantic import BaseModel
    class TestSchema(BaseModel):
        command: str
        timeout: int = 10
    args, err = validate_tool_args("shell", {"command": "ls"}, TestSchema)
    assert err is None
    assert args["command"] == "ls"
    ok("tool args: valid args")
except Exception as e:
    fail("tool args: valid args", str(e))

try:
    from pydantic import BaseModel
    class TestSchema2(BaseModel):
        command: str
    args, err = validate_tool_args("shell", {"wrong": "key"}, TestSchema2)
    assert err is not None
    ok("tool args: invalid args detected")
except Exception as e:
    fail("tool args: invalid args detected", str(e))

# memory parser
try:
    raw = '{"facts": [{"subject": "user", "predicate": "likes_tea", "object_value": "tea", "category": "preference", "confidence": 0.95}]}'
    facts = parse_memory_facts(raw)
    assert len(facts) == 1
    assert facts[0].object_value == "tea"
    ok("memory parser: valid facts")
except Exception as e:
    fail("memory parser: valid facts", str(e))

try:
    raw = '{"facts": [{"subject": "user", "predicate": "maybe", "object_value": "x", "category": "fact", "confidence": 0.3}]}'
    facts = parse_memory_facts(raw, confidence_threshold=0.7)
    assert len(facts) == 0
    ok("memory parser: drops low-confidence facts")
except Exception as e:
    fail("memory parser: drops low-confidence facts", str(e))


# ─── C7/C8: Ingest Pipeline ───────────────────────────────────────
section("C7/C8: Document Loaders + Text Splitters")

from ingest.loader_registry import get_loader, supported_extensions
from ingest.loaders import load_text_file, load_csv, load_json
from ingest.splitters import split_documents, SplitterFactory
from ingest.ingest_log import IngestLog
from ingest.chat_exporter import export_chat_turns, export_training_jsonl

# loader registry
try:
    exts = supported_extensions()
    assert ".txt" in exts
    assert ".md" in exts
    ok(f"loader registry: {len(exts)} extensions registered", ", ".join(sorted(exts)[:8]) + "...")
except Exception as e:
    fail("loader registry", str(e))

# text file loader
with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
    f.write("Hello world\nThis is a test document.")
    tmp_path = f.name
try:
    docs = load_text_file(Path(tmp_path))
    assert len(docs) == 1
    assert "Hello world" in docs[0].page_content
    ok("text file loader")
except Exception as e:
    fail("text file loader", str(e))
finally:
    os.unlink(tmp_path)

# CSV loader
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
    f.write("name,age\nAlice,30\nBob,25\n")
    tmp_path = f.name
try:
    docs = load_csv(Path(tmp_path))
    assert len(docs) == 2
    assert "Alice" in docs[0].page_content
    ok("CSV loader: 2 rows")
except Exception as e:
    fail("CSV loader", str(e))
finally:
    os.unlink(tmp_path)

# JSON loader
with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    json.dump({"key": "value", "nested": {"a": 1}}, f)
    tmp_path = f.name
try:
    docs = load_json(Path(tmp_path))
    assert len(docs) == 1
    ok("JSON loader")
except Exception as e:
    fail("JSON loader", str(e))
finally:
    os.unlink(tmp_path)

# splitters
try:
    from langchain_core.documents import Document
    docs = [Document(page_content="Hello world. " * 200, metadata={"source": "test.txt"})]
    chunks = split_documents(docs, path_suffix=".txt")
    assert len(chunks) > 1
    ok(f"recursive splitter: {len(docs)} doc → {len(chunks)} chunks")
except Exception as e:
    fail("recursive splitter", str(e))

# markdown splitter
try:
    md_text = "# Title\nSome intro.\n## Section 1\nDetails here.\n## Section 2\nMore details."
    docs = [Document(page_content=md_text, metadata={"source": "test.md"})]
    chunks = split_documents(docs, path_suffix=".md")
    assert len(chunks) >= 1
    ok(f"markdown splitter: {len(chunks)} chunks from headers")
except Exception as e:
    fail("markdown splitter", str(e))

# ingest log dedup
with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
    tmp_db = f.name
try:
    log = IngestLog(tmp_db)
    assert log.is_stale("test.txt", "hash1") is True
    log.record("test.txt", "hash1", chunk_count=5)
    assert log.is_stale("test.txt", "hash1") is False
    assert log.is_stale("test.txt", "hash2") is True
    stats = log.stats()
    assert stats["total_documents"] == 1
    ok("ingest log: dedup works")
except Exception as e:
    fail("ingest log: dedup works", str(e))
finally:
    os.unlink(tmp_db)

# chat exporter
try:
    rows = [
        {"role": "user", "content": "What's the weather?", "ts": "2026-08-10T10:00:00"},
        {"role": "assistant", "content": "Rain, operator. Pack an umbrella.", "ts": "2026-08-10T10:00:01"},
    ]
    docs = export_chat_turns(rows, "thread-abc")
    assert len(docs) == 1
    assert "weather" in docs[0].page_content.lower()
    ok("chat exporter: turn pairs")
except Exception as e:
    fail("chat exporter: turn pairs", str(e))


# ─── C12: Memory ──────────────────────────────────────────────────
section("C12: Memory (profile, retention)")

from memory.profile import ProfileBuilder

try:
    # mock fact store
    mock_vs = MagicMock()
    mock_vs.collections = {"memory": MagicMock()}
    mock_vs.collections["memory"].get.return_value = {
        "ids": ["f1", "f2"],
        "metadatas": [
            {"subject": "user", "predicate": "likes_tea", "object_value": "tea",
             "category": "preference", "confidence": 0.95, "ts": "2026-08-01T00:00:00"},
            {"subject": "user", "predicate": "works_at", "object_value": "MIT",
             "category": "fact", "confidence": 0.85, "ts": "2026-08-01T00:00:00"},
        ],
    }
    mock_store = MagicMock()
    mock_store.vs = mock_vs

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_profile = Path(f.name)

    builder = ProfileBuilder(mock_store, profile_file=tmp_profile)
    profile = builder.build(token_cap=300)
    assert "tea" in profile
    assert "MIT" in profile
    ok("profile builder: generates profile from facts", f"{len(profile)} chars")
    tmp_profile.unlink()
except Exception as e:
    fail("profile builder", str(e))


# ─── C14: Tracing ─────────────────────────────────────────────────
section("C14: Tracing")

from trace.redact import redact_body, redact_tool_args, redact_run_metadata
from trace.store import RunStore

# redaction
try:
    assert redact_body("short") == "short"
    long = "x" * 1000
    r = redact_body(long)
    assert len(r) < len(long)
    assert "truncated" in r
    ok("redact: truncates long bodies")
except Exception as e:
    fail("redact: truncates long bodies", str(e))

try:
    args = redact_tool_args("shell", {"command": "rm -rf /"})
    assert "_redacted" in args
    ok("redact: shell args fully redacted")
except Exception as e:
    fail("redact: shell args fully redacted", str(e))

try:
    args = redact_tool_args("web_search", {"query": "hello"})
    assert "query" in args
    ok("redact: non-sensitive tool args kept")
except Exception as e:
    fail("redact: non-sensitive tool args kept", str(e))

# run store
with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
    tmp_trace = f.name
try:
    store = RunStore(tmp_trace)
    store.log_run("run-1", "thread-1", task_type="coding", tokens_used=500,
                  iterations=3, duration_ms=1234.5)
    store.log_run("run-2", "thread-1", task_type="system", status="error",
                  error="tool failed", duration_ms=500)
    rollup = store.daily_rollup()
    assert rollup["total_runs"] == 2
    assert rollup["error_count"] == 1
    ok("run store: log + rollup", f"{rollup}")
    store.close()
except Exception as e:
    fail("run store", str(e))
finally:
    os.unlink(tmp_trace)


# ─── C13: Specialist Sub-graphs ───────────────────────────────────
section("C13: Specialist Sub-graphs")

from core.subgraphs.coder import CODER_TOOLS, RESULT_CAP
from core.subgraphs.vision import RESULT_CAP as VISION_CAP
from core.subgraphs.reasoner import RESULT_CAP as REASONER_CAP

try:
    assert "file_read" in CODER_TOOLS
    assert "shell" in CODER_TOOLS
    assert RESULT_CAP == 2048
    ok(f"coder sub-graph: {len(CODER_TOOLS)} tools, cap={RESULT_CAP}")
except Exception as e:
    fail("coder sub-graph", str(e))

try:
    assert VISION_CAP == 2048
    ok("vision sub-graph: cap=2048")
except Exception as e:
    fail("vision sub-graph", str(e))

try:
    assert REASONER_CAP == 2048
    ok("reasoner sub-graph: cap=2048")
except Exception as e:
    fail("reasoner sub-graph", str(e))


# ─── C5: New Tools ────────────────────────────────────────────────
section("C5: New Tools (comms, coding, home, media)")

from tools.comms.tools import push_notify, email_send, email_search, calendar_list
from tools.coding.tools import github_list_repos, github_get_file, github_create_issue
from tools.home.tools import mqtt_publish, mqtt_subscribe
from tools.media.tools import yt_download, yt_info, rss_read

# comms tools
try:
    assert push_notify.name == "push_notify"
    assert email_send.name == "email_send"
    assert calendar_list.name == "calendar_list"
    ok(f"comms tools: {', '.join([t.name for t in [push_notify, email_send, email_search, calendar_list]])}")
except Exception as e:
    fail("comms tools", str(e))

# coding tools
try:
    assert github_list_repos.name == "github_list_repos"
    assert github_get_file.name == "github_get_file"
    assert github_create_issue.name == "github_create_issue"
    ok(f"coding tools: {', '.join([t.name for t in [github_list_repos, github_get_file, github_create_issue]])}")
except Exception as e:
    fail("coding tools", str(e))

# home tools
try:
    assert mqtt_publish.name == "mqtt_publish"
    assert mqtt_subscribe.name == "mqtt_subscribe"
    ok(f"home tools: {mqtt_publish.name}, {mqtt_subscribe.name}")
except Exception as e:
    fail("home tools", str(e))

# media tools
try:
    assert yt_download.name == "yt_download"
    assert yt_info.name == "yt_info"
    assert rss_read.name == "rss_read"
    ok(f"media tools: {yt_download.name}, {yt_info.name}, {rss_read.name}")
except Exception as e:
    fail("media tools", str(e))

# test email stub
try:
    result = email_send.invoke({"to": "test@test.com", "subject": "hi", "body": "hello"})
    assert "not yet configured" in result
    ok("email_send: returns stub message")
except Exception as e:
    fail("email_send: stub", str(e))

# test calendar stub
try:
    result = calendar_list.invoke({"date": "2026-08-17"})
    assert "not yet configured" in result
    ok("calendar_list: returns stub message")
except Exception as e:
    fail("calendar_list: stub", str(e))


# ─── Tool Registry (all tools) ────────────────────────────────────
section("Tool Registry: All Tools Registered")

from tools.registry import ToolRegistry

try:
    registry = ToolRegistry()
    names = registry.names()
    ok(f"registry loaded: {len(names)} tools total")
    for n in sorted(names):
        spec = registry.get_spec(n)
        icon = {"read": "📖", "action": "⚡", "destructive": "💀"}.get(spec.danger, "?")
        status = "✓" if spec.enabled else "✗"
        print(f"    {icon} {status} {n:25s} [{spec.danger:12s}] {spec.source}")
except Exception as e:
    fail("tool registry", str(e))


# ─── C15: Voice Pipeline ──────────────────────────────────────────
section("C15: Voice Pipeline")

from voice.wake import WakeWordDetector
from voice.vad import VoiceActivityDetector
from voice.stt import SpeechToText
from voice.tts import TextToSpeech, split_sentences
from voice.stream import VoiceStreamManager, AudioChunkQueue
from voice.bridge import VoiceBridge

# TTS sentence splitter
try:
    sentences = split_sentences("Hello world. This is a test. And another sentence!")
    assert len(sentences) >= 2
    ok(f"TTS sentence splitter: {len(sentences)} sentences")
except Exception as e:
    fail("TTS sentence splitter", str(e))

# TTS sentence splitter with code blocks
try:
    text = "Here is code: ```python\nprint('hi')\n```\nAnd more text after."
    sentences = split_sentences(text)
    assert len(sentences) >= 1
    ok(f"TTS sentence splitter: handles code blocks")
except Exception as e:
    fail("TTS sentence splitter: code blocks", str(e))

# audio chunk queue
try:
    q = AudioChunkQueue()
    q.push("hello", b"audio1")
    q.push("world", b"audio2")
    import asyncio
    async def _run_queue_test():
        chunk1 = await q.next(timeout=1)
        assert chunk1 == ("hello", b"audio1")
        chunk2 = await q.next(timeout=1)
        assert chunk2 == ("world", b"audio2")
        q.cancel()
        chunk3 = await q.next(timeout=1)
        assert chunk3 is None
    asyncio.run(_run_queue_test())
    ok("audio chunk queue: push/next/cancel")
except Exception as e:
    fail("audio chunk queue", str(e))

# voice components init
try:
    wake = WakeWordDetector()
    vad = VoiceActivityDetector()
    stt = SpeechToText()
    tts = TextToSpeech()
    bridge = VoiceBridge(stt, tts, vad, wake)
    ok("voice bridge: all components initialized")
except Exception as e:
    fail("voice bridge init", str(e))


# ─── C16: Device Bridge ───────────────────────────────────────────
section("C16: Device Bridge (alerter)")

from server.alerter import Alerter, THRESHOLDS

try:
    assert THRESHOLDS["disk_percent"] == 90
    assert THRESHOLDS["ram_percent"] == 85
    alerter = Alerter()
    alerts = alerter.check_system_health()
    ok(f"alerter: system health check returned {len(alerts)} alerts", 
       ", ".join(a["type"] for a in alerts) if alerts else "all clear")
except Exception as e:
    fail("alerter", str(e))


# ─── Bridge: MQTT ─────────────────────────────────────────────────
section("Bridge: MQTT Bridge")

from bridge.mqtt_bridge import MQTTBridge

try:
    bridge = MQTTBridge(broker="localhost", port=1883)
    assert bridge.broker == "localhost"
    assert bridge.port == 1883
    ok("mqtt bridge: init OK")
except Exception as e:
    fail("mqtt bridge init", str(e))


# ─── Summary ──────────────────────────────────────────────────────
section("RESULTS")
total = PASS + FAIL
print(f"\n  \033[32m{PASS} passed\033[0m / \033[31m{FAIL} failed\033[0m / {total} total\n")
if FAIL == 0:
    print("  \033[32m ALL TESTS PASSED \033[0m\n")
else:
    print(f"  \033[31m {FAIL} TESTS FAILED \033[0m\n")
    sys.exit(1)
