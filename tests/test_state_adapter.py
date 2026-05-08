"""Unit tests for `pdca.api.state_adapter` — pure-function adapter.

Covers:
- Status derivation from `snapshot.next`.
- Partial state at each phase produces a valid RunSession.
- HITL interrupt state surfaces as `waiting_for_approval`.
- Completed run with verifications produces correct evidence + remediation
  status per finding.
- Strip private (`_*`) keys.
"""

from __future__ import annotations

import pytest

from pdca.api.state_adapter import to_run_session, _split_markdown_sections


# ─── Helpers ──────────────────────────────────────────────────────────────
def _snapshot(values: dict, next_nodes: list[str] | None = None) -> dict:
    return {"values": values, "next": next_nodes or [], "checkpoint_ts": None}


def _finding(fid: str, status: str = "FAIL", severity: str = "high",
             check_id: str = "s3_bucket_public_access") -> dict:
    return {
        "finding_id": fid,
        "finding_uid": f"uid_{fid}",
        "event_code": check_id,
        "service": "s3",
        "resource_id": f"bucket-{fid}",
        "region": "us-east-1",
        "status": status,
        "severity": severity,
        "description": f"finding {fid} description",
    }


# ─── Status derivation ────────────────────────────────────────────────────
def test_idle_when_environment_pending():
    rs = to_run_session("run_1", _snapshot({"run_id": "run_1"}, ["environment"]), [])
    assert rs["status"] == "validating_environment"
    assert rs["currentNode"] == "environment"


def test_polling_status():
    rs = to_run_session(
        "run_1",
        _snapshot({"run_id": "run_1", "pending_jobs": {"j1": {"status": "pending"}}},
                  ["scan_poll"]),
        [],
    )
    assert rs["status"] == "polling"


def test_waiting_for_approval():
    state = {
        "run_id": "run_1",
        "remediation_tasks": [
            {"task_id": "t1", "finding_id": "f1", "tool_name": "x", "tool_params": {}},
        ],
        "task_execution_plan": {},
        "current_task_index": 0,
    }
    rs = to_run_session("run_1", _snapshot(state, ["review_task"]), [])
    assert rs["status"] == "waiting_for_approval"
    assert rs["currentNode"] == "review_task"
    assert rs["remediationTasks"][0]["decision"] == "pending"


def test_completed_no_errors():
    rs = to_run_session("run_1", _snapshot({"run_id": "run_1", "errors": []}, []), [])
    assert rs["status"] == "completed"


def test_failed_when_errors_and_no_next():
    rs = to_run_session(
        "run_1",
        _snapshot({"run_id": "run_1", "errors": [{"msg": "boom"}]}, []),
        [],
    )
    assert rs["status"] == "failed"


# ─── AWS environment mapping ──────────────────────────────────────────────
def test_aws_account_masked():
    state = {
        "run_id": "run_1",
        "aws_context": {"account_id": "123456789012", "region": "ap-southeast-1", "buckets": ["a", "b"]},
        "rag_available": True,
    }
    rs = to_run_session("run_1", _snapshot(state, ["planning"]), [])
    env = rs["awsEnvironment"]
    assert env["accountMask"].startswith("1234")
    assert env["accountMask"].endswith("12")
    assert "•" in env["accountMask"]
    assert env["region"] == "ap-southeast-1"
    assert env["bucketsDiscovered"] == 2
    assert env["ragAvailable"] is True


def test_aws_not_connected_when_no_account():
    rs = to_run_session("run_1", _snapshot({"run_id": "run_1"}, ["environment"]), [])
    assert rs["awsEnvironment"]["status"] == "not_connected"
    assert rs["awsEnvironment"]["accountMask"] == "————"


# ─── Findings + evidence wiring ───────────────────────────────────────────
def test_findings_with_evidence_for_fail():
    f1 = _finding("f1", status="FAIL")
    f2 = _finding("f2", status="PASS")
    state = {"run_id": "run_1", "prioritized_findings": [f1, f2]}
    rs = to_run_session("run_1", _snapshot(state, ["operational_planning"]), [])
    findings = rs["findings"]
    assert len(findings) == 2
    fail_finding = next(f for f in findings if f["status"] == "FAIL")
    assert len(fail_finding["evidenceIds"]) == 1
    assert fail_finding["evidenceIds"][0].startswith("ev_f_")
    pass_finding = next(f for f in findings if f["status"] == "PASS")
    assert pass_finding["evidenceIds"] == []  # no evidence for PASS


def test_finding_severity_lowercased():
    f = _finding("f1", severity="HIGH")
    rs = to_run_session("run_1", _snapshot({"run_id": "run_1", "prioritized_findings": [f]}, ["report"]), [])
    assert rs["findings"][0]["severity"] == "high"


