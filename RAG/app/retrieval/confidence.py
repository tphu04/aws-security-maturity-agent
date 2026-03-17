from __future__ import annotations

from typing import Any, Dict, List, Tuple

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
    - exact check hit
    - top1 score magnitude
    - ambiguity gap between top1 and top2
    - verification penalties
    - route type
    """
    if not results:
        return Confidence.low

    query_type = route_info.get("query_type", "check_search")
    requires_exact = bool(route_info.get("requires_exact_lookup", False))
    top1, top2 = _top_scores(results)

    matched_by = results[0].get("matched_by", []) or []
    exact_hit = "exact_check_id" in matched_by or "exact_mapping" in matched_by

    # Base confidence by route + score
    if exact_hit:
        base = Confidence.high
    elif query_type == "mapping_resolution":
        base = Confidence.high if top1 >= 0.99 else Confidence.medium
    elif query_type == "check_search":
        if top1 >= 0.90:
            base = Confidence.high
        elif top1 >= 0.55:
            base = Confidence.medium
        else:
            base = Confidence.low
    elif query_type == "maturity_search":
        if top1 >= 0.75:
            base = Confidence.high
        elif top1 >= 0.45:
            base = Confidence.medium
        else:
            base = Confidence.low
    else:
        if top1 >= 0.80:
            base = Confidence.high
        elif top1 >= 0.50:
            base = Confidence.medium
        else:
            base = Confidence.low

    # Ambiguity penalty
    gap = top1 - top2
    if len(results) > 1 and gap < 0.05 and base == Confidence.high:
        base = Confidence.medium
    elif len(results) > 1 and gap < 0.02:
        base = Confidence.low

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
