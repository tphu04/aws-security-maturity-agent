import json
import datetime
import time
from typing import Any, Dict, List
from botocore.exceptions import ClientError, BotoCoreError

from agent_tools import ALL_TOOLS
from .environment_agent import EnvironmentAgent


class ExecutionAgent:
    """
    ExecutionAgent – DO phase
    --------------------------------
    - Thực thi tool thật (không còn chế độ dry-run).
    - Bắt lỗi chi tiết (AWS ClientError, BotoCoreError).
    - In log theo format bảng.
    - Phân biệt chính xác success/manual/failure.
    """

    def __init__(self, aws_context: Dict[str, Any]):
        self.aws_context = aws_context or {}
        self.tools_map = {tool.name: tool for tool in ALL_TOOLS}
        print(
            f"[ExecutionAgent] 🤖 Initialized with Context: Region={self.aws_context.get('region')}"
        )

    def _timestamp(self):
        return datetime.datetime.utcnow().isoformat()

    # ======================================================================
    # 🔥 CLASSIFY TOOL RESULT
    # ======================================================================
    def classify_result(self, parsed: Dict[str, Any]) -> str:
        """Phân loại output theo chuẩn: success / failed / manual_required."""

        if not isinstance(parsed, dict):
            return "failed"

        # Manual-required → thất bại
        if parsed.get("status") == "manual_required":
            return "manual_required"

        # Auto-fix thành công
        if parsed.get("success") is True:
            return "success"

        return "failed"

    # ======================================================================
    # 🔥 PARSE TOOL OUTPUT
    # ======================================================================
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
    # 🔥 EXECUTE TASK
    # ======================================================================
    def execute_task(self, task: Dict[str, Any], decision: str) -> Dict[str, Any]:
        task_id = task["task_id"]
        tool_name = task["tool_name"]
        tool_params = dict(task["tool_params"])

        # ❌ REMOVE DRY RUN — Chỉ giữ skip hoặc approve
        if decision != "approve":
            msg = f"[SKIP] Task {task_id} skipped."
            print(f"→ Task {task_id} (SKIP)\n   {msg}")
            return self._build_log(task_id, tool_name, "skipped", msg, 0)

        # APPROVE → chạy tool
        tool = self.tools_map.get(tool_name)
        if not tool:
            return self._build_log(task_id, tool_name, "error", "Tool not found", 0)

        # Inject region + account ID
        injected_info = []
        if "region" not in tool_params and self.aws_context.get("region"):
            tool_params["region"] = self.aws_context["region"]
            injected_info.append(f"Auto-injected region: {tool_params['region']}")

        if "account_id" not in tool_params and self.aws_context.get("account_id"):
            tool_params["account_id"] = self.aws_context["account_id"]

        # Log header
        print(f"→ Task {task_id} (APPROVE)")
        for info in injected_info:
            print(f"   -> {info}")
        print(f"[ExecutionAgent] Running tool: {tool_name}")
        print(f"→ Params: {tool_params}")

        started_at = self._timestamp()
        start_perf = time.perf_counter()

        result_payload = {}
        status = "unknown"
        error_details = None

        try:
            # Chạy tool
            raw_result = tool.invoke(tool_params)

            # Parse JSON output
            parsed = self.parse_tool_output(raw_result)
            result_payload = parsed

            # Phân loại success/fail/manual
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

        # In Result Table
        print("------Result-------")
        print(f"Tool      : {tool_name}")
        print(f"Status    : {status.upper()}")
        print(f"Success   : {status == 'success'}")
        print(f"Started   : {started_at}")
        print(f"Ended     : {ended_at}")
        print(f"Duration  : {duration:.2f}s")

        if error_details:
            print("\n[ERROR DETAILS]")
            print(json.dumps(error_details, indent=4))

        print("-------------------\n")

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
        print("\n================ EXECUTION PHASE ================")
        print(f"[ExecutionAgent] Processing {len(tasks)} tasks...")
        print("=================================================\n")

        for task in tasks:
            task_id = task["task_id"]
            decision = decisions.get(task_id, "skip")
            logs.append(self.execute_task(task, decision))

        print("\n[ExecutionAgent] ✅ Completed execution phase.")
        return logs
