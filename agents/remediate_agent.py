import json
import logging
from typing import List, Dict, Any, Optional

# Import BaseAgent
from .base_agent import BaseAgent

# Import LangChain Ollama và Message Types
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

# Import danh sách tool
from agent_tools import ALL_TOOLS 

class RemediateAgent(BaseAgent):
    """
    RemediateAgent (Fully Dynamic Version)
    --------------------------------------
    Dựa hoàn toàn vào khả năng hiểu của AI đối với tên và mô tả của Tool.
    """

    SYSTEM_PROMPT = """
    Bạn là chuyên gia khắc phục sự cố bảo mật AWS.
    Nhiệm vụ: Chọn ĐÚNG công cụ (Tool) để sửa lỗi dựa trên mô tả lỗi.

    DANH SÁCH CÔNG CỤ HIỆN CÓ VÀ CHỨC NĂNG:
    {tool_descriptions}

    QUY TẮC SUY LUẬN (BẮT BUỘC):
    1. So sánh kỹ "Tiêu đề lỗi" (Check Title) với "Chức năng" của từng tool.
    2. Tìm từ khóa khớp nhau (Ví dụ: Lỗi "Versioning" -> Phải tìm tool có chữ "versioning").
    3. Lỗi "Logging" -> Phải tìm tool có chữ "logging".
    4. Lỗi "Encryption" -> Phải tìm tool có chữ "encryption" hoặc "kms".
    5. Nếu lỗi là "Public Access" -> Mới được dùng tool "s3_public_access_block".
    
    Đừng đoán mò. Hãy chọn tool có ý nghĩa sát nhất với lỗi.
    """

    def __init__(self, model_name, api_key, base_url):
        super().__init__(model_name, api_key, base_url)
        
        print(f"[RemediateAgent] Init LangChain (Dynamic Mode) với model {model_name}...")
        
        self.lc_llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0, 
        )
        
        # Bind tools
        self.llm_with_tools = self.lc_llm.bind_tools(ALL_TOOLS)
        self.tools_map = {tool.name: tool for tool in ALL_TOOLS}
        
        # Tạo chuỗi mô tả tool động để nạp vào Prompt
        # Giúp AI hiểu rõ từng tool làm gì mà không cần Hardcode mapping
        self.tools_desc_str = "\n".join(
            [f"- {tool.name}: {tool.description}" for tool in ALL_TOOLS]
        )

    def recommend_fixes(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        print(f"[RemediateAgent] 🤖 Bắt đầu xử lý {len(findings)} findings (Dynamic Matching)...")
        
        for finding in findings:
            if finding.get("status") != "FAIL":
                continue
                
            finding_id = finding.get("finding_id")
            resource_id = finding.get("resource_id")
            region = finding.get("region", "us-east-1")
            
            # Lấy thông tin lỗi
            prowler_check_id = finding.get("prowler_check_id") or finding.get("issue_hint") or ""
            check_title = finding.get("check_title", "")
            description = finding.get("short_description") or finding.get("status_details", "")

            # Bỏ qua Account ID (logic bảo vệ cơ bản, không tính là hardcode tool)
            if resource_id and resource_id.isdigit() and len(resource_id) == 12:
                print(f"[RemediateAgent] ⏩ Bỏ qua Resource là AccountID: {resource_id}")
                continue

            if not resource_id or resource_id == "N/A":
                continue

            print(f"\n[RemediateAgent] 🧠 Đang suy luận tool cho: {prowler_check_id}...")
            
            # Format System Prompt với danh sách tool động
            formatted_system_prompt = self.SYSTEM_PROMPT.format(tool_descriptions=self.tools_desc_str)

            user_msg = f"""
            LỖI CẦN SỬA:
            - ID: {prowler_check_id}
            - Tiêu đề: {check_title}
            - Mô tả chi tiết: {description}
            
            TÀI NGUYÊN:
            - Resource ID: {resource_id}
            - Region: {region}
            
            Hãy suy nghĩ từng bước và GỌI tool phù hợp nhất trong danh sách trên.
            """
            
            try:
                # Gọi AI
                messages = [
                    SystemMessage(content=formatted_system_prompt),
                    HumanMessage(content=user_msg)
                ]
                
                response = self.llm_with_tools.invoke(messages)
                
                # Thực thi Tool
                if response.tool_calls:
                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        
                        print(f"   -> 🎯 AI Quyết định chọn: {tool_name}")
                        
                        target_tool = self.tools_map.get(tool_name)
                        if target_tool:
                            try:
                                tool_result = target_tool.invoke(tool_args)
                                print(f"   -> ✅ Kết quả: {tool_result}")
                                
                                results.append({
                                    "finding_id": finding_id,
                                    "resource_id": resource_id,
                                    "tool_used": tool_name,
                                    "status": "executed",
                                    "result": json.loads(tool_result) if isinstance(tool_result, str) else tool_result
                                })
                            except Exception as e:
                                print(f"   -> ❌ Lỗi chạy tool: {e}")
                                results.append({"finding_id": finding_id, "status": "failed", "error": str(e)})
                else:
                    print(f"   -> 🤷 AI không tìm thấy tool phù hợp.")
                    
            except Exception as e:
                print(f"[RemediateAgent] ❌ Lỗi: {e}")

        return results