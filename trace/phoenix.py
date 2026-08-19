"""trace/phoenix.py — OpenInference + OTLP wiring → Arize Phoenix.

Auto-instrumentation registers once at process start — zero changes to
node code. Phoenix provides the full debug UI.
See docs/component-14 §3, §5.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

log = logging.getLogger("don.trace.phoenix")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG = CONFIG_DIR / "phoenix.yaml"


def _load_config(path: Path | None = None) -> dict:
    path = path or DEFAULT_CONFIG
    if not path.exists():
        return {}
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def setup_phoenix(config_path: Path | None = None) -> bool:
    """Initialize Phoenix tracing. Returns True if successfully wired.

    This should be called once at process start, before any LLM/graph code
    is imported. It registers OpenInference auto-instrumentation which
    captures all LangChain/LangGraph calls automatically.
    """
    config = _load_config(config_path)
    if not config.get("enabled", True):
        log.info("phoenix tracing disabled in config")
        return False

    try:
        import phoenix as px

        # launch Phoenix if not already running
        port = config.get("port", 6006)
        project_name = config.get("project_name", "don")

        px.launch_app(port=port)
        log.info("phoenix launched on port %d", port)

        # register OpenInference auto-instrumentation
        try:
            from openinference.instrumentation.langchain import LangChainInstrumentor

            instrumentor = LangChainInstrumentor()
            if not instrumentor.is_instrumented_by_opentelemetry:
                instrumentor.instrument()
                log.info("langchain auto-instrumentation registered")
        except ImportError:
            log.warning(
                "openinference-instrumentation-langchain not installed; "
                "pip install openinference-instrumentation-langchain"
            )
            return True  # phoenix running but no auto-instrumentation

        return True

    except ImportError:
        log.warning("phoenix not installed; pip install arize-phoenix")
        return False
    except Exception as exc:  # noqa: BLE001
        log.error("phoenix setup failed: %s", exc)
        return False


def get_phoenix_url(config_path: Path | None = None) -> str:
    """Return the Phoenix dashboard URL."""
    config = _load_config(config_path)
    port = config.get("port", 6006)
    host = config.get("host", "localhost")
    return f"http://{host}:{port}"
