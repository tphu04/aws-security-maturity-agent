"""
Generate a Markdown summary dashboard from the latest benchmark report.

Reads benchmark_latest.json and produces a formatted Markdown document
suitable for pasting into reports, PR descriptions, or meeting notes.

Usage:
    python -m scripts.generate_dashboard
    python -m scripts.generate_dashboard --input path/to/report.json
    python -m scripts.generate_dashboard --output dashboard.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

SCRIPT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = SCRIPT_DIR / "data" / "benchmarks" / "benchmark_outputs" / "benchmark_latest.json"
DEFAULT_OUTPUT = SCRIPT_DIR / "data" / "benchmarks" / "benchmark_outputs" / "benchmark_dashboard.md"


def load_report(path: Path) -> Dict[str, Any]:
    """Load a benchmark report JSON file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _pct(value: Optional[float], multiplier: float = 100.0) -> str:
    """Format a float as percentage string."""
    if value is None:
        return "N/A"
    return f"{value * multiplier:.1f}%" if multiplier != 1.0 else f"{value:.1f}%"


def _fmt(value: Optional[float], decimals: int = 2) -> str:
    """Format a float with given decimal places."""
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def _status(passed: bool) -> str:
    """Return pass/fail indicator."""
    return "PASS" if passed else "FAIL"


def _check_threshold(actual: Optional[float], threshold: float, is_max: bool) -> str:
    """Check if actual meets threshold and return status."""
    if actual is None:
        return "N/A"
    if is_max:
        return "PASS" if actual <= threshold else "FAIL"
    return "PASS" if actual >= threshold else "FAIL"


