"""Scanner tools — gọi Prowler scanner HTTP API.

URL đọc từ `settings.scanner_api_url`. Endpoints (Phase D2):
- POST `/v1/scan/group`     (body: {group})
- POST `/v1/scan/checks`    (body: {check_ids})
- GET  `/v1/job/{job_id}`
"""

from __future__ import annotations

import requests
from langchain_core.tools import tool

from pdca.config import settings
from pdca.observability.logger import get_logger
from pdca.observability.tracing import span as obs_span
from pdca.tools.registry import REGISTRY
from pdca.tools.schemas import JobStatusInput, ScanChecksInput, ScanGroupInput

logger = get_logger(__name__)


def _api_url() -> str:
    return settings.scanner_api_url


@tool(args_schema=ScanChecksInput)
def start_scan_by_check_ids(check_ids: str) -> dict:
    """[TOOL] Quét hệ thống AWS theo các Check ID cụ thể (nhanh hơn quét Group).
    Dùng tool này khi người dùng chỉ định rõ vấn đề (vd: logging, mfa, encryption).
    """
    logger.info(
        "Calling scanner API",
        extra={"endpoint": "/v1/scan/checks", "check_ids": check_ids},
    )
    with obs_span(
        "scanner:start_scan_by_check_ids", input={"check_ids": check_ids}
    ) as sp:
        try:
            resp = requests.post(
                f"{_api_url()}/v1/scan/checks",
                json={"check_ids": check_ids},
                timeout=settings.rag_timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()
            sp.update(output={"http_status": resp.status_code, "ok": True})
            return data
        except Exception as e:
            sp.set_status("error", str(e))
            return {"success": False, "error": str(e)}


@tool(args_schema=ScanGroupInput)
def start_scan_by_group(group: str) -> dict:
    """[TOOL] Bắt đầu một công việc quét tài khoản AWS theo TÊN SERVICE."""
    logger.info(
        "Calling scanner API",
        extra={"endpoint": "/v1/scan/group", "group": group},
    )
    with obs_span("scanner:start_scan_by_group", input={"group": group}) as sp:
        try:
            resp = requests.post(
                f"{_api_url()}/v1/scan/group",
                json={"group": group},
                timeout=settings.rag_timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()
            sp.update(
                output={
                    "http_status": resp.status_code,
                    "job_id_present": bool(data.get("job_id")),
                }
            )
            return {
                "job_id": data.get("job_id"),
                "success": True,
                "data": data,
                "status_code": resp.status_code,
            }
        except Exception as e:
            sp.set_status("error", str(e))
            return {"success": False, "error": str(e)}


@tool(args_schema=JobStatusInput)
def check_job_status(job_id: str) -> dict:
    """[TOOL] Kiểm tra trạng thái của một công việc (job) đang chạy."""
    logger.info(
        "Calling scanner API",
        extra={"endpoint": "/v1/job/{job_id}", "job_id": job_id},
    )
    with obs_span("scanner:check_job_status", input={"job_id": job_id}) as sp:
        try:
            resp = requests.get(
                f"{_api_url()}/v1/job/{job_id}",
                timeout=settings.rag_timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()
            sp.update(
                output={"http_status": resp.status_code, "status": data.get("status")}
            )
            return {"success": True, "data": data}
        except Exception as e:
            sp.set_status("error", str(e))
            return {"success": False, "error": str(e)}


REGISTRY.register(start_scan_by_check_ids, category="scanner")
REGISTRY.register(start_scan_by_group, category="scanner")
REGISTRY.register(check_job_status, category="scanner")
