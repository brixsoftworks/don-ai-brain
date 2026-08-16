"""server/scheduler.py — proactive DON (docs/component-16 §7).

APScheduler (pin apscheduler<4) runs cron jobs from config/schedule.yaml;
each fired job enters the graph at classify_input with source=scheduler so
the same guard/approval rules apply. Dev uses a simple polling loop so no
extra dependency is required on the dev box.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger("don.scheduler")


def run_scheduled(graph, checkpointer, jobs: list[dict]):
    """Poll loop: for each job whose schedule has passed, enter the graph.

    jobs: [{name, cron: "HH:MM", prompt, thread_id}] from config/schedule.yaml.
    Kept deliberately simple; swap for APScheduler AsyncIOScheduler on the A1.
    """
    from langchain_core.messages import HumanMessage

    last_fired: dict[str, str] = {}
    while True:
        import time
        now = datetime.now(timezone.utc).strftime("%H:%M")
        for job in jobs:
            if job.get("cron") == now and last_fired.get(job["name"]) != now:
                last_fired[job["name"]] = now
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
        time.sleep(30)
