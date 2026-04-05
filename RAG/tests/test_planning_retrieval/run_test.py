"""
Benchmark retrieval quality for Planning Agent use-cases.

Simulates how a human describes a security scope in natural language,
then checks whether the RAG returns the right checks for that intent.

Input style mimics real user requests to the planning agent:
  - "I want to secure my S3 buckets"           (broad scope)
  - "make sure nobody can SSH into my servers"  (specific concern)
  - "harden the database layer"                 (vague scope)

Metrics:
  - Hit Rate @k   : >= 1 relevant check in top-k
  - MRR            : 1/rank of first relevant check
  - Precision @k   : relevant / k
  - MAP @k         : mean average precision
  - Scope Coverage : fraction of expected checks actually retrieved in top-k
  - Latency        : p50, p90, p99

Usage:
    python run_test.py
    python run_test.py --base-url http://localhost:8080
    python run_test.py --k 1 3 5 10
"""
from __future__ import annotations

import argparse
import json
import statistics
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
K_VALUES = [1, 3, 5, 10]

# ---------------------------------------------------------------------------
# Test cases — natural language inputs + ground-truth check scopes
# ---------------------------------------------------------------------------
# Each case represents a realistic user request to the planning agent.
# "relevant" = the check IDs that SHOULD be retrieved for this intent.
# "must_have" (optional) = subset that MUST appear — stricter than relevant.

