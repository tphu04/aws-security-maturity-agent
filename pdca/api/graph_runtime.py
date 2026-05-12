"""LangGraph web driver — Phase D-web (replaces threaded RunOrchestrator).

Thin shim between FastAPI handlers (`pdca/api/chatbot.py`) and the LangGraph
runtime in `pdca/graph/`. Responsibilities:

1. Build & cache the compiled graph singleton (`SqliteSaver` checkpointer).
2. `start_run(...)` — assign run_id/thread_id, build initial PDCAState,
   spawn a daemon thread that streams the graph until it interrupts at
   `review_task` (or runs to END if no FAIL findings).
3. `resume_after_decision(...)` — `app.update_state()` with the new task
   decision + `current_task_index` bump, then spawn a thread to resume.
4. `list_run_ids()` / `get_state_values(...)` — read snapshots for FE.

Threading model: one daemon thread per run. Interrupt is cooperative —
the thread runs until LangGraph returns (interrupt or END) and exits.
A new POST /approvals spawns a fresh thread that resumes from checkpoint.

Concurrency: a per-thread_id `Lock` serializes start + resume so a slow
client cannot double-spawn the same run.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

import requests

from pdca.config import settings
from pdca.graph.graph import build_graph
from pdca.observability.context import set_run_id
from pdca.observability.logger import get_logger
from pdca.observability.tracing import end_trace, start_trace

logger = get_logger("pdca.api.graph_runtime")


# ---------------------------------------------------------------------------
# Compiled graph singleton + run registry
# ---------------------------------------------------------------------------
_app = None
_app_lock = threading.Lock()

# Per-thread_id lock: serializes start/resume for a single run.
_run_locks: Dict[str, threading.Lock] = {}
_run_locks_guard = threading.Lock()

# In-memory registry of runs created in this process. Persists across
# checkpointer restart? No — but `SqliteSaver` keeps its own thread state
# in `data/checkpoints/pdca_state.db`. List endpoint can union both.
_known_runs: Dict[str, Dict[str, Any]] = {}
_known_runs_lock = threading.Lock()


def get_app():
    """Lazy-build the compiled graph; safe to call from any thread."""
    global _app
    if _app is None:
        with _app_lock:
            if _app is None:
                _app = build_graph()
                logger.info("graph compiled (singleton)")
    return _app


def _config_for(thread_id: str) -> Dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _run_lock(thread_id: str) -> threading.Lock:
    with _run_locks_guard:
        lock = _run_locks.get(thread_id)
        if lock is None:
            lock = threading.Lock()
            _run_locks[thread_id] = lock
    return lock


def _register_run(run_id: str, thread_id: str, prompt: str, scope: Optional[str], group: str) -> None:
    with _known_runs_lock:
        _known_runs[run_id] = {
            "run_id": run_id,
            "thread_id": thread_id,
            "prompt": prompt,
            "scope": scope,
            "group": group,
            "started_at": time.time(),
        }


def list_run_ids() -> List[str]:
    """All run_ids known to this process. Sorted by start time desc."""
    with _known_runs_lock:
        items = sorted(
            _known_runs.values(),
            key=lambda r: r.get("started_at", 0),
            reverse=True,
        )
    return [r["run_id"] for r in items]


def get_run_metadata(run_id: str) -> Optional[Dict[str, Any]]:
    with _known_runs_lock:
        meta = _known_runs.get(run_id)
        return dict(meta) if meta else None


# ---------------------------------------------------------------------------
# Initial state builder
# ---------------------------------------------------------------------------
def _initial_state(run_id: str, prompt: str, group: str) -> Dict[str, Any]:
    """PDCAState seed for a fresh run.

    Notes:
    - `user_request` includes the explicit group hint so PlanningAgent can
      use it (PlanningAgent reads NL but the group nudge increases hit rate).
    - `cycle_iteration=0` matches the CLI seed (see orchestrator.py:152).
    - We do NOT pre-seed `assessment_plan` — planning_node owns it.
    """
    request_text = prompt.strip()
    if group and group.lower() not in request_text.lower():
        request_text = f"{request_text} (focus: {group})"
    return {
        "run_id": run_id,
        "user_request": request_text,
        "cycle_iteration": 0,
        "performance_metrics": {
            "step_duration": {},
            "llm_latency": {},
            "system_info": {"start_time": time.time()},
        },
    }


# ---------------------------------------------------------------------------
# Thread workers
# ---------------------------------------------------------------------------
def _stream_until_pause(thread_id: str, payload) -> None:
    """Drive `app.stream(payload, config)` until interrupt or END.

    `payload` is the seed dict for first stream, or `None` to resume from
    the checkpointer (post-update_state).

    Errors are logged + persisted as `errors` state delta — graph will
    surface them via `report` outcome tag. We never re-raise; the thread
    must exit cleanly.
    """
    app = get_app()
    config = _config_for(thread_id)
    set_run_id(thread_id)

    trace = start_trace(thread_id, environment="prod")
    try:
        for _event in app.stream(payload, config=config):
            # Drain stream — every event = 1 super-step. Side-effects
            # (state updates, checkpoints) handled by LangGraph.
            pass

        snapshot = app.get_state(config)
        next_nodes = list(snapshot.next or ())
        logger.info(
            "stream paused",
            extra={"thread_id": thread_id, "next": next_nodes or "END"},
        )
    except Exception as e:
        logger.exception(
            "stream failed", extra={"thread_id": thread_id, "error": str(e)}
        )
        try:
            trace.set_status("error", f"{type(e).__name__}: {e}")
        except Exception:
            pass
    finally:
        try:
            end_trace(trace)
        except Exception:
            pass


def _spawn(thread_id: str, payload) -> None:
    t = threading.Thread(
        target=_stream_until_pause,
        args=(thread_id, payload),
        daemon=True,
        name=f"graph-{thread_id[:12]}",
    )
    t.start()


# ---------------------------------------------------------------------------
# Public driver API
# ---------------------------------------------------------------------------
def start_run(prompt: str, scope: Optional[str], group: str) -> Dict[str, str]:
    """Start a new PDCA run end-to-end.

    Returns:
        {"run_id": ..., "thread_id": ...}. The graph runs in a daemon
        thread; the caller should poll `GET /v1/runs/{run_id}` to observe
        progress.
    """
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    thread_id = run_id  # 1:1 mapping — simplifies adapter + lookups
    _register_run(run_id, thread_id, prompt, scope, group)

    initial = _initial_state(run_id, prompt, group)

    lock = _run_lock(thread_id)
    with lock:
        _spawn(thread_id, initial)

    logger.info(
        "run started",
        extra={"run_id": run_id, "thread_id": thread_id, "group": group},
    )
    return {"run_id": run_id, "thread_id": thread_id}


def get_state_values(run_id: str) -> Optional[Dict[str, Any]]:
    """Return the current snapshot.values + snapshot.next as a flat dict.

    Shape returned to caller:
      {
        "values": <PDCAState dict>,
        "next": ["review_task"] | [],   # empty when run reached END
        "checkpoint_ts": <iso str | None>,
      }

    Returns None if no checkpoint exists yet for this run_id (e.g. POST
    /v1/runs returned but the worker thread hasn't checkpointed — race
    condition only on the very first ms).
    """
    app = get_app()
    config = _config_for(run_id)
    snapshot = app.get_state(config)
    if snapshot is None or snapshot.values is None or not snapshot.values:
        return None
    return {
        "values": dict(snapshot.values),
        "next": list(snapshot.next or ()),
        "checkpoint_ts": getattr(snapshot, "created_at", None),
    }


def get_state_history(run_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Return checkpoint history for a run (used by adapter to build graphNodes)."""
    app = get_app()
    config = _config_for(run_id)
    out: List[Dict[str, Any]] = []
    try:
        for s in app.get_state_history(config):
            out.append({
                "values": dict(s.values) if s.values else {},
                "next": list(s.next or ()),
                "metadata": dict(s.metadata) if s.metadata else {},
                "created_at": getattr(s, "created_at", None),
            })
            if len(out) >= limit:
                break
    except Exception as e:
        logger.warning(
            "get_state_history failed",
            extra={"run_id": run_id, "error": str(e)},
        )
    # LangGraph yields newest first — reverse for chronological order.
    out.reverse()
    return out


