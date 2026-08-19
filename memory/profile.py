"""memory/profile.py — user profile builder (nightly).

Rebuilds the curated, high-confidence profile from memory facts.
Injected as {memory_context} into DON's system prompt.
See docs/component-12 §4.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("don.memory.profile")

PROFILE_FILE = Path.home() / "jarvishome" / "profile.json"
PROFILE_TOKEN_CAP = 300


class ProfileBuilder:
    """Build and cache the user profile from memory facts."""

    def __init__(self, fact_store, profile_file: Path = PROFILE_FILE):
        self.fact_store = fact_store
        self.profile_file = profile_file

    def build(self, token_cap: int = PROFILE_TOKEN_CAP) -> str:
        """Rebuild the profile text from top-confidence facts.

        Returns the profile string (≤ token_cap tokens, ~4 chars/token).
        Also writes to profile_file for caching.
        """
        coll = self.fact_store.vs.collections["memory"]
        try:
            res = coll.get(limit=200)
        except Exception as exc:  # noqa: BLE001
            log.error("failed to fetch facts for profile: %s", exc)
            return self._load_cached()

        metas = res.get("metadatas") or []
        if not metas:
            return self._load_cached()

        # sort by confidence descending, keep top facts
        facts = sorted(metas, key=lambda m: float(m.get("confidence", 0.0)), reverse=True)

        # build profile lines grouped by category
        lines = []
        char_budget = token_cap * 4  # ~4 chars per token
        used = 0

        for m in facts:
            subject = m.get("subject", "user")
            predicate = m.get("predicate", "")
            obj = m.get("object_value", "")
            category = m.get("category", "fact")

            if not predicate:
                continue

            line = f"- [{category}] {subject} {predicate} {obj}"
            if used + len(line) > char_budget:
                break
            lines.append(line)
            used += len(line)

        text = "\n".join(lines)

        # cache to disk
        try:
            self.profile_file.parent.mkdir(parents=True, exist_ok=True)
            self.profile_file.write_text(json.dumps({
                "built_at": datetime.now(timezone.utc).isoformat(),
                "fact_count": len(lines),
                "token_cap": token_cap,
                "profile": text,
            }, indent=2, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            log.error("failed to write profile cache: %s", exc)

        log.info("profile rebuilt: %d facts, ~%d tokens", len(lines), used // 4)
        return text

    def _load_cached(self) -> str:
        """Load the previously cached profile from disk."""
        try:
            if self.profile_file.exists():
                data = json.loads(self.profile_file.read_text())
                return data.get("profile", "")
        except Exception:  # noqa: BLE001
            pass
        return ""

    def get(self) -> str:
        """Get the current profile (cached or built)."""
        cached = self._load_cached()
        return cached if cached else self.build()
