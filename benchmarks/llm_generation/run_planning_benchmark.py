"""
CLI entry point cho Planning Agent Generation Benchmark.

Usage:
    # Chay full pipeline (inference + evaluate)
    python benchmarks/llm_generation/run_planning_benchmark.py --mode full

    # Chi chay inference, luu output
    python benchmarks/llm_generation/run_planning_benchmark.py --mode inference-only

    # Chi evaluate tu inference da luu
    python benchmarks/llm_generation/run_planning_benchmark.py --mode evaluate-only --inference-dir benchmarks/llm_generation/inference_outputs/run_xxx

    # Chay khong co RAG (ablation)
    python benchmarks/llm_generation/run_planning_benchmark.py --mode full --no-rag
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.llm_generation.benchmark_planning import (
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
    print("PLANNING AGENT — GENERATION BENCHMARK RESULTS")
    print("=" * 70)
    print(f"Total cases: {report['total_cases']}")
    print()

    # Structure
    s = report["structure"]
    print("[Structure]")
    print(f"  Valid output rate:       {s['valid_output_rate']:.2%}")

    # Faithfulness
    f = report["faithfulness"]
    print("[Faithfulness]")
    print(f"  Grounded reasoning:      {f['grounded_reasoning_rate']:.4f}")

    # Correctness
    c = report["correctness"]
    print("[Correctness]")
    print(f"  Check Selection F1:      {c['check_selection_f1']:.4f}  "
          f"(P={c['check_selection_precision']:.4f}, R={c['check_selection_recall']:.4f})")
    print(f"  Avg Predicted Checks:    {c.get('avg_predicted_checks', 0):.2f}")
    print(f"  Avg Ground Truth Checks: {c.get('avg_gt_checks', 0):.2f}")
    print(f"  Over-selection rate:     {c['over_selection_rate']:.4f}  "
          f"(FP/predicted — low is better)")
    print(f"  Under-selection rate:    {c['under_selection_rate']:.4f}  "
          f"(FN/relevant — low is better)")
    print(f"  Exact Match rate:        {c['exact_match_rate']:.2%}")
    print(f"  Service Accuracy:        {c['service_accuracy']:.2%}")
    print(f"  Planning Correctness:    {c['planning_correctness']:.4f}  "
          f"(0.7*F1 + 0.3*SA)")
    print(f"  Cases: {c['specific_cases']} specific, "
          f"{c['group_cases']} group, {c['error_cases']} error")

    # Completeness
    comp = report["completeness"]
    print("[Completeness]")
    print(f"  Action Type Accuracy:    {comp['action_type_accuracy']:.2%}")

    # By input_type
    print(f"\n[By Input Type]")
    for t, data in report.get("by_input_type", {}).items():
        f1_str = f"F1={data['f1_mean']:.2f}" if data.get("f1_mean") is not None else "F1=N/A"
        svc_str = f"svc={data['service_accuracy']:.2%}" if data.get("service_accuracy") is not None else "svc=N/A"
        over_str = f"over={data['over_selection_rate']:.2f}" if data.get("over_selection_rate") is not None else "over=N/A"
        under_str = f"under={data['under_selection_rate']:.2f}" if data.get("under_selection_rate") is not None else "under=N/A"
        em_str = f"EM={data['exact_match_rate']:.0%}" if data.get("exact_match_rate") is not None else "EM=N/A"
        print(f"  {t:20s}  n={data['total']}  {f1_str}  {svc_str}  "
              f"action={data['action_type_accuracy']:.2%}  "
              f"faith={data['faithfulness_mean']:.2f}  "
              f"{over_str}  {under_str}  {em_str}")

    # Release criteria
    rc = report.get("release_criteria", {})
    if rc:
        verdict = rc.get("verdict", "N/A")
        print(f"\n[Release Criteria] Verdict: {verdict}")
        for check in rc.get("checks", []):
            status = "PASS" if check["passed"] else "FAIL"
            print(f"  {status}  {check['criterion']:35s}  "
                  f"threshold={check['threshold']:.2f}  actual={check['actual']:.4f}")

    # Per-case details
    print(f"\n[Per-case Details]")
    for case in report.get("cases", []):
        d = case.get("debug", {})
        corr = case["correctness"]
        action = case["completeness"]["action_type"]

        if corr["output_type"] == "specific_checks":
            corr_str = f"F1={corr['f1']:.2f}" if corr.get("f1") is not None else "F1=?"
            sel = case.get("selection_analysis", {})
            over_r = sel.get("over_selection", {}).get("over_selection_rate")
            under_r = sel.get("under_selection", {}).get("under_selection_rate")
            em = sel.get("exact_match", {}).get("exact_match")
            sel_str = (f"  over={over_r:.2f}" if over_r is not None else "") + \
                      (f"  under={under_r:.2f}" if under_r is not None else "") + \
                      (f"  EM={'Y' if em else 'N'}" if em is not None else "")
        elif corr["output_type"] == "group_scan":
            corr_str = f"svc={'OK' if corr.get('service_correct') else 'MISS'}"
            sel_str = ""
        else:
            corr_str = "ERR"
            sel_str = ""

        action_str = "OK" if action["correct"] else "MISS"

        print(f"  {case['case_id']:35s}  {corr['output_type']:15s}  "
              f"{corr_str:10s}  action={action_str:4s}  "
              f"faith={case['faithfulness']['score']:.2f}{sel_str}")

        if d.get("agent_error"):
            print(f"    ERROR: {d['agent_error'][:80]}")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Generation Benchmark for Planning Agent"
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
        help="Path to benchmark cases JSON (default: benchmark_planning_cases.json)",
    )
    parser.add_argument(
        "--no-rag",
        action="store_true",
        help="Run without RAG (ablation test)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    logger = logging.getLogger("run_planning_benchmark")

    # Load cases
    cases = load_cases(args.cases)

    # Create run directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = INFERENCE_DIR / f"planning_run_{ts}"

    if args.mode in ("full", "inference-only"):
        logger.info("Starting inference (%d cases, rag=%s)", len(cases), not args.no_rag)
        outputs = run_inference(cases, rag_enabled=not args.no_rag)
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
