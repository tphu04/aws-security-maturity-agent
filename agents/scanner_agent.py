import json
import time
from typing import List, Dict, Any, Optional

from .base_agent import BaseAgent
from langchain_ollama import ChatOllama
from langchain_core.callbacks import BaseCallbackHandler

from agent_tools import SCANNER_AGENT_TOOLS


class TimerCallback(BaseCallbackHandler):
    def __init__(self):
        self.total_duration = 0.0
        self.call_history = []
        self.start_time = 0.0

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> Any:
        self.start_time = time.perf_counter()

    def on_llm_end(self, response: Any, **kwargs: Any) -> Any:
        duration = time.perf_counter() - self.start_time
        self.total_duration += duration
        self.call_history.append(duration)


class ScannerAgent(BaseAgent):
    """
    ScannerAgent (Refactored)
    Nhiệm vụ:
    - Nhận plan đã được PlanningAgent xử lý
    - Thực thi scan một cách deterministic
    - Không để LLM tự build tool args ở bước execution
    """

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

    def __init__(self, model_name, api_key, base_url):
        super().__init__(model_name, api_key, base_url)

        self.timer = TimerCallback()

        # Giữ lại để tương thích nếu sau này cần reasoning phụ
        # nhưng execution path bên dưới không phụ thuộc vào LLM nữa
        print(f"[ScannerModule] Init LangChain với model {model_name}...")
        self.lc_llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            callbacks=[self.timer],
        )

        self.tools_map = {tool.name: tool for tool in SCANNER_AGENT_TOOLS}

    def get_llm_metrics(self) -> Dict[str, Any]:
        return {
            "total_latency": round(self.timer.total_duration, 4),
            "call_history": [round(t, 4) for t in self.timer.call_history],
            "call_count": len(self.timer.call_history),
        }

    def run_batch(
        self, target_groups: List[str], specific_checks: List[str]
    ) -> List[str]:
        """
        Hàm được gọi bởi Orchestrator (Scanning Node).

        Ưu tiên:
        1. Nếu có specific_checks -> scan theo check IDs
        2. Nếu có target_groups -> scan theo service groups

        Không dùng LLM để quyết định tool/args ở bước này.
        """
        collected_job_ids: List[str] = []
        print("[ScannerModule] Bắt đầu Batch Scan...")

        normalized_groups = self._normalize_groups(target_groups)
        normalized_checks = self._normalize_check_ids(specific_checks)

        if not normalized_groups and not normalized_checks:
            print(
                "[ScannerModule] ⚠️ Không có target_groups hoặc specific_checks hợp lệ để scan."
            )
            return collected_job_ids

        # 1) Scan theo danh sách check cụ thể
        if normalized_checks:
            ids_str = ",".join(normalized_checks)
            print(f"[ScannerModule] -> Requesting specific checks: {ids_str}")

            jid = self._execute_tool(
                tool_name="start_scan_by_check_ids",
                tool_args={"check_ids": ids_str},
            )
            if jid:
                collected_job_ids.append(jid)

        # 2) Scan theo group/service
        if normalized_groups:
            for group in normalized_groups:
                print(f"[ScannerModule] -> Requesting scan for group: {group}")

                jid = self._execute_tool(
                    tool_name="start_scan_by_group",
                    tool_args={"group": group},
                )
                if jid:
                    collected_job_ids.append(jid)

        return collected_job_ids

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[str]:
        """
        Thực thi tool một cách deterministic.
        """
        target_tool = self.tools_map.get(tool_name)
        if not target_tool:
            print(f"[ScannerModule] ❌ Tool '{tool_name}' không tồn tại trong map.")
            return None

        try:
            print(f"[ScannerModule] Calling tool: {tool_name} with args: {tool_args}")
            tool_output = target_tool.invoke(tool_args)

            jid = self._extract_job_id(tool_output)
            if jid:
                print(f"[ScannerModule] Job Created: {jid}")
                return jid

            print("[ScannerModule] Tool executed but returned no Job ID.")
            print(f"[ScannerModule] Tool output: {tool_output}")
            return None

        except Exception as e:
            print(f"[ScannerModule] ❌ Lỗi tool {tool_name}: {e}")
            return None

    def _normalize_groups(self, groups: List[str]) -> List[str]:
        """
        Chuẩn hóa và lọc group hợp lệ.
        """
        if not isinstance(groups, list):
            return []

        cleaned: List[str] = []
        seen = set()

        for raw in groups:
            if not isinstance(raw, str):
                continue

            group = raw.strip().lower()
            if not group:
                continue

            # Nếu muốn mềm hơn thì bỏ check whitelist này
            if group not in self.ALLOWED_GROUPS:
                print(f"[ScannerModule] ⚠️ Bỏ qua group không hợp lệ/không hỗ trợ: {group}")
                continue

            if group not in seen:
                seen.add(group)
                cleaned.append(group)

        return cleaned

    def _normalize_check_ids(self, check_ids: List[str]) -> List[str]:
        """
        Chuẩn hóa danh sách check IDs:
        - bỏ None/rỗng
        - strip space
        - bỏ trùng
        """
        if not isinstance(check_ids, list):
            return []

        cleaned: List[str] = []
        seen = set()

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
        """
        Hỗ trợ nhiều format output khác nhau từ tool/API.
        """
        try:
            data = tool_output

            if isinstance(tool_output, str):
                data = json.loads(tool_output)

            if isinstance(data, dict):
                # Case 1: job_id ở root
                if data.get("job_id"):
                    return str(data["job_id"])

                # Case 2: nested trong data
                nested = data.get("data")
                if isinstance(nested, dict) and nested.get("job_id"):
                    return str(nested["job_id"])

                # Case 3: nested trong result
                result = data.get("result")
                if isinstance(result, dict) and result.get("job_id"):
                    return str(result["job_id"])

        except Exception:
            pass

        return None

    # Giữ lại để backward compatibility nếu nơi khác còn gọi
    def run_scan(self, task_description: str) -> Optional[str]:
        """
        Deprecated path.
        Không khuyến nghị dùng vì dễ lỗi tool-call format với model local.
        """
        print(
            "[ScannerModule] ⚠️ run_scan(task_description) đã deprecated. "
            "Hãy dùng run_batch(target_groups, specific_checks)."
        )
        return None

