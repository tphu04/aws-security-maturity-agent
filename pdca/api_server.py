"""Scanner HTTP API (Phase D — hardened).

Changes vs legacy:
- POST + `/v1/` prefix for job-creating endpoints (HTTP semantics).
- SQLite-backed job database (`data/jobs/scanner_jobs.db`) — survives restart.
- AWS profile/region read from `pdca.config.settings` (no hardcoded constants).
- Python logging (no `print`). Conditional output-file cleanup.
- CORS middleware (Chatbot UI prerequisite).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from pdca.config import settings
from pdca.observability.logger import get_logger

load_dotenv()
logger = get_logger("pdca.api_server")

CHECKS_DIR = "custom_checks"
JOB_OUTPUT_DIR = "job_outputs"
JOB_DB_PATH = "data/jobs/scanner_jobs.db"

ALLOWED_GROUPS = {
    "accessanalyzer", "account", "acm", "apigateway", "apigatewayv2", "appstream",
    "appsync", "athena", "autoscaling", "awslambda", "backup", "bedrock",
    "cloudformation", "cloudfront", "cloudtrail", "cloudwatch", "codeartifact",
    "codebuild", "cognito", "config", "datasync", "directconnect", "directoryservice",
    "dlm", "dms", "documentdb", "drs", "dynamodb", "ec2", "ecr", "ecs", "efs", "eks",
    "elasticache", "elasticbeanstalk", "elb", "elbv2", "emr", "eventbridge", "firehose",
    "fms", "fsx", "glacier", "glue", "guardduty", "iam", "inspector2", "kafka",
    "kinesis", "kms", "lightsail", "macie", "memorydb", "mq", "neptune",
    "networkfirewall", "opensearch", "organizations", "rds", "redshift",
    "resourceexplorer2", "route53", "s3", "sagemaker", "secretsmanager", "securityhub",
    "servicecatalog", "ses", "shield", "sns", "sqs", "ssm", "ssmincidents",
    "stepfunctions", "storagegateway", "transfer", "trustedadvisor", "vpc", "waf",
    "wafv2", "wellarchitected", "workspaces",
}

os.makedirs(JOB_OUTPUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# SQLite job database (D3)
# ---------------------------------------------------------------------------
def _init_job_db() -> None:
    os.makedirs(os.path.dirname(JOB_DB_PATH), exist_ok=True)
    with sqlite3.connect(JOB_DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id        TEXT PRIMARY KEY,
                status        TEXT NOT NULL DEFAULT 'pending',
                task_type     TEXT,
                task_value    TEXT,
                command_details TEXT,
                submitted_at  REAL,
                started_at    REAL,
                ended_at      REAL,
                duration_s    REAL,
                result_json   TEXT,
                error_json    TEXT,
                summary       TEXT
            )
            """
        )


@contextmanager
def _job_db():
    conn = sqlite3.connect(JOB_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_job(row: sqlite3.Row) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "job_id": row["job_id"],
        "status": row["status"],
        "task_type": row["task_type"],
        "task_value": row["task_value"],
        "command_details": row["command_details"],
        "submitted_time": row["submitted_at"],
        "start_time": row["started_at"],
        "end_time": row["ended_at"],
        "duration_seconds": row["duration_s"],
        "summary_text": row["summary"],
    }
    out["result"] = json.loads(row["result_json"]) if row["result_json"] else None
    out["error"] = json.loads(row["error_json"]) if row["error_json"] else None
    return out


def _insert_job(job_id: str, task_type: str, task_value: str, command_details: str) -> None:
    with _job_db() as conn:
        conn.execute(
            "INSERT INTO jobs (job_id, status, task_type, task_value, "
            "command_details, submitted_at) VALUES (?, 'pending', ?, ?, ?, ?)",
            (job_id, task_type, task_value, command_details, time.time()),
        )


def _update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with _job_db() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE job_id = ?", values)


