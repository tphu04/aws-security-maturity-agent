"""
PlanningAgent V3 — LLM-intent + RAG-retrieve
===============================================
Architecture:
  1. LLM Intent Classifier (single call, always) → {mode, services, check_ids, topics}
  2. Validate (pure logic + RAG lexical lookup for explicit check_ids)
  3. Route:
       - group_scan + valid services → emit groups (no RAG)
       - explicit valid check_ids → emit checks (no RAG semantic)
       - specific_checks + topics → RAG retrieve per (service × topic)
  4. Fallback: if LLM intent classifier fails → V2 regex pipeline (_run_legacy)

Why this design:
  - Single, predictable LLM call up front; no _llm_refine cascade.
  - LLM only sees the request — does NOT pick check_ids from a candidate pool,
    so it cannot fabricate IDs (RAG lexical validates / RAG semantic retrieves).
  - Multi-service requests ("scan s3 và iam") work natively — no regex hack.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from pdca.agents.shared.utils import parse_llm_json, sanitize_check_id
from pdca.observability.tracing import span as obs_span

if TYPE_CHECKING:
    from pdca.agents.shared.rag_client import RAGClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SCORING CONSTANTS
# ---------------------------------------------------------------------------

SEVERITY_WEIGHTS = {
    "critical": 1.0,
    "high": 0.8,
    "medium": 0.5,
    "low": 0.2,
}
SCORE_WEIGHT_RAG = 0.6
SCORE_WEIGHT_SEVERITY = 0.3
SCORE_WEIGHT_SERVICE = 0.1
TOP_K_RESULTS = 5

# Confidence gate thresholds
CONFIDENCE_SKIP_LLM = {"high", "medium"}
MIN_TOP_SCORE_FOR_SKIP = 0.35

# Score gap filter: drop candidates whose score falls below
# (top_score * DROP_RATIO_THRESHOLD). Prevents returning irrelevant
# candidates that happen to be in TOP_K.
DROP_RATIO_THRESHOLD = 0.85  # keep candidates within 85% of top score

# ---------------------------------------------------------------------------
# INPUT CLASSIFICATION CONSTANTS
# ---------------------------------------------------------------------------

# Check ID pattern: mimics RAG router's looks_like_check_id()
# Requires: ≥3 underscore-separated parts, starts with known service prefix, ≥12 chars
_KNOWN_SERVICE_PREFIXES = (
    "s3_", "iam_", "ec2_", "rds_", "vpc_", "lambda_", "cloudtrail_",
    "kms_", "eks_", "sns_", "sqs_", "dynamodb_", "cloudwatch_",
    "cloudfront_", "elasticache_", "ecs_", "ecr_", "secretsmanager_",
    "ssm_", "guardduty_", "config_", "waf_", "route53_", "elb_",
    "elbv2_", "redshift_", "opensearch_", "apigateway_", "glue_",
    "sagemaker_",
)

# Security-specific topic keywords (keys from _KEYWORD_SERVICE_MAP).
# Used to distinguish "scan all S3" (no topic → group) from
# "check S3 encryption" (has topic → specific).  Built once at import.
_SECURITY_TOPIC_KEYWORDS: set = set()

# Generic words that appear in requests but don't indicate a specific topic.
_GENERIC_TOKENS = {
    "scan", "check", "run", "assess", "verify", "control",
    "security", "assessment", "audit", "review",
    "all", "full", "complete", "entire", "everything",
}

ALLOWED_GROUPS = {
    "s3", "iam", "ec2", "rds", "cloudtrail", "eks", "vpc", "lambda", "kms",
}

# Extended service list (superset of ALLOWED_GROUPS, for detection only)
VALID_SERVICES = [
    "s3", "iam", "ec2", "rds", "vpc", "lambda", "cloudtrail", "kms",
    "eks", "sns", "sqs", "dynamodb", "cloudwatch", "cloudfront",
    "elasticache", "ecs", "ecr", "secretsmanager", "ssm", "guardduty",
    "config", "waf", "route53", "elb", "elbv2", "redshift", "opensearch",
    "apigateway", "glue", "sagemaker",
]

_KEYWORD_SERVICE_MAP = {
    "bucket": "s3", "storage": "s3", "object": "s3",
    "user": "iam", "role": "iam", "policy": "iam", "permission": "iam",
    "password": "iam", "credential": "iam", "mfa": "iam", "access key": "iam",
    "instance": "ec2", "server": "ec2", "security group": "ec2",
    "database": "rds", "db": "rds", "aurora": "rds",
    "network": "vpc", "subnet": "vpc", "firewall": "vpc",
    "function": "lambda", "serverless": "lambda",
    "trail": "cloudtrail", "audit": "cloudtrail", "logging": "cloudtrail",
    "encryption": "kms", "key": "kms", "cmk": "kms",
    "kubernetes": "eks", "container": "ecs", "cluster": "eks",
    "queue": "sqs", "message": "sns", "notification": "sns",
    "secret": "secretsmanager", "parameter": "ssm",
    "cdn": "cloudfront", "distribution": "cloudfront",
    "cache": "elasticache", "redis": "elasticache",
    "registry": "ecr", "image": "ecr",
    "threat": "guardduty", "detection": "guardduty",
}

# Vietnamese -> English security keyword mapping for RAG query enhancement.
# RAG documents are in English; Vietnamese queries get poor retrieval without translation.
_VI_EN_SECURITY_KEYWORDS = {
    # Actions
    "kiểm tra": "check", "kiểm soát": "control", "xác minh": "verify",
    "quét": "scan", "đánh giá": "assess", "chạy": "run",
    # Security concepts
    "mã hóa": "encryption", "mã hoá": "encryption",
    "mật khẩu": "password", "quyền truy cập": "access",
    "truy cập": "access", "công khai": "public",
    "bảo mật": "security", "rủi ro": "risk",
    "quyền": "permission", "xác thực": "authentication",
    "nhật ký": "logging", "ghi log": "logging",
    "sao lưu": "backup", "khóa": "key",
    "tường lửa": "firewall", "mạng": "network",
    "cơ sở dữ liệu": "database", "lưu trữ": "storage",
    "người dùng": "user", "tài khoản": "account",
    "vai trò": "role", "chính sách": "policy",
    "tuân thủ": "compliance", "cấu hình": "configuration",
    # States
    "bật": "enabled", "tắt": "disabled",
    "hết hạn": "expired", "không sử dụng": "unused",
    "công cộng": "public", "riêng tư": "private",
}

# Build _SECURITY_TOPIC_KEYWORDS from existing domain knowledge.
# These are the English security-concept words (keys of _KEYWORD_SERVICE_MAP
# + translated values from _VI_EN_SECURITY_KEYWORDS) minus generic/action words.
# A request that contains a service name but NONE of these → group scan intent.
_SECURITY_TOPIC_KEYWORDS.update(
    kw for kw in _KEYWORD_SERVICE_MAP if kw not in _GENERIC_TOKENS
)
_SECURITY_TOPIC_KEYWORDS.update(
    en for en in _VI_EN_SECURITY_KEYWORDS.values() if en not in _GENERIC_TOKENS
)
# Remove service names themselves — they are not "topics"
_SECURITY_TOPIC_KEYWORDS -= set(VALID_SERVICES)
_SECURITY_TOPIC_KEYWORDS -= ALLOWED_GROUPS

# Multi-intent trigger: conjunction detection in original request.
# Keeps splitter LLM-conditional — only fires when user plausibly asks
# about multiple topics in one breath.
_CONJUNCTION_PATTERN = re.compile(
    r"\b(?:và|and|plus|cùng)\b|&", re.IGNORECASE
)

# Per-sub-query candidate cap after gap filter (keeps merged pool bounded).
TOP_K_PER_SUBQUERY = 3
# Hard cap on merged multi-intent candidate list.
MAX_MERGED_CANDIDATES = 10

# ---------------------------------------------------------------------------
# LLM PROMPTS
# ---------------------------------------------------------------------------

INTENT_CLASSIFIER_PROMPT = """You are an AWS security request classifier. Extract structured intent from a user request written in Vietnamese or English.

