"""Chatbot orchestration API — Phase D-web.

LangGraph-driven web API. Endpoints:

- `GET  /v1/environment`                       — AWS connection + RAG ping (cached 30s).
- `POST /v1/runs`                              — start a new PDCA run (background daemon thread).
- `GET  /v1/runs`                              — list runs (orchestrator + scanner job DB).
- `GET  /v1/runs/{run_id}`                     — current `RunSession` snapshot.
- `POST /v1/runs/{run_id}/approvals/{task_id}` — record HITL decision + resume graph.
- `GET  /v1/runs/{run_id}/report`              — download markdown / JSON report.

Threading: each run is one daemon thread inside `pdca.api.graph_runtime`.
The chatbot module itself is stateless — all state lives in the LangGraph
`SqliteSaver` checkpointer (`data/checkpoints/pdca_state.db`).
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from pdca.api.graph_runtime import (
    get_run_metadata,
    get_state_history,
    get_state_values,
    list_run_ids,
    resume_after_decision,
    start_run,
)
from pdca.api.state_adapter import to_run_session
from pdca.config import settings
from pdca.observability.logger import get_logger

load_dotenv()
logger = get_logger("pdca.api.chatbot")

# Reuse scanner job DB for History view (combined with orchestrator runs).
JOB_DB_PATH = "data/jobs/scanner_jobs.db"


# ---------------------------------------------------------------------------
# Request / response models — kept loose; FE owns the canonical shape.
# ---------------------------------------------------------------------------
class CreateRunRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    scope: Optional[str] = None


class CreateRunResponse(BaseModel):
    run_id: str
    thread_id: str
    status: str = "idle"


class EnvironmentResponse(BaseModel):
    status: str
    accountMask: str
    region: str
    credentialType: str
    lastValidatedAt: str
    bucketsDiscovered: int
    ragAvailable: bool


class ApprovalRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected|skipped)$")


# ---------------------------------------------------------------------------
# Group inference (lightweight rule — full NLU lives in PlanningAgent)
# ---------------------------------------------------------------------------
_KNOWN_GROUPS = {
    "s3", "iam", "ec2", "rds", "kms", "ecr", "vpc", "cloudtrail", "guardduty",
}


def infer_group(prompt: str, default: str = "s3") -> str:
    lower = (prompt or "").lower()
    for g in _KNOWN_GROUPS:
        if re.search(rf"\b{g}\b", lower):
            return g
    return default


# ---------------------------------------------------------------------------
# AWS environment probe (cached)
# ---------------------------------------------------------------------------
def _mask_account(account_id: Optional[str]) -> str:
    if not account_id:
        return "————"
    s = str(account_id)
    if len(s) < 6:
        return s
    return s[:4] + "•" * (len(s) - 6) + s[-2:]


def _probe_aws() -> Dict[str, Any]:
    region = settings.aws_default_region
    profile = settings.aws_profile
    try:
        if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
            session = boto3.Session(region_name=region)
            credential_type = "Access key (env)"
        else:
            session = boto3.Session(profile_name=profile, region_name=region)
            credential_type = f"Profile: {profile}"
    except BotoCoreError as e:
        return {
            "status": "not_connected", "accountMask": "————", "region": region,
            "credentialType": "(unconfigured)", "bucketsDiscovered": 0,
            "error": str(e),
        }

    try:
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        account = identity.get("Account")
    except NoCredentialsError:
        return {
            "status": "not_connected", "accountMask": "————", "region": region,
            "credentialType": credential_type, "bucketsDiscovered": 0,
        }
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        status = "expired_session" if "Expired" in code else "error"
        return {
            "status": status, "accountMask": "————", "region": region,
            "credentialType": credential_type, "bucketsDiscovered": 0,
            "error": str(e),
        }

    buckets = 0
    try:
        s3 = session.client("s3")
        resp = s3.list_buckets()
        buckets = len(resp.get("Buckets", []))
    except ClientError as e:
        logger.warning("list_buckets failed during /v1/environment", extra={"error": str(e)})

    return {
        "status": "connected",
        "accountMask": _mask_account(account),
        "region": region,
        "credentialType": credential_type,
        "bucketsDiscovered": buckets,
    }


def _probe_rag() -> bool:
    try:
        with httpx.Client(timeout=2.5) as c:
            r = c.get(settings.rag_api_url.rstrip("/") + "/")
            return r.status_code == 200
    except Exception:
        return False


_ENV_CACHE: Dict[str, Any] = {"value": None, "ts": 0.0}
_ENV_TTL_S = 30.0


def _cached_environment() -> EnvironmentResponse:
    now = time.time()
    if _ENV_CACHE["value"] is not None and now - _ENV_CACHE["ts"] < _ENV_TTL_S:
        return _ENV_CACHE["value"]
    aws = _probe_aws()
    rag_up = _probe_rag()
    resp = EnvironmentResponse(
        status=aws["status"],
        accountMask=aws["accountMask"],
        region=aws["region"],
        credentialType=aws["credentialType"],
        lastValidatedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        bucketsDiscovered=aws.get("bucketsDiscovered", 0),
        ragAvailable=rag_up,
    )
    _ENV_CACHE["value"] = resp
    _ENV_CACHE["ts"] = now
    return resp


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/v1", tags=["chatbot"])


@router.get("/environment", response_model=EnvironmentResponse)
def get_environment() -> EnvironmentResponse:
    return _cached_environment()


@router.post("/runs", response_model=CreateRunResponse)
def create_run(payload: CreateRunRequest) -> CreateRunResponse:
    group = infer_group(payload.prompt, default="s3")
    res = start_run(prompt=payload.prompt, scope=payload.scope, group=group)
    logger.info(
        "run started",
        extra={"run_id": res["run_id"], "thread_id": res["thread_id"], "scope": payload.scope, "group": group},
    )
    return CreateRunResponse(run_id=res["run_id"], thread_id=res["thread_id"])


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    snapshot = get_state_values(run_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Không tìm thấy run.")
    history = get_state_history(run_id, limit=200)

    # Overlay accountMask + lastValidatedAt from the env probe cache so the
    # FE Settings panel shows fresh data even before the run reaches
    # `environment_node`.
    env_extras: Dict[str, Any] = {}
    cached_env = _ENV_CACHE.get("value")
    if cached_env is not None:
        env_extras = {
            "accountMask": cached_env.accountMask,
            "credentialType": cached_env.credentialType,
            "lastValidatedAt": cached_env.lastValidatedAt,
        }
    return to_run_session(run_id, snapshot, history, aws_environment_extras=env_extras)


@router.post("/runs/{run_id}/approvals/{task_id}")
def post_approval(run_id: str, task_id: str, payload: ApprovalRequest) -> Dict[str, Any]:
    snapshot = get_state_values(run_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="run not found")
    ok = resume_after_decision(run_id, task_id, payload.decision)
    if not ok:
        raise HTTPException(status_code=409, detail="run not waiting for approval or task unknown")
    return {"ok": True, "decision": payload.decision}


@router.get("/runs/{run_id}/report")
def get_report(run_id: str, format: str = "markdown") -> Any:
    """Return the run's report. format=markdown (default) → text/markdown
    download; format=json → structured sections list."""
    snapshot = get_state_values(run_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="run not found")
    values = snapshot.get("values") or {}
    final_report = values.get("final_report")
    # ReportAgent.run() returns {"markdown": path, "html": ..., "pdf": ..., "validation_report": ...}
    # Older code paths may store a bare path string — handle both.
    if isinstance(final_report, dict):
        report_path = final_report.get("markdown")
    else:
        report_path = final_report
    if not report_path or not isinstance(report_path, str) or not os.path.exists(report_path):
        raise HTTPException(status_code=409, detail="report not ready")

    if format == "json":
        # Reuse adapter — it produces the same `sections[]` shape.
        rs = to_run_session(run_id, snapshot, get_state_history(run_id, limit=10))
        return rs.get("report") or {}

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"could not read report: {e}")

    return PlainTextResponse(
        content,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=pdca-report-{run_id}.md"},
    )


@router.get("/runs")
def list_runs(limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit phải trong [1, 500].")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset phải >= 0.")

    items: List[Dict[str, Any]] = []

    # Active runs (orchestrator-driven).
    for rid in list_run_ids():
        snapshot = get_state_values(rid)
        if not snapshot:
            continue
        rs = to_run_session(rid, snapshot, [])  # skip history for list view
        meta = get_run_metadata(rid) or {}
        started_at = rs.get("startedAt") or _ts(meta.get("started_at", time.time()))
        items.append({
            "id": rs["id"],
            "target": meta.get("scope") or (meta.get("prompt") or "")[:80] or rs["currentNode"],
            "status": rs["status"],
            "startedAt": started_at,
            "durationMs": 0,
            "findingsTotal": len(rs.get("findings") or []),
            "remediated": sum(
                1 for v in rs.get("verifications") or [] if v.get("result") == "passed"
            ),
            "reportStatus": (rs.get("report") or {}).get("status", "pending"),
            "awsAccountMask": (rs.get("awsEnvironment") or {}).get("accountMask", "————"),
            "kind": "run",
        })

    # Legacy scanner-only jobs (combined for History view).
    if os.path.exists(JOB_DB_PATH):
        with sqlite3.connect(JOB_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            jrows = conn.execute(
                "SELECT job_id, status, command_details, submitted_at, ended_at, "
                "duration_s FROM jobs ORDER BY submitted_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        for j in jrows:
            items.append({
                "id": j["job_id"],
                "target": j["command_details"],
                "status": j["status"],
                "startedAt": _ts(j["submitted_at"]),
                "durationMs": int((j["duration_s"] or 0) * 1000),
                "findingsTotal": 0,
                "remediated": 0,
                "reportStatus": "pending",
                "awsAccountMask": "————",
                "kind": "scan_job",
            })

    items.sort(key=lambda x: x["startedAt"], reverse=True)
    return {"items": items[offset:offset + limit], "limit": limit, "offset": offset}


def _ts(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch or 0)))


# ---------------------------------------------------------------------------
# App factory — runs standalone on port 9002 by default.
# ---------------------------------------------------------------------------
app = FastAPI(title="PDCA Chatbot API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.on_event("startup")
def _warmup() -> None:
    """Eager-build the graph singleton + warm env probe so first POST /v1/runs
    isn't slow."""
    from pdca.api.graph_runtime import get_app
    get_app()
    _cached_environment()
    logger.info("Chatbot API ready (graph compiled, env probed)")


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Chatbot API on 127.0.0.1:9002")
    uvicorn.run("pdca.api.chatbot:app", host="127.0.0.1", port=9002, reload=True)
