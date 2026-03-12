import json
import requests
import re
from typing import List, Dict, Any
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from .base_agent import BaseAgent

# Prompt dịch thuật kỹ thuật (English-centric)
TRANSLATION_PROMPT = """You are an AWS Security Expert. 
Classify the request into the correct AWS Service (iam, s3, ec2, rds, cloudtrail, etc.) and translate to technical keywords.

USER REQUEST: "{request}"

EXAMPLES:
- "check mfa": {{"target_service": "iam", "search_queries": ["mfa enabled", "console access"]}}
- "public buckets": {{"target_service": "s3", "search_queries": ["public access", "bucket policy"]}}

JSON OUTPUT:"""

# Prompt Re-ranking sử dụng dữ liệu đã làm giàu (Enrichment)
RERANK_PROMPT = """Analyze these AWS Security Checks for the request: "{request}"
CANDIDATES (Enriched):
{candidates}

Select the top 5 most relevant Check IDs. 
IMPORTANT: Return the clean Prowler Check ID (e.g., instead of 'check_id_risk', return 'check_id').
Prioritize 'critical' or 'high' severity.
JSON OUTPUT: {{"selected_ids": ["id1", "id2"], "reasoning": "explanation"}}"""
class PlanningAgent(BaseAgent):
    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)
        self.retrieval_api_url = "http://localhost:8111/retrieve"
        
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            format="json"
        )
    def _sanitize_id(self, raw_id: str) -> str:
            """Loại bỏ các hậu tố tài liệu để trả về Prowler Check ID chuẩn"""
            # Danh sách các hậu tố cần loại bỏ
            suffixes = ["_overview", "_risk", "_recommendation", "_remediation"]
            clean_id = raw_id
            for suffix in suffixes:
                if clean_id.endswith(suffix):
                    clean_id = clean_id.replace(suffix, "")
            return clean_id.strip()
    def _clean_json(self, text: str) -> Dict:
        try:
            return json.loads(text)
        except:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            return json.loads(match.group(0)) if match else {}

    def _call_retrieval_service(self, query: str, target_service: str = None) -> List[Dict]:
        try:
            payload = {
                "query": query,
                "mode": "technical",
                "top_k": 5,
                "service": target_service # <--- TRUYỀN THÊM DÒNG NÀY
            }
            response = requests.post(self.retrieval_api_url, json=payload, timeout=10)
            return response.json().get("technical", [])
        except Exception as e:
            return []

    def run(self, user_request: str) -> Dict[str, Any]:
            print(f"   [PlanningAgent] 🧠 Phân tích: '{user_request}'")
            try:
                # --- BƯỚC 1: TRANSLATION (Giữ nguyên như bạn đã sửa) ---
                t_prompt = ChatPromptTemplate.from_template(TRANSLATION_PROMPT)
                raw_t = (t_prompt | self.llm | StrOutputParser()).invoke({"request": user_request})
                t_data = self._clean_json(raw_t)
                
                eng_query = t_data.get("search_queries", [user_request])[0]
                target_svc = t_data.get("target_service", None) 
                print(f"   [PlanningAgent] 🌐 Dịch: -> '{eng_query}' (Service: {target_svc})")

                # --- BƯỚC 2: GỌI RETRIEVAL ---
                enriched_candidates = self._call_retrieval_service(eng_query, target_svc)
                
                # Mẹo: Làm sạch ID ngay tại log debug để bạn dễ theo dõi
                print(f"   [DEBUG Retrieval] Tìm thấy {len(enriched_candidates)} ứng viên.")
                for c in enriched_candidates:
                    clean_c_id = self._sanitize_id(c['id'])
                    print(f"      -> ID: {clean_c_id} (Gốc: {c['id']}) | Severity: {c['metadata'].get('severity')}")

                if not enriched_candidates:
                    return {"groups_to_scan": [target_svc], "checks_to_scan": [], "reasoning": "..."}

                # --- BƯỚC 3: RE-RANKING ---
                r_prompt = ChatPromptTemplate.from_template(RERANK_PROMPT)
                raw_final = (r_prompt | self.llm | StrOutputParser()).invoke({
                    "request": user_request,
                    "candidates": json.dumps(enriched_candidates, indent=2)
                })
                
                final_data = self._clean_json(raw_final)
                raw_selected_ids = final_data.get("selected_ids", [])
                
                # --- BƯỚC 4: FINAL CLEANING (QUAN TRỌNG NHẤT) ---
                # Đảm bảo mọi ID trong danh sách cuối đều không có hậu tố và không bị trùng
                clean_ids = list(set([self._sanitize_id(idx) for idx in raw_selected_ids]))
                
                return {
                    "groups_to_scan": [],
                    "checks_to_scan": clean_ids, # Trả về danh sách đã làm sạch
                    "reasoning": final_data.get("reasoning", "Đã chọn các check phù hợp.")
                }

            except Exception as e:
                return {"error": str(e), "groups_to_scan": ["s3"], "checks_to_scan": []}