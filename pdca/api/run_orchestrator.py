"""Run orchestrator — Sprint 3.

Drives a single PDCA run end-to-end:

    scan_submit → scan_poll → scan_collect → risk_eval (rule-based)
    → operational_planning (rule-based) → review_task (HITL)
    → execution → verification → report

Design decisions:

* Self-contained — no LangGraph dependency yet. Runs as a background thread.
  Wiring the full LangGraph driver is a future iteration; the FE contract is
  identical so the swap will not require UI changes.
* Rule-based remediation suggester. Maps Prowler check_id substrings to S3
  remediation tools registered in `pdca.tools`. LLM (RemediationPlannerAgent)
  can be plugged in later — the data shape it emits already matches what we
  produce here.
* All run state is held in memory under a per-run lock, persisted to
  `data/runs/run_state.json` after every transition so a server restart can
  reload the last snapshot (read-only resume — execution does not auto-resume).
* The scanner API (`/v1/scan/*`) is treated as an external service —
  orchestrator HTTP-calls it, never imports the worker.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx

from pdca.config import settings
from pdca.observability.logger import get_logger

logger = get_logger("pdca.api.run_orchestrator")

STATE_DIR = "data/runs"
STATE_FILE = os.path.join(STATE_DIR, "run_state.json")
os.makedirs(STATE_DIR, exist_ok=True)


# ─── Rule-based remediation map ────────────────────────────────────────────
# Maps a substring in Prowler check_id (event_code) to a tool from
# `pdca.tools.remediation.s3`. Order matters — first match wins.
REMEDIATION_RULES: List[tuple[str, str, str]] = [
    # (check_id_substring, tool_name, human-readable rationale)
    ("account_level_public_access_blocks", "s3_block_account_public_access",
     "Account-level Public Access Block missing — enables all 4 BPA flags."),
    ("bucket_level_public_access_block",  "s3_block_account_public_access",
     "Bucket Public Access Block missing — apply BPA at account level."),
    ("bucket_public_access",              "s3_block_account_public_access",
     "Bucket is publicly accessible — block public access."),
    ("bucket_no_mfa_delete",              "s3_enable_mfa_delete",
     "MFA Delete missing — protects against accidental object deletion."),
    ("bucket_object_lock",                "s3_enable_object_lock",
     "Object Lock missing — required for compliance-grade WORM."),
    ("bucket_object_versioning",          "s3_enable_versioning",
     "Versioning disabled — enable to recover from overwrites."),
    ("bucket_default_encryption",         "s3_enable_kms_encryption",
     "Default encryption missing — enforce SSE-KMS."),
    ("bucket_kms_encryption",             "s3_enable_kms_encryption",
     "Encryption is not KMS — upgrade to SSE-KMS for key rotation."),
    ("bucket_secure_transport_policy",    "s3_secure_transport",
     "TLS-only policy missing — block HTTP."),
    ("bucket_server_access_logging",      "s3_enable_access_logging",
     "Access logging missing — required for forensics."),
    ("bucket_lifecycle_enabled",          "s3_enable_lifecycle_configuration",
     "Lifecycle policy missing — manage object expiry."),
    ("bucket_acl_prohibited",             "s3_disable_bucket_acls",
     "Bucket ACLs in use — switch to BucketOwnerEnforced."),
    ("bucket_event_notifications",        "s3_enable_event_notifications",
     "Event notifications missing — for change auditing."),
    ("bucket_intelligent_tiering",        "s3_enable_intelligent_tiering",
     "Intelligent-Tiering missing — automatic cost optimisation."),
    ("bucket_cross_account",              "s3_remove_cross_account_principals",
     "Cross-account principal in policy — remove for least privilege."),
    ("bucket_cross_region_replication",   "s3_prepare_replication",
     "CRR missing — needed for DR."),
]


def _suggest_remediation(check_id: str) -> Optional[tuple[str, str]]:
    needle = check_id.lower()
    for pattern, tool, rationale in REMEDIATION_RULES:
        if pattern in needle:
            return tool, rationale
    return None


# ─── State store ───────────────────────────────────────────────────────────
class RunStore:
    """Thread-safe in-memory run registry, with JSON snapshot to disk."""

    def __init__(self) -> None:
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._runs = data
        except Exception as e:
            logger.warning("RunStore._load failed", extra={"error": str(e)})

    def _persist_locked(self) -> None:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._runs, f, ensure_ascii=False, default=str)
        os.replace(tmp, STATE_FILE)

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            run = self._runs.get(run_id)
            return json.loads(json.dumps(run, default=str)) if run else None

    def all_ids(self) -> List[str]:
        with self._lock:
            return list(self._runs.keys())

    def update(self, run_id: str, mutator) -> Dict[str, Any]:
        with self._lock:
            run = self._runs.setdefault(run_id, {})
            mutator(run)
            self._persist_locked()
            return json.loads(json.dumps(run, default=str))


STORE = RunStore()


# ─── Helpers ───────────────────────────────────────────────────────────────
def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ms_since(epoch: float) -> int:
    return int((time.time() - epoch) * 1000)


def _scanner_base() -> str:
    """Read scanner URL from env first, fall back to settings."""
    return os.getenv("SCANNER_API_URL", settings.scanner_api_url).rstrip("/")


def _ocsf_severity(raw: Dict) -> str:
    sid = raw.get("severity_id")
    if sid in (4, 5, 6):
        return "high" if sid == 4 else "critical"
    if sid == 3:
        return "medium"
    if sid == 2:
        return "low"
    sev = str(raw.get("severity", "")).upper()
    return {
        "CRITICAL": "critical", "HIGH": "high",
        "MEDIUM": "medium", "LOW": "low",
        "INFORMATIONAL": "info",
    }.get(sev, "info")


def _ocsf_status(raw: Dict) -> str:
    code = str(raw.get("status_code") or raw.get("status") or "").upper()
    if code in ("PASS", "FAIL", "MANUAL"):
        return code
    if raw.get("status_id") == 1:
        return "PASS"
    if raw.get("status_id") == 2:
        return "FAIL"
    return "MANUAL"


def _ocsf_resource(raw: Dict) -> Dict[str, str]:
    r = (raw.get("resources") or [{}])[0] or {}
    return {
        "resource":   str(r.get("uid") or r.get("name") or "unknown"),
        "region":     str(r.get("region") or raw.get("region") or ""),
        "service":    str(r.get("type") or raw.get("service_name") or "aws"),
        "account_id": str(r.get("cloud_partition") or raw.get("cloud", {}).get("account", {}).get("uid", "")),
    }


def _ocsf_check_id(raw: Dict) -> str:
    return str(
        raw.get("metadata", {}).get("event_code")
        or raw.get("finding_info", {}).get("uid")
        or raw.get("check_id")
        or raw.get("unmapped", {}).get("check_id")
        or "unknown_check"
    )


def _normalize_findings(run_id: str, raw_list: List[Dict]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, raw in enumerate(raw_list):
        r = _ocsf_resource(raw)
        check_id = _ocsf_check_id(raw)
        out.append({
            "id": f"{run_id}-f{i:03d}",
            "prowlerCheckId": check_id,
            "service": r["service"] or "aws",
            "resource": r["resource"],
            "region": r["region"],
            "title": raw.get("finding_info", {}).get("title") or check_id,
            "description": raw.get("finding_info", {}).get("desc") or raw.get("message") or "",
            "severity": _ocsf_severity(raw),
            "status": _ocsf_status(raw),
            "remediationStatus": "open",
            "recommendation": raw.get("remediation", {}).get("desc") or "",
            "evidenceIds": [],
            "_account_id": r["account_id"],
        })
    return out


# ─── Graph node bookkeeping ────────────────────────────────────────────────
def _start_node(run: Dict[str, Any], name: str, input_summary: str = "") -> None:
    run.setdefault("graphNodes", []).append({
        "name": name, "status": "running",
        "startedAt": _iso(), "_started_perf": time.time(),
        "inputSummary": input_summary, "checkpointed": True,
    })
    run["currentNode"] = name


def _finish_node(run: Dict[str, Any], status: str, output_summary: str = "") -> None:
    nodes = run.get("graphNodes") or []
    if not nodes:
        return
    n = nodes[-1]
    started = n.pop("_started_perf", time.time())
    n["status"] = status
    n["durationMs"] = _ms_since(started)
    n["outputSummary"] = output_summary


def _add_message(run: Dict[str, Any], cards: List[Dict[str, Any]]) -> None:
    run.setdefault("messages", []).append({
        "id": _new_id("m"),
        "role": "assistant",
        "timestamp": _iso(),
        "cards": cards,
    })


def _record_tool_call(
    run: Dict[str, Any],
    *, name: str, category: str, manual_only: bool = False,
    status: str, input_payload: Dict[str, Any],
    output_summary: str = "", duration_ms: int = 0,
    related_node: Optional[str] = None,
    related_finding: Optional[str] = None,
) -> str:
    tc_id = _new_id("tc")
    run.setdefault("toolCalls", []).append({
        "id": tc_id,
        "name": name,
        "category": category,
        "manualOnly": manual_only,
        "status": status,
        "inputPayload": input_payload,
        "outputSummary": output_summary,
        "returnType": "dict",
        "timestamp": _iso(),
        "durationMs": duration_ms,
        "relatedGraphNode": related_node,
        "relatedFindingId": related_finding,
    })
    return tc_id


def _record_evidence(run: Dict[str, Any], ev: Dict[str, Any]) -> str:
    ev = {**ev, "id": ev.get("id") or _new_id("ev"), "timestamp": _iso()}
    run.setdefault("evidence", []).append(ev)
    return ev["id"]


# ─── Optional LLM reasoning enrichment ─────────────────────────────────────
def _ollama_reason(check_id: str, resource: str, fallback: str) -> str:
    """Best-effort: ask Ollama to produce a one-sentence rationale.

    Soft-fail: if Ollama is down or slow, return the rule-based fallback.
    """
    base = os.getenv("OLLAMA_BASE_URL") or settings.ollama_base_url
    model = os.getenv("OLLAMA_MODEL") or settings.ollama_model
    prompt = (
        "You are an AWS security expert. In ONE sentence (max 30 words), explain "
        f"the risk of finding '{check_id}' on resource '{resource}' and why "
        "remediation is required. Plain prose only — no markdown, no preface."
    )
    try:
        with httpx.Client(timeout=8.0) as c:
            r = c.post(
                base.rstrip("/") + "/api/generate",
                json={"model": model, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0, "num_predict": 80}},
            )
            r.raise_for_status()
            txt = (r.json().get("response") or "").strip()
            return txt or fallback
    except Exception:
        return fallback


# ─── Orchestrator ──────────────────────────────────────────────────────────
class RunOrchestrator:
    """One instance per run, executed on a worker thread."""

    POLL_INTERVAL_S = 4
    POLL_MAX_S = 30 * 60  # 30 min

    def __init__(self, run_id: str):
        self.run_id = run_id

    # State helpers
    def _patch(self, mutator) -> None:
        STORE.update(self.run_id, mutator)

    def _scanner(self) -> httpx.Client:
        return httpx.Client(base_url=_scanner_base(), timeout=15.0)

    # ─── Public entrypoint ────────────────────────────────────────────
    def run(self, prompt: str, scope: Optional[str], group: str) -> None:
        try:
            self._phase_environment()
            self._phase_planning(prompt, scope, group)
            jobs = self._phase_scan(group)
            findings = self._phase_collect(jobs)
            self._phase_rag_enrich(findings)
            self._phase_risk_eval(findings)
            self._phase_plan_remediation(findings)
            self._phase_wait_for_approval()
            self._phase_execute()
            self._phase_verify()
            self._phase_report(prompt, scope)
            self._patch(lambda r: r.update({"status": "completed", "completedAt": _iso()}))
        except Exception as e:
            logger.exception("run failed", extra={"run_id": self.run_id})
            self._patch(lambda r: r.update({
                "status": "failed",
                "error": {"message": str(e)},
            }))

    # ─── Phases ───────────────────────────────────────────────────────
    def _phase_environment(self) -> None:
        self._patch(lambda r: (
            r.update({"status": "validating_environment"}),
            _start_node(r, "environment", "AWS profile probe"),
            _add_message(r, [{"kind": "text",
                "text": "🔐 Đang xác thực kết nối AWS — kiểm tra profile, region và quyền truy cập…"}]),
            _finish_node(r, "completed", "boto3 session ready"),
        ))

    def _phase_planning(self, prompt: str, scope: Optional[str], group: str) -> None:
        self._patch(lambda r: (
            r.update({"status": "planning"}),
            _start_node(r, "planning", prompt),
            _add_message(r, [{"kind": "planning",
                "scanner": "Prowler",
                "provider": "AWS",
                "scope": scope or f"{group} only",
                "groups": [group],
                "specificChecks": "auto",
                "expectedOutput": "OCSF JSON findings",
                "nextNode": "scan_submit"}]),
            _finish_node(r, "completed", f"Provider AWS · group {group}"),
        ))

    def _phase_scan(self, group: str) -> List[Dict[str, Any]]:
        self._patch(lambda r: (
            r.update({"status": "submitting_scan"}),
            _start_node(r, "scan_submit", f"POST /v1/scan/group {{group:{group}}}"),
        ))
        with self._scanner() as c:
            res = c.post("/v1/scan/group", json={"group": group}).json()
        job_id = res["job_id"]

        def upd(r, jid=job_id, gp=group):
            r.setdefault("scanJobs", []).append({
                "id": jid,
                "apiEndpoint": "POST /v1/scan/group",
                "httpMethod": "POST",
                "taskType": "group",
                "taskValue": gp,
                "status": "pending",
                "submittedAt": _iso(),
            })
            _record_tool_call(
                r, name=f"scan_group_{gp}", category="scanner",
                status="success",
                input_payload={"group": gp, "endpoint": "/v1/scan/group"},
                output_summary=f"job {jid} queued",
                related_node="scan_submit",
            )
            _record_evidence(r, {
                "kind": "scanner_job",
                "sourceNode": "scan_submit",
                "sourceTool": f"scan_group_{gp}",
                "jobId": jid,
                "apiEndpoint": "POST /v1/scan/group",
                "httpMethod": "POST",
                "taskType": "group",
                "taskValue": gp,
                "status": "pending",
            })
            _add_message(r, [{
                "kind": "scan_submitted",
                "api": "POST /v1/scan/group",
                "group": gp,
                "jobId": jid,
                "status": "pending",
                "nextNode": "scan_poll",
            }])
            _finish_node(r, "completed", f"job {jid} queued")
            _start_node(r, "scan_poll", f"polling {jid}")
            _add_message(r, [{"kind": "text",
                "text": f"⏳ Prowler đang quét — sẽ poll job {jid} mỗi 4 giây cho đến khi hoàn tất…"}])
            r.update({"status": "polling"})
        self._patch(upd)

        deadline = time.time() + self.POLL_MAX_S
        iters = 0
        last_job: Dict[str, Any] = {}
        while time.time() < deadline:
            time.sleep(self.POLL_INTERVAL_S)
            iters += 1
            with self._scanner() as c:
                last_job = c.get(f"/v1/job/{job_id}").json()

            def upd(r, j=last_job, n=iters):
                jobs = r.setdefault("scanJobs", [])
                for sj in jobs:
                    if sj["id"] == job_id:
                        sj["status"] = j.get("status", sj["status"])
                        if j.get("end_time"):
                            sj["finishedAt"] = _iso()
                        result = j.get("result") or []
                        sj["resultCount"] = len(result) if isinstance(result, list) else 0
                        break
                # Per-iteration trace
                pn = r["graphNodes"][-1]
                pn.setdefault("pollIterations", []).append({
                    "index": n,
                    "startedAt": _iso(),
                    "durationMs": int(self.POLL_INTERVAL_S * 1000),
                    "pendingAfter": 0 if j.get("status") in ("completed", "failed") else 1,
                    "completedAfter": 1 if j.get("status") == "completed" else 0,
                    "newFindings": len(j.get("result") or []) if j.get("status") == "completed" else 0,
                })
            self._patch(upd)

            if last_job.get("status") in ("completed", "failed"):
                break

        if last_job.get("status") != "completed":
            raise RuntimeError(
                f"scan {job_id} did not complete: status={last_job.get('status')}"
            )

        self._patch(lambda r: _finish_node(r, "completed", f"{iters} polls · job done"))
        return [last_job]

    def _phase_collect(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self._patch(lambda r: (
            r.update({"status": "collecting_findings"}),
            _start_node(r, "scan_collect", f"{sum(len(j.get('result') or []) for j in jobs)} raw"),
        ))
        all_findings: List[Dict[str, Any]] = []
        for j in jobs:
            all_findings.extend(_normalize_findings(self.run_id, j.get("result") or []))
        passes = sum(1 for f in all_findings if f["status"] == "PASS")
        fails  = sum(1 for f in all_findings if f["status"] == "FAIL")
        manual = sum(1 for f in all_findings if f["status"] == "MANUAL")

        def upd(r, fs=all_findings):
            r["findings"] = fs
            # Attach finding-evidence for every FAIL — that's what shows up
            # in the right-hand Tool & Evidence trace panel.
            for f in fs:
                if f["status"] != "FAIL":
                    continue
                ev_id = _record_evidence(r, {
                    "kind": "finding",
                    "sourceNode": "scan_collect",
                    "relatedFindingId": f["id"],
                    "prowlerCheckId": f["prowlerCheckId"],
                    "service": f["service"],
                    "resource": f["resource"],
                    "region": f["region"],
                    "status": f["status"],
                    "severity": f["severity"],
                    "snippet": (f.get("description") or f["title"])[:240],
                })
                f.setdefault("evidenceIds", []).append(ev_id)
            _finish_node(r, "completed", f"{fails} FAIL · {passes} PASS · {manual} MANUAL")
            _add_message(r, [{
                "kind": "findings_collected",
                "rawFindings": len(fs),
                "passed": passes, "failed": fails, "manual": manual,
                "node": "scan_collect",
                "snapshot": f"{fails} FAIL · {passes} PASS · {manual} MANUAL",
            }])
        self._patch(upd)
        return all_findings

    def _phase_rag_enrich(self, findings: List[Dict[str, Any]]) -> None:
        """Multi-query RAG enrichment.

        Calls 3 RAG endpoints to gather knowledge context:
        1. `POST /v1/retrieve/report_context` — Q1 (check details) + Q2
           (capability themes per domain) + Q3 (remediation guides per
           failed check_id) in ONE batched request.
        2. `POST /v1/resolve/mapping` — per unique check_id, fetch the
           compliance framework mappings (CIS, NIST, etc.).

        Results are stored on the run so:
        - FE can render the capability themes + remediation guides in the
          Tool & Evidence panel ("Knowledge" tab).
        - The remediation planner can read steps[] (cli/iac/console
          snippets) to enrich each task.
        - The Report agent receives a richer `rag_context`.
        """
        fails = [f for f in findings if f.get("status") == "FAIL"]
        if not fails:
            return

        unique_check_ids = sorted({f["prowlerCheckId"] for f in fails})
        domains = sorted({(f.get("service") or "").lower() for f in fails if f.get("service")})

        self._patch(lambda r: (
            _start_node(r, "rag_enrich",
                        f"{len(fails)} FAIL · {len(unique_check_ids)} unique checks · {len(domains)} domains"),
            _add_message(r, [{"kind": "text",
                "text": (
                    f"📚 RAG multi-query đang chạy: report_context (Q1+Q2+Q3) cho "
                    f"{len(unique_check_ids)} check IDs + {len(domains)} domains, "
                    f"và resolve_mapping cho compliance framework…"
                )}]),
        ))

        rag_base = os.getenv("RAG_API_URL") or settings.rag_api_url

        # Build severity_map for Q3 (remediation top-k filter).
        sev_map: Dict[str, str] = {}
        for f in fails:
            cid = f["prowlerCheckId"]
            s = (f.get("severity") or "").upper()
            if s in ("CRITICAL", "HIGH", "MEDIUM", "LOW") and cid not in sev_map:
                sev_map[cid] = s

        bundle: Dict[str, Any] = {}
        mappings: Dict[str, Any] = {}

        try:
            with httpx.Client(base_url=rag_base, timeout=20.0) as c:
                # ─── Q1+Q2+Q3 bundle ────────────────────────────────────
                try:
                    r = c.post("/v1/retrieve/report_context", json={
                        "check_ids":         unique_check_ids,
                        "domains":           domains,
                        "severity_map":      sev_map,
                        "include_q2":        True,
                        "include_q3":        True,
                        "top_k_check":       10,
                        "top_k_capability":  5,
                        "top_k_remediation": 3,
                    })
                    r.raise_for_status()
                    bundle = r.json() or {}
                except Exception as e:
                    logger.warning("retrieve/report_context failed", extra={"err": str(e)})

                # ─── Resolve mappings per check_id ──────────────────────
                for cid in unique_check_ids:
                    try:
                        # Pull service from the first finding that has this cid.
                        f0 = next((x for x in fails if x["prowlerCheckId"] == cid), {})
                        r = c.post("/v1/resolve/mapping", json={
                            "check_id": cid,
                            "provider": "aws",
                            "service":  f0.get("service") or None,
                        })
                        r.raise_for_status()
                        payload = r.json() or {}
                        mappings[cid] = (payload.get("data") or {}) or payload
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("RAG enrich session failed", extra={"err": str(e)})

        # ─── Project bundle results back onto findings ─────────────────
        # Q1: check_findings — index by check_id, attach compliance / risk.
        check_index: Dict[str, Dict[str, Any]] = {}
        for cf in (bundle.get("check_findings") or []):
            cid = cf.get("check_id") or cf.get("metadata", {}).get("check_id")
            if cid:
                check_index[cid] = cf

        # Q3: remediations — index by check_id.
        rem_index: Dict[str, Dict[str, Any]] = {}
        for rg in (bundle.get("remediations") or []):
            cid = rg.get("check_id")
            if cid:
                rem_index[cid] = rg

        enriched = 0
        for f in fails:
            cid = f["prowlerCheckId"]
            cf = check_index.get(cid) or {}
            md = cf.get("metadata") or cf
            if md:
                f["compliance"]                = md.get("keywords") or md.get("compliance") or []
                f["riskFromRag"]               = (md.get("risk") or "")[:300]
                f["remediationRecommendation"] = md.get("remediation_recommendation") or ""
                f["remediationUrl"]            = md.get("remediation_url") or ""
                f["ragTitle"]                  = md.get("title") or ""
                rag_sev = (md.get("severity") or "").lower()
                if rag_sev in ("critical", "high", "medium", "low", "info"):
                    f["severity"] = rag_sev
                enriched += 1
            # Attach Q3 remediation guide (steps + effort + side_effects).
            rg = rem_index.get(cid)
            if rg:
                f["remediationGuide"] = rg
            # Attach mapping (Q4 — control framework references).
            m = mappings.get(cid)
            if m:
                f["controlMappings"] = m

        capability_themes = bundle.get("capability_themes") or []
        remediation_guides = list(rem_index.values())
        confidence = bundle.get("confidence") or "unknown"

        # Persist + record tool calls for the trace panel.
        def upd(r, fs=findings, n=enriched, ct=capability_themes,
                rg_count=len(remediation_guides), mc=len(mappings)):
            r["findings"] = fs
            r["ragBundle"] = {
                "capabilityThemes": ct,
                "remediationGuides": remediation_guides,
                "controlMappings": mappings,
                "confidence": confidence,
                "diagnostics": bundle.get("diagnostics") or {},
            }
            _record_tool_call(
                r, name="rag_report_context", category="knowledge",
                status="success" if bundle else "failed",
                input_payload={"check_ids": len(unique_check_ids), "domains": len(domains)},
                output_summary=(
                    f"Q1: {len(check_index)} checks · Q2: {len(ct)} themes · "
                    f"Q3: {rg_count} guides · confidence={confidence}"
                ),
                related_node="rag_enrich",
            )
            if mc:
                _record_tool_call(
                    r, name="rag_resolve_mapping", category="knowledge",
                    status="success",
                    input_payload={"check_ids": list(mappings.keys())[:5]},
                    output_summary=f"{mc} compliance mappings resolved",
                    related_node="rag_enrich",
                )
            _finish_node(
                r, "completed",
                f"enriched {n}/{len(unique_check_ids)} · {len(ct)} themes · {rg_count} guides",
            )
        self._patch(upd)

    def _phase_risk_eval(self, findings: List[Dict[str, Any]]) -> None:
        self._patch(lambda r: (
            r.update({"status": "evaluating_risk"}),
            _start_node(r, "risk_evaluation", f"{sum(1 for f in findings if f['status']=='FAIL')} FAIL"),
            _add_message(r, [{"kind": "text",
                "text": "📊 Đang phân tích rủi ro: phân loại theo severity (critical/high/medium/low) và xác định mức ưu tiên xử lý…"}]),
        ))
        # Rule-based: severity already provided by Prowler; just count.
        fails = [f for f in findings if f["status"] == "FAIL"]
        high = sum(1 for f in fails if f["severity"] in ("critical", "high"))
        med  = sum(1 for f in fails if f["severity"] == "medium")
        low  = sum(1 for f in fails if f["severity"] == "low")
        self._patch(lambda r: (
            _finish_node(r, "completed", f"{high} high · {med} medium · {low} low"),
            _add_message(r, [{
                "kind": "risk_evaluation",
                "high": high, "medium": med, "low": low,
                "manualReview": sum(1 for f in findings if f["status"] == "MANUAL"),
                "prioritized": len(fails),
            }]),
        ))

    def _phase_plan_remediation(self, findings: List[Dict[str, Any]]) -> None:
        # LLM enrich switch: opt-in via env (default on).
        llm_on = os.getenv("PDCA_LLM_ENRICH", "1") not in ("0", "false", "False")
        self._patch(lambda r: (
            r.update({"status": "executing_remediation"}),
            _start_node(r, "operational_planning", f"{sum(1 for f in findings if f['status']=='FAIL')} FAIL"),
            _add_message(r, [{"kind": "text",
                "text": (
                    "🤖 RemediationPlannerAgent đang chạy: map mỗi FAIL finding → AWS remediation tool. "
                    + ("Đang gọi LLM (Ollama) để giải thích lý do và rủi ro cho từng task…"
                       if llm_on else "Dùng rule-based mapping (không LLM).")
                )
            }]),
        ))

        tasks: List[Dict[str, Any]] = []
        for f in findings:
            if f["status"] != "FAIL":
                continue
            suggestion = _suggest_remediation(f["prowlerCheckId"])
            if not suggestion:
                continue
            tool_name, rule_rationale = suggestion
            task_id = _new_id("task")

            llm_reasoning = None
            if llm_on:
                llm_reasoning = _ollama_reason(
                    f["prowlerCheckId"], f["resource"], rule_rationale,
                )

            # Pull RAG remediation guide if present (Q3 from multi-query).
            rg = f.get("remediationGuide") or {}
            rag_steps = rg.get("steps") or []
            rag_effort = rg.get("effort") or "medium"

            tasks.append({
                "id": task_id,
                "findingId": f["id"],
                "findingTitle": f["title"],
                "severity": f["severity"],
                "resource": f["resource"],
                "toolName": tool_name,
                "toolCategory": "remediation",
                "manualOnly": False,
                "proposedAction": llm_reasoning or rule_rationale,
                "expectedImpact": rule_rationale,
                "requiredAwsPermission": "see tool docstring",
                "decision": "pending",
                "toolParams": {
                    "resource_id": f["resource"],
                    "region": f["region"] or "us-east-1",
                    "account_id": f.get("_account_id") or "",
                },
                "guardChecks": {
                    "registeredTool": True,
                    "isRemediationCategory": True,
                    "notManualOnly": True,
                },
                "ragSteps":      rag_steps,        # [{order, type, snippet, prerequisite}]
                "ragEffort":     rag_effort,       # low | medium | high
                "ragSideEffects": rg.get("side_effects") or [],
                "ragRollback":   rg.get("rollback"),
                "compliance":    f.get("compliance") or [],
                "_ruleRationale": rule_rationale,
                "_llmReasoning": llm_reasoning,
            })

        self._patch(lambda r: (
            r.update({"remediationTasks": tasks, "status": "waiting_for_approval"}),
            _finish_node(r, "completed", f"{len(tasks)} task(s) · awaiting approval"),
            _start_node(r, "review_task", f"{len(tasks)} pending"),
        ))
        if tasks:
            self._patch(lambda r: _add_message(r, [{"kind": "text",
                "text": (
                    f"✅ Đã lập **{len(tasks)} kế hoạch sửa lỗi**. "
                    "Vui lòng review từng task bên dưới và bấm **Approve** để cho phép thực thi, "
                    "hoặc **Reject** để bỏ qua. AI sẽ chỉ chạy những task được approve."
                )}]))
            # Each task has its own offer card so the user can approve inline
            # in the chat. The card carries no payload — the task data is
            # rendered from `run.remediationTasks` (matched by id).
            self._patch(lambda r: _add_message(r, [
                {"kind": "remediation_offer", "taskId": t["id"]} for t in tasks
            ]))
        else:
            self._patch(lambda r: _add_message(r, [{"kind": "text",
                "text": "ℹ️ Không có task nào auto-remediable cho findings này. Tất cả cần xử lý thủ công."}]))

    def _phase_wait_for_approval(self) -> None:
        deadline = time.time() + 30 * 60
        while time.time() < deadline:
            time.sleep(2)
            run = STORE.get(self.run_id) or {}
            tasks = run.get("remediationTasks", [])
            if not tasks:
                break
            pending = [t for t in tasks if t.get("decision") == "pending"]
            if not pending:
                break
        self._patch(lambda r: _finish_node(r, "completed", "approvals received"))

    def _phase_execute(self) -> None:
        self._patch(lambda r: (
            r.update({"status": "executing_remediation"}),
            _start_node(r, "execution", "running approved tools"),
            _add_message(r, [{"kind": "text",
                "text": "⚙️ ExecutionAgent đang thực thi các task được approve trên AWS thực tế (boto3)…"}]),
        ))
        run = STORE.get(self.run_id) or {}
        tasks = run.get("remediationTasks", [])
        approved = [t for t in tasks if t.get("decision") == "approved"]

        # Late import to keep this module importable on systems without boto3.
        from pdca.agents.execution_agent import ExecutionAgent

        agent = ExecutionAgent(aws_context={
            "region": settings.aws_default_region,
            "account_id": "",
        })

        logs: List[Dict[str, Any]] = []
        for t in approved:
            shape = {
                "task_id": t["id"],
                "tool_name": t["toolName"],
                "tool_params": t["toolParams"],
                "finding_id": t["findingId"],
            }
            try:
                result = agent.execute_task(shape, decision="approve")
            except Exception as e:
                result = {"task_id": t["id"], "tool_name": t["toolName"],
                          "status": "error", "output": str(e), "duration": 0}
            logs.append({
                "taskId": result["task_id"],
                "toolName": result["tool_name"],
                "status": result.get("status", "error"),
                "message": (
                    json.dumps(result.get("output"))[:300]
                    if not isinstance(result.get("output"), str)
                    else result["output"]
                ),
                "durationMs": int((result.get("duration") or 0) * 1000),
                "timestamp": _iso(),
            })

        # Update task remediation status + emit tool/evidence + chat cards.
        def upd(r, log_list=logs, approved_tasks=approved):
            r.setdefault("executionLogs", []).extend(log_list)
            log_index = {l["taskId"]: l for l in log_list}
            tasks_by_id = {t["id"]: t for t in r.get("remediationTasks", [])}
            for lg in log_list:
                t = tasks_by_id.get(lg["taskId"]) or {}
                _record_tool_call(
                    r, name=lg["toolName"], category="remediation",
                    status="success" if lg["status"] == "success" else "failed",
                    input_payload=t.get("toolParams") or {},
                    output_summary=lg["message"][:200],
                    duration_ms=lg["durationMs"],
                    related_node="execution",
                    related_finding=t.get("findingId"),
                )
                _record_evidence(r, {
                    "kind": "remediation",
                    "sourceNode": "execution",
                    "sourceTool": lg["toolName"],
                    "relatedFindingId": t.get("findingId"),
                    "toolName": lg["toolName"],
                    "awsAction": lg["toolName"],
                    "resource": t.get("resource", ""),
                    "beforeState": "FAIL",
                    "afterState": "PASS" if lg["status"] == "success" else "FAIL",
                    "verificationStatus": "passed" if lg["status"] == "success" else "failed",
                    "decision": "approved",
                })
                # Chat card so the user sees "remediation_execution" inline.
                _add_message(r, [{
                    "kind": "remediation_execution",
                    "taskId": lg["taskId"],
                    "toolName": lg["toolName"],
                    "decision": "approved",
                    "status": lg["status"],
                    "guardChecks": (t.get("guardChecks") or {
                        "registeredTool": True,
                        "isRemediationCategory": True,
                        "notManualOnly": True,
                    }),
                }])
                if t:
                    t["remediationStatus"] = (
                        "remediated" if lg["status"] == "success" else "failed"
                    )
            _finish_node(
                r, "completed",
                f"{sum(1 for l in log_list if l['status']=='success')} ok / {len(log_list)} total",
            )
        self._patch(upd)

    def _phase_verify(self) -> None:
        self._patch(lambda r: (
            r.update({"status": "verifying"}),
            _start_node(r, "verification", "rescan executed targets"),
            _add_message(r, [{"kind": "text",
                "text": "🔍 Đang verify: so sánh trạng thái trước/sau cho mỗi resource đã sửa…"}]),
        ))
        # Lightweight verification: rely on the scanner job's findings as the
        # single source of truth. A real rescan would re-submit specific check
        # ids; we skip that here to keep the demo time-bounded.
        run = STORE.get(self.run_id) or {}
        verifications: List[Dict[str, Any]] = []
        log_index = {l["taskId"]: l for l in run.get("executionLogs", [])}
        for t in run.get("remediationTasks", []):
            lg = log_index.get(t["id"])
            if not lg:
                continue
            verifications.append({
                "id": _new_id("ver"),
                "findingId": t["findingId"],
                "resource": t["resource"],
                "toolName": t["toolName"],
                "beforeState": "FAIL",
                "afterState": "PASS" if lg["status"] == "success" else "FAIL",
                "result": "passed" if lg["status"] == "success" else "failed",
                "timestamp": _iso(),
                "executionLogTaskId": t["id"],
            })
        def upd(r, vs=verifications):
            r["verifications"] = vs
            for v in vs:
                _record_evidence(r, {
                    "kind": "verification",
                    "sourceNode": "verification",
                    "relatedFindingId": v["findingId"],
                    "prowlerCheckId": v.get("toolName", ""),
                    "result": "PASS" if v["result"] == "passed" else "FAIL",
                    "snippet": f"{v['beforeState']} → {v['afterState']} after {v['toolName']}",
                })
                # Chat card.
                _add_message(r, [{
                    "kind": "verification",
                    "findingId": v["findingId"],
                    "beforeState": v["beforeState"],
                    "afterState": v["afterState"],
                    "verificationStatus": v["result"],
                }])
            _finish_node(
                r, "completed",
                f"{sum(1 for v in vs if v['result']=='passed')}/{len(vs)} verified",
            )
        self._patch(upd)

    def _phase_report(self, prompt: str, scope: Optional[str]) -> None:
        self._patch(lambda r: (
            r.update({"status": "generating_report"}),
            _start_node(r, "report", "ReportAgent + RAG"),
            _add_message(r, [{"kind": "text",
                "text": "📝 Đang gọi ReportAgent (LLM + RAG) để tổng hợp báo cáo executive…"}]),
        ))
        run = STORE.get(self.run_id) or {}
        findings = run.get("findings", [])
        tasks = run.get("remediationTasks", [])
        verifications = run.get("verifications", [])

        # Try to use the real ReportAgent (executive-style report with RAG +
        # maturity assessment). Fall back to a simple inline assembler if the
        # heavy import or the LLM call blows up — we never want a report
        # failure to abort the whole run.
        sections = self._build_report_via_agent(prompt, scope, findings, tasks, verifications)
        if sections is None:
            logger.warning("falling back to simple report assembler", extra={"run_id": self.run_id})
            sections = self._build_report_simple(prompt, scope, findings, tasks, verifications)
        # Persist generated markdown so the download endpoint can serve the
        # exact file ReportAgent produced (or our fallback equivalent).
        report_path = os.path.join(STATE_DIR, f"report-{self.run_id}.md")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(_assemble_markdown(self.run_id, sections))
        except Exception:
            report_path = None

        section_titles = [s["title"] for s in sections]
        self._patch(lambda r, st=section_titles, p=report_path: (
            r.update({
                "report": {
                    "filename": f"pdca-report-{self.run_id}.md",
                    "status": "ready",
                    "generatedAt": _iso(),
                    "runId": self.run_id,
                    "version": "0.1.0",
                    "sections": sections,
                    "_path": p,
                },
            }),
            _finish_node(r, "completed", f"{len(sections)} sections"),
            _add_message(r, [{
                "kind": "report_ready",
                "filename": f"pdca-report-{self.run_id}.md",
                "includes": st,
            }]),
        ))


    # ─── Report builders ──────────────────────────────────────────────
    def _build_report_via_agent(
        self, prompt: str, scope: Optional[str],
        findings: List[Dict[str, Any]],
        tasks: List[Dict[str, Any]],
        verifications: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        """Call the real `ReportAgent` (executive report + RAG context).
        Returns parsed `sections` list, or None on failure."""
        try:
            # Lazy imports — keep the module loadable on systems where
            # langchain-ollama / RAG aren't installed.
            from pdca.agents.report_agent import ReportAgent
            from pdca.agents.report_module.data_builder import ReportDataBuilder
            from pdca.agents.shared.rag_client import RAGClient
        except Exception as e:
            logger.warning("ReportAgent import failed", extra={"err": str(e)})
            return None

        # Build pre/post stats from current state.
        pre_pass = sum(1 for f in findings if f.get("status") == "PASS")
        pre_fail = sum(1 for f in findings if f.get("status") == "FAIL")
        manual   = sum(1 for f in findings if f.get("status") == "MANUAL")
        sev_count = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in findings:
            s = (f.get("severity") or "").lower()
            if s in sev_count:
                sev_count[s] += 1
        fixed = sum(1 for v in verifications if v.get("result") == "passed")
        failed_remed = sum(1 for v in verifications if v.get("result") == "failed")

        analysis_results = {
            "pre_stats":  {"total": len(findings), "pass": pre_pass, "fail": pre_fail, "severity": sev_count},
            "post_stats": {"pass": pre_pass + fixed, "fail": pre_fail - fixed},
            "remediation_stats": {"fixed": fixed, "failed": failed_remed, "manual": manual},
            "raw_pre_findings": [
                {**f, "compliance": f.get("compliance", [])}
                for f in findings
            ],
            "findings_table": [
                {
                    "check_id": f["prowlerCheckId"],
                    "service": f.get("service"),
                    "resource_id": f["resource"],
                    "region": f.get("region"),
                    "severity": (f.get("severity") or "").lower(),
                    "status": f.get("status"),
                    "description": f.get("description"),
                }
                for f in findings
            ],
            "success_findings": [f for f in findings if f.get("status") == "PASS"],
            "failed_findings":  [f for f in findings if f.get("status") == "FAIL"],
            "manual_findings":  [f for f in findings if f.get("status") == "MANUAL"],
        }

        run = STORE.get(self.run_id) or {}
        env = run.get("awsEnvironment") or {}
        aws_context = {
            "account_id": env.get("accountMask", "Unknown"),
            "region": env.get("region", settings.aws_default_region),
            "buckets": [],
        }

        plan = {"target_services": [run.get("_group", "s3")]}

        # Build context (this fetches RAG via the supplied client).
        rag_client = None
        try:
            rag_client = RAGClient(base_url=os.getenv("RAG_API_URL") or settings.rag_api_url)
        except Exception as e:
            logger.warning("RAGClient init failed; proceeding without RAG", extra={"err": str(e)})

        try:
            data_ctx = ReportDataBuilder.build({
                "analysis_results": analysis_results,
                "raw_findings": findings,
                "aws_context": aws_context,
                "assessment_plan": plan,
                "user_request": prompt or f"Scan {run.get('_group','s3')}",
            }, rag_client=rag_client)
        except Exception:
            logger.exception("ReportDataBuilder.build failed")
            return None

        try:
            agent = ReportAgent(
                model=os.getenv("OLLAMA_MODEL") or settings.ollama_model,
                base_url=os.getenv("OLLAMA_BASE_URL") or settings.ollama_base_url,
                output_path=os.path.join(STATE_DIR, f"report-{self.run_id}-agent.md"),
            )
            result = agent.run(data=data_ctx)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error("ReportAgent.run failed: %s\n%s", e, tb)
            return None

        md_path = result.get("markdown") or result.get("path") if isinstance(result, dict) else None
        if not md_path or not os.path.exists(md_path):
            return None

        # Parse the produced markdown into our `sections` shape (split on `## `).
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return None
        return _split_markdown_sections(content)

    def _build_report_simple(
        self, prompt: str, scope: Optional[str],
        findings: List[Dict[str, Any]],
        tasks: List[Dict[str, Any]],
        verifications: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return [
            {"id": "cover", "title": "Cover",
             "body": f"PDCA Prowler Agent · run {self.run_id}\nGenerated: {_iso()}"},
            {"id": "executive_summary", "title": "Executive Summary",
             "body": f"User request: {prompt}\nScope: {scope or 'default'}\n"
                     f"Total findings: {len(findings)} · "
                     f"FAIL: {sum(1 for f in findings if f['status']=='FAIL')} · "
                     f"PASS: {sum(1 for f in findings if f['status']=='PASS')}"},
            {"id": "findings", "title": "Findings",
             "body": "\n".join(
                 f"- [{(f.get('severity') or '').upper()}] {f['prowlerCheckId']} · "
                 f"{f['resource']} · {f['status']}"
                 for f in findings[:50]) or "(none)"},
            {"id": "remediation_decisions", "title": "Remediation Decisions",
             "body": "\n".join(
                 f"- {t['toolName']} on {t['resource']} → {t['decision']}"
                 for t in tasks) or "(none)"},
            {"id": "verification_results", "title": "Verification",
             "body": "\n".join(
                 f"- {v['toolName']} → {v['result']} ({v['beforeState']}→{v['afterState']})"
                 for v in verifications) or "(none)"},
            {"id": "conclusion", "title": "Conclusion",
             "body": f"{sum(1 for v in verifications if v['result']=='passed')} "
                     f"of {len(verifications)} remediations verified."},
        ]


# ─── Markdown helpers ──────────────────────────────────────────────────────
def _slugify(s: str) -> str:
    out = []
    for c in s.lower():
        if c.isalnum():
            out.append(c)
        elif c in (" ", "-", "_"):
            out.append("_")
    return "".join(out).strip("_") or "section"


def _split_markdown_sections(md: str) -> List[Dict[str, Any]]:
    """Parse a markdown document into the FE `sections` shape.

    Splits on top-level `## ` headings; treats anything before the first one
    as a `cover` section.
    """
    lines = md.splitlines()
    sections: List[Dict[str, Any]] = []
    current_title: Optional[str] = None
    buf: List[str] = []
    cover_buf: List[str] = []

    def flush():
        nonlocal buf, current_title
        if current_title is not None:
            sections.append({
                "id": _slugify(current_title),
                "title": current_title,
                "body": "\n".join(buf).strip(),
            })
        buf = []

    for line in lines:
        if line.startswith("## "):
            flush()
            current_title = line[3:].strip()
            continue
        if current_title is None:
            cover_buf.append(line)
        else:
            buf.append(line)
    flush()

    cover_body = "\n".join(cover_buf).strip()
    if cover_body:
        sections.insert(0, {"id": "cover", "title": "Cover", "body": cover_body})
    return sections or [{"id": "report", "title": "Report", "body": md}]


def _assemble_markdown(run_id: str, sections: List[Dict[str, Any]]) -> str:
    parts = [f"# PDCA Prowler Agent — Report\n", f"_Run: `{run_id}`_\n"]
    for s in sections:
        parts.append(f"\n## {s['title']}\n\n{s['body']}\n")
    return "\n".join(parts)


# ─── Public functions used by HTTP routes ──────────────────────────────────
def start_run(prompt: str, scope: Optional[str], group: str) -> str:
    run_id = _new_id("run")
    thread_id = _new_id("thread")
    started_at = _iso()

    def init(r):
        r.update({
            "id": run_id,
            "threadId": thread_id,
            "status": "idle",
            "startedAt": started_at,
            "currentNode": "environment",
            "checkpointer": "json",
            "lastCheckpointAt": started_at,
            "awsEnvironment": {},
            "graphNodes": [],
            "scanJobs": [],
            "toolCalls": [],
            "evidence": [],
            "findings": [],
            "remediationTasks": [],
            "executionLogs": [],
            "verifications": [],
            "messages": [{
                "id": _new_id("m"),
                "role": "user",
                "timestamp": started_at,
                "text": prompt,
            }],
            "report": {
                "filename": "", "status": "pending", "runId": run_id,
                "version": "0.1.0", "sections": [],
            },
            "_prompt": prompt, "_scope": scope, "_group": group,
        })

    STORE.update(run_id, init)

    def _worker():
        RunOrchestrator(run_id).run(prompt, scope, group)

    t = threading.Thread(target=_worker, daemon=True, name=f"run-{run_id}")
    t.start()
    return run_id


def list_run_ids() -> List[str]:
    return STORE.all_ids()


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    return STORE.get(run_id)


def set_decision(run_id: str, task_id: str, decision: str) -> bool:
    if decision not in ("approved", "rejected", "skipped"):
        return False
    found = {"v": False}

    def upd(r):
        for t in r.get("remediationTasks", []):
            if t["id"] == task_id:
                t["decision"] = decision
                found["v"] = True
                _add_message(r, [{
                    "kind": "remediation_execution",
                    "taskId": task_id,
                    "toolName": t["toolName"],
                    "decision": decision,
                    "status": "success" if decision == "approved" else "failed",
                    "guardChecks": t["guardChecks"],
                }])
                break
    STORE.update(run_id, upd)
    return found["v"]


# ─── Group inference from prompt ───────────────────────────────────────────
KNOWN_GROUPS = {
    "s3", "iam", "ec2", "rds", "kms", "ecr", "vpc",
    "cloudtrail", "guardduty",
}


def infer_group(prompt: str, default: str = "s3") -> str:
    lower = prompt.lower()
    for g in KNOWN_GROUPS:
        if re.search(rf"\b{g}\b", lower):
            return g
    return default
