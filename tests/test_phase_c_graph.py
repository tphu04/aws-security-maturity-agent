"""Phase C — graph topology, scan flow, checkpoint per poll, HITL."""

from __future__ import annotations

import os
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from pdca.graph.checkpointer import get_checkpointer
from pdca.graph.graph import build_graph
from pdca.graph.routing import route_after_risk, route_review_task, route_scan_poll
from pdca.graph.state import PDCAState, ScanJobMeta


# ---------------------------------------------------------------------------
# State + topology smoke
# ---------------------------------------------------------------------------


def test_state_has_phase_c_fields():
    annotations = PDCAState.__annotations__
    for field in (
        "run_id",
        "raw_findings",
        "normalized_findings",
        "pending_jobs",
        "completed_jobs",
        "scan_started_at",
        "scan_poll_count",
        "pre_scan_snapshot",
        "post_scan_snapshot",
        "errors",
    ):
        assert field in annotations, f"PDCAState missing field: {field}"


def test_build_graph_with_memory_saver():
    cp = get_checkpointer("memory")
    g = build_graph(checkpointer=cp)
    assert g is not None


def test_subgraphs_dir_does_not_exist():
    """Phase C v1.4 inline scan nodes — subgraphs/ must not be created."""
    here = os.path.dirname(__file__)
    subgraphs = os.path.join(here, "..", "pdca", "graph", "subgraphs")
    assert not os.path.isdir(subgraphs)


def test_monitoring_agent_deleted():
    path = os.path.join(
        os.path.dirname(__file__), "..", "pdca", "agents", "monitoring_agent.py"
    )
    assert not os.path.exists(path)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_route_after_risk_with_fail():
    state = {"prioritized_findings": [{"status": "FAIL"}, {"status": "PASS"}]}
    assert route_after_risk(state) == "operational_planning"


def test_route_after_risk_no_fail():
    state = {"prioritized_findings": [{"status": "PASS"}]}
    assert route_after_risk(state) == "report"


def test_route_review_task_no_auto_tasks():
    state = {"remediation_tasks": [{"manual_required": True}]}
    assert route_review_task(state) == "reset_then_execute"


def test_route_review_task_pending():
    state = {
        "remediation_tasks": [{"manual_required": False}, {"manual_required": False}],
        "current_task_index": 0,
    }
    assert route_review_task(state) == "review_task"


def test_route_review_task_done():
    state = {
        "remediation_tasks": [{"manual_required": False}],
        "current_task_index": 1,
    }
    assert route_review_task(state) == "reset_then_execute"


def test_route_scan_poll_continues_when_pending():
    import time

    state = {
        "pending_jobs": {"j1": {"status": "pending"}},
        "scan_poll_count": 0,
        "scan_started_at": time.time(),
    }
    assert route_scan_poll(state) == "scan_poll"


def test_route_scan_poll_collects_when_empty():
    state = {"pending_jobs": {}, "scan_poll_count": 0, "scan_started_at": 0}
    assert route_scan_poll(state) == "scan_collect"


def test_route_scan_poll_collects_on_timeout():
    # scan_started_at = 0 (epoch) → elapsed always > timeout
    state = {
        "pending_jobs": {"j1": {"status": "pending"}},
        "scan_poll_count": 0,
        "scan_started_at": 0.0,
    }
    assert route_scan_poll(state) == "scan_collect"


# ---------------------------------------------------------------------------
# Scan node behavior — checkpoint-per-poll + crash recovery semantic
# ---------------------------------------------------------------------------


def _make_check_status_tool(responses_by_job: Dict[str, list]):
    """Tool stub: pop next response from per-job queue when invoked."""
    state = {jid: list(resps) for jid, resps in responses_by_job.items()}

    class _Stub:
        def invoke(self, args):
            jid = args["job_id"]
            queue = state.get(jid, [])
            if not queue:
                return {"status": "completed", "result": []}
            return queue.pop(0)

    return _Stub()


