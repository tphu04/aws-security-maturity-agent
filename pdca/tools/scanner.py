"""Scanner tools — gọi Prowler scanner HTTP API (B13).

URL đọc từ `settings.scanner_api_url` (B2). Bỏ `start_scan_by_file` (B18 —
zero-usage trong pipeline).
"""

from __future__ import annotations

import requests
from langchain_core.tools import tool

from pdca.config import settings
from pdca.observability.logger import get_logger
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
    logger.info("Calling scanner API",
                extra={"endpoint": "/scan/specific", "check_ids": check_ids})
    try:
        resp = requests.get(
            f"{_api_url()}/scan/specific", params={"check_ids": check_ids},
            timeout=settings.rag_timeout_s,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool(args_schema=ScanGroupInput)
def start_scan_by_group(group: str) -> dict:
    """[TOOL] Bắt đầu một công việc quét tài khoản AWS theo TÊN SERVICE."""
    logger.info("Calling scanner API",
                extra={"endpoint": "/scan/check", "group": group})
    try:
        resp = requests.get(
            f"{_api_url()}/scan/check", params={"group": group},
            timeout=settings.rag_timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "job_id": data.get("job_id"),
            "success": True,
            "data": data,
            "status_code": resp.status_code,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool(args_schema=JobStatusInput)
def check_job_status(job_id: str) -> dict:
    """[TOOL] Kiểm tra trạng thái của một công việc (job) đang chạy."""
    logger.info("Calling scanner API",
                extra={"endpoint": "/job/status", "job_id": job_id})
    try:
        resp = requests.get(
            f"{_api_url()}/job/status", params={"job_id": job_id},
            timeout=settings.rag_timeout_s,
        )
        resp.raise_for_status()
        return {"success": True, "data": resp.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


REGISTRY.register(start_scan_by_check_ids, category="scanner")
REGISTRY.register(start_scan_by_group, category="scanner")
REGISTRY.register(check_job_status, category="scanner")