# import json
# import logging
# import time
# from typing import List, Dict, Any, Optional

# from .base_agent import BaseAgent
# from langchain_ollama import ChatOllama
# from langchain_core.messages import HumanMessage, SystemMessage
# from langchain_core.callbacks import BaseCallbackHandler

# # Import danh sách tool từ agent_tools
# from agent_tools import SCANNER_AGENT_TOOLS


# class TimerCallback(BaseCallbackHandler):
#     def __init__(self):
#         self.total_duration = 0.0
#         self.call_history = []  # Thêm cái này
#         self.start_time = 0.0

#     def on_llm_start(
#         self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
#     ) -> Any:
#         self.start_time = time.perf_counter()

#     def on_llm_end(self, response: Any, **kwargs: Any) -> Any:
#         duration = time.perf_counter() - self.start_time
#         self.total_duration += duration
#         self.call_history.append(duration)


# class ScannerAgent(BaseAgent):
#     """
#     ScannerAgent (AI Version)
#     Nhiệm vụ: Nhận mô tả task (VD: "Quét check logging") -> Gọi đúng Tool.
#     """

#     def __init__(self, model_name, api_key, base_url):
#         # Init khớp với graph_orchestator
#         super().__init__(model_name, api_key, base_url)

#         self.timer = TimerCallback()

#         print(f"[ScannerModule] Init LangChain với model {model_name}...")
#         self.lc_llm = ChatOllama(
#             model=model_name, base_url=base_url, temperature=0, callbacks=[self.timer]
#         )

#         # 1. Bind tools cho AI
#         self.llm_with_tools = self.lc_llm.bind_tools(SCANNER_AGENT_TOOLS)

#         # 2. Tự động tạo map tool {name: func} để execute thủ công nếu cần
#         self.tools_map = {tool.name: tool for tool in SCANNER_AGENT_TOOLS}

#     def get_llm_metrics(self) -> Dict[str, Any]:
#         return {
#             "total_latency": round(self.timer.total_duration, 4),
#             "call_history": [round(t, 4) for t in self.timer.call_history],
#             "call_count": len(self.timer.call_history),
#         }