def test_scan_submit_initializes_state():
    from pdca.graph.nodes.scan_submit import scan_submit_node

    state: Dict[str, Any] = {
        "assessment_plan": {"groups_to_scan": [], "checks_to_scan": []},
        "performance_metrics": {},
    }
    with patch("pdca.graph.nodes.scan_submit.ScannerAgent") as Sc:
        Sc.return_value.run_batch.return_value = [
            {"job_id": "j1", "task_type": "group", "task_value": "s3"},
            {"job_id": "j2", "task_type": "checks", "task_value": "c1,c2"},
        ]
        out = scan_submit_node(state, {})

    assert set(out["pending_jobs"].keys()) == {"j1", "j2"}
    assert out["completed_jobs"] == {}
    assert out["raw_findings"] == []
    assert out["scan_poll_count"] == 0
    assert out["scan_started_at"] > 0


def test_scan_poll_appends_findings_and_marks_completed():
    from pdca.graph.nodes import scan_poll as sp

    import time as _t

    base_time = _t.time()
    state = {
        "pending_jobs": {
            "j1": {"task_type": "group", "task_value": "s3", "status": "pending"},
            "j2": {"task_type": "checks", "task_value": "c1", "status": "pending"},
        },
        "completed_jobs": {},
        "raw_findings": [{"existing": True}],
        "scan_started_at": base_time,
        "scan_poll_count": 1,
    }
    tool = _make_check_status_tool(
        {
            "j1": [
                {
                    "data": {
                        "status": "completed",
                        "result": [{"finding_id": "f1"}, {"finding_id": "f2"}],
                    }
                }
            ],
            "j2": [{"data": {"status": "running"}}],
        }
    )
    with patch.dict(sp.AVAILABLE_FUNCTIONS, {"check_job_status": tool}, clear=False):
        with patch("pdca.graph.nodes.scan_poll.time.sleep"):
            out = sp.scan_poll_node(state, {})

    # j1 completed → moved to completed_jobs; j2 still pending
    assert "j1" in out["completed_jobs"]
    assert out["completed_jobs"]["j1"]["status"] == "completed"
    assert out["pending_jobs"] == {
        "j2": {"task_type": "checks", "task_value": "c1", "status": "pending"}
    }
    # raw_findings appended (no reducer — explicit replace)
    assert out["raw_findings"][0] == {"existing": True}
    assert {"finding_id": "f1"} in out["raw_findings"]
    assert out["scan_poll_count"] == 2


def test_scan_poll_timeout_marks_pending_as_timeout():
    from pdca.graph.nodes import scan_poll as sp

    state = {
        "pending_jobs": {"j1": {"status": "pending"}},
        "completed_jobs": {},
        "raw_findings": [],
        "scan_started_at": 0.0,  # huge elapsed → timeout
        "scan_poll_count": 0,
    }
    out = sp.scan_poll_node(state, {})
    assert out["pending_jobs"] == {}
    assert out["completed_jobs"]["j1"]["status"] == "timeout"


def test_scan_collect_drains_pending_on_max_iterations(monkeypatch, tmp_path):
    """Router cuts to scan_collect at max_iter — collect must finalize."""
    from pdca.config import settings as _settings
    from pdca.graph.nodes import scan_collect as sc

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_settings, "poll_max_iterations", 5, raising=False)

    import time as _t

    state = {
        "raw_findings": [],
        "pending_jobs": {
            "j1": {"task_type": "group", "task_value": "s3", "status": "pending"},
            "j2": {"task_type": "group", "task_value": "iam", "status": "pending"},
        },
        "completed_jobs": {"j0": {"status": "completed"}},
        "scan_poll_count": 5,
        "scan_started_at": _t.time(),  # not timed out
    }
    out = sc.scan_collect_node(state, {})
    assert out["pending_jobs"] == {}
    assert out["completed_jobs"]["j1"]["status"] == "max_iterations"
    assert out["completed_jobs"]["j2"]["status"] == "max_iterations"
    assert out["completed_jobs"]["j0"]["status"] == "completed"  # preserved


