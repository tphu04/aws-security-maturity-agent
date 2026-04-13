"""
Benchmark Tầng 2 + 3: Field Accuracy & Context Completeness.

Tầng 2 — RiskEvaluation flow:
    build_context(consumer="risk", check_ids=[...])
    → severity đúng? title đúng? mapping có? confidence hợp lý?

Tầng 3 — Report flow:
    build_context(consumer="report", check_ids=[...])
    → key_findings đủ? risk_summary có nội dung? themes có? practices có?

Also covers PlanningAgent flow:
    build_context(consumer="planning", query="...")
    → related_findings non-empty? severity populated? service correct?
"""

from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# UTF-8 output for Vietnamese text
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_URL = "http://localhost:8000"
CONTEXT_ENDPOINT = f"{BASE_URL}/v1/context/build"
TIMEOUT = 30

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "benchmark_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ================================================================
# Test Case Definitions
# ================================================================

TIER2_CASES: List[Dict[str, Any]] = [
    # --- RiskEvaluation agent: check_id → correct fields ---
    # S3
    {
        "case_id": "risk_field_01",
        "consumer": "risk",
        "check_ids": ["s3_bucket_public_access"],
        "expect": {
            "primary_severity": "critical",
            "primary_title_contains": "s3 bucket",
            "has_mapping": True,
            "mapping_capability_ids": ["block_public_access"],
        },
    },
    {
        "case_id": "risk_field_02",
        "consumer": "risk",
        "check_ids": ["s3_bucket_default_encryption"],
        "expect": {
            "primary_severity": "medium",
            "primary_title_contains": "encryption",
            "has_mapping": True,
            "mapping_capability_ids": ["data_encryption_at_rest"],
        },
    },
    {
        "case_id": "risk_field_03",
        "consumer": "risk",
        "check_ids": ["s3_bucket_secure_transport_policy"],
        "expect": {
            "primary_severity": "medium",
            "primary_title_contains": "transport",
            "has_mapping": True,
            "mapping_capability_ids": ["encryption_in_transit"],
        },
    },
    # IAM
    {
        "case_id": "risk_field_04",
        "consumer": "risk",
        "check_ids": ["iam_root_mfa_enabled"],
        "expect": {
            "primary_severity": "critical",
            "primary_title_contains": "mfa",
            "has_mapping": True,
        },
    },
    {
        "case_id": "risk_field_05",
        "consumer": "risk",
        "check_ids": ["iam_no_root_access_key"],
        "expect": {
            "primary_severity": "critical",
            "primary_title_contains": "root",
            "has_mapping": True,
        },
    },
    {
        "case_id": "risk_field_06",
        "consumer": "risk",
        "check_ids": ["iam_avoid_root_usage"],
        "expect": {
            "primary_severity": "critical",
            "primary_title_contains": "root",
            "has_mapping": True,
            "mapping_capability_ids": ["root_account_protection"],
        },
    },
    {
        "case_id": "risk_field_07",
        "consumer": "risk",
        "check_ids": ["iam_password_policy_minimum_length_14"],
        "expect": {
            "primary_severity": "medium",
            "primary_title_contains": "password",
            "has_mapping": True,
        },
    },
    # EC2
    {
        "case_id": "risk_field_08",
        "consumer": "risk",
        "check_ids": ["ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22"],
        "expect": {
            "primary_severity": "high",
            "primary_title_contains": "security group",
            "has_mapping": True,
            "mapping_capability_ids": ["cleanup_risky_open_admin_ports_in_security_groups"],
        },
    },
    {
        "case_id": "risk_field_09",
        "consumer": "risk",
        "check_ids": ["ec2_ebs_default_encryption"],
        "expect": {
            "primary_severity": "medium",
            "primary_title_contains": "encryption",
            "has_mapping": True,
            "mapping_capability_ids": ["data_encryption_at_rest"],
        },
    },
    {
        "case_id": "risk_field_10",
        "consumer": "risk",
        "check_ids": ["ec2_launch_template_imdsv2_required"],
        "expect": {
            "primary_severity": "high",
            "primary_title_contains": "imdsv2",
            "has_mapping": True,
            "mapping_capability_ids": ["instance_metadata_service_imds_v2"],
        },
    },
    # RDS
    {
        "case_id": "risk_field_11",
        "consumer": "risk",
        "check_ids": ["rds_instance_no_public_access"],
        "expect": {
            "primary_severity": "critical",
            "primary_title_contains": "public",
            "has_mapping": True,
            "mapping_capability_ids": ["block_public_access"],
        },
    },
    {
        "case_id": "risk_field_12",
        "consumer": "risk",
        "check_ids": ["rds_instance_storage_encrypted"],
        "expect": {
            "primary_severity": "medium",
            "primary_title_contains": "encrypt",
            "has_mapping": True,
        },
    },
    # CloudTrail
    {
        "case_id": "risk_field_13",
        "consumer": "risk",
        "check_ids": ["cloudtrail_multi_region_enabled"],
        "expect": {
            "primary_severity": "high",
            "primary_title_contains": "cloudtrail",
            "has_mapping": True,
        },
    },
    # GuardDuty
    {
        "case_id": "risk_field_14",
        "consumer": "risk",
        "check_ids": ["guardduty_is_enabled"],
        "expect": {
            "primary_severity": "high",
            "primary_title_contains": "guardduty",
            "has_mapping": True,
            "mapping_capability_ids": ["detect_common_threats"],
        },
    },
    # KMS
    {
        "case_id": "risk_field_15",
        "consumer": "risk",
        "check_ids": ["kms_cmk_rotation_enabled"],
        "expect": {
            "primary_severity": "medium",
            "primary_title_contains": "rotation",
            "has_mapping": True,
        },
    },
    # --- Batch check_ids (RiskEval batches 20+ findings) ---
    {
        "case_id": "risk_batch_01",
        "consumer": "risk",
        "check_ids": [
            "s3_bucket_public_access",
            "iam_root_mfa_enabled",
            "ec2_ebs_default_encryption",
        ],
        "expect": {
            "primary_severity": "critical",  # highest severity first
            "has_mapping": True,
            "min_related_findings": 2,
        },
    },
    # --- PlanningAgent: NL query → correct fields ---
    {
        "case_id": "plan_field_01",
        "consumer": "planning",
        "query": "s3 public access check",
        "expect": {
            "min_related_findings": 3,
            "findings_have_severity": True,
            "findings_have_service": True,
            "expected_service_in_findings": "s3",
        },
    },
    {
        "case_id": "plan_field_02",
        "consumer": "planning",
        "query": "iam root access",
        "expect": {
            "min_related_findings": 2,
            "findings_have_severity": True,
            "expected_service_in_findings": "iam",
        },
    },
    {
        "case_id": "plan_field_03",
        "consumer": "planning",
        "query": "ec2 security group open ports",
        "expect": {
            "min_related_findings": 2,
            "findings_have_severity": True,
            "expected_service_in_findings": "ec2",
        },
    },
    {
        "case_id": "plan_field_04",
        "consumer": "planning",
        "query": "rds storage encryption",
        "expect": {
            "min_related_findings": 1,
            "findings_have_severity": True,
            "expected_service_in_findings": "rds",
        },
    },
    {
        "case_id": "plan_field_05",
        "consumer": "planning",
        "query": "kiểm tra xem S3 bucket có bị public access không",
        "expect": {
            "min_related_findings": 2,
            "findings_have_severity": True,
            "expected_service_in_findings": "s3",
        },
    },
    # ---- NEW: Risk field cases (more services) ----
    {
        "case_id": "risk_field_16",
        "consumer": "risk",
        "check_ids": ["vpc_flow_logs_enabled"],
        "expect": {
            "primary_severity": "medium",
            "primary_title_contains": "flow log",
            "has_mapping": True,
        },
    },
    {
        "case_id": "risk_field_17",
        "consumer": "risk",
        "check_ids": ["awslambda_function_no_secrets_in_code"],
        "expect": {
            "primary_severity": "critical",
            "primary_title_contains": "secret",
            "has_mapping": True,
        },
    },
    {
        "case_id": "risk_field_18",
        "consumer": "risk",
        "check_ids": ["secretsmanager_automatic_rotation_enabled"],
        "expect": {
            "primary_severity": "medium",
            "primary_title_contains": "rotation",
            "has_mapping": True,
        },
    },
    {
        "case_id": "risk_field_19",
        "consumer": "risk",
        "check_ids": ["cloudfront_distributions_https_enabled"],
        "expect": {
            "primary_severity": "medium",
            "primary_title_contains": "https",
            "has_mapping": True,
        },
    },
    {
        "case_id": "risk_field_20",
        "consumer": "risk",
        "check_ids": ["s3_bucket_object_versioning"],
        "expect": {
            "primary_severity": "low",
            "primary_title_contains": "version",
            "has_mapping": True,
        },
    },
    # ---- NEW: Larger batch risk ----
    {
        "case_id": "risk_batch_02",
        "consumer": "risk",
        "check_ids": [
            "iam_root_mfa_enabled",
            "iam_no_root_access_key",
            "iam_avoid_root_usage",
            "iam_password_policy_minimum_length_14",
            "iam_user_mfa_enabled_console_access",
        ],
        "expect": {
            "primary_severity": "critical",
            "has_mapping": True,
            "min_related_findings": 3,
        },
    },
    # ---- NEW: Planning agent (more services + Vietnamese) ----
    {
        "case_id": "plan_field_06",
        "consumer": "planning",
        "query": "cloudtrail logging audit",
        "expect": {
            "min_related_findings": 2,
            "findings_have_severity": True,
            "expected_service_in_findings": "cloudtrail",
        },
    },
    {
        "case_id": "plan_field_07",
        "consumer": "planning",
        "query": "kms key rotation encryption",
        "expect": {
            "min_related_findings": 1,
            "findings_have_severity": True,
            "expected_service_in_findings": "kms",
        },
    },
    {
        "case_id": "plan_field_08",
        "consumer": "planning",
        "query": "guardduty threat detection enabled",
        "expect": {
            "min_related_findings": 1,
            "findings_have_severity": True,
            "expected_service_in_findings": "guardduty",
        },
    },
    {
        "case_id": "plan_vi_01",
        "consumer": "planning",
        "query": "tài khoản root chưa bật MFA bảo vệ",
        "expect": {
            "min_related_findings": 2,
            "findings_have_severity": True,
            "expected_service_in_findings": "iam",
        },
    },
    {
        "case_id": "plan_vi_02",
        "consumer": "planning",
        "query": "RDS database đang bị public access từ ngoài",
        "expect": {
            "min_related_findings": 1,
            "findings_have_severity": True,
            "expected_service_in_findings": "rds",
        },
    },
    {
        "case_id": "plan_vi_03",
        "consumer": "planning",
        "query": "security group đang mở port SSH ra ngoài internet",
        "expect": {
            "min_related_findings": 2,
            "findings_have_severity": True,
            "expected_service_in_findings": "ec2",
        },
    },
]

