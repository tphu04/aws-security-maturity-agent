"""
Test suite for /v1/context/build endpoint.

Tests context construction for the 3 consumer types:
  - planning  (PlanningBundle)
  - risk      (RiskBundle)
  - report    (ReportBundle)

Each consumer is tested with multiple scenarios (query-based, check_id-based,
findings-based, cross-service).

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
ENDPOINT = "/v1/context/build"
TIMEOUT = 60
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
CASES: List[Dict[str, Any]] = [
    # =======================================================================
    # PLANNING consumer
    # =======================================================================
    {
        "name": "planning__s3_public_access_query",
        "category": "planning",
        "body": {
            "consumer": "planning",
            "query": "s3 public access block",
            "service": "s3",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
            "debug": True,
        },
        "expect": {
            "has_bundle": "planning_bundle",
            "min_checks": 1,
        },
    },
    {
        "name": "planning__iam_mfa_check_ids",
        "category": "planning",
        "body": {
            "consumer": "planning",
            "check_ids": ["iam_root_hardware_mfa_enabled", "iam_root_mfa_totp_enabled"],
            "service": "iam",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
            "debug": True,
        },
        "expect": {
            "has_bundle": "planning_bundle",
            "min_checks": 1,
        },
    },
    {
        "name": "planning__ec2_security_query",
        "category": "planning",
        "body": {
            "consumer": "planning",
            "query": "ec2 security group unrestricted SSH access",
            "service": "ec2",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
            "debug": True,
        },
        "expect": {
            "has_bundle": "planning_bundle",
            "min_checks": 1,
        },
    },
    {
        "name": "planning__rds_multi_intent",
        "category": "planning",
        "body": {
            "consumer": "planning",
            "query": "rds public access and encryption",
            "service": "rds",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
            "debug": True,
        },
        "expect": {
            "has_bundle": "planning_bundle",
            "min_checks": 1,
        },
    },

    # =======================================================================
    # RISK consumer
    # =======================================================================
    {
        "name": "risk__s3_public_access_check_ids",
        "category": "risk",
        "body": {
            "consumer": "risk",
            "check_ids": ["s3_bucket_level_public_access_block"],
            "service": "s3",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
            "debug": True,
        },
        "expect": {
            "has_bundle": "risk_bundle",
            "has_primary_finding": True,
        },
    },
    {
        "name": "risk__s3_findings_based",
        "category": "risk",
        "body": {
            "consumer": "risk",
            "findings": [
                {
                    "check_id": "s3_bucket_level_public_access_block",
                    "service": "s3",
                    "status": "FAIL",
                    "severity": "high",
                },
            ],
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
            "debug": True,
        },
        "expect": {
            "has_bundle": "risk_bundle",
            "has_primary_finding": True,
        },
    },
    {
        "name": "risk__cloudtrail_query",
        "category": "risk",
        "body": {
            "consumer": "risk",
            "query": "cloudtrail not enabled in all regions",
            "service": "cloudtrail",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
            "debug": True,
        },
        "expect": {
            "has_bundle": "risk_bundle",
        },
    },
    {
        "name": "risk__iam_root_mfa",
        "category": "risk",
        "body": {
            "consumer": "risk",
            "check_ids": ["iam_root_hardware_mfa_enabled"],
            "service": "iam",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
            "debug": True,
        },
        "expect": {
            "has_bundle": "risk_bundle",
            "has_primary_finding": True,
        },
    },

    # =======================================================================
    # REPORT consumer
    # =======================================================================
    {
        "name": "report__s3_encryption_query",
        "category": "report",
        "body": {
            "consumer": "report",
            "query": "s3 encryption and access controls",
            "service": "s3",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
            "debug": True,
        },
        "expect": {
            "has_bundle": "report_bundle",
        },
    },
    {
        "name": "report__iam_broad_query",
        "category": "report",
        "body": {
            "consumer": "report",
            "query": "IAM security posture and access management",
            "service": "iam",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
            "debug": True,
        },
        "expect": {
            "has_bundle": "report_bundle",
        },
    },
    {
        "name": "report__multi_check_ids",
        "category": "report",
        "body": {
            "consumer": "report",
            "check_ids": [
                "s3_bucket_level_public_access_block",
                "s3_bucket_default_encryption",
                "s3_bucket_object_versioning",
            ],
            "service": "s3",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
            "debug": True,
        },
        "expect": {
            "has_bundle": "report_bundle",
            "min_checks": 2,
        },
    },

    # =======================================================================
    # Edge cases
    # =======================================================================
    {
        "name": "edge__no_mappings",
        "category": "edge",
        "body": {
            "consumer": "planning",
            "query": "s3 public access",
            "service": "s3",
            "include_mappings": False,
            "include_maturity": False,
            "top_k": 5,
            "debug": True,
        },
        "expect": {
            "has_bundle": "planning_bundle",
        },
    },
    {
        "name": "edge__small_top_k",
        "category": "edge",
        "body": {
            "consumer": "risk",
            "query": "s3 bucket encryption",
            "service": "s3",
            "top_k": 1,
            "debug": True,
        },
        "expect": {
            "has_bundle": "risk_bundle",
        },
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


def check_expectation(response: Dict[str, Any], expect: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {"passed": True, "details": []}
    if not expect:
        return result

    data = response.get("response", {}).get("data", {})
    payload = data.get("payload", {})
    diagnostics = data.get("diagnostics", {})

    # Check bundle exists
    bundle_key = expect.get("has_bundle")
    if bundle_key:
        bundle = payload.get(bundle_key)
        has = bundle is not None
        result["details"].append(f"has {bundle_key}: {'PASS' if has else 'FAIL'}")
        if not has:
            result["passed"] = False

    # Check primary_finding for risk
    if expect.get("has_primary_finding"):
        risk_bundle = payload.get("risk_bundle", {})
        pf = risk_bundle.get("primary_finding") if risk_bundle else None
        has = pf is not None
        result["details"].append(f"has primary_finding: {'PASS' if has else 'FAIL'}")
        if not has:
            result["passed"] = False

    # Check min selected checks
    min_checks = expect.get("min_checks")
    if min_checks is not None:
        selected = diagnostics.get("selected_checks", [])
        count = len(selected)
        ok = count >= min_checks
        result["details"].append(f"selected_checks >= {min_checks} (got {count}): {'PASS' if ok else 'FAIL'}")
        if not ok:
            result["passed"] = False

    return result


def summarize_bundle(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a compact summary of the context build response."""
    payload = data.get("payload", {})
    diagnostics = data.get("diagnostics", {})
    bundle_stats = diagnostics.get("bundle_stats", {})

    summary: Dict[str, Any] = {
        "consumer": data.get("consumer"),
        "status": None,
        "bundle_stats": bundle_stats,
        "selected_check_count": len(diagnostics.get("selected_checks", [])),
        "selected_mapping_count": len(diagnostics.get("selected_mappings", [])),
        "selected_capability_count": len(diagnostics.get("selected_capabilities", [])),
    }

    # Show which bundle is present
    for key in ["planning_bundle", "risk_bundle", "report_bundle"]:
        if payload.get(key):
            summary["bundle_type"] = key
            break

    return summary


