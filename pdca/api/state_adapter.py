"""PDCAState → RunSession adapter — Phase D-web.

Pure translation layer between LangGraph runtime state and the Frontend's
canonical `RunSession` shape (see Frontend/src/types/pdca.ts).

Design:
- Pure function: same input → same output. No HTTP, no DB, no Langfuse.
  The only I/O is reading the final_report markdown file (if present).
- Tolerant of partial state: every field uses .get() defaults so a snapshot
  taken mid-run still produces a valid RunSession.
- Strips private fields (`_*`) before returning, recursively (1 level deep
  is enough — PDCAState only has `_langfuse_*` at top level).
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from pdca.observability.logger import get_logger
from pdca.tools import REGISTRY

logger = get_logger("pdca.api.state_adapter")


# ---------------------------------------------------------------------------
# Status derivation — snapshot.next[0] → FE RunStatus
# ---------------------------------------------------------------------------
_NEXT_TO_STATUS: Dict[str, str] = {
    "environment": "validating_environment",
    "planning": "planning",
    "scan_submit": "submitting_scan",
    "scan_poll": "polling",
    "scan_collect": "collecting_findings",
    "risk_evaluation": "evaluating_risk",
    "rag_enrich": "evaluating_risk",       # FE groups with risk
    "operational_planning": "evaluating_risk",
    "review_task": "waiting_for_approval",
    "reset_index": "executing_remediation",
    "execution": "executing_remediation",
    "verification": "verifying",
    "report": "generating_report",
}


def _derive_status(values: Dict[str, Any], next_nodes: List[str]) -> Tuple[str, str]:
    """Return (status, currentNode).

    - If `next_nodes` non-empty: about-to-run node drives the status.
    - If `next_nodes` empty: graph reached END → check errors → completed/failed.
    """
    if values.get("cancelled"):
        return ("cancelled", "scan_poll")
    errors = values.get("errors") or []
    if not next_nodes:
        if errors:
            return ("failed", "report")
        return ("completed", "report")
    head = next_nodes[0]
    return (_NEXT_TO_STATUS.get(head, "idle"), head)


# ---------------------------------------------------------------------------
# AWS environment
# ---------------------------------------------------------------------------
def _mask_account(account_id: Optional[str]) -> str:
    if not account_id:
        return "————"
    s = str(account_id)
    if len(s) < 6:
        return s
    return s[:4] + "•" * (len(s) - 6) + s[-2:]


def _aws_environment(values: Dict[str, Any]) -> Dict[str, Any]:
    ctx = values.get("aws_context") or {}
    rag_available = bool(values.get("rag_available", False))
    status = "connected"
    if ctx.get("_degraded"):
        status = "error"
    elif not ctx.get("account_id"):
        status = "not_connected"
    return {
        "status": status,
        "accountMask": _mask_account(ctx.get("account_id")),
        "region": ctx.get("region", ""),
        "credentialType": "Profile",  # actual type lives in env probe; placeholder
        "lastValidatedAt": "",         # filled by chatbot.py from environment cache
        "bucketsDiscovered": len(ctx.get("buckets") or []),
        "ragAvailable": rag_available,
    }


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------
def _humanize_check_id(check_id: str) -> str:
    """Turn `s3_bucket_acl_prohibited` → `S3 Bucket Acl Prohibited`. Used as
    a last-resort title when the source has no friendlier description."""
    if not check_id:
        return ""
    parts = re.split(r"[_\-]+", str(check_id).strip())
    out: List[str] = []
    for p in parts:
        if not p:
            continue
        # Keep all-caps acronyms (s3, vpc, kms, iam) uppercase.
        if len(p) <= 3 and p.isalpha():
            out.append(p.upper())
        else:
            out.append(p[:1].upper() + p[1:])
    return " ".join(out)


def _friendly_title(f: Dict[str, Any], check_id: str) -> str:
    """Pick the most human-readable title available.

    Priority: rag_title (curated) → description → humanized check_id. Skip
    sources that just echo `check_id` so the FE doesn't render the raw key.
    """
    candidates = [
        str(f.get("rag_title") or "").strip(),
        str(f.get("title") or "").strip(),
        str(f.get("description") or "").strip(),
    ]
    cid = str(check_id or "").strip()
    for c in candidates:
        if c and c != cid:
            return c
    return _humanize_check_id(cid) or cid or "Unknown check"


def _findings(values: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Prefer prioritized_findings (richer — risk score, RAG enrichment) over
    normalized_findings. Both share the base shape from `normalize_finding`."""
    src = values.get("prioritized_findings") or values.get("normalized_findings") or []
    out: List[Dict[str, Any]] = []
    for f in src:
        check_id = (
            f.get("event_code")
            or f.get("check_id")
            or (f.get("metadata") or {}).get("event_code")
            or "unknown_check"
        )
        out.append({
            "id": str(f.get("finding_id") or f.get("finding_uid") or check_id),
            "prowlerCheckId": str(check_id),
            "service": str(f.get("service") or "aws"),
            "resource": str(f.get("resource_id") or f.get("resource") or "unknown"),
            "region": str(f.get("region") or ""),
            "title": _friendly_title(f, str(check_id)),
            "description": str(f.get("description") or ""),
            "severity": str(f.get("severity") or "info").lower(),
            "status": str(f.get("status") or "MANUAL").upper(),
            "remediationStatus": _remediation_status(f, values),
            "recommendation": str(
                f.get("remediation_recommendation")
                or f.get("recommendation")
                or ""
            ),
            "evidenceIds": [],   # populated below in _evidence()
            # RAG enrichment passthrough (FE renders if present):
            "compliance": f.get("compliance") or [],
            "controlMappings": f.get("control_mappings") or {},
            "remediationGuide": f.get("remediation_guide") or None,
            "remediationUrl": f.get("remediation_url") or "",
            "ragTitle": f.get("rag_title") or "",
            "riskFromRag": f.get("risk_from_rag") or "",
        })
    return out


