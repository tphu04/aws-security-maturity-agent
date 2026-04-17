"""
CLI entry point cho Generation Benchmark.

Usage:
    # Chay full pipeline (inference + evaluate)
    python benchmarks/llm_generation/run_gen_benchmark.py --mode full

    # Chi chay inference, luu output
    python benchmarks/llm_generation/run_gen_benchmark.py --mode inference-only

    # Chi evaluate tu inference da luu
    python benchmarks/llm_generation/run_gen_benchmark.py --mode evaluate-only --inference-dir benchmarks/llm_generation/inference_outputs/run_xxx

    # Chay khong co RAG (ablation)
    python benchmarks/llm_generation/run_gen_benchmark.py --mode full --no-rag
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

from benchmarks.llm_generation.benchmark_generation import (
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
    print("\n" + "=" * 60)
    print("GENERATION BENCHMARK RESULTS")
    print("=" * 60)
    print(f"Total cases: {report['total_cases']}")
    print()

    # 4 truc
    s = report["structure"]
    print(f"[Structure]")
    print(f"  JSON parse rate:         {s['json_parse_rate']:.2%}")
    print(f"  Schema compliance:       {s['schema_compliance_rate']:.2%}")
    print(f"  Internal consistency:    {s['internal_consistency_rate']:.2%}")

    f = report["faithfulness"]
    print(f"[Faithfulness]")
    print(f"  Mean score:              {f['mean']:.4f}")

    c = report["correctness"]
    print(f"[Correctness]")
    print(f"  Severity accuracy:       {c['severity_accuracy']:.2%}")
    print(f"  Severity QWK:            {c['severity_qwk']:.4f}")

    comp = report["completeness"]
    print(f"[Completeness]")
    print(f"  Evidence coverage:       {comp['evidence_coverage_mean']:.2%}")

    # By category
    print(f"\n[By Category]")
    for cat, data in report.get("by_category", {}).items():
        print(f"  {cat:15s}  n={data['total']}  acc={data['severity_accuracy']:.2%}  "
              f"faith={data['faithfulness_mean']:.2f}  comp={data['completeness_mean']:.2%}")

    # Release criteria
    rc = report.get("release_criteria", {})
    if rc:
        verdict = rc.get("verdict", "N/A")
        print(f"\n[Release Criteria] Verdict: {verdict}")
        for check in rc.get("checks", []):
            status = "PASS" if check["passed"] else "FAIL"
            print(f"  {status}  {check['criterion']:40s}  "
                  f"threshold={check['threshold']:.2f}  actual={check['actual']:.4f}")

    # Per-case details
    print(f"\n[Per-case Details]")
    for case in report.get("cases", []):
        d = case.get("debug", {})
        sev_ok = "OK" if case["correctness"]["severity_match"] else "MISS"
        print(f"  {case['case_id']:30s}  {sev_ok:4s}  "
              f"expected={d.get('expected_severity', '?'):8s}  "
              f"got={d.get('agent_severity', '?')!s:8s}  "
              f"faith={case['faithfulness']['score']:.2f}  "
              f"comp={case['completeness']['score']:.2f}")
        if d.get("inference_error"):
            print(f"    ERROR: {d['inference_error']}")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Generation Benchmark for Risk Evaluation Agent"
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
        help="Path to benchmark cases JSON (default: benchmark_gen_cases.json)",
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

    logger = logging.getLogger("run_gen_benchmark")

    # Load cases
    cases = load_cases(args.cases)

    # Create run directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = INFERENCE_DIR / f"run_{ts}"

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
