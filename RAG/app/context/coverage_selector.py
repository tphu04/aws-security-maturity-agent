"""
Coverage-aware selection for context building.

Handles all item selection: checks (with planning diversification),
mappings (with entity gating), and capabilities (with domain filtering).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from app.core.constants import QUERY_INTENT_CLUSTERS
from app.core.models import (
    Confidence,
    SelectedCapabilityContext,
    SelectedCheckContext,
    SelectedMappingContext,
)
from app.core.utils import mapping_sort_key
from app.context.intent_detector import IntentDetector
from app.context._helpers import (
    compress_capability_text,
    compress_check_text,
    compress_text,
    ensure_dict,
    extract_capability_name,
    extract_check_title,
    maybe_float,
    maybe_str,
    normalize_confidence,
    normalize_str_list,
)


class CoverageSelector:
    """
    Coverage-aware selection for checks, mappings, and capabilities.

    Uses IntentDetector for query intent detection and entity gating.
    """

    def __init__(self) -> None:
        self._intent_detector = IntentDetector()

    # ============================================================
    # Check selection
    # ============================================================

    def select_checks(
        self,
        check_results: Sequence[Dict[str, Any]],
        consumer: str,
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
        max_chars_per_item: int,
        requested_check_ids: Sequence[str],
        query: Optional[str] = None,
    ) -> Tuple[List[SelectedCheckContext], List[SelectedCheckContext]]:
        target_n = self.target_check_count(consumer, confidence, review_recommended, warnings)
        requested_ids = {_strip_doc_prefix(str(x).strip().lower()) for x in requested_check_ids}

        requested: List[SelectedCheckContext] = []
        related: List[SelectedCheckContext] = []
        seen_doc_ids: set[str] = set()
        seen_check_ids: set[str] = set()
        planning_candidates: List[SelectedCheckContext] = []

        for item in check_results:
            doc_id = str(item.get("doc_id") or "").strip()
            metadata = ensure_dict(item.get("metadata"))
            check_id = str(metadata.get("check_id") or "").strip()

            if not doc_id or not check_id:
                continue
            if doc_id in seen_doc_ids or check_id in seen_check_ids:
                continue

            ctx = SelectedCheckContext(
                check_id=check_id,
                doc_id=doc_id,
                service=maybe_str(metadata.get("service")),
                title=extract_check_title(item),
                short_text=compress_check_text(item, max_chars_per_item),
                matched_by=normalize_str_list(item.get("matched_by")),
                score=maybe_float(item.get("score")),
                confidence=confidence,
                metadata=metadata,
            )

            seen_doc_ids.add(doc_id)
            seen_check_ids.add(check_id)

            if consumer == "planning":
                planning_candidates.append(ctx)
                if len(planning_candidates) >= target_n:
                    break
            else:
                if check_id.lower() in requested_ids:
                    requested.append(ctx)
                else:
                    related.append(ctx)
                if len(requested) + len(related) >= target_n:
                    break

        if consumer == "planning":
            for c in self.planning_coverage_select(planning_candidates, query):
                if c.check_id.lower() in requested_ids:
                    requested.append(c)
                else:
                    related.append(c)

        return requested, related

    # ============================================================
    # Mapping selection
    # ============================================================

    def select_mappings(
        self,
        mapping_results: Sequence[Dict[str, Any]],
        consumer: str,
        max_chars_per_item: int,
        check_signal: Optional[str] = None,
    ) -> List[SelectedMappingContext]:
        target_n = 2 if consumer == "planning" else 3
        selected: List[SelectedMappingContext] = []
        seen_pairs: set[Tuple[str, str]] = set()

        for item in sorted(mapping_results, key=mapping_sort_key, reverse=True):
            check_id = maybe_str(item.get("check_id")) or maybe_str(item.get("source_check_id"))
            capability_id = maybe_str(item.get("capability_id"))
            if not check_id or not capability_id:
                continue

            pair = (check_id, capability_id)
            if pair in seen_pairs:
                continue

            if not self._intent_detector.mapping_passes_entity_gate(
                check_id=check_id,
                capability_id=capability_id,
                capability_name=maybe_str(item.get("capability_name")),
                mapping_confidence=item.get("mapping_confidence"),
                mapping_type=item.get("mapping_type"),
                review_status=item.get("review_status"),
                check_signal=check_signal or check_id,
            ):
                continue

            rationale = compress_text(
                item.get("mapping_reason") or item.get("rationale") or "",
                max_chars=max_chars_per_item,
            )

            selected.append(SelectedMappingContext(
                check_id=check_id,
                capability_id=capability_id,
                capability_name=maybe_str(item.get("capability_name")),
                mapping_confidence=normalize_confidence(item.get("mapping_confidence")),
                mapping_type=maybe_str(item.get("mapping_type")),
                review_status=maybe_str(item.get("review_status")),
                rationale=rationale or None,
                metadata=ensure_dict(item),
            ))
            seen_pairs.add(pair)

            if len(selected) >= target_n:
                break

        return selected

    # ============================================================
    # Capability selection
    # ============================================================

    def select_capabilities(
        self,
        maturity_results: Sequence[Dict[str, Any]],
        consumer: str,
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
        max_chars_per_item: int,
        check_context: Optional[str] = None,
    ) -> List[SelectedCapabilityContext]:
        target_n = self.target_capability_count(consumer, confidence, review_recommended, warnings)
        selected: List[SelectedCapabilityContext] = []
        seen_doc_ids: set[str] = set()
        seen_capability_ids: set[str] = set()

        for item in maturity_results:
            doc_id = str(item.get("doc_id") or "").strip()
            metadata = ensure_dict(item.get("metadata"))
            capability_id = str(metadata.get("capability_id") or "").strip()

            if not doc_id or not capability_id:
                continue
            if doc_id in seen_doc_ids or capability_id in seen_capability_ids:
                continue

            cap_name = extract_capability_name(item)

            if check_context and self._intent_detector.capability_domain_mismatch(
                capability_id, cap_name, check_context,
            ):
                continue

            selected.append(SelectedCapabilityContext(
                capability_id=capability_id,
                doc_id=doc_id,
                capability_name=cap_name,
                domain=maybe_str(metadata.get("domain")),
                short_text=compress_capability_text(item, max_chars_per_item),
                score=maybe_float(item.get("score")),
                confidence=confidence,
                metadata=metadata,
            ))
            seen_doc_ids.add(doc_id)
            seen_capability_ids.add(capability_id)

            if len(selected) >= target_n:
                break

        return selected

    # ============================================================
    # Planning diversification
    # ============================================================

    def planning_coverage_select(
        self,
        candidates: Sequence[SelectedCheckContext],
        query: Optional[str],
    ) -> List[SelectedCheckContext]:
        """
        Greedy coverage selection for planning consumer.

        Strategy:
        1. Detect active intents from the query.
        2. Dynamic target = clamp(len(intents) * 2, min=2, max=8).
        3. First pass: one representative per intent.
        4. Second pass: fill with new service coverage.
        5. Final pass: fill remaining slots by highest score.
        """
        if not candidates:
            return []

        intents = self._intent_detector.detect_query_intents(query)
        n_intents = len(intents)
        dynamic_target = max(2, min(8, n_intents * 2 if n_intents > 0 else 3))

        selected: List[SelectedCheckContext] = []
        selected_ids: Set[str] = set()
        covered_intents: Set[str] = set()
        covered_services: Set[str] = set()

        def score_of(c: SelectedCheckContext) -> float:
            return c.score or 0.0

        def intent_priority(c: SelectedCheckContext) -> float:
            check_id = (c.check_id or "").lower()
            text = " ".join(filter(None, [
                c.check_id, c.title, c.short_text,
                ensure_dict(c.metadata).get("description", ""),
            ])).lower()
            boost = 0.0
            if "public_access" in intents:
                if "public_access" in check_id or "public_access_block" in check_id:
                    boost += 0.40
                if "public" in text and ("acl" in text or "policy" in text):
                    boost += 0.15
            if "encryption" in intents:
                if "secure_transport" in check_id or "https" in check_id:
                    boost += 0.25
                if "default_encryption" in check_id or "kms_encryption" in check_id:
                    boost += 0.25
            if "logging" in intents and ("cloudtrail" in text or "log" in text):
                boost += 0.10
            return boost

        def check_matches_intent(c: SelectedCheckContext, intent: str) -> bool:
            keywords = QUERY_INTENT_CLUSTERS.get(intent, [])
            text = " ".join(filter(None, [
                c.check_id, c.title, c.short_text,
                ensure_dict(c.metadata).get("description", ""),
            ])).lower()
            return any(kw in text for kw in keywords)

        sorted_candidates = sorted(
            candidates,
            key=lambda c: (intent_priority(c), score_of(c)),
            reverse=True,
        )

        # Pass 1: one representative per intent
        for intent in intents:
            if intent in covered_intents:
                continue
            best: Optional[SelectedCheckContext] = None
            for c in sorted_candidates:
                if c.check_id in selected_ids:
                    continue
                if check_matches_intent(c, intent):
                    best = c
                    break
            if best:
                selected.append(best)
                selected_ids.add(best.check_id)
                covered_intents.add(intent)
                if best.service:
                    covered_services.add(best.service.lower())

        # Pass 2: new service coverage
        for c in sorted_candidates:
            if len(selected) >= dynamic_target:
                break
            if c.check_id in selected_ids:
                continue
            svc = (c.service or "").lower()
            if svc and svc not in covered_services:
                selected.append(c)
                selected_ids.add(c.check_id)
                covered_services.add(svc)

        # Pass 3: fill by score
        for c in sorted_candidates:
            if len(selected) >= dynamic_target:
                break
            if c.check_id in selected_ids:
                continue
            selected.append(c)
            selected_ids.add(c.check_id)

        return selected

    # ============================================================
    # Target count helpers
    # ============================================================

    def target_check_count(
        self,
        consumer: str,
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
    ) -> int:
        if consumer == "planning":
            return 15
        return 3

    def target_capability_count(
        self,
        consumer: str,
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
    ) -> int:
        if consumer == "planning":
            return 1
        if consumer == "risk":
            return 3 if self._should_expand(confidence, review_recommended, warnings) else 2
        return 3

    def _should_expand(
        self,
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
    ) -> bool:
        if review_recommended:
            return True
        if confidence == Confidence.low:
            return True
        lowered = {w.lower() for w in warnings}
        return "ambiguous_top_results" in lowered or "low_score_top1" in lowered


def _strip_doc_prefix(identifier: str) -> str:
    """Strip 'check:' or 'capability:' prefix so IDs match metadata values."""
    for prefix in ("check:", "capability:"):
        if identifier.startswith(prefix):
            return identifier[len(prefix):]
    return identifier
