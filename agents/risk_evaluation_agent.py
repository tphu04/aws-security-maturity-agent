"""
RiskEvaluationAgent — Đánh giá rủi ro findings từ Prowler scan
================================================================
Refactored theo SLICE-RS-3 (Integration_Implementation_Plan.md):
  - Import shared utils: extract_check_id, parse_llm_json (xóa _extract_json_from_text)
  - Replace 22-dòng regex × 2 bằng extract_check_id() (1 dòng)
  - Tách God Method run() thành 5 sub-methods
  - Fix extended_description luôn empty → dùng check_title (từ RAG title)
  - Validate LLM output: whitelist 3 fields, enum severity, int risk_score
  - Fix SYSTEM_PROMPT: xóa ký tự rác `._`
  - Thêm response.raise_for_status() trong _fetch_rag_context()
  - PEP 8: 4-space indent toàn bộ file
  - Replace print() → logging

SLICE-2.1: Chuyển sang RAGClient
  - Replace rag_base_url + raw HTTP calls → rag_client: RAGClient
  - _fetch_rag_context() dùng self.rag_client.build_context(consumer="risk")
  - Fallback: rag_client=None → return {} (graceful degradation)
  - Xóa import requests (không còn cần thiết)

SLICE-2.2: Batch & Confidence & Cache
  - Batch chunking: split check_ids thành groups of 20 khi >20 ids (tránh timeout)
  - Confidence hint: đọc _meta.confidence → inject vào LLM prompt
  - In-memory cache: self._rag_cache per run, avoid duplicate RAG calls
  - Metrics: cache hit/miss rate trong get_llm_metrics()
"""

import json
import logging
import time
from typing import Any, Dict, List, TYPE_CHECKING

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from agents.shared.utils import extract_check_id, parse_llm_json
from .base_agent import BaseAgent

if TYPE_CHECKING:
    from agents.shared.rag_client import RAGClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CALLBACK: Timer cho LLM calls
# ---------------------------------------------------------------------------


class TimerCallback(BaseCallbackHandler):
    def __init__(self):
        self.total_duration = 0.0
        self.call_history = []
        self.start_time = 0.0

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> Any:
        self.start_time = time.perf_counter()

    def on_llm_end(self, response: Any, **kwargs: Any) -> Any:
        duration = time.perf_counter() - self.start_time
        self.total_duration += duration
        self.call_history.append(duration)


# ---------------------------------------------------------------------------
# VALID SEVERITY VALUES
# ---------------------------------------------------------------------------

_VALID_SEVERITIES = {"Critical", "High", "Medium", "Low"}

_SEVERITY_MAP = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "N/A": 0}

# Max check_ids per RAG call to avoid timeout (SLICE-2.2)
_RAG_BATCH_CHUNK_SIZE = 20

# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------

# --- Pass 1: Đánh giá dựa trên finding ONLY (không RAG) ---
# Giữ rubric giống hệt prompt gốc (đạt 76.7% baseline), chỉ bỏ phần RAG instructions
SYSTEM_PROMPT_PASS1 = """
Bạn là Chuyên gia An ninh mạng AWS (Senior AWS Security Analyst).
Nhiệm vụ: Đánh giá rủi ro dựa trên thông tin lỗ hổng bảo mật.

HƯỚNG DẪN CHẤM ĐIỂM (SCORING RUBRIC):
1. CRITICAL (Score 9-10): Public Access vào dữ liệu nhạy cảm, chiếm quyền Admin, mất dữ liệu.
2. HIGH (Score 7-8): Cấu hình sai nghiêm trọng, thiếu mã hóa, dịch vụ phơi bày ra internet.
3. MEDIUM (Score 4-6): Thiếu Logging/Monitoring, thiếu MFA, vi phạm Compliance không nguy hiểm tức thì.
4. LOW (Score 1-3): Lỗi thông tin, thiếu Tagging.

YÊU CẦU OUTPUT JSON:
{
    "ai_severity": "Critical" | "High" | "Medium" | "Low",
    "ai_risk_score": <int 0-10>,
    "ai_reasoning": "<Giải thích ngắn gọn 1-2 câu>"
}
"""