def resume_after_decision(run_id: str, task_id: str, decision: str) -> bool:
    """Apply a HITL decision and resume the graph by one step.

    Resume semantics:
      1. Read current state. If next != ('review_task',), refuse — the run
         is not waiting on us.
      2. update_state with the new task_execution_plan + bumped
         current_task_index.
      3. Spawn a worker thread to call `app.stream(None, config)` —
         this either pauses again (next task) or runs to END.

    Returns True on success, False if the task_id is unknown or the run is
    not in waiting state.
    """
    if decision not in ("approve", "approved", "reject", "rejected", "skip", "skipped"):
        logger.warning(
            "invalid decision rejected",
            extra={"run_id": run_id, "task_id": task_id, "decision": decision},
        )
        return False
    # Normalize FE shorthand. Execution only runs "approve"; both "reject"
    # and "skip" are non-executing decisions, but keeping them distinct lets
    # the API adapter preserve the user's choice after refresh.
    if decision in ("approve", "approved"):
        decision_norm = "approve"
    elif decision in ("reject", "rejected"):
        decision_norm = "reject"
    else:
        decision_norm = "skip"

    app = get_app()
    config = _config_for(run_id)

    lock = _run_lock(run_id)
    with lock:
        snapshot = app.get_state(config)
        if not snapshot or not snapshot.values:
            logger.warning("resume refused — no snapshot", extra={"run_id": run_id})
            return False
        next_nodes = list(snapshot.next or ())
        if "review_task" not in next_nodes:
            state = snapshot.values
            matching_task = next(
                (t for t in state.get("remediation_tasks", []) if t.get("task_id") == task_id),
                None,
            )
            if matching_task and (matching_task.get("manual_required") or decision_norm in ("skip", "reject")):
                plan = dict(state.get("task_execution_plan") or {})
                plan[task_id] = decision_norm
                app.update_state(config, {"task_execution_plan": plan})
                logger.info(
                    "decision recorded without resume",
                    extra={"run_id": run_id, "task_id": task_id, "decision": decision_norm, "next": next_nodes},
                )
                return True
            logger.warning(
                "resume refused — not waiting at review_task",
                extra={"run_id": run_id, "next": next_nodes},
            )
            return False

        state = snapshot.values
        tasks = [t for t in state.get("remediation_tasks", []) if not t.get("manual_required")]
        idx = state.get("current_task_index", 0)
        # All-manual case: the filtered queue is empty, but the graph still
        # paused at `interrupt_before=["review_task"]`. Resuming here just
        # means stepping past review_task — its conditional edge routes
        # directly to reset_then_execute (no decisions needed). We still
        # record the plan entry so the audit trail is honest.
        if not tasks:
            plan = dict(state.get("task_execution_plan") or {})
            plan[task_id] = decision_norm
            app.update_state(config, {"task_execution_plan": plan})
            _spawn(run_id, None)
            logger.info(
                "resume scheduled (all-manual passthrough)",
                extra={"run_id": run_id, "task_id": task_id, "decision": decision},
            )
            return True
        if idx >= len(tasks):
            logger.warning(
                "resume refused — index past last task",
                extra={"run_id": run_id, "idx": idx, "len": len(tasks)},
            )
            return False
        current = tasks[idx]
        if current.get("task_id") != task_id:
            # Soft-fail: caller specified a task_id that isn't the head of
            # the queue. We still record the decision — they may approve in
            # a different order than the graph processes. The graph only
            # cares about the head index.
            logger.info(
                "decision recorded for non-head task",
                extra={
                    "run_id": run_id,
                    "task_id": task_id,
                    "head_task_id": current.get("task_id"),
                },
            )

        plan = dict(state.get("task_execution_plan") or {})
        plan[task_id] = decision_norm

        # If we received a decision for the head task, advance the index.
        # Otherwise, keep idx — graph will re-interrupt on the same head.
        new_idx = idx + 1 if current.get("task_id") == task_id else idx

        app.update_state(
            config,
            {"task_execution_plan": plan, "current_task_index": new_idx},
        )
        _spawn(run_id, None)

    logger.info(
        "resume scheduled",
        extra={
            "run_id": run_id,
            "task_id": task_id,
            "decision": decision_norm,
            "new_idx": new_idx,
        },
    )
    return True


