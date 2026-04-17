"""
CLI entry point cho Report Agent Benchmark.

Usage:
    # Chay full pipeline (inference + evaluate)
    python benchmarks/llm_generation/run_report_benchmark.py --mode full

    # Chi chay inference, luu output
    python benchmarks/llm_generation/run_report_benchmark.py --mode inference-only

    # Chi evaluate tu inference da luu
    python benchmarks/llm_generation/run_report_benchmark.py --mode evaluate-only --inference-dir benchmarks/llm_generation/inference_outputs/report_run_xxx

    # Custom test cases
    python benchmarks/llm_generation/run_report_benchmark.py --mode full --cases custom_cases.json

All core metrics are DETERMINISTIC (chi phi = 0, khong can LLM judge).
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.llm_generation.benchmark_report import (
    INFERENCE_DIR,
    aggregate_results,
    load_cases,
    load_inference,
    run_evaluation,
    run_inference,
    save_inference,
    save_report,
)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def print_summary(report: dict) -> None:
    """In tom tat ket qua ra console."""
    print("\n" + "=" * 70)
    print("REPORT AGENT BENCHMARK RESULTS")
    print("=" * 70)
    print(f"Total cases: {report['total_cases']}")
    print()

    # Structure (gate check)
    s = report["structure"]
    print("[Structure — Gate Check]")
    print(f"  HTML valid:              {s['html_valid_rate']:.2%}")
    print(f"  Section presence:        {s['section_presence_rate']:.2%}")
    print(f"  No template leak:        {s['no_template_leak_rate']:.2%}")
    print(f"  No None display:         {s['no_none_display_rate']:.2%}")
    print(f"  Cover page complete:     {s['cover_page_rate']:.2%}")
    print(f"  Chart presence:          {s['chart_presence_rate']:.2%}")
    print(f"  --- Gate PASS rate:      {s['gate_pass_rate']:.2%}")

    # Correctness
    c = report["correctness"]
    print(f"\n[Correctness — Deterministic]")
    print(f"  Stats accuracy:          {c['stats_accuracy']:.2%}")
    print(f"  Findings table accuracy: {c['findings_table_accuracy']:.2%}")
    print(f"  Score accuracy:          {c['score_accuracy']:.2%}")
    print(f"  Status color accuracy:   {c['status_color_accuracy']:.2%}")

    # Faithfulness
    f = report["faithfulness"]
    print(f"\n[Faithfulness — Numerical]")
    print(f"  Numerical faithfulness:  {f['numerical_faithfulness']:.4f}")

    # Completeness
    comp = report["completeness"]
    print(f"\n[Completeness]")
    print(f"  Findings coverage:       {comp['findings_coverage']:.2%}")
    print(f"  Bypass correctness:      {comp['conditional_bypass_correctness']:.2%}")

    # By group
    print(f"\n[By Group]")
    for grp, data in report.get("by_group", {}).items():
        print(f"  {grp:20s}  n={data['total']}  gate={data['gate_pass_rate']:.2%}  "
              f"stats={data['stats_accuracy']:.2%}  faith={data['faithfulness']:.2f}  "
              f"coverage={data['findings_coverage']:.2%}")

    # By scenario
    print(f"\n[By Scenario]")
    for scn, data in report.get("by_scenario", {}).items():
        print(f"  {scn:25s}  n={data['total']}  gate={data['gate_pass_rate']:.2%}  "
              f"stats={data['stats_accuracy']:.2%}  faith={data['faithfulness']:.2f}")

    # Release criteria
    rc = report.get("release_criteria", {})
    if rc:
        verdict = rc.get("verdict", "N/A")
        print(f"\n[Release Criteria] Verdict: {verdict}")
        for check in rc.get("checks", []):
            status = "PASS" if check["passed"] else "FAIL"
            print(f"  {status}  {check['criterion']:45s}  "
                  f"threshold={check['threshold']:.2f}  actual={check['actual']:.4f}")

    # Per-case details
    print(f"\n[Per-case Details]")
    for case in report.get("cases", []):
        d = case.get("debug", {})
        gate = "GATE" if d.get("gate_passed") else "FAIL"
        scenario = case.get("scenario", "?")
        bug = case.get("bug_regression", "")
        bug_str = f"  [{bug}]" if bug else ""

        struct_ok = case["structure"]["hard_pass"]
        stats = case["correctness"]["stats_accuracy"]
        faith = case["faithfulness"]["score"]
        coverage = case["completeness"]["findings_coverage"]

        print(f"  {case['case_id']:35s}  {gate:4s}  {scenario:20s}"
              f"  stats={stats:.2f}  faith={faith:.2f}  cov={coverage:.2f}{bug_str}")

        if d.get("inference_error"):
            print(f"    ERROR: {d['inference_error']}")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Report Agent Benchmark — all deterministic metrics"
    )
    parser.add_argument(
        "--mode",
        choices=["full", "inference-only", "evaluate-only"],
        default="full",
        help="Pipeline mode (default: full)",
    )
    parser.add_argument(
        "--inference-dir",
        help="Path to inference outputs dir (required for evaluate-only)",
    )
    parser.add_argument(
        "--cases",
        default=None,
        help="Path to benchmark cases JSON (default: benchmark_report_cases.json)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    logger = logging.getLogger("run_report_benchmark")

    # Load cases
    cases = load_cases(args.cases)

    # Create run directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = INFERENCE_DIR / f"report_run_{ts}"

    if args.mode in ("full", "inference-only"):
        logger.info("Starting inference (%d cases)", len(cases))
        outputs = run_inference(cases)
        save_inference(outputs, run_dir)

        if args.mode == "inference-only":
            logger.info("Inference-only mode — done. Results in %s", run_dir)
            return

    elif args.mode == "evaluate-only":
        if not args.inference_dir:
            parser.error("--inference-dir is required for evaluate-only mode")
        outputs = load_inference(args.inference_dir)
        run_dir = Path(args.inference_dir)

    # Evaluate
    logger.info("Starting evaluation...")
    evaluated = run_evaluation(cases, outputs)

    # Aggregate
    report = aggregate_results(evaluated)

    # Save
    filepath = save_report(report)

    # Print summary
    print_summary(report)

    logger.info("Done. Report: %s", filepath)


if __name__ == "__main__":
    main()