# ─── Remediation tasks ────────────────────────────────────────────────────
def test_remediation_task_decision_mapping():
    tasks = [
        {"task_id": "t1", "finding_id": "f1", "tool_name": "tool_a", "tool_params": {"x": 1}},
        {"task_id": "t2", "finding_id": "f2", "tool_name": "tool_b", "tool_params": {}},
        {"task_id": "t3", "finding_id": "f3", "tool_name": "tool_c", "tool_params": {},
         "manual_required": True},
    ]
    state = {
        "run_id": "run_1",
        "remediation_tasks": tasks,
        "task_execution_plan": {"t1": "approve", "t2": "skip"},
        "prioritized_findings": [_finding("f1"), _finding("f2"), _finding("f3")],
    }
    rs = to_run_session("run_1", _snapshot(state, ["review_task"]), [])
    by_id = {t["id"]: t for t in rs["remediationTasks"]}
    assert by_id["t1"]["decision"] == "approved"
    assert by_id["t2"]["decision"] == "rejected"
    assert by_id["t3"]["decision"] == "manual_required"
    assert by_id["t3"]["manualOnly"] is True
    assert by_id["t3"]["guardChecks"]["notManualOnly"] is False


# ─── Verifications + remediation status ──────────────────────────────────
def test_completed_run_verifications():
    state = {
        "run_id": "run_1",
        "prioritized_findings": [_finding("f1"), _finding("f2")],
        "remediation_tasks": [
            {"task_id": "t1", "finding_id": "f1", "tool_name": "fix_1", "tool_params": {}},
            {"task_id": "t2", "finding_id": "f2", "tool_name": "fix_2", "tool_params": {}},
        ],
        "task_execution_plan": {"t1": "approve", "t2": "approve"},
        "execution_logs": [
            {"task_id": "t1", "tool_name": "fix_1", "status": "success", "duration": 1.5},
            {"task_id": "t2", "tool_name": "fix_2", "status": "failed", "duration": 0.3},
        ],
        "verification_results": [
            {"finding_uid": "uid_f1", "finding_id": "f1", "before_status": "FAIL",
             "after_status": "PASS", "change": "Fixed", "tool_name": "fix_1"},
            {"finding_uid": "uid_f2", "finding_id": "f2", "before_status": "FAIL",
             "after_status": "FAIL", "change": "RemediationFailed", "tool_name": "fix_2"},
        ],
    }
    rs = to_run_session("run_1", _snapshot(state, []), [])
    assert rs["status"] == "completed"
    by_id = {f["id"]: f for f in rs["findings"]}
    assert by_id["f1"]["remediationStatus"] == "remediated"
    assert by_id["f2"]["remediationStatus"] == "failed"
    vers = rs["verifications"]
    assert len(vers) == 2
    assert any(v["result"] == "passed" for v in vers)
    assert any(v["result"] == "failed" for v in vers)


# ─── Scan jobs ────────────────────────────────────────────────────────────
def test_scan_jobs_merge_pending_completed():
    state = {
        "run_id": "run_1",
        "pending_jobs": {"job_b": {"task_type": "checks", "task_value": "s3_x", "status": "running"}},
        "completed_jobs": {"job_a": {"task_type": "group", "task_value": "s3", "status": "completed"}},
        "scan_started_at": 1000.0,
    }
    rs = to_run_session("run_1", _snapshot(state, ["scan_poll"]), [])
    by_id = {j["id"]: j for j in rs["scanJobs"]}
    assert by_id["job_a"]["status"] == "completed"
    assert by_id["job_a"]["taskType"] == "group"
    assert by_id["job_b"]["status"] == "running"
    assert by_id["job_b"]["taskType"] == "checks"


# ─── RAG bundle passthrough ───────────────────────────────────────────────
def test_rag_bundle_camelcased_keys():
    state = {
        "run_id": "run_1",
        "rag_bundle": {
            "capability_themes": [{"domain": "s3", "narrative": "..."}],
            "remediation_guides": [{"check_id": "x", "steps": []}],
            "control_mappings": {"x": {"nist": ["AC-3"]}},
            "confidence": "high",
        },
    }
    rs = to_run_session("run_1", _snapshot(state, ["operational_planning"]), [])
    bundle = rs["ragBundle"]
    assert bundle is not None
    assert bundle["confidence"] == "high"
    assert len(bundle["capabilityThemes"]) == 1
    assert len(bundle["remediationGuides"]) == 1
    assert "x" in bundle["controlMappings"]


def test_rag_bundle_none_when_absent():
    rs = to_run_session("run_1", _snapshot({"run_id": "run_1"}, ["scan_poll"]), [])
    assert rs["ragBundle"] is None


# ─── Strip private fields ─────────────────────────────────────────────────
def test_private_fields_stripped():
    state = {
        "run_id": "run_1",
        "_langfuse_trace_id": "should not leak",
        "_langfuse_parent_span_id": "should not leak",
        "aws_context": {"account_id": "1", "region": "us-east-1", "buckets": [],
                         "_degraded": False},
    }
    rs = to_run_session("run_1", _snapshot(state, ["planning"]), [])
    flat = str(rs)
    assert "_langfuse_trace_id" not in flat
    assert "_langfuse_parent_span_id" not in flat


# ─── Markdown section parser ──────────────────────────────────────────────
def test_split_markdown_sections_simple():
    md = """\
# Title

intro text

## Executive Summary

body 1

## Findings

body 2"""
    sections = _split_markdown_sections(md)
    titles = [s["title"] for s in sections]
    assert "Cover" in titles
    assert "Executive Summary" in titles
    assert "Findings" in titles


def test_split_markdown_sections_no_headings():
    sections = _split_markdown_sections("just plain text without headings")
    assert len(sections) == 1
    assert sections[0]["title"] == "Cover"
