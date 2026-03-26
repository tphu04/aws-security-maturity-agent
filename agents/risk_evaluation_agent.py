import json
import re
import time
import requests
from typing import List, Dict, Any
from langchain_core.callbacks import BaseCallbackHandler
from .base_agent import BaseAgent

# Import LangChain Ollama và message types
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage


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


class RiskEvaluationAgent(BaseAgent):
    """
    RiskEvaluationAgent v4 (Compatible with Normalizer)
    --------------------------------------------------
    - Nhận danh sách findings ĐÃ CHUẨN HOÁ (từ Normalizer).
    - Lọc các finding có status="FAIL".
    - Gọi LLM để chấm điểm (Severity/Risk Score).
    """

    SYSTEM_PROMPT_SINGLE = """
        Bạn là Chuyên gia An ninh mạng AWS (Senior AWS Security Analyst)._
        Nhiệm vụ: Đánh giá rủi ro dựa trên thông tin lỗ hổng và RAG Context (Compliance & Best Practices).

        HƯỚNG DẪN CHẤM ĐIỂM (SCORING RUBRIC):
        1. CRITICAL (Score 9-10): Public Access vào dữ liệu nhạy cảm, chiếm quyền Admin, mất dữ liệu.
        2. HIGH (Score 7-8): Cấu hình sai nghiêm trọng, thiếu mã hóa, dịch vụ phơi bày ra internet.
        3. MEDIUM (Score 4-6): Thiếu Logging/Monitoring, thiếu MFA, vi phạm Compliance không nguy hiểm tức thì.
        4. LOW (Score 1-3): Lỗi thông tin, thiếu Tagging.

        LƯU Ý QUAN TRỌNG: 
        - Hãy tham khảo phần "rag_context" (nếu có). Nếu lỗ hổng vi phạm các chuẩn nghiêm trọng (như CIS, PCI-DSS) hoặc có official_severity là High/Critical từ AWS, hãy điều chỉnh điểm số cho phù hợp.

        YÊU CẦU OUTPUT JSON:
        {
            "ai_severity": "Critical" | "High" | "Medium" | "Low",
            "ai_risk_score": <int 0-10>,
            "ai_reasoning": "<Giải thích ngắn gọn 1-2 câu, có nhắc đến chuẩn compliance nếu có>"
        }
        """

    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)
        self.timer = TimerCallback()
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            format="json",
            callbacks=[self.timer],
        )

    def get_llm_metrics(self) -> Dict[str, Any]:
        return {
            "total_latency": round(self.timer.total_duration, 4),
            "call_history": [round(t, 4) for t in self.timer.call_history],
            "call_count": len(self.timer.call_history),
        }

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
    def _fetch_risk_context_batch(self, check_ids: list) -> Dict[str, Any]:
            if not check_ids: return {}
            url = "http://localhost:8001/v1/context/build"
            
            formatted_ids = [f"check:{cid}" if not str(cid).startswith("check:") else cid for cid in check_ids]
            payload = {"consumer": "risk", "check_ids": formatted_ids, "include_mappings": True}

            try:
                response = requests.post(url, json=payload, timeout=10)
                data = response.json()
                
                # --- PHẦN SỬA ĐỔI CHÍNH Ở ĐÂY ---
                # Truy cập đúng vào related_findings thay vì checks
                risk_bundle = data.get("data", {}).get("payload", {}).get("risk_bundle", {})
                findings = risk_bundle.get("related_findings", []) # API của bạn dùng key này
                mappings = risk_bundle.get("control_mapping", [])   # Và key này cho compliance
                
                context_map = {}
                # 1. Map thông tin cơ bản (Severity, Title)
                for f in findings:
                    cid = f.get("check_id")
                    if cid:
                        clean_id = str(cid).replace("check:", "")
                        context_map[clean_id] = {
                            "severity": f.get("severity"),
                            "title": f.get("title"),
                            "mappings": [] # Khởi tạo mảng mappings
                        }
                
                # 2. Bơm thêm thông tin Compliance Mapping vào
                for m in mappings:
                    cid = m.get("check_id")
                    clean_id = str(cid).replace("check:", "")
                    if clean_id in context_map:
                        context_map[clean_id]["mappings"].append(m.get("capability_id"))

                return context_map
                
            except Exception as e:
                print(f"   [RiskEvaluationAgent] ❌ Lỗi bóc tách JSON RAG: {e}")
                return {}
    # ===============================================================
    # 2. CORE: XỬ LÝ
    # ===============================================================
    def run(self, normalized_findings: list) -> list:
            """
            Input: List[Dict] đã được chuẩn hóa bởi Normalizer.
            Output: List[Dict] đã được bổ sung điểm rủi ro từ AI và Compliance từ RAG.
            """
            print("--------------------------------------------------")

            # 1. LỌC FINDINGS (Chỉ lấy FAIL)
            fail_findings = [
                f
                for f in normalized_findings
                if isinstance(f, dict) and f.get("status") == "FAIL"
            ]

            if not fail_findings:
                print(
                    "[RiskEvaluationModule] Không có finding 'FAIL' nào. Hệ thống an toàn."
                )
                return []

            print(
                f"[RiskEvaluationModule] Bắt đầu phân tích rủi ro cho {len(fail_findings)} finding(s) 'FAIL'..."
            )

            # --- BƯỚC MỚI: LẤY RAG CONTEXT THEO LÔ (BATCH) ---
            unique_check_ids = []
            for f in fail_findings:
                # Ưu tiên lấy từ các key trực tiếp trước
                cid = f.get("check_id") or f.get("CheckID") or f.get("checkId")
                
                # Nếu không có, mổ xẻ từ finding_id / uid / id
                if not cid:
                    raw_str = f.get("finding_id") or f.get("uid") or f.get("id") or str(f)
                    # Dùng Regex để bắt theo chuẩn của Prowler (vd: prowler-aws-s3_account_level_public_access_blocks-123...)
                    match = re.search(r'prowler-[^-]+-([a-z0-9_]+)-\d+', raw_str)
                    if match:
                        cid = match.group(1)
                    else:
                        # Fallback tìm cụm có dấu gạch dưới
                        fallback_match = re.search(r'\b[a-z0-9]+_[a-z0-9_]+\b', raw_str)
                        if fallback_match:
                            cid = fallback_match.group(0)
                            
                if cid:
                    unique_check_ids.append(cid)
                    
            unique_check_ids = list(set(unique_check_ids))
            
            print(f"   -> Đang tải RAG Context cho {len(unique_check_ids)} loại lỗ hổng...")
            rag_context_map = self._fetch_risk_context_batch(unique_check_ids)

            enriched_results = []

            # 2. LOOP VÀ CHẤM ĐIỂM
            for index, finding in enumerate(fail_findings):
                short_title = finding.get("description", "Unknown")[:60]
                print(
                    f"--- [{index + 1}/{len(fail_findings)}] Evaluating: {short_title}..."
                )

                try:
                    # Trích xuất lại check_id cho finding hiện tại (dùng chung logic Regex ở trên)
                    check_id = finding.get("check_id") or finding.get("CheckID") or finding.get("checkId")
                    if not check_id:
                        raw_str = finding.get("finding_id") or finding.get("uid") or finding.get("id") or str(finding)
                        match = re.search(r'prowler-[^-]+-([a-z0-9_]+)-\d+', raw_str)
                        if match:
                            check_id = match.group(1)
                        else:
                            fallback_match = re.search(r'\b[a-z0-9]+_[a-z0-9_]+\b', raw_str)
                            check_id = fallback_match.group(0) if fallback_match else ""

                    # Lookup RAG data
                    rag_data = rag_context_map.get(check_id, {})

                    # A. Tạo View tối giản cho LLM + Bơm RAG Context
                    llm_view = {
                        "check_id": check_id,
                        "service": finding.get("service"),
                        "resource_id": finding.get("resource_id"),
                        "region": finding.get("region"),
                        "description": finding.get("description"),
                        "original_severity": finding.get("severity"),  # Severity gốc của Prowler
                        "remediation_text": finding.get("remediation_text"),
                        "rag_context": {
                            "official_severity": rag_data.get("severity", "Unknown"),
                            "compliance_mappings": rag_data.get("mappings", []),
                            "extended_description": rag_data.get("description", "")
                        }
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
                    print(f"      => Điểm AI chấm: {ai_data.get('ai_severity')} (Score: {ai_data.get('ai_risk_score')})")
                    print(f"      => Lý do (AI): {ai_data.get('ai_reasoning')}")
                    mappings = rag_data.get("mappings", [])
                    if mappings:
                        print(f"      => 📚 Vi phạm chuẩn (Từ RAG): {len(mappings)} frameworks")
                    else:
                        print(f"      => 📚 Vi phạm chuẩn (Từ RAG): Không có data")
                    # D. Merge vào Finding gốc
                    enriched_finding = finding.copy()
                    enriched_finding.update(
                        {
                            "severity": ai_data.get(
                                "ai_severity", finding.get("severity")
                            ),  # Ưu tiên AI severity
                            "risk_score": ai_data.get("ai_risk_score", 0),
                            "reasoning": ai_data.get("ai_reasoning", ""),
                            "prowler_severity": finding.get("severity"),
                            "compliance": rag_data.get("mappings", []) # Lưu thêm Compliance để report
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
                f"[RiskEvaluationModule] Hoàn tất. Output {len(sorted_results)} findings đã chấm điểm."
            )
            return sorted_results