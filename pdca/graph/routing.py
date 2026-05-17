"""Routing functions — Phase C3.

Read-only — every router function MUST NOT mutate state. Mutations belong in
node return dicts so LangGraph can checkpoint them.
"""

from __future__ import annotations

import time
from typing import Literal

from langgraph.graph import END

from pdca.config import settings
from pdca.graph.state import PDCAState


def route_after_planning(state: PDCAState):
    """Halt the workflow at planning if the agent asked the user a clarifying
    question. The clarification is surfaced via assessment_plan and the FE
    reads it from the run snapshot — no scanning/reporting needed.
    """
    plan = state.get("assessment_plan") or {}
    if plan.get("status") == "needs_clarification":
        return END
    return "scan_submit"


def route_after_risk(state: PDCAState) -> Literal["operational_planning", "report"]:
    fails = [
        f for f in state.get("prioritized_findings", []) if f.get("status") == "FAIL"
    ]
    return "operational_planning" if fails else "report"


def route_review_task(state: PDCAState) -> Literal["review_task", "reset_then_execute"]:
    """Continue per-task review or move to execution."""
    tasks = [
        t for t in state.get("remediation_tasks", []) if not t.get("manual_required")
    ]
    if not tasks:
        return "reset_then_execute"
    idx = state.get("current_task_index", 0)
    return "review_task" if idx < len(tasks) else "reset_then_execute"


def route_scan_poll(state: PDCAState) -> Literal["scan_poll", "scan_collect"]:
    """Loop scan_poll while pending, max-iter, and timeout allow.

    Uses `time.time()` (Unix epoch) NOT `time.monotonic()` — state is
    persisted to SqliteSaver and must remain meaningful across process
    restart (decision #27).
    """
    pending = state.get("pending_jobs") or {}
    if not pending:
        return "scan_collect"
    if state.get("scan_poll_count", 0) >= settings.poll_max_iterations:
        return "scan_collect"
    if time.time() - state.get("scan_started_at", 0) > settings.poll_timeout_s:
        return "scan_collect"
    return "scan_poll"
