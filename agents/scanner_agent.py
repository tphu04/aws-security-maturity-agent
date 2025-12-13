import json
import logging
from typing import List, Dict, Any, Optional

from .base_agent import BaseAgent
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

# Import danh sách tool từ agent_tools
from agent_tools import SCANNER_AGENT_TOOLS


class ScannerAgent(BaseAgent):
    """
    ScannerAgent (AI Version)
    Nhiệm vụ: Nhận mô tả task (VD: "Quét check logging") -> Gọi đúng Tool.
    """

    def __init__(self, model_name, api_key, base_url):
        # Init khớp với graph_orchestator
        super().__init__(model_name, api_key, base_url)

        print(f"[ScannerAgent] Init LangChain với model {model_name}...")
        self.lc_llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
        )

        # 1. Bind tools cho AI
        self.llm_with_tools = self.lc_llm.bind_tools(SCANNER_AGENT_TOOLS)

        # 2. Tự động tạo map tool {name: func} để execute thủ công nếu cần
        self.tools_map = {tool.name: tool for tool in SCANNER_AGENT_TOOLS}

    def run_batch(
        self, target_groups: List[str], specific_checks: List[str]
    ) -> List[str]:
        """
        Hàm được gọi bởi Orchestrator (Scanning Node).
        Xử lý cả Service Groups và Specific Checks.
        """
        collected_job_ids = []
        print(f"[ScannerAgent] 🚀 Bắt đầu Batch Scan...")

        # 1. Xử lý Specific Checks (Nếu có danh sách Check ID cụ thể)
        # VD: ['check_s3_01', 'check_iam_02']
        if specific_checks:
            # Gom tất cả check IDs vào 1 request để tối ưu (hoặc chia nhỏ nếu cần)
            ids_str = ", ".join(specific_checks)
            print(f"[ScannerAgent] -> Requesting specific checks: {ids_str}")

            # Tạo prompt thật rõ để AI chọn tool 'start_scan_by_check_ids'
            task_desc = (
                f"Start a security scan specifically for these check IDs: {ids_str}"
            )

            job_id = self.run_scan(task_desc)
            if job_id:
                collected_job_ids.append(job_id)

        # 2. Xử lý Target Groups (Nếu có tên service)
        # VD: ['s3', 'iam']
        if target_groups:
            for group in target_groups:
                print(f"[ScannerAgent] -> Requesting scan for group: {group}")

                # Tạo prompt thật rõ để AI chọn tool 'start_scan_by_service_group'
                task_desc = f"Start a security scan for the service group: {group}"

                job_id = self.run_scan(task_desc)
                if job_id:
                    collected_job_ids.append(job_id)

        return collected_job_ids

    def run_scan(self, task_description: str) -> Optional[str]:
        """
        Nhận lệnh -> AI suy nghĩ -> Gọi Tool -> Trả về Job ID
        """
        messages = [
            SystemMessage(
                content="Bạn là trợ lý bảo mật AWS. Nhiệm vụ của bạn là gọi Tool thích hợp để quét hệ thống dựa trên yêu cầu."
            ),
            HumanMessage(content=task_description),
        ]

        try:
            # 1. Gọi AI
            ai_msg = self.llm_with_tools.invoke(messages)

            # 2. Xử lý Tool Call
            if ai_msg.tool_calls:
                for tool_call in ai_msg.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]

                    target_tool = self.tools_map.get(tool_name)

                    if target_tool:
                        try:
                            print(
                                f"[ScannerAgent] 🛠  Calling tool: {tool_name} with args: {tool_args}"
                            )
                            # Thực thi tool
                            tool_output = target_tool.invoke(tool_args)

                            # Trích xuất Job ID từ output
                            jid = self._extract_job_id(tool_output)
                            if jid:
                                print(f"[ScannerAgent] ✅ Job Created: {jid}")
                                return jid
                            else:
                                print(
                                    f"[ScannerAgent] ⚠️ Tool executed but returned no Job ID."
                                )

                        except Exception as e:
                            print(f"[ScannerAgent] ❌ Lỗi tool {tool_name}: {e}")
                            return None
                    else:
                        print(
                            f"[ScannerAgent] ❌ Lỗi: Tool '{tool_name}' không tồn tại trong map."
                        )
                        return None
            else:
                print(
                    f"[ScannerAgent] ⚠️ AI không gọi tool nào cho task: '{task_description}'"
                )
                return None

        except Exception as e:
            print(f"[ScannerAgent] ❌ Lỗi Critical: {e}")
            return None

        return None

    def _extract_job_id(self, tool_output):
        try:
            data = tool_output
            if isinstance(tool_output, str):
                data = json.loads(tool_output)

            if isinstance(data, dict):
                # 🔧 FIX: support nested data
                if "job_id" in data:
                    return data["job_id"]

                nested = data.get("data")
                if isinstance(nested, dict):
                    return nested.get("job_id")

        except Exception:
            pass
        return None

