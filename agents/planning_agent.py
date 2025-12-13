# planning_agent.py - PHIÊN BẢN FIX: SMART INTENT FILTERING (LỌC NHIỄU THÔNG MINH)
import json
import re
import difflib
from typing import List, Dict, Any
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from .base_agent import BaseAgent

try:
    from agent_tools import ALLOWED_GROUPS_LIST
except ImportError:
    from ..agent_tools import ALLOWED_GROUPS_LIST

# ===============================================
# 1. KNOWLEDGE BASE
# ===============================================
PROWLER_KNOWLEDGE_BASE = {
    "s3_access_point_public_access_block": "Block Public Access Settings enabled on Access Points.",
    "s3_account_level_public_access_blocks": "Check S3 Account Level Public Access Block.",
    "s3_bucket_acl_prohibited": "Check if S3 buckets have ACLs enabled.",
    "s3_bucket_cross_account_access": "Ensure that general-purpose bucket policies restrict access to other AWS accounts.",
    "s3_bucket_cross_region_replication": "Check if S3 buckets use cross region replication.",
    "s3_bucket_default_encryption": "Check if S3 buckets have default encryption (SSE) enabled or use a bucket policy to enforce it.",
    "s3_bucket_event_notifications_enabled": "Check if S3 buckets have event notifications enabled.",
    "s3_bucket_kms_encryption": "Check if S3 buckets have KMS encryption enabled.",
    "s3_bucket_level_public_access_block": "Check S3 Bucket Level Public Access Block.",
    "s3_bucket_lifecycle_enabled": "Check if S3 buckets have a Lifecycle configuration enabled.",
    "s3_bucket_no_mfa_delete": "Check if S3 bucket MFA Delete is not enabled.",
    "s3_bucket_object_lock": "Check if S3 buckets have object lock enabled.",
    "s3_bucket_object_versioning": "Check if S3 buckets have object versioning enabled.",
    "s3_bucket_policy_public_write_access": "Check if S3 buckets have policies which allow WRITE access.",
    "s3_bucket_public_access": "Ensure there are no S3 buckets open to Everyone or Any AWS user.",
    "s3_bucket_public_list_acl": "Ensure there are no S3 buckets listable by Everyone or Any AWS customer.",
    "s3_bucket_public_write_acl": "Ensure there are no S3 buckets writable by Everyone or Any AWS customer.",
    "s3_bucket_secure_transport_policy": "Check if S3 buckets have secure transport policy (SSL/HTTPS).",
    "s3_bucket_server_access_logging_enabled": "Check if S3 buckets have server access logging enabled.",
    "s3_bucket_shadow_resource_vulnerability": "Check for S3 buckets vulnerable to Shadow Resource Hijacking (Bucket Monopoly).",
    "s3_multi_region_access_point_public_access_block": "Block Public Access Settings enabled on Multi Region Access Points.",
}

# ===============================================
# 2. CONSTANTS: TỪ ĐIỂN TỪ VÔ NGHĨA (STOP WORDS)
# ===============================================
# Những từ này sẽ bị loại bỏ để xem user có ý định cụ thể nào khác không
COMMON_STOP_WORDS = [
    # Hành động
    "scan",
    "check",
    "quét",
    "kiểm",
    "tra",
    "xem",
    "verify",
    "audit",
    "assess",
    # Số lượng / Phạm vi
    "all",
    "tất",
    "cả",
    "full",
    "toàn",
    "bộ",
    "mọi",
    "hết",
    "các",
    "những",
    "cái",
    # Đối tượng chung
    "group",
    "nhóm",
    "dịch",
    "vụ",
    "service",
    "services",
    "aws",
    "cloud",
    # Liên từ / Giới từ
    "liên",
    "quan",
    "tới",
    "đến",
    "về",
    "related",
    "to",
    "in",
    "on",
    "for",
    "of",
    "with",
    "cho",
    "tôi",
    "dùm",
    "hộ",
    "là",
    "bị",
    "có",
    "have",
    "has",
    "the",
]

