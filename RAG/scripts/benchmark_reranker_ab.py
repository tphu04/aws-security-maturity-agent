"""
Benchmark Reranker A/B Comparison.

Analyzes the impact of the CrossEncoder reranker by comparing
pre-rerank (RRF-only) vs post-rerank ordering using diagnostics
data captured during a single benchmark run.

Two modes:
  --mode diagnostics  (default) Uses reranker_pre_order/post_order
                      from a single run — no server restart needed.
  --mode live         Runs benchmark twice: once with reranker enabled,
                      once with it disabled (toggles scoring_config.json).

Usage:
    python -m scripts.benchmark_reranker_ab
    python -m scripts.benchmark_reranker_ab --mode live
    python -m scripts.benchmark_reranker_ab --report path/to/report.json
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

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.evaluation.metrics import (
    compute_ndcg,
    compute_reciprocal_rank,
    compute_latency_percentiles,
)

SCRIPT_DIR = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = SCRIPT_DIR / "data" / "benchmarks"
OUTPUT_DIR = BENCHMARKS_DIR / "benchmark_outputs"
SCORING_CONFIG = SCRIPT_DIR / "app" / "core" / "scoring_config.json"


# ---------------------------------------------------------------------------
# Diagnostics mode — analyze from an existing benchmark report
# ---------------------------------------------------------------------------

def analyze_from_report(report_path: Path) -> Dict[str, Any]:
    """Extract reranker A/B data from an existing benchmark report.

    The report must have been generated after Task 3.1/3.2 so that
    each case row contains ``reranker_pre_order``, ``reranker_post_order``,
    and the per-case lift fields.
    """
    with report_path.open("r", encoding="utf-8") as f:
        report = json.load(f)

    # Handle both unified (combined) and single-suite reports
    all_cases: List[Dict[str, Any]] = []
    suites: List[str] = []

    if "checks_report" in report:
        all_cases.extend(report["checks_report"].get("cases", []))
        suites.append("checks")
    if "maturity_report" in report:
        all_cases.extend(report["maturity_report"].get("cases", []))
        suites.append("maturity")
    if not all_cases and "cases" in report:
        all_cases = report["cases"]
        suites.append(report.get("report_name", "unknown"))

    return _build_ab_comparison(all_cases, suites, source=str(report_path.name))


def _build_ab_comparison(
    cases: List[Dict[str, Any]],
    suites: List[str],
    source: str,
) -> Dict[str, Any]:
    """Build the A/B comparison from case rows that contain reranker fields."""
    cases_with_data = [
        c for c in cases
        if c.get("reranker_mrr_before") is not None
    ]

    if not cases_with_data:
        print("[reranker_ab] No cases with reranker diagnostics data found.")
        return {"error": "No reranker diagnostics data in report"}

    # Per-case analysis
    per_case: List[Dict[str, Any]] = []
    for c in cases_with_data:
        mrr_lift = c.get("reranker_mrr_lift", 0)
        ndcg_lift = c.get("reranker_ndcg_lift", 0)
        per_case.append({
            "case_id": c.get("case_id"),
            "category": c.get("category"),
            "service": c.get("service"),
            "mrr_before": c.get("reranker_mrr_before"),
            "mrr_after": c.get("reranker_mrr_after"),
            "mrr_lift": mrr_lift,
            "ndcg_before": c.get("reranker_ndcg_before"),
            "ndcg_after": c.get("reranker_ndcg_after"),
            "ndcg_lift": ndcg_lift,
            "impact": (
                "improved" if mrr_lift > 0
                else "degraded" if mrr_lift < 0
                else "unchanged"
            ),
        })

    # Aggregate
    n = len(cases_with_data)
    mrr_before_vals = [c["reranker_mrr_before"] for c in cases_with_data]
    mrr_after_vals = [c["reranker_mrr_after"] for c in cases_with_data]
    ndcg_before_vals = [c["reranker_ndcg_before"] for c in cases_with_data]
    ndcg_after_vals = [c["reranker_ndcg_after"] for c in cases_with_data]
    latencies = [c.get("latency_ms", 0) for c in cases_with_data]

    mrr_before = round(statistics.mean(mrr_before_vals), 4)
    mrr_after = round(statistics.mean(mrr_after_vals), 4)
    ndcg_before = round(statistics.mean(ndcg_before_vals), 4)
    ndcg_after = round(statistics.mean(ndcg_after_vals), 4)

    improved = sum(1 for c in per_case if c["impact"] == "improved")
    degraded = sum(1 for c in per_case if c["impact"] == "degraded")
    unchanged = sum(1 for c in per_case if c["impact"] == "unchanged")

    mrr_delta = round(mrr_after - mrr_before, 4)
    ndcg_delta = round(ndcg_after - ndcg_before, 4)

    # Per-category breakdown
    by_category: Dict[str, Dict[str, Any]] = {}
    for c in per_case:
        cat = c.get("category", "unknown")
        bucket = by_category.setdefault(cat, {
            "count": 0, "improved": 0, "degraded": 0, "unchanged": 0,
            "_mrr_before": [], "_mrr_after": [],
            "_ndcg_before": [], "_ndcg_after": [],
        })
        bucket["count"] += 1
        bucket[c["impact"]] += 1
        bucket["_mrr_before"].append(c["mrr_before"])
        bucket["_mrr_after"].append(c["mrr_after"])
        bucket["_ndcg_before"].append(c["ndcg_before"])
        bucket["_ndcg_after"].append(c["ndcg_after"])

    for cat, bucket in by_category.items():
        bucket["mrr_before"] = round(statistics.mean(bucket.pop("_mrr_before")), 4)
        bucket["mrr_after"] = round(statistics.mean(bucket.pop("_mrr_after")), 4)
        bucket["mrr_lift"] = round(bucket["mrr_after"] - bucket["mrr_before"], 4)
        bucket["ndcg_before"] = round(statistics.mean(bucket.pop("_ndcg_before")), 4)
        bucket["ndcg_after"] = round(statistics.mean(bucket.pop("_ndcg_after")), 4)
        bucket["ndcg_lift"] = round(bucket["ndcg_after"] - bucket["ndcg_before"], 4)

    # Build verdict
    if mrr_delta > 0.01:
        verdict = (
            f"Reranker improves MRR by {mrr_delta:+.4f} "
            f"and NDCG@5 by {ndcg_delta:+.4f}. "
            f"{improved}/{n} cases improved, {degraded}/{n} degraded."
        )
    elif mrr_delta < -0.01:
        verdict = (
            f"Reranker DEGRADES MRR by {mrr_delta:+.4f}. "
            f"Consider disabling or tuning. "
            f"{degraded}/{n} cases degraded."
        )
    else:
        verdict = (
            f"Reranker has minimal impact (MRR delta {mrr_delta:+.4f}). "
            f"May not justify latency overhead."
        )

    return {
        "mode": "diagnostics",
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "suites": suites,
        "total_cases_analyzed": n,
        "without_reranker": {
            "mrr": mrr_before,
            "ndcg@5": ndcg_before,
        },
        "with_reranker": {
            "mrr": mrr_after,
            "ndcg@5": ndcg_after,
            "latency_percentiles": compute_latency_percentiles(latencies),
        },
        "comparison": {
            "mrr_delta": mrr_delta,
            "ndcg@5_delta": ndcg_delta,
            "cases_improved": improved,
            "cases_degraded": degraded,
            "cases_unchanged": unchanged,
            "improvement_rate": round(improved / n * 100, 1) if n else 0,
            "verdict": verdict,
        },
        "by_category": by_category,
        "per_case": per_case,
    }


# ---------------------------------------------------------------------------
# Live mode — run benchmark twice with config toggle
# ---------------------------------------------------------------------------

def _toggle_reranker(enabled: bool) -> None:
    """Toggle reranker.enabled in scoring_config.json."""
    with SCORING_CONFIG.open("r", encoding="utf-8") as f:
        config = json.load(f)

    config["reranker"]["enabled"] = enabled

    with SCORING_CONFIG.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[reranker_ab] Set reranker.enabled = {enabled}")


def run_live_ab() -> Dict[str, Any]:
    """Run benchmark twice — with and without reranker.

    WARNING: This modifies scoring_config.json and requires the
    RAG server to reload config between runs (restart or hot-reload).
    """
    from data.benchmarks.benchmark_retrieval import (
        _load_cases_from_file,
        evaluate_cases,
        CHECKS_ENDPOINT,
        MATURITY_ENDPOINT,
    )

    check_cases, maturity_cases = _load_cases_from_file()

    # Run A: with reranker (default)
    print("\n[reranker_ab] === Run A: WITH reranker ===")
    _toggle_reranker(True)
    print("[reranker_ab] Please ensure server has reloaded config.")
    input("[reranker_ab] Press Enter to continue...")

    checks_a = evaluate_cases(CHECKS_ENDPOINT, check_cases, "reranker_ab_checks_with")
    maturity_a = evaluate_cases(MATURITY_ENDPOINT, maturity_cases, "reranker_ab_maturity_with")

    # Run B: without reranker
    print("\n[reranker_ab] === Run B: WITHOUT reranker ===")
    _toggle_reranker(False)
    print("[reranker_ab] Please restart server or wait for config reload.")
    input("[reranker_ab] Press Enter to continue...")

    checks_b = evaluate_cases(CHECKS_ENDPOINT, check_cases, "reranker_ab_checks_without")
    maturity_b = evaluate_cases(MATURITY_ENDPOINT, maturity_cases, "reranker_ab_maturity_without")

    # Restore config
    _toggle_reranker(True)
    print("[reranker_ab] Restored reranker.enabled = true")

    # Build comparison
    summary_a = {
        "mrr": checks_a["summary"].get("mrr", 0),
        "ndcg@5": checks_a["summary"].get("ndcg@5", 0),
        "map@5": checks_a["summary"].get("map@5", 0),
        "average_latency_ms": checks_a["summary"].get("average_latency_ms"),
    }
    summary_b = {
        "mrr": checks_b["summary"].get("mrr", 0),
        "ndcg@5": checks_b["summary"].get("ndcg@5", 0),
        "map@5": checks_b["summary"].get("map@5", 0),
        "average_latency_ms": checks_b["summary"].get("average_latency_ms"),
    }

    mrr_delta = round(summary_a["mrr"] - summary_b["mrr"], 4)
    ndcg_delta = round(summary_a["ndcg@5"] - summary_b["ndcg@5"], 4)
    latency_delta = round(
        (summary_a["average_latency_ms"] or 0) - (summary_b["average_latency_ms"] or 0), 2
    )

    return {
        "mode": "live",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "with_reranker": summary_a,
        "without_reranker": summary_b,
        "comparison": {
            "mrr_delta": mrr_delta,
            "ndcg@5_delta": ndcg_delta,
            "latency_delta_ms": latency_delta,
            "verdict": (
                f"Reranker {'improves' if mrr_delta > 0 else 'degrades'} MRR by "
                f"{mrr_delta:+.4f} at cost of {latency_delta:+.0f}ms latency"
            ),
        },
        "checks_with": checks_a["summary"],
        "checks_without": checks_b["summary"],
        "maturity_with": maturity_a["summary"],
        "maturity_without": maturity_b["summary"],
    }


# ---------------------------------------------------------------------------
# Print
# ---------------------------------------------------------------------------

def print_ab_report(result: Dict[str, Any]) -> None:
    """Print a human-readable A/B comparison report."""
    print("\n" + "=" * 80)
    print("  RERANKER A/B COMPARISON")
    print("=" * 80)
    print(f"  Mode      : {result.get('mode', '?')}")
    print(f"  Source    : {result.get('source', 'live run')}")
    print(f"  Cases     : {result.get('total_cases_analyzed', '?')}")

    comp = result.get("comparison", {})
    wa = result.get("with_reranker", {})
    wo = result.get("without_reranker", {})

    print(f"\n  {'Metric':<20} {'Without Reranker':>18} {'With Reranker':>18} {'Delta':>12}")
    print(f"  {'-' * 68}")
    print(f"  {'MRR':<20} {wo.get('mrr', 0):>18.4f} {wa.get('mrr', 0):>18.4f}"
          f" {comp.get('mrr_delta', 0):>+12.4f}")
    print(f"  {'NDCG@5':<20} {wo.get('ndcg@5', 0):>18.4f} {wa.get('ndcg@5', 0):>18.4f}"
          f" {comp.get('ndcg@5_delta', 0):>+12.4f}")

    if comp.get("latency_delta_ms") is not None:
        print(f"  {'Latency (ms)':<20} {'':>18} {'':>18}"
              f" {comp['latency_delta_ms']:>+12.0f}")

    print(f"\n  Cases improved : {comp.get('cases_improved', '?')}")
    print(f"  Cases degraded : {comp.get('cases_degraded', '?')}")
    print(f"  Cases unchanged: {comp.get('cases_unchanged', '?')}")
    if comp.get("improvement_rate") is not None:
        print(f"  Improvement rate: {comp['improvement_rate']}%")

    # Per-category
    by_cat = result.get("by_category", {})
    if by_cat:
        print(f"\n  Per-category breakdown:")
        print(f"  {'Category':<16} {'MRR Lift':>10} {'NDCG Lift':>10}"
              f" {'Improved':>10} {'Degraded':>10}")
        print(f"  {'-' * 56}")
        for cat, data in by_cat.items():
            print(f"  {cat:<16} {data.get('mrr_lift', 0):>+10.4f}"
                  f" {data.get('ndcg_lift', 0):>+10.4f}"
                  f" {data.get('improved', 0):>10}"
                  f" {data.get('degraded', 0):>10}")

    print(f"\n  VERDICT: {comp.get('verdict', 'N/A')}")
    print("=" * 80)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Reranker A/B comparison benchmark")
    parser.add_argument(
        "--mode", choices=["diagnostics", "live"], default="diagnostics",
        help="Analysis mode (default: diagnostics — uses existing report data)",
    )
    parser.add_argument(
        "--report", type=str, default=None,
        help="Path to benchmark report JSON (diagnostics mode). "
             "Defaults to benchmark_latest.json",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.mode == "diagnostics":
        if args.report:
            report_path = Path(args.report)
        else:
            report_path = OUTPUT_DIR / "benchmark_latest.json"

        if not report_path.exists():
            print(f"[reranker_ab] Report not found: {report_path}")
            print("[reranker_ab] Run the benchmark first: python -m scripts.run_benchmark")
            sys.exit(1)

        print(f"[reranker_ab] Analyzing: {report_path}")
        result = analyze_from_report(report_path)
    else:
        result = run_live_ab()

    # Save
    output_path = OUTPUT_DIR / "benchmark_reranker_ab.json"
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n[reranker_ab] Saved: {output_path}")

    # Print
    if "error" not in result:
        print_ab_report(result)


if __name__ == "__main__":
    main()