def cancel_run(run_id: str) -> bool:
    """Cooperatively cancel a run and any scanner jobs it is waiting on."""
    app = get_app()
    config = _config_for(run_id)

    lock = _run_lock(run_id)
    with lock:
        snapshot = app.get_state(config)
        if not snapshot or not snapshot.values:
            logger.warning("cancel refused — no snapshot", extra={"run_id": run_id})
            return False

        state = snapshot.values
        pending = dict(state.get("pending_jobs") or {})
        completed = dict(state.get("completed_jobs") or {})
        now_ts = time.time()

        for job_id, meta in pending.items():
            try:
                requests.post(
                    f"{settings.scanner_api_url.rstrip('/')}/v1/job/{job_id}/cancel",
                    timeout=8,
                )
            except Exception as e:
                logger.warning(
                    "scanner cancel failed",
                    extra={"run_id": run_id, "job_id": job_id, "error": str(e)},
                )
            completed[job_id] = {
                **meta,
                "status": "cancelled",
                "completed_at": now_ts,
            }

        app.update_state(
            config,
            {
                "cancelled": True,
                "pending_jobs": {},
                "completed_jobs": completed,
                "errors": [{"type": "cancelled", "message": "Run cancelled by user"}],
            },
        )

    logger.info("run cancelled", extra={"run_id": run_id, "cancelled_jobs": len(pending)})
    return True
