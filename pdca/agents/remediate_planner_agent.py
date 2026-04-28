import inspect
import json
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from pdca.agents.shared.callbacks import TimerCallback
from pdca.observability.logger import get_logger
from pdca.observability.tracing import span as obs_span
from pdca.tools import REGISTRY, REMEDIATION_TOOLS

from .base_agent import BaseAgent

logger = get_logger(__name__)

# B14: manual_only flag là metadata trong REGISTRY (`REGISTRY.is_manual_only`).


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
    def __init__(self, model_name, api_key, base_url, aws_context=None,
                 callbacks: list = None):
        super().__init__(model_name, api_key, base_url, callbacks=callbacks)
        self.timer = TimerCallback()
        self.aws_context = aws_context or {}

        # Langfuse hook (B4): timer đo latency, self.callbacks propagate
        # external handlers (eg. CallbackHandler từ langfuse).
        self.lc_llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            callbacks=[self.timer] + self.callbacks,
        )

        # Bind tools để LLM biết schema, nhưng KHÔNG dùng để invoke trực tiếp
        self.llm_with_tools = self.lc_llm.bind_tools(REMEDIATION_TOOLS)

        # Tạo chuỗi mô tả tool để nạp vào prompt
        self.tools_desc_str = "\n".join(
            [f"- {tool.name}: {tool.description}" for tool in REMEDIATION_TOOLS]
        )

        # B14: REGISTRY là single source of truth. Giữ tools_map làm cache nhỏ
        # cho hot path (LLM response loop) — tránh dict comprehension mỗi finding.
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
        with obs_span(
            "agent:RemediationPlannerAgent",
            input={"findings_count": len(findings or [])},
        ) as agent_sp:
            result = self._plan_remediation_impl(findings)
            agent_sp.update(
                output={
                    "plan_count": len(result),
                    "manual_count": sum(1 for p in result if p.get("manual_required")),
                }
            )
            return result

    def _plan_remediation_impl(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            plans = []
            logger.info("Planning remediation", extra={"finding_count": len(findings)})

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
                    except Exception:
                        logger.warning("LLM response is not valid JSON",
                                       extra={"event_code": event_code})
                        continue

                    tool_name = parsed.get("tool_name")

                    if not tool_name or tool_name not in self.tools_map:
                        logger.warning("No matching tool found",
                                       extra={"event_code": event_code,
                                              "tool_name": tool_name})
                        continue

                    tool_obj = self.tools_map[tool_name]

                    # Build params tự động
                    tool_params = build_params_from_signature(
                        tool=tool_obj,
                        finding=finding,
                        aws_context=self.aws_context,
                    )

                    # B14: REGISTRY là source of truth cho manual_only flag
                    is_manual = REGISTRY.is_manual_only(tool_name)

                    # B16: canonical key = `tool_name` / `tool_params`
                    # (thay cho `tool_id` / `params` cũ). Orchestrator giờ
                    # spread `**plan` vào task — không còn translate keys.
                    plans.append(
                        {
                            "finding_id": finding_id,
                            "tool_name": tool_name,
                            "tool_params": tool_params,
                            "reasoning": parsed.get("reasoning", "Không có giải thích"),
                            "manual_required": is_manual,
                            "compliance": compliance_list,
                            "severity": finding.get("severity"),
                            "risk_score": finding.get("risk_score"),
                        }
                    )

                except Exception as e:
                    logger.error("Tool reasoning failed",
                                 extra={"event_code": event_code, "error": str(e)})

            logger.info("Remediation plan generated", extra={"task_count": len(plans)})
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
