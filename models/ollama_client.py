"""Ollama client — invoke/load/embed/health with fallback chains.

Low-level primitive for everything that touches Ollama.
See docs/component-2 §5–6.
"""
from __future__ import annotations

import logging
import time

import ollama

from models.registry import ModelRegistry, ModelSpec

log = logging.getLogger("don.ollama")


class OllamaClient:
    def __init__(
        self,
        registry: ModelRegistry,
        host: str = "http://localhost:11434",
        gen_timeout_s: float = 60.0,
        connect_timeout_s: float = 30.0,
        max_fallback: int = 2,
    ):
        self.registry = registry
        self._client = ollama.Client(host=host)
        self.gen_timeout_s = gen_timeout_s
        self.connect_timeout_s = connect_timeout_s
        self.max_fallback = max_fallback

    # ------------------------------------------------------------------ health

    def health(self) -> dict:
        """Poll /api/ps -> {model_name: resident}."""
        try:
            ps = self._client.ps()
            return {m.get("name", ""): True for m in ps.get("models", [])}
        except Exception as exc:  # noqa: BLE001
            log.warning("ollama health check failed: %s", exc)
            return {}

    def list_models(self) -> list[str]:
        try:
            tags = self._client.list()
            return [m.get("name", "") for m in tags.get("models", [])]
        except Exception as exc:  # noqa: BLE001
            log.warning("ollama list failed: %s", exc)
            return []

    def ensure_pulled(self, depts: list[str] | None = None) -> list[str]:
        """Auto-pull any configured model missing locally (first boot only)."""
        available = self.list_models()
        missing = self.registry.validate_against_ollama(available)
        targets = missing
        if depts:
            targets = [m for m in missing if m in {self.registry.get(d).name for d in depts}]
        for model in targets:
            log.info("pulling model %s (first boot)", model)
            try:
                self._client.pull(model)
            except Exception as exc:  # noqa: BLE001
                log.error("pull failed for %s: %s", model, exc)
        return targets

    # ------------------------------------------------------------------- load

    def load(self, dept: str) -> float:
        """Set keep_alive + warm a department model. Returns load seconds."""
        spec = self.registry.get(dept)
        t0 = time.monotonic()
        try:
            self._client.chat(
                model=spec.name,
                messages=[{"role": "user", "content": ""}],
                keep_alive=spec.keep_alive,
                options={"num_predict": 1},
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("warm-up failed for %s (%s): %s", dept, spec.name, exc)
        return time.monotonic() - t0

    # ----------------------------------------------------------------- invoke

    @staticmethod
    def _to_ollama_msg(message) -> dict:
        """Normalize LangChain BaseMessage or dict to ollama's {role, content}."""
        if isinstance(message, dict):
            role = message.get("role", "user")
            return {"role": role, "content": message.get("content", "")}
        mtype = getattr(message, "type", "human")
        role = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}.get(mtype, "user")
        return {"role": role, "content": getattr(message, "content", "")}

    def invoke(
        self,
        dept: str,
        messages: list[dict],
        images: list[str] | None = None,
        temperature: float | None = None,
        tools: list[dict] | None = None,
    ) -> dict:
        """Chat completion for a department, walking its fallback chain.

        Accepts plain dicts ({"role", "content"}) or LangChain BaseMessages.
        `tools` are Ollama function schemas ({"type": "function", ...}); the
        raw model message is returned as `message` so callers can read
        native `tool_calls`.

        Returns {"content": str, "model": str, "dept": str, "prompt_eval_count": int,
                 "eval_count": int, "fallback_from": str | None,
                 "message": dict (raw), "tool_calls": list}
        Raises RuntimeError if the whole chain fails.
        """
        normalized = [self._to_ollama_msg(m) for m in messages]
        spec = self.registry.get(dept)
        chain: list[tuple[str, ModelSpec]] = [(dept, spec)]
        chain += [(f"fallback->{f}", self.registry.get(f)) for f in spec.fallback[: self.max_fallback]]
        last_err: Exception | None = None
        for label, candidate in chain:
            try:
                payload: dict = {
                    "model": candidate.name,
                    "messages": normalized,
                    "keep_alive": candidate.keep_alive,
                    "options": {"temperature": temperature if temperature is not None else candidate.temperature},
                }
                if candidate.max_tokens:
                    payload["options"]["num_predict"] = candidate.max_tokens
                if images:
                    payload["images"] = images
                if tools:
                    payload["tools"] = tools
                resp = self._client.chat(**payload)
                msg = resp.get("message", {})
                out = {
                    "content": msg.get("content", ""),
                    "model": candidate.name,
                    "dept": dept,
                    "prompt_eval_count": resp.get("prompt_eval_count", 0),
                    "eval_count": resp.get("eval_count", 0),
                    "fallback_from": label if label.startswith("fallback") else None,
                    "message": msg,
                    "tool_calls": msg.get("tool_calls") or [],
                }
                if label.startswith("fallback"):
                    log.warning("model fallback for dept=%s -> %s", dept, candidate.name)
                return out
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                log.warning("invoke %s (%s) failed: %s", dept, candidate.name, exc)
        raise RuntimeError(f"all models failed for dept={dept}: {last_err}")

    # ------------------------------------------------------------------- embed

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embeddings via the embeddings department model (batch)."""
        spec = self.registry.get("embeddings")
        resp = self._client.embed(model=spec.name, input=texts)
        return resp["embeddings"]

    def embed_query(self, text: str) -> list[float]:
        """Query embedding with the Qwen instruction prefix (see docs/component-9)."""
        prefixed = f"Instruct: Given a document query, retrieve the most relevant chunk.\nQuery: {text}"
        return self.embed([prefixed])[0]
