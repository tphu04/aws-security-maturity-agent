"""
Ablation study: BM25-only vs Vector-only vs Hybrid.

Runs the Tier 1 benchmark (benchmark_cases.json) with three different
retrieval_mode settings and compares MRR, Top-1, Top-5 across modes.
"""

from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_URL = "http://localhost:8000"
CHECKS_ENDPOINT = f"{BASE_URL}/v1/retrieve/checks"
MATURITY_ENDPOINT = f"{BASE_URL}/v1/retrieve/maturity"
TIMEOUT = 60

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "benchmark_outputs"
CASES_FILE = SCRIPT_DIR / "benchmark_cases.json"


def load_cases():
    with CASES_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("check_cases", []), data.get("maturity_cases", [])


def run_single(endpoint: str, query: str, mode: str, top_k: int = 5) -> Dict[str, Any]:
    payload = {"query": query, "top_k": top_k, "retrieval_mode": mode}
    t0 = time.perf_counter()
    try:
        resp = requests.post(endpoint, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        latency = (time.perf_counter() - t0) * 1000
        d = resp.json()
        results = d.get("data", {}).get("results", [])
        meta = d.get("meta", {})
        return {
            "top_ids": [r.get("doc_id") for r in results],
            "latency_ms": latency,
            "confidence": meta.get("confidence"),
            "status": resp.status_code,
        }
    except Exception as exc:
        return {
            "top_ids": [],
            "latency_ms": (time.perf_counter() - t0) * 1000,
            "error": str(exc),
            "status": 0,
        }


def evaluate_mode(mode: str, check_cases: List, maturity_cases: List) -> Dict[str, Any]:
    """Run all cases with a given retrieval_mode and compute metrics."""
    results = []

    # Filter out negative cases (no expected_doc_id)
    valid_checks = [c for c in check_cases if c.get("expected_doc_id")]
    valid_maturity = [c for c in maturity_cases if c.get("expected_doc_id")]

    for case in valid_checks:
        r = run_single(CHECKS_ENDPOINT, case["query"], mode)
        expected = case["expected_doc_id"]
        top_ids = r["top_ids"]
        hit_top1 = len(top_ids) > 0 and top_ids[0] == expected
        hit_top5 = expected in top_ids[:5]
        rr = 1.0 / (top_ids.index(expected) + 1) if expected in top_ids else 0.0
        results.append({
            "case_id": case["case_id"],
            "category": case["category"],
            "type": "check",
            "hit_top1": hit_top1,
            "hit_top5": hit_top5,
            "reciprocal_rank": rr,
            "latency_ms": r["latency_ms"],
        })

    for case in valid_maturity:
        r = run_single(MATURITY_ENDPOINT, case["query"], mode)
        expected = case["expected_doc_id"]
        top_ids = r["top_ids"]
        hit_top1 = len(top_ids) > 0 and top_ids[0] == expected
        hit_top5 = expected in top_ids[:5]
        rr = 1.0 / (top_ids.index(expected) + 1) if expected in top_ids else 0.0
        results.append({
            "case_id": case["case_id"],
            "category": case["category"],
            "type": "maturity",
            "hit_top1": hit_top1,
            "hit_top5": hit_top5,
            "reciprocal_rank": rr,
            "latency_ms": r["latency_ms"],
        })

    total = len(results)
    top1 = sum(1 for r in results if r["hit_top1"])
    top5 = sum(1 for r in results if r["hit_top5"])
    mrr = sum(r["reciprocal_rank"] for r in results) / total if total else 0
    avg_lat = sum(r["latency_ms"] for r in results) / total if total else 0

    # By category
    from collections import Counter
    cats = {}
    for cat in set(r["category"] for r in results):
        cat_results = [r for r in results if r["category"] == cat]
        n = len(cat_results)
        cats[cat] = {
            "total": n,
            "top1": sum(1 for r in cat_results if r["hit_top1"]),
            "top5": sum(1 for r in cat_results if r["hit_top5"]),
            "mrr": sum(r["reciprocal_rank"] for r in cat_results) / n if n else 0,
        }

    return {
        "mode": mode,
        "total": total,
        "top1": top1,
        "top1_rate": top1 / total if total else 0,
        "top5": top5,
        "top5_rate": top5 / total if total else 0,
        "mrr": mrr,
        "avg_latency_ms": avg_lat,
        "by_category": cats,
        "cases": results,
    }


def main():
    print(f"[ablation] Running ablation study: lexical vs vector vs hybrid")
    print(f"[ablation] Base URL: {BASE_URL}")
    print(f"[ablation] Timestamp: {datetime.now(timezone.utc).isoformat()}\n")

    # Health check
    try:
        requests.get(f"{BASE_URL}/health", timeout=5).raise_for_status()
    except Exception as exc:
        print(f"Server not available: {exc}")
        sys.exit(1)

    check_cases, maturity_cases = load_cases()
    print(f"Loaded {len(check_cases)} check + {len(maturity_cases)} maturity cases\n")

    modes = ["lexical", "vector", "hybrid"]
    all_results = {}

    for mode in modes:
        print(f"--- Running mode: {mode} ---")
        result = evaluate_mode(mode, check_cases, maturity_cases)
        all_results[mode] = result
        print(f"  Top-1: {result['top1']}/{result['total']} ({result['top1_rate']:.1%})")
        print(f"  Top-5: {result['top5']}/{result['total']} ({result['top5_rate']:.1%})")
        print(f"  MRR:   {result['mrr']:.4f}")
        print(f"  Avg latency: {result['avg_latency_ms']:.0f}ms\n")

    # Comparison table
    print("=" * 70)
    print("ABLATION COMPARISON")
    print("=" * 70)
    print(f"{'Metric':<25} {'BM25-only':>12} {'Vector-only':>12} {'Hybrid':>12}")
    print("-" * 61)

    for metric, key in [
        ("Top-1 Accuracy", "top1_rate"),
        ("Top-5 Accuracy", "top5_rate"),
        ("MRR", "mrr"),
        ("Avg Latency (ms)", "avg_latency_ms"),
    ]:
        vals = []
        for mode in modes:
            v = all_results[mode][key]
            if "rate" in key or key == "mrr":
                vals.append(f"{v:.1%}" if "rate" in key else f"{v:.4f}")
            else:
                vals.append(f"{v:.0f}")
        print(f"{metric:<25} {vals[0]:>12} {vals[1]:>12} {vals[2]:>12}")

    # By-category breakdown for each mode
    print()
    all_cats = sorted(set(
        cat for mode in modes for cat in all_results[mode]["by_category"]
    ))
    for cat in all_cats:
        print(f"\n  {cat}:")
        for mode in modes:
            c = all_results[mode]["by_category"].get(cat, {})
            if c:
                t1r = c["top1"] / c["total"] * 100 if c["total"] else 0
                print(f"    {mode:<10} top1={c['top1']:>2}/{c['total']:<2} ({t1r:>5.1f}%)  mrr={c['mrr']:.3f}")

    # Save
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "modes": all_results,
    }
    output_path = OUTPUT_DIR / "benchmark_ablation_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n[saved] {output_path}")


if __name__ == "__main__":
    main()
