import json
from .base_agent import BaseAgent
from agent_tools import SCANNER_AGENT_TOOLS, AVAILABLE_FUNCTIONS # Dùng thực đơn tool mới

class ScannerAgent(BaseAgent):
    """
    Agent này nhận một nhiệm vụ cụ thể (ví dụ: "quét s3")
    và gọi MỘT tool duy nhất để thực hiện nó.
    Nó được thiết kế để chạy song song (trong các luồng).
    """
    
    SYSTEM_PROMPT = """
    Bạn là một agent quét (Scanner Agent). 
    Nhiệm vụ của bạn là ngay lập tức gọi công cụ (tool) được
    yêu cầu dựa trên prompt của người dùng.
    Chỉ gọi tool, không nói gì khác.
    """
    
    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)
        self.tools_menu = SCANNER_AGENT_TOOLS
        self.available_tools = AVAILABLE_FUNCTIONS

    def run_scan(self, scan_prompt: str) -> str:
        """
        Chạy một nhiệm vụ quét và trả về job_id (hoặc None nếu lỗi).
        """
        print(f"[ScannerAgent] ⚡️ Nhận nhiệm vụ: '{scan_prompt}'")
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": scan_prompt}
        ]
        
        response_message = self.call_llm(messages, tools=self.tools_menu)
        
        if not response_message or not response_message.tool_calls:
            print(f"[ScannerAgent] ❌ Lỗi: AI không gọi tool cho '{scan_prompt}'")
            return None

        # Agent này chỉ nên gọi 1 tool
        tool_call = response_message.tool_calls[0]
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)
        
        print(f"   -> Đang gọi hàm: {function_name}(**{function_args})")
        function_to_call = self.available_tools.get(function_name)
        
        if function_to_call:
            function_response_json = function_to_call(**function_args)
            print(f"   <- API trả về: {function_response_json[:200]}...")
            try:
                response_data = json.loads(function_response_json)
                if response_data.get("status") == "pending" and "job_id" in response_data:
                    job_id = response_data["job_id"]
                    print(f"   <- ✅ Tạo Job thành công: {job_id}")
                    return job_id
                else:
                    print(f"   <- ❌ Lỗi tạo job: {response_data.get('error')}")
                    return None
            except json.JSONDecodeError:
                print(f"   <- ❌ Lỗi: Phản hồi từ tool không phải JSON.")
                return None
        return None