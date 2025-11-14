import json
import re  # <-- Thêm import
from .base_agent import BaseAgent
from aws_smm_data import SMMRetriever  # <-- Module Checklist (Giả định có hàm .search)


class AssessmentAgent(BaseAgent):
    """
    (LOGIC MỚI)
    Agent này nhận danh sách findings ĐÃ ĐƯỢC PHÂN TÍCH RỦI RO.
    Nó lặp qua TỪNG finding, dùng RAG (SMMRetriever) để tìm Tiêu chuẩn SMM
    bị vi phạm, sau đó gọi LLM để thêm phân tích chi tiết về Độ trưởng thành.
    """

    # --- (PROMPT MỚI) ---
    SYSTEM_PROMPT_SINGLE_FINDING = """
    Bạn là một API chỉ trả về MỘT đối tượng JSON duy nhất.
    Nhiệm vụ của bạn là nhận MỘT finding (Prowler) và MỘT tiêu chuẩn SMM (Checklist) mà nó vi phạm.
    Phân tích và trả về MỘT JSON object chứa:
    "smm_control_id": (Mã của tiêu chuẩn SMM, ví dụ 'S3.2.1')
    "smm_maturity_level": (Cấp độ trưởng thành, ví dụ 2)
    "smm_domain": (Lĩnh vực SMM, ví dụ 'Data Protection')
    "assessment_notes": (Một phân tích NGẮN GỌN giải thích tại sao finding này vi phạm tiêu chuẩn, và ý nghĩa của nó.)

    VÍ DỤ INPUT (USER):
    --- PROWLER FINDING ---
    { "check_title": "s3_bucket_public_read_access", "status_details": "S3 bucket my-bucket has public read access." }
    --- SMM CONTROL ---
    { "control_id": "S3.2.1", "maturity_level": 2, "domain": "Data Protection", "title": "Block S3 public access" }
    
    VÍ DỤ OUTPUT (BẠN):
    {
        "smm_control_id": "S3.2.1",
        "smm_maturity_level": 2,
        "smm_domain": "Data Protection",
        "assessment_notes": "Phát hiện này (S3 public read) vi phạm trực tiếp Tiêu chuẩn SMM 'S3.2.1'. Đây là một vi phạm ở Cấp độ 2 (Foundational), cho thấy một lỗ hổng bảo mật cơ bản trong việc bảo vệ dữ liệu."
    }
    KHÔNG GIẢI THÍCH GÌ THÊM. CHỈ TRẢ VỀ JSON OBJECT.
    """

    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)
        self.retriever = SMMRetriever()

    def _get_json_from_llm(self, text: str) -> dict:
        """Helper function để trích xuất JSON từ phản hồi LLM"""
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        print(f"   -> ⚠️ Không thể parse JSON từ: {text[:100]}...")
        return None

    # --- (HÀM RUN ĐÃ VIẾT LẠI HOÀN TOÀN) ---
    def run(self, enriched_findings: list) -> list:
        """
        Chạy đánh giá SMM cho TỪNG finding một.
        Sử dụng RAG để tìm SMM control, sau đó dùng LLM để phân tích.
        """
        print(f"--------------------------------------------------")
        print(
            f"[AssessmentAgent] 🤖 Bắt đầu Đánh giá SMM cho {len(enriched_findings)} finding(s) (từng cái một)..."
        )

        assessed_findings_list = []  # List mới để chứa kết quả cuối cùng

        for index, finding in enumerate(enriched_findings):
            print(
                f"--- [Finding {index + 1}/{len(enriched_findings)}] Đang đánh giá: {finding.get('check_title')[:70]}..."
            )

            finding["smm_assessment"] = {}

            try:
                # BƯỚC 1: RAG (TRA CỨU TRỰC TIẾP)
                # Lấy Prowler Check ID từ finding
                prowler_check_id = finding.get("prowler_check_id")

                if not prowler_check_id:
                    print("   -> ⚠️ Không thể tra cứu: Finding thiếu 'check_title'.")
                    finding["smm_assessment"] = {
                        "assessment_notes": "Finding thiếu 'check_title' để tra cứu SMM."
                    }
                    assessed_findings_list.append(finding)
                    continue

                # Gọi hàm tra cứu mới thay vì tìm kiếm ngữ nghĩa
                smm_control = self.retriever.search_by_prowler_check(prowler_check_id)

                if not smm_control:
                    print(
                        f"   -> ⚠️ Không tìm thấy SMM control (Lookup) cho check: '{prowler_check_id}'."
                    )
                    finding["smm_assessment"] = {
                        "assessment_notes": f"Không tìm thấy Tiêu chuẩn SMM (Lookup) tương ứng cho '{prowler_check_id}'."
                    }
                    assessed_findings_list.append(finding)
                    continue

                # BƯỚC 2: LLM - Yêu cầu AI phân tích (Finding + SMM Control)
                # (Logic bên dưới giữ nguyên y hệt code cũ)
                user_prompt = f"""
                Hãy phân tích và trả về JSON theo HƯỚNG DẪN.

                --- PROWLER FINDING (ĐÃ VI PHẠM) ---
                {json.dumps(finding, indent=2, ensure_ascii=False)}

                --- SMM CONTROL (BỊ VI PHẠM) ---
                {json.dumps(smm_control, indent=2, ensure_ascii=False)}
                """

                messages = [
                    {"role": "system", "content": self.SYSTEM_PROMPT_SINGLE_FINDING},
                    {"role": "user", "content": user_prompt},
                ]
                # ... (Phần gọi LLM và Gộp kết quả giữ nguyên) ...

                response_message = self.call_llm(
                    messages, response_format={"type": "json_object"}
                )

                if not response_message or not response_message.content:
                    print("   -> ❌ Lỗi: AI không trả về phản hồi.")
                    finding["smm_assessment"] = {
                        "assessment_notes": "Lỗi AI (no response)."
                    }
                    assessed_findings_list.append(finding)
                    continue

                assessment_data = self._get_json_from_llm(response_message.content)

                if assessment_data and isinstance(assessment_data, dict):
                    finding["smm_assessment"] = assessment_data
                    # (Đổi tên key cho chính xác)
                    smm_id = assessment_data.get(
                        "smm_control_id", smm_control.get("capability")
                    )  # Lấy control_id nếu có, nếu không thì lấy capability
                    print(
                        f"   -> ✅ SMM Mapped: {smm_id} (Level {assessment_data.get('smm_maturity_level')})"
                    )
                else:
                    print(
                        f"   -> ❌ Lỗi: AI trả về JSON không hợp lệ: {response_message.content[:100]}..."
                    )
                    finding["smm_assessment"] = {
                        "assessment_notes": "Lỗi AI (invalid JSON)."
                    }

            except Exception as e:
                print(f"   -> ❌ Lỗi hệ thống (Lookup/LLM): {e}")
                finding["smm_assessment"] = {"assessment_notes": f"Lỗi hệ thống: {e}"}

            assessed_findings_list.append(finding)

        print(
            f"[AssessmentAgent] ✅ Đã đánh giá SMM xong {len(assessed_findings_list)} finding(s)."
        )
        return assessed_findings_list