def _remediation_status(finding: Dict[str, Any], values: Dict[str, Any]) -> str:
    """Compute per-finding remediation status from execution_logs + verifications."""
    fid = finding.get("finding_id") or finding.get("finding_uid")
    if not fid:
        return "open"
    # Manual override?
    for t in values.get("remediation_tasks", []) or []:
        if t.get("finding_id") == fid and t.get("manual_required"):
            return "manual"
    # Verification result wins (post-rescan diff).
    for v in values.get("verification_results", []) or []:
        if v.get("finding_uid") == fid or v.get("finding_id") == fid:
            chg = str(v.get("change") or "").lower()
            if "fixed" in chg:
                return "remediated"
            if "manual" in chg:
                return "manual"
            if "fail" in chg or "error" in chg:
                return "failed"
    # Execution log fallback (not yet verified).
    task_ids = {
        t.get("task_id")
        for t in values.get("remediation_tasks", []) or []
        if t.get("finding_id") == fid
    }
    for log in values.get("execution_logs", []) or []:
        if log.get("task_id") in task_ids:
            s = str(log.get("status") or "").lower()
            if s == "success":
                return "remediated"
            if s in ("failed", "error"):
                return "failed"
    return "open"


# ---------------------------------------------------------------------------
# Scan jobs (FE shape from pending_jobs ∪ completed_jobs)
# ---------------------------------------------------------------------------
def _scan_jobs(values: Dict[str, Any]) -> List[Dict[str, Any]]:
    pending = values.get("pending_jobs") or {}
    completed = values.get("completed_jobs") or {}
    out: List[Dict[str, Any]] = []
    seen: set = set()
    started_at_iso = _epoch_to_iso(values.get("scan_started_at"))
    for job_id, meta in {**pending, **completed}.items():
        if job_id in seen:
            continue
        seen.add(job_id)
        task_type = meta.get("task_type") or "group"
        # FE union: "group" | "checks" | "custom"
        if task_type not in ("group", "checks", "custom"):
            task_type = "group"
        api_endpoint = (
            "POST /v1/scan/group" if task_type == "group"
            else "POST /v1/scan/checks" if task_type == "checks"
            else "POST /v1/scan/custom"
        )
        finished_at_iso = _epoch_to_iso(meta.get("completed_at"))
        entry = {
            "id": job_id,
            "apiEndpoint": api_endpoint,
            "httpMethod": "POST",
            "taskType": task_type,
            "taskValue": meta.get("task_value", ""),
            "status": _scan_job_status(meta.get("status")),
            "submittedAt": started_at_iso or "",
        }
        if finished_at_iso:
            entry["finishedAt"] = finished_at_iso
        out.append(entry)
    return out


