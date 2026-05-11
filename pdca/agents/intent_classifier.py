"""IntentClassifier — phân loại user prompt thành intent để route trong /v1/chat.

Phase 1 — Unified Chat (QA + Scan + Action).

Output intent: `qa | scan | action | mixed` + confidence + optional metadata
(target_service, finding_ref). Backend (`pdca/api/chatbot.py`) dùng kết quả này
để switch handler. Khi confidence < threshold → force `mixed` để FE hiển thị
suggestion chips.

LLM: Ollama qua ChatOllama (JSON-mode). Có rule-based fast path cho các trường
hợp rất rõ (giảm latency + LLM cost). Toàn bộ classification được log qua
`obs_span` để Langfuse trace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from pdca.agents.shared.utils import parse_llm_json
from pdca.observability.logger import get_logger
from pdca.observability.tracing import span as obs_span

logger = get_logger(__name__)


IntentKind = Literal["qa", "scan", "mixed"]

KNOWN_SERVICES = {
    "s3", "iam", "ec2", "rds", "kms", "ecr", "vpc", "cloudtrail", "guardduty",
}

# Threshold dưới mức này → force "mixed" để FE hiển thị suggestion chips.
DEFAULT_CONFIDENCE_THRESHOLD = 0.8


@dataclass
class IntentResult:
    intent: IntentKind
    confidence: float
    reason: str = ""
    target_service: Optional[str] = None
    finding_ref: Optional[str] = None
    # Track which path produced the result for telemetry.
    source: Literal["rule", "llm", "fallback"] = "llm"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "target_service": self.target_service,
            "finding_ref": self.finding_ref,
            "source": self.source,
        }


@dataclass
class ChatContext:
    """Context passed alongside the user prompt — improves classification."""
    run_id: Optional[str] = None
    current_service: Optional[str] = None
    findings_count: int = 0
    last_turns: List[Dict[str, str]] = field(default_factory=list)  # [{role, content}, ...]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

CLASSIFIER_PROMPT = """You classify messages for an AWS security chatbot into ONE intent.

Intents:
- "scan": user wants to start/run a NEW security scan on AWS resources
         (the scan pipeline will automatically evaluate risk, propose remediation,
         pause for approval, execute, and verify — so "scan" covers the whole flow)
- "qa":   user asks for explanation, definition, advice, or "what/why/how" —
         including questions about specific findings, checks, or past runs
- "mixed": ambiguous, OR both a question and a scan request in the same message

Rules:
- A question that references an existing finding (e.g. "why did check X fail?") is "qa".
- A request to "fix / remediate / verify" something maps to "scan" (the pipeline handles
  remediation inline) unless the user is clearly asking ABOUT remediation (then "qa").
- If unsure, prefer "mixed" with confidence ~0.5-0.7.

Context:
- Active run: {run_id}
- Currently scanning: {current_service}
- Findings so far: {findings_count}
- Recent turns (most recent last):
{history_block}

User message: "{prompt}"

Output ONE JSON object (no prose, no markdown fences):
{{"intent": "scan|qa|mixed",
  "confidence": 0.0-1.0,
  "target_service": "s3|iam|ec2|... or null",
  "finding_ref": "finding/check id or null",
  "reason": "short justification"}}
