from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.core.config import load_scoring_config
from app.core.models import Confidence


def _safe_score(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _top_scores(results: List[Dict[str, Any]]) -> Tuple[float, float]:
    if not results:
        return 0.0, 0.0
    top1 = _safe_score(results[0].get("score", 0.0))
    top2 = _safe_score(results[1].get("score", 0.0)) if len(results) > 1 else 0.0
    return top1, top2


def calculate_confidence(
    results: List[Dict[str, Any]],
    route_info: Dict[str, Any],
    verification: Dict[str, Any],
) -> Confidence:
    """
    Route-aware confidence estimation.

    Signals considered:
    - exact hit
    - top1 score
    - ambiguity gap between top1 and top2
    - verification penalties
    - route type
    """
    if not results:
        return Confidence.low

    scoring = load_scoring_config()
    thresholds = scoring["confidence_thresholds"]
    ambiguity = scoring["ambiguity"]

    query_type = route_info.get("query_type", "check_search")
    requires_exact = bool(route_info.get("requires_exact_lookup", False))
    top1, top2 = _top_scores(results)

    matched_by = results[0].get("matched_by", []) or []
    exact_hit = (
        "exact_check_id" in matched_by
        or "exact_mapping" in matched_by
        or "exact_capability_id" in matched_by
    )

    # Base confidence by route + score
    if exact_hit:
        base = Confidence.high
    elif query_type in thresholds:
        t = thresholds[query_type]
        if top1 >= t["high"]:
            base = Confidence.high
        elif "medium" in t and top1 >= t["medium"]:
            base = Confidence.medium
        else:
            base = Confidence.low
    else:
        t = thresholds["default"]
        if top1 >= t["high"]:
            base = Confidence.high
        elif top1 >= t["medium"]:
            base = Confidence.medium
        else:
            base = Confidence.low

    # Ambiguity penalty — exact-lookup queries use absolute gap,
    # NL queries use ratio-based approach.
    if requires_exact:
        gap = top1 - top2
        if len(results) > 1 and gap < ambiguity["gap_high_to_medium"] and base == Confidence.high:
            base = Confidence.medium
        elif len(results) > 1 and gap < ambiguity["gap_to_low"]:
            base = Confidence.low
    else:
        # Ratio-based ambiguity for NL queries.
        # Absolute gap is unreliable when reranker produces tight score clusters.
        # Ratio (top2/top1) is scale-invariant: 0.98 means "top-2 is 98% of top-1".
        nl_ratio_threshold = ambiguity.get("nl_ratio_high_to_medium", 0.98)
        if len(results) > 1 and top1 > 0 and base == Confidence.high:
            score_ratio = top2 / top1
            if score_ratio >= nl_ratio_threshold:
                base = Confidence.medium

    # Exact required but no exact hit
    if requires_exact and not exact_hit:
        if base == Confidence.high:
            base = Confidence.medium
        else:
            base = Confidence.low

    # Verification penalties
    if verification.get("valid") is False:
        return Confidence.low

    warnings = verification.get("warnings", []) or []
    severe_warning_codes = {
        "exact_lookup_miss",
        "exact_lookup_mismatch",
        "mapping_missing",
        "top1_doc_type_mismatch",
        "top1_filter_mismatch",
    }
    moderate_warning_codes = {
        "service_mismatch_top1",
        "low_score_top1",
        "ambiguous_top_results",
        "weak_domain_alignment",
    }

    if any(code in severe_warning_codes for code in warnings):
        return Confidence.low

    if any(code in moderate_warning_codes for code in warnings):
        if base == Confidence.high:
            return Confidence.medium
        return Confidence.low if base == Confidence.low else Confidence.medium

    return base