def _scan_job_status(s: Optional[str]) -> str:
    s = (s or "pending").lower()
    if s in ("pending", "running", "completed", "failed", "timeout", "cancelled"):
        return s
    if s == "max_iterations":
        return "timeout"
    return "pending"


# ---------------------------------------------------------------------------
# Remediation tasks
# ---------------------------------------------------------------------------
def _remediation_tasks(values: Dict[str, Any]) -> List[Dict[str, Any]]:
    tasks = values.get("remediation_tasks") or []
    plan = values.get("task_execution_plan") or {}
    findings_by_id = {
        (f.get("finding_id") or f.get("finding_uid")): f
        for f in (values.get("prioritized_findings") or values.get("normalized_findings") or [])
    }
    out: List[Dict[str, Any]] = []
    for t in tasks:
        tid = t.get("task_id")
        fid = t.get("finding_id")
        tool_name = t.get("tool_name") or ""
        finding = findings_by_id.get(fid) or {}
        decision_raw = plan.get(tid, "pending")
        decision = (
            "approved" if decision_raw == "approve"
            else "rejected" if decision_raw in ("reject", "rejected")
            else "skipped" if decision_raw in ("skip", "skipped")
            else "manual_required" if t.get("manual_required")
            else "pending"
        )
        guide = finding.get("remediation_guide") or {}

        # guardChecks — computed from REGISTRY (single source of truth)
        tool_meta = REGISTRY.meta(tool_name)
        guard_checks = {
            "registeredTool": tool_meta is not None,
            "isRemediationCategory": tool_meta is not None and tool_meta.category == "remediation",
            "notManualOnly": tool_meta is not None and not tool_meta.manual_only,
        }

        # ai_reasoning: planner stores it as "reasoning" key in task dict
        ai_reasoning = t.get("ai_reasoning") or t.get("reasoning") or t.get("description") or ""
        # expectedImpact — prefer explicit LLM-generated field, fallback to first sentence of reasoning
        expected_impact = t.get("expected_impact") or ""
        if not expected_impact and ai_reasoning:
            first_sentence = ai_reasoning.split(".")[0].strip()
            expected_impact = first_sentence + "." if first_sentence else ""

        out.append({
            "id": tid,
            "findingId": fid,
            "findingTitle": finding.get("title") or finding.get("description", "")[:80],
            "severity": str(finding.get("severity") or "info").lower(),
            "resource": str(finding.get("resource_id") or finding.get("resource") or ""),
            "toolName": tool_name,
            "toolCategory": "remediation",
            "manualOnly": bool(t.get("manual_required", False)),
            "proposedAction": ai_reasoning,
            "expectedImpact": expected_impact,
            "requiredAwsPermission": t.get("required_permission") or "",
            "manualGuidance": t.get("manual_guidance") or "",
            "decision": decision,
            "toolParams": t.get("tool_params") or {},
            "guardChecks": guard_checks,
            "ragSteps": guide.get("steps") or [],
            "ragEffort": guide.get("effort") or "medium",
            "ragSideEffects": guide.get("side_effects") or [],
            "ragRollback": guide.get("rollback"),
            "compliance": finding.get("compliance") or [],
        })
    return out


# ---------------------------------------------------------------------------
# Execution logs
# ---------------------------------------------------------------------------
def _execution_logs(values: Dict[str, Any]) -> List[Dict[str, Any]]:
    logs = values.get("execution_logs") or []
    out: List[Dict[str, Any]] = []
    for log in logs:
        ts = log.get("timestamp") or log.get("ended_at") or log.get("started_at") or ""
        msg = log.get("output")
        if isinstance(msg, dict):
            import json as _json
            msg = _json.dumps(msg)[:300]
        elif msg is None:
            msg = ""
        out.append({
            "taskId": log.get("task_id"),
            "toolName": log.get("tool_name"),
            "status": str(log.get("status") or "unknown").lower(),
            "message": str(msg)[:300],
            "durationMs": int((log.get("duration") or 0) * 1000),
            "timestamp": str(ts),
        })
    return out


