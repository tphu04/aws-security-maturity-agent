from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_score(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _metadata(result: Dict[str, Any]) -> Dict[str, Any]:
    return result.get("metadata", {}) or {}


def _top1(results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return results[0] if results else None


def verify_retrieval(
    route_info: Dict[str, Any],
    results: List[Dict[str, Any]],
    mapping_exists: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Verification layer for retrieval quality and business-alignment.

    Returns:
    {
        "valid": bool,
        "warnings": [...],
        "diagnostics": {...}
    }
    """
    warnings: List[str] = []
    diagnostics: Dict[str, Any] = {
        "result_count": len(results),
    }

    query_type = route_info.get("query_type")
    requires_exact = bool(route_info.get("requires_exact_lookup", False))
    exact_check_id = route_info.get("exact_check_id")
    expected_service = route_info.get("service")
    expected_domain = route_info.get("domain")
    expected_doc_types = set(route_info.get("doc_types", []) or [])

    if not results:
        if requires_exact:
            warnings.append("exact_lookup_miss")
        return {
            "valid": False,
            "warnings": warnings,
            "diagnostics": diagnostics,
        }

    top1 = _top1(results)
    top1_meta = _metadata(top1)
    top1_score = _safe_score(top1.get("score", 0.0))
    diagnostics["top1_score"] = top1_score

    # Exact hit integrity
    if requires_exact:
        matched_by = set(top1.get("matched_by", []) or [])
        if "exact_check_id" not in matched_by and "exact_mapping" not in matched_by:
            warnings.append("exact_lookup_miss")

        actual_check_id = top1_meta.get("check_id")
        if (
            exact_check_id
            and actual_check_id
            and str(actual_check_id).lower() != str(exact_check_id).lower()
        ):
            warnings.append("exact_lookup_mismatch")

    # Doc type alignment
    top1_doc_type = top1_meta.get("doc_type")
    diagnostics["top1_doc_type"] = top1_doc_type
    if expected_doc_types and top1_doc_type not in expected_doc_types:
        warnings.append("top1_doc_type_mismatch")

    # Service filter alignment
    if expected_service:
        actual_service = top1_meta.get("service")
        diagnostics["top1_service"] = actual_service
        if (
            actual_service
            and str(actual_service).lower() != str(expected_service).lower()
        ):
            warnings.append("service_mismatch_top1")
        if actual_service is None and query_type == "check_search":
            warnings.append("top1_filter_mismatch")

    # Domain alignment for maturity search
    if expected_domain and query_type == "maturity_search":
        actual_domain = top1_meta.get("domain")
        diagnostics["top1_domain"] = actual_domain
        if (
            actual_domain
            and str(actual_domain).strip().lower()
            != str(expected_domain).strip().lower()
        ):
            warnings.append("weak_domain_alignment")

    # Mapping presence when expected
    if (
        query_type in {"mapping_resolution", "context_build"}
        and mapping_exists is False
    ):
        warnings.append("mapping_missing")

    # Score floor
    if query_type == "check_search" and top1_score < 0.20:
        warnings.append("low_score_top1")
    elif query_type == "maturity_search" and top1_score < 0.15:
        warnings.append("low_score_top1")

    # Ambiguity: top1 too close to top2
    if len(results) > 1:
        top2_score = _safe_score(results[1].get("score", 0.0))
        diagnostics["top2_score"] = top2_score
        if (top1_score - top2_score) < 0.03:
            warnings.append("ambiguous_top_results")

    severe = {
        "exact_lookup_miss",
        "exact_lookup_mismatch",
        "mapping_missing",
        "top1_doc_type_mismatch",
        "top1_filter_mismatch",
    }

    valid = not any(code in severe for code in warnings)
    return {
        "valid": valid,
        "warnings": warnings,
        "diagnostics": diagnostics,
    }
