import openai
import os

class BaseAgent:
    """Lớp cơ sở cho tất cả các Agent, xử lý việc khởi tạo client."""
    def __init__(self, model_name: str, api_key: str, base_url: str):
        if not api_key:
            api_key = "ollama" # Giá trị giả, client 'openai' yêu cầu
        
        self.model_name = model_name
        self.client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key,
        )
    
    def call_llm(self, messages, tools=None, tool_choice="auto"):
        """Hàm helper để gọi LLM."""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice
            )
            return response.choices[0].message
        except Exception as e:
            print(f"[LỖI] Không thể gọi LLM ({self.model_name} tại {self.client.base_url}).")
            print(f"   -> Lỗi: {e}")
            print(f"   -> Gợi ý: Đảm bảo Ollama đang chạy và model '{self.model_name}' đã được pull.")
            return None