# ---------------------------------------------------------------------------
# Verifications — prefer analysis_results.findings_table (has populated
# `change`); fall back to verification_results (raw diff) when absent.
# ---------------------------------------------------------------------------
def _change_to_result(change: str, before: str, after: str) -> str:
    chg = str(change or "").lower()
    if "fixed" in chg:
        return "passed"
    if "manual" in chg:
        return "manual_required"
    if "fail" in chg or "error" in chg or "newissue" in chg:
        return "failed"
    if before == "PASS" and after == "PASS":
        return "passed"
    if before == "FAIL" and after == "PASS":
        return "passed"
    return "partial"


def _verifications(values: Dict[str, Any]) -> List[Dict[str, Any]]:
    analysis = values.get("analysis_results") or {}
    table = analysis.get("findings_table") or []
    diff = values.get("verification_results") or []

    # Index diff_result by (check_id, resource) so findings_table rows can
    # recover finding_id / tool_name / task_id (which the table strips).
    diff_idx: Dict[tuple, Dict[str, Any]] = {}
    for d in diff:
        key = (
            str(d.get("event_code") or "").strip(),
            str(d.get("resource_id") or d.get("resource") or "").strip(),
        )
        if key != ("", ""):
            diff_idx[key] = d

    # Index source findings by (check_id, resource) for finding_id lookup.
    finding_idx: Dict[tuple, Dict[str, Any]] = {}
    for f in (values.get("prioritized_findings") or values.get("normalized_findings") or []):
        key = (
            str(f.get("event_code") or f.get("check_id") or "").strip(),
            str(f.get("resource_id") or f.get("resource") or "").strip(),
        )
        if key != ("", ""):
            finding_idx[key] = f

    out: List[Dict[str, Any]] = []
    if table:
        for i, row in enumerate(table):
            check_id = str(row.get("check_id") or "").strip()
            resource = str(row.get("resource") or "").strip()
            key = (check_id, resource)
            d = diff_idx.get(key) or {}
            f = finding_idx.get(key) or {}
            before = str(row.get("before") or "")
            after = str(row.get("after") or "")
            result = _change_to_result(row.get("change") or "", before, after)
            out.append({
                "id": f"ver_{i:03d}",
                "findingId": (
                    d.get("finding_id")
                    or d.get("finding_uid")
                    or f.get("finding_id")
                    or f.get("finding_uid")
                    or check_id
                ),
                "resource": resource,
                "toolName": str(d.get("tool_name") or ""),
                "beforeState": before,
                "afterState": after,
                "result": result,
                "timestamp": "",
                "executionLogTaskId": d.get("task_id"),
            })
        return out

    # Fallback path — older runs / partial state without analysis_results.
    for i, v in enumerate(diff):
        before = (v.get("before") or {}).get("status") or v.get("before_status") or ""
        after = v.get("after_status") or (v.get("after") or {}).get("status") or ""
        result = _change_to_result(v.get("change") or "", before, after)
        out.append({
            "id": f"ver_{i:03d}",
            "findingId": v.get("finding_id") or v.get("finding_uid"),
            "resource": str(v.get("resource") or v.get("resource_id") or ""),
            "toolName": v.get("tool_name") or "",
            "beforeState": str(before),
            "afterState": str(after),
            "result": result,
            "timestamp": "",
            "executionLogTaskId": v.get("task_id"),
        })
    return out


