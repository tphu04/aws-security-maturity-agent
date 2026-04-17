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
from pdca.tools import REMEDIATION_TOOLS

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
        Nhiệm vụ: Dựa trên thông tin Finding và chuẩn Compliance liên quan, hãy chọn đúng tool sửa lỗi.

        DANH SÁCH CÔNG CỤ (TOOLS):
        {tool_descriptions}

        QUY TẮC SUY LUẬN MỚI:
        1. Ưu tiên dựa vào "Compliance Context" để chọn Tool. Ví dụ: Nếu vi phạm 'block_public_access', hãy tìm tool có chức năng tương ứng.
        2. Phân biệt rõ cấp độ: Nếu lỗi là cấp Bucket, dùng tool Bucket. Nếu lỗi cấp Account, dùng tool Account.
        3. Trong 'reasoning', hãy nhắc tên chuẩn Compliance (ví dụ: "Vi phạm chuẩn {compliance_data}") để tăng tính thuyết phục.

        FORMAT OUTPUT JSON:
        {{
        "tool_name": "<tên_tool_hoặc_null>",
        "reasoning": "<lý do chọn tool + nhắc đến compliance>"
        }}
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
            Input: Danh sách Fail Findings (Đã được enriched bởi RiskEvaluationAgent)
            Output: Danh sách Remediation Plans có chứa thông tin Compliance
            """
            plans = []
            print(f"[RemediationPlanner] Đang lập kế hoạch cho {len(findings)} findings...")

            for finding in findings:
                if finding.get("status") != "FAIL":
                    continue

                # --- TRÍCH XUẤT DỮ LIỆU TỪ RAG & RISK AGENT ---
                compliance_list = finding.get("compliance", [])
                compliance_str = ", ".join(compliance_list) if compliance_list else "Unknown/None"
                risk_reasoning = finding.get("reasoning", "N/A") # Phân tích từ Risk Agent

                finding_id = finding.get("finding_id")
                event_code = finding.get("event_code", "")
                description = finding.get("description") or finding.get("short_description") or ""
                resource_id = finding.get("resource_id", "N/A")
                region = finding.get("region", "us-east-1")

                if not resource_id or resource_id == "N/A":
                    continue

                # Tạo Prompt với Context mới
                formatted_prompt = self.SYSTEM_PROMPT.replace(
                    "{tool_descriptions}", self.tools_desc_str
                )
                
                user_msg = f"""
                LẬP KẾ HOẠCH SỬA LỖI:
                - Mã lỗi (event_code): {event_code}
                - Mô tả: {description}
                - Chuẩn vi phạm (RAG): {compliance_str}
                - Phân tích rủi ro: {risk_reasoning}
                - Resource ID: {resource_id}
                - Region: {region}
                
                YÊU CẦU: Hãy chọn tool phù hợp nhất để thỏa mãn chuẩn {compliance_str}.
                OUTPUT CHỈ JSON.
                """

                try:
                    response = self.lc_llm.invoke(
                        [
                            SystemMessage(content=formatted_prompt),
                            HumanMessage(content=user_msg),
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

                    if not tool_name or tool_name not in self.tools_map:
                        print(f"[Planner] ⚠️ Không tìm thấy tool phù hợp cho: {event_code}")
                        continue

                    tool_obj = self.tools_map[tool_name]

                    # Build params tự động
                    tool_params = build_params_from_signature(
                        tool=tool_obj,
                        finding=finding,
                        aws_context=self.aws_context,
                    )

                    is_manual = tool_name in ALWAYS_MANUAL_TOOLS

                    # THÊM: Lưu thông tin compliance vào task để hiển thị ở bước Review
                    plans.append(
                        {
                            "finding_id": finding_id,
                            "tool_id": tool_name,
                            "params": tool_params,
                            "reasoning": parsed.get("reasoning", "Không có giải thích"),
                            "manual_required": is_manual,
                            "compliance": compliance_list, # Quan trọng: Để in ra màn hình
                            "severity": finding.get("severity"), # Lấy từ Risk Agent luôn
                            "risk_score": finding.get("risk_score")
                        }
                    )

                except Exception as e:
                    print(f"[RemediationPlanner] ❌ Lỗi khi suy luận tool: {e}")

            print(f"[RemediationPlanner] Generated remediation plan với {len(plans)} task(s).")
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
