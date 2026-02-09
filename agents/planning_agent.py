import json
import requests
import re
from typing import List, Dict, Any
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from .base_agent import BaseAgent

# Prompt dịch thuật kỹ thuật (English-centric)
TRANSLATION_PROMPT = """You are an AWS Security Expert. Translate the user request into technical English keywords.
USER REQUEST: "{request}"
FORMAT: {{"target_service": "s3", "search_queries": ["public access", "encryption"]}}
JSON OUTPUT:"""

# Prompt Re-ranking sử dụng dữ liệu đã làm giàu (Enrichment)
RERANK_PROMPT = """Analyze these AWS Security Checks for the request: "{request}"
CANDIDATES (Enriched):
{candidates}

Select the top 5 most relevant Check IDs. Prioritize 'critical' or 'high' severity.
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
            # --- BƯỚC 1: TRANSLATION (Chuyển sang Tiếng Anh kỹ thuật) ---
            t_prompt = ChatPromptTemplate.from_template(TRANSLATION_PROMPT)
            raw_t = (t_prompt | self.llm | StrOutputParser()).invoke({"request": user_request})
            t_data = self._clean_json(raw_t)
            
            eng_query = t_data.get("search_queries", [user_request])[0]
            target_svc = t_data.get("target_service", "s3")
            print(f"   [PlanningAgent] 🌐 Dịch: -> '{eng_query}' (Service: {target_svc})")

            # --- BƯỚC 2: GỌI RETRIEVAL VỚI TIẾNG ANH ---
            enriched_candidates = self._call_retrieval_service(eng_query)
            print(f"   [DEBUG Retrieval] Tìm thấy {len(enriched_candidates)} ứng viên từ DB.")
            for c in enriched_candidates:
                print(f"      -> ID: {c['id']} | Severity: {c['metadata'].get('severity')}")

            if not enriched_candidates:
                return {
                    "groups_to_scan": [target_svc], 
                    "checks_to_scan": [], 
                    "reasoning": f"Không tìm thấy check cụ thể cho '{eng_query}', thực hiện quét toàn bộ service {target_svc}."
                }

            # --- BƯỚC 3: RE-RANKING (Dựa trên Metadata rủi ro) ---
            r_prompt = ChatPromptTemplate.from_template(RERANK_PROMPT)
            raw_final = (r_prompt | self.llm | StrOutputParser()).invoke({
                "request": user_request,
                "candidates": json.dumps(enriched_candidates, indent=2)
            })
            
            final_data = self._clean_json(raw_final)
            return {
                "groups_to_scan": [],
                "checks_to_scan": final_data.get("selected_ids", []),
                "reasoning": final_data.get("reasoning", "Đã chọn các check phù hợp dựa trên rủi ro.")
            }

        except Exception as e:
            return {"error": str(e), "groups_to_scan": ["s3"], "checks_to_scan": []}