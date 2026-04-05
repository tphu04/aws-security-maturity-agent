"""
Benchmark comparison tool for the RAG system.

Compares two benchmark runs and shows a diff table with directional
indicators, then evaluates release criteria for PASS/FAIL verdict.

Usage:
    python -m scripts.compare_benchmarks --baseline <path> --current <path>
    python -m scripts.compare_benchmarks --baseline last --current latest

Special values:
    "last"   - second most recent benchmark_run_*.json in output dir
    "latest" - benchmark_latest.json in output dir
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

SCRIPT_DIR = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = SCRIPT_DIR / "data" / "benchmarks"
OUTPUT_DIR = BENCHMARKS_DIR / "benchmark_outputs"
RELEASE_CRITERIA_FILE = BENCHMARKS_DIR / "release_criteria.json"


def resolve_report_path(value: str) -> Path:
    """Resolve a report path from a user-provided value."""
    if value == "latest":
        path = OUTPUT_DIR / "benchmark_latest.json"
        if not path.exists():
            raise FileNotFoundError(f"Latest benchmark not found: {path}")
        return path

    if value == "last":
        runs = sorted(OUTPUT_DIR.glob("benchmark_run_*.json"))
        if len(runs) < 2:
            raise FileNotFoundError(
                "Need at least 2 benchmark runs to use 'last'. "
                f"Found {len(runs)} in {OUTPUT_DIR}"
            )
        return runs[-2]  # second most recent

    path = Path(value)
    if not path.exists():
        raise FileNotFoundError(f"Benchmark file not found: {path}")
    return path


def load_report(path: Path) -> Dict[str, Any]:
    """Load a benchmark report JSON file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_release_criteria() -> Dict[str, Any]:
    """Load release criteria."""
    if not RELEASE_CRITERIA_FILE.exists():
        return {}
    with RELEASE_CRITERIA_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def extract_metrics(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract comparable metrics from a unified benchmark report.
    Handles both unified (combined_summary) and legacy (summary) formats.
    """
    # Unified format
    if "combined_summary" in report:
        summary = report["combined_summary"]
        checks_summary = report.get("checks_report", {}).get("summary", {})
        maturity_summary = report.get("maturity_report", {}).get("summary", {})

        lat_p = summary.get("latency_percentiles", {}) or {}
        gap = summary.get("robustness_gap", {}) or {}

        return {
            "total_cases": summary.get("total_cases", 0),
            "combined_top1_rate": summary.get("combined_top1_rate", 0.0),
            "combined_top5_rate": summary.get("combined_top5_rate", 0.0),
            "checks_top1_rate": summary.get("checks_top1_rate", 0.0),
            "checks_top5_rate": summary.get("checks_top5_rate", 0.0),
            "checks_top1_hits": checks_summary.get("hit_expected_in_top1", 0),
            "checks_top5_hits": checks_summary.get("hit_expected_in_top5", 0),
            "checks_total": checks_summary.get("total_cases", 0),
            "maturity_top1_rate": summary.get("maturity_top1_rate", 0.0),
            "maturity_top5_rate": summary.get("maturity_top5_rate", 0.0),
            "maturity_top1_hits": maturity_summary.get("hit_expected_in_top1", 0),
            "maturity_top5_hits": maturity_summary.get("hit_expected_in_top5", 0),
            "maturity_total": maturity_summary.get("total_cases", 0),
            "combined_mrr": summary.get("combined_mrr"),
            "combined_ndcg@5": summary.get("combined_ndcg@5"),
            "combined_map@5": summary.get("combined_map@5"),
            "latency_percentiles.p50_ms": lat_p.get("p50_ms"),
            "latency_percentiles.p90_ms": lat_p.get("p90_ms"),
            "latency_percentiles.p99_ms": lat_p.get("p99_ms"),
            "robustness_gap.gap_pp": gap.get("gap_pp"),
            "confidence_calibration.ece": (
                summary.get("confidence_calibration", {}) or {}
            ).get("ece"),
            "confidence_calibration.check_search.ece": (
                (summary.get("confidence_calibration_by_route", {}) or {})
                .get("check_search", {})
            ).get("ece"),
            "confidence_calibration.maturity_search.ece": (
                (summary.get("confidence_calibration_by_route", {}) or {})
                .get("maturity_search", {})
            ).get("ece"),
            "forbidden_capability_rate_pct": summary.get("forbidden_capability_rate_pct", 0.0),
            "service_precision_pct": summary.get("service_precision_pct"),
            "average_latency_ms": summary.get("average_latency_ms"),
            "median_latency_ms": summary.get("median_latency_ms"),
            "timestamp": report.get("timestamp"),
            "tag": report.get("tag"),
        }

    # Legacy format (single suite)
    summary = report.get("summary", {})
    total = summary.get("total_cases", 0)
    return {
        "total_cases": total,
        "combined_top1_rate": (
            summary.get("hit_expected_in_top1", 0) / total if total > 0 else 0.0
        ),
        "combined_top5_rate": (
            summary.get("hit_expected_in_top5", 0) / total if total > 0 else 0.0
        ),
        "forbidden_capability_rate_pct": summary.get("forbidden_capability_rate_pct", 0.0),
        "service_precision_pct": summary.get("service_precision_pct"),
        "average_latency_ms": summary.get("average_latency_ms"),
        "timestamp": report.get("timestamp"),
        "tag": report.get("tag"),
    }


def format_delta(baseline_val: Any, current_val: Any, lower_is_better: bool = False) -> str:
    """Format a delta value with directional indicator."""
    if baseline_val is None or current_val is None:
        return "N/A"

    try:
        b = float(baseline_val)
        c = float(current_val)
    except (TypeError, ValueError):
        return "N/A"

    delta = c - b
    if abs(delta) < 0.0001:
        return "="

    if lower_is_better:
        indicator = "v (better)" if delta < 0 else "^ (worse)"
    else:
        indicator = "^ (better)" if delta > 0 else "v (worse)"

    return f"{delta:+.4f} {indicator}"


def compare_metrics(
    baseline: Dict[str, Any],
    current: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build comparison rows between baseline and current metrics."""
    metrics_config = [
        # (key, label, lower_is_better, is_latency)
        ("total_cases", "Total cases", False, False),
        ("combined_top1_rate", "Combined Top-1 rate", False, False),
        ("combined_top5_rate", "Combined Top-5 rate", False, False),
        ("checks_top1_rate", "Checks Top-1 rate", False, False),
        ("checks_top5_rate", "Checks Top-5 rate", False, False),
        ("maturity_top1_rate", "Maturity Top-1 rate", False, False),
        ("maturity_top5_rate", "Maturity Top-5 rate", False, False),
        ("combined_mrr", "MRR", False, False),
        ("combined_ndcg@5", "NDCG@5", False, False),
        ("combined_map@5", "MAP@5", False, False),
        ("forbidden_capability_rate_pct", "Forbidden cap. rate %", True, True),
        ("service_precision_pct", "Service precision %", False, False),
        ("average_latency_ms", "Avg latency (ms)", True, True),
        ("median_latency_ms", "Median latency (ms)", True, True),
        ("latency_percentiles.p90_ms", "Latency P90 (ms)", True, True),
        ("latency_percentiles.p99_ms", "Latency P99 (ms)", True, True),
        ("robustness_gap.gap_pp", "Robustness Gap (pp)", True, False),
        ("confidence_calibration.ece", "Confidence ECE", True, False),
        ("confidence_calibration.check_search.ece", "ECE (check_search)", True, False),
        ("confidence_calibration.maturity_search.ece", "ECE (maturity_search)", True, False),
    ]

    rows = []
    for key, label, lower_is_better, is_latency in metrics_config:
        b_val = baseline.get(key)
        c_val = current.get(key)

        if b_val is None and c_val is None:
            continue

        delta = format_delta(b_val, c_val, lower_is_better)

        rows.append({
            "metric": label,
            "key": key,
            "baseline": b_val,
            "current": c_val,
            "delta": delta,
        })

    return rows


def evaluate_current_criteria(
    current: Dict[str, Any],
    criteria: Dict[str, Any],
) -> Tuple[str, List[Dict[str, Any]]]:
    """Evaluate current metrics against release criteria."""
    actual_map = {
        "checks_top1_accuracy_min": current.get("checks_top1_rate", 0.0),
        "checks_top5_accuracy_min": current.get("checks_top5_rate", 0.0),
        "maturity_top1_accuracy_min": current.get("maturity_top1_rate", 0.0),
        "maturity_top5_accuracy_min": current.get("maturity_top5_rate", 0.0),
        "forbidden_capability_rate_max": (
            current.get("forbidden_capability_rate_pct", 0.0) / 100.0
        ),
        "empty_bundle_rate_max": 0.0,
        "service_precision_min": (
            (current.get("service_precision_pct") or 0.0) / 100.0
        ),
        "average_latency_ms_max": current.get("average_latency_ms", 0.0) or 0.0,
        "combined_mrr_min": current.get("combined_mrr", 0.0) or 0.0,
        "combined_ndcg5_min": current.get("combined_ndcg@5", 0.0) or 0.0,
        "latency_p90_ms_max": (
            current.get("latency_percentiles.p90_ms", 0.0) or 0.0
        ),
        "robustness_gap_pp_max": (
            current.get("robustness_gap.gap_pp", 0.0) or 0.0
        ),
        "confidence_ece_max": (
            current.get("confidence_calibration.ece", 0.0) or 0.0
        ),
    }

    results = []
    all_passed = True

    for criterion, threshold in criteria.items():
        actual = actual_map.get(criterion)
        if actual is None:
            results.append({
                "criterion": criterion,
                "threshold": threshold,
                "actual": None,
                "passed": True,
                "note": "metric not available",
            })
            continue

        if criterion.endswith("_min"):
            passed = actual >= threshold
        elif criterion.endswith("_max"):
            passed = actual <= threshold
        else:
            passed = True

        if not passed:
            all_passed = False

        results.append({
            "criterion": criterion,
            "threshold": threshold,
            "actual": round(actual, 4),
            "passed": passed,
        })

    verdict = "PASS" if all_passed else "FAIL"
    return verdict, results


def print_comparison(
    baseline_path: Path,
    current_path: Path,
    baseline_metrics: Dict[str, Any],
    current_metrics: Dict[str, Any],
    comparison_rows: List[Dict[str, Any]],
    verdict: str,
    criteria_results: List[Dict[str, Any]],
) -> None:
    """Print the full comparison report."""
    print("=" * 100)
    print("BENCHMARK COMPARISON")
    print("=" * 100)
    print(f"Baseline : {baseline_path.name}")
    if baseline_metrics.get("timestamp"):
        print(f"           {baseline_metrics['timestamp']}")
    if baseline_metrics.get("tag"):
        print(f"           tag: {baseline_metrics['tag']}")
    print(f"Current  : {current_path.name}")
    if current_metrics.get("timestamp"):
        print(f"           {current_metrics['timestamp']}")
    if current_metrics.get("tag"):
        print(f"           tag: {current_metrics['tag']}")

    print("\n" + "-" * 100)
    print(f"{'Metric':<30} {'Baseline':>12} {'Current':>12} {'Delta'}")
    print("-" * 100)
    for row in comparison_rows:
        b_str = _format_val(row["baseline"])
        c_str = _format_val(row["current"])
        print(f"{row['metric']:<30} {b_str:>12} {c_str:>12}   {row['delta']}")
    print("-" * 100)

    print(f"\nRELEASE CRITERIA VERDICT: {verdict}")
    print("-" * 60)
    for check in criteria_results:
        status = "PASS" if check["passed"] else "FAIL"
        actual_str = f"{check['actual']}" if check["actual"] is not None else "N/A"
        note = f"  ({check['note']})" if check.get("note") else ""
        print(f"  [{status}] {check['criterion']}: "
              f"threshold={check['threshold']}, actual={actual_str}{note}")
    print("=" * 100)


def _format_val(val: Any) -> str:
    """Format a metric value for display."""
    if val is None:
        return "N/A"
    if isinstance(val, float):
        return f"{val:.4f}"
    return str(val)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two RAG benchmark runs")
    parser.add_argument(
        "--baseline", type=str, required=True,
        help="Path to baseline report, or 'last' for second-most-recent run",
    )
    parser.add_argument(
        "--current", type=str, required=True,
        help="Path to current report, or 'latest' for most recent run",
    )
    args = parser.parse_args()

    baseline_path = resolve_report_path(args.baseline)
    current_path = resolve_report_path(args.current)

    print(f"[compare] Loading baseline: {baseline_path}")
    print(f"[compare] Loading current:  {current_path}")

    baseline_report = load_report(baseline_path)
    current_report = load_report(current_path)

    baseline_metrics = extract_metrics(baseline_report)
    current_metrics = extract_metrics(current_report)

    comparison_rows = compare_metrics(baseline_metrics, current_metrics)

    criteria = load_release_criteria()
    verdict, criteria_results = evaluate_current_criteria(current_metrics, criteria)

    print_comparison(
        baseline_path=baseline_path,
        current_path=current_path,
        baseline_metrics=baseline_metrics,
        current_metrics=current_metrics,
        comparison_rows=comparison_rows,
        verdict=verdict,
        criteria_results=criteria_results,
    )

    # Save comparison result
    comparison_output = {
        "baseline_file": str(baseline_path.name),
        "current_file": str(current_path.name),
        "baseline_timestamp": baseline_metrics.get("timestamp"),
        "current_timestamp": current_metrics.get("timestamp"),
        "comparison": comparison_rows,
        "release_criteria_verdict": verdict,
        "release_criteria_checks": criteria_results,
    }

    output_path = OUTPUT_DIR / "benchmark_comparison.json"
    output_path.write_text(
        json.dumps(comparison_output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n[compare] Saved comparison: {output_path}")

    if verdict == "FAIL":
        print("\n[compare] RELEASE CRITERIA NOT MET")
        sys.exit(1)
    else:
        print("\n[compare] All release criteria met.")


if __name__ == "__main__":
    main()