#     def run_batch(
#         self, target_groups: List[str], specific_checks: List[str]
#     ) -> List[str]:
#         """
#         Hàm được gọi bởi Orchestrator (Scanning Node).
#         Xử lý cả Service Groups và Specific Checks.
#         """
#         collected_job_ids = []
#         print(f"[ScannerModule] Bắt đầu Batch Scan...")

#         # 1. Xử lý Specific Checks (Nếu có danh sách Check ID cụ thể)
#         # VD: ['check_s3_01', 'check_iam_02']
#         if specific_checks:
#             # Gom tất cả check IDs vào 1 request để tối ưu (hoặc chia nhỏ nếu cần)
#             ids_str = ", ".join(specific_checks)
#             print(f"[ScannerModule] -> Requesting specific checks: {ids_str}")

#             # Tạo prompt thật rõ để AI chọn tool 'start_scan_by_check_ids'
#             task_desc = (
#                 f"Start a security scan specifically for these check IDs: {ids_str}"
#             )

#             job_id = self.run_scan(task_desc)
#             if job_id:
#                 collected_job_ids.append(job_id)

#         # 2. Xử lý Target Groups (Nếu có tên service)
#         # VD: ['s3', 'iam']
#         if target_groups:
#             for group in target_groups:
#                 print(f"[ScannerModule] -> Requesting scan for group: {group}")

#                 # Tạo prompt thật rõ để AI chọn tool 'start_scan_by_service_group'
#                 task_desc = f"Start a security scan for the service group: {group}"

#                 job_id = self.run_scan(task_desc)
#                 if job_id:
#                     collected_job_ids.append(job_id)

#         return collected_job_ids

#     def run_scan(self, task_description: str) -> Optional[str]:
#         """
#         Nhận lệnh -> AI suy nghĩ -> Gọi Tool -> Trả về Job ID
#         """
#         messages = [
#             SystemMessage(
#                 content="Bạn là trợ lý bảo mật AWS. Nhiệm vụ của bạn là gọi Tool thích hợp để quét hệ thống dựa trên yêu cầu."
#             ),
#             HumanMessage(content=task_description),
#         ]

#         try:
#             # 1. Gọi AI
#             ai_msg = self.llm_with_tools.invoke(messages)

#             # 2. Xử lý Tool Call
#             if ai_msg.tool_calls:
#                 for tool_call in ai_msg.tool_calls:
#                     tool_name = tool_call["name"]
#                     tool_args = tool_call["args"]

#                     target_tool = self.tools_map.get(tool_name)

#                     if target_tool:
#                         try:
#                             print(
#                                 f"[ScannerModule] Calling tool: {tool_name} with args: {tool_args}"
#                             )
#                             # Thực thi tool
#                             tool_output = target_tool.invoke(tool_args)

#                             # Trích xuất Job ID từ output
#                             jid = self._extract_job_id(tool_output)
#                             if jid:
#                                 print(f"[ScannerModule] Job Created: {jid}")
#                                 return jid
#                             else:
#                                 print(
#                                     f"[ScannerModule] Tool executed but returned no Job ID."
#                                 )

#                         except Exception as e:
#                             print(f"[ScannerModule] ❌ Lỗi tool {tool_name}: {e}")
#                             return None
#                     else:
#                         print(
#                             f"[ScannerModule] ❌ Lỗi: Tool '{tool_name}' không tồn tại trong map."
#                         )
#                         return None
#             else:
#                 print(
#                     f"[ScannerModule] ⚠️ AI không gọi tool nào cho task: '{task_description}'"
#                 )
#                 return None

#         except Exception as e:
#             print(f"[ScannerModule] ❌ Lỗi Critical: {e}")
#             return None

#         return None

#     def _extract_job_id(self, tool_output):
#         try:
#             data = tool_output
#             if isinstance(tool_output, str):
#                 data = json.loads(tool_output)

#             if isinstance(data, dict):
#                 # 🔧 FIX: support nested data
#                 if "job_id" in data:
#                     return data["job_id"]

#                 nested = data.get("data")
#                 if isinstance(nested, dict):
#                     return nested.get("job_id")

#         except Exception:
#             pass
#         return None