# ---------------------------------------------------------------------------
# Tool calls (derive from execution_logs + scan jobs)
# ---------------------------------------------------------------------------
def _tool_calls(values: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    # Scan tools (one per submitted job).
    for job_id, meta in (values.get("completed_jobs") or {}).items():
        task_type = meta.get("task_type") or "group"
        out.append({
            "id": f"tc_{job_id}",
            "name": f"start_scan_by_{task_type}",
            "category": "scanner",
            "manualOnly": False,
            "status": "success" if meta.get("status") == "completed" else "failed",
            "inputPayload": {task_type: meta.get("task_value", "")},
            "outputSummary": f"job {job_id} {meta.get('status')}",
            "returnType": "dict",
            "timestamp": _epoch_to_iso(values.get("scan_started_at")) or "",
            "relatedGraphNode": "scan_submit",
        })
    # RAG enrichment (one knowledge call for the multi-query report_context
    # request, plus mapping sub-queries summarized inside ragBundle.trace).
    rag_bundle = values.get("rag_bundle") or {}
    if rag_bundle:
        trace = rag_bundle.get("trace") or {}
        request_payload = trace.get("report_context_request") or {}
        counts = trace.get("response_counts") or {}
        out.append({
            "id": "tc_rag_report_context",
            "name": "build_report_context",
            "category": "knowledge",
            "manualOnly": False,
            "status": "success" if rag_bundle.get("confidence") != "unavailable" else "failed",
            "inputPayload": request_payload,
            "outputSummary": (
                f"{counts.get('check_findings', 0)} checks, "
                f"{counts.get('capability_themes', 0)} themes, "
                f"{counts.get('remediation_guides', 0)} guides, "
                f"{counts.get('control_mappings', 0)} mappings"
            ),
            "returnType": "dict",
            "timestamp": "",
            "durationMs": int(((rag_bundle.get("diagnostics") or {}).get("total_latency_ms") or 0)),
            "relatedGraphNode": "rag_enrich",
        })
    # Remediation tools (one per execution_log).
    # FE `ToolStatus = queued|running|success|failed` (no manual_required) —
    # so manual cases must surface as `manualOnly=True` + `status="failed"`
    # and the FE keys off `manualOnly` to render the manual badge. This keeps
    # ToolCall ↔ ExecutionLog rows aligned for the same task even though the
    # two views use different status enums.
    for log in (values.get("execution_logs") or []):
        s = str(log.get("status") or "").lower()
        is_manual = s == "manual_required"
        if s == "success":
            tc_status = "success"
        elif s in ("queued", "running"):
            tc_status = s
        else:
            # failed | error | manual_required | unknown → "failed"
            tc_status = "failed"
        out.append({
            "id": f"tc_{log.get('task_id')}",
            "name": str(log.get("tool_name") or ""),
            "category": "remediation",
            "manualOnly": is_manual,
            "status": tc_status,
            "inputPayload": {},
            "outputSummary": str(log.get("output", ""))[:200] if not isinstance(log.get("output"), dict) else "see execution log",
            "returnType": "dict",
            "timestamp": str(log.get("ended_at") or log.get("timestamp") or ""),
            "durationMs": int((log.get("duration") or 0) * 1000),
            "relatedGraphNode": "execution",
            "relatedFindingId": _task_to_finding(log.get("task_id"), values),
        })
    return out


def _task_to_finding(task_id: Optional[str], values: Dict[str, Any]) -> Optional[str]:
    if not task_id:
        return None
    for t in values.get("remediation_tasks", []) or []:
        if t.get("task_id") == task_id:
            return t.get("finding_id")
    return None


# ---------------------------------------------------------------------------
# Evidence (1 per FAIL finding, 1 per execution_log, 1 per verification)
# ---------------------------------------------------------------------------
def _evidence(values: Dict[str, Any], findings_fe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    findings_by_id = {f["id"]: f for f in findings_fe}

    # Scanner job evidence.
    for job_id, meta in (values.get("completed_jobs") or {}).items():
        task_type = meta.get("task_type") or "group"
        ev_id = f"ev_job_{job_id}"
        out.append({
            "id": ev_id,
            "kind": "scanner_job",
            "timestamp": _epoch_to_iso(values.get("scan_started_at")) or "",
            "sourceNode": "scan_submit",
            "sourceTool": f"start_scan_by_{task_type}",
            "jobId": job_id,
            "apiEndpoint": "POST /v1/scan/group" if task_type == "group" else "POST /v1/scan/checks",
            "httpMethod": "POST",
            "taskType": task_type,
            "taskValue": meta.get("task_value", ""),
            "status": _scan_job_status(meta.get("status")),
        })

    # Finding evidence — only FAIL.
    for f in findings_fe:
        if f["status"] != "FAIL":
            continue
        ev_id = f"ev_f_{f['id']}"
        out.append({
            "id": ev_id,
            "kind": "finding",
            "timestamp": "",
            "sourceNode": "scan_collect",
            "relatedFindingId": f["id"],
            "prowlerCheckId": f["prowlerCheckId"],
            "service": f["service"],
            "resource": f["resource"],
            "region": f["region"],
            "status": f["status"],
            "severity": f["severity"],
            "snippet": (f["description"] or f["title"])[:240],
        })
        # Wire evidenceIds back into the finding.
        if f["id"] in findings_by_id:
            findings_by_id[f["id"]]["evidenceIds"].append(ev_id)

    # Remediation evidence (one per execution_log).
    log_idx_by_task = {l.get("task_id"): l for l in values.get("execution_logs", []) or []}
    for t in values.get("remediation_tasks", []) or []:
        log = log_idx_by_task.get(t.get("task_id"))
        if not log:
            continue
        s = str(log.get("status") or "").lower()
        ev_id = f"ev_rem_{t.get('task_id')}"
        out.append({
            "id": ev_id,
            "kind": "remediation",
            "timestamp": str(log.get("ended_at") or log.get("timestamp") or ""),
            "sourceNode": "execution",
            "sourceTool": str(log.get("tool_name") or ""),
            "relatedFindingId": t.get("finding_id"),
            "toolName": str(log.get("tool_name") or ""),
            "awsAction": str(log.get("tool_name") or ""),
            "resource": "",
            "beforeState": "FAIL",
            "afterState": "PASS" if s == "success" else "FAIL",
            "verificationStatus": "passed" if s == "success" else ("manual_required" if s == "manual_required" else "failed"),
            "decision": "approved" if s == "success" else "rejected",
        })

    # Verification evidence.
    for i, v in enumerate(values.get("verification_results", []) or []):
        ev_id = f"ev_ver_{i:03d}"
        before = (v.get("before") or {}).get("status") or v.get("before_status") or ""
        after = v.get("after_status") or (v.get("after") or {}).get("status") or ""
        out.append({
            "id": ev_id,
            "kind": "verification",
            "timestamp": "",
            "sourceNode": "verification",
            "relatedFindingId": v.get("finding_uid") or v.get("finding_id"),
            "prowlerCheckId": str(v.get("event_code") or v.get("tool_name") or ""),
            "result": str(after or "FAIL").upper() if after.upper() in ("PASS", "FAIL", "MANUAL") else "FAIL",
            "snippet": f"{before} → {after}",
        })

    return out


# ---------------------------------------------------------------------------
# Graph nodes (from app.get_state_history)
# ---------------------------------------------------------------------------
def _parse_iso(s: Any):
    if not s:
        return None
    try:
        from datetime import datetime as _dt
        return _dt.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _graph_nodes(history: List[Dict[str, Any]], next_nodes: List[str]) -> List[Dict[str, Any]]:
    """Build a chronological list of nodes that have run, with status/duration.

    `history` is chronological-ascending (`graph_runtime.get_state_history`).
    LangGraph in this version persists `metadata` as only
    `{source, step, parents}` — the older `metadata.writes` map is empty —
    so we derive node names by walking the `next` chain instead:
    `history[i-1].next[0]` is the node that produced state at `history[i]`.
    """
    out: List[Dict[str, Any]] = []
    for i in range(1, len(history)):
        prev = history[i - 1]
        cur = history[i]
        prev_next = prev.get("next") or []
        if not prev_next:
            continue
        node_name = prev_next[0]
        if node_name in ("__start__", "__end__"):
            continue
        started_at = prev.get("created_at") or ""
        ended_at = cur.get("created_at") or ""
        d0 = _parse_iso(started_at)
        d1 = _parse_iso(ended_at)
        duration_ms: Optional[int] = (
            max(0, int((d1 - d0).total_seconds() * 1000)) if (d0 and d1) else None
        )
        entry: Dict[str, Any] = {
            "name": node_name,
            "status": "completed",
            "startedAt": str(started_at),
            "checkpointed": True,
        }
        if duration_ms is not None:
            entry["durationMs"] = duration_ms
        if node_name == "scan_poll":
            cur_values = cur.get("values") or {}
            entry["pollIterations"] = [{
                "index": int(cur_values.get("scan_poll_count") or 0) or (len(out) + 1),
                "startedAt": str(started_at),
                "durationMs": duration_ms or 0,
                "pendingAfter": len(cur_values.get("pending_jobs") or {}),
                "completedAfter": len(cur_values.get("completed_jobs") or {}),
                "newFindings": 0,
            }]
        out.append(entry)

    # Mark the "next" node as running/queued (not yet completed).
    for nxt in next_nodes:
        if nxt in ("__start__", "__end__"):
            continue
        out.append({
            "name": nxt,
            "status": "running",
            "startedAt": "",
            "checkpointed": False,
        })

    # Collapse duplicate scan_poll entries into one with pollIterations[].
    return _collapse_scan_poll(out)


def _collapse_scan_poll(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    poll_acc: Optional[Dict[str, Any]] = None
    for n in nodes:
        if n["name"] != "scan_poll":
            if poll_acc:
                out.append(poll_acc)
                poll_acc = None
            out.append(n)
            continue
        if poll_acc is None:
            poll_acc = {**n, "pollIterations": list(n.get("pollIterations", []))}
        else:
            poll_acc["pollIterations"].extend(n.get("pollIterations", []))
            poll_acc["status"] = n["status"]
            if n.get("durationMs"):
                poll_acc["durationMs"] = (poll_acc.get("durationMs") or 0) + n["durationMs"]
    if poll_acc:
        out.append(poll_acc)
    return out


# ---------------------------------------------------------------------------
# Report — read final_report markdown file, parse sections
# ---------------------------------------------------------------------------
_HEADING_LEVEL2_RE = re.compile(r"^##\s+(.+?)\s*#*\s*$")
_HEADING_LEVEL1_RE = re.compile(r"^#\s+(.+?)\s*#*\s*$")


def _split_markdown_sections(md: str) -> List[Dict[str, str]]:
    """Split markdown into FE-displayable sections.

    Reports rendered from the HTML template (via `html_to_markdown`) emit
    multiple `# ` headings (one per top-level chapter) plus `## ` for
    subsections. Older simple docs use a single `# Title` as the document
    title with `## ` as section breaks.

    Heuristic: if the doc has 2+ `# ` headings, treat each `# ` and `## `
    as a section break. Otherwise split only on `## ` so a lone `# Title`
    becomes the cover.
    """
    h1_count = sum(1 for ln in md.splitlines() if _HEADING_LEVEL1_RE.match(ln))
    split_on_h1 = h1_count >= 2

    sections: List[Dict[str, str]] = []
    current_title: Optional[str] = None
    buf: List[str] = []
    cover_buf: List[str] = []

    def _slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "section"

    def _flush():
        nonlocal buf, current_title
        if current_title is not None:
            sections.append({
                "id": _slug(current_title),
                "title": current_title,
                "body": "\n".join(buf).strip(),
            })
        buf = []

    for line in md.splitlines():
        m2 = _HEADING_LEVEL2_RE.match(line)
        m1 = _HEADING_LEVEL1_RE.match(line) if split_on_h1 else None
        if m2 or m1:
            _flush()
            current_title = (m2 or m1).group(1).strip()
            continue
        if current_title is None:
            cover_buf.append(line)
        else:
            buf.append(line)
    _flush()

    cover_body = "\n".join(cover_buf).strip()
    if cover_body:
        sections.insert(0, {"id": "cover", "title": "Cover", "body": cover_body})
    return sections or [{"id": "report", "title": "Report", "body": md}]


def _report(values: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    final_report = values.get("final_report")
    # ReportAgent emits {"markdown": ..., "html": ..., "pdf": ..., "validation_report": ...}
    if isinstance(final_report, dict):
        path = final_report.get("markdown")
        pdf_path = final_report.get("pdf")
    else:
        path = final_report
        pdf_path = None
    sections: List[Dict[str, Any]] = []
    if path and isinstance(path, str) and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                sections = _split_markdown_sections(f.read())
        except Exception as e:
            logger.warning(
                "report read failed",
                extra={"run_id": run_id, "path": path, "error": str(e)},
            )

    has_pdf = bool(pdf_path and isinstance(pdf_path, str) and os.path.exists(pdf_path))
    status = "ready" if sections or has_pdf else "pending"
    return {
        "filename": f"pdca-report-{run_id}.pdf" if has_pdf else f"pdca-report-{run_id}.md",
        "status": status,
        "runId": run_id,
        "version": "0.1.0",
        "sections": sections,
        "generatedAt": "",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _epoch_to_iso(epoch: Optional[float]) -> Optional[str]:
    if not epoch:
        return None
    try:
        import time as _t
        return _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime(float(epoch)))
    except Exception:
        return None


def _strip_private(d: Any) -> Any:
    """Recursively drop keys starting with `_` (one level deep is enough for
    PDCAState — `_langfuse_*`)."""
    if isinstance(d, dict):
        return {k: _strip_private(v) for k, v in d.items() if not str(k).startswith("_")}
    if isinstance(d, list):
        return [_strip_private(x) for x in d]
    return d


def _rag_capability_themes(themes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Expose only concise, document-backed RAG context to the FE trace."""
    out: List[Dict[str, Any]] = []
    for t in themes:
        if not isinstance(t, dict):
            continue
        citations = t.get("citations") or []
        if not citations or not any((c or {}).get("url") for c in citations if isinstance(c, dict)):
            continue
        narrative = " ".join(str(t.get("narrative") or "").split())
        if not narrative:
            continue
        if len(narrative) > 360:
            narrative = narrative[:357].rstrip() + "..."
        out.append({
            "domain": t.get("domain") or "general",
            "narrative": narrative,
            "common_pitfalls": [],
            "baselines": [],
            "citations": citations[:3],
        })
        if len(out) >= 5:
            break
    return out


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
def to_run_session(
    run_id: str,
    snapshot: Dict[str, Any],
    history: List[Dict[str, Any]],
    *,
    aws_environment_extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a RunSession dict for the FE.

    Args:
        run_id: the FE-facing run identifier (= LangGraph thread_id).
        snapshot: dict from `graph_runtime.get_state_values(run_id)` —
                  has keys `values`, `next`, `checkpoint_ts`.
        history: list from `graph_runtime.get_state_history(run_id)`.
        aws_environment_extras: optional overlay fields for awsEnvironment
                  (e.g. `accountMask`, `lastValidatedAt` from chatbot.py's
                  `_probe_aws()` cache).
    """
    values = (snapshot or {}).get("values") or {}
    next_nodes = (snapshot or {}).get("next") or []
    status, current_node = _derive_status(values, next_nodes)

    findings_fe = _findings(values)
    evidence_fe = _evidence(values, findings_fe)   # mutates findings_fe.evidenceIds

    aws_env = _aws_environment(values)
    if aws_environment_extras:
        aws_env.update({k: v for k, v in aws_environment_extras.items() if v is not None})

    rag_bundle = values.get("rag_bundle") or {}

    plan = values.get("assessment_plan") or {}
    clarification: Optional[Dict[str, Any]] = None
    if plan.get("status") == "needs_clarification":
        clarification = {
            "question": plan.get("clarification_question", ""),
            "originalRequest": values.get("user_request", ""),
        }
        # Override the derived status so the FE knows to surface a question
        # instead of treating an empty run as a successful completion.
        status = "needs_clarification"

    out: Dict[str, Any] = {
        "id": run_id,
        "threadId": run_id,
        "status": status,
        "currentNode": current_node,
        "checkpointer": "sqlite",
        "lastCheckpointAt": (snapshot or {}).get("checkpoint_ts") or "",
        "startedAt": _epoch_to_iso(((values.get("performance_metrics") or {}).get("system_info") or {}).get("start_time")) or "",
        "awsEnvironment": aws_env,
        "graphNodes": _graph_nodes(history or [], next_nodes),
        "scanJobs": _scan_jobs(values),
        "toolCalls": _tool_calls(values),
        "evidence": evidence_fe,
        "findings": findings_fe,
        "remediationTasks": _remediation_tasks(values),
        "executionLogs": _execution_logs(values),
        "verifications": _verifications(values),
        "messages": [],   # FE-only; client generates from status transitions
        "report": _report(values, run_id),
        "ragBundle": {
            "capabilityThemes": _rag_capability_themes(rag_bundle.get("capability_themes") or []),
            "remediationGuides": rag_bundle.get("remediation_guides") or [],
            "controlMappings": rag_bundle.get("control_mappings") or {},
            "confidence": rag_bundle.get("confidence") or "unknown",
            "diagnostics": rag_bundle.get("diagnostics") or {},
            "trace": rag_bundle.get("trace") or {},
        } if rag_bundle else None,
    }
    if clarification is not None:
        out["clarification"] = clarification
    return _strip_private(out)
