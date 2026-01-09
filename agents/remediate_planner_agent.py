import json
import time
from typing import List, Dict, Any
import inspect
from .base_agent import BaseAgent

# Import LangChain Ollama và Message Types
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.callbacks import BaseCallbackHandler

# Import danh sách tool (để lấy mô tả cho AI hiểu)
from agent_tools import REMEDIATION_TOOLS

# Đây là danh sách tool luôn yêu cầu sửa thủ công
ALWAYS_MANUAL_TOOLS = {
    "s3_enable_object_lock",
    "s3_enable_mfa_delete",
    "s3_prepare_replication",
    "s3_remove_cross_account_principals",
    "s3_enable_intelligent_tiering",
}


def build_params_from_signature(tool, finding: Dict, aws_context: Dict):
    """
    Tự động build params từ tool signature
    """

    sig = inspect.signature(tool.func)
    params = {}

    for name, param in sig.parameters.items():

        # --- Mapping rule ---
        if name == "bucket_name":
            params[name] = finding.get(
                "resource_id"
            )  # Bạn có thể thay đổi theo nhu cầu
        elif name == "resource_id":
            params[name] = finding.get("resource_id")
        elif name == "region":
            params[name] = finding.get("region", aws_context.get("region", "us-east-1"))
        elif name == "account_id":
            params[name] = aws_context.get("account_id")
        else:
            continue  # Bỏ qua các tham số không rõ nguồn gốc

    return params


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