"""


# ---------------------------------------------------------------------------
# Rule-based fast path
# ---------------------------------------------------------------------------

_QA_MARKERS = (
    "what is", "what's", "what about", "why", "how do", "how does", "explain",
    "tell me about", "tell me more", "want to know", "i'd like to know",
    "là gì", "là sao", "tại sao", "làm sao", "giải thích",
    "muốn biết", "cho tôi biết", "khác nhau", "vs ",
)
_SCAN_VERBS = (
    "scan ", "audit ", "run scan", "start scan",
    "quét ", "rà soát", "kiểm tra hệ thống",
)
_FINDING_REF_RE = re.compile(r"\b([a-z][a-z0-9_]{6,}|F-\d+|T-\d+)\b", re.IGNORECASE)


def _detect_service(text: str) -> Optional[str]:
    lower = text.lower()
    for s in KNOWN_SERVICES:
        if re.search(rf"\b{s}\b", lower):
            return s
    return None


def _detect_finding_ref(text: str) -> Optional[str]:
    """Pull out a check_id-like or finding ref token if present."""
    # Strong refs first.
    for pat in (r"F-\d+", r"T-\d+"):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0)
    # Prowler-style check IDs (e.g. s3_bucket_encryption, iam_root_mfa).
    # Service prefix can include digits (s3, ec2), so use [a-z][a-z0-9]+.
    m = re.search(r"\b[a-z][a-z0-9]+_[a-z][a-z0-9_]+\b", text.lower())
    if m:
        return m.group(0)
    return None


def _rule_classify(prompt: str) -> Optional[IntentResult]:
    """Return IntentResult only when a rule matches with high confidence (≥0.9).

    Anything ambiguous is left to the LLM.
    """
    p = " " + prompt.lower().strip() + " "
    svc = _detect_service(p)
    finding = _detect_finding_ref(prompt)

    has_qa = any(m in p for m in _QA_MARKERS)
    has_scan = any(v in p for v in _SCAN_VERBS)

    # Scan verb + service = strong scan signal.
    if has_scan and svc and not has_qa:
        return IntentResult(
            intent="scan", confidence=0.93,
            reason="scan verb + known service",
            target_service=svc, source="rule",
        )

    # Pure question with no scan verb.
    if has_qa and not has_scan:
        return IntentResult(
            intent="qa", confidence=0.9,
            reason="question marker without scan verb",
            target_service=svc, finding_ref=finding, source="rule",
        )

    return None


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class IntentClassifier:
    """LLM-backed intent classifier with rule-based fast path.

    Designed to be cheap: short prompt, JSON-mode, temperature=0. Latency budget
    ~300-500ms with `gemma3:4b`. Cache (prompt hash) is the caller's
    responsibility — we keep this class stateless so it's trivially testable.
    """

    def __init__(
        self,
        model_name: str,
        base_url: str = "http://localhost:11434",
        callbacks: Optional[List[BaseCallbackHandler]] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url
        self.callbacks: List[BaseCallbackHandler] = list(callbacks or [])
        self.confidence_threshold = confidence_threshold
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            format="json",
            callbacks=self.callbacks,
        )

    # ------------------------------------------------------------------
    def classify(self, prompt: str, context: Optional[ChatContext] = None) -> IntentResult:
        if not prompt or not prompt.strip():
            return IntentResult(intent="qa", confidence=0.5, reason="empty prompt", source="fallback")

        ctx = context or ChatContext()
        with obs_span(
            "agent:IntentClassifier",
            input={
                "prompt_chars": len(prompt),
                "has_run": bool(ctx.run_id),
                "current_service": ctx.current_service,
            },
        ) as sp:
            # 1. Rule fast path
            rule = _rule_classify(prompt)
            if rule is not None:
                sp.update(output=rule.to_dict())
                logger.info("intent classified (rule)", extra=rule.to_dict())
                return rule

            # 2. LLM
            result = self._classify_via_llm(prompt, ctx)

            # 3. Confidence gate → mixed
            if result.confidence < self.confidence_threshold and result.intent != "mixed":
                logger.info(
                    "intent below threshold → forced mixed",
                    extra={"raw_intent": result.intent, "confidence": result.confidence},
                )
                result = IntentResult(
                    intent="mixed",
                    confidence=result.confidence,
                    reason=f"low-confidence ({result.intent}): {result.reason}",
                    target_service=result.target_service,
                    finding_ref=result.finding_ref,
                    source=result.source,
                )

            sp.update(output=result.to_dict())
            logger.info("intent classified (llm)", extra=result.to_dict())
            return result

    # ------------------------------------------------------------------
    def _classify_via_llm(self, prompt: str, ctx: ChatContext) -> IntentResult:
        history_block = self._format_history(ctx.last_turns)
        chain = ChatPromptTemplate.from_template(CLASSIFIER_PROMPT) | self.llm | StrOutputParser()
        try:
            raw = chain.invoke({
                "prompt": prompt.strip(),
                "run_id": ctx.run_id or "none",
                "current_service": ctx.current_service or "none",
                "findings_count": ctx.findings_count,
                "history_block": history_block,
            })
        except Exception as e:
            logger.error("classifier LLM call failed", extra={"error": str(e)})
            return self._heuristic_fallback(prompt, reason=f"llm error: {e}")

        data = parse_llm_json(raw) or {}
        intent_raw = (data.get("intent") or "").strip().lower()
        # Tolerate legacy "action" from LLM by mapping it to "scan" (pipeline handles remediation).
        if intent_raw == "action":
            intent_raw = "scan"
        if intent_raw not in {"qa", "scan", "mixed"}:
            return self._heuristic_fallback(prompt, reason=f"invalid intent '{intent_raw}'")

        try:
            confidence = float(data.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        return IntentResult(
            intent=intent_raw,  # type: ignore[arg-type]
            confidence=confidence,
            reason=str(data.get("reason") or "")[:200],
            target_service=_coerce_service(data.get("target_service")),
            finding_ref=_coerce_str(data.get("finding_ref")),
            source="llm",
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _format_history(turns: List[Dict[str, str]]) -> str:
        if not turns:
            return "  (no prior turns)"
        last = turns[-3:]
        lines = []
        for t in last:
            role = (t.get("role") or "user").strip()[:9]
            content = (t.get("content") or "").strip().replace("\n", " ")[:160]
            lines.append(f"  - {role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _heuristic_fallback(prompt: str, reason: str) -> IntentResult:
        """When LLM fails entirely, return a safe 'mixed' so UX can recover."""
        svc = _detect_service(prompt)
        return IntentResult(
            intent="mixed", confidence=0.5,
            reason=f"fallback ({reason})",
            target_service=svc,
            finding_ref=_detect_finding_ref(prompt),
            source="fallback",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce_service(v: Any) -> Optional[str]:
    if not v or not isinstance(v, str):
        return None
    s = v.strip().lower()
    if s in KNOWN_SERVICES:
        return s
    return None


def _coerce_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in {"null", "none"}:
        return None
    return s[:64]
