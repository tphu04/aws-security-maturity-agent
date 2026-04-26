"""MVP Ablation Runner — 4-condition ablation for multi-query RAG.

Conditions (vary include_q2 / include_q3):
  baseline  — Q1 only  (include_q2=False, include_q3=False)
  q1_q2     — Q1+Q2    (include_q2=True,  include_q3=False)
  q1_q3     — Q1+Q3    (include_q2=False, include_q3=True)
  full_mvp  — Q1+Q2+Q3 (include_q2=True,  include_q3=True)

MULTI_QUERY_MODE must be True for all conditions.
baseline here means "Q1 only via multi-query path" (not pure LLM).

Usage
-----
    # Run all 4 conditions (slow — ~4 × 30 min):
    python -m benchmarks.llm_generation.ablation_mvp

    # Skip already-done conditions:
    python -m benchmarks.llm_generation.ablation_mvp --skip full_mvp

    # Metrics-only (reuse existing HTMLs):
    python -m benchmarks.llm_generation.ablation_mvp --mode metrics-only

Output
------
    benchmarks/llm_generation/results/ablation_mvp.json
    benchmarks/llm_generation/results/ablation_mvp_table.md
"""
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

from benchmarks.llm_generation.report_metrics_v3 import aggregate, evaluate_case_deterministic  # noqa: E402

logger = logging.getLogger(__name__)

BENCHMARK_DIR = Path(__file__).resolve().parent
DEFAULT_CASES = BENCHMARK_DIR / "benchmark_report_cases_v3.json"
INFERENCE_BASE = BENCHMARK_DIR / "inference_outputs"
RESULTS_DIR = BENCHMARK_DIR / "results"

ABLATION_CONDITIONS: List[Dict[str, Any]] = [
    {"name": "baseline",  "include_q2": False, "include_q3": False},
    {"name": "q1_q2",     "include_q2": True,  "include_q3": False},
    {"name": "q1_q3",     "include_q2": False, "include_q3": True},
    {"name": "full_mvp",  "include_q2": True,  "include_q3": True},
]

KEY_METRICS = [
    "numerical_faithfulness",
    "capability_grounding_rate",
    "ndcg_at_5_severity",
    "structure_pass_rate",
    "off_scope_mention_rate",
    "template_data_accuracy",
]


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def _patch_planner_flags(include_q2: bool, include_q3: bool) -> None:
    """Monkey-patch RAGQueryPlanner.plan() to fix include_q2/q3 flags.

    This avoids adding yet another env var while keeping the agent code clean.
    """
    import pdca.agents.report_module.rag_query_planner as _mod
    _orig_plan = _mod.RAGQueryPlanner.plan

    def _patched_plan(self, findings, scope_domains):
        req = _orig_plan(self, findings, scope_domains)
        req["include_q2"] = include_q2
        req["include_q3"] = include_q3
        return req

    _mod.RAGQueryPlanner.plan = _patched_plan