def _get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _job_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def _list_jobs(limit: int, offset: int) -> List[Dict[str, Any]]:
    with _job_db() as conn:
        rows = conn.execute(
            "SELECT job_id, status, command_details, submitted_at "
            "FROM jobs ORDER BY submitted_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [
        {
            "job_id": r["job_id"],
            "status": r["status"],
            "details": r["command_details"],
            "submitted_time": r["submitted_at"],
        }
        for r in rows
    ]


_init_job_db()


# ---------------------------------------------------------------------------
# FastAPI app + CORS (D4)
# ---------------------------------------------------------------------------
app = FastAPI(title="PDCA Scanner API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Validation — argument-injection defence
# ---------------------------------------------------------------------------
# Prowler check IDs and service names are lowercase snake_case. Anything else
# (whitespace, dashes, leading `-`, glob chars) is a sign of injection attempt.
_TOKEN_RE = re.compile(r"^[a-z0-9_]+$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_token(value: str, field: str) -> str:
    v = value.strip()
    if not v:
        raise ValueError(f"{field} rỗng.")
    if not _TOKEN_RE.fullmatch(v):
        raise ValueError(
            f"{field} chứa ký tự không hợp lệ (chỉ a-z, 0-9, _): {value!r}"
        )
    return v


def _parse_check_ids(raw: str) -> List[str]:
    """Split comma/space separated string into validated check-id tokens."""
    parts = [p for p in re.split(r"[,\s]+", raw.strip()) if p]
    if not parts:
        raise ValueError("check_ids rỗng.")
    return [_validate_token(p, "check_id") for p in parts]


# ---------------------------------------------------------------------------
# Request models (D2.1)
# ---------------------------------------------------------------------------
class ScanGroupRequest(BaseModel):
    group: str = Field(..., description="AWS service group, e.g. 's3'.")

    @field_validator("group")
    @classmethod
    def _check_group(cls, v: str) -> str:
        return _validate_token(v, "group")


class ScanChecksRequest(BaseModel):
    check_ids: str = Field(..., description="Comma-separated Prowler check IDs.")

    @field_validator("check_ids")
    @classmethod
    def _check_ids(cls, v: str) -> str:
        # Re-emit canonical comma-separated form after validation.
        return ",".join(_parse_check_ids(v))


class ScanCustomRequest(BaseModel):
    filename: str = Field(..., description="Custom checks JSON filename in CHECKS_DIR.")

    @field_validator("filename")
    @classmethod
    def _check_filename(cls, v: str) -> str:
        v = v.strip()
        if not _FILENAME_RE.fullmatch(v):
            raise ValueError("filename chứa ký tự không hợp lệ.")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def strip_ansi_codes(text: str) -> str:
    if not text:
        return ""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def _new_job_id() -> str:
    return f"job_{str(uuid.uuid4())[:8]}"


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
def _run_prowler_command_worker(job_id: str) -> None:
    job_info = _get_job(job_id)
    if not job_info:
        logger.error("worker: job not found", extra={"job_id": job_id})
        return

    started_at = time.time()
    _update_job(job_id, status="running", started_at=started_at)

    # Settings are operator-controlled but validate anyway — argv hygiene.
    profile_re = re.compile(r"^[A-Za-z0-9_.@-]+$")
    region_re = re.compile(r"^[a-z0-9-]+$")
    profile = settings.aws_profile
    region = settings.aws_default_region
    if not profile_re.fullmatch(profile) or not region_re.fullmatch(region):
        logger.error(
            "worker: invalid aws profile/region in settings",
            extra={"job_id": job_id, "profile": profile, "region": region},
        )
        _update_job(
            job_id,
            status="failed",
            ended_at=time.time(),
            error_json=json.dumps({"error": "invalid aws profile/region"}),
        )
        return
    task_type = job_info.get("task_type")
    task_value = job_info.get("task_value") or ""
    output_filename = job_id

    # Build argv list directly (no shell, no shlex). Re-validate task_value at
    # worker boundary as defence-in-depth — DB row could be tampered with.
    # PROWLER_PYTHON env var lets ops point at a separate interpreter that has
    # Prowler installed (Prowler 5.x requires Python <= 3.12, while the rest
    # of the project may run on Python 3.13).
    prowler_python = os.getenv("PROWLER_PYTHON", sys.executable)
    if not os.path.isfile(prowler_python):
        logger.error(
            "PROWLER_PYTHON does not point to a real interpreter",
            extra={"job_id": job_id, "path": prowler_python},
        )
        _update_job(
            job_id,
            status="failed",
            ended_at=time.time(),
            error_json=json.dumps({"error": f"PROWLER_PYTHON invalid: {prowler_python}"}),
        )
        return
    argv: List[str] = [
        prowler_python, "-m", "prowler", "aws",
        "--profile", profile,
        "--region", region,
        "--output-mode", "json-ocsf",
        "--ignore-exit-code-3",
        "--no-color",
    ]
    try:
        if task_type == "group":
            argv += ["--services", _validate_token(task_value, "group")]
        elif task_type == "custom_file":
            tokens = _parse_check_ids(task_value)
            argv += ["--check", *tokens]
    except ValueError as e:
        logger.error(
            "worker: invalid task_value rejected",
            extra={"job_id": job_id, "task_value": task_value, "error": str(e)},
        )
        _update_job(
            job_id,
            status="failed",
            ended_at=time.time(),
            error_json=json.dumps({"error": "invalid task_value", "details": str(e)}),
        )
        return

    argv += [
        "--output-directory", JOB_OUTPUT_DIR,
        "--output-filename", output_filename,
    ]
    full_output_path = os.path.join(JOB_OUTPUT_DIR, f"{output_filename}.ocsf.json")

    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = os.getenv("AWS_ACCESS_KEY_ID", "")
    env["AWS_SECRET_ACCESS_KEY"] = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["LC_ALL"] = "C.UTF-8"
    env["LANG"] = "C.UTF-8"

    try:
        logger.info("prowler start", extra={"job_id": job_id, "argv": argv})
        result = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            check=True,
            timeout=1800,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        text_summary = strip_ansi_codes(result.stdout)
        findings_data: List[Any] = []

        if os.path.exists(full_output_path):
            try:
                with open(full_output_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if content:
                    findings_data = json.loads(content)
                    if not isinstance(findings_data, list):
                        findings_data = [findings_data]
                logger.info(
                    "prowler output parsed",
                    extra={"job_id": job_id, "finding_count": len(findings_data)},
                )
            except json.JSONDecodeError as e:
                logger.error(
                    "OCSF JSON decode failed",
                    extra={"job_id": job_id, "error": str(e)},
                )
            except Exception as e:
                logger.error(
                    "OCSF read failed",
                    extra={"job_id": job_id, "error": str(e)},
                )
        else:
            logger.error(
                "OCSF file missing",
                extra={"job_id": job_id, "path": full_output_path},
            )

        ended_at = time.time()
        _update_job(
            job_id,
            status="completed",
            ended_at=ended_at,
            duration_s=ended_at - started_at,
            result_json=json.dumps(findings_data),
            summary=text_summary,
        )

    except subprocess.TimeoutExpired:
        logger.error("prowler timeout", extra={"job_id": job_id})
        _update_job(
            job_id,
            status="failed",
            ended_at=time.time(),
            error_json=json.dumps({"error": "Scan timed out (30 minutes)"}),
        )
    except subprocess.CalledProcessError as e:
        logger.error("prowler failed", extra={"job_id": job_id, "rc": e.returncode})
        _update_job(
            job_id,
            status="failed",
            ended_at=time.time(),
            error_json=json.dumps(
                {
                    "error": "Prowler chạy bị lỗi (CalledProcessError)",
                    "stdout_details": strip_ansi_codes(e.stdout or ""),
                    "stderr_details": strip_ansi_codes(e.stderr or ""),
                }
            ),
        )
    except Exception as e:
        logger.exception("prowler unknown error", extra={"job_id": job_id})
        _update_job(
            job_id,
            status="failed",
            ended_at=time.time(),
            error_json=json.dumps({"error": "Lỗi không xác định", "details": str(e)}),
        )
    finally:
        if settings.cleanup_scan_output and os.path.exists(full_output_path):
            try:
                os.remove(full_output_path)
                logger.info(
                    "output cleaned",
                    extra={"job_id": job_id, "path": full_output_path},
                )
            except Exception as e:
                logger.warning(
                    "cleanup failed",
                    extra={"job_id": job_id, "error": str(e)},
                )


# ---------------------------------------------------------------------------
# Endpoints (D2)
# ---------------------------------------------------------------------------
@app.post("/v1/scan/group")
def run_simple_scan(payload: ScanGroupRequest, tasks: BackgroundTasks):
    if payload.group not in ALLOWED_GROUPS:
        raise HTTPException(
            status_code=400, detail=f"Nhóm '{payload.group}' không được phép."
        )
    job_id = _new_job_id()
    _insert_job(
        job_id,
        task_type="group",
        task_value=payload.group,
        command_details=f"scan group: {payload.group}",
    )
    tasks.add_task(_run_prowler_command_worker, job_id)
    logger.info("job queued (group)", extra={"job_id": job_id, "group": payload.group})
    return {"status": "pending", "job_id": job_id, "message": "Scan job đã được bắt đầu."}


@app.post("/v1/scan/checks")
def run_specific_checks(payload: ScanChecksRequest, tasks: BackgroundTasks):
    # payload.check_ids already validated + canonicalized to comma-separated.
    job_id = _new_job_id()
    _insert_job(
        job_id,
        task_type="custom_file",
        task_value=payload.check_ids,
        command_details=f"scan checks: {payload.check_ids}",
    )
    tasks.add_task(_run_prowler_command_worker, job_id)
    logger.info(
        "job queued (checks)", extra={"job_id": job_id, "checks": payload.check_ids}
    )
    return {"status": "pending", "job_id": job_id, "message": "Specific checks scan started"}


@app.post("/v1/scan/custom")
def run_custom_scan(payload: ScanCustomRequest, tasks: BackgroundTasks):
    filename = payload.filename
    full_path = os.path.join(CHECKS_DIR, filename)
    # Resolve to absolute and verify it stays within CHECKS_DIR (defence vs symlink/traversal).
    checks_root = os.path.realpath(CHECKS_DIR)
    full_real = os.path.realpath(full_path)
    if not full_real.startswith(checks_root + os.sep) and full_real != checks_root:
        raise HTTPException(status_code=400, detail="Tên file không hợp lệ.")
    if not os.path.isfile(full_real):
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file check: {filename}")
    try:
        with open(full_real, "r", encoding="utf-8") as f:
            checks_list = json.load(f)
        if not isinstance(checks_list, list) or not checks_list:
            raise HTTPException(
                status_code=400, detail="File JSON phải là một list và không rỗng."
            )
        try:
            validated = [_validate_token(c, "check_id") for c in checks_list]
        except (TypeError, ValueError) as e:
            raise HTTPException(
                status_code=400, detail=f"File chứa check_id không hợp lệ: {e}"
            )
        checks_string = ",".join(validated)
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"File JSON không hợp lệ: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc file JSON: {str(e)}")

    job_id = _new_job_id()
    _insert_job(
        job_id,
        task_type="custom_file",
        task_value=checks_string,
        command_details=f"scan custom file: {filename}",
    )
    tasks.add_task(_run_prowler_command_worker, job_id)
    logger.info(
        "job queued (custom)", extra={"job_id": job_id, "checks_filename": filename}
    )
    return {"status": "pending", "job_id": job_id, "message": "Scan job đã được bắt đầu."}


@app.get("/v1/job/{job_id}")
def get_job_status(job_id: str):
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job ID")
    return job


@app.get("/v1/jobs")
def list_all_jobs(limit: int = 50, offset: int = 0):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit phải trong [1, 500].")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset phải >= 0.")
    return {"items": _list_jobs(limit, offset), "limit": limit, "offset": offset}


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Prowler Scan API server")
    uvicorn.run("pdca.api_server:app", host="127.0.0.1", port=8000, reload=True)
