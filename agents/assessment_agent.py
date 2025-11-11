import json
from .base_agent import BaseAgent
from aws_smm_data import SMMRetriever # <-- Import Module Checklist

class AssessmentAgent(BaseAgent):
    """
    Agent này thực hiện Đánh giá Độ trưởng thành (Maturity Assessment).
    Nó sử dụng RAG (truy vấn SMMRetriever) và so sánh kết quả quét Prowler.
    """
    
    SYSTEM_PROMPT = """
    Bạn là một chuyên gia Đánh giá Độ trưởng thành Bảo mật AWS (AWS Security Maturity Assessor).
    Nhiệm vụ của bạn là đọc các TIÊU CHUẨN SMM và KẾT QUẢ QUÉT THỰC TẾ.
    Sau đó, hãy đưa ra một đánh giá chuyên nghiệp.

    QUY TẮC ĐÁNH GIÁ:
    1. Chỉ tập trung vào Domain được yêu cầu.
    2. So sánh KẾT QUẢ QUÉT (scan_results) với các TIÊU CHUẨN SMM (smm_documents).
    3. Nếu kết quả quét cho thấy các finding (lỗi) liên quan đến TIÊU CHUẨN (tức là mã lỗi Prowler trong 'prowler_checks_map' bị FAIL), tổ chức đó CHƯA đạt mức độ trưởng thành (Maturity Level) đó.
    4. Cung cấp một báo cáo chuyên nghiệp, bao gồm:
       - Tên Domain được đánh giá.
       - Tóm tắt Mức độ trưởng thành HIỆN TẠI (ví dụ: "Đạt Level 1, Chưa đạt Level 2").
       - Liệt kê các TIÊU CHUẨN còn thiếu (dẫn chứng từ smm_documents) và các LỖI PROWLER (dẫn chứng từ scan_results) liên quan đến tiêu chuẩn đó.
    """
    
    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)
        self.retriever = SMMRetriever()
    
    def run_assessment(self, structured_report_data: list, domain_to_assess: str) -> str:
        """
        Thực hiện đánh giá độ trưởng thành cho một Domain cụ thể.
        """
        print(f"--------------------------------------------------")
        print(f"[AssessmentAgent] 🤖 Bắt đầu Đánh giá Độ trưởng thành cho Domain: {domain_to_assess}")
        
        # BƯỚC 1: RAG - Truy vấn SMM (Lấy Checklist)
        smm_documents = self.retriever.retrieve_by_domain(domain_to_assess)
        
        if not smm_documents:
            return f"Lỗi: Không tìm thấy tiêu chuẩn SMM cho Domain '{domain_to_assess}'."
            
        # BƯỚC 2: Xây dựng Prompt
        
        # Đưa dữ liệu quét và tiêu chuẩn SMM vào prompt
        prompt_data = {
            "smm_documents": smm_documents,
            "scan_results": structured_report_data # Dữ liệu JSON thô đã thu thập
        }
        
        user_query = f"""
        Thực hiện đánh giá độ trưởng thành bảo mật cho Domain: {domain_to_assess}.

        Đây là các tiêu chuẩn SMM (CHECKLIST) được tra cứu (RAG) từ cơ sở dữ liệu:
        --- SMM CHECKLIST ---
        {json.dumps(prompt_data['smm_documents'], indent=2, ensure_ascii=False)}
        --- HẾT SMM CHECKLIST ---

        Và đây là kết quả quét Prowler thực tế (CHỈ CẦN QUAN TÂM ĐẾN 'FAIL'):
        --- KẾT QUẢ QUÉT THÔ ---
        {json.dumps(prompt_data['scan_results'], indent=2, ensure_ascii=False)}
        --- HẾT KẾT QUẢ QUÉT THÔ ---
        
        Hãy viết báo cáo theo QUY TẮC ĐÁNH GIÁ (SYSTEM PROMPT)
        """
        
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_query}
        ]
        
        # BƯỚC 3: Gọi AI
        print(f"[AssessmentAgent] 🤖 Đang gọi AI để so sánh {len(smm_documents)} tiêu chuẩn với kết quả quét...")
        response_message = self.call_llm(messages)
        
        if response_message and response_message.content:
            return response_message.content
        else:
            return "Lỗi: Agent đánh giá không thể tạo báo cáo."