def run_inference_condition(
    condition: Dict[str, Any],
    cases: List[Dict[str, Any]],
    inference_dir: Path,
) -> List[Dict[str, Any]]:
    """Run inference for one ablation condition."""
    import tempfile
    from pdca.agents.report_agent import ReportAgent

    try:
        from pdca.config import OLLAMA_BASE_URL, OLLAMA_MODEL
    except ImportError:
        OLLAMA_BASE_URL = "http://localhost:11434"
        OLLAMA_MODEL = "gemma3:4b"

    # Patch planner flags for this condition
    _patch_planner_flags(condition["include_q2"], condition["include_q3"])

    os.environ["MULTI_QUERY_MODE"] = "true"

    inference_dir.mkdir(parents=True, exist_ok=True)
    records = []
    total = len(cases)

    for i, case in enumerate(cases, 1):
        logger.info("[%d/%d] %s — %s", i, total, condition["name"], case["case_id"])
        tmp_dir = tempfile.mkdtemp(prefix=f"ablation_{condition['name']}_{case['case_id']}_")
        report_data = case["input"]["report_data"]

        try:
            agent = ReportAgent(
                model=OLLAMA_MODEL,
                base_url=OLLAMA_BASE_URL,
                output_path=os.path.join(tmp_dir, "final_report.md"),
            )
            start = time.perf_counter()
            error: Optional[str] = None
            result: Dict[str, Any] = {}
            try:
                result = agent.run(data=report_data)
            except Exception as e:
                error = str(e)
                logger.exception("Inference failed: %s / %s", condition["name"], case["case_id"])

            latency_ms = (time.perf_counter() - start) * 1000
            html_path = result.get("html", "") if isinstance(result, dict) else ""
            html_content = ""
            if html_path and os.path.exists(html_path):
                html_content = open(html_path, encoding="utf-8").read()

            dest = inference_dir / f"{case['case_id']}.html"
            dest.write_text(html_content, encoding="utf-8")
            records.append({
                "case_id": case["case_id"],
                "latency_ms": round(latency_ms, 1),
                "html_path": str(dest),
                "output_dir": tmp_dir,
                "error": error,
            })
        except Exception as e:
            records.append({
                "case_id": case["case_id"],
                "latency_ms": 0.0,
                "html_path": "",
                "output_dir": tmp_dir,
                "error": str(e),
            })

    return records


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_condition(
    condition_name: str,
    cases: List[Dict[str, Any]],
    inference_dir: Path,
    inference_records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    rec_map = {r["case_id"]: r for r in (inference_records or [])}
    scored = []
    for case in cases:
        path = inference_dir / f"{case['case_id']}.html"
        html = path.read_text(encoding="utf-8") if path.exists() else ""
        rec = rec_map.get(case["case_id"], {})
        metrics = evaluate_case_deterministic(html, case, output_dir=rec.get("output_dir"))
        metrics["debug"] = {
            "html_length": len(html),
            "latency_ms": rec.get("latency_ms"),
            "error": rec.get("error"),
        }
        scored.append(metrics)

    summary = aggregate(scored)
    return {
        "condition": condition_name,
        "summary": summary,
        "cases": scored,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _mean(summary: Dict[str, Any], metric: str) -> Optional[float]:
    return (summary.get("overall", {}).get(metric) or {}).get("mean")


def build_markdown_table(results: List[Dict[str, Any]]) -> str:
    header = "| Condition | " + " | ".join(KEY_METRICS) + " |"
    sep = "|---|" + "---|" * len(KEY_METRICS)
    rows = [header, sep]
    for r in results:
        s = r["summary"]
        values = [f"{_mean(s, m):.4f}" if _mean(s, m) is not None else "N/A" for m in KEY_METRICS]
        rows.append(f"| {r['condition']} | " + " | ".join(values) + " |")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--mode", choices=("full", "metrics-only"), default="full",
        help="full=run inference+score; metrics-only=score existing HTMLs",
    )
    parser.add_argument(
        "--skip", nargs="*", default=[],
        help="Condition names to skip inference for (reuse existing HTMLs)",
        metavar="CONDITION",
    )
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "ablation_mvp.json")
    args = parser.parse_args()

    cases_payload = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = cases_payload.get("cases", [])
    logger.info("Loaded %d cases", len(cases))

    all_results: List[Dict[str, Any]] = []

    for cond in ABLATION_CONDITIONS:
        name = cond["name"]
        inference_dir = INFERENCE_BASE / f"report_v3_ablation_{name}"

        if args.mode == "full" and name not in args.skip:
            logger.info("=== Running inference: %s (q2=%s q3=%s) ===",
                        name, cond["include_q2"], cond["include_q3"])
            records = run_inference_condition(cond, cases, inference_dir)
        else:
            logger.info("=== Skipping inference (metrics-only): %s ===", name)
            records = None

        logger.info("=== Scoring: %s ===", name)
        result = score_condition(name, cases, inference_dir, records)
        all_results.append(result)

        summary_line = {m: _mean(result["summary"], m) for m in KEY_METRICS}
        logger.info("  %s scores: %s", name, {k: f"{v:.4f}" if v else "N/A" for k, v in summary_line.items()})

    # Build output
    table_md = build_markdown_table(all_results)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conditions": [r["condition"] for r in all_results],
        "key_metrics": KEY_METRICS,
        "results": all_results,
        "markdown_table": table_md,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    table_path = args.out.parent / "ablation_mvp_table.md"
    table_path.write_text(table_md, encoding="utf-8")

    print("\n=== ABLATION RESULTS ===")
    print(table_md)
    print(f"\nFull output: {args.out}")
    print(f"Table: {table_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