def generate_dashboard(report: Dict[str, Any]) -> str:
    """Generate Markdown dashboard from a unified benchmark report."""
    lines: List[str] = []

    summary = report.get("combined_summary", {})
    criteria = report.get("release_criteria", {})
    checks_report = report.get("checks_report", {})
    maturity_report = report.get("maturity_report", {})
    checks_summary = checks_report.get("summary", {})
    maturity_summary = maturity_report.get("summary", {})

    timestamp = report.get("timestamp", "unknown")
    tag = report.get("tag", "")

    # --- Header ---
    lines.append(f"# RAG Benchmark Dashboard")
    lines.append("")
    lines.append(f"**Date**: {timestamp}  ")
    if tag:
        lines.append(f"**Tag**: {tag}  ")
    lines.append(f"**Total cases**: {summary.get('total_cases', 0)} (checks: {checks_summary.get('total_cases', 0)}, maturity: {maturity_summary.get('total_cases', 0)})")
    lines.append("")

    # --- Release Status ---
    verdict = criteria.get("verdict", "N/A")
    checks_list = criteria.get("checks", [])
    passed_count = sum(1 for c in checks_list if c.get("passed"))
    total_count = len(checks_list)
    verdict_icon = "PASS" if verdict == "PASS" else "FAIL"
    lines.append(f"## Release Status: {verdict_icon} ({passed_count}/{total_count} criteria)")
    lines.append("")

    # Criteria table
    lines.append("| Criterion | Threshold | Actual | Status |")
    lines.append("|-----------|-----------|--------|--------|")
    for check in checks_list:
        crit = check["criterion"]
        threshold = check["threshold"]
        actual = check.get("actual")
        passed = check.get("passed", True)
        note = check.get("note", "")
        actual_str = f"{actual}" if actual is not None else f"N/A ({note})"
        status = "PASS" if passed else "**FAIL**"
        lines.append(f"| {crit} | {threshold} | {actual_str} | {status} |")
    lines.append("")

    # --- Retrieval Quality ---
    lines.append("## Retrieval Quality")
    lines.append("")
    lines.append("| Metric | Checks | Maturity | Combined |")
    lines.append("|--------|--------|----------|----------|")

    c_total = checks_summary.get("total_cases", 0)
    m_total = maturity_summary.get("total_cases", 0)

    c_top1 = checks_summary.get("hit_expected_in_top1", 0)
    c_top5 = checks_summary.get("hit_expected_in_top5", 0)
    m_top1 = maturity_summary.get("hit_expected_in_top1", 0)
    m_top5 = maturity_summary.get("hit_expected_in_top5", 0)

    lines.append(
        f"| Hit Rate @1 | {c_top1}/{c_total} ({_pct(summary.get('checks_top1_rate'))}) "
        f"| {m_top1}/{m_total} ({_pct(summary.get('maturity_top1_rate'))}) "
        f"| {summary.get('combined_top1_hits', 0)}/{summary.get('total_cases', 0)} ({_pct(summary.get('combined_top1_rate'))}) |"
    )
    lines.append(
        f"| Hit Rate @5 | {c_top5}/{c_total} ({_pct(summary.get('checks_top5_rate'))}) "
        f"| {m_top5}/{m_total} ({_pct(summary.get('maturity_top5_rate'))}) "
        f"| {summary.get('combined_top5_hits', 0)}/{summary.get('total_cases', 0)} ({_pct(summary.get('combined_top5_rate'))}) |"
    )
    lines.append(
        f"| MRR | {_fmt(checks_summary.get('mrr'), 4)} "
        f"| {_fmt(maturity_summary.get('mrr'), 4)} "
        f"| {_fmt(summary.get('combined_mrr'), 4)} |"
    )
    lines.append(
        f"| NDCG@5 | {_fmt(checks_summary.get('ndcg@5'), 4)} "
        f"| {_fmt(maturity_summary.get('ndcg@5'), 4)} "
        f"| {_fmt(summary.get('combined_ndcg@5'), 4)} |"
    )
    lines.append(
        f"| MAP@5 | {_fmt(checks_summary.get('map@5'), 4)} "
        f"| {_fmt(maturity_summary.get('map@5'), 4)} "
        f"| {_fmt(summary.get('combined_map@5'), 4)} |"
    )
    lines.append("")

    # --- Robustness ---
    lines.append("## Robustness by Category")
    lines.append("")

    # Use checks by_category (primary) and maturity by_category
    checks_by_cat = checks_summary.get("by_category", {})
    maturity_by_cat = maturity_summary.get("by_category", {})

    lines.append("### Checks Retrieval")
    lines.append("")
    lines.append("| Category | Total | Top-1 | Top-5 | MRR | NDCG@5 | Avg Latency |")
    lines.append("|----------|-------|-------|-------|-----|--------|-------------|")
    for cat in ("exact", "paraphrase", "risk", "semantic_hard"):
        data = checks_by_cat.get(cat, {})
        if not data:
            continue
        lines.append(
            f"| {cat} | {data.get('total', 0)} "
            f"| {data.get('top1', 0)} ({_fmt(data.get('top1_rate', 0) * 100, 1)}%) "
            f"| {data.get('top5', 0)} "
            f"| {_fmt(data.get('mrr'), 4)} "
            f"| {_fmt(data.get('ndcg@5'), 4)} "
            f"| {_fmt(data.get('avg_latency_ms'), 0)}ms |"
        )

    gap = summary.get("robustness_gap", {})
    if gap and gap.get("best_category"):
        lines.append("")
        lines.append(
            f"**Robustness Gap**: {gap.get('gap_pp', 0)} pp "
            f"(best: {gap['best_category']} {_fmt(gap['best_value'], 2)}, "
            f"worst: {gap['worst_category']} {_fmt(gap['worst_value'], 2)})"
        )
    lines.append("")

    lines.append("### Maturity Retrieval")
    lines.append("")
    lines.append("| Category | Total | Top-1 | Top-5 | MRR | NDCG@5 | Avg Latency |")
    lines.append("|----------|-------|-------|-------|-----|--------|-------------|")
    for cat in ("exact", "paraphrase", "risk", "semantic_hard"):
        data = maturity_by_cat.get(cat, {})
        if not data:
            continue
        lines.append(
            f"| {cat} | {data.get('total', 0)} "
            f"| {data.get('top1', 0)} ({_fmt(data.get('top1_rate', 0) * 100, 1)}%) "
            f"| {data.get('top5', 0)} "
            f"| {_fmt(data.get('mrr'), 4)} "
            f"| {_fmt(data.get('ndcg@5'), 4)} "
            f"| {_fmt(data.get('avg_latency_ms'), 0)}ms |"
        )
    lines.append("")

    # --- Reranker Impact ---
    checks_rl = checks_summary.get("reranker_lift", {})
    maturity_rl = maturity_summary.get("reranker_lift", {})
    if checks_rl or maturity_rl:
        lines.append("## Reranker Impact")
        lines.append("")
        lines.append("| Suite | Metric | Before | After | Lift | Improved | Degraded | Unchanged |")
        lines.append("|-------|--------|--------|-------|------|----------|----------|-----------|")
        if checks_rl:
            lines.append(
                f"| Checks | MRR | {_fmt(checks_rl.get('mrr_before'), 4)} "
                f"| {_fmt(checks_rl.get('mrr_after'), 4)} "
                f"| {_fmt(checks_rl.get('mrr_lift'), 4)} "
                f"| {checks_rl.get('cases_improved', 0)} "
                f"| {checks_rl.get('cases_degraded', 0)} "
                f"| {checks_rl.get('cases_unchanged', 0)} |"
            )
            lines.append(
                f"| Checks | NDCG@5 | {_fmt(checks_rl.get('ndcg_before'), 4)} "
                f"| {_fmt(checks_rl.get('ndcg_after'), 4)} "
                f"| {_fmt(checks_rl.get('ndcg_lift'), 4)} "
                f"| | | |"
            )
        if maturity_rl and maturity_rl.get("cases_with_data", 0) > 0:
            lines.append(
                f"| Maturity | MRR | {_fmt(maturity_rl.get('mrr_before'), 4)} "
                f"| {_fmt(maturity_rl.get('mrr_after'), 4)} "
                f"| {_fmt(maturity_rl.get('mrr_lift'), 4)} "
                f"| {maturity_rl.get('cases_improved', 0)} "
                f"| {maturity_rl.get('cases_degraded', 0)} "
                f"| {maturity_rl.get('cases_unchanged', 0)} |"
            )
        lines.append("")

    # --- Confidence Calibration ---
    cal = summary.get("confidence_calibration", {})
    if cal and cal.get("total_cases", 0) > 0:
        lines.append("## Confidence Calibration")
        lines.append("")
        lines.append(f"**Combined ECE**: {_fmt(cal.get('ece'), 4)}  ")
        lines.append(f"**Overall Calibrated**: {'Yes' if cal.get('overall_calibrated') else 'No'}")
        lines.append("")

        lines.append("### Combined")
        lines.append("")
        lines.append("| Level | Count | Actual Accuracy | Expected | Calibrated |")
        lines.append("|-------|-------|-----------------|----------|------------|")
        for level in ("high", "medium", "low"):
            bin_data = cal.get(level, {})
            if not isinstance(bin_data, dict):
                continue
            count = bin_data.get("count", 0)
            acc = bin_data.get("actual_accuracy")
            acc_str = f"{acc * 100:.1f}%" if acc is not None else "-"
            calibrated = bin_data.get("calibrated")
            cal_str = "Yes" if calibrated is True else ("No" if calibrated is False else "N/A")
            expected = ""
            if "expected_min" in bin_data and "expected_max" in bin_data:
                expected = f"{bin_data['expected_min'] * 100:.0f}%-{bin_data['expected_max'] * 100:.0f}%"
            elif "expected_min" in bin_data:
                expected = f">= {bin_data['expected_min'] * 100:.0f}%"
            elif "expected_max" in bin_data:
                expected = f"< {bin_data['expected_max'] * 100:.0f}%"
            lines.append(f"| {level} | {count} | {acc_str} | {expected} | {cal_str} |")
        lines.append("")

        # Per-route
        by_route = summary.get("confidence_calibration_by_route", {})
        if by_route:
            lines.append("### Per Route Type")
            lines.append("")
            lines.append("| Route | ECE | High (count/acc) | Medium (count/acc) | Low (count/acc) | Calibrated |")
            lines.append("|-------|-----|-------------------|--------------------|-----------------| -----------|")
            for route, rcal in by_route.items():
                if not isinstance(rcal, dict) or rcal.get("total_cases", 0) == 0:
                    continue
                ece = _fmt(rcal.get("ece"), 4)
                overall_cal = "Yes" if rcal.get("overall_calibrated") else "No"

                parts = []
                for level in ("high", "medium", "low"):
                    bd = rcal.get(level, {})
                    if not isinstance(bd, dict):
                        parts.append("-")
                        continue
                    c = bd.get("count", 0)
                    a = bd.get("actual_accuracy")
                    a_str = f"{a * 100:.0f}%" if a is not None else "-"
                    parts.append(f"{c} / {a_str}")

                lines.append(f"| {route} | {ece} | {parts[0]} | {parts[1]} | {parts[2]} | {overall_cal} |")
            lines.append("")

    # --- Performance ---
    lines.append("## Performance")
    lines.append("")

    lat_p = summary.get("latency_percentiles", {})
    lines.append("| Metric | Checks | Maturity | Combined |")
    lines.append("|--------|--------|----------|----------|")

    c_lat = checks_summary.get("latency_percentiles", {})
    m_lat = maturity_summary.get("latency_percentiles", {})
    for label, key in [("Mean", "mean_ms"), ("P50", "p50_ms"), ("P90", "p90_ms"), ("P99", "p99_ms")]:
        lines.append(
            f"| {label} | {_fmt(c_lat.get(key), 0)}ms "
            f"| {_fmt(m_lat.get(key), 0)}ms "
            f"| {_fmt(lat_p.get(key), 0)}ms |"
        )
    lines.append("")

    # Safety metrics
    lines.append("## Safety Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Forbidden Capability Rate | {summary.get('forbidden_capability_rate_pct', 0.0)}% |")
    svc_prec = summary.get("service_precision_pct")
    lines.append(f"| Service Precision | {svc_prec}% |" if svc_prec is not None else "| Service Precision | N/A |")
    lines.append("")

    # --- By Service ---
    by_service = checks_summary.get("by_service", {})
    if by_service:
        lines.append("## By Service (Checks)")
        lines.append("")
        lines.append("| Service | Total | Top-1 | Top-5 | Svc Correct |")
        lines.append("|---------|-------|-------|-------|-------------|")
        for svc, data in sorted(by_service.items()):
            svc_corr = data.get("service_correct", "-")
            lines.append(
                f"| {svc} | {data.get('total', 0)} "
                f"| {data.get('top1', 0)} "
                f"| {data.get('top5', 0)} "
                f"| {svc_corr}/{data.get('total', 0)} |"
            )
        lines.append("")

    # --- Footer ---
    lines.append("---")
    lines.append(f"*Generated from `benchmark_latest.json` on {timestamp}*")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate RAG benchmark dashboard (Markdown)")
    parser.add_argument(
        "--input", type=str, default=None,
        help=f"Path to benchmark report JSON (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Path for output Markdown file (default: stdout + save to benchmark_outputs/)",
    )
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else DEFAULT_INPUT
    if not input_path.exists():
        print(f"[ERROR] Report not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    report = load_report(input_path)
    dashboard = generate_dashboard(report)

    # Always print to stdout
    print(dashboard)

    # Save to file
    output_path = Path(args.output) if args.output else DEFAULT_OUTPUT
    output_path.write_text(dashboard, encoding="utf-8")
    print(f"\n[dashboard] Saved to: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