# --- Pass 2: Điều chỉnh dựa trên RAG context ---
SYSTEM_PROMPT_PASS2 = """
Bạn là Chuyên gia An ninh mạng AWS (Senior AWS Security Analyst).

Bạn vừa đánh giá sơ bộ một lỗ hổng với kết quả "draft_severity", "draft_score", "draft_reasoning".
Bây giờ hãy đối chiếu với thông tin chính thức từ Prowler Knowledge Base:
- "rag_official_severity": Mức severity chính thức từ AWS/Prowler.
- "rag_check_title": Tên chính thức của security check.

QUY TẮC ĐIỀU CHỈNH:
1. Nếu draft_severity TRÙNG với rag_official_severity → giữ nguyên.
2. Nếu draft_severity CAO HƠN rag_official_severity → hạ xuống theo rag nếu mô tả
   lỗ hổng không cho thấy mức nguy hiểm vượt mức official.
3. Nếu draft_severity THẤP HƠN rag_official_severity → tăng lên theo rag nếu mô tả
   lỗ hổng phù hợp với mức official.
4. Luôn ưu tiên bằng chứng từ mô tả lỗ hổng hơn là chỉ dựa vào nhãn severity.

YÊU CẦU OUTPUT JSON:
{
    "ai_severity": "Critical" | "High" | "Medium" | "Low",
    "ai_risk_score": <int 0-10>,
    "ai_reasoning": "<Dựa trên draft_reasoning, giữ lại mô tả lỗ hổng và bằng chứng kỹ thuật. Thêm ghi chú nếu có điều chỉnh severity so với draft.>"
}
"""

# Legacy alias — giữ tương thích cho code bên ngoài import trực tiếp
SYSTEM_PROMPT_SINGLE = SYSTEM_PROMPT_PASS1


# ---------------------------------------------------------------------------
# AGENT CLASS
# ---------------------------------------------------------------------------


