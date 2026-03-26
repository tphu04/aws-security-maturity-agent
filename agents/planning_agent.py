import json
import requests
import re
import logging
from typing import List, Dict, Any
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# --- PROMPT DEFINITIONS ---
TRANSLATION_PROMPT = """You are an AWS Security Expert. 
Analyze the user request and determine the target AWS Service and scan type.

USER REQUEST: "{request}"

JSON OUTPUT FORMAT:
{{
  "target_service": "short_service_code",
  "is_group_scan": true/false,
  "search_queries": ["specific technical terms"]
}}

EXAMPLES:
- "check s3 group": {{"target_service": "s3", "is_group_scan": true, "search_queries": []}}
- "scan all iam": {{"target_service": "iam", "is_group_scan": true, "search_queries": []}}
- "check public buckets": {{"target_service": "s3", "is_group_scan": false, "search_queries": ["public access"]}}

IMPORTANT: Return ONLY raw JSON. No conversational filler."""

RERANK_PROMPT = """Analyze these AWS Security Checks for the request: "{request}"
CANDIDATES (Enriched):
{candidates}

Select the top 5 most relevant Prowler Check IDs. 
JSON OUTPUT: {{"selected_ids": ["check_id_1", "check_id_2"], "reasoning": "short explanation"}}"""


# --- AGENT CLASS ---