TIER3_CASES: List[Dict[str, Any]] = [
    # --- ReportAgent: check_ids → complete context ---
    {
        "case_id": "report_ctx_01",
        "consumer": "report",
        "check_ids": ["s3_bucket_public_access"],
        "expect": {
            "min_key_findings": 1,
            "key_findings_have_risk_summary": True,
            "min_control_themes": 1,
            "min_recommended_practices": 1,
            "has_primary_topics": True,
        },
    },
    {
        "case_id": "report_ctx_02",
        "consumer": "report",
        "check_ids": ["iam_root_mfa_enabled"],
        "expect": {
            "min_key_findings": 1,
            "key_findings_have_risk_summary": True,
            "min_control_themes": 1,
        },
    },
    {
        "case_id": "report_ctx_03",
        "consumer": "report",
        "check_ids": ["ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22"],
        "expect": {
            "min_key_findings": 1,
            "key_findings_have_risk_summary": True,
            "min_control_themes": 1,
            "min_recommended_practices": 1,
        },
    },
    {
        "case_id": "report_ctx_04",
        "consumer": "report",
        "check_ids": ["rds_instance_no_public_access"],
        "expect": {
            "min_key_findings": 1,
            "key_findings_have_risk_summary": True,
        },
    },
    {
        "case_id": "report_ctx_05",
        "consumer": "report",
        "check_ids": ["cloudtrail_multi_region_enabled"],
        "expect": {
            "min_key_findings": 1,
            "key_findings_have_risk_summary": True,
            "min_control_themes": 1,
        },
    },
    # --- Multi-check batch (real report scenario) ---
    {
        "case_id": "report_batch_01",
        "consumer": "report",
        "check_ids": [
            "s3_bucket_public_access",
            "iam_root_mfa_enabled",
            "ec2_ebs_default_encryption",
            "rds_instance_no_public_access",
            "cloudtrail_multi_region_enabled",
        ],
        "expect": {
            "min_key_findings": 4,
            "key_findings_have_risk_summary": True,
            "min_control_themes": 2,
            "min_recommended_practices": 2,
            "has_primary_topics": True,
        },
    },
    {
        "case_id": "report_batch_02",
        "consumer": "report",
        "check_ids": [
            "ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22",
            "ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_3389",
            "ec2_instance_public_ip",
        ],
        "expect": {
            "min_key_findings": 2,
            "key_findings_have_risk_summary": True,
            "has_primary_topics": True,
        },
    },
    # ---- NEW: Single-check for more services ----
    {
        "case_id": "report_ctx_06",
        "consumer": "report",
        "check_ids": ["guardduty_is_enabled"],
        "expect": {
            "min_key_findings": 1,
            "key_findings_have_risk_summary": True,
        },
    },
    {
        "case_id": "report_ctx_07",
        "consumer": "report",
        "check_ids": ["kms_cmk_rotation_enabled"],
        "expect": {
            "min_key_findings": 1,
            "key_findings_have_risk_summary": True,
        },
    },
    {
        "case_id": "report_ctx_08",
        "consumer": "report",
        "check_ids": ["vpc_flow_logs_enabled"],
        "expect": {
            "min_key_findings": 1,
            "key_findings_have_risk_summary": True,
        },
    },
    {
        "case_id": "report_ctx_09",
        "consumer": "report",
        "check_ids": ["awslambda_function_no_secrets_in_code"],
        "expect": {
            "min_key_findings": 1,
            "key_findings_have_risk_summary": True,
        },
    },
    {
        "case_id": "report_ctx_10",
        "consumer": "report",
        "check_ids": ["secretsmanager_automatic_rotation_enabled"],
        "expect": {
            "min_key_findings": 1,
            "key_findings_have_risk_summary": True,
        },
    },
    # ---- NEW: Batch scenarios (realistic report) ----
    {
        "case_id": "report_batch_03",
        "consumer": "report",
        "check_ids": [
            "iam_root_mfa_enabled",
            "iam_no_root_access_key",
            "iam_avoid_root_usage",
        ],
        "expect": {
            "min_key_findings": 2,
            "key_findings_have_risk_summary": True,
            "min_control_themes": 1,
            "has_primary_topics": True,
        },
    },
    {
        "case_id": "report_batch_04",
        "consumer": "report",
        "check_ids": [
            "s3_bucket_default_encryption",
            "ec2_ebs_default_encryption",
            "rds_instance_storage_encrypted",
            "kms_cmk_rotation_enabled",
        ],
        "expect": {
            "min_key_findings": 3,
            "key_findings_have_risk_summary": True,
            "min_control_themes": 1,
            "has_primary_topics": True,
        },
    },
    # --- Edge: nonexistent check_id ---
    {
        "case_id": "report_neg_01",
        "consumer": "report",
        "check_ids": ["nonexistent_check_xyz"],
        "expect": {
            "min_key_findings": 0,
            "allows_empty": True,
        },
    },
]