CASES: List[Dict[str, Any]] = [
    # =====================================================================
    # S3 — Storage security
    # =====================================================================
    {
        "name": "s3__lock_down_public_buckets",
        "intent": "I want to make sure none of my S3 buckets are publicly accessible",
        "service": "s3",
        "relevant": [
            "s3_bucket_level_public_access_block",
            "s3_account_level_public_access_blocks",
            "s3_bucket_public_access",
            "s3_bucket_policy_public_write_access",
            "s3_access_point_public_access_block",
        ],
        "must_have": [
            "s3_bucket_level_public_access_block",
            "s3_account_level_public_access_blocks",
        ],
    },
    {
        "name": "s3__encrypt_everything",
        "intent": "all data stored in S3 should be encrypted, both at rest and in transit",
        "service": "s3",
        "relevant": [
            "s3_bucket_default_encryption",
            "s3_bucket_secure_transport_policy",
        ],
    },
    {
        "name": "s3__protect_against_accidental_deletion",
        "intent": "protect our S3 data from accidental or malicious deletion",
        "service": "s3",
        "relevant": [
            "s3_bucket_object_versioning",
            "s3_bucket_object_lock",
        ],
    },
    {
        "name": "s3__logging_and_monitoring",
        "intent": "I need visibility into who is accessing our buckets and what they are doing",
        "service": "s3",
        "relevant": [
            "s3_bucket_server_access_logging_enabled",
        ],
    },

    # =====================================================================
    # IAM — Identity & Access
    # =====================================================================
    {
        "name": "iam__secure_root_account",
        "intent": "secure the root account, it should have MFA and no access keys",
        "service": "iam",
        "relevant": [
            "iam_root_hardware_mfa_enabled",
            "iam_root_mfa_totp_enabled",
            "iam_no_root_access_key",
        ],
        "must_have": [
            "iam_no_root_access_key",
        ],
    },
    {
        "name": "iam__rotate_credentials",
        "intent": "make sure developers are rotating their access keys regularly",
        "service": "iam",
        "relevant": [
            "iam_rotate_access_key_90_days",
            "iam_user_mfa_enabled_console_access",
        ],
    },
    {
        "name": "iam__least_privilege",
        "intent": "review policies to enforce least privilege, no wildcard permissions",
        "service": "iam",
        "relevant": [
            "iam_policy_no_statements_with_admin_access",
            "iam_policy_no_statements_with_full_access",
            "iam_aws_attached_policy_no_administrative_privileges",
        ],
    },
    {
        "name": "iam__unused_credentials",
        "intent": "find and disable stale credentials and unused IAM users",
        "service": "iam",
        "relevant": [
            "iam_user_accesskey_unused",
            "iam_disable_90_days_credentials",
        ],
    },
    {
        "name": "iam__password_policy",
        "intent": "enforce a strong password policy for all IAM users",
        "service": "iam",
        "relevant": [
            "iam_password_policy_uppercase",
            "iam_password_policy_lowercase",
            "iam_password_policy_number",
            "iam_password_policy_symbol",
            "iam_password_policy_minimum_length_14",
            "iam_password_policy_expires_passwords_within_90_days_or_less",
            "iam_password_policy_reuse_24",
        ],
    },

    # =====================================================================
    # EC2 — Compute security
    # =====================================================================
    {
        "name": "ec2__no_open_ssh",
        "intent": "make sure nobody can SSH into our servers from the internet",
        "service": "ec2",
        "relevant": [
            "ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22",
        ],
    },
    {
        "name": "ec2__restrict_open_ports",
        "intent": "close all unnecessary open ports in security groups facing the internet",
        "service": "ec2",
        "relevant": [
            "ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22",
            "ec2_securitygroup_allow_ingress_from_internet_to_any_port",
            "ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_3389",
        ],
    },
    {
        "name": "ec2__encrypt_volumes",
        "intent": "all our EBS volumes should be encrypted by default",
        "service": "ec2",
        "relevant": [
            "ec2_ebs_default_encryption",
            "ec2_ebs_volume_encryption",
        ],
    },
    {
        "name": "ec2__patch_and_runtime",
        "intent": "instances should use IMDSv2 and not run outdated AMIs",
        "service": "ec2",
        "relevant": [
            "ec2_instance_imdsv2_enabled",
        ],
    },

    # =====================================================================
    # RDS — Database security
    # =====================================================================
    {
        "name": "rds__no_public_databases",
        "intent": "databases should never be reachable from the public internet",
        "service": "rds",
        "relevant": [
            "rds_instance_no_public_access",
            "rds_snapshots_public_access",
        ],
    },
    {
        "name": "rds__encrypt_and_backup",
        "intent": "harden the database layer with encryption and automated backups",
        "service": "rds",
        "relevant": [
            "rds_instance_storage_encrypted",
            "rds_instance_backup_enabled",
            "rds_instance_multi_az",
        ],
    },

    # =====================================================================
    # CloudTrail — Audit & logging
    # =====================================================================
    {
        "name": "cloudtrail__full_audit_trail",
        "intent": "I need a complete audit trail of everything happening in the account",
        "service": "cloudtrail",
        "relevant": [
            "cloudtrail_multi_region_enabled",
            "cloudtrail_log_file_validation_enabled",
            "cloudtrail_s3_dataevents_read_enabled",
            "cloudtrail_s3_dataevents_write_enabled",
        ],
        "must_have": [
            "cloudtrail_multi_region_enabled",
        ],
    },

    # =====================================================================
    # KMS — Key management
    # =====================================================================
    {
        "name": "kms__rotate_keys",
        "intent": "our encryption keys should be rotated automatically",
        "service": "kms",
        "relevant": [
            "kms_cmk_rotation_enabled",
        ],
    },

    # =====================================================================
    # Lambda — Serverless security
    # =====================================================================
    {
        "name": "lambda__runtime_and_access",
        "intent": "check that our Lambda functions are not using deprecated runtimes and are not publicly invocable",
        "service": "awslambda",
        "relevant": [
            "awslambda_function_using_supported_runtimes",
            "awslambda_function_url_public",
        ],
    },

    # =====================================================================
    # Cross-service / broad scope
    # =====================================================================
    {
        "name": "broad__encrypt_data_at_rest",
        "intent": "encrypt all data at rest across the entire account",
        "service": None,
        "relevant": [
            "s3_bucket_default_encryption",
            "ec2_ebs_default_encryption",
            "ec2_ebs_volume_encryption",
            "rds_instance_storage_encrypted",
        ],
    },
    {
        "name": "broad__full_security_audit_s3",
        "intent": "run a full security audit on S3",
        "service": "s3",
        "relevant": [
            "s3_bucket_level_public_access_block",
            "s3_account_level_public_access_blocks",
            "s3_bucket_default_encryption",
            "s3_bucket_secure_transport_policy",
            "s3_bucket_server_access_logging_enabled",
            "s3_bucket_object_versioning",
        ],
    },
]


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def post(base_url: str, body: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{base_url}{ENDPOINT}"
    t0 = time.perf_counter()
    resp = requests.post(url, json=body, timeout=TIMEOUT)
    latency_ms = (time.perf_counter() - t0) * 1000
    try:
        data = resp.json()
    except Exception:
        data = {"_raw": resp.text}
    return {"http_status": resp.status_code, "latency_ms": latency_ms, "response": data}


# ---------------------------------------------------------------------------
# Extract & normalise doc IDs
# ---------------------------------------------------------------------------
def extract_doc_ids(response: Dict[str, Any]) -> List[str]:
    results = response.get("response", {}).get("data", {}).get("results", [])
    ids = []
    for r in results:
        raw = r.get("doc_id") or r.get("metadata", {}).get("check_id", "<unknown>")
        ids.append(raw.removeprefix("check:").lower())
    return ids


# ---------------------------------------------------------------------------
# Per-query metrics
# ---------------------------------------------------------------------------
def compute_metrics(
    retrieved: List[str],
    relevant: List[str],
    must_have: List[str],
    k_values: List[int],
) -> Dict[str, Any]:
    rel_set = {r.lower() for r in relevant}
    must_set = {r.lower() for r in must_have}
    metrics: Dict[str, Any] = {}

    # Reciprocal Rank
    rr = 0.0
    for i, doc in enumerate(retrieved):
        if doc in rel_set:
            rr = 1.0 / (i + 1)
            break
    metrics["reciprocal_rank"] = rr

    for k in k_values:
        top_k = retrieved[:k]
        hits = [d for d in top_k if d in rel_set]

        metrics[f"hit@{k}"] = 1.0 if hits else 0.0
        metrics[f"precision@{k}"] = round(len(hits) / k, 4)

        # Scope Coverage @k = how many of the expected checks did we find
        metrics[f"coverage@{k}"] = round(len(hits) / len(rel_set), 4) if rel_set else 0.0

        # AP @k
        num_found = 0
        sum_prec = 0.0
        for i, doc in enumerate(top_k):
            if doc in rel_set:
                num_found += 1
                sum_prec += num_found / (i + 1)
        metrics[f"ap@{k}"] = round(sum_prec / min(len(rel_set), k), 4) if rel_set else 0.0

    # Must-have check
    must_found = [d for d in retrieved[:max(k_values)] if d in must_set]
    metrics["must_have_recall"] = round(len(must_found) / len(must_set), 4) if must_set else 1.0

    return metrics


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------
def aggregate(per_query: List[Dict[str, Any]], k_values: List[int]) -> Dict[str, Any]:
    n = len(per_query)
    if n == 0:
        return {}
    agg: Dict[str, Any] = {}
    agg["MRR"] = round(statistics.mean(q["reciprocal_rank"] for q in per_query), 4)
    agg["MustHaveRecall"] = round(statistics.mean(q["must_have_recall"] for q in per_query), 4)
    for k in k_values:
        agg[f"HitRate@{k}"] = round(statistics.mean(q[f"hit@{k}"] for q in per_query), 4)
        agg[f"Precision@{k}"] = round(statistics.mean(q[f"precision@{k}"] for q in per_query), 4)
        agg[f"Coverage@{k}"] = round(statistics.mean(q[f"coverage@{k}"] for q in per_query), 4)
        agg[f"MAP@{k}"] = round(statistics.mean(q[f"ap@{k}"] for q in per_query), 4)
    return agg


def latency_stats(latencies: List[float]) -> Dict[str, float]:
    if not latencies:
        return {}
    s = sorted(latencies)
    n = len(s)
    return {
        "p50_ms": round(s[n // 2], 1),
        "p90_ms": round(s[int(n * 0.9)], 1),
        "p99_ms": round(s[min(int(n * 0.99), n - 1)], 1),
        "mean_ms": round(statistics.mean(s), 1),
    }


# ---------------------------------------------------------------------------
# Pretty print
# ---------------------------------------------------------------------------
def print_per_query(results: List[Dict[str, Any]], k_values: List[int]):
    hdr = f"  {'Case':<42}{'RR':>6}{'must':>6}"
    for k in k_values:
        hdr += f"{'h@' + str(k):>6}"
    hdr += f"{'cov@5':>7}{'ms':>8}"
    print(hdr)
    print(f"  {'-' * (len(hdr) - 2)}")

    for r in results:
        m = r["metrics"]
        row = f"  {r['name']:<42}{m['reciprocal_rank']:>6.3f}{m['must_have_recall']:>6.2f}"
        for k in k_values:
            row += f"{m[f'hit@{k}']:>6.0f}"
        row += f"{m.get('coverage@5', 0):>7.2f}"
        row += f"{r['latency_ms']:>8.0f}"
        print(row)


def print_aggregate(agg: Dict[str, Any], lat: Dict[str, float], k_values: List[int]):
    print(f"\n{'=' * 72}")
    print(f"  AGGREGATE METRICS")
    print(f"{'=' * 72}")

    hdr = f"  {'Metric':<20}"
    for k in k_values:
        hdr += f"{'@' + str(k):>10}"
    print(hdr)
    print(f"  {'-' * (20 + 10 * len(k_values))}")

    for name in ["HitRate", "Precision", "Coverage", "MAP"]:
        row = f"  {name:<20}"
        for k in k_values:
            row += f"{agg.get(f'{name}@{k}', 0):>10.4f}"
        print(row)

    print(f"\n  {'MRR':<20}{agg.get('MRR', 0):>10.4f}")
    print(f"  {'MustHaveRecall':<20}{agg.get('MustHaveRecall', 0):>10.4f}")

    if lat:
        print(f"\n  {'Latency':<20}{'p50':>10}{'p90':>10}{'p99':>10}{'mean':>10}")
        print(f"  {'-' * 60}")
        print(
            f"  {'(ms)':<20}"
            f"{lat['p50_ms']:>10.1f}"
            f"{lat['p90_ms']:>10.1f}"
            f"{lat['p99_ms']:>10.1f}"
            f"{lat['mean_ms']:>10.1f}"
        )


def print_failures(results: List[Dict[str, Any]]):
    """Print details for cases with must_have_recall < 1."""
    failures = [r for r in results if r["metrics"]["must_have_recall"] < 1.0]
    if not failures:
        return
    print(f"\n{'=' * 72}")
    print(f"  MUST-HAVE MISSES ({len(failures)} cases)")
    print(f"{'=' * 72}")
    for r in failures:
        missing = set(r["must_have"]) - set(r["retrieved_top10"])
        print(f"\n  {r['name']}")
        print(f"    intent    : {r['intent']}")
        print(f"    missing   : {sorted(missing)}")
        print(f"    got top-5 : {r['retrieved_top10'][:5]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(base_url: str, k_values: List[int]) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    max_k = max(k_values)

    print(f"Planning Retrieval Benchmark — {datetime.now(timezone.utc).isoformat()}")
    print(f"Endpoint : {base_url}{ENDPOINT}")
    print(f"Cases    : {len(CASES)}")
    print(f"k values : {k_values}\n")

    all_metrics: List[Dict[str, Any]] = []
    all_latencies: List[float] = []
    query_results: List[Dict[str, Any]] = []

    for case in CASES:
        body: Dict[str, Any] = {
            "query": case["intent"],
            "top_k": max_k,
            "debug": True,
        }
        if case.get("service"):
            body["service"] = case["service"]

        try:
            result = post(base_url, body)
        except requests.ConnectionError:
            print(f"  [SKIP] {case['name']} — cannot connect")
            continue

        doc_ids = extract_doc_ids(result)
        metrics = compute_metrics(
            doc_ids,
            case["relevant"],
            case.get("must_have", []),
            k_values,
        )

        all_metrics.append(metrics)
        all_latencies.append(result["latency_ms"])

        query_results.append({
            "name": case["name"],
            "intent": case["intent"],
            "service": case.get("service"),
            "relevant": case["relevant"],
            "must_have": case.get("must_have", []),
            "retrieved_top10": doc_ids[:max_k],
            "metrics": metrics,
            "latency_ms": round(result["latency_ms"], 1),
            "confidence": result["response"].get("meta", {}).get("confidence"),
        })

    if not all_metrics:
        print("No results — is the server running?")
        return 1

    # Print
    print_per_query(query_results, k_values)
    agg = aggregate(all_metrics, k_values)
    lat = latency_stats(all_latencies)
    print_aggregate(agg, lat, k_values)
    print_failures(query_results)

    # Summary line
    must_ok = sum(1 for m in all_metrics if m["must_have_recall"] >= 1.0)
    print(f"\n  Must-have recall: {must_ok}/{len(all_metrics)} cases fully satisfied")

    # Save
    report = {
        "timestamp": timestamp,
        "base_url": base_url,
        "endpoint": ENDPOINT,
        "k_values": k_values,
        "num_cases": len(query_results),
        "aggregate": agg,
        "latency": lat,
        "per_query": query_results,
    }
    out_file = OUTPUT_DIR / f"planning_retrieval_{timestamp}.json"
    out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Report saved to: {out_file}")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark retrieval for planning agent scenarios")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--k", nargs="+", type=int, default=K_VALUES)
    args = parser.parse_args()
    sys.exit(run(args.base_url, sorted(args.k)))
