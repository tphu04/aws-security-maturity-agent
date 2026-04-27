from __future__ import annotations

import json
import logging
import os
import time

from langchain_core.runnables import RunnableConfig

from pdca.agents.shared.normalizer import normalize_results
from pdca.config import settings
from pdca.graph._metrics import measure_time, update_metrics
from pdca.graph.state import PDCAState

logger = logging.getLogger(__name__)


def _finalize_pending(state: PDCAState) -> tuple[dict, dict]:
    """Drain `pending_jobs` into `completed_jobs` with terminal status.

    Router (`route_scan_poll`) can divert to `scan_collect` because of
    `max_iterations` or `timeout` while jobs are still pending — `scan_poll`
    won't run again to mark them. We reconcile here so state reflects reality.
    """
    pending = dict(state.get("pending_jobs") or {})
    if not pending:
        return {}, dict(state.get("completed_jobs") or {})

    elapsed = time.time() - state.get("scan_started_at", 0)
    poll_count = state.get("scan_poll_count", 0)
    if elapsed > settings.poll_timeout_s:
        terminal_status = "timeout"
    elif poll_count >= settings.poll_max_iterations:
        terminal_status = "max_iterations"
    else:
        # Should not happen — router only routes here when one of the above
        # holds OR pending is empty. Use "timeout" as the safe default.
        terminal_status = "timeout"

    drained = {jid: {**meta, "status": terminal_status} for jid, meta in pending.items()}
    completed = {**(state.get("completed_jobs") or {}), **drained}
    logger.warning(
        "scan_collect draining unfinished jobs",
        extra={
            "run_id": state.get("run_id", ""),
            "drained": len(drained),
            "reason": terminal_status,
            "elapsed_s": elapsed,
            "poll_count": poll_count,
        },
    )
    return {}, completed


def scan_collect_node(state: PDCAState, config: RunnableConfig) -> dict:
    """Normalize all raw_findings → normalized_findings (set ONCE, replace).

    Also reconciles any pending jobs left over when router exited the poll
    loop because of max_iterations / timeout — drains them into completed_jobs
    with terminal status so checkpointed state matches reality.
    """
    run_id = state.get("run_id", "")
    metrics = state.get("performance_metrics", {})

    pending_after, completed_after = _finalize_pending(state)

    raw = state.get("raw_findings") or []
    with measure_time() as timer:
        normalized_pkg = normalize_results(raw) if raw else {"findings": []}
    findings = normalized_pkg.get("findings", []) if isinstance(normalized_pkg, dict) else []

    logger.info(
        "scan_collect done",
        extra={
            "run_id": run_id,
            "raw_count": len(raw),
            "normalized_count": len(findings),
            "completed_jobs": len(completed_after),
        },
    )

    # Optional artifact for backward-compat (RescanAgent.load_initial_config + debug).
    try:
        os.makedirs("data/artifacts", exist_ok=True)
        with open("data/artifacts/pre_scan.json", "w", encoding="utf-8") as f:
            json.dump(normalized_pkg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("Could not write pre_scan artifact", extra={"error": str(e)})

    metrics = update_metrics(metrics, "step_duration", "scan_collect", timer())

    out = {
        "normalized_findings": findings,
        "pre_scan_snapshot": normalized_pkg,
        "performance_metrics": metrics,
    }
    # Only emit pending/completed updates when finalization actually drained.
    if state.get("pending_jobs"):
        out["pending_jobs"] = pending_after
        out["completed_jobs"] = completed_after
    return out