class RiskEvaluationAgent(BaseAgent):
    """Agent đánh giá rủi ro: nhận findings đã chuẩn hóa → chấm điểm AI + RAG context."""

    def __init__(self, model_name: str, api_key: str, base_url: str,
                 rag_client: "RAGClient" = None):
        super().__init__(model_name, api_key, base_url)
        self.rag_client = rag_client
        if self.rag_client is None:
            logger.warning("RiskEvaluationAgent created without rag_client — RAG context disabled")
        self.timer = TimerCallback()
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            format="json",
            callbacks=[self.timer],
        )
        self._no_think = False  # /no_think không tương thích format="json" của Ollama
        # SLICE-2.2: in-memory cache + metrics
        self._rag_cache: Dict[str, Dict] = {}
        self._rag_confidence: str = "unknown"
        self._cache_hits: int = 0
        self._cache_misses: int = 0

    def get_llm_metrics(self) -> Dict[str, Any]:
        total_lookups = self._cache_hits + self._cache_misses
        return {
            "total_latency": round(self.timer.total_duration, 4),
            "call_history": [round(t, 4) for t in self.timer.call_history],
            "call_count": len(self.timer.call_history),
            "rag_cache": {
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "hit_rate": round(self._cache_hits / total_lookups, 2) if total_lookups > 0 else 0.0,
                "confidence": self._rag_confidence,
            },
        }

    # ------------------------------------------------------------------
    # Sub-method 1: Filter FAIL findings
    # ------------------------------------------------------------------

    def _filter_fail_findings(self, normalized_findings: list) -> List[Dict]:
        """Lọc chỉ findings có status == 'FAIL'."""
        return [f for f in normalized_findings if isinstance(f, dict) and f.get("status") == "FAIL"]

    # ------------------------------------------------------------------
    # Sub-method 2: Fetch RAG context (batch)
    # ------------------------------------------------------------------

    def _fetch_rag_context(self, fail_findings: List[Dict]) -> Dict[str, Any]:
        """Batch RAG call: extract check_ids → RAGClient.build_context → context_map.

        SLICE-2.2 enhancements:
          - Chunk large batches (>20 ids) to avoid RAG timeout
          - Extract _meta.confidence for LLM prompt hint
          - Populate self._rag_cache for dedup within same run
        """
        if self.rag_client is None:
            logger.info("No rag_client — skipping RAG context fetch")
            return {}
        unique_ids = list({extract_check_id(f) for f in fail_findings} - {None})
        if not unique_ids:
            return {}
        # Check cache — skip ids already fetched (SLICE-2.2)
        uncached_ids = [cid for cid in unique_ids if cid not in self._rag_cache]
        if not uncached_ids:
            logger.info("All %d check_ids found in cache — skipping RAG call", len(unique_ids))
            self._cache_hits += len(unique_ids)
            return self._rag_cache
        formatted_ids = [f"check:{cid}" if not cid.startswith("check:") else cid for cid in uncached_ids]
        # Chunk batch to avoid timeout (SLICE-2.2)
        context_map: Dict[str, Dict] = {}
        for i in range(0, len(formatted_ids), _RAG_BATCH_CHUNK_SIZE):
            chunk = formatted_ids[i:i + _RAG_BATCH_CHUNK_SIZE]
            chunk_data = self._fetch_rag_chunk(chunk)
            context_map.update(chunk_data)
        # Update cache (SLICE-2.2)
        self._rag_cache.update(context_map)
        self._cache_misses += len(uncached_ids)
        self._cache_hits += len(unique_ids) - len(uncached_ids)
        logger.info("RAG context loaded for %d check types (cache size: %d)",
                     len(context_map), len(self._rag_cache))
        return self._rag_cache

    def _fetch_rag_chunk(self, check_ids: List[str]) -> Dict[str, Dict]:
        """Fetch RAG context for a single chunk of check_ids."""
        try:
            data = self.rag_client.build_context(
                consumer="risk",
                check_ids=check_ids,
                include_mappings=True,
            )
        except Exception as e:
            logger.warning("RAG context batch call failed: %s", e)
            return {}
        if data is None:
            logger.warning("RAG context build returned None — RAG unavailable")
            return {}
        # Extract confidence from _meta (injected by RAGClient SLICE-1.2)
        meta = data.get("_meta", {})
        confidence = meta.get("confidence", "unknown")
        if confidence != "unknown":
            self._rag_confidence = confidence
            logger.debug("RAG confidence: %s", confidence)
        # RAGClient._post() strips envelope: data = envelope["data"]
        risk_bundle = data.get("payload", {}).get("risk_bundle", {})
        chunk_map: Dict[str, Dict] = {}
        # Primary finding: check chính đang được query
        pf = risk_bundle.get("primary_finding") or {}
        if pf.get("check_id"):
            clean_id = str(pf["check_id"]).replace("check:", "")
            chunk_map[clean_id] = {"severity": pf.get("severity"),
                                   "title": pf.get("title"), "mappings": []}
        # Related findings: các check liên quan
        for f in risk_bundle.get("related_findings", []):
            cid = f.get("check_id")
            if cid:
                clean_id = str(cid).replace("check:", "")
                chunk_map[clean_id] = {"severity": f.get("severity"),
                                       "title": f.get("title"), "mappings": []}
        for m in risk_bundle.get("control_mapping", []):
            clean_id = str(m.get("check_id", "")).replace("check:", "")
            if clean_id in chunk_map:
                chunk_map[clean_id]["mappings"].append(m.get("capability_id"))
        return chunk_map

    # ------------------------------------------------------------------
    # Sub-method 3: Score single finding (LLM call + validate)
    # ------------------------------------------------------------------

    def _build_rag_context_view(self, rag_data: Dict) -> Dict[str, Any]:
        """Build rag_context dict for LLM view, with confidence hint (SLICE-2.2)."""
        view: Dict[str, Any] = {
            "official_severity": rag_data.get("severity", "Unknown"),
            "compliance_mappings": rag_data.get("mappings", []),
            "check_title": rag_data.get("title", ""),
        }
        if self._rag_confidence != "unknown":
            view["rag_confidence"] = self._rag_confidence
            view["confidence_note"] = (
                "High confidence: trust compliance data."
                if self._rag_confidence == "high"
                else "Low confidence: compliance data may be incomplete, rely more on finding details."
                if self._rag_confidence == "low"
                else "Medium confidence: use compliance data as supporting evidence."
            )
        return view

    def _build_human_msg(self, payload: Dict) -> str:
        """Tạo human message content, thêm /no_think cho qwen3 models."""
        text = json.dumps(payload, ensure_ascii=False)
        return text + " /no_think" if self._no_think else text

    def _pass1_evaluate(self, check_id: str, finding_view: Dict) -> Dict[str, Any]:
        """Pass 1: Đánh giá severity từ finding alone (không RAG)."""
        ai_data = {"ai_severity": "Medium", "ai_risk_score": 5, "ai_reasoning": "Parse Error"}
        try:
            resp = self.llm.invoke([SystemMessage(content=SYSTEM_PROMPT_PASS1),
                                    HumanMessage(content=self._build_human_msg(finding_view))])
            if resp and resp.content:
                ai_data = self._validate_llm_output(parse_llm_json(resp.content))
        except Exception as e:
            logger.warning("Pass 1 scoring failed for %s: %s", check_id, e)
        logger.info("Pass1 %s: %s (score=%s)", check_id, ai_data["ai_severity"], ai_data["ai_risk_score"])
        return ai_data

    def _pass2_adjust(self, check_id: str, finding: Dict, ai_data: Dict, rag_data: Dict) -> Dict[str, Any]:
        """Pass 2: Điều chỉnh draft severity dựa trên RAG official_severity.

        Fallback: nếu LLM parse fail → giữ nguyên Pass 1 result.
        Smart reasoning: nếu severity không đổi → giữ reasoning Pass 1 (giàu evidence).
        """
        draft_severity = ai_data["ai_severity"]
        draft_reasoning = ai_data["ai_reasoning"]
        pass2_view = {
            "check_id": check_id, "description": finding.get("description"),
            "draft_severity": draft_severity, "draft_score": ai_data["ai_risk_score"],
            "draft_reasoning": draft_reasoning,
            "rag_official_severity": rag_data.get("severity", "Unknown"),
            "rag_check_title": rag_data.get("title", ""),
        }
        adjusted = ai_data  # fallback: giữ Pass 1 nếu Pass 2 fail
        try:
            resp = self.llm.invoke([SystemMessage(content=SYSTEM_PROMPT_PASS2),
                                    HumanMessage(content=self._build_human_msg(pass2_view))])
            if resp and resp.content:
                adjusted = self._validate_llm_output(parse_llm_json(resp.content))
        except Exception as e:
            logger.warning("Pass 2 failed for %s, keeping Pass 1: %s", check_id, e)
        # Smart reasoning: giữ reasoning Pass 1 nếu severity không đổi
        if adjusted["ai_severity"] == draft_severity:
            adjusted["ai_reasoning"] = draft_reasoning
        logger.info("Pass2 %s: %s (score=%s)", check_id, adjusted["ai_severity"], adjusted["ai_risk_score"])
        return adjusted

    def _score_single_finding(self, finding: Dict, rag_data: Dict) -> Dict[str, Any]:
        """Two-Pass scoring: Pass 1 (finding only) → Pass 2 (RAG adjustment)."""
        check_id = extract_check_id(finding) or ""
        finding_view = {
            "check_id": check_id, "service": finding.get("service"),
            "resource_id": finding.get("resource_id"), "region": finding.get("region"),
            "description": finding.get("description"),
            "original_severity": finding.get("severity"),
            "remediation_text": finding.get("remediation_text"),
        }
        ai_data = self._pass1_evaluate(check_id, finding_view)
        if rag_data and rag_data.get("severity"):
            ai_data = self._pass2_adjust(check_id, finding, ai_data, rag_data)
        enriched = finding.copy()
        enriched.update({"severity": ai_data["ai_severity"], "risk_score": ai_data["ai_risk_score"],
                         "reasoning": ai_data["ai_reasoning"], "prowler_severity": finding.get("severity"),
                         "compliance": rag_data.get("mappings", [])})
        return enriched

    # ------------------------------------------------------------------
    # Sub-method 4: Validate LLM output (whitelist)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_llm_output(parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        Whitelist validation: chỉ cho phép 3 fields.
        - ai_severity: phải thuộc enum {Critical, High, Medium, Low}
        - ai_risk_score: phải int 0-10
        - ai_reasoning: str
        """
        severity = parsed.get("ai_severity", "Medium")
        if severity not in _VALID_SEVERITIES:
            logger.debug("Invalid ai_severity '%s', defaulting to 'Medium'", severity)
            severity = "Medium"

        risk_score = parsed.get("ai_risk_score", 5)
        try:
            risk_score = int(risk_score)
            risk_score = max(0, min(10, risk_score))
        except (TypeError, ValueError):
            logger.debug("Invalid ai_risk_score '%s', defaulting to 5", risk_score)
            risk_score = 5

        reasoning = str(parsed.get("ai_reasoning", "No reasoning provided"))

        return {"ai_severity": severity, "ai_risk_score": risk_score, "ai_reasoning": reasoning}

    # ------------------------------------------------------------------
    # Sub-method 5: Score all findings (loop)
    # ------------------------------------------------------------------

    def _score_findings(self, fail_findings: List[Dict], rag_context_map: Dict) -> List[Dict]:
        """Loop qua fail_findings, gọi _score_single_finding cho từng finding."""
        results = []
        for idx, finding in enumerate(fail_findings):
            short_title = finding.get("description", "Unknown")[:60]
            logger.info("[%d/%d] Evaluating: %s", idx + 1, len(fail_findings), short_title)
            check_id = extract_check_id(finding) or ""
            rag_data = rag_context_map.get(check_id, {})
            try:
                enriched = self._score_single_finding(finding, rag_data)
                results.append(enriched)
            except Exception as e:
                logger.error("Failed to score finding %s: %s", check_id, e)
                fallback = finding.copy()
                fallback.update({"severity": "Medium", "risk_score": 5,
                                 "reasoning": "Evaluation error — default Medium",
                                 "prowler_severity": finding.get("severity"),
                                 "compliance": rag_data.get("mappings", [])})
                results.append(fallback)
        return results

    # ------------------------------------------------------------------
    # Sub-method 6: Sort by priority
    # ------------------------------------------------------------------

    @staticmethod
    def _sort_by_priority(scored_findings: List[Dict]) -> List[Dict]:
        """Sort findings by (severity_map desc, risk_score desc)."""
        return sorted(
            scored_findings,
            key=lambda f: (_SEVERITY_MAP.get(f.get("severity"), 0), f.get("risk_score", 0)),
            reverse=True,
        )

    # ------------------------------------------------------------------
    # MAIN: run() — orchestration only
    # ------------------------------------------------------------------

    def run(self, normalized_findings: list) -> list:
        """Entry point: filter FAIL → fetch RAG context → score → sort."""
        # SLICE-2.2: reset per-run cache
        self._rag_cache.clear()
        self._rag_confidence = "unknown"
        self._cache_hits = 0
        self._cache_misses = 0
        logger.info("Starting risk evaluation for %d findings", len(normalized_findings))
        fail_findings = self._filter_fail_findings(normalized_findings)
        if not fail_findings:
            logger.info("No FAIL findings found. System is secure.")
            return []
        logger.info("Scoring %d FAIL findings", len(fail_findings))
        rag_context = self._fetch_rag_context(fail_findings)
        scored = self._score_findings(fail_findings, rag_context)
        result = self._sort_by_priority(scored)
        logger.info("Risk evaluation complete: %d findings scored", len(result))
        return result
