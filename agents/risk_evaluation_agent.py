import json
import re
from typing import List, Dict, Any

from .base_agent import BaseAgent

# Import LangChain Ollama và message types
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage


class RiskEvaluationAgent(BaseAgent):
    """
    RiskEvaluationAgent v4 (Compatible with Normalizer)
    --------------------------------------------------
    - Nhận danh sách findings ĐÃ CHUẨN HOÁ (từ Normalizer).
    - Lọc các finding có status="FAIL".
    - Gọi LLM để chấm điểm (Severity/Risk Score).
    """

    SYSTEM_PROMPT_SINGLE = """
    Bạn là Chuyên gia An ninh mạng AWS (Senior AWS Security Analyst).
    Nhiệm vụ: Đánh giá rủi ro dựa trên thông tin lỗ hổng đã được cung cấp.

    HƯỚNG DẪN CHẤM ĐIỂM (SCORING RUBRIC):
    
    1. CRITICAL (Score 9-10):
        - Public Access vào dữ liệu nhạy cảm (S3 Public, SG Open 0.0.0.0/0).
        - Chiếm quyền Admin/Root hoặc leo thang đặc quyền.
        - Mất dữ liệu vĩnh viễn.

    2. HIGH (Score 7-8):
        - Cấu hình sai nghiêm trọng (IAM Policy rộng) nhưng giới hạn nội bộ.
        - Thiếu mã hóa dữ liệu quan trọng.
        - Services (EC2/Lambda) phơi bày ra internet không cần thiết.

    3. MEDIUM (Score 4-6):
        - Thiếu Logging/Monitoring (CloudTrail, VPC Flow Logs).
        - Thiếu MFA.
        - Vi phạm Compliance không gây nguy hiểm tức thì.

    4. LOW (Score 1-3):
        - Lỗi cấu hình nhỏ, thông tin (Informational).
        - Tagging thiếu sót.

    YÊU CẦU OUTPUT JSON:
    {
        "ai_severity": "Critical" | "High" | "Medium" | "Low",
        "ai_risk_score": <int 0-10>,
        "ai_reasoning": "<Giải thích ngắn gọn 1 câu tại sao>"
    }
    """

    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)
        self.llm = ChatOllama(
            model=model_name, base_url=base_url, temperature=0, format="json"
        )

    # ===============================================================
    # 1. UTIL: Trích JSON (Robust)
    # ===============================================================
    def _extract_json_from_text(self, text: str) -> str:
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            return match.group(1)
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            return match.group(1)
        return text

    # ===============================================================
    # 2. CORE: XỬ LÝ
    # ===============================================================
    def run(self, normalized_findings: list) -> list:
        """
        Input: List[Dict] đã được chuẩn hóa bởi Normalizer.
        Output: List[Dict] đã được bổ sung điểm rủi ro từ AI.
        """
        print("--------------------------------------------------")

        # 1. LỌC FINDINGS (Chỉ lấy FAIL)
        # Normalizer đã flatten dữ liệu, nên ta truy cập trực tiếp key "status"
        fail_findings = [
            f
            for f in normalized_findings
            if isinstance(f, dict) and f.get("status") == "FAIL"
        ]

        if not fail_findings:
            print(
                "[RiskEvaluationAgent] ✅ Không có finding 'FAIL' nào. Hệ thống an toàn."
            )
            return []

        print(
            f"[RiskEvaluationAgent] 🤖 Bắt đầu phân tích rủi ro cho {len(fail_findings)} finding(s) 'FAIL'..."
        )

        enriched_results = []

        # 2. LOOP VÀ CHẤM ĐIỂM
        for index, finding in enumerate(fail_findings):
            short_title = finding.get("description", "Unknown")[:60]
            print(
                f"--- [{index + 1}/{len(fail_findings)}] Evaluating: {short_title}..."
            )

            try:
                # A. Tạo View tối giản cho LLM (Tiết kiệm token & tăng độ chính xác)
                # Dữ liệu từ Normalizer đã có sẵn các trường này
                llm_view = {
                    "service": finding.get("service"),
                    "resource_id": finding.get("resource_id"),
                    "region": finding.get("region"),
                    "description": finding.get("description"),
                    "original_severity": finding.get(
                        "severity"
                    ),  # Severity gốc của Prowler
                    "remediation_text": finding.get("remediation_text"),
                }

                # B. Gọi LLM
                messages = [
                    SystemMessage(content=self.SYSTEM_PROMPT_SINGLE),
                    HumanMessage(content=json.dumps(llm_view, ensure_ascii=False)),
                ]

                # Invoke
                response = self.llm.invoke(messages)

                # C. Parse Output
                ai_data = {
                    "ai_severity": "Medium",
                    "ai_risk_score": 5,
                    "ai_reasoning": "Parse Error",
                }

                if response and response.content:
                    try:
                        json_str = self._extract_json_from_text(response.content)
                        parsed = json.loads(json_str)
                        # Merge an toàn
                        ai_data.update(parsed)
                    except Exception as e:
                        print(f"   -> ⚠️ Lỗi parse JSON AI: {e}")

                # D. Merge vào Finding gốc
                # Chúng ta giữ nguyên finding gốc và chỉ thêm các trường AI vào
                enriched_finding = finding.copy()
                enriched_finding.update(
                    {
                        "severity": ai_data.get(
                            "ai_severity", finding.get("severity")
                        ),  # Ưu tiên AI severity
                        "risk_score": ai_data.get("ai_risk_score", 0),
                        "reasoning": ai_data.get("ai_reasoning", ""),
                        # Giữ lại severity gốc để tham khảo nếu cần
                        "prowler_severity": finding.get("severity"),
                    }
                )

                enriched_results.append(enriched_finding)

            except Exception as e:
                print(f"   -> ❌ Lỗi xử lý finding: {e}")
                # Fallback: Giữ nguyên finding gốc
                enriched_results.append(finding)

        # 3. SẮP XẾP (Priority Sort)
        severity_map = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "N/A": 0}

        sorted_results = sorted(
            enriched_results,
            key=lambda f: (
                severity_map.get(f.get("severity"), 0),
                f.get("risk_score", 0),
            ),
            reverse=True,
        )

        print(
            f"[RiskEvaluationAgent] ✅ Hoàn tất. Output {len(sorted_results)} findings đã chấm điểm."
        )
        return sorted_results
