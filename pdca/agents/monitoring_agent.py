"""MonitoringAgent — Poll scanner job status cho đến khi hoàn tất.

Phase A5: Thêm `max_iterations` + `timeout_s` để chặn infinite loop. Dùng
`time.monotonic()` đo elapsed (chỉ có nghĩa trong process hiện tại — agent
này không persist qua restart, MemorySaver/SqliteSaver checkpoint nằm ở
graph layer).
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from pdca.config import settings
from pdca.observability.logger import get_logger
from pdca.tools import AVAILABLE_FUNCTIONS

logger = get_logger(__name__)


class MonitoringAgent:
    def __init__(
        self,
        poll_interval: Optional[float] = None,
        max_iterations: Optional[int] = None,
        timeout_s: Optional[float] = None,
    ) -> None:
        self.check_status_tool = AVAILABLE_FUNCTIONS["check_job_status"]
        self.poll_interval = (
            poll_interval if poll_interval is not None else settings.poll_interval_s
        )
        self.max_iterations = (
            max_iterations if max_iterations is not None else settings.poll_max_iterations
        )
        self.timeout_s = timeout_s if timeout_s is not None else settings.poll_timeout_s

    # ------------------------------------------------------------------
    # Helpers — tách để Phase E (async) dễ swap
    # ------------------------------------------------------------------
    def _sleep(self, interval: float) -> None:
        time.sleep(interval)

    def _check(self, job_id: str) -> Dict[str, Any]:
        response_raw = self.check_status_tool.invoke({"job_id": job_id})
        if isinstance(response_raw, str):
            return json.loads(response_raw)
        return response_raw

    # ------------------------------------------------------------------
    def run(self, job_ids: List[str]) -> List[Dict[str, Any]]:
        logger.info(
            "MonitoringAgent start",
            extra={"job_count": len(job_ids), "timeout_s": self.timeout_s},
        )

        active_jobs = set(job_ids)
        all_findings: List[Dict[str, Any]] = []
        iteration = 0
        started_at = time.monotonic()

        while active_jobs:
            iteration += 1
            elapsed = time.monotonic() - started_at

            if iteration > self.max_iterations:
                raise RuntimeError(
                    f"Scan poll exceeded max_iterations={self.max_iterations} "
                    f"with {len(active_jobs)} job(s) still pending"
                )
            if elapsed > self.timeout_s:
                raise RuntimeError(
                    f"Scan timeout: {len(active_jobs)} job(s) still pending "
                    f"after {self.timeout_s}s"
                )

            jobs_to_remove = set()
            for job_id in active_jobs:
                try:
                    tool_output = self._check(job_id)
                    api_response = tool_output.get("data", tool_output)
                    job_status = api_response.get("status")

                    if job_status == "completed":
                        logger.info("Job completed", extra={"job_id": job_id})
                        job_result = api_response.get("result", [])
                        if isinstance(job_result, list):
                            all_findings.extend(job_result)
                        elif job_result:
                            all_findings.append(job_result)
                        jobs_to_remove.add(job_id)

                    elif job_status == "failed":
                        logger.warning("Job failed", extra={"job_id": job_id})
                        jobs_to_remove.add(job_id)

                except Exception as e:
                    logger.error(
                        "check_job_status error",
                        extra={"job_id": job_id, "error": str(e)},
                    )

            active_jobs -= jobs_to_remove

            if active_jobs:
                self._sleep(self.poll_interval)

        logger.info(
            "MonitoringAgent done",
            extra={"finding_count": len(all_findings), "iterations": iteration},
        )
        return all_findings
