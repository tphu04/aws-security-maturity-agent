"""ScannerAgent — Trigger Prowler scan jobs (deterministic HTTP, no LLM).

Phase B2:
- Bỏ kế thừa `BaseAgent` (run_batch là pure HTTP — không cần LLM client).
- Bỏ `lc_llm = ChatOllama(...)` + `TimerCallback` (không dùng).
- `__init__()` không nhận tham số: URL đến scanner API được set qua
  `settings.scanner_api_url` (env `SCANNER_API_URL`) — đọc 1 lần ở
  `pdca/tools.py` khi import module. Không expose `scanner_url` param
  vì các tool (`@tool` decorator) không nhận URL runtime — đó là
  cấu hình module-level. B13 sẽ tách `pdca/tools.py` thành package
  và mỗi tool đọc settings trực tiếp.
- `run_batch()` trả `List[Dict]` thay vì `List[str]` — giữ `task_type` +
  `task_value` để các node sau (scan_poll, scan_collect — Phase C) có
  context retry/log.
- Bỏ `run_scan()` deprecated + comment block legacy AI version.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pdca.observability.logger import get_logger
from pdca.tools import SCANNER_AGENT_TOOLS

logger = get_logger(__name__)


class ScannerAgent:
    """Deterministic scan trigger — không gọi LLM ở bước này."""

    ALLOWED_GROUPS = {
        "s3",
        "iam",
        "ec2",
        "rds",
        "cloudtrail",
        "eks",
        "vpc",
        "lambda",
        "kms",
    }

    def __init__(self) -> None:
        self.tools_map = {tool.name: tool for tool in SCANNER_AGENT_TOOLS}

    # ------------------------------------------------------------------
    def run_batch(
        self,
        target_groups: List[str],
        specific_checks: List[str],
    ) -> List[Dict[str, Any]]:
        """Khởi tạo scan jobs theo plan.

        Returns:
            list các job-meta dict, shape:
                {"job_id": str, "task_type": "checks"|"group", "task_value": str}

            (Trống nếu không có target hợp lệ.)
        """
        collected: List[Dict[str, Any]] = []
        logger.info("ScannerAgent batch start")

        normalized_groups = self._normalize_groups(target_groups)
        normalized_checks = self._normalize_check_ids(specific_checks)

        if not normalized_groups and not normalized_checks:
            logger.warning(
                "No valid target_groups or specific_checks to scan",
                extra={"groups_in": target_groups, "checks_in": specific_checks},
            )
            return collected

        # 1) Specific checks
        if normalized_checks:
            ids_str = ",".join(normalized_checks)
            logger.info("Requesting specific checks", extra={"check_ids": ids_str})
            jid = self._execute_tool(
                tool_name="start_scan_by_check_ids",
                tool_args={"check_ids": ids_str},
            )
            if jid:
                collected.append(
                    {"job_id": jid, "task_type": "checks", "task_value": ids_str}
                )

        # 2) Per-group
        if normalized_groups:
            for group in normalized_groups:
                logger.info("Requesting scan for group", extra={"group": group})
                jid = self._execute_tool(
                    tool_name="start_scan_by_group",
                    tool_args={"group": group},
                )
                if jid:
                    collected.append(
                        {"job_id": jid, "task_type": "group", "task_value": group}
                    )

        return collected

    # ------------------------------------------------------------------
    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[str]:
        target_tool = self.tools_map.get(tool_name)
        if not target_tool:
            logger.error("Tool not found", extra={"tool": tool_name})
            return None

        try:
            tool_output = target_tool.invoke(tool_args)
            jid = self._extract_job_id(tool_output)
            if jid:
                logger.info("Job created", extra={"tool": tool_name, "job_id": jid})
                return jid
            logger.warning(
                "Tool executed but returned no job_id",
                extra={"tool": tool_name, "output": tool_output},
            )
            return None
        except Exception as e:
            logger.error("Tool invocation failed",
                         extra={"tool": tool_name, "error": str(e)})
            return None

    def _normalize_groups(self, groups: List[str]) -> List[str]:
        if not isinstance(groups, list):
            return []
        cleaned: List[str] = []
        seen: set = set()
        for raw in groups:
            if not isinstance(raw, str):
                continue
            group = raw.strip().lower()
            if not group:
                continue
            if group not in self.ALLOWED_GROUPS:
                logger.warning("Unsupported group skipped", extra={"group": group})
                continue
            if group not in seen:
                seen.add(group)
                cleaned.append(group)
        return cleaned

    def _normalize_check_ids(self, check_ids: List[str]) -> List[str]:
        if not isinstance(check_ids, list):
            return []
        cleaned: List[str] = []
        seen: set = set()
        for raw in check_ids:
            if not isinstance(raw, str):
                continue
            cid = raw.strip()
            if not cid:
                continue
            if cid not in seen:
                seen.add(cid)
                cleaned.append(cid)
        return cleaned

    def _extract_job_id(self, tool_output: Any) -> Optional[str]:
        try:
            data = tool_output
            if isinstance(tool_output, str):
                data = json.loads(tool_output)
            if isinstance(data, dict):
                if data.get("job_id"):
                    return str(data["job_id"])
                nested = data.get("data")
                if isinstance(nested, dict) and nested.get("job_id"):
                    return str(nested["job_id"])
                result = data.get("result")
                if isinstance(result, dict) and result.get("job_id"):
                    return str(result["job_id"])
        except Exception:
            pass
        return None
