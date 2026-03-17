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


def _normalize_identifier_like(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_ ")


def verify_retrieval(
    route_info: Dict[str, Any],
    results: List[Dict[str, Any]],
    mapping_exists: Optional[bool] = None,
) -> Dict[str, Any]:
    warnings: List[str] = []
    diagnostics: Dict[str, Any] = {
        "result_count": len(results),
    }

    query_type = route_info.get("query_type")
    requires_exact = bool(route_info.get("requires_exact_lookup", False))
    exact_check_id = route_info.get("exact_check_id")
    exact_capability_id = route_info.get("exact_capability_id")
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

    if requires_exact:
        matched_by = set(top1.get("matched_by", []) or [])
        if not (
            "exact_check_id" in matched_by
            or "exact_mapping" in matched_by
            or "exact_capability_id" in matched_by
        ):
            warnings.append("exact_lookup_miss")

        if exact_check_id:
            actual_check_id = top1_meta.get("check_id")
            if actual_check_id and _normalize_identifier_like(
                actual_check_id
            ) != _normalize_identifier_like(exact_check_id):
                warnings.append("exact_lookup_mismatch")

        if exact_capability_id:
            actual_capability_id = top1_meta.get("capability_id")
            if (
                actual_capability_id
                and _normalize_identifier_like(actual_capability_id)
                != _normalize_identifier_like(exact_capability_id)
                and not _normalize_identifier_like(actual_capability_id).startswith(
                    _normalize_identifier_like(exact_capability_id)
                )
                and not _normalize_identifier_like(actual_capability_id).endswith(
                    _normalize_identifier_like(exact_capability_id)
                )
            ):
                warnings.append("exact_lookup_mismatch")

    top1_doc_type = top1_meta.get("doc_type")
    diagnostics["top1_doc_type"] = top1_doc_type
    if expected_doc_types and top1_doc_type not in expected_doc_types:
        warnings.append("top1_doc_type_mismatch")

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

    if expected_domain and query_type == "maturity_search":
        actual_domain = top1_meta.get("domain")
        diagnostics["top1_domain"] = actual_domain
        if (
            actual_domain
            and str(actual_domain).strip().lower()
            != str(expected_domain).strip().lower()
        ):
            warnings.append("weak_domain_alignment")

    if (
        query_type in {"mapping_resolution", "context_build"}
        and mapping_exists is False
    ):
        warnings.append("mapping_missing")

    if len(results) > 1:
        top2_score = _safe_score(results[1].get("score", 0.0))
        diagnostics["top2_score"] = top2_score
        if abs(top1_score - top2_score) < 0.03:
            warnings.append("ambiguous_top_results")

    if top1_score < 0.20:
        warnings.append("low_score_top1")

    return {
        "valid": len(
            [
                w
                for w in warnings
                if w
                in {
                    "exact_lookup_miss",
                    "exact_lookup_mismatch",
                    "mapping_missing",
                    "top1_doc_type_mismatch",
                    "top1_filter_mismatch",
                }
            ]
        )
        == 0,
        "warnings": warnings,
        "diagnostics": diagnostics,
    }
