"""LLM Judge runner — Day 2 qualitative metrics.

Runs FaithfulnessJudge (claim_support_rate) and ActionabilityJudge
(actionability_likert) on benchmark HTML outputs.

Usage
-----
    # Score baseline HTMLs (inference_outputs/report_v3/):
    python -m benchmarks.llm_generation.run_llm_judge --mode baseline

    # Score MVP HTMLs (inference_outputs/report_v3/):
    python -m benchmarks.llm_generation.run_llm_judge --mode mvp

    # Score both and compare:
    python -m benchmarks.llm_generation.run_llm_judge --mode compare

    # Score from a specific inference dir:
    python -m benchmarks.llm_generation.run_llm_judge \
        --inference-dir benchmarks/llm_generation/inference_outputs/report_v3 \
        --out results/judge_mvp.json

Requires GROQ_API_KEY in .env (primary) or GOOGLE_API_KEY (fallback).
"""
# ---------------------------------------------------------------------------
# Langfuse bench guard (Phase F.7) — runner default OFF, dev có thể override.
# ---------------------------------------------------------------------------
import os as _os_bench_guard
_os_bench_guard.environ.setdefault("LANGFUSE_ENABLED", "false")

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.llm_generation.report_judges import JudgeCache, judge_case  # noqa: E402

logger = logging.getLogger(__name__)

BENCHMARK_DIR = Path(__file__).resolve().parent
DEFAULT_CASES = BENCHMARK_DIR / "benchmark_report_cases_v3.json"
INFERENCE_DIR = BENCHMARK_DIR / "inference_outputs" / "report_v3"
RESULTS_DIR = BENCHMARK_DIR / "results"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_html(case_id: str, inference_dir: Path) -> str:
    path = inference_dir / f"{case_id}.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _mean(scores: List[Optional[float]]) -> Optional[float]:
    valid = [s for s in scores if s is not None]
    return sum(valid) / len(valid) if valid else None


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def run_judges(
    cases: List[Dict[str, Any]],
    inference_dir: Path,
    label: str,
    cache: JudgeCache,
    samples: int = 2,
) -> Dict[str, Any]:
    results = []
    total = len(cases)
    claim_scores: List[Optional[float]] = []
    action_scores: List[Optional[float]] = []

    for i, case in enumerate(cases, 1):
        cid = case["case_id"]
        logger.info("[%d/%d] %s — judging %s", i, total, label, cid)

        html = _load_html(cid, inference_dir)
        if not html:
            logger.warning("  No HTML for %s — skipping", cid)
            results.append({"case_id": cid, "skipped": True})
            continue

        rag_context = case.get("input", {}).get("report_data", {}).get("rag_context") or {}
        findings = case.get("input", {}).get("report_data", {}).get("raw_pre_findings") or []

        try:
            scores = judge_case(
                html,
                rag_context=rag_context,
                findings=findings,
                cache=cache,
                samples=samples,
            )
        except Exception as e:
            logger.warning("  Judge failed for %s: %s", cid, e)
            scores = {
                "claim_support_rate": {"score": None, "error": str(e)},
                "actionability_likert": {"score": None, "error": str(e)},
            }

        c_score = scores.get("claim_support_rate", {}).get("score")
        a_score = scores.get("actionability_likert", {}).get("score")
        claim_scores.append(c_score)
        action_scores.append(a_score)

        logger.info("  claim_support=%.3f  actionability=%.2f",
                    c_score or 0, a_score or 0)
        results.append({"case_id": cid, **scores})

    return {
        "label": label,
        "inference_dir": str(inference_dir),
        "total_cases": total,
        "judged": sum(1 for r in results if not r.get("skipped")),
        "summary": {
            "claim_support_rate_mean": _mean(claim_scores),
            "actionability_likert_mean": _mean(action_scores),
        },
        "cases": results,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("baseline", "mvp", "compare"),
        default="compare",
    )
    parser.add_argument("--inference-dir", type=Path, default=None)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--samples", type=int, default=2,
                        help="LLM samples per judge call (default 2)")
    args = parser.parse_args()

    cases_data = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = cases_data.get("cases", [])
    logger.info("Loaded %d cases", len(cases))

    cache = JudgeCache()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Baseline HTML dir — from Phase 1 no_rag folder or main report_v3
    baseline_dir = BENCHMARK_DIR / "inference_outputs" / "report_v3_no_rag"
    if not baseline_dir.exists():
        baseline_dir = INFERENCE_DIR  # fallback
    mvp_dir = INFERENCE_DIR

    payload: Dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "samples_per_judge": args.samples,
    }

    if args.mode == "baseline":
        inf_dir = args.inference_dir or baseline_dir
        result = run_judges(cases, inf_dir, "baseline", cache, args.samples)
        payload["results"] = [result]

    elif args.mode == "mvp":
        inf_dir = args.inference_dir or mvp_dir
        result = run_judges(cases, inf_dir, "mvp", cache, args.samples)
        payload["results"] = [result]

    elif args.mode == "compare":
        b_dir = baseline_dir if not args.inference_dir else args.inference_dir
        m_dir = mvp_dir
        b_result = run_judges(cases, b_dir, "baseline", cache, args.samples)
        m_result = run_judges(cases, m_dir, "mvp", cache, args.samples)
        payload["results"] = [b_result, m_result]

        b_claim = b_result["summary"]["claim_support_rate_mean"]
        m_claim = m_result["summary"]["claim_support_rate_mean"]
        b_action = b_result["summary"]["actionability_likert_mean"]
        m_action = m_result["summary"]["actionability_likert_mean"]

        def _fmt(v): return f"{v:.4f}" if v is not None else "N/A"
        def _delta(b, m, hib=True):
            if b is None or m is None: return "N/A"
            d = m - b
            mark = "++" if (d > 0.01 and hib) or (d < -0.01 and not hib) else (
                   "--" if (d < -0.01 and hib) or (d > 0.01 and not hib) else "==")
            return f"{mark} {d:+.4f}"

        print("\n=== LLM JUDGE COMPARISON ===")
        print(f"{'Metric':<30} {'Baseline':>10} {'MVP':>10} {'Delta':>15}")
        print("-" * 65)
        print(f"{'claim_support_rate':<30} {_fmt(b_claim):>10} {_fmt(m_claim):>10} {_delta(b_claim, m_claim):>15}")
        print(f"{'actionability_likert':<30} {_fmt(b_action):>10} {_fmt(m_action):>10} {_delta(b_action, m_action):>15}")

    out_path = args.out or (RESULTS_DIR / f"judge_{args.mode}_{ts}.json")
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nOutput: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
