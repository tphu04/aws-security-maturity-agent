"""Phase I.8 — integration tests for the full Langfuse instrumentation.

These tests run the actual node bodies (with mocked agents/clients) against
an in-memory FakeLangfuse to assert the trace tree shape, redaction, score
emission and best-effort failure isolation match the design in
``docs/LANGFUSE_INTEGRATION_GUIDE.md`` §4.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pdca.config import settings
from pdca.observability import langfuse_client as lf
from pdca.observability import tracing


class FakeObservation:
    def __init__(self, **payload):
        self.payload = dict(payload)
        self.updates: list[dict] = []
        self.events: list[dict] = []
        self.id = f"obs-{id(self)}"
        self.ended = False

    def update(self, **kwargs):
        self.updates.append(kwargs)

    def event(self, **kwargs):
        self.events.append(kwargs)

    def end(self):
        self.ended = True


class FakeManager:
    def __init__(self, obs):
        self.obs = obs

    def __enter__(self):
        return self.obs

    def __exit__(self, exc_type, exc, tb):
        self.obs.end()
        return False


class FakeLangfuse:
    """Minimal stand-in for SDK v3 Langfuse client used by the tracing layer."""

    def __init__(self):
        self.spans: list[FakeObservation] = []
        self.scores: list[dict] = []
        self.flushed = 0
        self.trace_updates: list[dict] = []

    def start_as_current_span(self, *, trace_context=None, name, input=None, metadata=None):
        obs = FakeObservation(
            trace_context=trace_context,
            name=name,
            input=input,
            metadata=metadata,
        )
        self.spans.append(obs)
        return FakeManager(obs)

    def update_current_trace(self, **payload):
        self.trace_updates.append(payload)

    def create_score(self, *, trace_id, name, value, comment=None):
        self.scores.append(
            {"trace_id": trace_id, "name": name, "value": value, "comment": comment}
        )

    def flush(self):
        self.flushed += 1


@pytest.fixture
def fake_lf(monkeypatch):
    client = FakeLangfuse()
    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_flush_at_node", True)
    monkeypatch.setattr(lf, "_langfuse", client)
    monkeypatch.setattr("pdca.observability.tracing.get_langfuse_client", lambda: client)
    monkeypatch.setattr(
        "pdca.observability.langfuse_client.get_langfuse_client", lambda: client
    )
    yield client
    lf._reset_for_tests()


# ---------------------------------------------------------------------------
# Trace topology
# ---------------------------------------------------------------------------


def test_environment_node_emits_node_span_and_redacted_metadata(fake_lf, monkeypatch):
    from pdca.graph.nodes import environment as env_node

    fake_agent = MagicMock()
    fake_agent.get_aws_context.return_value = {
        "account_id": "123456789012",
        "region": "ap-southeast-1",
        "identity_arn": "arn:aws:iam::123456789012:user/admin",
        "buckets": ["company-prod-data"],
    }
    fake_rag = MagicMock()
    fake_rag.is_healthy.return_value = True

    monkeypatch.setattr(env_node, "EnvironmentAgent", lambda: fake_agent)
    monkeypatch.setattr(env_node, "RAGClient", lambda **kw: fake_rag)

    from pdca.observability.tracing import start_trace
    with start_trace("run-env"):
        out = env_node.environment_node(
            {"run_id": "run-env", "performance_metrics": {}}, {}
        )

    assert out["aws_context"]["account_id"] == "123456789012"  # state untouched
    node_span = next(s for s in fake_lf.spans if s.payload["name"] == "node:environment")
    # account_id must be masked everywhere we send to Langfuse — root span
    # metadata updates + any per-span output payloads.
    all_payloads = " ".join(
        [str(s.payload) for s in fake_lf.spans]
        + [str(u) for s in fake_lf.spans for u in s.updates]
        + [str(u) for u in fake_lf.trace_updates]
    )
    assert "123456789012" not in all_payloads
    assert "***9012" in all_payloads
    assert node_span.ended


def test_planning_node_emits_score_when_top_score_present(fake_lf, monkeypatch):
    from pdca.graph.nodes import planning

    fake_agent = MagicMock()
    fake_agent.run.return_value = {
        "groups_to_scan": ["s3"],
        "checks_to_scan": ["check1", "check2"],
        "fast_track": True,
        "top_score": 0.42,
        "confidence": "high",
    }
    monkeypatch.setattr(planning, "PlanningAgent", lambda **kw: fake_agent)
    monkeypatch.setattr(planning, "RAGClient", lambda **kw: MagicMock())
    monkeypatch.setattr(planning, "save_scan_configuration", lambda *a, **kw: None)

    planning.planning_node(
        {
            "run_id": "run-plan",
            "user_request": "scan s3",
            "performance_metrics": {},
            "rag_available": True,
        },
        {},
    )

    scores = [s for s in fake_lf.scores if s["name"] == "planning_top_score"]
    assert scores, "planning_top_score must be emitted"
    assert scores[0]["value"] == pytest.approx(0.42)


def test_risk_eval_emits_severity_scores_and_subspans(fake_lf, monkeypatch):
    from pdca.graph.nodes import risk_eval

    fake_agent = MagicMock()
    fake_agent.run.return_value = [
        {"severity": "Critical", "ai_severity": "critical"},
        {"severity": "Critical", "ai_severity": "critical"},
        {"severity": "High", "ai_severity": "high"},
    ]
    fake_agent.get_llm_metrics.return_value = {}
    monkeypatch.setattr(risk_eval, "RiskEvaluationAgent", lambda *a, **kw: fake_agent)
    monkeypatch.setattr(risk_eval, "RAGClient", lambda **kw: MagicMock())

    risk_eval.risk_eval_node(
        {
            "run_id": "run-risk",
            "raw_findings": [],
            "normalized_findings": [],
            "performance_metrics": {},
        },
        {},
    )

    score_names = [s["name"] for s in fake_lf.scores]
    assert "risk_severity_critical" in score_names
    assert "risk_severity_high" in score_names
    crit_score = next(s for s in fake_lf.scores if s["name"] == "risk_severity_critical")
    assert crit_score["value"] == 2.0


def test_hitl_wait_span_records_decision_and_latency(fake_lf, monkeypatch):
    from pdca import orchestrator as orch
    from pdca.tools.registry import REGISTRY as ToolRegistry

    fake_app = MagicMock()
    snapshot = MagicMock()
    snapshot.values = {
        "run_id": "run-hitl",
        "current_task_index": 0,
        "remediation_tasks": [
            {
                "task_id": "t1",
                "tool_name": "noop",
                "tool_params": {},
                "finding_id": "f1",
                "manual_required": False,
            }
        ],
        "prioritized_findings": [],
        "task_execution_plan": {},
        "_langfuse_trace_id": "12345678-1234-4abc-9def-1234567890ae",
        "_langfuse_parent_span_id": "obs-parent",
    }
    fake_app.get_state.return_value = snapshot

    monkeypatch.setattr(ToolRegistry, "get", lambda name: None)
    monkeypatch.setattr("builtins.input", lambda *_a, **_kw: "y")

    orch.handle_task_review_interaction(fake_app, {})

    hitl_span = next(s for s in fake_lf.spans if s.payload["name"] == "hitl:wait")
    assert hitl_span.payload["trace_context"] == {
        "trace_id": "1234567812344abc9def1234567890ae",
        "parent_span_id": "obs-parent",
    }
    decision_update = next(
        u for u in hitl_span.updates if u.get("output", {}).get("decision") == "approve"
    )
    assert "latency_human_ms" in decision_update["output"]
    fake_app.update_state.assert_called_once()


def test_remediation_node_persists_langfuse_parent_before_interrupt(fake_lf, monkeypatch):
    from pdca.graph.nodes import remediation
    from pdca.observability.tracing import start_trace

    fake_planner = MagicMock()
    fake_planner.plan_remediation.return_value = []
    fake_planner.get_llm_metrics.return_value = {}
    monkeypatch.setattr(
        remediation,
        "RemediationPlannerAgent",
        lambda *a, **kw: fake_planner,
    )

    with start_trace("12345678-1234-4abc-9def-1234567890af"):
        out = remediation.remediation_node(
            {
                "run_id": "12345678-1234-4abc-9def-1234567890af",
                "performance_metrics": {},
                "aws_context": {},
                "prioritized_findings": [],
            },
            {},
        )

    assert out["_langfuse_parent_span_id"]
    assert out["_langfuse_trace_id"] == "12345678-1234-4abc-9def-1234567890af"


def test_pipeline_continues_when_langfuse_handler_raises(monkeypatch):
    """Failure injection — Langfuse handler raising must not break pipeline."""

    class ExplodingClient:
        def start_as_current_span(self, **kwargs):
            raise RuntimeError("network down")

        def flush(self):
            raise RuntimeError("flush down")

    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(lf, "_langfuse", ExplodingClient())
    monkeypatch.setattr(
        "pdca.observability.tracing.get_langfuse_client", lambda: ExplodingClient()
    )
    monkeypatch.setattr(
        "pdca.observability.langfuse_client.get_langfuse_client",
        lambda: ExplodingClient(),
    )

    # Span call must not raise — ContextManager yields a NoopSpan.
    with tracing.span("test-op", input={"x": 1}) as sp:
        sp.update(output={"ok": True})  # also no-op

    # Score helper must swallow as well.
    lf.score_safe(trace_id="t", name="x", value=1.0)
    lf._reset_for_tests()
