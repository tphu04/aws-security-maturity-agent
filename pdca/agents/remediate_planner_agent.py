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

    SYSTEM_PROMPT = """Bạn là kỹ sư AWS Security cấp cao, chuyên xử lý sự cố bảo mật cloud theo chuẩn CIS, NIST, PCI-DSS.
Nhiệm vụ: Phân tích finding bảo mật → chọn tool phù hợp → giải thích rõ ràng bằng tiếng Việt cho người vận hành.

DANH SÁCH CÔNG CỤ:
{tool_descriptions}

QUY TẮC CHỌN TOOL:
- Ưu tiên tool khớp chính xác với loại vi phạm (bucket-level vs account-level).
- Nếu không có tool tự động phù hợp, chọn tool kiểm tra/chuẩn bị thủ công tương ứng.
- Không bao giờ chọn tool sai phạm vi chỉ vì không có lựa chọn tốt hơn.

HƯỚNG DẪN VIẾT TỪNG TRƯỜNG (PHẢI bằng tiếng Việt, KHÔNG dùng tiếng Anh):

"reasoning" — 2-3 câu: (1) Finding này vi phạm điều gì, (2) Tại sao chọn tool này, (3) Rủi ro nếu không xử lý.

"expected_impact" — 1-2 câu: Sau khi thực thi, trạng thái resource thay đổi thế nào. Bắt đầu bằng động từ (ví dụ: "Bucket sẽ...", "Tính năng X sẽ được bật...").

"manual_guidance" — Chỉ điền khi tool KHÔNG tự động thực thi được. Viết 2-3 câu ngắn:
  Câu 1: Tại sao không thể tự động hóa (lý do kỹ thuật hoặc policy của AWS).
  Câu 2-3: Người vận hành cần làm gì ở mức tổng quan (không cần liệt kê lệnh cụ thể — report sẽ có hướng dẫn chi tiết).

--- VÍ DỤ MẪU ---

Finding: S3 bucket không bật MFA Delete. Tool: s3_enable_mfa_delete (manual_only=true).
{{
  "tool_name": "s3_enable_mfa_delete",
  "reasoning": "Bucket vi phạm chuẩn CIS AWS 2.1.2 yêu cầu bật MFA Delete để ngăn xóa object version trái phép. Tool s3_enable_mfa_delete xác minh điều kiện tiên quyết (versioning đã bật) trước khi hướng dẫn bật MFA Delete. Nếu không xử lý, attacker có thể xóa vĩnh viễn dữ liệu khi tài khoản bị xâm phạm.",
  "expected_impact": "Sau khi bật MFA Delete, mọi thao tác xóa object version hoặc tắt versioning sẽ yêu cầu xác thực MFA bổ sung, ngăn chặn xóa dữ liệu trái phép.",
  "manual_guidance": "AWS chỉ cho phép bật MFA Delete bằng root credentials qua CLI — không thể thực hiện qua IAM role hoặc SDK thông thường. Người vận hành cần dùng tài khoản root để kích hoạt tính năng này trên bucket. Hướng dẫn chi tiết từng bước có trong báo cáo."
}}

Finding: S3 bucket thiếu cấu hình Cross-Region Replication. Tool: s3_prepare_replication (manual_only=true).
{{
  "tool_name": "s3_prepare_replication",
  "reasoning": "Bucket vi phạm yêu cầu sao lưu đa vùng theo chuẩn NIST 800-53 CP-9. Tool s3_prepare_replication kiểm tra các điều kiện tiên quyết (versioning, IAM role, destination bucket) cần thiết trước khi bật CRR. Thiếu replication khiến dữ liệu mất hoàn toàn nếu region us-east-1 gặp sự cố.",
  "expected_impact": "Sau khi hoàn thành, dữ liệu trong bucket sẽ được sao chép tự động sang region đích, đảm bảo tính sẵn sàng và phục hồi thảm họa.",
  "manual_guidance": "Bật Cross-Region Replication yêu cầu tạo IAM Role và destination bucket ở region khác — cần quyết định kiến trúc từ người vận hành. Tool này kiểm tra điều kiện tiên quyết; người vận hành thực hiện cấu hình cuối cùng trên AWS Console. Hướng dẫn chi tiết có trong báo cáo."
}}
--- KẾT THÚC VÍ DỤ ---

OUTPUT: Chỉ trả về JSON hợp lệ, không giải thích thêm.
{{
  "tool_name": "<tên_tool>",
  "reasoning": "<tiếng Việt>",
  "expected_impact": "<tiếng Việt>",
  "manual_guidance": "<tiếng Việt hoặc để trống nếu tool tự động>"
}}"""
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

                    # Debug: warn nếu LLM bỏ field optional
                    missing_fields = [
                        k for k in ("expected_impact", "manual_guidance")
                        if not parsed.get(k)
                    ]
                    if missing_fields:
                        logger.warning(
                            "LLM missed optional fields",
                            extra={
                                "event_code": event_code,
                                "tool_name": tool_name,
                                "missing": missing_fields,
                                "raw_keys": list(parsed.keys()),
                            },
                        )

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
                            "expected_impact": parsed.get("expected_impact", ""),
                            "manual_guidance": parsed.get("manual_guidance", ""),
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
