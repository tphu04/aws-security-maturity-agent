"""ExecutionAgent — DO phase: thực thi remediation tools.

Phase B9: thay toàn bộ `print()` → `logger.info/warning/error`.

Phase B15 (v1.7):
- Tool layer đã đảm bảo invariant "luôn return dict" (decision #35) — branch
  parse JSON-string trong `parse_tool_output` chỉ còn safety net.
- Thêm 3 guard trong `execute_task` (defense-in-depth):
  GUARD 1: tool_name phải tồn tại trong REGISTRY.
  GUARD 2: tool category phải = "remediation" (chặn scanner/knowledge tool
           bị lẫn vào execution path).
  GUARD 3: manual_only tool — REGISTRY là source of truth, KHÔNG tin
           task["manual_required"] (HITL UI có thể override).
"""

from __future__ import annotations

import datetime
import json
import time
from typing import Any, Dict, List

from botocore.exceptions import BotoCoreError, ClientError

from pdca.observability.logger import get_logger
from pdca.tools import REGISTRY

logger = get_logger(__name__)


class ExecutionAgent:
    """Thực thi tool thật (không dry-run), bắt lỗi chi tiết, log structured."""

    def __init__(self, aws_context: Dict[str, Any]):
        self.aws_context = aws_context or {}
        logger.info(
            "ExecutionAgent initialized",
            extra={"region": self.aws_context.get("region"),
                   "tool_count": len(REGISTRY.for_category("remediation"))},
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
        """B15: tool layer đã chuẩn hóa return dict. Branch JSON-string giờ
        chỉ là safety net cho legacy hoặc tool 3rd-party tương lai."""
        if isinstance(raw_result, dict):
            return raw_result
        logger.warning(
            "Tool returned non-dict — should be fixed in tools layer (B15 invariant)",
            extra={"type": type(raw_result).__name__},
        )
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

        # GUARD 0: decision != approve → skip
        if decision != "approve":
            msg = f"Task {task_id} skipped (decision={decision})."
            logger.info("Task skipped",
                        extra={"task_id": task_id, "decision": decision})
            return self._build_log(task_id, tool_name, "skipped", msg, 0)

        # GUARD 1 (B15 v1.7): tool phải tồn tại trong REGISTRY
        meta = REGISTRY.meta(tool_name)
        if meta is None:
            logger.error("Refused: tool not registered",
                         extra={"task_id": task_id, "tool_name": tool_name})
            return self._build_log(
                task_id, tool_name, "error",
                f"Tool '{tool_name}' không tồn tại trong REGISTRY", 0,
            )

        # GUARD 2 (B15 v1.7): chỉ category="remediation" được execute ở đây
        if meta.category != "remediation":
            logger.error("Refused: non-remediation tool in execution path",
                         extra={"task_id": task_id, "tool_name": tool_name,
                                "category": meta.category})
            return self._build_log(
                task_id, tool_name, "error",
                f"Category '{meta.category}' không được execute ở remediation path",
                0,
            )

        # GUARD 3 (B15 v1.7): manual_only — REGISTRY là source of truth
        if meta.manual_only:
            logger.warning("Refused: manual_only tool",
                           extra={"task_id": task_id, "tool_name": tool_name})
            return self._build_log(
                task_id, tool_name, "manual_required",
                "Tool yêu cầu thao tác thủ công — execution refused", 0,
            )

        tool = meta.tool

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
