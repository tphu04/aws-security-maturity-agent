from __future__ import annotations

import logging
import time

from langchain_core.runnables import RunnableConfig

from pdca.agents.scanner_agent import ScannerAgent
from pdca.graph._metrics import measure_time, update_metrics
from pdca.graph.state import PDCAState

logger = logging.getLogger(__name__)


def scan_submit_node(state: PDCAState, config: RunnableConfig) -> dict:
    """Submit scan jobs, init pending_jobs dict + scan timing fields."""
    run_id = state.get("run_id", "")
    metrics = state.get("performance_metrics", {})
    plan = state.get("assessment_plan") or {}

    logger.info("scan_submit start", extra={"run_id": run_id})

    with measure_time() as timer:
        agent = ScannerAgent()
        submitted = agent.run_batch(
            target_groups=plan.get("groups_to_scan", []),
            specific_checks=plan.get("checks_to_scan", []),
        )

    pending: dict = {
        item["job_id"]: {
            "task_type": item.get("task_type", "unknown"),
            "task_value": item.get("task_value", ""),
            "status": "pending",
        }
        for item in submitted
        if item.get("job_id")
    }

    metrics = update_metrics(metrics, "step_duration", "scan_submit", timer())
    logger.info(
        "scan_submit done",
        extra={"run_id": run_id, "job_count": len(pending)},
    )

    return {
        "pending_jobs": pending,
        "completed_jobs": {},
        "raw_findings": [],            # explicit reset (no reducer — decision #28)
        "scan_started_at": time.time(),  # wall-clock — survives restart
        "scan_poll_count": 0,
        "scan_job_ids": list(pending.keys()),  # legacy field — keep until end of Phase C
        "performance_metrics": metrics,
    }