# ===============================================
# 3. PROMPT
# ===============================================
SEMANTIC_PLANNING_PROMPT = """Bạn là trợ lý dịch thuật kỹ thuật AWS Security.

USER REQUEST: "{request}"

NHIỆM VỤ:
1. **SỬA CHÍNH TẢ** (VD: "encrpytion" -> "encryption").
2. **TÁCH QUERY**: Tách danh sách nếu có "và", ",", "với".
3. **DỊCH SÁT NGHĨA**:
   - Dịch từ khóa kỹ thuật sang tiếng Anh (encryption, public, mfa...).
   - BỎ các từ thừa (liên quan, tới, tất cả, all, dịch vụ).
   - Luôn kèm tên service (s3, ec2).

Ví dụ:
- Input: "tất cả s3 liên quan tới mã hóa"
  -> Output: {{"search_queries": ["s3 encryption"]}}

- Input: "check các dịch vụ s3 public"
  -> Output: {{"search_queries": ["s3 public"]}}

OUTPUT JSON:
{{
    "is_group_scan": boolean,
    "target_service": "string" | null,
    "search_queries": ["string"]
}}
"""


class PlanningAgent(BaseAgent):
    def __init__(self, model_name: str, api_key: str, base_url: str):
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            format="json",
        )
        self.knowledge_base = PROWLER_KNOWLEDGE_BASE

    def _clean_json_text(self, text: str) -> Dict:
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        try:
            return json.loads(text)
        except:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            return json.loads(match.group(0)) if match else {}

    def _is_term_match(self, term: str, text: str) -> bool:
        if term in text:
            return True
        matches = difflib.get_close_matches(term, text.split(), n=1, cutoff=0.8)
        return bool(matches)

    def _semantic_search(self, queries: List[str]) -> List[str]:
        found_ids = set()

        # Fallback Splitter
        refined_queries = []
        for q in queries:
            clean_q = (
                q.lower()
                .replace(" và ", ",")
                .replace(" and ", ",")
                .replace(" với ", ",")
                .replace(" with ", ",")
            )
            parts = clean_q.split(",")
            for p in parts:
                if p.strip():
                    refined_queries.append(p.strip())

        print(f"   [Search Engine] Processing refined queries: {refined_queries}")

        for query in refined_queries:
            raw_terms = query.split()
            # Lọc từ rác bằng danh sách COMMON_STOP_WORDS
            terms = [t for t in raw_terms if t not in COMMON_STOP_WORDS and len(t) > 1]

            if not terms:
                continue

            strict_matches = []
            loose_matches = []

            for check_id, description in self.knowledge_base.items():
                search_corpus = (check_id.replace("_", " ") + " " + description).lower()

                match_count = 0
                for term in terms:
                    if self._is_term_match(term, search_corpus):
                        match_count += 1

                # Logic Strict Match
                if match_count == len(terms):
                    strict_matches.append(check_id)
                elif match_count / len(terms) >= 0.6:
                    loose_matches.append(check_id)

            if strict_matches:
                print(
                    f"     -> Query '{query}': Found {len(strict_matches)} STRICT matches."
                )
                found_ids.update(strict_matches)
            else:
                found_ids.update(loose_matches)

        return list(found_ids)

    def run(self, user_request: str) -> Dict[str, Any]:
        print(f"   [PlanningAgent] Analyzing request: '{user_request}'")
        req_lower = user_request.lower()

        # ---------------------------------------------------------
        # 1. SMART RULE-BASED OVERRIDE (LỌC NHIỄU)
        # ---------------------------------------------------------
        # Logic: Tìm tên Service -> Xóa Service + Từ rác -> Còn lại gì không?
        # Nếu Rỗng -> Group Scan.
        # Nếu Còn chữ -> Specific Scan.

        alias_map = {
            "storage": "s3",
            "lưu trữ": "s3",
            "compute": "ec2",
            "danh tính": "iam",
            "tài khoản": "iam",
        }

        # 1.1 Xác định Service
        detected_service = None
        for svc in ALLOWED_GROUPS_LIST:
            if svc in req_lower:
                detected_service = svc
                break
        if not detected_service:
            for alias, real in alias_map.items():
                if alias in req_lower:
                    detected_service = real
                    break

        # 1.2 Nếu tìm thấy service, kiểm tra xem có từ khóa cụ thể nào không
        if detected_service:
            # Tạo danh sách các từ trong request
            words = req_lower.split()

            # Lọc bỏ: Tên Service, Stop Words, Ký tự đặc biệt
            meaningful_words = []
            for w in words:
                clean_w = w.strip(",.?!")
                if clean_w == detected_service:
                    continue  # Bỏ tên service
                if clean_w in COMMON_STOP_WORDS:
                    continue  # Bỏ từ rác
                if clean_w in alias_map:
                    continue  # Bỏ alias
                meaningful_words.append(clean_w)

            # 1.3 QUYẾT ĐỊNH
            if not meaningful_words:
                # Không còn từ nào có nghĩa -> GROUP SCAN
                print(
                    f"   [Rule Override] Pure intent detected: 'GROUP SCAN' for {detected_service}"
                )
                return {
                    "groups_to_scan": [detected_service],
                    "checks_to_scan": [],
                    "reasoning": "Pure group scan intent",
                }
            else:
                # Vẫn còn từ (VD: "public", "encryption") -> SPECIFIC SCAN (Để Semantic Search xử lý)
                print(
                    f"   [PlanningAgent] Specific intent detected (Keywords: {meaningful_words}). Skipping Rule Override."
                )

        # ---------------------------------------------------------
        # 2. AI SEMANTIC PLANNING (Xử lý Specific)
        # ---------------------------------------------------------
        top_groups = list(ALLOWED_GROUPS_LIST)[:50]
        prompt = ChatPromptTemplate.from_template(SEMANTIC_PLANNING_PROMPT)

        try:
            raw_output = (prompt | self.llm | StrOutputParser()).invoke(
                {"request": user_request, "allowed_groups": ", ".join(top_groups)}
            )
            plan_data = self._clean_json_text(raw_output)
            print(f"   [PlanningAgent] AI Translation: {plan_data}")

            is_group = plan_data.get("is_group_scan", False)
            target_service = plan_data.get("target_service")
            queries = plan_data.get("search_queries", [])

            # Fallback Splitter
            if not queries or (
                len(queries) == 1 and (" và " in user_request or "," in user_request)
            ):
                print("   [PlanningAgent] AI missed split. Using Python Fallback.")
                raw_splits = (
                    user_request.replace(" và ", ",").replace(" với ", ",").split(",")
                )
                for s in raw_splits:
                    clean_s = s.strip()
                    if clean_s and clean_s not in queries:
                        queries.append(clean_s)

            # Nếu AI vẫn nhất quyết bảo là Group Scan nhưng ở trên ta đã thấy có meaningful_words
            # Thì ta vẫn ưu tiên tìm kiếm theo queries nếu queries không rỗng
            if is_group and target_service and not queries:
                svc = target_service.lower().strip()
                return {
                    "groups_to_scan": [svc],
                    "checks_to_scan": [],
                    "reasoning": f"AI identified group scan",
                }

            if queries:
                found_checks = self._semantic_search(queries)
                if found_checks:
                    return {
                        "groups_to_scan": [],
                        "checks_to_scan": found_checks,
                        "reasoning": f"Semantic search matches for: {queries}",
                    }
                else:
                    # Fallback về Group nếu tìm không ra
                    for q in queries:
                        for word in q.split():
                            if word in ALLOWED_GROUPS_LIST:
                                return {
                                    "groups_to_scan": [word],
                                    "checks_to_scan": [],
                                    "reasoning": "Fallback to group",
                                }

            return {
                "groups_to_scan": ["iam"],
                "checks_to_scan": [],
                "reasoning": "Fallback default",
            }

        except Exception as e:
            print(f"   [PlanningAgent] Error: {e}")
            import traceback

            traceback.print_exc()
            return {
                "groups_to_scan": ["s3"],
                "checks_to_scan": [],
                "reasoning": "Error fallback",
            }
