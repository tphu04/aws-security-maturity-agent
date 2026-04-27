"""ExecutionAgent — DO phase: thực thi remediation tools.

Phase B9: thay toàn bộ `print()` → `logger.info/warning/error`. Logic
classify/parse/execute giữ nguyên (B15 sẽ chuẩn hóa tool return type +
thêm REGISTRY guards trong Phase B.2).
"""

from __future__ import annotations

import datetime
import json
import time
from typing import Any, Dict, List

from botocore.exceptions import BotoCoreError, ClientError

from pdca.observability.logger import get_logger
from pdca.tools import REMEDIATION_TOOLS

logger = get_logger(__name__)


class ExecutionAgent:
    """Thực thi tool thật (không dry-run), bắt lỗi chi tiết, log structured."""

    def __init__(self, aws_context: Dict[str, Any]):
        self.aws_context = aws_context or {}
        self.tools_map = {tool.name: tool for tool in REMEDIATION_TOOLS}
        logger.info(
            "ExecutionAgent initialized",
            extra={"region": self.aws_context.get("region"),
                   "tool_count": len(self.tools_map)},
        )

    def _timestamp(self):
        return datetime.datetime.utcnow().isoformat()

    # ======================================================================
    def classify_result(self, parsed: Dict[str, Any]) -> str:
        """Phân loại output: success / failed / manual_required."""
        if not isinstance(parsed, dict):
            return "failed"
        if parsed.get("status") == "manual_required":
            return "manual_required"
        if parsed.get("success") is True:
            return "success"
        return "failed"

    def parse_tool_output(self, raw_result: Any):
        """Tool có thể trả về JSON string → parse thành dict."""
        if isinstance(raw_result, dict):
            return raw_result
        if isinstance(raw_result, str):
            try:
                return json.loads(raw_result)
            except json.JSONDecodeError:
                return {"output": raw_result}
        return {"output": raw_result}

    # ======================================================================
    def execute_task(self, task: Dict[str, Any], decision: str) -> Dict[str, Any]:
        task_id = task["task_id"]
        tool_name = task["tool_name"]
        tool_params = dict(task["tool_params"])

        if decision != "approve":
            msg = f"Task {task_id} skipped (decision={decision})."
            logger.info("Task skipped",
                        extra={"task_id": task_id, "decision": decision})
            return self._build_log(task_id, tool_name, "skipped", msg, 0)

        tool = self.tools_map.get(tool_name)
        if not tool:
            logger.error("Tool not found",
                         extra={"task_id": task_id, "tool_name": tool_name})
            return self._build_log(task_id, tool_name, "error", "Tool not found", 0)

        # Inject region + account ID
        if "region" not in tool_params and self.aws_context.get("region"):
            tool_params["region"] = self.aws_context["region"]
        if "account_id" not in tool_params and self.aws_context.get("account_id"):
            tool_params["account_id"] = self.aws_context["account_id"]

        logger.info(
            "Executing tool",
            extra={"task_id": task_id, "tool": tool_name, "params": tool_params},
        )

        started_at = self._timestamp()
        start_perf = time.perf_counter()

        result_payload: Dict[str, Any] = {}
        status = "unknown"
        error_details = None

        try:
            raw_result = tool.invoke(tool_params)
            parsed = self.parse_tool_output(raw_result)
            result_payload = parsed
            status = self.classify_result(parsed)

        except ClientError as ce:
            status = "failed"
            err = ce.response.get("Error", {})
            error_details = {
                "type": "ClientError",
                "code": err.get("Code"),
                "message": err.get("Message"),
                "request_id": ce.response.get("ResponseMetadata", {}).get("RequestId"),
            }

        except BotoCoreError as be:
            status = "failed"
            error_details = {"type": "BotoCoreError", "message": str(be)}

        except Exception as e:
            status = "failed"
            error_details = {"type": "Exception", "message": str(e)}

        ended_at = self._timestamp()
        duration = time.perf_counter() - start_perf

        log_payload = {
            "task_id": task_id,
            "tool": tool_name,
            "status": status,
            "duration_s": round(duration, 4),
        }
        if error_details:
            log_payload["error"] = error_details
            logger.warning("Tool execution finished with error", extra=log_payload)
        else:
            logger.info("Tool execution finished", extra=log_payload)

        return {
            "task_id": task_id,
            "tool_name": tool_name,
            "status": status,
            "success": (status == "success"),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration": duration,
            "output": result_payload,
            "error": error_details,
        }

    # ======================================================================
    def _build_log(self, task_id, tool_name, status, output, duration):
        return {
            "task_id": task_id,
            "tool_name": tool_name,
            "status": status,
            "output": output,
            "duration": duration,
            "timestamp": self._timestamp(),
            "error": None,
        }

    # ======================================================================
    def execute_all(self, tasks: List[Dict[str, Any]], decisions: Dict[str, str]):
        logs = []
        logger.info("Execution phase start", extra={"task_count": len(tasks)})
        for task in tasks:
            task_id = task["task_id"]
            decision = decisions.get(task_id, "skip")
            logs.append(self.execute_task(task, decision))
        logger.info("Execution phase done", extra={"log_count": len(logs)})
        return logs
