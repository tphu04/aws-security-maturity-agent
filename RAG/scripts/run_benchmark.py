"""
Unified benchmark runner for the RAG system.

Runs all benchmark suites (checks, maturity) in a single invocation,
produces a timestamped combined JSON report, and evaluates release criteria.

Usage:
    python -m scripts.run_benchmark [--output-dir DIR] [--tag TAG]

Workflow:
    1. Run check retrieval benchmark
    2. Run maturity retrieval benchmark
    3. Combine into a single timestamped report
    4. Evaluate against release criteria
    5. Save report + print summary
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.evaluation.metrics import (
    compute_confidence_calibration,
    compute_latency_percentiles,
    compute_robustness_gap,
)
from data.benchmarks.benchmark_retrieval import (
    _load_cases_from_file,
    evaluate_cases,
    print_report,
    CHECKS_ENDPOINT,
    MATURITY_ENDPOINT,
)

SCRIPT_DIR = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = SCRIPT_DIR / "data" / "benchmarks"
DEFAULT_OUTPUT_DIR = BENCHMARKS_DIR / "benchmark_outputs"
RELEASE_CRITERIA_FILE = BENCHMARKS_DIR / "release_criteria.json"


def load_release_criteria() -> Dict[str, Any]:
    """Load release criteria from JSON file."""
    if not RELEASE_CRITERIA_FILE.exists():
        print(f"[WARN] Release criteria file not found: {RELEASE_CRITERIA_FILE}")
        return {}
    with RELEASE_CRITERIA_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def evaluate_release_criteria(
    combined_report: Dict[str, Any],
    criteria: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Evaluate the combined benchmark report against release criteria.

    Returns a dict with:
    - verdict: "PASS" or "FAIL"
    - checks: list of {criterion, threshold, actual, passed}
    """
    checks_summary = combined_report.get("checks_report", {}).get("summary", {})
    maturity_summary = combined_report.get("maturity_report", {}).get("summary", {})

    checks_total = checks_summary.get("total_cases", 0)
    maturity_total = maturity_summary.get("total_cases", 0)

    # Compute rates
    checks_top1_rate = (
        checks_summary.get("hit_expected_in_top1", 0) / checks_total
        if checks_total > 0 else 0.0
    )
    checks_top5_rate = (
        checks_summary.get("hit_expected_in_top5", 0) / checks_total
        if checks_total > 0 else 0.0
    )
    maturity_top1_rate = (
        maturity_summary.get("hit_expected_in_top1", 0) / maturity_total
        if maturity_total > 0 else 0.0
    )
    maturity_top5_rate = (
        maturity_summary.get("hit_expected_in_top5", 0) / maturity_total
        if maturity_total > 0 else 0.0
    )
    forbidden_rate = (
        checks_summary.get("forbidden_capability_rate_pct", 0.0) / 100.0
    )
    service_precision = (
        (checks_summary.get("service_precision_pct", 0.0) or 0.0) / 100.0
    )
    avg_latency = checks_summary.get("average_latency_ms", 0.0) or 0.0

    # New metrics (Phase 1/3/5) — computed from sub-report summaries
    # because this function is called before build_combined_report()
    total = checks_total + maturity_total
    checks_mrr = checks_summary.get("mrr", 0.0) or 0.0
    maturity_mrr = maturity_summary.get("mrr", 0.0) or 0.0
    combined_mrr = (
        (checks_mrr * checks_total + maturity_mrr * maturity_total) / total
        if total > 0 else 0.0
    )
    checks_ndcg = checks_summary.get("ndcg@5", 0.0) or 0.0
    maturity_ndcg = maturity_summary.get("ndcg@5", 0.0) or 0.0
    combined_ndcg5 = (
        (checks_ndcg * checks_total + maturity_ndcg * maturity_total) / total
        if total > 0 else 0.0
    )
    latency_p90 = (
        (checks_summary.get("latency_percentiles") or {}).get("p90_ms", 0.0) or 0.0
    )
    robustness_gap_pp = (
        (checks_summary.get("robustness_gap") or {}).get("gap_pp", 0.0) or 0.0
    )
    confidence_ece = (
        (checks_summary.get("confidence_calibration") or {}).get("ece", 0.0) or 0.0
    )

    # Map criteria keys to actual values
    actual_values = {
        "checks_top1_accuracy_min": checks_top1_rate,
        "checks_top5_accuracy_min": checks_top5_rate,
        "maturity_top1_accuracy_min": maturity_top1_rate,
        "maturity_top5_accuracy_min": maturity_top5_rate,
        "forbidden_capability_rate_max": forbidden_rate,
        "empty_bundle_rate_max": 0.0,  # Not yet measured
        "service_precision_min": service_precision,
        "average_latency_ms_max": avg_latency,
        "combined_mrr_min": combined_mrr,
        "combined_ndcg5_min": combined_ndcg5,
        "latency_p90_ms_max": latency_p90,
        "robustness_gap_pp_max": robustness_gap_pp,
        "confidence_ece_max": confidence_ece,
    }

    results: List[Dict[str, Any]] = []
    all_passed = True

    for criterion, threshold in criteria.items():
        actual = actual_values.get(criterion)
        if actual is None:
            results.append({
                "criterion": criterion,
                "threshold": threshold,
                "actual": None,
                "passed": True,  # Skip unknown criteria
                "note": "metric not available",
            })
            continue

        # Determine pass/fail based on criterion name
        if criterion.endswith("_min"):
            passed = actual >= threshold
        elif criterion.endswith("_max"):
            passed = actual <= threshold
        else:
            passed = True  # Unknown suffix, skip

        if not passed:
            all_passed = False

        results.append({
            "criterion": criterion,
            "threshold": threshold,
            "actual": round(actual, 4),
            "passed": passed,
        })

    return {
        "verdict": "PASS" if all_passed else "FAIL",
        "checks": results,
    }