class PlanningAgent:
    def __init__(self, model_name: str, api_key: str = None, base_url: str = "http://localhost:11434"):
        self.retrieval_api_url = "http://localhost:8111/retrieve"
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            format="json"
        )
        # Danh sách service AWS phổ biến để lọc text thừa
        self.valid_services = ['s3', 'iam', 'ec2', 'rds', 'vpc', 'lambda', 'cloudtrail', 'kms', 'eks', 'sns']

    def _clean_json(self, text: str) -> Dict:
        """Trích xuất JSON từ chuỗi text, loại bỏ các ký tự thừa bên ngoài dấu { }"""
        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                json_str = match.group(0)
                # Loại bỏ các ký tự điều khiển (control characters) không hợp lệ
                json_str = re.sub(r'[\x00-\x1F\x7F]', '', json_str)
                return json.loads(json_str)
            return json.loads(text)
        except Exception as e:
            print(f"   [PlanningAgent] ⚠️ JSON Parse Error: {e}")
            return {}

    def _sanitize_service_name(self, raw_svc: str) -> str:
        """Lọc bỏ mọi text thừa, chỉ lấy mã service AWS hợp lệ"""
        if not raw_svc: 
            return "s3"
        
        # Chuyển về chữ thường và tìm trong whitelist
        clean_text = str(raw_svc).lower().strip()
        
        for svc in self.valid_services:
            if svc in clean_text:
                return svc
        
        # Nếu không có trong whitelist, dùng regex lấy từ đầu tiên có độ dài 2-10 ký tự
        match = re.search(r'[a-z0-9]{2,10}', clean_text)
        return match.group(0) if match else "s3"

    def _sanitize_id(self, raw_id: str) -> str:
            """Loại bỏ các hậu tố và tiền tố tài liệu để trả về Prowler Check ID chuẩn"""
            clean_id = str(raw_id).strip()
            
            # 1. Cắt bỏ tiền tố "check:" hoặc "capability:" do RAG API sinh ra
            if clean_id.startswith("check:"):
                clean_id = clean_id[6:]  # Bỏ 6 ký tự đầu ("check:")
            elif clean_id.startswith("capability:"):
                clean_id = clean_id[11:] # Bỏ 11 ký tự đầu ("capability:")
                
            # 2. Cắt bỏ các hậu tố rác (nếu có)
            suffixes = ["_overview", "_risk", "_recommendation", "_remediation"]
            for suffix in suffixes:
                if clean_id.endswith(suffix):
                    clean_id = clean_id.replace(suffix, "")
                    
            return clean_id
    def _call_retrieval_service(self, query: str, target_svc: str) -> List[str]:
            """Gọi API RAG và chỉ lấy check của đúng Service"""
            url = "http://localhost:8001/v1/retrieve/checks"
            
            # CÁCH 1: Nhồi thêm tên service vào query để Vector DB tìm chính xác hơn
            enhanced_query = f"{target_svc} {query}"
            
            payload = {
                "query": enhanced_query,
                "top_k": 10, # Tăng top_k lên xíu để có vùng chọn rộng hơn
                "retrieval_mode": "hybrid",
                "debug": True
            }
            
            try:
                response = requests.post(url, json=payload, timeout=15)
                response.raise_for_status()
                data = response.json()
                
                results = data.get("data", {}).get("results", [])
                ids: List[str] = []
                
                for item in results:
                    # CÁCH 2: Lọc cứng (Hard filter) - Chỉ lấy những check thuộc đúng service
                    item_svc = item.get("metadata", {}).get("service", "").lower()
                    if target_svc and item_svc and target_svc != item_svc:
                        continue # Nếu check là của ec2 mà target là s3 thì bỏ qua luôn
                    
                    doc_id = item.get("doc_id")
                    if doc_id:
                        ids.append(doc_id)
                        continue
                    
                    if item.get("check_id"):
                        ids.append(item["check_id"])
                    elif item.get("capability_id"):
                        ids.append(item["capability_id"])
                        
                clean_ids = []
                for i in ids:
                    sanitized = self._sanitize_id(i)
                    if sanitized and sanitized != "<unknown>":
                        clean_ids.append(sanitized)
                        
                # Trả về tối đa 5 checks sau khi đã lọc sạch sẽ
                return list(set(clean_ids))[:5]
                
            except Exception as e:
                print(f"   [PlanningAgent] ⚠️ Lỗi RAG: {e}")
                return []
    def run(self, user_request: str) -> Dict[str, Any]:
            print(f"   [PlanningAgent] 🧠 Phân tích yêu cầu: '{user_request}'")
            try:
                # --- BƯỚC 0: FAST TRACK (PHÁT HIỆN CHECK ID TRỰC TIẾP) ---
                # Tìm các chuỗi giống định dạng Prowler Check (chứa dấu '_', chữ thường/số)
                # Ví dụ: s3_bucket_kms_encryption
                explicit_checks = re.findall(r'\b[a-z0-9]+_[a-z0-9_]+\b', user_request.lower())
                
                # Lọc sơ bộ: Check ID thường dài hơn 8 ký tự để tránh bắt nhầm các từ viết tắt
                valid_explicit_checks = [c for c in explicit_checks if len(c) > 8]
                
                if valid_explicit_checks:
                    clean_explicit_checks = list(set([self._sanitize_id(c) for c in valid_explicit_checks]))
                    print(f"   [PlanningAgent] ⚡ FAST TRACK: Phát hiện người dùng nhập trực tiếp {len(clean_explicit_checks)} Check IDs. Bỏ qua LLM & RAG!")
                    return {
                        "groups_to_scan": [],
                        "checks_to_scan": clean_explicit_checks,
                        "reasoning": f"User explicitly provided check IDs in the prompt."
                    }

                # --- BƯỚC 1: NHẬN DIỆN Ý ĐỊNH (Nếu Bước 0 không tìm thấy) ---
                t_prompt = ChatPromptTemplate.from_template(TRANSLATION_PROMPT)
                raw_t = (t_prompt | self.llm | StrOutputParser()).invoke({"request": user_request})
                t_data = self._clean_json(raw_t)
                
                target_svc = self._sanitize_service_name(t_data.get("target_service", "s3"))
                is_group_scan = t_data.get("is_group_scan", False)

                # --- LUỒNG 1: QUÉT TOÀN BỘ SERVICE (GROUP SCAN) ---
                if is_group_scan:
                    print(f"   [PlanningAgent] 🌐 Phát hiện yêu cầu quét toàn bộ dịch vụ: {target_svc}")
                    return {
                        "groups_to_scan": [target_svc],
                        "checks_to_scan": [],
                        "reasoning": f"User requested a full general scan for {target_svc}."
                    }

                # --- LUỒNG 2: GỌI API RAG (Bắt buộc) ---
                print(f"   [PlanningAgent] 🔍 Đang gọi API RAG (Hybrid mode) cho '{target_svc}'...")
                
                search_queries = t_data.get("search_queries", [])
                if isinstance(search_queries, list) and len(search_queries) > 0:
                    search_query = search_queries[0]
                else:
                    search_query = user_request
                    
                print(f"   [PlanningAgent] ➡️ Payload Query gửi đi: '{search_query}' cho service '{target_svc}'")
                rag_candidates = self._call_retrieval_service(search_query, target_svc)

                # --- BƯỚC 3: LLM RE-RANKING (Đánh giá CoT) ---
                if rag_candidates:
                    print(f"   [PlanningAgent] 🧠 Đang đánh giá độc lập {len(rag_candidates)} ứng viên...")
                    r_prompt = ChatPromptTemplate.from_template(RERANK_PROMPT)
                    raw_final = (r_prompt | self.llm | StrOutputParser()).invoke({
                        "request": user_request,
                        "candidates": json.dumps(rag_candidates, indent=2, ensure_ascii=False)
                    })
                    
                    final_data = self._clean_json(raw_final)
                    evaluations = final_data.get("evaluations", [])
                    
                    for eval_item in evaluations:
                        status = "✅" if eval_item.get("decision") == "KEEP" else "❌"
                        print(f"      {status} {eval_item.get('check_id')}: {eval_item.get('reasoning')}")
                    
                    selected_ids = final_data.get("selected_ids", [])
                    clean_checks = list(set([self._sanitize_id(idx) for idx in selected_ids]))
                    
                    print(f"   [PlanningAgent] ✅ LLM đã chốt {len(clean_checks)} checks chuẩn nhất.")
                    return {
                        "groups_to_scan": [],
                        "checks_to_scan": clean_checks,
                        "reasoning": "Evaluated via Chain of Thought Re-ranking."
                    }
                else:
                    print(f"   [PlanningAgent] ⚠️ RAG không trả về check nào. Fallback sang Group Scan.")
                    return {
                        "groups_to_scan": [target_svc],
                        "checks_to_scan": [],
                        "reasoning": "RAG returned no results, performing full group scan."
                    }

            except Exception as e:
                print(f"   [PlanningAgent] ❌ Lỗi nghiêm trọng: {e}")
                return {"groups_to_scan": ["s3"], "checks_to_scan": [], "error": str(e)}