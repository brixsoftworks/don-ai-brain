"""Prompt builders — ALL template text lives in config/prompts.yaml.

See docs/component-3-prompt-templates.md.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage, SystemMessage

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_PROMPTS_YAML = CONFIG_DIR / "prompts.yaml"


class PromptError(RuntimeError):
    pass


class PromptBank:
    """Loads config/prompts.yaml and renders templates."""

    def __init__(self, path: Path = DEFAULT_PROMPTS_YAML):
        if not path.exists():
            raise PromptError(f"prompts.yaml not found: {path}")
        with open(path) as fh:
            data = yaml.safe_load(fh)
        self.data = data

    # ---------------------------------------------------------------- shared

    def build_shared(self, *, user_name: str = "Operator", device: str = "laptop",
                     timestamp: str | None = None, memory_context: str = "") -> SystemMessage:
        template = self.data["shared_base"]["system"]
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        return SystemMessage(
            content=template.format(
                user_name=user_name, device=device, timestamp=ts, memory_context=memory_context
            )
        )

    def build_department(self, dept: str) -> str:
        try:
            return self.data["departments"][dept]
        except KeyError:
            raise PromptError(f"no department extension for: {dept}")

    def system_for(self, dept: str, **shared_vars) -> SystemMessage:
        """Shared DON core + department extension."""
        base = self.build_shared(**shared_vars).content
        return SystemMessage(content=f"{base}\n\n{self.build_department(dept)}")

    # -------------------------------------------------------------- classifier

    def build_classifier(self, user_input: str) -> list:
        """Few-shot JSON classifier prompt (system + human)."""
        cls = self.data["classifier"]
        human = cls["prompt"].format(user_input=user_input)
        return [
            SystemMessage(content=f"{cls['system']}\n\nExamples:\n{cls['examples']}"),
            HumanMessage(content=human),
        ]

    # --------------------------------------------------------------- approval

    def build_approval(self, *, tool: str, args: str, reason: str = "") -> dict:
        appr = self.data["approval"]
        action = f"{tool} {args}".strip()
        return {
            "request": appr["request"].format(action=action),
            "detail": appr["detail"].format(tool=tool, args=args, reason=reason),
            "question": appr["question"],
        }


def load_prompt_bank() -> PromptBank:
    return PromptBank()
