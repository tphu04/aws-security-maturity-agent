"""RescanAgent — Quét lại sau remediation để verify fixes.

Phase A5:
- `__init__` nhận `config: dict` optional → khi truyền vào sẽ dùng thẳng,
  không đọc file (decouple file-based coupling, prepare cho LangGraph node).
- `poll()` có `max_iterations` + `timeout_s` chặn infinite loop.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import requests

from pdca.agents.shared.normalizer import normalize_results
from pdca.config import settings
from pdca.observability.logger import get_logger

logger = get_logger(__name__)


class RescanAgent:
    def __init__(
        self,
        config_path: str = "data/artifacts/initial_scan_config.json",
        scanner_base_url: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        poll_interval: Optional[float] = None,
        max_iterations: Optional[int] = None,
        timeout_s: Optional[float] = None,
    ) -> None:
        self.config_path = config_path
        self.scanner_base_url = scanner_base_url or settings.scanner_api_url
        self._config = config  # nếu None → fallback đọc file
        self.poll_interval = (
            poll_interval if poll_interval is not None else settings.poll_interval_s
        )
        self.max_iterations = (
            max_iterations if max_iterations is not None else settings.poll_max_iterations
        )
        self.timeout_s = timeout_s if timeout_s is not None else settings.poll_timeout_s

    # ------------------------------------------------------------------
    def load_initial_config(self) -> Dict[str, Any]:
        """Trả config được inject (nếu có), nếu không đọc từ file (backward compat)."""
        if self._config is not None:
            return self._config
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"groups_to_scan": [], "checks_to_scan": []}

    # ------------------------------------------------------------------
    def start_job(self, group: str) -> Optional[str]:
        """Khởi tạo job scan theo Group (s3, iam,...)."""
        try:
            url = f"{self.scanner_base_url}/scan/check?group={group}"
            resp = requests.get(url).json()
            return resp.get("job_id")
        except Exception as e:
            logger.error("start_job failed", extra={"group": group, "error": str(e)})
            return None

    def start_specific_job(self, check_ids_list: List[str]) -> Optional[str]:
        """Khởi tạo job scan theo danh sách Check ID."""
        try:
            ids_str = ",".join(check_ids_list)
            url = f"{self.scanner_base_url}/scan/specific?check_ids={ids_str}"
            resp = requests.get(url).json()
            return resp.get("job_id")
        except Exception as e:
            logger.error(
                "start_specific_job failed",
                extra={"check_count": len(check_ids_list), "error": str(e)},
            )
            return None

    # ------------------------------------------------------------------
    def _sleep(self, interval: float) -> None:
        time.sleep(interval)

    def poll(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Poll job đến khi `completed`/`failed` hoặc timeout. Raise khi vượt giới hạn."""
        url = f"{self.scanner_base_url}/job/status?job_id={job_id}"
        iteration = 0
        started_at = time.monotonic()

        while True:
            iteration += 1
            elapsed = time.monotonic() - started_at

            if iteration > self.max_iterations:
                raise RuntimeError(
                    f"Rescan poll exceeded max_iterations={self.max_iterations} "
                    f"for job_id={job_id}"
                )
            if elapsed > self.timeout_s:
                raise RuntimeError(
                    f"Rescan timeout for job_id={job_id} after {self.timeout_s}s"
                )

            try:
                job = requests.get(url).json()
            except Exception as e:
                logger.error(
                    "poll request failed",
                    extra={"job_id": job_id, "error": str(e)},
                )
                return None

            if job.get("status") in ("completed", "failed"):
                return job

            self._sleep(self.poll_interval)

    # ------------------------------------------------------------------
    def run(self) -> Dict[str, Any]:
        logger.info("RescanAgent start (verifying fixes)")

        plan = self.load_initial_config()
        groups = plan.get("groups_to_scan", []) or plan.get("target_services", [])
        specific_checks = plan.get("checks_to_scan", [])

        all_raw_findings: List[Dict[str, Any]] = []

        if specific_checks:
            logger.info(
                "Specific check mode",
                extra={"check_count": len(specific_checks)},
            )
            job_id = self.start_specific_job(specific_checks)
            if job_id:
                job_data = self.poll(job_id)
                if job_data and job_data.get("status") == "completed":
                    findings = job_data.get("result", []) or []
                    all_raw_findings.extend(findings)
                    logger.info(
                        "Specific scan completed",
                        extra={"finding_count": len(findings)},
                    )
                else:
                    logger.warning("Specific scan failed", extra={"job_id": job_id})
            else:
                logger.warning("Specific scan: cannot create job")

        elif groups:
            for i, g in enumerate(groups, 1):
                logger.info(
                    "Group scan", extra={"index": i, "total": len(groups), "group": g}
                )
                job_id = self.start_job(g)
                if not job_id:
                    logger.warning("Group scan: cannot create job", extra={"group": g})
                    continue

                job_data = self.poll(job_id)
                if job_data and job_data.get("status") == "completed":
                    findings = job_data.get("result", []) or []
                    if isinstance(findings, list):
                        all_raw_findings.extend(findings)
                        logger.info(
                            "Group scan completed",
                            extra={"group": g, "finding_count": len(findings)},
                        )
                    else:
                        logger.warning(
                            "Group scan: invalid result format", extra={"group": g}
                        )
                else:
                    logger.warning("Group scan failed", extra={"group": g})
        else:
            logger.warning("No scan config found (groups or checks)")

        norm_data = normalize_results(all_raw_findings)

        with open("data/artifacts/post_scan.json", "w", encoding="utf-8") as f:
            json.dump(norm_data, f, indent=2, ensure_ascii=False)

        # `normalize_results` trả {"metadata": {...}, "findings": [...]}
        findings = norm_data.get("findings", []) if isinstance(norm_data, dict) else []
        logger.info(
            "RescanAgent done — saved to data/artifacts/post_scan.json",
            extra={"finding_count": len(findings)},
        )
        return norm_data
