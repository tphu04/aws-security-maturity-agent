from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "http://localhost:8000"
TOP_K = 5
TIMEOUT = 30

OUTPUT_DIR = Path("benchmark_outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CHECKS_ENDPOINT = f"{BASE_URL}/v1/retrieve/checks"
MATURITY_ENDPOINT = f"{BASE_URL}/v1/retrieve/maturity"


CHECK_CASES: List[Dict[str, Any]] = [
    # exact
    {
        "id": "checks_exact_check_id_1",
        "category": "exact",
        "query": "s3_bucket_level_public_access_block",
        "expected_doc_id": "check:s3_bucket_level_public_access_block",
        "expected_service": "s3",
    },
    {
        "id": "checks_exact_check_id_2",
        "category": "exact",
        "query": "s3_account_level_public_access_blocks",
        "expected_doc_id": "check:s3_account_level_public_access_blocks",
        "expected_service": "s3",
    },
    {
        "id": "checks_exact_check_id_3",
        "category": "exact",
        "query": "s3_bucket_public_write_acl",
        "expected_doc_id": "check:s3_bucket_public_write_acl",
        "expected_service": "s3",
    },
    {
        "id": "checks_exact_check_id_4",
        "category": "exact",
        "query": "s3_bucket_public_list_acl",
        "expected_doc_id": "check:s3_bucket_public_list_acl",
        "expected_service": "s3",
    },
    {
        "id": "checks_exact_check_id_5",
        "category": "exact",
        "query": "s3_bucket_policy_public_write_access",
        "expected_doc_id": "check:s3_bucket_policy_public_write_access",
        "expected_service": "s3",
    },
    # paraphrase
    {
        "id": "checks_paraphrase_1",
        "category": "paraphrase",
        "query": "how to prevent an s3 bucket from being publicly exposed",
        "expected_doc_id": "check:s3_bucket_level_public_access_block",
        "expected_service": "s3",
    },
    {
        "id": "checks_paraphrase_2",
        "category": "paraphrase",
        "query": "stop public access to aws object storage",
        "expected_doc_id": "check:s3_account_level_public_access_blocks",
        "expected_service": "s3",
    },
    {
        "id": "checks_paraphrase_3",
        "category": "paraphrase",
        "query": "prevent anonymous users from accessing bucket data",
        "expected_doc_id": "check:s3_bucket_policy_public_write_access",
        "expected_service": "s3",
    },
    {
        "id": "checks_paraphrase_4",
        "category": "paraphrase",
        "query": "make sure users cannot upload files publicly to s3",
        "expected_doc_id": "check:s3_bucket_public_write_acl",
        "expected_service": "s3",
    },
    {
        "id": "checks_paraphrase_5",
        "category": "paraphrase",
        "query": "avoid public listing of files in object storage buckets",
        "expected_doc_id": "check:s3_bucket_public_list_acl",
        "expected_service": "s3",
    },
    # risk
    {
        "id": "checks_risk_1",
        "category": "risk",
        "query": "misconfiguration that allows public reads on cloud storage",
        "expected_doc_id": "check:s3_bucket_level_public_access_block",
        "expected_service": "s3",
    },
    {
        "id": "checks_risk_2",
        "category": "risk",
        "query": "security issue when bucket objects are publicly accessible",
        "expected_doc_id": "check:s3_account_level_public_access_blocks",
        "expected_service": "s3",
    },
    {
        "id": "checks_risk_3",
        "category": "risk",
        "query": "how to avoid accidental public exposure of files in s3",
        "expected_doc_id": "check:s3_bucket_level_public_access_block",
        "expected_service": "s3",
    },
    {
        "id": "checks_risk_4",
        "category": "risk",
        "query": "publicly writable bucket through acl misconfiguration",
        "expected_doc_id": "check:s3_bucket_public_write_acl",
        "expected_service": "s3",
    },
    {
        "id": "checks_risk_5",
        "category": "risk",
        "query": "anyone can enumerate objects in the bucket",
        "expected_doc_id": "check:s3_bucket_public_list_acl",
        "expected_service": "s3",
    },
    # semantic hard
    {
        "id": "checks_semantic_hard_1",
        "category": "semantic_hard",
        "query": "make object storage private by default",
        "expected_doc_id": "check:s3_account_level_public_access_blocks",
        "expected_service": "s3",
    },
    {
        "id": "checks_semantic_hard_2",
        "category": "semantic_hard",
        "query": "avoid outsiders browsing files in cloud buckets",
        "expected_doc_id": "check:s3_bucket_public_list_acl",
        "expected_service": "s3",
    },
    {
        "id": "checks_semantic_hard_3",
        "category": "semantic_hard",
        "query": "prevent world-readable bucket objects",
        "expected_doc_id": "check:s3_bucket_level_public_access_block",
        "expected_service": "s3",
    },
    {
        "id": "checks_semantic_hard_4",
        "category": "semantic_hard",
        "query": "stop unauthenticated access to bucket contents",
        "expected_doc_id": "check:s3_bucket_policy_public_write_access",
        "expected_service": "s3",
    },
    {
        "id": "checks_semantic_hard_5",
        "category": "semantic_hard",
        "query": "keep cloud file storage inaccessible to the public",
        "expected_doc_id": "check:s3_account_level_public_access_blocks",
        "expected_service": "s3",
    },
]

MATURITY_CASES: List[Dict[str, Any]] = [
    # exact
    {
        "id": "maturity_exact_1",
        "category": "exact",
        "query": "block_public_access",
        "expected_capability_id": "block_public_access",
        "expected_doc_id": "capability:block_public_access",
    },
    {
        "id": "maturity_exact_2",
        "category": "exact",
        "query": "audit_api_calls",
        "expected_capability_id": "audit_api_calls",
        "expected_doc_id": "capability:audit_api_calls",
    },
    {
        "id": "maturity_exact_3",
        "category": "exact",
        "query": "data_backups",
        "expected_capability_id": "data_backups",
        "expected_doc_id": "capability:data_backups",
    },
    {
        "id": "maturity_exact_4",
        "category": "exact",
        "query": "encryption_at_rest",
        "expected_capability_id": "encryption_at_rest",
        "expected_doc_id": "capability:encryption_at_rest",
    },
    {
        "id": "maturity_exact_5",
        "category": "exact",
        "query": "network_segmentation",
        "expected_capability_id": "network_segmentation",
        "expected_doc_id": "capability:network_segmentation",
    },
    # paraphrase
    {
        "id": "maturity_paraphrase_1",
        "category": "paraphrase",
        "query": "practice to stop public access to resources",
        "expected_capability_id": "block_public_access",
    },
    {
        "id": "maturity_paraphrase_2",
        "category": "paraphrase",
        "query": "ability to record and monitor api activity",
        "expected_capability_id": "audit_api_calls",
    },
    {
        "id": "maturity_paraphrase_3",
        "category": "paraphrase",
        "query": "capability for recovering data from backups",
        "expected_capability_id": "data_backups",
    },
    {
        "id": "maturity_paraphrase_4",
        "category": "paraphrase",
        "query": "protect stored data with encryption",
        "expected_capability_id": "encryption_at_rest",
    },
    {
        "id": "maturity_paraphrase_5",
        "category": "paraphrase",
        "query": "separate networks to reduce exposure",
        "expected_capability_id": "network_segmentation",
    },
    # semantic hard
    {
        "id": "maturity_semantic_hard_1",
        "category": "semantic_hard",
        "query": "control internet-facing access to storage services",
        "expected_capability_id": "block_public_access",
    },
    {
        "id": "maturity_semantic_hard_2",
        "category": "semantic_hard",
        "query": "know who called cloud apis and when",
        "expected_capability_id": "audit_api_calls",
    },
    {
        "id": "maturity_semantic_hard_3",
        "category": "semantic_hard",
        "query": "restore critical information after loss or corruption",
        "expected_capability_id": "data_backups",
    },
    {
        "id": "maturity_semantic_hard_4",
        "category": "semantic_hard",
        "query": "make stolen storage media unreadable",
        "expected_capability_id": "encryption_at_rest",
    },
    {
        "id": "maturity_semantic_hard_5",
        "category": "semantic_hard",
        "query": "limit blast radius by isolating network zones",
        "expected_capability_id": "network_segmentation",
    },
]


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

    # Fallback compatibility for older APIs
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

    if "lexical_candidate_count" not in diagnostics:
        diagnostics["lexical_candidate_count"] = None
    if "vector_candidate_count" not in diagnostics:
        diagnostics["vector_candidate_count"] = None
    if "top_lexical_doc_ids" not in diagnostics:
        diagnostics["top_lexical_doc_ids"] = None
    if "top_vector_doc_ids" not in diagnostics:
        diagnostics["top_vector_doc_ids"] = None
    if "vector_error" not in diagnostics:
        diagnostics["vector_error"] = None
    if "corpus" not in diagnostics:
        diagnostics["corpus"] = None
    if "collection_name" not in diagnostics:
        diagnostics["collection_name"] = None

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


def evaluate_cases(
    endpoint: str,
    cases: List[Dict[str, Any]],
    report_name: str,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []

    for idx, case in enumerate(cases, start=1):
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

        row = {
            "case_index": idx,
            "case_id": case["id"],
            "category": case["category"],
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
            "confidence": _extract_confidence(body),
            "review_recommended": (body.get("meta", {}) or {}).get("review_recommended"),
            "warnings": verification.get("warnings", []),
            "verification": verification,
            "index_version": _extract_index_version(body),
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
                "avg_latency_ms": [],
            },
        )
        bucket["total"] += 1
        bucket["top1"] += 1 if row["hit_top1"] else 0
        bucket["top3"] += 1 if row["hit_top3"] else 0
        bucket["top5"] += 1 if row["hit_top5"] else 0
        bucket["vector"] += 1 if row["diagnostics"].get("used_vector") else 0
        bucket["hybrid"] += 1 if row["diagnostics"].get("used_hybrid") else 0
        bucket["avg_latency_ms"].append(row["latency_ms"])

    for category, bucket in by_category.items():
        bucket["avg_latency_ms"] = round(
            statistics.mean(bucket["avg_latency_ms"]), 2
        ) if bucket["avg_latency_ms"] else None

    failures = [
        {
            "case_id": row["case_id"],
            "category": row["category"],
            "query": row["query"],
            "expected_doc_id": row["expected_doc_id"],
            "expected_capability_id": row["expected_capability_id"],
            "top_ids": row["top_ids"],
            "confidence": row["confidence"],
            "warnings": row["warnings"],
            "diagnostics": row["diagnostics"],
        }
        for row in rows
        if not row["hit_top5"]
    ]

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
        "by_category": by_category,
        "failures_top5": failures,
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

    print("\nBy category:")
    for category, bucket in summary["by_category"].items():
        print(
            f"  - {category:<14} total={bucket['total']:<2} "
            f"top1={bucket['top1']:<2} top3={bucket['top3']:<2} top5={bucket['top5']:<2} "
            f"vector={bucket['vector']:<2} hybrid={bucket['hybrid']:<2} "
            f"avg_latency={bucket['avg_latency_ms']} ms"
        )

    failures = summary["failures_top5"]
    if failures:
        print("\n" + "-" * 100)
        print("TOP5 FAILURES")
        print("-" * 100)
        for item in failures:
            print(f"[{item['category']}] {item['case_id']}")
            print(f"query          : {item['query']}")
            if item["expected_doc_id"]:
                print(f"expected_doc_id: {item['expected_doc_id']}")
            if item["expected_capability_id"]:
                print(f"expected_cap   : {item['expected_capability_id']}")
            print(f"top_ids        : {item['top_ids']}")
            print(f"confidence     : {item['confidence']}")
            print(f"warnings       : {item['warnings']}")
            print(f"diagnostics    : {json.dumps(item['diagnostics'], ensure_ascii=False)}")
            print("-" * 100)


def main() -> None:
    checks_report = evaluate_cases(
        endpoint=CHECKS_ENDPOINT,
        cases=CHECK_CASES,
        report_name="benchmark_checks_report",
    )
    print_report(checks_report)

    print("\n")

    maturity_report = evaluate_cases(
        endpoint=MATURITY_ENDPOINT,
        cases=MATURITY_CASES,
        report_name="benchmark_maturity_report",
    )
    print_report(maturity_report)


if __name__ == "__main__":
    main()