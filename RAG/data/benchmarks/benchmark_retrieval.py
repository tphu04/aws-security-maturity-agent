"""
Benchmark retrieval quality for RAG service.

Supports:
- Loading test cases from external JSON (benchmark_cases.json)
- Inline fallback cases for backward compatibility
- New metrics: forbidden_capability_rate, service_precision, mapping_false_positive_rate
- Per-service and per-category breakdowns
- JSON diff-able report output
"""

from __future__ import annotations

import json
import statistics
import sys
import io
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# Ensure UTF-8 output on Windows (Vietnamese queries in benchmark)
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.evaluation.metrics import (
    compute_average_precision,
    compute_confidence_calibration,
    compute_latency_percentiles,
    compute_ndcg,
    compute_reciprocal_rank,
    compute_robustness_gap,
)

BASE_URL = "http://localhost:8000"
TOP_K = 5
TIMEOUT = 30

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "benchmark_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CASES_FILE = SCRIPT_DIR / "benchmark_cases.json"

CHECKS_ENDPOINT = f"{BASE_URL}/v1/retrieve/checks"
MATURITY_ENDPOINT = f"{BASE_URL}/v1/retrieve/maturity"


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------

def _load_cases_from_file() -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load test cases from benchmark_cases.json."""
    if not CASES_FILE.exists():
        raise FileNotFoundError(f"Benchmark cases file not found: {CASES_FILE}")

    with CASES_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    check_cases = data.get("check_cases", [])
    maturity_cases = data.get("maturity_cases", [])

    # Normalize: ensure case_id field exists (map from 'id' if needed)
    for case in check_cases + maturity_cases:
        if "case_id" not in case and "id" in case:
            case["case_id"] = case["id"]

    return check_cases, maturity_cases


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _post_json(url: str, payload: Dict[str, Any]) -> tuple[int, Dict[str, Any], float]:
    start = time.perf_counter()
    response = requests.post(url, json=payload, timeout=TIMEOUT)
    latency_ms = (time.perf_counter() - start) * 1000.0

    try:
        body = response.json()
    except Exception:
        body = {"_raw_text": response.text}

    return response.status_code, body, latency_ms


def _extract_doc_ids(results: List[Dict[str, Any]]) -> List[str]:
    return [str(item.get("doc_id", "")) for item in results if item.get("doc_id")]


def _top1_service(results: List[Dict[str, Any]]) -> Optional[str]:
    if not results:
        return None
    meta = results[0].get("metadata", {}) or {}
    service = meta.get("service")
    return str(service) if service is not None else None


def _extract_diagnostics(body: Dict[str, Any]) -> Dict[str, Any]:
    meta = body.get("meta", {}) or {}
    diagnostics = meta.get("diagnostics", {}) or {}

    results = body.get("results", []) or body.get("data", {}).get("results", []) or []
    matched_by_values: List[str] = []
    for item in results:
        for source in item.get("matched_by", []) or []:
            matched_by_values.append(str(source).lower())

    if "used_vector" not in diagnostics:
        diagnostics["used_vector"] = any(v == "vector" for v in matched_by_values)

    if "used_hybrid" not in diagnostics:
        diagnostics["used_hybrid"] = any(v == "bm25" for v in matched_by_values) and any(
            v == "vector" for v in matched_by_values
        )

    if "retrieval_mode" not in diagnostics:
        diagnostics["retrieval_mode"] = meta.get("retrieval_mode", "unknown")

    for key in [
        "lexical_candidate_count", "vector_candidate_count",
        "top_lexical_doc_ids", "top_vector_doc_ids",
        "vector_error", "corpus", "collection_name",
    ]:
        if key not in diagnostics:
            diagnostics[key] = None

    return diagnostics


def _normalize_results(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(body.get("results"), list):
        return body["results"]
    data = body.get("data", {})
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data["results"]
    return []


def _extract_confidence(body: Dict[str, Any]) -> Optional[str]:
    meta = body.get("meta", {}) or {}
    confidence = meta.get("confidence")
    return str(confidence) if confidence is not None else None


def _extract_status(body: Dict[str, Any]) -> Optional[str]:
    status = body.get("status")
    return str(status) if status is not None else None


def _extract_verification(body: Dict[str, Any]) -> Dict[str, Any]:
    meta = body.get("meta", {}) or {}
    verification = meta.get("verification", {}) or {}
    return verification if isinstance(verification, dict) else {}


def _extract_index_version(body: Dict[str, Any]) -> Optional[str]:
    meta = body.get("meta", {}) or {}
    val = meta.get("index_version")
    return str(val) if val is not None else None


def _build_payload(query: str) -> Dict[str, Any]:
    return {
        "query": query,
        "top_k": TOP_K,
        "retrieval_mode": "hybrid",
        "debug": True,
    }


# ---------------------------------------------------------------------------
# Forbidden capability checking
# ---------------------------------------------------------------------------

def _check_forbidden_capabilities(
    results: List[Dict[str, Any]],
    forbidden_ids: List[str],
) -> Dict[str, Any]:
    """Check if any top-K results contain forbidden capability IDs."""
    if not forbidden_ids:
        return {"has_forbidden": False, "forbidden_found": []}

    found: List[str] = []
    for result in results[:TOP_K]:
        meta = result.get("metadata", {}) or {}
        cap_id = str(meta.get("capability_id", "") or "")
        if cap_id in forbidden_ids:
            found.append(cap_id)

    return {
        "has_forbidden": len(found) > 0,
        "forbidden_found": found,
    }


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def _infer_route_type(endpoint: str) -> str:
    """Infer route type from endpoint URL for calibration analysis."""
    if "/checks" in endpoint:
        return "check_search"
    if "/maturity" in endpoint:
        return "maturity_search"
    return "unknown"


def evaluate_cases(
    endpoint: str,
    cases: List[Dict[str, Any]],
    report_name: str,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    route_type = _infer_route_type(endpoint)

    for idx, case in enumerate(cases, start=1):
        case_id = case.get("case_id", case.get("id", f"case_{idx}"))
        payload = _build_payload(case["query"])
        status_code, body, latency_ms = _post_json(endpoint, payload)

        results = _normalize_results(body)
        top_ids = _extract_doc_ids(results)
        diagnostics = _extract_diagnostics(body)
        verification = _extract_verification(body)
        top1_service = _top1_service(results)

        expected_doc_id = case.get("expected_doc_id")
        expected_capability_id = case.get("expected_capability_id")
        expected_service = case.get("expected_service")
        forbidden_ids = case.get("forbidden_capability_ids", [])

        hit_top1 = False
        hit_top3 = False
        hit_top5 = False

        if expected_doc_id:
            hit_top1 = len(top_ids) >= 1 and top_ids[0] == expected_doc_id
            hit_top3 = expected_doc_id in top_ids[:3]
            hit_top5 = expected_doc_id in top_ids[:5]
        elif expected_capability_id:
            capability_hits = []
            for result in results[:5]:
                meta = result.get("metadata", {}) or {}
                capability_hits.append(str(meta.get("capability_id", "")))
            hit_top1 = len(capability_hits) >= 1 and capability_hits[0] == expected_capability_id
            hit_top3 = expected_capability_id in capability_hits[:3]
            hit_top5 = expected_capability_id in capability_hits[:5]

        # Forbidden capability check
        forbidden_result = _check_forbidden_capabilities(results, forbidden_ids)

        # Per-query evaluation metrics (Task 1.2)
        # Determine retrieved list & ground truth based on case type
        if expected_doc_id:
            _retrieved_for_metrics = top_ids
            _relevant_for_metrics = [expected_doc_id]
        elif expected_capability_id:
            _retrieved_for_metrics = [
                str((r.get("metadata") or {}).get("capability_id", ""))
                for r in results[:TOP_K]
            ]
            _relevant_for_metrics = [expected_capability_id]
        else:
            _retrieved_for_metrics = top_ids
            _relevant_for_metrics = []

        _rr = compute_reciprocal_rank(_retrieved_for_metrics, _relevant_for_metrics)
        _ndcg5 = compute_ndcg(_retrieved_for_metrics, _relevant_for_metrics, k=5)
        _ap5 = compute_average_precision(_retrieved_for_metrics, _relevant_for_metrics, k=5)

        # Reranker lift metrics (Task 3.2)
        pre_order = diagnostics.get("reranker_pre_order", [])
        post_order = diagnostics.get("reranker_post_order", [])
        _reranker_applied = diagnostics.get("reranker_applied", False)

        if pre_order and post_order and _relevant_for_metrics:
            _reranker_mrr_before = compute_reciprocal_rank(pre_order, _relevant_for_metrics)
            _reranker_mrr_after = compute_reciprocal_rank(post_order, _relevant_for_metrics)
            _reranker_ndcg_before = compute_ndcg(pre_order, _relevant_for_metrics, k=5)
            _reranker_ndcg_after = compute_ndcg(post_order, _relevant_for_metrics, k=5)
        else:
            _reranker_mrr_before = None
            _reranker_mrr_after = None
            _reranker_ndcg_before = None
            _reranker_ndcg_after = None

        row = {
            "case_index": idx,
            "case_id": case_id,
            "route_type": route_type,
            "category": case.get("category", "unknown"),
            "service": case.get("service"),
            "query": case["query"],
            "http_status": status_code,
            "response_status": _extract_status(body),
            "latency_ms": round(latency_ms, 2),
            "hit_top1": hit_top1,
            "hit_top3": hit_top3,
            "hit_top5": hit_top5,
            "top1_doc_id": top_ids[0] if top_ids else None,
            "top_ids": top_ids[:TOP_K],
            "top1_service": top1_service,
            "expected_doc_id": expected_doc_id,
            "expected_capability_id": expected_capability_id,
            "expected_service": expected_service,
            "top1_correct_service": top1_service == expected_service if expected_service else None,
            "forbidden_capability_ids": forbidden_ids,
            "has_forbidden_in_results": forbidden_result["has_forbidden"],
            "forbidden_found": forbidden_result["forbidden_found"],
            "confidence": _extract_confidence(body),
            "review_recommended": (body.get("meta", {}) or {}).get("review_recommended"),
            "warnings": verification.get("warnings", []),
            "verification": verification,
            "index_version": _extract_index_version(body),
            "reciprocal_rank": _rr,
            "ndcg@5": _ndcg5,
            "ap@5": _ap5,
            "reranker_applied": _reranker_applied,
            "reranker_mrr_before": _reranker_mrr_before,
            "reranker_mrr_after": _reranker_mrr_after,
            "reranker_ndcg_before": _reranker_ndcg_before,
            "reranker_ndcg_after": _reranker_ndcg_after,
            "reranker_mrr_lift": (
                round(_reranker_mrr_after - _reranker_mrr_before, 4)
                if _reranker_mrr_before is not None else None
            ),
            "reranker_ndcg_lift": (
                round(_reranker_ndcg_after - _reranker_ndcg_before, 4)
                if _reranker_ndcg_before is not None else None
            ),
            "diagnostics": {
                "retrieval_mode": diagnostics.get("retrieval_mode"),
                "corpus": diagnostics.get("corpus"),
                "collection_name": diagnostics.get("collection_name"),
                "lexical_candidate_count": diagnostics.get("lexical_candidate_count"),
                "vector_candidate_count": diagnostics.get("vector_candidate_count"),
                "top_lexical_doc_ids": diagnostics.get("top_lexical_doc_ids"),
                "top_vector_doc_ids": diagnostics.get("top_vector_doc_ids"),
                "used_vector": diagnostics.get("used_vector"),
                "used_hybrid": diagnostics.get("used_hybrid"),
                "vector_error": diagnostics.get("vector_error"),
            },
            "raw_response": body,
        }
        rows.append(row)

    summary = summarize_rows(rows, report_name=report_name)

    report = {
        "report_name": report_name,
        "base_url": BASE_URL,
        "endpoint": endpoint,
        "top_k": TOP_K,
        "requested_retrieval_mode": "hybrid",
        "total_cases": len(rows),
        "summary": summary,
        "cases": rows,
    }

    output_path = OUTPUT_DIR / f"{report_name}.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[saved] {output_path}")

    return report


def summarize_rows(rows: List[Dict[str, Any]], report_name: str) -> Dict[str, Any]:
    total = len(rows)
    http_200 = sum(1 for row in rows if row["http_status"] == 200)
    top1 = sum(1 for row in rows if row["hit_top1"])
    top3 = sum(1 for row in rows if row["hit_top3"])
    top5 = sum(1 for row in rows if row["hit_top5"])
    vector_visible = sum(1 for row in rows if row["diagnostics"].get("used_vector"))
    hybrid_visible = sum(1 for row in rows if row["diagnostics"].get("used_hybrid"))
    service_top1 = sum(
        1 for row in rows if row.get("top1_correct_service") is True
    )
    latencies = [row["latency_ms"] for row in rows]

    # New metrics: forbidden capability rate
    cases_with_forbidden_spec = [
        row for row in rows if row.get("forbidden_capability_ids")
    ]
    forbidden_violations = sum(
        1 for row in cases_with_forbidden_spec if row.get("has_forbidden_in_results")
    )
    forbidden_capability_rate = (
        round(forbidden_violations / len(cases_with_forbidden_spec) * 100, 1)
        if cases_with_forbidden_spec
        else 0.0
    )

    # New metrics: service precision (top-1 service correctness)
    cases_with_service = [
        row for row in rows if row.get("expected_service") is not None
    ]
    service_correct = sum(
        1 for row in cases_with_service if row.get("top1_correct_service") is True
    )
    service_precision = (
        round(service_correct / len(cases_with_service) * 100, 1)
        if cases_with_service
        else None
    )

    # By category
    by_category: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        category = row["category"]
        bucket = by_category.setdefault(
            category,
            {
                "total": 0,
                "top1": 0,
                "top3": 0,
                "top5": 0,
                "vector": 0,
                "hybrid": 0,
                "forbidden_violations": 0,
                "avg_latency_ms": [],
                "_rr_values": [],
                "_ndcg5_values": [],
            },
        )
        bucket["total"] += 1
        bucket["top1"] += 1 if row["hit_top1"] else 0
        bucket["top3"] += 1 if row["hit_top3"] else 0
        bucket["top5"] += 1 if row["hit_top5"] else 0
        bucket["vector"] += 1 if row["diagnostics"].get("used_vector") else 0
        bucket["hybrid"] += 1 if row["diagnostics"].get("used_hybrid") else 0
        if row.get("has_forbidden_in_results"):
            bucket["forbidden_violations"] += 1
        bucket["avg_latency_ms"].append(row["latency_ms"])
        bucket["_rr_values"].append(row["reciprocal_rank"])
        bucket["_ndcg5_values"].append(row["ndcg@5"])

    for category, bucket in by_category.items():
        bucket["avg_latency_ms"] = round(
            statistics.mean(bucket["avg_latency_ms"]), 2
        ) if bucket["avg_latency_ms"] else None
        # Per-category top1_rate, MRR, NDCG@5
        bucket["top1_rate"] = round(
            bucket["top1"] / bucket["total"], 4
        ) if bucket["total"] else 0.0
        bucket["mrr"] = round(
            statistics.mean(bucket["_rr_values"]), 4
        ) if bucket["_rr_values"] else 0.0
        bucket["ndcg@5"] = round(
            statistics.mean(bucket["_ndcg5_values"]), 4
        ) if bucket["_ndcg5_values"] else 0.0
        # Clean up temporary accumulators
        del bucket["_rr_values"]
        del bucket["_ndcg5_values"]

    # By service
    by_service: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        svc = row.get("service") or "unknown"
        bucket = by_service.setdefault(
            svc,
            {
                "total": 0,
                "top1": 0,
                "top3": 0,
                "top5": 0,
                "forbidden_violations": 0,
                "service_correct": 0,
            },
        )
        bucket["total"] += 1
        bucket["top1"] += 1 if row["hit_top1"] else 0
        bucket["top3"] += 1 if row["hit_top3"] else 0
        bucket["top5"] += 1 if row["hit_top5"] else 0
        if row.get("has_forbidden_in_results"):
            bucket["forbidden_violations"] += 1
        if row.get("top1_correct_service") is True:
            bucket["service_correct"] += 1

    # Failures
    failures = [
        {
            "case_id": row["case_id"],
            "category": row["category"],
            "service": row.get("service"),
            "query": row["query"],
            "expected_doc_id": row["expected_doc_id"],
            "expected_capability_id": row["expected_capability_id"],
            "top_ids": row["top_ids"],
            "confidence": row["confidence"],
            "warnings": row["warnings"],
            "has_forbidden_in_results": row.get("has_forbidden_in_results", False),
            "forbidden_found": row.get("forbidden_found", []),
            "diagnostics": row["diagnostics"],
        }
        for row in rows
        if not row["hit_top5"]
    ]

    # Forbidden violations detail
    forbidden_detail = [
        {
            "case_id": row["case_id"],
            "query": row["query"],
            "forbidden_found": row["forbidden_found"],
        }
        for row in rows
        if row.get("has_forbidden_in_results")
    ]

    # Aggregate retrieval metrics (Task 1.2)
    rr_values = [row["reciprocal_rank"] for row in rows]
    ndcg5_values = [row["ndcg@5"] for row in rows]
    ap5_values = [row["ap@5"] for row in rows]

    mrr = round(statistics.mean(rr_values), 4) if rr_values else 0.0
    ndcg5 = round(statistics.mean(ndcg5_values), 4) if ndcg5_values else 0.0
    map5 = round(statistics.mean(ap5_values), 4) if ap5_values else 0.0
    latency_percentiles = compute_latency_percentiles(latencies)
    robustness_gap = compute_robustness_gap(by_category, metric_key="top1_rate")

    # Aggregate reranker lift (Task 3.2)
    rows_with_reranker = [r for r in rows if r.get("reranker_mrr_before") is not None]
    if rows_with_reranker:
        reranker_lift = {
            "mrr_before": round(statistics.mean(
                r["reranker_mrr_before"] for r in rows_with_reranker), 4),
            "mrr_after": round(statistics.mean(
                r["reranker_mrr_after"] for r in rows_with_reranker), 4),
            "mrr_lift": round(statistics.mean(
                r["reranker_mrr_lift"] for r in rows_with_reranker), 4),
            "ndcg_before": round(statistics.mean(
                r["reranker_ndcg_before"] for r in rows_with_reranker), 4),
            "ndcg_after": round(statistics.mean(
                r["reranker_ndcg_after"] for r in rows_with_reranker), 4),
            "ndcg_lift": round(statistics.mean(
                r["reranker_ndcg_lift"] for r in rows_with_reranker), 4),
            "cases_with_data": len(rows_with_reranker),
            "cases_improved": sum(
                1 for r in rows_with_reranker if r["reranker_mrr_lift"] > 0),
            "cases_degraded": sum(
                1 for r in rows_with_reranker if r["reranker_mrr_lift"] < 0),
            "cases_unchanged": sum(
                1 for r in rows_with_reranker if r["reranker_mrr_lift"] == 0),
        }
    else:
        reranker_lift = None

    # Confidence calibration (Task 5.1)
    calibration_cases = [
        {"confidence": row["confidence"], "hit_top1": row["hit_top1"]}
        for row in rows
        if row.get("confidence") is not None
    ]
    confidence_calibration = compute_confidence_calibration(calibration_cases)

    summary = {
        "report_name": report_name,
        "total_cases": total,
        "http_200": http_200,
        "hit_expected_in_top1": top1,
        "hit_expected_in_top3": top3,
        "hit_expected_in_top5": top5,
        "top1_correct_service": service_top1 if any(
            row.get("top1_correct_service") is not None for row in rows
        ) else None,
        "vector_visible_cases": vector_visible,
        "hybrid_visible_cases": hybrid_visible,
        "average_latency_ms": round(statistics.mean(latencies), 2) if latencies else None,
        "median_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
        "mrr": mrr,
        "ndcg@5": ndcg5,
        "map@5": map5,
        "latency_percentiles": latency_percentiles,
        "robustness_gap": robustness_gap,
        "reranker_lift": reranker_lift,
        "confidence_calibration": confidence_calibration,
        "forbidden_capability_rate_pct": forbidden_capability_rate,
        "service_precision_pct": service_precision,
        "by_category": by_category,
        "by_service": by_service,
        "failures_top5": failures,
        "forbidden_violations": forbidden_detail,
    }

    return summary


def print_report(report: Dict[str, Any]) -> None:
    summary = report["summary"]
    print("=" * 100)
    print(report["report_name"].upper())
    print("=" * 100)
    print(f"Base URL               : {report['base_url']}")
    print(f"Endpoint               : {report['endpoint']}")
    print(f"Requested mode         : {report['requested_retrieval_mode']}")
    print(f"Total cases            : {summary['total_cases']}")
    print(f"HTTP 200               : {summary['http_200']}/{summary['total_cases']}")
    print(f"Hit expected in Top 1  : {summary['hit_expected_in_top1']}/{summary['total_cases']}")
    print(f"Hit expected in Top 3  : {summary['hit_expected_in_top3']}/{summary['total_cases']}")
    print(f"Hit expected in Top 5  : {summary['hit_expected_in_top5']}/{summary['total_cases']}")
    if summary["top1_correct_service"] is not None:
        print(
            f"Top1 correct service   : {summary['top1_correct_service']}/{summary['total_cases']}"
        )
    print(f"Vector visible cases   : {summary['vector_visible_cases']}/{summary['total_cases']}")
    print(f"Hybrid visible cases   : {summary['hybrid_visible_cases']}/{summary['total_cases']}")
    print(f"Average latency        : {summary['average_latency_ms']} ms")
    print(f"Median latency         : {summary['median_latency_ms']} ms")

    # Retrieval quality metrics
    print(f"MRR                    : {summary.get('mrr', 'N/A')}")
    print(f"NDCG@5                 : {summary.get('ndcg@5', 'N/A')}")
    print(f"MAP@5                  : {summary.get('map@5', 'N/A')}")

    lat_p = summary.get("latency_percentiles", {})
    if lat_p:
        print(f"Latency P50/P90/P99    : {lat_p.get('p50_ms')} / {lat_p.get('p90_ms')} / {lat_p.get('p99_ms')} ms")

    gap = summary.get("robustness_gap", {})
    if gap and gap.get("best_category"):
        print(f"Robustness gap         : {gap['gap_pp']} pp"
              f" (best={gap['best_category']} {gap['best_value']:.2f},"
              f" worst={gap['worst_category']} {gap['worst_value']:.2f})")

    # Reranker lift
    rl = summary.get("reranker_lift")
    if rl:
        print(f"\nReranker Lift ({rl['cases_with_data']} cases):")
        print(f"  MRR  : {rl['mrr_before']:.4f} -> {rl['mrr_after']:.4f}"
              f"  (lift {rl['mrr_lift']:+.4f})")
        print(f"  NDCG : {rl['ndcg_before']:.4f} -> {rl['ndcg_after']:.4f}"
              f"  (lift {rl['ndcg_lift']:+.4f})")
        print(f"  Cases: {rl['cases_improved']} improved,"
              f" {rl['cases_degraded']} degraded,"
              f" {rl['cases_unchanged']} unchanged")

    # Confidence calibration
    cal = summary.get("confidence_calibration", {})
    if cal and cal.get("total_cases", 0) > 0:
        print(f"\nConfidence Calibration (ECE: {cal.get('ece', '?')}):")
        print(f"  {'Level':<10} {'Count':>6} {'Accuracy':>10} {'Expected':>16} {'Calibrated':>12}")
        print(f"  {'-' * 54}")
        for level in ("high", "medium", "low"):
            b = cal.get(level, {})
            cnt = b.get("count", 0)
            acc = f"{b['actual_accuracy']:.2%}" if b.get("actual_accuracy") is not None else "—"
            if level == "high":
                exp = f">= {b.get('expected_min', 0.8):.0%}"
            elif level == "medium":
                exp = f"{b.get('expected_min', 0.5):.0%}-{b.get('expected_max', 0.8):.0%}"
            else:
                exp = f"< {b.get('expected_max', 0.5):.0%}"
            cal_flag = {True: "Yes", False: "NO", None: "N/A"}.get(b.get("calibrated"), "N/A")
            print(f"  {level:<10} {cnt:>6} {acc:>10} {exp:>16} {cal_flag:>12}")
        print(f"  Overall calibrated   : {cal.get('overall_calibrated', 'N/A')}")

    # Forbidden / service metrics
    print(f"Forbidden cap. rate    : {summary['forbidden_capability_rate_pct']}%"
          f" (target: 0%)")
    if summary["service_precision_pct"] is not None:
        print(f"Service precision      : {summary['service_precision_pct']}%"
              f" (target: >= 90%)")

    print("\nBy category:")
    for category, bucket in summary["by_category"].items():
        forbidden_str = f" forbidden={bucket['forbidden_violations']}" if bucket["forbidden_violations"] else ""
        mrr_str = f" mrr={bucket.get('mrr', 'N/A')}"
        ndcg_str = f" ndcg@5={bucket.get('ndcg@5', 'N/A')}"
        print(
            f"  - {category:<14} total={bucket['total']:<2} "
            f"top1={bucket['top1']:<2} top3={bucket['top3']:<2} top5={bucket['top5']:<2} "
            f"vector={bucket['vector']:<2} hybrid={bucket['hybrid']:<2} "
            f"avg_latency={bucket['avg_latency_ms']} ms{mrr_str}{ndcg_str}{forbidden_str}"
        )

    print("\nBy service:")
    for svc, bucket in summary["by_service"].items():
        svc_str = f" svc_correct={bucket['service_correct']}/{bucket['total']}" if bucket.get("service_correct") else ""
        print(
            f"  - {svc:<12} total={bucket['total']:<2} "
            f"top1={bucket['top1']:<2} top3={bucket['top3']:<2} top5={bucket['top5']:<2}"
            f"{svc_str}"
        )

    # Forbidden violations
    forbidden_detail = summary.get("forbidden_violations", [])
    if forbidden_detail:
        print("\n" + "-" * 100)
        print("FORBIDDEN CAPABILITY VIOLATIONS")
        print("-" * 100)
        for item in forbidden_detail:
            print(f"  [{item['case_id']}] query: {item['query']}")
            print(f"    forbidden found: {item['forbidden_found']}")
        print("-" * 100)

    failures = summary["failures_top5"]
    if failures:
        print("\n" + "-" * 100)
        print("TOP5 FAILURES")
        print("-" * 100)
        for item in failures:
            svc_label = f" [{item.get('service', '?')}]" if item.get("service") else ""
            print(f"[{item['category']}]{svc_label} {item['case_id']}")
            print(f"  query          : {item['query']}")
            if item["expected_doc_id"]:
                print(f"  expected_doc_id: {item['expected_doc_id']}")
            if item["expected_capability_id"]:
                print(f"  expected_cap   : {item['expected_capability_id']}")
            print(f"  top_ids        : {item['top_ids']}")
            print(f"  confidence     : {item['confidence']}")
            if item.get("has_forbidden_in_results"):
                print(f"  FORBIDDEN FOUND: {item['forbidden_found']}")
            print(f"  diagnostics    : {json.dumps(item['diagnostics'], ensure_ascii=False)}")
            print("-" * 100)


def main() -> None:
    # Load cases from external file
    check_cases, maturity_cases = _load_cases_from_file()
    print(f"[benchmark] Loaded {len(check_cases)} check cases, {len(maturity_cases)} maturity cases from {CASES_FILE.name}")

    checks_report = evaluate_cases(
        endpoint=CHECKS_ENDPOINT,
        cases=check_cases,
        report_name="benchmark_checks_report",
    )
    print_report(checks_report)

    print("\n")

    maturity_report = evaluate_cases(
        endpoint=MATURITY_ENDPOINT,
        cases=maturity_cases,
        report_name="benchmark_maturity_report",
    )
    print_report(maturity_report)

    # Print combined summary
    print("\n" + "=" * 100)
    print("COMBINED SUMMARY")
    print("=" * 100)
    total_checks = checks_report["summary"]["total_cases"]
    total_maturity = maturity_report["summary"]["total_cases"]
    total = total_checks + total_maturity

    combined_top1 = (
        checks_report["summary"]["hit_expected_in_top1"]
        + maturity_report["summary"]["hit_expected_in_top1"]
    )
    combined_top5 = (
        checks_report["summary"]["hit_expected_in_top5"]
        + maturity_report["summary"]["hit_expected_in_top5"]
    )
    combined_forbidden = (
        len(checks_report["summary"].get("forbidden_violations", []))
        + len(maturity_report["summary"].get("forbidden_violations", []))
    )

    print(f"Total cases            : {total}")
    print(f"Combined Top-1 hit     : {combined_top1}/{total} ({round(combined_top1/total*100,1)}%)")
    print(f"Combined Top-5 hit     : {combined_top5}/{total} ({round(combined_top5/total*100,1)}%)")
    print(f"Forbidden violations   : {combined_forbidden}")
    print(f"Services covered       : 6 (s3, iam, ec2, rds, cloudtrail, kms)")
    print("=" * 100)


if __name__ == "__main__":
    main()