class RemediationPlannerAgent(BaseAgent):
    """
    PLANNER AGENT:
    - Nhiệm vụ: Nhận input là lỗi -> Output là kế hoạch (Tên tool + Tham số).
    - Đặc điểm: Chỉ "nghĩ", tuyệt đối KHÔNG "làm" (không execute code).
    """

    SYSTEM_PROMPT = """
    Bạn là chuyên gia AWS Security chuyên về remediating misconfigurations.
    Nhiệm vụ: dựa trên thông tin finding, hãy chọn đúng tool để sửa lỗi.

    Bạn phải trả 2 trường:
    1) tool_name  → Tên tool chính xác trong danh sách tools. Nếu không tìm được thì dùng null.
    2) reasoning  → Một câu giải thích ngắn gọn vì sao chọn tool đó.


    FORMAT OUTPUT BẮT BUỘC (JSON THUẦN):
    {
    "tool_name": "<tên_tool_trong_danh_sách_hoặc_null>",
    "reasoning": "<một câu giải thích ngắn gọn>"
    }

    TRẢ LỜI CHỈ BẰNG JSON. KHÔNG dùng Markdown block (```json). KHÔNG THÊM CHỮ, KHÔNG GIẢI THÍCH.

    DANH SÁCH CÔNG CỤ (TOOLS):
    {tool_descriptions}

    QUY TẮC SUY LUẬN (BẮT BUỘC):
    1. So sánh kỹ "Tiêu đề lỗi" (Check Title) với "Chức năng" của từng tool.
    2. Tìm từ khóa khớp nhau (Ví dụ: Lỗi "Versioning" -> Phải tìm tool có chữ "versioning").
    3. Lỗi "Logging" -> Phải tìm tool có chữ "logging".
    4. Lỗi "Encryption" -> Phải tìm tool có chữ "encryption" hoặc "kms".
    5. Nếu lỗi là "Public Access" -> Mới được dùng tool "s3_public_access_block".
    6. Nếu lỗi có chữ "ACL", "ACLs enabled", "ACL prohibited", "BucketOwnerEnforced" -> Tìm các tool có chữ "acls"
    
    Đừng đoán mò. Hãy chọn tool có ý nghĩa sát nhất với lỗi. Nếu không tìm thấy tool phù hợp, hãy trả lời "Không tìm thấy công cụ phù hợp".
    """

    def __init__(self, model_name, api_key, base_url, aws_context=None):
        super().__init__(model_name, api_key, base_url)
        self.timer = TimerCallback()
        self.aws_context = aws_context or {}

        # Init LLM
        self.lc_llm = ChatOllama(
            model=model_name, base_url=base_url, temperature=0, callbacks=[self.timer]
        )

        # Bind tools để LLM biết schema, nhưng KHÔNG dùng để invoke trực tiếp
        self.llm_with_tools = self.lc_llm.bind_tools(REMEDIATION_TOOLS)

        # Tạo chuỗi mô tả tool để nạp vào prompt
        self.tools_desc_str = "\n".join(
            [f"- {tool.name}: {tool.description}" for tool in REMEDIATION_TOOLS]
        )

        self.tools_map = {t.name: t for t in REMEDIATION_TOOLS}

    def get_llm_metrics(self) -> Dict[str, Any]:
        return {
            "total_latency": round(self.timer.total_duration, 4),
            "call_history": [round(t, 4) for t in self.timer.call_history],
            "call_count": len(self.timer.call_history),
        }

    def plan_remediation(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Input: Danh sách Fail Findings
        Output: Danh sách Remediation Plans (không thực thi)
        """
        plans = []
        print(f"[RemediationPlanner] Đang lập kế hoạch cho {len(findings)} findings...")

        for finding in findings:
            if finding.get("status") != "FAIL":
                continue

            # Chuẩn bị Context
            finding_id = finding.get("finding_id")
            event_code = finding.get("event_code", "")
            description = (
                finding.get("description") or finding.get("short_description") or ""
            )
            resource_id = finding.get("resource_id", "N/A")
            region = finding.get("region", "us-east-1")

            # Validate sơ bộ
            if not resource_id or resource_id == "N/A":
                continue

            # Tạo Prompt
            formatted_prompt = self.SYSTEM_PROMPT.replace(
                "{tool_descriptions}", self.tools_desc_str
            )
            user_msg = f"""
            LẬP KẾ HOẠCH SỬA LỖI:
            - Mã lỗi (event_code): {event_code}
            - Mô tả: {description}
            - Resource ID: {resource_id}
            - Region: {region}
            
            OUTPUT CHỈ JSON. KHÔNG GIẢI THÍCH THÊM.
            """

            try:
                response = self.lc_llm.invoke(
                    [
                        SystemMessage(content=formatted_prompt),
                        HumanMessage(content=f"FINDING:\n{user_msg}"),
                    ]
                )

                parsed = {}
                try:
                    clean_content = self._clean_json_text(response.content)
                    parsed = json.loads(clean_content)
                except:
                    print(f"[RemediationPlanner] ❌ Response không phải JSON hợp lệ.")
                    continue

                tool_name = parsed.get("tool_name")

                # Nếu không có tool phù hợp
                if not tool_name or tool_name not in self.tools_map:
                    print(
                        f"[Planner] ⚠️ Không tìm thấy tool phù hợp cho finding: {event_code}"
                    )
                    continue

                tool_obj = self.tools_map[tool_name]

                # ========================
                # Build params tự động
                # ========================

                tool_params = build_params_from_signature(
                    tool=tool_obj,
                    finding=finding,
                    aws_context=self.aws_context,
                )

                is_manual = tool_name in ALWAYS_MANUAL_TOOLS

                plans.append(
                    {
                        "finding_id": finding_id,
                        "tool_id": tool_name,
                        "params": tool_params,
                        "reasoning": parsed.get(
                            "reasoning", "Không có giải thích từ AI"
                        ),
                        "manual_required": is_manual,
                    }
                )

            except Exception as e:
                print(f"[RemediationPlanner] ❌ Lỗi khi suy luận tool: {e}")

        print(
            f"[RemediationPlanner] Generated remediation plan với {len(plans)} task(s)."
        )

        return plans

    def _clean_json_text(self, text: str) -> str:
        text = text.strip()
        # Xử lý trường hợp có markdown block ```json
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        # Xử lý trường hợp có markdown block ``` thường
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return text.strip()