==================== HARD RULES (read first) ====================

R1. EXTRACT, DO NOT INFER.
    Only include AWS services that appear LITERALLY in the request — by name
    (s3, iam, ec2, ...) or by an explicit keyword that maps to one service:
        bucket / lưu trữ / storage           -> s3
        user / role / policy / permission /
        mfa / access key / password / tài khoản -> iam
        instance / server / security group   -> ec2
        database / aurora / db               -> rds
        function / serverless / lambda       -> lambda
        trail / audit log / cloudtrail       -> cloudtrail
        cmk / customer master key /
        encryption key / key rotation        -> kms
        kubernetes / cluster / eks           -> eks
        subnet / flow log / vpc              -> vpc
    NEVER add a related service. Examples of FORBIDDEN inference:
      - "encryption" alone -> do NOT add kms (unless user names kms/CMK)
      - "logging" alone -> do NOT add cloudtrail (unless user names trail/audit/cloudtrail)
      - "network" alone -> do NOT add vpc (unless user names vpc/subnet/flow log)

R2. LIST ALL SERVICES MENTIONED, even when 3, 4, 5+ are listed without
    conjunctions. "s3 iam ec2 rds" must yield 4 services, not 2.

R3. VALID SERVICE CODES (use these only, lowercase):
        s3, iam, ec2, rds, vpc, lambda, cloudtrail, kms, eks
    Anything else (typos like "ecryption", names like "dynamodb" not in this
    list) MUST be omitted from the services array.

R4. mode = "group_scan" only if the user wants a broad scan and gives NO
    specific security concern.
    mode = "specific_checks" if the request mentions ANY topic such as:
    encryption, mfa, public access, password policy, logging enabled,
    key rotation, security group rules, expired credentials, root usage,
    versioning, flow log, port exposure, etc.

R5. check_ids = explicit Prowler IDs the user typed verbatim (format:
    word_word_word with at least 3 underscored parts). Empty list otherwise.

R6. ACTION VERBS ARE NOT TOPICS.
    Words like "kiểm tra / check / scan / quét / đánh giá / audit / xem /
    review / assess / verify" applied to a BARE service name with NO
    security concern = group_scan. The verb itself is NEVER a topic.
        "kiểm tra iam"        -> group_scan, topics=[]
        "check rds và lambda" -> group_scan, topics=[]
    Only add to topics if the request names an actual security CONCERN
    (encryption, mfa, public, password, ...) — not the act of checking.

R7. SERVICE KEYWORDS ARE NEVER TOPICS, AND DO NOT INFER EXTRA SERVICES.
    Every word in the R1 mapping table (bucket, kubernetes, cluster,
    security group, instance, function, trail, ...) is a SERVICE keyword.
    It maps to ITS ONE service only. Do NOT also list it under "topics".
    Do NOT add a related service:
        "security group" -> ec2 ONLY (not vpc)
        "kubernetes" / "cluster" -> eks ONLY (not ec2)
        "bucket" -> s3 ONLY

==================== REASONING STEPS ====================

Work through these silently before producing the JSON:

Step 1. Scan the request and list every service name OR keyword that maps
        to exactly one VALID service (per R1).
Step 2. Scan for security topic words. Translate Vietnamese to English.
Step 3. If Step 2 found ANY topic word -> mode = "specific_checks".
        Else -> mode = "group_scan".
Step 4. Extract any literal Prowler check ID (≥3 underscored parts).
Step 5. Build the JSON.

==================== OUTPUT FORMAT ====================

Return RAW JSON only — no markdown fences, no prose before or after:
{{
  "mode": "group_scan" | "specific_checks",
  "services": ["s3", "iam"],
  "check_ids": [],
  "topics": []
}}

==================== EXAMPLES ====================

Request: "scan toàn bộ s3"
-> {{"mode":"group_scan","services":["s3"],"check_ids":[],"topics":[]}}

Request: "kiểm tra s3 iam ec2 rds"   (no conjunction, list ALL four)
-> {{"mode":"group_scan","services":["s3","iam","ec2","rds"],"check_ids":[],"topics":[]}}

