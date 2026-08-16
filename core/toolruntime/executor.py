"""Tool executor: thread pool, per-tool timeout, kill semantics.

Sync tools (shell, MQTT, python) run in a bounded thread pool so they never
block the async graph; on timeout the Future is cancelled and the agent gets
an explicit "tool timed out" message.

See docs/component-6 §5.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError

log = logging.getLogger("don.toolruntime")


class ToolExecutor:
    def __init__(self, pool_size: int = 4, default_timeout: float = 60.0):
        self.pool = ThreadPoolExecutor(max_workers=pool_size, thread_name_prefix="don-tool")
        self.default_timeout = default_timeout

    def run_sync(self, fn, *args, timeout: float | None = None, **kwargs) -> str:
        """Run fn synchronously with a hard timeout. Returns result string."""
        timeout = timeout if timeout is not None else self.default_timeout
        future: Future = self.pool.submit(fn, *args, **kwargs)
        try:
            return str(future.result(timeout=timeout))
        except TimeoutError:
            future.cancel()
            raise TimeoutError(f"tool timed out after {timeout:.0f}s")

    async def run_async(self, fn, *args, timeout: float | None = None, **kwargs) -> str:
        """Run fn (sync) in the pool from async context with timeout."""
        timeout = timeout if timeout is not None else self.default_timeout
        loop = asyncio.get_running_loop()
        future = self.pool.submit(fn, *args, **kwargs)
        try:
            return str(await asyncio.wait_for(loop.run_in_executor(None, future.result), timeout=timeout))
        except asyncio.TimeoutError:
            future.cancel()
            raise TimeoutError(f"tool timed out after {timeout:.0f}s")

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False)
