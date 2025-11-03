import json
import re 
from .base_agent import BaseAgent
from agent_tools import REMEDIATE_AGENT_TOOLS, AVAILABLE_FUNCTIONS

class RemediateAgent(BaseAgent):
    """
    Agent này thực hiện 2 nhiệm vụ:
    1. (Python) Dọn dẹp JSON thô (CHỈ LẤY FAIL).
    2. (AI) Đọc JSON đã dọn dẹp -> Đề xuất Kế hoạch sửa lỗi (JSON).
    3. (Code) Thực thi kế hoạch sửa lỗi đó.
    """
    
    # -------------------------------------------------------------------
    # HÀM 1A: (DỌN DẸP DỮ LIỆU) - ĐÃ SỬA LỖI
    # -------------------------------------------------------------------
    
    def _simplify_findings(self, structured_report_data: list) -> list:
        """
        Hàm này dùng Python để 'dọn dẹp' JSON OCSF thô
        thành một danh sách đơn giản (CHỈ LẤY STATUS 'FAIL') 
        mà AI có thể hiểu được.
        """
        print(f"[RemediateAgent] ℹ️ Đang dọn dẹp dữ liệu thô...")
        simplified_findings = []
        
        try:
            for job_result in structured_report_data:
                if job_result.get("status") != "completed" or not job_result.get("result", {}).get("data"):
                    continue
                
                for finding in job_result["result"]["data"]:
                    
                    # Bộ lọc CHỈ LẤY LỖI 'FAIL'
                    if finding.get("status_code") != "FAIL":
                        continue 
                    
                    # --- (SỬA LỖI LOGIC: Lấy 'uid' từ 'finding_info') ---
                    finding_id = finding.get('finding_info', {}).get('uid')
                    # --- (HẾT SỬA LỖI) ---

                    message = finding.get('message')
                    status_detail = finding.get('status_detail')
                    
                    resource_name = None
                    resources_list = finding.get("resources")
                    if resources_list and isinstance(resources_list, list) and len(resources_list) > 0:
                        resource_name = resources_list[0].get("name")
                        
                    if finding_id and message and resource_name:
                        simplified_findings.append({
                            "finding_id": finding_id,
                            "message": message,
                            "resource_name": resource_name,
                            "status_detail": status_detail
                        })
                    else:
                        # Log nếu thiếu thông tin
                        print(f"[RemediateAgent] ⚠️ Bỏ qua finding (thiếu info): finding_id={finding_id}, resource_name={resource_name}")
            
            print(f"[RemediateAgent] ℹ️ Đã dọn dẹp xong. Tìm thấy {len(simplified_findings)} finding 'FAIL' hợp lệ.")
            return simplified_findings
            
        except Exception as e:
            print(f"[RemediateAgent] ❌ Lỗi khi dọn dẹp JSON: {e}")
            return []

    # -------------------------------------------------------------------
    # HÀM 1B: DÙNG AI ĐỂ LẬP KẾ HOẠCH SỬA LỖI (ANALYZE/PLAN)
    # (Giữ nguyên)
    # -------------------------------------------------------------------
    
    SYSTEM_PROMPT_RECOMMEND = """
    Bạn là một chuyên gia An ninh mạng AWS (Cybersecurity Expert).
    Nhiệm vụ của bạn là đọc một DANH SÁCH FINDING ĐƠN GIẢN (chỉ chứa lỗi FAIL)
    và tạo ra một "Kế hoạch Sửa lỗi" (Remediation Plan) dưới dạng JSON.

    QUAN TRỌNG: Chỉ trả về một DANH SÁCH JSON (list) các hành động.
    Định dạng:
    [
      {
        "finding_id": "<ID của finding>",
        "remediation_comment": "<Mô tả lỗi VÀ chi tiết từ status_detail>",
        "tool_to_call": "<Tên tool chính xác, ví dụ 'remediate_s3_public_access'>",
        "tool_parameters": { ... }
      }
    ]
    
    DỮ LIỆU BẠN NHẬN ĐƯỢC CÓ DẠNG (đã lọc FAIL):
    [
      {
        "finding_id": "prowler-aws-s3_bucket_public_read_access-...",
        "message": "S3 Bucket prowler-test-public-bucket has public read access.",
        "resource_name": "prowler-test-public-bucket",
        "status_detail": "S3 Bucket prowler-test-public-bucket has public read access due to bucket ACL."
      }
    ]

    Hãy dùng 'resource_name' để điền vào 'tool_parameters' (ví dụ 'bucket_name').
    Chỉ trả lời bằng JSON.
    """
    
    def _extract_json_from_text(self, text: str) -> str:
        # (Hàm này giữ nguyên)
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            print("[RemediateAgent] ℹ️ (Đã trích xuất JSON từ khối ```json)")
            return match.group(1)
        match = re.search(r"(\[[\s\S]*\])", text) 
        if match:
            print("[RemediateAgent] ℹ️ (Đã trích xuất JSON từ khối [ ... ])")
            return match.group(1)
        print("[RemediateAgent] ⚠️ (Không tìm thấy khối JSON, trả về text thô)")
        return text

    def recommend_fixes(self, structured_report_data: list) -> str:
        """
        Dùng AI (Ollama) để phân tích JSON ĐÃ DỌN DẸP và trả về 
        một KẾ HOẠCH (dưới dạng JSON string).
        """
        print(f"--------------------------------------------------")
        print(f"[RemediateAgent] 🤖 Bắt đầu quy trình Đề xuất Sửa lỗi...")

        # BƯỚC 1: DỌN DẸP (Giờ sẽ lọc FAIL và lấy đúng resource_name)
        simplified_findings = self._simplify_findings(structured_report_data)

        if not simplified_findings:
            print("[RemediateAgent] ℹ️ Không có finding 'FAIL' nào cần sửa.")
            return "[]"

        # BƯỚC 2: GỌI AI
        print(f"[RemediateAgent] 🤖 Đang dùng AI để phân tích {len(simplified_findings)} finding 'FAIL' (đã dọn dẹp)...")
        
        summary_prompt = f"""
        Đây là danh sách các finding 'FAIL' đã được đơn giản hóa. Hãy tạo kế hoạch sửa lỗi:
        {json.dumps(simplified_findings, indent=2, ensure_ascii=False)}
        """
        
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT_RECOMMEND},
            {"role": "user", "content": summary_prompt}
        ]
        
        response_message = self.call_llm(messages) 
        
        if response_message and response_message.content:
            print(f"[RemediateAgent] 🤖 AI đã trả về (thô): {response_message.content}")
            cleaned_json_string = self._extract_json_from_text(response_message.content)
            return cleaned_json_string
        else:
            print("[RemediateAgent] ❌ Lỗi: AI không trả về kế hoạch.")
            return "[]" 

    # -------------------------------------------------------------------
    # HÀM 2: DÙNG CODE ĐỂ THỰC THI SỬA LỖI (REMEDIATE)
    # (Giữ nguyên)
    # -------------------------------------------------------------------
    
    def execute_fixes(self, remediation_plan: list) -> list:
        # (Toàn bộ code của hàm này giữ nguyên)
        print(f"--------------------------------------------------")
        print(f"[RemediateAgent] ⚙️ Bắt đầu thực thi {len(remediation_plan)} tác vụ sửa lỗi...")
        execution_results = []
        for task in remediation_plan:
            tool_name = task.get("tool_to_call")
            params = task.get("tool_parameters", {})
            function_to_call = AVAILABLE_FUNCTIONS.get(tool_name)
            if function_to_call:
                print(f"\n   -> Đang chạy tác vụ: {tool_name}(**{params})")
                try:
                    result_str = function_to_call(**params)
                    result_json = json.loads(result_str)
                    execution_results.append(result_json)
                except Exception as e:
                    print(f"   -> ❌ Lỗi khi thực thi tool: {e}")
                    execution_results.append({"status": "failed", "tool": tool_name, "error": str(e)})
            else:
                print(f"   -> ⚠️ Bỏ qua: Không tìm thấy tool '{tool_name}'")
                execution_results.append({"status": "skipped", "tool": tool_name})
        print(f"\n[RemediateAgent] ✅ Đã thực thi xong.")
        return execution_results