Request: "kiểm tra mã hoá trên s3"   (encryption mentioned, but ONLY s3 named)
-> {{"mode":"specific_checks","services":["s3"],"check_ids":[],"topics":["encryption"]}}
   WRONG would be: services=["s3","kms"]  -- kms was not named.

Request: "user nào chưa bật MFA"   (iam keywords: user + mfa)
-> {{"mode":"specific_checks","services":["iam"],"check_ids":[],"topics":["mfa"]}}

Request: "kiểm tra dịch vụ lưu trữ"   ("lưu trữ" maps to s3, no topic)
-> {{"mode":"group_scan","services":["s3"],"check_ids":[],"topics":[]}}

Request: "scan everything"   (no service identifiable; do NOT default)
-> {{"mode":"group_scan","services":[],"check_ids":[],"topics":[]}}

Request: "run s3_bucket_public_access"   (literal check ID)
-> {{"mode":"specific_checks","services":["s3"],"check_ids":["s3_bucket_public_access"],"topics":[]}}

Request: "kiểm tra dịch vụ iam"   (verb + bare service, no concern -> group_scan)
-> {{"mode":"group_scan","services":["iam"],"check_ids":[],"topics":[]}}
   WRONG would be: mode="specific_checks" -- "kiểm tra" is just the verb.

Request: "check rds với lambda"   (verb + 2 bare services -> group_scan)
-> {{"mode":"group_scan","services":["rds","lambda"],"check_ids":[],"topics":[]}}

Request: "kiểm tra cluster kubernetes"   (cluster+kubernetes are SERVICE keywords for eks)
-> {{"mode":"group_scan","services":["eks"],"check_ids":[],"topics":[]}}
   WRONG would be: topics=["kubernetes"] -- it's a service keyword, not a topic.

Request: "có security group ec2 nào mở port 22"   (security group -> ec2 ONLY)
-> {{"mode":"specific_checks","services":["ec2"],"check_ids":[],"topics":["security group","port"]}}
   WRONG would be: services=["ec2","vpc"] -- security group is ec2 only.

Request: "đánh giá toàn bộ s3 iam và cloudtrail"   (toàn bộ = "all" -> group_scan, no topic)
-> {{"mode":"group_scan","services":["s3","iam","cloudtrail"],"check_ids":[],"topics":[]}}
   WRONG would be: mode="specific_checks" -- "đánh giá toàn bộ" is just verb+all,
   there is NO security concern named.

Request: "audit toàn bộ rds và lambda"   (audit + toàn bộ + bare services -> group_scan)
-> {{"mode":"group_scan","services":["rds","lambda"],"check_ids":[],"topics":[]}}

==================== NOW CLASSIFY ====================

USER REQUEST: "{request}"

JSON:"""


INTENT_SPLITTER_PROMPT = """Split this AWS security request into English sub-queries, one per distinct topic.

REQUEST: "{request}"
DETECTED SERVICE: {service}

Return raw JSON only:
{{"sub_queries": ["short english phrase", "..."]}}

Rules:
- 1 sub-query if the request covers a single topic.
- 2-4 sub-queries if the request joins multiple distinct topics (via và/and/,).
- Each sub-query: 2-6 English words; include the service name when relevant.
- Translate Vietnamese to English; fix obvious typos (e.g. "encrytipn" -> "encryption").
- Do NOT invent topics that are not in the request."""


# ---------------------------------------------------------------------------
# LLM REFINEMENT PROMPT (conditional — only used when confidence is low)
# ---------------------------------------------------------------------------

LLM_REFINEMENT_PROMPT = """You are an AWS Security Expert. The user wants a security assessment but the automated system has low confidence in the results.

USER REQUEST: "{request}"

CANDIDATE CHECKS (from RAG retrieval, may be noisy):
{candidates}
{maturity_context}

Your task:
1. Understand what the user actually wants to check
2. Select the most relevant checks from the candidates (up to 5)
3. If NO candidates are relevant, determine the AWS service group to scan

JSON OUTPUT (return ONLY raw JSON):
{{
  "selected_ids": ["check_id_1", "check_id_2"],
  "target_group": "service_name_or_empty",
  "reasoning": "short explanation"
}}

