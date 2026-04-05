"""
Test suite for /v1/retrieve/maturity endpoint.

Tests maturity capability retrieval across multiple query styles:
  - exact capability_id lookup
  - keyword / exact phrase
  - paraphrase (semantic)
  - stage coverage (quickwins, foundational, ...)

Outputs JSON results to ./output/ for manual inspection.

Usage:
    # Start RAG server first, then:
    python run_test.py
    python run_test.py --base-url http://localhost:8080
"""
from __future__ import annotations

import argparse
import json
import sys
import time 
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
ENDPOINT = "/v1/retrieve/maturity"
TIMEOUT = 60
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
CASES: List[Dict[str, Any]] = [
    # ---- Exact capability_id lookup ----
    {
        "name": "exact_id__block_public_access",
        "category": "exact_id",
        "body": {"capability_id": "block_public_access", "top_k": 5, "debug": True},
        "expect_top1": "block_public_access",
    },
    {
        "name": "exact_id__detect_common_threats",
        "category": "exact_id",
        "body": {"capability_id": "detect_common_threats", "top_k": 5, "debug": True},
        "expect_top1": "detect_common_threats",
    },
    {
        "name": "exact_id__data_backups",
        "category": "exact_id",
        "body": {"capability_id": "data_backups", "top_k": 5, "debug": True},
        "expect_top1": "data_backups",
    },

    # ---- Keyword / exact phrase ----
    {
        "name": "keyword__block_public_access",
        "category": "keyword",
        "body": {"query": "block public access", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["block_public_access"],
    },
    {
        "name": "keyword__encryption_at_rest",
        "category": "keyword",
        "body": {"query": "encryption at rest", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["encryption_at_rest"],
    },
    {
        "name": "keyword__mfa",
        "category": "keyword",
        "body": {"query": "multi factor authentication MFA", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["enable_mfa"],
    },

    # ---- Semantic / paraphrase ----
    {
        "name": "semantic__prevent_public_exposure",
        "category": "semantic",
        "body": {"query": "prevent public exposure of cloud resources", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["block_public_access"],
    },
    {
        "name": "semantic__audit_api_calls",
        "category": "semantic",
        "body": {"query": "track and audit all API activity in the account", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["enable_logging_and_monitoring"],
    },
    {
        "name": "semantic__network_segmentation",
        "category": "semantic",
        "body": {"query": "isolate workloads with network segmentation", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["limit_network_access_using_security_groups"],
    },
    {
        "name": "semantic__protect_data_loss",
        "category": "semantic",
        "body": {"query": "protect against data loss with regular backups", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["data_backups"],
    },
    {
        "name": "semantic__least_privilege",
        "category": "semantic",
        "body": {"query": "apply least privilege principle to IAM policies", "top_k": 5, "debug": True},
    },

    # ---- Stage coverage (quickwins vs foundational) ----
    {
        "name": "stage__quickwins_billing",
        "category": "stage_coverage",
        "body": {"query": "billing alarms anomaly detection", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["billing_alarms_for_anomaly_detection"],
    },
    {
        "name": "stage__foundational_imds_v2",
        "category": "stage_coverage",
        "body": {"query": "enforce IMDSv2 on EC2 instances", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["instance_metadata_service_imds_v2"],
    },
    {
        "name": "stage__foundational_multi_az",
        "category": "stage_coverage",
        "body": {"query": "achieve redundancy across availability zones", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["achieve_redundancy_using_multiple_availability_zones"],
    },

    # ---- Retrieval mode comparison ----
    {
        "name": "mode_lexical__encryption",
        "category": "retrieval_mode",
        "body": {"query": "encryption at rest", "retrieval_mode": "lexical", "top_k": 5, "debug": True},
    },
    {
        "name": "mode_vector__encryption",
        "category": "retrieval_mode",
        "body": {"query": "encryption at rest", "retrieval_mode": "vector", "top_k": 5, "debug": True},
    },
    {
        "name": "mode_hybrid__encryption",
        "category": "retrieval_mode",
        "body": {"query": "encryption at rest", "retrieval_mode": "hybrid", "top_k": 5, "debug": True},
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def post(base_url: str, body: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{base_url}{ENDPOINT}"
    t0 = time.perf_counter()
    resp = requests.post(url, json=body, timeout=TIMEOUT)
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    try:
        data = resp.json()
    except Exception:
        data = {"_raw": resp.text}
    return {
        "http_status": resp.status_code,
        "latency_ms": latency_ms,
        "response": data,
    }


def extract_doc_ids(response: Dict[str, Any]) -> List[str]:
    results = response.get("response", {}).get("data", {}).get("results", [])
    ids = []
    for r in results:
        doc_id = r.get("doc_id", "")
        cap_id = r.get("metadata", {}).get("capability_id", "")
        ids.append(cap_id or doc_id or "<unknown>")
    return ids


def check_expectation(
    doc_ids: List[str],
    expect_top1: Optional[str] = None,
    expect_any_in_top5: Optional[List[str]] = None,
) -> Dict[str, Any]:
    lowered = [x.lower() for x in doc_ids]
    result: Dict[str, Any] = {"passed": True, "details": []}

    if expect_top1:
        hit = len(lowered) > 0 and expect_top1.lower() in lowered[0]
        result["details"].append(f"top1 contains '{expect_top1}': {'PASS' if hit else 'FAIL'}")
        if not hit:
            result["passed"] = False

    if expect_any_in_top5:
        hit = any(
            any(exp.lower() in lid for lid in lowered[:5])
            for exp in expect_any_in_top5
        )
        result["details"].append(f"any_in_top5={expect_any_in_top5}: {'PASS' if hit else 'FAIL'}")
        if not hit:
            result["passed"] = False

    return result


def print_case(case: Dict[str, Any], result: Dict[str, Any], verdict: Dict[str, Any]) -> None:
    status = "PASS" if verdict["passed"] else "FAIL"
    doc_ids = extract_doc_ids(result)
    meta = result["response"].get("meta", {})

    print(f"\n{'=' * 90}")
    print(f"[{status}] {case['name']}  ({case['category']})")
    print(f"  query/cap_id   : {case['body'].get('query') or case['body'].get('capability_id')}")
    print(f"  mode           : {case['body'].get('retrieval_mode', 'hybrid')}")
    print(f"  latency        : {result['latency_ms']} ms")
    print(f"  confidence     : {meta.get('confidence')}")
    print(f"  top_ids        : {doc_ids[:5]}")
    for d in verdict["details"]:
        print(f"  expectation    : {d}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(base_url: str) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    all_results: List[Dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    skip_count = 0

    print(f"Running {len(CASES)} test cases against {base_url}{ENDPOINT}\n")

    for case in CASES:
        try:
            result = post(base_url, case["body"])
        except requests.ConnectionError:
            print(f"\n[SKIP] {case['name']} — cannot connect to {base_url}")
            skip_count += 1
            continue

        doc_ids = extract_doc_ids(result)
        verdict = check_expectation(
            doc_ids,
            expect_top1=case.get("expect_top1"),
            expect_any_in_top5=case.get("expect_any_in_top5"),
        )
        print_case(case, result, verdict)

        if verdict["passed"]:
            pass_count += 1
        else:
            fail_count += 1

        all_results.append({
            "case": case["name"],
            "category": case["category"],
            "request": case["body"],
            "http_status": result["http_status"],
            "latency_ms": result["latency_ms"],
            "top_doc_ids": doc_ids[:5],
            "confidence": result["response"].get("meta", {}).get("confidence"),
            "passed": verdict["passed"],
            "expectation_details": verdict["details"],
            "full_response": result["response"],
        })

    # ---- Summary ----
    total = pass_count + fail_count + skip_count
    print(f"\n{'=' * 90}")
    print(f"SUMMARY: {pass_count}/{total} passed, {fail_count} failed, {skip_count} skipped")

    # ---- Save output ----
    report = {
        "endpoint": ENDPOINT,
        "base_url": base_url,
        "timestamp": timestamp,
        "summary": {
            "total": total,
            "passed": pass_count,
            "failed": fail_count,
            "skipped": skip_count,
        },
        "results": all_results,
    }

    out_file = OUTPUT_DIR / f"retrieve_maturity_{timestamp}.json"
    out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Output saved to: {out_file}")

    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test /v1/retrieve/maturity")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()
    sys.exit(run(args.base_url))
