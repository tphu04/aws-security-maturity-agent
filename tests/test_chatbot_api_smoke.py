"""Smoke test for the Chatbot API (Phase D-web).

Verifies the FastAPI surface without spawning the real LangGraph runtime
(no Prowler scanner, no Ollama, no AWS calls). Mocks `pdca.api.graph_runtime`
+ `pdca.api.chatbot._probe_aws/_probe_rag` so the test runs offline.

Goals:
- POST /v1/runs returns a run_id + thread_id
- GET /v1/runs/{id} produces a RunSession-shaped dict via the adapter
- HITL flow: POST /approvals returns 409 when not waiting; 200 when waiting
- Error responses for unknown run_id
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient


# ─── Fixtures ─────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _mock_aws_and_rag(monkeypatch):
    """Stub AWS + RAG probes so tests are offline + fast."""
    from pdca.api import chatbot

    monkeypatch.setattr(chatbot, "_probe_aws", lambda: {
        "status": "connected", "accountMask": "1234••••••12",
        "region": "us-east-1", "credentialType": "Profile: test",
        "bucketsDiscovered": 3,
    })
    monkeypatch.setattr(chatbot, "_probe_rag", lambda: True)
    chatbot._ENV_CACHE["value"] = None
    chatbot._ENV_CACHE["ts"] = 0.0
    yield
    chatbot._ENV_CACHE["value"] = None
    chatbot._ENV_CACHE["ts"] = 0.0


@pytest.fixture
def fake_runtime(monkeypatch):
    """Replace `pdca.api.graph_runtime` calls used by chatbot endpoints with
    in-memory fakes. Provides a tiny state machine that mimics LangGraph."""
    from pdca.api import chatbot

    runs: Dict[str, Dict[str, Any]] = {}

    def _start_run(prompt: str, scope, group: str) -> Dict[str, str]:
        run_id = f"run_test_{len(runs):03d}"
        runs[run_id] = {
            "values": {
                "run_id": run_id,
                "user_request": prompt,
                "aws_context": {"account_id": "111122223333", "region": "us-east-1", "buckets": []},
                "rag_available": True,
                "remediation_tasks": [
                    {"task_id": "t1", "finding_id": "f1", "tool_name": "fix_a",
                     "tool_params": {"x": 1}, "ai_reasoning": "fix it"},
                ],
                "task_execution_plan": {},
                "current_task_index": 0,
                "prioritized_findings": [
                    {"finding_id": "f1", "finding_uid": "uid_f1",
                     "event_code": "s3_bucket_public", "service": "s3",
                     "resource_id": "bucket-x", "region": "us-east-1",
                     "status": "FAIL", "severity": "high", "description": "public"},
                ],
            },
            "next": ["review_task"],
            "checkpoint_ts": None,
        }
        return {"run_id": run_id, "thread_id": run_id}

    def _get_state_values(run_id: str):
        return runs.get(run_id)

    def _get_state_history(run_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return []

    def _list_run_ids() -> List[str]:
        return list(runs.keys())

    def _get_run_metadata(run_id: str):
        return {"prompt": "test", "scope": None, "group": "s3", "started_at": 0}

    def _resume_after_decision(run_id: str, task_id: str, decision: str) -> bool:
        snap = runs.get(run_id)
        if not snap:
            return False
        if "review_task" not in snap["next"]:
            return False
        # Advance the index, drop interrupt → simulate END.
        snap["values"]["task_execution_plan"][task_id] = (
            "approve" if decision in ("approved", "approve") else "skip"
        )
        snap["values"]["current_task_index"] += 1
        snap["next"] = []  # END
        snap["values"]["execution_logs"] = [
            {"task_id": task_id, "tool_name": "fix_a", "status": "success", "duration": 0.5}
        ]
        snap["values"]["verification_results"] = [
            {"finding_id": "f1", "finding_uid": "uid_f1",
             "before_status": "FAIL", "after_status": "PASS",
             "change": "Fixed", "tool_name": "fix_a"},
        ]
        return True

    monkeypatch.setattr(chatbot, "start_run", _start_run)
    monkeypatch.setattr(chatbot, "get_state_values", _get_state_values)
    monkeypatch.setattr(chatbot, "get_state_history", _get_state_history)
    monkeypatch.setattr(chatbot, "list_run_ids", _list_run_ids)
    monkeypatch.setattr(chatbot, "get_run_metadata", _get_run_metadata)
    monkeypatch.setattr(chatbot, "resume_after_decision", _resume_after_decision)

    return runs


@pytest.fixture
def client(fake_runtime):
    from pdca.api.chatbot import app
    # Avoid actually building the graph in the startup hook.
    app.router.on_startup.clear()
    return TestClient(app)


# ─── Tests ────────────────────────────────────────────────────────────────
def test_environment_endpoint(client):
    r = client.get("/v1/environment")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "connected"
    assert body["region"] == "us-east-1"
    assert body["bucketsDiscovered"] == 3
    assert body["ragAvailable"] is True
    assert body["accountMask"].startswith("1234")


def test_create_run_returns_ids(client):
    r = client.post("/v1/runs", json={"prompt": "scan s3", "scope": "S3 only"})
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"].startswith("run_test_")
    assert body["thread_id"] == body["run_id"]


def test_get_run_returns_run_session_shape(client):
    rid = client.post("/v1/runs", json={"prompt": "scan s3"}).json()["run_id"]
    r = client.get(f"/v1/runs/{rid}")
    assert r.status_code == 200
    rs = r.json()
    # RunSession must have these top-level keys.
    expected_keys = {
        "id", "threadId", "status", "currentNode", "awsEnvironment",
        "graphNodes", "scanJobs", "toolCalls", "evidence", "findings",
        "remediationTasks", "executionLogs", "verifications", "messages",
        "report", "ragBundle",
    }
    assert expected_keys.issubset(rs.keys()), f"missing: {expected_keys - rs.keys()}"
    assert rs["id"] == rid
    assert rs["status"] == "waiting_for_approval"
    assert rs["currentNode"] == "review_task"
    assert len(rs["remediationTasks"]) == 1
    assert rs["remediationTasks"][0]["decision"] == "pending"


def test_unknown_run_returns_404(client):
    r = client.get("/v1/runs/run_does_not_exist")
    assert r.status_code == 404


def test_approval_advances_run_and_completes(client):
    rid = client.post("/v1/runs", json={"prompt": "scan s3"}).json()["run_id"]
    # Verify waiting state.
    rs = client.get(f"/v1/runs/{rid}").json()
    assert rs["status"] == "waiting_for_approval"

    # POST decision.
    r = client.post(f"/v1/runs/{rid}/approvals/t1", json={"decision": "approved"})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Now run should reach completion (fake_runtime pushes to END).
    rs = client.get(f"/v1/runs/{rid}").json()
    assert rs["status"] == "completed"
    assert rs["remediationTasks"][0]["decision"] == "approved"
    assert rs["findings"][0]["remediationStatus"] == "remediated"
    assert rs["verifications"][0]["result"] == "passed"


def test_approval_rejected_when_not_waiting(client):
    rid = client.post("/v1/runs", json={"prompt": "scan s3"}).json()["run_id"]
    # First approval succeeds, drives to END.
    client.post(f"/v1/runs/{rid}/approvals/t1", json={"decision": "approved"})
    # Second approval should 409 — graph no longer waiting.
    r = client.post(f"/v1/runs/{rid}/approvals/t1", json={"decision": "approved"})
    assert r.status_code == 409


def test_invalid_decision_rejected(client):
    rid = client.post("/v1/runs", json={"prompt": "scan s3"}).json()["run_id"]
    # FastAPI validator rejects bad enum at 422.
    r = client.post(f"/v1/runs/{rid}/approvals/t1", json={"decision": "maybe"})
    assert r.status_code == 422


def test_list_runs_includes_active(client):
    client.post("/v1/runs", json={"prompt": "scan s3"})
    client.post("/v1/runs", json={"prompt": "scan iam"})
    r = client.get("/v1/runs?limit=10")
    assert r.status_code == 200
    items = r.json()["items"]
    run_items = [i for i in items if i["kind"] == "run"]
    assert len(run_items) >= 2


def test_report_not_ready_returns_409(client):
    rid = client.post("/v1/runs", json={"prompt": "scan s3"}).json()["run_id"]
    r = client.get(f"/v1/runs/{rid}/report")
    # No final_report path in fake state → 409 not ready.
    assert r.status_code == 409
