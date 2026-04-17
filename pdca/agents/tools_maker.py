# agents/tool_maker_agent.py
import json
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

class ToolMakerAgent:
    def __init__(self, model_name, base_url):
        self.llm = ChatOllama(model=model_name, base_url=base_url, temperature=0)
        
    def create_tool_code(self, finding_desc, sdk_docs):
        prompt = f"""
Bạn là chuyên gia lập trình AWS Boto3. Hãy viết một hàm Python (Tool) để sửa lỗi sau:
LỖI: {finding_desc}

DỰA TRÊN TÀI LIỆU SDK:
{sdk_docs}

YÊU CẦU:
1. Sử dụng decorator @tool từ langchain_core.tools.
2. Hàm phải nhận vào (resource_id: str, region: str = "us-east-1").
3. Trả về một Dictionary: {{"success": bool, "message": str}}.
4. CHỈ TRẢ VỀ CODE, không giải thích.

MẪU:
@tool
def auto_fix_example(resource_id: str, region: str = "us-east-1"):
    import boto3
    client = boto3.client("s3", region_name=region)
    # logic...
    return {{"success": True, "message": "done"}}
"""
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return response.content