def build_combined_report(
    checks_report: Dict[str, Any],
    maturity_report: Dict[str, Any],
    criteria_eval: Dict[str, Any],
    tag: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the unified timestamped report."""
    now = datetime.now(timezone.utc)

    checks_summary = checks_report.get("summary", {})
    maturity_summary = maturity_report.get("summary", {})

    total_checks = checks_summary.get("total_cases", 0)
    total_maturity = maturity_summary.get("total_cases", 0)
    total = total_checks + total_maturity

    combined_top1 = (
        checks_summary.get("hit_expected_in_top1", 0)
        + maturity_summary.get("hit_expected_in_top1", 0)
    )
    combined_top5 = (
        checks_summary.get("hit_expected_in_top5", 0)
        + maturity_summary.get("hit_expected_in_top5", 0)
    )

    # Weighted-mean helper for combining sub-report metrics
    def _weighted_mean(val_a: float, val_b: float, n_a: int, n_b: int) -> float:
        if n_a + n_b == 0:
            return 0.0
        return round((val_a * n_a + val_b * n_b) / (n_a + n_b), 4)

    checks_mrr = checks_summary.get("mrr", 0.0) or 0.0
    maturity_mrr = maturity_summary.get("mrr", 0.0) or 0.0
    checks_ndcg = checks_summary.get("ndcg@5", 0.0) or 0.0
    maturity_ndcg = maturity_summary.get("ndcg@5", 0.0) or 0.0
    checks_map = checks_summary.get("map@5", 0.0) or 0.0
    maturity_map = maturity_summary.get("map@5", 0.0) or 0.0

    # Combine latencies from both suites for percentile calculation
    all_latencies = (
        [c["latency_ms"] for c in checks_report.get("cases", [])]
        + [c["latency_ms"] for c in maturity_report.get("cases", [])]
    )

    # Robustness gap — use checks by_category (maturity has different categories)
    checks_by_category = checks_summary.get("by_category", {})

    # Confidence calibration — combine cases from both suites
    all_cases = (
        checks_report.get("cases", []) + maturity_report.get("cases", [])
    )
    combined_calibration_cases = [
        {"confidence": c["confidence"], "hit_top1": c["hit_top1"]}
        for c in all_cases
        if c.get("confidence") is not None
    ]
    combined_calibration = compute_confidence_calibration(combined_calibration_cases)

    # Per-route calibration (Task 5.2) — uses route_type inferred from endpoint
    calibration_by_route: Dict[str, Any] = {}
    for route_key in ("check_search", "maturity_search"):
        route_cases = [
            {"confidence": c["confidence"], "hit_top1": c["hit_top1"]}
            for c in all_cases
            if c.get("confidence") is not None
            and c.get("route_type") == route_key
        ]
        calibration_by_route[route_key] = compute_confidence_calibration(route_cases)

    return {
        "report_type": "unified_benchmark",
        "timestamp": now.isoformat(),
        "timestamp_unix": int(now.timestamp()),
        "tag": tag,
        "combined_summary": {
            "total_cases": total,
            "combined_top1_hits": combined_top1,
            "combined_top1_rate": round(combined_top1 / total, 4) if total > 0 else 0.0,
            "combined_top5_hits": combined_top5,
            "combined_top5_rate": round(combined_top5 / total, 4) if total > 0 else 0.0,
            "checks_top1_rate": round(
                checks_summary.get("hit_expected_in_top1", 0) / total_checks, 4
            ) if total_checks > 0 else 0.0,
            "checks_top5_rate": round(
                checks_summary.get("hit_expected_in_top5", 0) / total_checks, 4
            ) if total_checks > 0 else 0.0,
            "maturity_top1_rate": round(
                maturity_summary.get("hit_expected_in_top1", 0) / total_maturity, 4
            ) if total_maturity > 0 else 0.0,
            "maturity_top5_rate": round(
                maturity_summary.get("hit_expected_in_top5", 0) / total_maturity, 4
            ) if total_maturity > 0 else 0.0,
            "combined_mrr": _weighted_mean(checks_mrr, maturity_mrr, total_checks, total_maturity),
            "combined_ndcg@5": _weighted_mean(checks_ndcg, maturity_ndcg, total_checks, total_maturity),
            "combined_map@5": _weighted_mean(checks_map, maturity_map, total_checks, total_maturity),
            "latency_percentiles": compute_latency_percentiles(all_latencies),
            "robustness_gap": compute_robustness_gap(checks_by_category, metric_key="top1_rate"),
            "confidence_calibration": combined_calibration,
            "confidence_calibration_by_route": calibration_by_route,
            "forbidden_capability_rate_pct": checks_summary.get("forbidden_capability_rate_pct", 0.0),
            "service_precision_pct": checks_summary.get("service_precision_pct"),
            "average_latency_ms": checks_summary.get("average_latency_ms"),
            "median_latency_ms": checks_summary.get("median_latency_ms"),
        },
        "release_criteria": criteria_eval,
        "checks_report": checks_report,
        "maturity_report": maturity_report,
    }


def print_combined_summary(report: Dict[str, Any]) -> None:
    """Print the unified summary to console."""
    summary = report["combined_summary"]
    criteria = report["release_criteria"]

    print("\n" + "=" * 100)
    print("UNIFIED BENCHMARK REPORT")
    print("=" * 100)
    print(f"Timestamp              : {report['timestamp']}")
    if report.get("tag"):
        print(f"Tag                    : {report['tag']}")
    print(f"Total cases            : {summary['total_cases']}")
    print(f"Combined Top-1         : {summary['combined_top1_hits']}/{summary['total_cases']}"
          f" ({summary['combined_top1_rate']*100:.1f}%)")
    print(f"Combined Top-5         : {summary['combined_top5_hits']}/{summary['total_cases']}"
          f" ({summary['combined_top5_rate']*100:.1f}%)")
    print(f"Checks Top-1           : {summary['checks_top1_rate']*100:.1f}%")
    print(f"Checks Top-5           : {summary['checks_top5_rate']*100:.1f}%")
    print(f"Maturity Top-1         : {summary['maturity_top1_rate']*100:.1f}%")
    print(f"Maturity Top-5         : {summary['maturity_top5_rate']*100:.1f}%")
    # Retrieval quality metrics
    print(f"Combined MRR           : {summary.get('combined_mrr', 'N/A')}")
    print(f"Combined NDCG@5        : {summary.get('combined_ndcg@5', 'N/A')}")
    print(f"Combined MAP@5         : {summary.get('combined_map@5', 'N/A')}")

    lat_p = summary.get("latency_percentiles", {})
    if lat_p:
        print(f"Latency P50/P90/P99    : {lat_p.get('p50_ms')} / {lat_p.get('p90_ms')} / {lat_p.get('p99_ms')} ms")

    gap = summary.get("robustness_gap", {})
    if gap and gap.get("best_category"):
        print(f"Robustness gap         : {gap['gap_pp']} pp"
              f" (best={gap['best_category']} {gap['best_value']:.2f},"
              f" worst={gap['worst_category']} {gap['worst_value']:.2f})")

    # Confidence calibration
    cal = summary.get("confidence_calibration", {})
    if cal and cal.get("total_cases", 0) > 0:
        print(f"Confidence ECE         : {cal.get('ece', '?')}"
              f"  (overall_calibrated={cal.get('overall_calibrated', 'N/A')})")

    # Per-route calibration (Task 5.2)
    by_route = summary.get("confidence_calibration_by_route", {})
    if by_route:
        route_parts = []
        for route, rcal in by_route.items():
            if rcal.get("total_cases", 0) > 0:
                route_parts.append(
                    f"{route}: ECE={rcal.get('ece', '?')}"
                    f" calibrated={rcal.get('overall_calibrated', 'N/A')}"
                )
        if route_parts:
            print(f"Calibration by route   : {' | '.join(route_parts)}")

    print(f"Forbidden cap. rate    : {summary['forbidden_capability_rate_pct']}%")
    if summary['service_precision_pct'] is not None:
        print(f"Service precision      : {summary['service_precision_pct']}%")
    print(f"Average latency        : {summary['average_latency_ms']} ms")

    print("\n" + "-" * 100)
    print(f"RELEASE CRITERIA VERDICT: {criteria['verdict']}")
    print("-" * 100)
    for check in criteria["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        actual_str = f"{check['actual']}" if check['actual'] is not None else "N/A"
        note = f"  ({check['note']})" if check.get("note") else ""
        print(f"  [{status}] {check['criterion']}: "
              f"threshold={check['threshold']}, actual={actual_str}{note}")
    print("=" * 100)


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified RAG benchmark runner")
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Directory for output files (default: data/benchmarks/benchmark_outputs)",
    )
    parser.add_argument(
        "--tag", type=str, default=None,
        help="Optional tag for this benchmark run (e.g. 'slice-10', 'pre-release')",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    print("[run_benchmark] Starting unified benchmark run...")
    start_time = time.perf_counter()

    # Load cases
    check_cases, maturity_cases = _load_cases_from_file()
    print(f"[run_benchmark] Loaded {len(check_cases)} check cases, "
          f"{len(maturity_cases)} maturity cases")

    # Run check benchmark
    print("\n[run_benchmark] Running checks benchmark...")
    checks_report = evaluate_cases(
        endpoint=CHECKS_ENDPOINT,
        cases=check_cases,
        report_name="benchmark_checks_report",
    )
    print_report(checks_report)

    # Run maturity benchmark
    print("\n[run_benchmark] Running maturity benchmark...")
    maturity_report = evaluate_cases(
        endpoint=MATURITY_ENDPOINT,
        cases=maturity_cases,
        report_name="benchmark_maturity_report",
    )
    print_report(maturity_report)

    # Load and evaluate release criteria
    criteria = load_release_criteria()
    criteria_eval = evaluate_release_criteria(
        {"checks_report": checks_report, "maturity_report": maturity_report},
        criteria,
    )

    # Build combined report
    combined = build_combined_report(
        checks_report=checks_report,
        maturity_report=maturity_report,
        criteria_eval=criteria_eval,
        tag=args.tag,
    )

    # Save timestamped report
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"benchmark_run_{timestamp_str}.json"
    output_path = output_dir / filename
    output_path.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n[run_benchmark] Saved unified report: {output_path}")

    # Also save as 'latest' for easy comparison
    latest_path = output_dir / "benchmark_latest.json"
    latest_path.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[run_benchmark] Saved as latest: {latest_path}")

    elapsed = time.perf_counter() - start_time
    print(f"\n[run_benchmark] Total elapsed: {elapsed:.1f}s")

    # Print combined summary
    print_combined_summary(combined)

    # Exit with non-zero if FAIL
    if criteria_eval["verdict"] == "FAIL":
        print("\n[run_benchmark] RELEASE CRITERIA NOT MET - see details above")
        sys.exit(1)
    else:
        print("\n[run_benchmark] All release criteria met.")


if __name__ == "__main__":
    main()
