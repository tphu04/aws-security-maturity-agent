"""
PlanningAgent V2 — RAG-first, LLM-conditional
===============================================
Architecture:
  1. InputClassifier (pure logic) → FAST_TRACK | GROUP_SCAN | RETRIEVAL_PATH
  2. RAG retrieval via build_context(consumer="planning")
  3. DeterministicScorer (pure function) — weighted scoring without LLM
  4. ConfidenceGate — only call LLM when RAG confidence is low
  5. [conditional] LLM refinement — single call, only when needed

Key improvements over V1:
  - Eliminates mandatory LLM call #1 (intent translation)
  - Replaces mandatory LLM call #2 (rerank) with deterministic scorer
  - Fails explicit — never silently defaults to S3
  - Clean output contract with both groups_to_scan and target_services
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from agents.shared.utils import parse_llm_json, sanitize_check_id

if TYPE_CHECKING:
    from agents.shared.rag_client import RAGClient

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

_GROUP_SCAN_PATTERNS = re.compile(
    r"\b(scan\s+all|full\s+scan|check\s+group|group\s+scan|scan\s+entire|"
    r"all\s+checks?\s+for|complete\s+scan)\b",
    re.IGNORECASE,
)

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
    ):
        self.rag_client = rag_client
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            format="json",
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
        """Entry point: phân tích user request → trả về assessment plan."""
        if not user_request or not isinstance(user_request, str) or not user_request.strip():
            return self._make_error_output("Empty or invalid user request.")

        request = user_request.strip()
        logger.info("PlanningAgent V2: '%s'", request)

        try:
            classification = self._classify_input(request)
            path = classification["path"]

            if path == "FAST_TRACK":
                logger.info("FAST TRACK: %d explicit check IDs", len(classification["check_ids"]))
                return self._make_output(
                    checks=classification["check_ids"],
                    reasoning="Explicit check IDs detected in request.",
                )

            if path == "GROUP_SCAN":
                logger.info("GROUP SCAN: %s", classification["service"])
                return self._make_output(
                    groups=[classification["service"]],
                    reasoning=f"Group scan requested for {classification['service']}.",
                )

            # RETRIEVAL_PATH
            retrieval = self._retrieve(request)
            scored = self._score_candidates(retrieval, classification.get("service"))
            return self._apply_confidence_gate(request, scored, retrieval)

        except Exception as e:
            logger.error("PlanningAgent critical error: %s", e, exc_info=True)
            return self._make_error_output(f"Planning failed: {e}")

    # ------------------------------------------------------------------
    # Step 1: Input Classification (pure logic, no LLM, no I/O)
    # ------------------------------------------------------------------

    def _classify_input(self, request: str) -> Dict[str, Any]:
        """
        Phân loại request thành 1 trong 3 paths.

        Returns:
            {"path": "FAST_TRACK"|"GROUP_SCAN"|"RETRIEVAL_PATH",
             "check_ids": [...],  # only for FAST_TRACK
             "service": "..."}    # detected service hoặc None
        """
        # 1. Check for explicit check IDs (strict pattern)
        check_ids = self._extract_check_ids(request)
        if check_ids:
            return {"path": "FAST_TRACK", "check_ids": check_ids, "service": None}

        # 2. Check for group scan intent
        detected_service = self._detect_service(request)
        if _GROUP_SCAN_PATTERNS.search(request) and detected_service:
            if detected_service in ALLOWED_GROUPS:
                return {"path": "GROUP_SCAN", "service": detected_service}

        # 3. Default: retrieval path
        return {"path": "RETRIEVAL_PATH", "service": detected_service}

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
          1. build_context(consumer="planning") → PlanningBundle
          2. retrieve_checks() → basic results
          3. empty result

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
            return bundle

        # Attempt 2: retrieve_checks (basic fallback)
        fallback = self._try_retrieve_checks(query)
        if fallback is not None:
            return fallback

        logger.warning("All RAG retrieval attempts failed")
        return empty

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
            check_ids = [c["check_id"] for c in scored]
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

        # Parse LLM output
        selected = [sanitize_check_id(i) for i in data.get("selected_ids", []) if i]
        selected = [s for s in selected if s]
        target_group = data.get("target_group", "").strip().lower()
        reasoning = data.get("reasoning", "LLM refinement.")

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
