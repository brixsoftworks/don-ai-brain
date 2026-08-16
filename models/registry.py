"""Model registry — loads config/models.yaml, validates against Ollama.

See docs/component-2-chat-models.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_MODELS_YAML = CONFIG_DIR / "models.yaml"


@dataclass(frozen=True)
class ModelSpec:
    """Behavior spec for one model department."""

    name: str
    keep_alive: int = -1
    temperature: float = 0.7
    max_tokens: int | None = 4096
    fallback: list[str] = field(default_factory=list)  # dept names


class RegistryError(RuntimeError):
    pass


class ModelRegistry:
    """Source of truth for models, loaded from YAML (config-driven, no code)."""

    def __init__(self, path: Path = DEFAULT_MODELS_YAML):
        self.path = path
        data = self._load_yaml(path)
        self.specs: dict[str, ModelSpec] = {
            dept: ModelSpec(**cfg)
            for dept, cfg in data.items()
            if dept != "routing"
        }
        self.routing: dict[str, str] = data.get("routing", {})

    @staticmethod
    def _load_yaml(path: Path) -> dict:
        if not path.exists():
            raise RegistryError(f"models.yaml not found: {path}")
        with open(path) as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise RegistryError(f"malformed models.yaml at {path}")
        return data

    def get(self, dept: str) -> ModelSpec:
        try:
            return self.specs[dept]
        except KeyError:
            raise RegistryError(f"unknown model department: {dept}")

    def default(self) -> ModelSpec:
        return self.specs["main"]

    def fallback_for(self, dept: str) -> list[ModelSpec]:
        spec = self.specs[dept]
        return [self.specs[d] for d in spec.fallback if d in self.specs]

    def route_task(self, task_type: str) -> str:
        """Map a task_type to a model department name (defaults to main)."""
        return self.routing.get(task_type, "main")

    def departments(self) -> list[str]:
        return list(self.specs.keys())

    def validate_against_ollama(self, available: list[str]) -> list[str]:
        """Return model names in config but missing from the local Ollama list."""
        configured = {s.name for s in self.specs.values()}
        return sorted(configured - set(available))


def load_registry() -> ModelRegistry:
    """Registry with an optional overrides file for dev/testing.

    Override model names (e.g. use a small local model during development)
    via config/models.override.yaml or the DON_MODELS_YAML env var.
    """
    override_path = os.environ.get("DON_MODELS_YAML")
    if override_path:
        return ModelRegistry(Path(override_path))
    override = CONFIG_DIR / "models.override.yaml"
    if override.exists():
        return ModelRegistry(override)
    return ModelRegistry()
