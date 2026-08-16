"""Runtime settings from config/limits.yaml (circuit breakers, timeouts)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@dataclass(frozen=True)
class Settings:
    max_iterations: int = 15
    max_tokens_per_task: int = 30_000
    tool_timeout_seconds: int = 60
    tool_output_cap_bytes: int = 8_192
    ollama_timeout_gen_seconds: int = 60
    ollama_timeout_connect_seconds: int = 30
    interrupt_timeout_hours: int = 24
    chat_log_retention_days: int = 90
    ollama_host: str = "http://localhost:11434"


def load_settings(path: Path | None = None) -> Settings:
    path = path or (CONFIG_DIR / "limits.yaml")
    if not path.exists():
        return Settings()
    with open(path) as fh:
        data = yaml.safe_load(fh) or {}
    limits = data.get("limits", {})
    ollama = data.get("ollama", {})
    return Settings(
        max_iterations=limits.get("MAX_ITERATIONS", 15),
        max_tokens_per_task=limits.get("MAX_TOKENS_PER_TASK", 30_000),
        tool_timeout_seconds=limits.get("TOOL_TIMEOUT_SECONDS", 60),
        tool_output_cap_bytes=limits.get("TOOL_OUTPUT_CAP_BYTES", 8_192),
        ollama_timeout_gen_seconds=limits.get("OLLAMA_TIMEOUT_GEN_SECONDS", 60),
        ollama_timeout_connect_seconds=limits.get("OLLAMA_TIMEOUT_CONNECT_SECONDS", 30),
        interrupt_timeout_hours=limits.get("INTERRUPT_TIMEOUT_HOURS", 24),
        chat_log_retention_days=limits.get("CHAT_LOG_RETENTION_DAYS", 90),
        ollama_host=ollama.get("host", "http://localhost:11434"),
    )