def test_scan_collect_drains_pending_on_timeout(monkeypatch, tmp_path):
    from pdca.graph.nodes import scan_collect as sc

    monkeypatch.chdir(tmp_path)
    state = {
        "raw_findings": [],
        "pending_jobs": {"j1": {"status": "pending"}},
        "completed_jobs": {},
        "scan_poll_count": 0,
        "scan_started_at": 0.0,  # epoch → elapsed >> timeout
    }
    out = sc.scan_collect_node(state, {})
    assert out["pending_jobs"] == {}
    assert out["completed_jobs"]["j1"]["status"] == "timeout"


def test_scan_collect_does_not_emit_job_keys_when_no_pending(tmp_path, monkeypatch):
    """When pending is already empty, scan_collect must not overwrite jobs state."""
    from pdca.graph.nodes import scan_collect as sc

    monkeypatch.chdir(tmp_path)
    state = {
        "raw_findings": [],
        "pending_jobs": {},
        "completed_jobs": {"j1": {"status": "completed"}},
        "scan_poll_count": 1,
        "scan_started_at": 0.0,
    }
    out = sc.scan_collect_node(state, {})
    assert "pending_jobs" not in out
    assert "completed_jobs" not in out


def test_llm_nodes_pass_callbacks_to_agents():
    """Hook 1+3: callbacks from RunnableConfig must reach agent constructors.

    Decision #31 — without this Langfuse silently drops traces.
    """
    from unittest.mock import MagicMock, patch

    from pdca.graph.nodes import planning, remediation, report, risk_eval

    sentinel = [MagicMock(name="langfuse_handler")]
    cfg = {"callbacks": sentinel}

    with patch("pdca.graph.nodes.planning.PlanningAgent") as P, \
         patch("pdca.graph.nodes.planning.RAGClient"):
        P.return_value.run.return_value = {"groups_to_scan": [], "checks_to_scan": []}
        planning.planning_node(
            {"user_request": "x", "performance_metrics": {}, "rag_available": False},
            cfg,
        )
        kw = P.call_args.kwargs
        assert kw["callbacks"] is sentinel

    with patch("pdca.graph.nodes.risk_eval.RiskEvaluationAgent") as R, \
         patch("pdca.graph.nodes.risk_eval.RAGClient"):
        R.return_value.run.return_value = []
        R.return_value.get_llm_metrics.return_value = {}
        risk_eval.risk_eval_node(
            {"raw_findings": [], "normalized_findings": [], "performance_metrics": {}},
            cfg,
        )
        assert R.call_args.kwargs["callbacks"] is sentinel

    with patch("pdca.graph.nodes.remediation.RemediationPlannerAgent") as Rm:
        Rm.return_value.plan_remediation.return_value = []
        Rm.return_value.get_llm_metrics.return_value = {}
        remediation.remediation_node(
            {
                "prioritized_findings": [],
                "performance_metrics": {},
                "aws_context": {},
            },
            cfg,
        )
        assert Rm.call_args.kwargs["callbacks"] is sentinel

    with patch("pdca.graph.nodes.report.ReportAgent") as Rp, \
         patch("pdca.graph.nodes.report.ReportDataBuilder") as Db:
        Db.build.return_value = {"scope": {"services": []}, "raw_pre_findings": []}
        Rp.return_value.run.return_value = "x.md"
        Rp.return_value.get_llm_metrics.return_value = {}
        report.report_node(
            {
                "analysis_results": None,
                "raw_findings": [],
                "aws_context": {},
                "assessment_plan": {},
                "user_request": "",
                "performance_metrics": {},
                "rag_available": False,
            },
            cfg,
        )
        assert Rp.call_args.kwargs["callbacks"] is sentinel


def test_scan_collect_normalizes_and_sets_snapshot(tmp_path, monkeypatch):
    from pdca.graph.nodes import scan_collect as sc

    monkeypatch.chdir(tmp_path)
    raw = [
        {
            "finding_unique_id": "u1",
            "status_code": "PASS",
            "resource_uid": "r1",
            "service_name": "s3",
            "check_id": "c1",
        }
    ]
    state = {"raw_findings": raw, "completed_jobs": {"j1": {"status": "completed"}}}
    out = sc.scan_collect_node(state, {})
    assert "normalized_findings" in out
    assert isinstance(out["normalized_findings"], list)
    assert out["pre_scan_snapshot"]["findings"] == out["normalized_findings"]
    # raw_findings NOT in output — scan_collect must not clobber it
    assert "raw_findings" not in out


