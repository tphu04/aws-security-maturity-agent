"""
Test suite for /v1/retrieve/checks endpoint.

Tests check retrieval across multiple query styles:
  - exact check_id lookup
  - keyword / exact phrase
  - paraphrase (semantic)
  - cross-service coverage

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
ENDPOINT = "/v1/retrieve/checks"
TIMEOUT = 60
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
CASES: List[Dict[str, Any]] = [
    # ---- Exact check_id lookup ----
    {
        "name": "exact_id__s3_public_access_block",
        "category": "exact_id",
        "body": {"check_id": "s3_bucket_level_public_access_block", "top_k": 5, "debug": True},
        "expect_top1": "s3_bucket_level_public_access_block",
    },
    {
        "name": "exact_id__iam_root_mfa",
        "category": "exact_id",
        "body": {"check_id": "iam_root_hardware_mfa_enabled", "top_k": 5, "debug": True},
        "expect_top1": "iam_root_hardware_mfa_enabled",
    },
    {
        "name": "exact_id__cloudtrail_enabled",
        "category": "exact_id",
        "body": {"check_id": "cloudtrail_multi_region_enabled", "top_k": 5, "debug": True},
        "expect_top1": "cloudtrail_multi_region_enabled",
    },

    # ---- Keyword / exact phrase ----
    {
        "name": "keyword__s3_encryption",
        "category": "keyword",
        "body": {"query": "s3 encryption", "service": "s3", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["s3_bucket_default_encryption", "s3_bucket_object_lock"],
    },
    {
        "name": "keyword__rds_public",
        "category": "keyword",
        "body": {"query": "rds publicly accessible", "service": "rds", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["rds_instance_no_public_access"],
    },
    {
        "name": "keyword__iam_access_key_rotation",
        "category": "keyword",
        "body": {"query": "iam access key rotation", "service": "iam", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["iam_rotate_access_key_90_days"],
    },

    # ---- Paraphrase / semantic ----
    {
        "name": "semantic__prevent_public_s3",
        "category": "semantic",
        "body": {"query": "how to prevent an s3 bucket from being publicly exposed", "top_k": 5, "debug": True},
        "expect_any_in_top5": [
            "s3_bucket_level_public_access_block",
            "s3_account_level_public_access_blocks",
            "s3_bucket_public_access",
        ],
    },
    {
        "name": "semantic__protect_database_internet",
        "category": "semantic",
        "body": {"query": "protect database instances from internet access", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["rds_instance_no_public_access"],
    },
    {
        "name": "semantic__logging_audit_trail",
        "category": "semantic",
        "body": {"query": "ensure we have an audit trail for all API calls", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["cloudtrail_multi_region_enabled"],
    },
    {
        "name": "semantic__encrypt_data_at_rest",
        "category": "semantic",
        "body": {"query": "encrypt data at rest for block storage volumes", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["ec2_ebs_default_encryption", "ec2_ebs_volume_encryption"],
    },

    # ---- Cross-service coverage ----
    {
        "name": "cross__ec2_security_group",
        "category": "cross_service",
        "body": {"query": "security group allows unrestricted SSH", "service": "ec2", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22"],
    },
    {
        "name": "cross__kms_key_rotation",
        "category": "cross_service",
        "body": {"query": "kms key rotation enabled", "service": "kms", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["kms_cmk_rotation_enabled"],
    },
    {
        "name": "cross__lambda_runtime",
        "category": "cross_service",
        "body": {"query": "lambda function using outdated runtime", "service": "awslambda", "top_k": 5, "debug": True},
        "expect_any_in_top5": ["awslambda_function_using_supported_runtimes"],
    },

    # ---- Retrieval mode comparison ----
    {
        "name": "mode_lexical__s3_versioning",
        "category": "retrieval_mode",
        "body": {"query": "s3 versioning", "retrieval_mode": "lexical", "top_k": 5, "debug": True},
    },
    {
        "name": "mode_vector__s3_versioning",
        "category": "retrieval_mode",
        "body": {"query": "s3 versioning", "retrieval_mode": "vector", "top_k": 5, "debug": True},
    },
    {
        "name": "mode_hybrid__s3_versioning",
        "category": "retrieval_mode",
        "body": {"query": "s3 versioning", "retrieval_mode": "hybrid", "top_k": 5, "debug": True},
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
        raw = r.get("doc_id") or r.get("metadata", {}).get("check_id", "<unknown>")
        ids.append(raw.removeprefix("check:"))
    return ids


def check_expectation(
    doc_ids: List[str],
    expect_top1: Optional[str] = None,
    expect_any_in_top5: Optional[List[str]] = None,
) -> Dict[str, Any]:
    lowered = [x.lower() for x in doc_ids]
    result: Dict[str, Any] = {"passed": True, "details": []}

    if expect_top1:
        hit = len(lowered) > 0 and expect_top1.lower() == lowered[0]
        result["details"].append(f"top1={expect_top1}: {'PASS' if hit else 'FAIL'}")
        if not hit:
            result["passed"] = False

    if expect_any_in_top5:
        hit = any(e.lower() in lowered[:5] for e in expect_any_in_top5)
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
    print(f"  query/check_id : {case['body'].get('query') or case['body'].get('check_id')}")
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

    out_file = OUTPUT_DIR / f"retrieve_checks_{timestamp}.json"
    out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Output saved to: {out_file}")

    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test /v1/retrieve/checks")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()
    sys.exit(run(args.base_url))
