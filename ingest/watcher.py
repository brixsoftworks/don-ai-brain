"""ingest/watcher.py — watchfiles folder watch + debounce + dedup.

Watches ~/jarvishome/notes and ~/jarvishome/inbox for new/changed files.
Debounces (2s) to avoid half-written files. Dedup via IngestLog.

See docs/component-7 §4.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

log = logging.getLogger("don.ingest.watcher")

try:
    from watchfiles import awatch, Change  # type: ignore[import-untyped]
    HAS_WATCHFILES = True
except ImportError:
    HAS_WATCHFILES = False
    log.warning("watchfiles not installed; folder watching disabled")


class FolderWatcher:
    """Watch configured folders for new/changed files.

    Usage:
        watcher = FolderWatcher(folders=["~/jarvishome/notes"])
        async for paths in watcher.watch():
            process(paths)
    """

    def __init__(
        self,
        folders: list[str | Path] | None = None,
        debounce_ms: int = 2000,
        ignored_suffixes: tuple[str, ...] = (".tmp", ".swp", ".DS_Store"),
    ):
        self.folders = [Path(f).expanduser() for f in (folders or [])]
        self.debounce_ms = debounce_ms
        self.ignored_suffixes = ignored_suffixes

    def _should_ignore(self, path: Path) -> bool:
        return (
            path.suffix in self.ignored_suffixes
            or path.name.startswith(".")
            or path.is_dir()
        )

    async def watch(self):
        """Async generator yielding batches of changed file paths.

        Yields lists of Path objects (batched by debounce window).
        """
        if not HAS_WATCHFILES:
            log.error("cannot watch: watchfiles not installed")
            return

        existing = {f for f in self.folders if f.exists()}
        if not existing:
            log.warning("no watch folders exist: %s", self.folders)
            return

        async for changes in awatch(
            *existing,
            debounce=self.debounce_ms,
        ):
            paths = []
            for change_type, path_str in changes:
                path = Path(path_str)
                if self._should_ignore(path):
                    continue
                if change_type in (Change.added, Change.modified):
                    paths.append(path)
            if paths:
                yield paths
