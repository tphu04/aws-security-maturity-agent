from __future__ import annotations

import json
import logging
import time

from langchain_core.runnables import RunnableConfig

from pdca.config import settings
from pdca.graph._tracing_helpers import flush_at_node, node_span
from pdca.graph.state import PDCAState
from pdca.tools import AVAILABLE_FUNCTIONS

logger = logging.getLogger(__name__)


def scan_poll_node(state: PDCAState, config: RunnableConfig) -> dict:
    """One poll iteration. Each entry into this node = 1 SqliteSaver checkpoint.

    Tech debt: `time.sleep()` blocks worker thread — accepted in Phase C
    (decision #26). Async migration is Phase E.

    Phase I.2: each iteration emits one `node:scan_poll` span carrying the
    iteration number — accepted "tall trace" trade-off per implementation
    plan §I2 (special case `scan_poll`).
    """
    run_id = state.get("run_id", "")
    check_status = AVAILABLE_FUNCTIONS["check_job_status"]

    iteration = state.get("scan_poll_count", 0) + 1
    pending = dict(state.get("pending_jobs") or {})
    completed_meta_delta: dict = {}
    new_raw: list = []
    still_pending: dict = {}

    with node_span(
        "scan_poll", run_id, iteration=iteration, pending_count=len(pending)
    ) as sp:
        elapsed = time.time() - state.get("scan_started_at", 0)
        now_ts = time.time()
        if elapsed > settings.poll_timeout_s:
            logger.warning(
                "scan timeout",
                extra={
                    "run_id": run_id,
                    "elapsed_s": elapsed,
                    "pending": len(pending),
                },
            )
            for jid, meta in pending.items():
                completed_meta_delta[jid] = {
                    **meta,
                    "status": "timeout",
                    "completed_at": now_ts,
                }
            sp.update(output={"reason": "timeout", "drained": len(pending)})
            flush_at_node()
            return {
                "pending_jobs": {},
                "completed_jobs": {
                    **state.get("completed_jobs", {}),
                    **completed_meta_delta,
                },
                "scan_poll_count": iteration,
            }

        for job_id, meta in pending.items():
            try:
                raw = check_status.invoke({"job_id": job_id})
                data = json.loads(raw) if isinstance(raw, str) else raw
                api_resp = data.get("data", data) if isinstance(data, dict) else {}
                status = api_resp.get("status")

                if status == "completed":
                    result = api_resp.get("result", [])
                    if isinstance(result, list):
                        new_raw.extend(result)
                    elif result:
                        new_raw.append(result)
                    completed_meta_delta[job_id] = {
                        **meta,
                        "status": "completed",
                        "completed_at": time.time(),
                    }
                    logger.info(
                        "job completed", extra={"run_id": run_id, "job_id": job_id}
                    )
                elif status == "failed":
                    completed_meta_delta[job_id] = {
                        **meta,
                        "status": "failed",
                        "completed_at": time.time(),
                    }
                    logger.warning(
                        "job failed", extra={"run_id": run_id, "job_id": job_id}
                    )
                else:
                    still_pending[job_id] = meta
            except Exception as e:
                logger.error(
                    "poll error",
                    extra={"run_id": run_id, "job_id": job_id, "error": str(e)},
                )
                still_pending[job_id] = meta

        sp.update(
            output={
                "completed_in_iter": len(completed_meta_delta),
                "still_pending": len(still_pending),
                "new_findings": len(new_raw),
            }
        )
        flush_at_node()

    if still_pending:
        time.sleep(settings.poll_interval_s)  # tech debt — decision #26

    return {
        "pending_jobs": still_pending,
        "completed_jobs": {
            **state.get("completed_jobs", {}),
            **completed_meta_delta,
        },
        # explicit append (no reducer — decision #28)
        "raw_findings": state.get("raw_findings", []) + new_raw,
        "scan_poll_count": iteration,
    }