# ---------------------------------------------------------------------------
# Crash-recovery / checkpoint per poll — minimal sub-graph: scan_poll loop
# ---------------------------------------------------------------------------


def test_scan_poll_subloop_resumes_with_remaining_pending(monkeypatch):
    """Verify per-poll checkpoint semantics: kill graph between iterations,
    resume → pending_jobs only contains still-pending jobs (not full reset).
    """
    from langgraph.graph import END, START, StateGraph

    from pdca.graph.checkpointer import get_checkpointer
    from pdca.graph.nodes.scan_poll import scan_poll_node
    from pdca.graph.routing import route_scan_poll
    from pdca.graph.state import PDCAState

    # Build a minimal graph: START → scan_poll → (loop|end_marker)
    def end_marker(state, config):
        return {}

    wf = StateGraph(PDCAState)
    wf.add_node("scan_poll", scan_poll_node)
    wf.add_node("end_marker", end_marker)
    wf.add_edge(START, "scan_poll")
    wf.add_conditional_edges(
        "scan_poll",
        route_scan_poll,
        {"scan_poll": "scan_poll", "scan_collect": "end_marker"},
    )
    wf.add_edge("end_marker", END)

    cp = get_checkpointer("memory")
    g = wf.compile(checkpointer=cp)

    # Tool that returns "running" for j1 first time, then "completed"; j2 always completed
    import time as _t
    from pdca.graph.nodes import scan_poll as sp

    responses = {
        "j1": [{"data": {"status": "running"}}, {"data": {"status": "completed", "result": []}}],
        "j2": [{"data": {"status": "completed", "result": []}}],
    }
    tool = _make_check_status_tool(responses)

    initial = {
        "pending_jobs": {
            "j1": {"task_type": "group", "task_value": "s3", "status": "pending"},
            "j2": {"task_type": "group", "task_value": "iam", "status": "pending"},
        },
        "completed_jobs": {},
        "raw_findings": [],
        "scan_started_at": _t.time(),
        "scan_poll_count": 0,
    }
    cfg = {"configurable": {"thread_id": "t-recover"}}

    with patch.dict(sp.AVAILABLE_FUNCTIONS, {"check_job_status": tool}, clear=False):
        with patch("pdca.graph.nodes.scan_poll.time.sleep"):
            for _ in g.stream(initial, config=cfg):
                pass

    # After completion: snapshot should show 2 completed, 0 pending
    snap = g.get_state(cfg)
    assert snap.values["pending_jobs"] == {}
    assert set(snap.values["completed_jobs"].keys()) == {"j1", "j2"}
    # scan_poll ran ≥ 2 times (j1 took 2 polls)
    assert snap.values["scan_poll_count"] >= 2


# ---------------------------------------------------------------------------
# HITL — interrupt_before review_task
# ---------------------------------------------------------------------------


def test_hitl_interrupt_before_review_task():
    """End-to-end: graph pauses BEFORE review_task. update_state advances index."""
    cp = get_checkpointer("memory")
    g = build_graph(checkpointer=cp)
    cfg = {"configurable": {"thread_id": "t-hitl"}}

    # Inject state right at review_task by updating from START via update_state
    g.update_state(
        cfg,
        {
            "remediation_tasks": [
                {
                    "task_id": "task_1",
                    "finding_id": "f1",
                    "tool_name": "x",
                    "tool_params": {},
                    "manual_required": False,
                    "ai_reasoning": "",
                }
            ],
            "current_task_index": 0,
            "task_execution_plan": {},
        },
        as_node="operational_planning",
    )

    # Stream until interrupt
    for _ in g.stream(None, config=cfg):
        pass

    snap = g.get_state(cfg)
    assert snap.next == ("review_task",)
    # Simulate user approve via update_state
    g.update_state(
        cfg,
        {"task_execution_plan": {"task_1": "approve"}, "current_task_index": 1},
    )
    snap2 = g.get_state(cfg)
    assert snap2.values["current_task_index"] == 1
