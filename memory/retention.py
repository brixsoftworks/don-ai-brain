"""memory/retention.py — pruning/decay jobs for memory layers.

Handles: chat_log archival (90d), chat collection downsampling (2yr),
memory fact decay (365d untouched → confidence -0.05/mo).
See docs/component-12 §5.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from memory.vectorstore import VectorStore

log = logging.getLogger("don.memory.retention")


class RetentionManager:
    """Prune and decay old data across memory layers."""

    def __init__(
        self,
        vs: VectorStore,
        chat_log_conn=None,
        *,
        short_term_days: int = 90,
        episodic_years: int = 2,
        decay_start_days: int = 365,
        decay_rate_per_month: float = 0.05,
    ):
        self.vs = vs
        self.chat_log_conn = chat_log_conn
        self.short_term_days = short_term_days
        self.episodic_years = episodic_years
        self.decay_start_days = decay_start_days
        self.decay_rate_per_month = decay_rate_per_month

    def prune_chat_log(self) -> int:
        """Delete chat_log rows older than short_term_days.

        These should already be archived to the chat vector collection.
        Returns number of rows deleted.
        """
        if self.chat_log_conn is None:
            return 0

        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.short_term_days)).isoformat()
        try:
            cur = self.chat_log_conn.execute(
                "DELETE FROM chat_log WHERE ts < ?", (cutoff,)
            )
            self.chat_log_conn.commit()
            count = cur.rowcount
            if count:
                log.info("pruned %d old chat_log rows (before %s)", count, cutoff[:10])
            return count
        except Exception as exc:  # noqa: BLE001
            log.error("chat_log prune failed: %s", exc)
            return 0

    def decay_memory_facts(self, embed_fn) -> int:
        """Apply confidence decay to old memory facts.

        Facts untouched for >decay_start_days lose decay_rate_per_month
        confidence per month. Facts below 0.1 confidence are deleted.
        Returns number of facts deleted.
        """
        coll = self.vs.collections["memory"]
        try:
            res = coll.get(limit=1000)
        except Exception as exc:  # noqa: BLE001
            log.error("memory decay fetch failed: %s", exc)
            return 0

        ids = res.get("ids") or []
        metas = res.get("metadatas") or []
        now = datetime.now(timezone.utc)
        deleted = 0
        updated = 0

        for i, (fid, meta) in enumerate(zip(ids, metas)):
            ts_str = meta.get("ts", "")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            age_days = (now - ts).total_seconds() / 86400
            if age_days <= self.decay_start_days:
                continue

            months_old = (age_days - self.decay_start_days) / 30
            current_conf = float(meta.get("confidence", 1.0))
            new_conf = current_conf - (months_old * self.decay_rate_per_month)

            if new_conf < 0.1:
                coll.delete(ids=[fid])
                deleted += 1
            elif new_conf != current_conf:
                meta["confidence"] = round(new_conf, 3)
                coll.update(ids=[fid], metadatas=[meta])
                updated += 1

        if deleted or updated:
            log.info("memory decay: %d deleted, %d updated", deleted, updated)
        return deleted

    def run_all(self, embed_fn=None) -> dict:
        """Run all retention jobs. Returns stats."""
        stats = {
            "chat_log_pruned": self.prune_chat_log(),
            "facts_decayed": 0,
        }
        if embed_fn:
            stats["facts_decayed"] = self.decay_memory_facts(embed_fn)
        return stats