Rules:
- selected_ids: actual check_id values from candidates above. Empty list if none are relevant.
- target_group: AWS service code (s3, iam, ec2, etc.) ONLY if no individual checks are relevant. Empty string otherwise.
- If you cannot determine intent at all, set both to empty and explain in reasoning."""


# ---------------------------------------------------------------------------
# AGENT CLASS
# ---------------------------------------------------------------------------

class PlanningAgent:
    """
    RAG-first, LLM-conditional planning agent.

    Flow: classify → retrieve → score → gate → [optional LLM] → output
    LLM is called in ≤20% of requests (only low-confidence cases).
    """

    def __init__(
        self,
        model_name: str,
        api_key: str = None,
        base_url: str = "http://localhost:11434",
        rag_client: "RAGClient" = None,
        callbacks: list = None,
    ):
        self.rag_client = rag_client
        self.callbacks = list(callbacks or [])
        # Langfuse hook (B5.5): planning_agent không có local TimerCallback
        # — chỉ propagate external callbacks (Langfuse handler).
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            format="json",
            callbacks=self.callbacks,
        )
        if self.rag_client is None:
            logger.warning(
                "PlanningAgent initialized without RAGClient — "
                "RAG retrieval will be unavailable"
            )

    # ------------------------------------------------------------------
    # MAIN ENTRY POINT
    # ------------------------------------------------------------------

    def run(self, user_request: str) -> Dict[str, Any]:
        """Entry point: phân tích user request → trả về assessment plan.

        Flow (Hybrid Validated FAST_TRACK):
          1. Detect service + build enhanced (English) query
          2. Extract candidate check IDs from request
          3. Validate each ID against RAG via lexical lookup (check_id param)
             - Valid IDs (found in RAG corpus)   → FAST_TRACK candidates
             - Invalid IDs (not in RAG corpus)   → used as query hints only
          4a. All IDs valid → FAST_TRACK (return immediately, no full retrieval)
          4b. Some/no valid IDs → enrich query with valid hints → RETRIEVAL_PATH
          5. Classify: GROUP_SCAN vs RETRIEVAL_PATH → retrieve → score → gate
        """
        with obs_span(
            "agent:PlanningAgent",
            input={"request_chars": len(user_request) if isinstance(user_request, str) else 0},
        ) as _agent_sp:
            result = self._run_impl(user_request)
            _agent_sp.update(
                output={
                    "checks_count": len(result.get("checks_to_scan", []) or []),
                    "groups_count": len(result.get("groups_to_scan", []) or []),
                    "fast_track": bool(result.get("fast_track")),
                }
            )
            return result

    def _run_impl(self, user_request: str) -> Dict[str, Any]:
        """V3 entry: LLM intent classifier first, regex pipeline as fallback."""
        if not user_request or not isinstance(user_request, str) or not user_request.strip():
            return self._make_error_output("Empty or invalid user request.")

        request = user_request.strip()
        logger.info("PlanningAgent V3: '%s'", request)

        intent = self._classify_intent_llm(request)
        if intent is None:
            logger.warning("LLM intent classifier failed — falling back to V2 regex pipeline")
            return self._run_legacy(request)

        try:
            return self._route_from_intent(request, intent)
        except Exception as e:
            logger.error("Intent routing crashed: %s — falling back to legacy", e, exc_info=True)
            return self._run_legacy(request)

    # ------------------------------------------------------------------
    # V3: LLM Intent Classifier (single mandatory call)
    # ------------------------------------------------------------------

    def _classify_intent_llm(self, request: str) -> Optional[Dict[str, Any]]:
        """Single LLM call to extract structured intent.

        Returns None on any failure — caller falls back to legacy regex path.
        """
        prompt = ChatPromptTemplate.from_template(INTENT_CLASSIFIER_PROMPT)
        try:
            raw = (prompt | self.llm | StrOutputParser()).invoke({"request": request})
            data = parse_llm_json(raw)
        except Exception as e:
            logger.warning("Intent classifier LLM call failed: %s", e)
            return None

        if not isinstance(data, dict):
            return None

        mode = str(data.get("mode", "")).strip().lower()
        if mode not in ("group_scan", "specific_checks"):
            logger.warning("Intent classifier returned invalid mode: %r", mode)
            return None

        services = data.get("services", [])
        check_ids = data.get("check_ids", [])
        topics = data.get("topics", [])
        if not isinstance(services, list) or not isinstance(check_ids, list) or not isinstance(topics, list):
            logger.warning("Intent classifier returned non-list field(s)")
            return None

        norm = {
            "mode": mode,
            "services": [s.strip().lower() for s in services if isinstance(s, str) and s.strip()],
            "check_ids": [sanitize_check_id(c) for c in check_ids if isinstance(c, str) and c.strip()],
            "topics": [t.strip().lower() for t in topics if isinstance(t, str) and t.strip()],
        }
        norm["check_ids"] = [c for c in norm["check_ids"] if c and c != "<unknown>"]
        logger.info(
            "Intent: mode=%s services=%s check_ids=%s topics=%s",
            norm["mode"], norm["services"], norm["check_ids"], norm["topics"],
        )
        return norm

    # ------------------------------------------------------------------
    # V3: Router — pure logic + RAG (no further LLM)
    # ------------------------------------------------------------------

    def _route_from_intent(self, request: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        mode = intent["mode"]
        services = [s for s in intent["services"] if s in ALLOWED_GROUPS]
        dropped = set(intent["services"]) - set(services)
        if dropped:
            logger.info("Dropping unsupported services from intent: %s", sorted(dropped))

        check_ids = intent["check_ids"]
        topics = intent["topics"]

        # 1. Explicit check_ids → validate via RAG lexical
        if check_ids:
            valid_ids, invalid_ids = self._validate_check_ids(check_ids)
            if valid_ids and not invalid_ids:
                return self._make_output(
                    checks=valid_ids,
                    reasoning=f"LLM intent: explicit check IDs validated ({len(valid_ids)}).",
                )
            if valid_ids:
                logger.info(
                    "Partial valid IDs (%d valid, %d invalid) — using valid + topic retrieval",
                    len(valid_ids), len(invalid_ids),
                )
                # fall through to retrieval, but seed topics with valid IDs as hints
                topics = topics + valid_ids

        # 2. Group scan
        if mode == "group_scan":
            if not services:
                return self._make_error_output(
                    "LLM identified group_scan intent but no valid AWS services. "
                    "Please specify a service (s3, iam, ec2, ...)."
                )
            return self._make_output(
                groups=services,
                reasoning=f"LLM intent: group scan {services}.",
            )

        # 3. specific_checks → RAG retrieval per (service × topic)
        if not services:
            return self._make_error_output(
                "LLM identified specific_checks intent but no valid AWS services."
            )

        all_checks: List[str] = []
        seen: set = set()
        # If no topics were extracted, use service name itself as the query.
        topic_list = topics or [""]
        for svc in services:
            for topic in topic_list:
                query = f"{svc} {topic}".strip()
                retrieval = self._retrieve(query)
                scored = self._score_candidates(retrieval, svc)
                for c in scored[:TOP_K_PER_SUBQUERY]:
                    cid = c["check_id"]
                    if cid not in seen:
                        seen.add(cid)
                        all_checks.append(cid)
                if len(all_checks) >= MAX_MERGED_CANDIDATES:
                    break
            if len(all_checks) >= MAX_MERGED_CANDIDATES:
                break

        if not all_checks:
            return self._make_error_output(
                f"LLM intent specific_checks for services={services} topics={topics} "
                "but RAG returned no candidates."
            )

        return self._make_output(
            checks=all_checks[:MAX_MERGED_CANDIDATES],
            reasoning=(
                f"LLM intent: {len(services)} service(s) × {len(topic_list)} topic(s) "
                f"→ {len(all_checks)} checks via RAG retrieval."
            ),
        )

    # ------------------------------------------------------------------
    # Legacy V2 pipeline (regex-first) — kept as fallback when LLM intent fails
    # ------------------------------------------------------------------

    def _run_legacy(self, request: str) -> Dict[str, Any]:
        try:
            # Step 1: Detect service + translate to English
            detected_service = self._detect_service(request)
            enhanced_query = self._build_rag_query(request, detected_service)

            # Step 2: Extract candidate check IDs from request
            candidate_ids = self._extract_check_ids(request)

            if candidate_ids:
                # Step 3: Validate each ID against RAG corpus (lexical — fast)
                valid_ids, invalid_ids = self._validate_check_ids(candidate_ids)
                logger.info(
                    "ID validation: %d valid, %d invalid (of %d candidates)",
                    len(valid_ids), len(invalid_ids), len(candidate_ids),
                )

                if valid_ids and not invalid_ids:
                    # Step 4a: All IDs confirmed valid → FAST_TRACK
                    logger.info("FAST_TRACK (all valid): %s", valid_ids)
                    return self._make_output(
                        checks=valid_ids,
                        reasoning=(
                            f"Explicit check IDs verified in RAG corpus: {', '.join(valid_ids)}."
                        ),
                    )

                # Step 4b: Some/all IDs invalid → enrich query with valid hints
                hints = valid_ids or candidate_ids  # prefer valid, fallback to all as hints
                hint_str = " ".join(hints)
                enhanced_query = f"{enhanced_query} {hint_str}".strip()
                if invalid_ids:
                    logger.info(
                        "Invalid IDs used as RAG hints: %s", invalid_ids
                    )

            # Step 5: Multi-intent check (LLM-conditional)
            # Trigger: conjunction in request + service detected + no explicit IDs.
            if (detected_service
                    and not candidate_ids
                    and _CONJUNCTION_PATTERN.search(request)):
                sub_queries = self._split_intents(request, detected_service)
                if len(sub_queries) >= 2:
                    logger.info(
                        "MULTI_INTENT: %d sub-queries: %s",
                        len(sub_queries), sub_queries,
                    )
                    return self._multi_retrieve_and_gate(
                        request, sub_queries, detected_service,
                    )

            # Step 6: Classify on enhanced query (language-independent)
            if self._is_group_intent(enhanced_query, detected_service):
                logger.info("GROUP SCAN: %s", detected_service)
                return self._make_output(
                    groups=[detected_service],
                    reasoning=f"Group scan requested for {detected_service}.",
                )

            # Step 7: RETRIEVAL_PATH (single query)
            retrieval = self._retrieve(enhanced_query)
            scored = self._score_candidates(retrieval, detected_service)
            return self._apply_confidence_gate(request, scored, retrieval)

        except Exception as e:
            logger.error("PlanningAgent critical error: %s", e, exc_info=True)
            return self._make_error_output(f"Planning failed: {e}")

    def _validate_check_ids(
        self, candidate_ids: List[str]
    ) -> tuple[List[str], List[str]]:
        """
        Validate extracted check IDs bằng cách query RAG với check_id param.
        Dùng lexical mode — cực nhanh, không cần embedding.

        Returns:
            (valid_ids, invalid_ids) — chia IDs thành 2 nhóm.
        """
        if not self.rag_client:
            # RAG unavailable — trust all IDs, fall back to old FAST_TRACK behavior
            logger.warning("RAG unavailable for ID validation, trusting all candidate IDs")
            return candidate_ids, []

        valid, invalid = [], []
        for cid in candidate_ids:
            try:
                result = self.rag_client.retrieve_checks(
                    check_id=cid,
                    top_k=1,
                    retrieval_mode="lexical",
                )
                results_list = (result or {}).get("results", [])
                if results_list:
                    # RAG found the check ID in its corpus — it's real
                    valid.append(cid)
                    logger.debug("ID validated: %s", cid)
                else:
                    invalid.append(cid)
                    logger.info("ID not found in RAG corpus (invalid): %s", cid)
            except Exception as e:
                # If lookup fails, be safe — treat as hint, not direct output
                invalid.append(cid)
                logger.warning("ID validation failed for %s: %s", cid, e)
        return valid, invalid

    # ------------------------------------------------------------------
    # Step 0: RAG Query Enhancement (pure logic, no LLM)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_rag_query(request: str, detected_service: Optional[str] = None) -> str:
        """Build English-enhanced query for RAG retrieval.

        RAG documents are in English. Vietnamese queries get poor retrieval
        because embedding similarity is low cross-language. This method:
        1. Translates known Vietnamese security keywords → English
        2. Prepends detected service name for better matching
        3. Falls back to original request if no translation needed

        Pure logic — no LLM call, no I/O.
        """
        lower = request.lower()

        # Check if request contains Vietnamese characters
        has_vietnamese = any(
            "\u00c0" <= ch <= "\u01b0" or "\u1ea0" <= ch <= "\u1ef9"
            for ch in request
        )

        if not has_vietnamese:
            # English request — use as-is, optionally prepend service
            if detected_service and detected_service not in lower:
                return f"{detected_service} {request}"
            return request

        # Vietnamese request — translate keywords
        translated_parts = []
        if detected_service:
            translated_parts.append(detected_service)

        # Replace Vietnamese keywords with English equivalents
        for vi_kw, en_kw in _VI_EN_SECURITY_KEYWORDS.items():
            if vi_kw in lower:
                translated_parts.append(en_kw)

        # Keep English words already in the request (e.g. "RDS", "MFA", "S3")
        # Filter out Vietnamese fragments that happen to be ASCII
        _vi_fragments = {
            "tra", "xem", "cho", "trong", "truy", "cac", "tat",
            "dang", "duoc", "khong", "hay", "nao", "toan", "bat",
        }
        english_words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]{2,}\b", request)
        for word in english_words:
            wl = word.lower()
            if wl not in translated_parts and wl not in _vi_fragments:
                translated_parts.append(wl)

        if translated_parts:
            enhanced = " ".join(dict.fromkeys(translated_parts))  # dedupe, preserve order
            logger.info("RAG query enhanced: '%s' → '%s'", request[:60], enhanced)
            return enhanced

        return request

    # ------------------------------------------------------------------
    # Step 1: Input Classification (pure logic, no LLM, no I/O)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_group_intent(enhanced_query: str, detected_service: Optional[str]) -> bool:
        """Detect group-scan intent from the enhanced (English) query.

        Logic: if we can identify a service but the query contains NO
        security-specific topic keyword, the user wants a broad group scan
        rather than checks for a specific concern.

        Operates on the already-translated query → language-independent.
        """
        if not detected_service or detected_service not in ALLOWED_GROUPS:
            return False

        # Tokenise the enhanced query and remove service names + generic words
        tokens = set(re.findall(r"[a-zA-Z]{2,}", enhanced_query.lower()))
        tokens -= _GENERIC_TOKENS
        tokens -= set(VALID_SERVICES)
        tokens -= ALLOWED_GROUPS

        # If any remaining token is a known security topic → specific intent
        has_specific_topic = bool(tokens & _SECURITY_TOPIC_KEYWORDS)
        if not has_specific_topic:
            logger.info(
                "Group intent detected: service=%s, no specific topic in '%s'",
                detected_service, enhanced_query,
            )
        return not has_specific_topic

    @staticmethod
    def _extract_check_ids(request: str) -> List[str]:
        """
        Extract Prowler check IDs dùng strict criteria matching
        RAG router's looks_like_check_id() logic.

        Criteria: starts with known service prefix, ≥3 underscore parts, ≥12 chars.
        """
        tokens = re.findall(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+){2,})\b", request.lower())
        valid = []
        seen = set()
        for token in tokens:
            if len(token) < 12:
                continue
            if not any(token.startswith(p) for p in _KNOWN_SERVICE_PREFIXES):
                continue
            clean = sanitize_check_id(token)
            if clean and clean not in seen:
                seen.add(clean)
                valid.append(clean)
        return valid

    @staticmethod
    def _detect_service(request: str) -> Optional[str]:
        """
        Detect AWS service từ request text bằng keyword matching.
        Returns first match hoặc None.
        """
        lower = request.lower()
        # Direct service name match (highest precision)
        for svc in VALID_SERVICES:
            if re.search(rf"\b{svc}\b", lower):
                return svc
        # Keyword-based inference
        for keyword, svc in _KEYWORD_SERVICE_MAP.items():
            if keyword in lower:
                return svc
        return None

    # ------------------------------------------------------------------
    # Step 2: RAG Retrieval
    # ------------------------------------------------------------------

    def _retrieve(self, query: str) -> Dict[str, Any]:
        """
        Gọi RAG service. Fallback chain:
          1. build_context(consumer="planning") → PlanningBundle (rich, có maturity)
          2. retrieve_checks() → basic results (có score chi tiết)
          3. empty result

        Nếu build_context thành công nhưng thiếu score (score=None),
        enrich bằng score từ retrieve_checks.

        Returns:
            {"candidates": [...], "maturity_context": str,
             "confidence": str, "source": str}
        """
        empty = {
            "candidates": [], "maturity_context": "",
            "confidence": "low", "source": "none",
        }

        if self.rag_client is None:
            return empty

        # Attempt 1: build_context (PlanningBundle — rich)
        bundle = self._try_build_context(query)
        if bundle is not None:
            # Enrich scores nếu PlanningBundle thiếu score (tất cả = 0.8 default)
            needs_scores = any(
                c.get("score") == 0.8 for c in bundle.get("candidates", [])
            )
            if needs_scores and bundle["candidates"]:
                bundle = self._enrich_scores(query, bundle)
            return bundle

        # Attempt 2: retrieve_checks (basic fallback)
        fallback = self._try_retrieve_checks(query)
        if fallback is not None:
            return fallback

        logger.warning("All RAG retrieval attempts failed")
        return empty

    def _enrich_scores(self, query: str, bundle: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich PlanningBundle candidates với scores từ retrieve_checks.

        PlanningBundle có maturity context nhưng thiếu relevance score.
        retrieve_checks có scores chi tiết. Kết hợp cả hai.
        """
        scores_data = self._try_retrieve_checks(query)
        if scores_data is None:
            return bundle

        # Build score lookup
        score_map = {}
        for c in scores_data.get("candidates", []):
            score_map[c["check_id"]] = c.get("score", 0.0)

        # Enrich candidates
        enriched = 0
        for c in bundle["candidates"]:
            real_score = score_map.get(c["check_id"])
            if real_score is not None:
                c["score"] = real_score
                enriched += 1

        if enriched:
            logger.info("Enriched %d/%d candidates with retrieval scores",
                        enriched, len(bundle["candidates"]))

        return bundle

    def _try_build_context(self, query: str) -> Optional[Dict[str, Any]]:
        """Try build_context(consumer='planning'). Returns None on failure."""
        result = self.rag_client.build_context(
            consumer="planning", query=query,
            top_k=10, retrieval_mode="hybrid",
        )
        if result is None:
            logger.warning("build_context returned None")
            return None

        bundle = result.get("payload", {}).get("planning_bundle")
        if bundle is None:
            logger.warning("build_context: missing planning_bundle")
            return None

        findings = bundle.get("related_findings", [])
        confidence = result.get("_meta", {}).get("confidence", "medium")

        candidates = []
        seen = set()
        for item in findings:
            cid = sanitize_check_id(item.get("check_id", ""))
            if not cid or cid == "<unknown>" or cid in seen:
                continue
            seen.add(cid)
            candidates.append({
                "check_id": cid,
                "title": item.get("title", ""),
                "severity": item.get("severity", "").lower(),
                "service": item.get("service", "").lower(),
                "score": item.get("score", 0.8),
            })

        maturity_context = self._format_maturity(
            bundle.get("control_mapping_ids", []),
            bundle.get("maturity_capability_ids", []),
        )

        logger.info(
            "build_context OK: %d candidates, confidence=%s",
            len(candidates), confidence,
        )
        return {
            "candidates": candidates[:10],
            "maturity_context": maturity_context,
            "confidence": confidence,
            "source": "build_context",
        }

    def _try_retrieve_checks(self, query: str) -> Optional[Dict[str, Any]]:
        """Fallback: retrieve_checks(). Returns None on failure."""
        result = self.rag_client.retrieve_checks(
            query=query, top_k=10, retrieval_mode="hybrid",
        )
        if result is None:
            logger.warning("retrieve_checks returned None")
            return None

        seen = {}
        for item in result.get("results", []):
            raw_id = item.get("doc_id") or item.get("check_id") or ""
            cid = sanitize_check_id(raw_id)
            if not cid or cid == "<unknown>":
                continue
            meta = item.get("metadata", {})
            score = round(item.get("score", 0.0), 3)
            if cid not in seen or score > seen[cid]["score"]:
                seen[cid] = {
                    "check_id": cid,
                    "title": meta.get("title", ""),
                    "severity": meta.get("severity", "").lower(),
                    "service": meta.get("service", "").lower(),
                    "score": score,
                }

        candidates = list(seen.values())[:10]
        if not candidates:
            return None

        logger.info("retrieve_checks fallback: %d candidates", len(candidates))
        return {
            "candidates": candidates,
            "maturity_context": "",
            "confidence": "medium",
            "source": "retrieve_checks",
        }

    @staticmethod
    def _format_maturity(mapping_ids: List[str], maturity_ids: List[str]) -> str:
        """Format maturity context cho LLM prompt. Truncate at logical boundary."""
        if not mapping_ids and not maturity_ids:
            return ""
        parts = []
        if mapping_ids:
            parts.append(f"Control mappings: {', '.join(mapping_ids[:5])}")
        if maturity_ids:
            parts.append(f"Maturity capabilities: {', '.join(maturity_ids[:5])}")
        text = "\nSECURITY MATURITY CONTEXT:\n" + "\n".join(parts)
        # Truncate at last comma to avoid cutting mid-token
        if len(text) > 500:
            cut = text[:500].rfind(",")
            text = text[:cut] if cut > 0 else text[:500]
        return text

    # ------------------------------------------------------------------
    # Step 3: Deterministic Scorer (pure function, no LLM)
    # ------------------------------------------------------------------

    @staticmethod
    def _score_candidates(
        retrieval: Dict[str, Any],
        detected_service: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        Score và rank candidates bằng weighted formula.

        final_score = SCORE_WEIGHT_RAG * rag_score
                    + SCORE_WEIGHT_SEVERITY * severity_weight
                    + SCORE_WEIGHT_SERVICE * service_match

        Returns top TOP_K_RESULTS candidates sorted by final_score desc.
        """
        scored = []
        for c in retrieval.get("candidates", []):
            rag_score = c.get("score", 0.0)
            sev_weight = SEVERITY_WEIGHTS.get(c.get("severity", ""), 0.3)
            svc_match = 1.0 if (
                detected_service and c.get("service") == detected_service
            ) else 0.0

            final = (
                SCORE_WEIGHT_RAG * rag_score
                + SCORE_WEIGHT_SEVERITY * sev_weight
                + SCORE_WEIGHT_SERVICE * svc_match
            )

            scored.append({**c, "final_score": round(final, 4)})

        scored.sort(key=lambda x: x["final_score"], reverse=True)
        return scored[:TOP_K_RESULTS]

    # ------------------------------------------------------------------
    # Step 4: Confidence Gate
    # ------------------------------------------------------------------

    def _apply_confidence_gate(
        self,
        request: str,
        scored: List[Dict[str, Any]],
        retrieval: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Decision point: trả kết quả deterministic hoặc gọi LLM.

        - confidence ∈ {high, medium} AND top_score > threshold → NO LLM
        - confidence == low OR no candidates → LLM refinement
        """
        confidence = retrieval.get("confidence", "low")
        top_score = scored[0]["final_score"] if scored else 0.0

        if (confidence in CONFIDENCE_SKIP_LLM
                and scored
                and top_score > MIN_TOP_SCORE_FOR_SKIP):
            # Score gap filter: chỉ giữ candidates có score >= top * DROP_RATIO
            cutoff = top_score * DROP_RATIO_THRESHOLD
            filtered = [c for c in scored if c["final_score"] >= cutoff]
            check_ids = [c["check_id"] for c in filtered]

            dropped = len(scored) - len(filtered)
            if dropped:
                logger.info(
                    "Score gap filter: dropped %d/%d candidates below %.3f (cutoff=%.1f%% of top)",
                    dropped, len(scored), cutoff, DROP_RATIO_THRESHOLD * 100,
                )

            logger.info(
                "ConfidenceGate PASS: confidence=%s, top=%.3f → %d checks (no LLM)",
                confidence, top_score, len(check_ids),
            )
            return self._make_output(
                checks=check_ids,
                reasoning=(
                    f"Deterministic selection: RAG confidence={confidence}, "
                    f"top_score={top_score:.3f}, selected {len(check_ids)} checks."
                ),
            )

        # Need LLM refinement
        logger.info(
            "ConfidenceGate FAIL: confidence=%s, top=%.3f → LLM refinement",
            confidence, top_score,
        )
        return self._llm_refine(request, scored, retrieval)

    # ------------------------------------------------------------------
    # Step 5: Conditional LLM Refinement
    # ------------------------------------------------------------------

    def _llm_refine(
        self,
        request: str,
        scored: List[Dict[str, Any]],
        retrieval: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Single LLM call cho low-confidence cases.
        Nếu LLM cũng fail → explicit error, KHÔNG BAO GIỜ default S3.
        """
        candidates_text = (
            json.dumps(scored, indent=2, ensure_ascii=False) if scored else "[]"
        )
        maturity_text = retrieval.get("maturity_context", "")

        prompt = ChatPromptTemplate.from_template(LLM_REFINEMENT_PROMPT)
        try:
            raw = (prompt | self.llm | StrOutputParser()).invoke({
                "request": request,
                "candidates": candidates_text,
                "maturity_context": maturity_text,
            })
            data = parse_llm_json(raw)
        except Exception as e:
            logger.error("LLM refinement failed: %s", e)
            return self._make_error_output(f"LLM refinement failed: {e}")

        # Parse LLM output — constrain to candidate pool (LLM selects, not fabricates)
        candidate_ids = {c["check_id"] for c in scored}
        raw_selected = [sanitize_check_id(i) for i in data.get("selected_ids", []) if i]
        selected = [s for s in raw_selected if s and s in candidate_ids]
        target_group = data.get("target_group", "").strip().lower()
        reasoning = data.get("reasoning", "LLM refinement.")

        if raw_selected and not selected:
            logger.warning(
                "LLM fabricated %d IDs not in candidate pool: %s",
                len(raw_selected), raw_selected[:3],
            )

        if selected:
            logger.info("LLM refinement selected %d checks", len(selected))
            return self._make_output(checks=selected, reasoning=reasoning)

        if target_group and target_group in ALLOWED_GROUPS:
            logger.info("LLM refinement → group scan: %s", target_group)
            return self._make_output(groups=[target_group], reasoning=reasoning)

        # LLM could not determine intent → explicit failure
        logger.warning("LLM refinement produced no actionable result")
        return self._make_error_output(
            "Could not determine assessment target. "
            "Please specify an AWS service or check IDs. "
            f"LLM reasoning: {reasoning}"
        )

    # ------------------------------------------------------------------
    # Multi-intent splitter (LLM-conditional, pre-RAG)
    # ------------------------------------------------------------------

    def _split_intents(
        self, request: str, detected_service: Optional[str],
    ) -> List[str]:
        """Ask LLM to split multi-topic request into English sub-queries.

        Returns an empty list on any failure so the caller falls back
        to the single-query path (never silently wrong).
        """
        prompt = ChatPromptTemplate.from_template(INTENT_SPLITTER_PROMPT)
        try:
            raw = (prompt | self.llm | StrOutputParser()).invoke({
                "request": request,
                "service": detected_service or "unknown",
            })
            data = parse_llm_json(raw)
        except Exception as e:
            logger.warning("Intent splitter failed: %s", e)
            return []

        sub_queries = data.get("sub_queries", [])
        if not isinstance(sub_queries, list):
            return []
        cleaned = [
            q.strip() for q in sub_queries
            if isinstance(q, str) and q.strip()
        ]
        # Cap at 4 to bound downstream RAG calls
        return cleaned[:4]

    def _multi_retrieve_and_gate(
        self,
        request: str,
        sub_queries: List[str],
        detected_service: Optional[str],
    ) -> Dict[str, Any]:
        """Run RAG per sub-query, union top candidates, then gate.

        Key difference from single-query path: the gap filter is applied
        PER sub-query (within-topic tightness) rather than across all
        candidates, so a second topic's top hit isn't culled by the
        first topic's stronger cluster.
        """
        merged: Dict[str, Dict[str, Any]] = {}
        maturity_parts: List[str] = []
        confidences: List[str] = []

        for sq in sub_queries:
            retrieval = self._retrieve(sq)
            confidences.append(retrieval.get("confidence", "low"))
            mat = retrieval.get("maturity_context", "")
            if mat:
                maturity_parts.append(mat)

            scored = self._score_candidates(retrieval, detected_service)
            if not scored:
                continue

            top = scored[0]["final_score"]
            cutoff = top * DROP_RATIO_THRESHOLD
            kept = 0
            for c in scored:
                if kept >= TOP_K_PER_SUBQUERY:
                    break
                if c["final_score"] < cutoff:
                    break  # scored is sorted desc
                cid = c["check_id"]
                prev = merged.get(cid)
                if prev is None or c["final_score"] > prev["final_score"]:
                    merged[cid] = c
                kept += 1

            logger.info(
                "Sub-query '%s': %d candidates kept (top=%.3f, cutoff=%.3f)",
                sq, kept, top, cutoff,
            )

        merged_list = sorted(
            merged.values(), key=lambda x: x["final_score"], reverse=True,
        )[:MAX_MERGED_CANDIDATES]

        # Aggregate confidence: worst-case across sub-queries.
        if not confidences or "low" in confidences:
            agg_confidence = "low"
        elif "medium" in confidences:
            agg_confidence = "medium"
        else:
            agg_confidence = "high"

        top_score = merged_list[0]["final_score"] if merged_list else 0.0

        if (merged_list
                and agg_confidence in CONFIDENCE_SKIP_LLM
                and top_score > MIN_TOP_SCORE_FOR_SKIP):
            check_ids = [c["check_id"] for c in merged_list]
            logger.info(
                "Multi-intent ConfidenceGate PASS: %d sub-queries -> %d checks (no LLM)",
                len(sub_queries), len(check_ids),
            )
            return self._make_output(
                checks=check_ids,
                reasoning=(
                    f"Multi-intent split into {len(sub_queries)} sub-queries "
                    f"[{'; '.join(sub_queries)}]: selected {len(check_ids)} checks."
                ),
            )

        # Low aggregate confidence or empty union -> LLM refine on merged pool
        logger.info(
            "Multi-intent ConfidenceGate FAIL: confidence=%s, top=%.3f -> LLM refine",
            agg_confidence, top_score,
        )
        maturity_text = "\n".join(maturity_parts[:2])
        return self._llm_refine(
            request, merged_list,
            {"maturity_context": maturity_text, "confidence": agg_confidence},
        )

    # ------------------------------------------------------------------
    # Output Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_output(
        groups: List[str] = None,
        checks: List[str] = None,
        reasoning: str = "",
    ) -> Dict[str, Any]:
        """
        Build output dict với cả groups_to_scan và target_services
        để backward-compatible với tất cả downstream consumers.
        """
        g = groups or []
        c = checks or []
        return {
            "groups_to_scan": g,
            "target_services": g,   # alias cho verification_node + report_node
            "checks_to_scan": c,
            "reasoning": reasoning,
        }

    @staticmethod
    def _make_error_output(error_msg: str) -> Dict[str, Any]:
        """
        Explicit error output. KHÔNG BAO GIỜ default S3.
        scanning_node nhận empty lists → không scan → pipeline surface error.
        """
        return {
            "groups_to_scan": [],
            "target_services": [],
            "checks_to_scan": [],
            "reasoning": "",
            "error": error_msg,
        }