def print_case(case: Dict[str, Any], result: Dict[str, Any], verdict: Dict[str, Any]) -> None:
    status_str = "PASS" if verdict["passed"] else "FAIL"
    data = result["response"].get("data", {})
    meta = result["response"].get("meta", {})
    bundle_summary = summarize_bundle(data)

    print(f"\n{'=' * 90}")
    print(f"[{status_str}] {case['name']}  ({case['category']})")
    print(f"  consumer       : {case['body']['consumer']}")
    print(f"  query/ids      : {case['body'].get('query') or case['body'].get('check_ids') or case['body'].get('findings')}")
    print(f"  service        : {case['body'].get('service', '-')}")
    print(f"  latency        : {result['latency_ms']} ms")
    print(f"  confidence     : {meta.get('confidence')}")
    print(f"  bundle_type    : {bundle_summary.get('bundle_type', '-')}")
    print(f"  checks/maps/caps: {bundle_summary['selected_check_count']}/{bundle_summary['selected_mapping_count']}/{bundle_summary['selected_capability_count']}")
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

        verdict = check_expectation(result, case.get("expect"))
        print_case(case, result, verdict)

        if verdict["passed"]:
            pass_count += 1
        else:
            fail_count += 1

        data = result["response"].get("data", {})
        all_results.append({
            "case": case["name"],
            "category": case["category"],
            "request": case["body"],
            "http_status": result["http_status"],
            "latency_ms": result["latency_ms"],
            "bundle_summary": summarize_bundle(data),
            "confidence": result["response"].get("meta", {}).get("confidence"),
            "passed": verdict["passed"],
            "expectation_details": verdict["details"],
            "full_response": result["response"],
        })

    # ---- Summary ----
    total = pass_count + fail_count + skip_count
    print(f"\n{'=' * 90}")
    print(f"SUMMARY: {pass_count}/{total} passed, {fail_count} failed, {skip_count} skipped")

    # Group by consumer
    for consumer in ["planning", "risk", "report", "edge"]:
        group = [r for r in all_results if r["category"] == consumer]
        if group:
            gp = sum(1 for r in group if r["passed"])
            print(f"  {consumer:10s}: {gp}/{len(group)} passed")

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

    out_file = OUTPUT_DIR / f"context_build_{timestamp}.json"
    out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Output saved to: {out_file}")

    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test /v1/context/build")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()
    sys.exit(run(args.base_url))
