"""Compare baseline vs MVP benchmark results and print a summary table.

Usage
-----
    python -m benchmarks.llm_generation.compare_results \
        --baseline results/baseline_single_query.json \
        --mvp     results/mvp_multi_query.json
"""
# ---------------------------------------------------------------------------
# Langfuse bench guard (Phase F.7) — runner default OFF, dev có thể override.
# ---------------------------------------------------------------------------
import os as _os_bench_guard
_os_bench_guard.environ.setdefault("LANGFUSE_ENABLED", "false")

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BENCHMARK_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BENCHMARK_DIR / "results"

KEY_METRICS = [
    ("numerical_faithfulness",    "Numerical Faithfulness", True),   # (key, label, higher_is_better)
    ("capability_grounding_rate", "Capability Grounding",   True),
    ("ndcg_at_5_severity",        "NDCG@5 Severity",        True),
    ("structure_pass_rate",       "Structure Pass Rate",     True),
    ("off_scope_mention_rate",    "Off-Scope Rate",          False),  # lower is better
    ("template_data_accuracy",    "Template Accuracy",       True),
]


def _mean(result: Dict[str, Any], metric: str) -> Optional[float]:
    return (result.get("summary", {}).get("overall", {}).get(metric) or {}).get("mean")


def _delta_str(base: Optional[float], mvp: Optional[float], higher_is_better: bool) -> str:
    if base is None or mvp is None:
        return "N/A"
    delta = mvp - base
    pct = (delta / base * 100) if base != 0 else 0.0
    arrow = ""
    if higher_is_better:
        arrow = "++" if delta > 0.001 else ("--" if delta < -0.001 else "==")
    else:
        arrow = "--" if delta < -0.001 else ("++" if delta > 0.001 else "==")
    return f"{arrow} {delta:+.4f} ({pct:+.1f}%)"


def compare(baseline_path: Path, mvp_path: Path) -> None:
    base = json.loads(baseline_path.read_text(encoding="utf-8"))
    mvp = json.loads(mvp_path.read_text(encoding="utf-8"))

    print(f"\n{'='*72}")
    print(f"  Baseline : {baseline_path.name}  (verdict={base.get('release',{}).get('verdict','?')})")
    print(f"  MVP      : {mvp_path.name}  (verdict={mvp.get('release',{}).get('verdict','?')})")
    print(f"{'='*72}")

    col_w = 26
    header = f"{'Metric':<{col_w}} {'Baseline':>10} {'MVP':>10} {'Delta':>20}"
    print(f"\n{header}")
    print("-" * len(header))

    improvements = 0
    regressions = 0
    for key, label, hib in KEY_METRICS:
        b_val = _mean(base, key)
        m_val = _mean(mvp, key)
        b_str = f"{b_val:.4f}" if b_val is not None else "N/A"
        m_str = f"{m_val:.4f}" if m_val is not None else "N/A"
        d_str = _delta_str(b_val, m_val, hib)
        print(f"{label:<{col_w}} {b_str:>10} {m_str:>10} {d_str:>20}")
        if b_val is not None and m_val is not None:
            delta = m_val - b_val
            improved = (delta > 0.001 and hib) or (delta < -0.001 and not hib)
            regressed = (delta < -0.001 and hib) or (delta > 0.001 and not hib)
            if improved:
                improvements += 1
            elif regressed:
                regressions += 1

    print("-" * len(header))
    print(f"\nSummary: {improvements} improved, {regressions} regressed, "
          f"{len(KEY_METRICS) - improvements - regressions} unchanged")

    # Target check: faithfulness +10% over baseline
    b_faith = _mean(base, "numerical_faithfulness")
    m_faith = _mean(mvp, "numerical_faithfulness")
    if b_faith and m_faith:
        target = b_faith * 1.10
        status = "PASS" if m_faith >= target else "FAIL"
        print(f"\nG2 target (faithfulness >= baseline+10%): {status}")
        print(f"  Required: {target:.4f}  Actual: {m_faith:.4f}")

    # Per-case comparison for weakest metrics
    print(f"\n{'='*72}")
    print("  Per-case delta — numerical_faithfulness")
    print(f"{'='*72}")
    base_cases = {c["case_id"]: c for c in base.get("cases", [])}
    mvp_cases = {c["case_id"]: c for c in mvp.get("cases", [])}
    deltas = []
    for cid, mc in mvp_cases.items():
        bc = base_cases.get(cid)
        if not bc:
            continue
        def _score(c):
            v = c.get("metrics", {}).get("numerical_faithfulness")
            return v.get("score") if isinstance(v, dict) else v
        b_s = _score(bc)
        m_s = _score(mc)
        if b_s is not None and m_s is not None:
            deltas.append((cid, b_s, m_s, m_s - b_s))

    deltas.sort(key=lambda x: x[3])
    print(f"  {'Case':<40} {'Base':>6} {'MVP':>6} {'Delta':>8}")
    for cid, b_s, m_s, d in deltas:
        marker = " [WORSE]" if d < -0.05 else (" [BETTER]" if d > 0.05 else "")
        print(f"  {cid:<40} {b_s:>6.4f} {m_s:>6.4f} {d:>+8.4f}{marker}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path,
                        default=RESULTS_DIR / "baseline_single_query.json")
    parser.add_argument("--mvp", type=Path,
                        default=RESULTS_DIR / "mvp_multi_query.json")
    args = parser.parse_args()

    if not args.baseline.exists():
        print(f"ERROR: baseline not found: {args.baseline}", file=sys.stderr)
        return 1
    if not args.mvp.exists():
        print(f"ERROR: MVP result not found: {args.mvp}", file=sys.stderr)
        return 1

    compare(args.baseline, args.mvp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
