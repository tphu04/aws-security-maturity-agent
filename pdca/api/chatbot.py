"""Chatbot orchestration API — Sprint 2b scaffold.

Goal: expose a UI-friendly surface that wraps the LangGraph PDCA pipeline.
For now this module provides:

- `GET /v1/environment` — AWS connection status + RAG reachability.
- `POST /v1/runs`        — register a new run (stub: returns a run_id).
- `GET  /v1/runs`        — list runs (currently delegates to the scanner job DB
                           so the History view has real data to render).
- `GET  /v1/runs/{id}`   — fetch a single run snapshot. While the LangGraph
                           wrapper is not yet built, this returns either a
                           known job projected to a minimal RunSession or 404.

The real LangGraph driver (background task, checkpoints, SSE stream, HITL
approvals) is intentionally not implemented here — that is Sprint 3+. The
adapter layer in the frontend is structured so wiring it later requires no
view changes.
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pdca.api.run_orchestrator import (
    get_run as orch_get_run,
    infer_group,
    list_run_ids,
    set_decision,
    start_run,
)
from pdca.config import settings
from pdca.observability.logger import get_logger

load_dotenv()
logger = get_logger("pdca.api.chatbot")

# Reuse the scanner's job DB so /v1/runs surfaces the same history users see
# in the existing /v1/jobs endpoint. When the LangGraph driver lands it will
# write to its own runs table; the history view will continue to work.
JOB_DB_PATH = "data/jobs/scanner_jobs.db"
RUNS_DB_PATH = "data/runs/chatbot_runs.db"


# ---------------------------------------------------------------------------
# Lightweight runs DB
# ---------------------------------------------------------------------------
def _init_runs_db() -> None:
    os.makedirs(os.path.dirname(RUNS_DB_PATH), exist_ok=True)
    with sqlite3.connect(RUNS_DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id     TEXT PRIMARY KEY,
                thread_id  TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'idle',
                prompt     TEXT,
                scope      TEXT,
                started_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )


@contextmanager
def _runs_db():
    conn = sqlite3.connect(RUNS_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


_init_runs_db()


# ---------------------------------------------------------------------------
# Models — kept loose; FE owns the canonical RunSession shape.
# ---------------------------------------------------------------------------
class CreateRunRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    scope: Optional[str] = None  # e.g. "S3 only" | "Full AWS account"


class CreateRunResponse(BaseModel):
    run_id: str
    thread_id: str
    status: str = "idle"


class EnvironmentResponse(BaseModel):
    status: str   # not_connected | validating | connected | error | expired_session | missing_permissions
    accountMask: str
    region: str
    credentialType: str
    lastValidatedAt: str
    bucketsDiscovered: int
    ragAvailable: bool


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/v1", tags=["chatbot"])


# ---- Environment probe ----------------------------------------------------
def _mask_account(account_id: Optional[str]) -> str:
    if not account_id:
        return "————"
    s = str(account_id)
    if len(s) < 6:
        return s
    return s[:4] + "•" * (len(s) - 6) + s[-2:]


def _probe_aws() -> Dict[str, Any]:
    """Best-effort AWS env check. Never raises — returns a status dict."""
    region = settings.aws_default_region
    profile = settings.aws_profile

    # Honor explicit env-var creds first; fall back to the profile.
    try:
        if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
            session = boto3.Session(region_name=region)
            credential_type = "Access key (env)"
        else:
            session = boto3.Session(profile_name=profile, region_name=region)
            credential_type = f"Profile: {profile}"
    except BotoCoreError as e:
        return {
            "status": "not_connected",
            "accountMask": "————",
            "region": region,
            "credentialType": "(unconfigured)",
            "bucketsDiscovered": 0,
            "error": str(e),
        }

    try:
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        account = identity.get("Account")
    except NoCredentialsError:
        return {
            "status": "not_connected",
            "accountMask": "————",
            "region": region,
            "credentialType": credential_type,
            "bucketsDiscovered": 0,
        }
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        status = "expired_session" if "Expired" in code else "error"
        return {
            "status": status,
            "accountMask": "————",
            "region": region,
            "credentialType": credential_type,
            "bucketsDiscovered": 0,
            "error": str(e),
        }

    buckets = 0
    try:
        s3 = session.client("s3")
        resp = s3.list_buckets()
        buckets = len(resp.get("Buckets", []))
    except ClientError as e:
        # Don't fail the whole probe just because s3:ListAllMyBuckets is missing.
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


@router.get("/environment", response_model=EnvironmentResponse)
def get_environment() -> EnvironmentResponse:
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


# ---- Runs (scaffold) ------------------------------------------------------
def _new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


class ApprovalRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected|skipped)$")


@router.post("/runs", response_model=CreateRunResponse)
def create_run(payload: CreateRunRequest) -> CreateRunResponse:
    """Start a real PDCA run end-to-end (scan → plan → HITL → execute → report)."""
    group = infer_group(payload.prompt, default="s3")
    run_id = start_run(prompt=payload.prompt, scope=payload.scope, group=group)
    logger.info(
        "run started",
        extra={"run_id": run_id, "scope": payload.scope, "group": group},
    )
    return CreateRunResponse(run_id=run_id, thread_id=f"thread_{run_id[4:]}")


@router.post("/runs/{run_id}/approvals/{task_id}")
def post_approval(run_id: str, task_id: str, payload: ApprovalRequest) -> Dict[str, Any]:
    if not orch_get_run(run_id):
        raise HTTPException(status_code=404, detail="run not found")
    ok = set_decision(run_id, task_id, payload.decision)
    if not ok:
        raise HTTPException(status_code=404, detail="task not found")
    return {"ok": True, "decision": payload.decision}


@router.get("/runs")
def list_runs(limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """List runs. Combines orchestrator runs with scanner-job rows so the
    History view has real data."""
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit phải trong [1, 500].")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset phải >= 0.")

    items: List[Dict[str, Any]] = []
    for rid in list_run_ids():
        run = orch_get_run(rid)
        if not run:
            continue
        items.append({
            "id": run["id"],
            "target": run.get("_scope") or (run.get("_prompt") or "")[:80] or "scan",
            "status": run.get("status", "idle"),
            "startedAt": run.get("startedAt", _ts(time.time())),
            "durationMs": 0,
            "findingsTotal": len(run.get("findings", [])),
            "remediated": sum(
                1 for v in run.get("verifications", []) if v.get("result") == "passed"
            ),
            "reportStatus": (run.get("report") or {}).get("status", "pending"),
            "awsAccountMask": (run.get("awsEnvironment") or {}).get("accountMask", "————"),
            "kind": "run",
        })

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


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    run = orch_get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Không tìm thấy run.")
    # Strip private (underscore-prefixed) fields before returning.
    return {k: v for k, v in run.items() if not k.startswith("_")}


def _ts(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


# ---------------------------------------------------------------------------
# App factory — runs standalone on port 8002 by default.
# ---------------------------------------------------------------------------
app = FastAPI(title="PDCA Chatbot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Chatbot API on 127.0.0.1:8002")
    uvicorn.run("pdca.api.chatbot:app", host="127.0.0.1", port=8002, reload=True)
