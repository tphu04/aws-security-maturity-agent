"""
RAG Integration Quality Evaluation Runner
============================================
Chay tat ca tests trong rag_evaluation suite va tao bao cao ket qua.

Usage:
    python -m tests.rag_evaluation.run_evaluation
    # hoac:
    python tests/rag_evaluation/run_evaluation.py
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def run_evaluation():
    """Chay pytest va tao bao cao."""
    import pytest

    test_dir = Path(__file__).parent
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Output paths
    report_dir = project_root / "tests" / "rag_evaluation" / "reports"
    report_dir.mkdir(exist_ok=True)

    junit_xml = report_dir / f"rag_eval_{timestamp}.xml"
    json_report = report_dir / f"rag_eval_{timestamp}.json"

    print("=" * 70)
    print("  RAG Integration Quality Evaluation")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Run pytest
    start_time = time.perf_counter()
    exit_code = pytest.main([
        str(test_dir),
        "-v",
        "--tb=short",
        f"--junitxml={junit_xml}",
        "-x" if "--fail-fast" in sys.argv else "",
        "--no-header",
    ])
    elapsed = time.perf_counter() - start_time

    print("\n" + "=" * 70)
    print(f"  Evaluation completed in {elapsed:.2f}s")
    print(f"  Exit code: {exit_code}")
    print(f"  JUnit XML: {junit_xml}")
    print("=" * 70)

    return exit_code


def run_with_summary():
    """Run with category-wise summary."""
    import pytest

    test_dir = Path(__file__).parent

    categories = {
        "Planning Agent RAG Quality": "test_planning_rag_quality.py",
        "Risk Agent RAG Quality": "test_risk_rag_quality.py",
        "Fallback & Degradation": "test_rag_fallback_degradation.py",
        "Performance Benchmarks": "test_rag_performance.py",
    }

    results = {}
    total_passed = 0
    total_failed = 0
    total_errors = 0

    for category, filename in categories.items():
        test_file = test_dir / filename
        if not test_file.exists():
            print(f"  SKIP: {filename} not found")
            continue

        print(f"\n{'─' * 60}")
        print(f"  {category}")
        print(f"{'─' * 60}")

        class ResultCollector:
            def __init__(self):
                self.passed = 0
                self.failed = 0
                self.errors = 0
                self.failures = []

            def pytest_runtest_logreport(self, report):
                if report.when == "call":
                    if report.passed:
                        self.passed += 1
                    elif report.failed:
                        self.failed += 1
                        self.failures.append(report.nodeid)
                elif report.when == "setup" and report.failed:
                    self.errors += 1

        collector = ResultCollector()
        pytest.main([
            str(test_file),
            "-v",
            "--tb=short",
            "--no-header",
            "-q",
        ], plugins=[collector])

        results[category] = {
            "passed": collector.passed,
            "failed": collector.failed,
            "errors": collector.errors,
            "failures": collector.failures,
            "total": collector.passed + collector.failed + collector.errors,
        }
        total_passed += collector.passed
        total_failed += collector.failed
        total_errors += collector.errors

    # Print summary
    print("\n" + "=" * 70)
    print("  EVALUATION SUMMARY")
    print("=" * 70)

    for category, data in results.items():
        status = "PASS" if data["failed"] == 0 and data["errors"] == 0 else "FAIL"
        icon = "[OK]" if status == "PASS" else "[!!]"
        print(f"  {icon} {category}: {data['passed']}/{data['total']} passed")
        if data["failures"]:
            for f in data["failures"]:
                print(f"      - FAILED: {f}")

    total = total_passed + total_failed + total_errors
    print(f"\n  Total: {total_passed}/{total} passed, {total_failed} failed, {total_errors} errors")
    pass_rate = (total_passed / total * 100) if total > 0 else 0
    print(f"  Pass rate: {pass_rate:.1f}%")
    print("=" * 70)

    # Save summary to JSON
    report_dir = Path(__file__).parent / "reports"
    report_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": total,
        "passed": total_passed,
        "failed": total_failed,
        "errors": total_errors,
        "pass_rate": round(pass_rate, 1),
        "categories": results,
    }
    summary_path = report_dir / f"summary_{timestamp}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\n  Summary saved to: {summary_path}")

    return 0 if total_failed == 0 and total_errors == 0 else 1


if __name__ == "__main__":
    if "--summary" in sys.argv:
        sys.exit(run_with_summary())
    else:
        sys.exit(run_evaluation())