# ================================================================
# Evaluation Logic
# ================================================================


def _call_context(case: Dict[str, Any]) -> Dict[str, Any]:
    """Call /v1/context/build and return parsed response."""
    payload: Dict[str, Any] = {
        "consumer": case["consumer"],
        "top_k": 10,
        "retrieval_mode": "hybrid",
        "include_mappings": True,
        "include_maturity": True,
    }
    if "check_ids" in case:
        payload["check_ids"] = case["check_ids"]
    if "query" in case:
        payload["query"] = case["query"]

    t0 = time.perf_counter()
    try:
        resp = requests.post(CONTEXT_ENDPOINT, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        latency_ms = (time.perf_counter() - t0) * 1000
        data = resp.json()
        data["_latency_ms"] = latency_ms
        return data
    except Exception as exc:
        return {"_error": str(exc), "_latency_ms": (time.perf_counter() - t0) * 1000}


def _get_bundle(resp: Dict[str, Any], consumer: str) -> Optional[Dict[str, Any]]:
    """Extract consumer bundle from response."""
    data = resp.get("data", {})
    payload = data.get("payload", {})
    key = f"{consumer}_bundle"
    return payload.get(key)


def _evaluate_risk(case: Dict[str, Any], resp: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate Tier 2 risk/planning field accuracy."""
    expect = case["expect"]
    bundle = _get_bundle(resp, case["consumer"])
    checks: Dict[str, bool] = {}

    if bundle is None:
        return {"pass": False, "checks": {"bundle_exists": False}, "reason": "no bundle"}

    checks["bundle_exists"] = True

    if case["consumer"] == "risk":
        pf = bundle.get("primary_finding") or {}

        # Severity check
        if "primary_severity" in expect:
            actual_sev = (pf.get("severity") or "").lower()
            checks["severity_correct"] = actual_sev == expect["primary_severity"]

        # Title contains check
        if "primary_title_contains" in expect:
            actual_title = (pf.get("title") or "").lower()
            checks["title_contains"] = expect["primary_title_contains"].lower() in actual_title

        # Mapping existence
        if "has_mapping" in expect:
            mappings = bundle.get("control_mapping") or []
            checks["has_mapping"] = len(mappings) > 0

        # Specific mapping capability_ids
        if "mapping_capability_ids" in expect:
            actual_caps = {m.get("capability_id", "") for m in (bundle.get("control_mapping") or [])}
            for exp_cap in expect["mapping_capability_ids"]:
                checks[f"mapping_{exp_cap}"] = exp_cap in actual_caps

        # Related findings count
        if "min_related_findings" in expect:
            related = bundle.get("related_findings") or []
            checks["related_count"] = len(related) >= expect["min_related_findings"]

    elif case["consumer"] == "planning":
        findings = bundle.get("related_findings") or []

        if "min_related_findings" in expect:
            checks["findings_count"] = len(findings) >= expect["min_related_findings"]

        if "findings_have_severity" in expect:
            has_sev = all(f.get("severity") for f in findings) if findings else False
            checks["findings_have_severity"] = has_sev

        if "findings_have_service" in expect:
            has_svc = all(f.get("service") for f in findings) if findings else False
            checks["findings_have_service"] = has_svc

        if "expected_service_in_findings" in expect:
            services = {(f.get("service") or "").lower() for f in findings}
            checks["service_present"] = expect["expected_service_in_findings"] in services

    all_pass = all(checks.values())
    return {"pass": all_pass, "checks": checks}


def _evaluate_report(case: Dict[str, Any], resp: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate Tier 3 report context completeness."""
    expect = case["expect"]
    bundle = _get_bundle(resp, "report")
    checks: Dict[str, bool] = {}

    if bundle is None:
        if expect.get("allows_empty"):
            return {"pass": True, "checks": {"allows_empty": True}}
        return {"pass": False, "checks": {"bundle_exists": False}, "reason": "no bundle"}

    checks["bundle_exists"] = True
    kf = bundle.get("key_findings") or []
    themes = bundle.get("control_themes") or []
    practices = bundle.get("recommended_practices") or []
    topics = bundle.get("primary_topics") or []

    if "min_key_findings" in expect:
        checks["key_findings_count"] = len(kf) >= expect["min_key_findings"]

    if "key_findings_have_risk_summary" in expect:
        has_risk = all(
            (f.get("risk_summary") or "").strip() for f in kf
        ) if kf else False
        checks["has_risk_summary"] = has_risk

    if "min_control_themes" in expect:
        checks["control_themes_count"] = len(themes) >= expect["min_control_themes"]

    if "min_recommended_practices" in expect:
        checks["practices_count"] = len(practices) >= expect["min_recommended_practices"]

    if "has_primary_topics" in expect:
        checks["has_topics"] = len(topics) > 0

    all_pass = all(checks.values())
    return {"pass": all_pass, "checks": checks}


# ================================================================
# Runner
# ================================================================


def run_tier(tier_name: str, cases: List[Dict[str, Any]], eval_fn) -> Dict[str, Any]:
    """Run a tier of benchmark cases and return report."""
    results = []
    passed = 0
    total = len(cases)

    for case in cases:
        resp = _call_context(case)
        error = resp.get("_error")
        latency = resp.get("_latency_ms", 0)

        if error:
            result = {
                "case_id": case["case_id"],
                "pass": False,
                "error": error,
                "latency_ms": latency,
                "checks": {},
            }
        else:
            evaluation = eval_fn(case, resp)
            result = {
                "case_id": case["case_id"],
                "consumer": case["consumer"],
                "pass": evaluation["pass"],
                "checks": evaluation["checks"],
                "latency_ms": latency,
            }

        if result["pass"]:
            passed += 1
        results.append(result)

    return {
        "tier": tier_name,
        "total": total,
        "passed": passed,
        "pass_rate": passed / total if total else 0,
        "cases": results,
    }


def print_tier_report(report: Dict[str, Any]) -> None:
    """Print a tier report to stdout."""
    tier = report["tier"]
    total = report["total"]
    passed = report["passed"]
    rate = report["pass_rate"]

    print("=" * 70)
    print(f"{tier}")
    print("=" * 70)
    print(f"Total: {total}  |  Passed: {passed}  |  Rate: {rate:.1%}")
    print("-" * 70)

    for case in report["cases"]:
        status = "PASS" if case["pass"] else "FAIL"
        cid = case["case_id"]
        latency = case.get("latency_ms", 0)
        print(f"  [{status}] {cid:<25} ({latency:.0f}ms)")

        if not case["pass"]:
            for check_name, check_val in case.get("checks", {}).items():
                if not check_val:
                    print(f"         ✗ {check_name}")
            if case.get("error"):
                print(f"         ✗ error: {case['error']}")

    print()


# ================================================================
# Main
# ================================================================


def main():
    print(f"[benchmark_context] Running Tier 2 + 3 against {BASE_URL}")
    print(f"[benchmark_context] Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()

    # Health check
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        r.raise_for_status()
        print("[benchmark_context] Server healthy\n")
    except Exception as exc:
        print(f"[benchmark_context] Server not available: {exc}")
        sys.exit(1)

    # Run tiers
    tier2 = run_tier("TIER 2 — Field Accuracy (Risk + Planning)", TIER2_CASES, _evaluate_risk)
    tier3 = run_tier("TIER 3 — Context Completeness (Report)", TIER3_CASES, _evaluate_report)

    # Print reports
    print_tier_report(tier2)
    print_tier_report(tier3)

    # Combined summary
    total = tier2["total"] + tier3["total"]
    passed = tier2["passed"] + tier3["passed"]
    print("=" * 70)
    print("COMBINED SUMMARY")
    print("=" * 70)
    print(f"Total cases:  {total}")
    print(f"Passed:       {passed}/{total} ({passed/total:.1%})")
    print(f"Tier 2 rate:  {tier2['pass_rate']:.1%}")
    print(f"Tier 3 rate:  {tier3['pass_rate']:.1%}")
    print()

    # Save
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tier2": tier2,
        "tier3": tier3,
        "combined": {"total": total, "passed": passed, "rate": passed / total},
    }
    output_path = OUTPUT_DIR / "benchmark_context_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"[saved] {output_path}")


if __name__ == "__main__":
    main()
