import json
import re
import time
import chromadb
from typing import List, Dict, Any
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import BaseCallbackHandler
from .base_agent import BaseAgent

try:
    from agent_tools import ALLOWED_GROUPS_LIST
except ImportError:
    from ..agent_tools import ALLOWED_GROUPS_LIST

# ===============================================
# 1. TIMER CALLBACK (Để đo hiệu năng cho Orchestrator)
# ===============================================
class TimerCallback(BaseCallbackHandler):
    def __init__(self):
        self.total_duration = 0.0
        self.call_history = []
        self.start_time = 0.0

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> Any:
        self.start_time = time.perf_counter()

    def on_llm_end(self, response: Any, **kwargs: Any) -> Any:
        duration = time.perf_counter() - self.start_time
        self.total_duration += duration
        self.call_history.append(duration)

# ===============================================
# 2. SYSTEM PROMPTS (Đã tối ưu cho RAG)
# ===============================================
TRANSLATION_PROMPT = """Bạn là chuyên gia bảo mật AWS. Hãy chuyển đổi yêu cầu sau đây sang các từ khóa tiếng Anh kỹ thuật và xác định service mục tiêu.

USER REQUEST: "{request}"

QUY TẮC:
1. target_service: Phải là tên service (vd: s3, iam, ec2, rds...).
2. search_queries: Danh sách các thuật ngữ kỹ thuật (vd: "KMS encryption", "Public access").

JSON OUTPUT: {{"target_service": "string", "search_queries": ["string"]}}
"""

RERANK_PROMPT = """Bạn là AWS Security Planner. Hãy chọn ra tối đa 5 mã kiểm tra (Check ID) phù hợp nhất.

YÊU CẦU NGƯỜI DÙNG: "{request}"
DỊCH VỤ MỤC TIÊU: "{target_service}"

DANH SÁCH ỨNG VIÊN TỪ DATABASE:
{candidates}

QUY TẮC CHỌN:
1. CHỈ chọn các ID thuộc về dịch vụ "{target_service}".
2. Ưu tiên các ID giải quyết trực tiếp vấn đề người dùng hỏi.
3. Nếu ứng viên không liên quan, hãy bỏ qua (trả về list rỗng).

JSON OUTPUT: {{"selected_ids": ["id1", "id2"]}}
"""

# ===============================================
# 3. PLANNING AGENT CLASS
# ===============================================
class PlanningAgent(BaseAgent):
    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)
        
        self.timer = TimerCallback()

        # 1. Khởi tạo LLM kèm Callback
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            format="json",
            callbacks=[self.timer]
        )

        # 2. Cấu hình RAG
        self.embeddings = OllamaEmbeddings(model="nomic-embed-text")
        self.chroma_client = chromadb.PersistentClient(path="./prowler_vector_kb")
        self.collection = self.chroma_client.get_collection(name="prowler_checks_v2")

    def get_llm_metrics(self) -> Dict[str, Any]:
        """Trả về dữ liệu hiệu năng cho Orchestrator"""
        return {
            "total_latency": round(self.timer.total_duration, 4),
            "call_history": [round(t, 4) for t in self.timer.call_history],
            "call_count": len(self.timer.call_history),
        }

    def _get_vector_candidates(self, queries: List[str], target_svc: str = None) -> List[Dict]:
        """Tìm kiếm ứng viên có sử dụng Metadata Filter để ép đúng Service"""
        all_candidates = []
        unique_ids = set()
        
        # Metadata Filtering: Chỉ tìm trong service được chỉ định
        search_filter = None
        if target_svc and target_svc != "null":
            search_filter = {"service": target_svc} 

        for q in queries:
            results = self.collection.query(
                query_embeddings=[self.embeddings.embed_query(q)],
                n_results=15, 
                where=search_filter # <--- QUAN TRỌNG: Loại bỏ nhiễu từ service khác
            )
            
            for i in range(len(results['ids'][0])):
                c_id = results['ids'][0][i]
                if c_id not in unique_ids:
                    unique_ids.add(c_id)
                    all_candidates.append({
                        "id": c_id, 
                        "description": results['documents'][0][i]
                    })
        return all_candidates

    def _clean_json(self, text: str) -> Dict:
        try:
            return json.loads(text)
        except:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            return json.loads(match.group(0)) if match else {}

    def run(self, user_request: str) -> Dict[str, Any]:
        print(f"   [PlanningAgent] 🧠 Bắt đầu phân tích: '{user_request}'")
        try:
            # Bước 1: Dịch intent sang English keywords và Target Service
            t_prompt = ChatPromptTemplate.from_template(TRANSLATION_PROMPT)
            raw_translation = (t_prompt | self.llm | StrOutputParser()).invoke({"request": user_request})
            translation_data = self._clean_json(raw_translation)
            
            search_queries = translation_data.get("search_queries", [])
            target_svc = translation_data.get("target_service", "").lower()

            # Kiểm tra Group Scan (Quét toàn bộ service)
            if any(word in user_request.lower() for word in ["tất cả", "toàn bộ", "full scan"]):
                if target_svc in ALLOWED_GROUPS_LIST:
                    return {
                        "groups_to_scan": [target_svc], 
                        "checks_to_scan": [], 
                        "reasoning": f"Yêu cầu quét toàn bộ dịch vụ {target_svc}."
                    }

            # Bước 2: RAG Recall (Có Filter Service)
            print(f"   [PlanningAgent] 🔍 Tìm kiếm trong service: {target_svc}")
            candidates = self._get_vector_candidates(search_queries, target_svc=target_svc)
            
            if not candidates:
                return {
                    "groups_to_scan": [target_svc] if target_svc in ALLOWED_GROUPS_LIST else ["s3"], 
                    "checks_to_scan": [], 
                    "reasoning": "Không tìm thấy check cụ thể, fallback về quét toàn bộ service."
                }

            # Bước 3: LLM Re-ranking (Chốt danh sách cuối cùng)
            r_prompt = ChatPromptTemplate.from_template(RERANK_PROMPT)
            raw_final = (r_prompt | self.llm | StrOutputParser()).invoke({
                "request": user_request,
                "target_service": target_svc,
                "candidates": json.dumps(candidates, indent=2)
            })
            final_data = self._clean_json(raw_final)
            selected_ids = final_data.get("selected_ids", [])

            return {
                "groups_to_scan": [],
                "checks_to_scan": selected_ids if selected_ids else [c['id'] for c in candidates[:2]],
                "reasoning": f"Đã lọc {len(candidates)} ứng viên và chọn {len(selected_ids)} check liên quan nhất đến {target_svc}."
            }
        except Exception as e:
            return {"groups_to_scan": ["s3"], "checks_to_scan": [], "reasoning": f"Lỗi hệ thống: {e}"}