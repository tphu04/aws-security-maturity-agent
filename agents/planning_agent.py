import json
import re 
from .base_agent import BaseAgent

class PlanningAgent(BaseAgent):
    """
    Agent này nhận yêu cầu từ người dùng và chỉ có một nhiệm vụ:
    Phân tích yêu cầu và trả về một "kế hoạch" (plan) dạng JSON.
    """
    
    SYSTEM_PROMPT = """
    Bạn là một agent lập kế hoạch (Planning Agent). 
    Nhiệm vụ của bạn là phân tích yêu cầu quét của người dùng và
    trả về một đối tượng JSON CHÍNH XÁC theo định dạng:
    {"groups_to_scan": ["group1", "group2", ...], "files_to_scan": ["file1.json", ...]}

    Ví dụ:
    - User: "quét s3 và iam"
    - Bạn trả về: {"groups_to_scan": ["s3", "iam"], "files_to_scan": []}

    Chỉ trả về JSON, không nói gì thêm.
    """
    
    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)
        self.tools_menu = None 
        self.available_tools = {}

    def _extract_json_from_text(self, text: str) -> str:
        """Helper function to extract JSON from messy AI text."""
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            print("[PlanningAgent] ℹ️ (Đã trích xuất JSON từ khối ```json)")
            return match.group(1)
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            print("[PlanningAgent] ℹ️ (Đã trích xuất JSON từ khối { ... })")
            return match.group(1)
        print("[PlanningAgent] ⚠️ (Không tìm thấy khối JSON, trả về text thô)")
        return text

    def run(self, user_prompt: str) -> dict:
        """
        Chạy agent và trả về một dictionary kế hoạch.
        """
        print(f"--------------------------------------------------")
        print(f"[PlanningAgent] 🤖 Đang phân tích yêu cầu: '{user_prompt}'")
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        
        response_message = self.call_llm(messages) 
        
        if not response_message or not response_message.content:
            print("[PlanningAgent] ❌ AI không trả về kế hoạch.")
            return {"groups_to_scan": [], "files_to_scan": []}

        print(f"[PlanningAgent] 🤖 AI trả về kế hoạch (thô): {response_message.content}")
        
        cleaned_json_string = self._extract_json_from_text(response_message.content)
        
        try:
            plan_raw = json.loads(cleaned_json_string) 
            
            # --- (MỚI) TỰ SỬA LỖI KEY (CẢI TIẾN) ---
            plan_fixed = {
                "groups_to_scan": [],
                "files_to_scan": []
            }

            # Tìm key chuẩn HOẶC key lỗi và chuyển dữ liệu sang
            if "groups_to_scan" in plan_raw:
                plan_fixed["groups_to_scan"] = plan_raw["groups_to_scan"]
            elif "groups_toScan" in plan_raw: # <-- SỬA LỖI MỚI (camelCase)
                print("[PlanningAgent] ℹ️ (Đã tự sửa key 'groups_toScan')")
                plan_fixed["groups_to_scan"] = plan_raw["groups_toScan"]
            elif "groupsto(scan" in plan_raw: # <-- Sửa lỗi cũ
                print("[PlanningAgent] ℹ️ (Đã tự sửa key 'groupsto(scan')")
                plan_fixed["groups_to_scan"] = plan_raw["groupsto(scan"]
                
            if "files_to_scan" in plan_raw:
                plan_fixed["files_to_scan"] = plan_raw["files_to_scan"]
            elif "filesToScan" in plan_raw: # <-- SỬA LỖI MỚI (camelCase)
                print("[PlanningAgent] ℹ️ (Đã tự sửa key 'filesToScan')")
                plan_fixed["files_to_scan"] = plan_raw["filesToScan"]
            elif "filesto(scan" in plan_raw: # <-- Sửa lỗi cũ
                print("[PlanningAgent] ℹ️ (Đã tự sửa key 'filesto(scan')")
                plan_fixed["files_to_scan"] = plan_raw["filesto(scan"]

            return plan_fixed # Trả về plan đã được sửa
            # --- HẾT PHẦN SỬA LỖI ---

        except json.JSONDecodeError:
            print(f"[PlanningAgent] ❌ Lỗi: Kế hoạch trả về không phải JSON (ngay cả sau khi dọn dẹp). Output thô: {cleaned_json_string}")
            return {"groups_to_scan": [], "files_to_scan": []}