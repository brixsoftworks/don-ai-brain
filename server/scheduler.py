"""server/scheduler.py — proactive DON (docs/component-16 §7).

APScheduler (pin apscheduler<4) runs cron jobs from config/schedule.yaml;
each fired job enters the graph at classify_input with source=scheduler so
the same guard/approval rules apply. Falls back to a simple HH:MM polling
loop if apscheduler is not installed.

Install: pip install "apscheduler<4"
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger("don.scheduler")

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import]
    _HAS_APSCHEDULER = True
except ImportError:
    _HAS_APSCHEDULER = False
    log.info("apscheduler not installed — using simple polling loop (pip install 'apscheduler<4')")


def _make_job_fn(graph, job: dict):
    """Return a callable that fires one scheduled job into the graph."""
    from langchain_core.messages import HumanMessage

    def _fire():
        thread_id = job.get("thread_id", "scheduler")
        config = {"configurable": {"thread_id": thread_id}}
        log.info("scheduler firing: %s", job["name"])
        try:
            graph.invoke(
                {
                    "messages": [HumanMessage(content=job["prompt"])],
                    "user_id": "scheduler",
                    "device": "server",
                    "iterations": 0,
                    "tokens_used": 0,
                    "source": "scheduler",
                },
                config,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("scheduler job %s failed: %s", job["name"], exc)

    return _fire


def start_scheduler(graph, jobs: list[dict]) -> object | None:
    """Start APScheduler with cron jobs. Returns the scheduler or None.

    If APScheduler is not installed, logs a warning and returns None.
    Call scheduler.shutdown() on app exit.
    """
    if not jobs:
        return None

    if _HAS_APSCHEDULER:
        scheduler = AsyncIOScheduler(timezone="UTC")
        for job in jobs:
            cron_expr = job.get("cron", "")
            if not cron_expr or ":" not in cron_expr:
                log.warning("scheduler job %s has invalid cron: %s", job.get("name"), cron_expr)
                continue
            hour, minute = cron_expr.split(":", 1)
            scheduler.add_job(
                _make_job_fn(graph, job),
                "cron",
                hour=int(hour),
                minute=int(minute),
                id=job["name"],
                name=job.get("name"),
                replace_existing=True,
            )
        scheduler.start()
        log.info("APScheduler started with %d job(s)", len(jobs))
        return scheduler

    log.warning(
        "apscheduler not available — install with: pip install 'apscheduler<4'. "
        "Scheduled jobs will not run."
    )
    return None


def run_scheduled(graph, checkpointer, jobs: list[dict]):
    """Blocking poll loop fallback (HH:MM matching). Used when APScheduler is unavailable."""
    from langchain_core.messages import HumanMessage

    last_fired: dict[str, str] = {}
    while True:
        import time
        now = datetime.now(timezone.utc).strftime("%H:%M")
        for job in jobs:
            if job.get("cron") == now and last_fired.get(job["name"]) != now:
                last_fired[job["name"]] = now
                _make_job_fn(graph, job)()
        time.sleep(30)

