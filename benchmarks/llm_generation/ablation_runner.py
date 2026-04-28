"""Ablation runner: no_rag vs with_rag_v2 for Report Agent v3.

Two conditions per case (24 × 2 = 48 inferences, 24 × 2 × 2 judges =
96 judge-ops × 2 samples = 192 judge calls). Artifacts:

    inference_outputs/report_v3_no_rag/<case_id>.html
    inference_outputs/report_v3_with_rag/<case_id>.html
    benchmark_outputs/report_v3_ablation_<ts>.json
    benchmark_outputs/report_v3_ablation_latest.json

The conditions differ only in what ``data["rag_context"]`` holds when the
Report Agent runs:

* **no_rag**       — ``{}`` (primary_topics=[], capability_details=[],
                      recommended_practices=[])
* **with_rag_v2**  — the case's ``rag_snapshot`` verbatim.

Everything else (findings, pre/post stats, scope hint) is identical so
the contrast isolates the RAG bundle's contribution.

Usage
-----
    python -m benchmarks.llm_generation.ablation_runner \
        [--skip-inference-for no_rag] [--skip-judges] [--cases PATH]

``--skip-inference-for`` reuses an existing HTML directory instead of
running the agent again — e.g. after Day 1 we already have the no_rag
artifacts in ``inference_outputs/report_v3/``, which is copied into
``report_v3_no_rag/`` on first run.
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
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.llm_generation.report_judges import (  # noqa: E402
    JudgeCache,
    judge_case,
)
from benchmarks.llm_generation.report_metrics_v3 import (  # noqa: E402
    evaluate_case_deterministic,
)
from benchmarks.llm_generation.run_report_benchmark_v3 import (  # noqa: E402
    DEFAULT_CASES,
    load_cases,
)

logger = logging.getLogger(__name__)

BENCHMARK_DIR = Path(__file__).resolve().parent
INF_ROOT = BENCHMARK_DIR / "inference_outputs"
OUT_DIR = BENCHMARK_DIR / "benchmark_outputs"

NO_RAG_DIR = INF_ROOT / "report_v3_no_rag"
WITH_RAG_DIR = INF_ROOT / "report_v3_with_rag"
# Day 1 artefacts live here — we copy them into NO_RAG_DIR on first run
# (because the Day 1 CLI didn't merge rag_snapshot into the agent input
# so those HTMLs are effectively the no_rag condition already).
LEGACY_DAY1_DIR = INF_ROOT / "report_v3"


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def _run_one_inference(
    case: Dict[str, Any],
    condition: str,
    dest_dir: Path,
) -> Dict[str, Any]:
    """Run ReportAgent under a single condition; persist HTML."""
    from pdca.agents.report_agent import ReportAgent

    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix=f"abl_{condition}_{case['case_id']}_")
    report_data = dict(case["input"]["report_data"])  # shallow copy
    if condition == "with_rag":
        report_data["rag_context"] = case["input"].get("rag_snapshot") or {}
    else:
        report_data["rag_context"] = {}

    try:
        try:
            from pdca.config import OLLAMA_BASE_URL, OLLAMA_MODEL
            agent = ReportAgent(
                model=OLLAMA_MODEL,
                base_url=OLLAMA_BASE_URL,
                output_path=os.path.join(tmp_dir, "final_report.md"),
            )
        except ImportError:
            agent = ReportAgent(
                output_path=os.path.join(tmp_dir, "final_report.md"),
            )

        start = time.perf_counter()
        error: Optional[str] = None
        result: Dict[str, Any] = {}
        try:
            result = agent.run(data=report_data)
        except Exception as e:
            error = str(e)
            logger.exception("inference failed %s/%s", condition, case["case_id"])
        latency_ms = (time.perf_counter() - start) * 1000

        html_path = result.get("html", "") if isinstance(result, dict) else ""
        html_content = ""
        if html_path and os.path.exists(html_path):
            with open(html_path, encoding="utf-8") as f:
                html_content = f.read()
        dest = dest_dir / f"{case['case_id']}.html"
        dest.write_text(html_content, encoding="utf-8")

        return {
            "case_id": case["case_id"],
            "condition": condition,
            "latency_ms": round(latency_ms, 1),
            "output_dir": tmp_dir,
            "error": error,
        }
    except Exception as e:
        return {
            "case_id": case["case_id"],
            "condition": condition,
            "latency_ms": 0.0,
            "output_dir": tmp_dir,
            "error": str(e),
        }


def _seed_no_rag_from_legacy() -> int:
    """Copy Day-1 HTMLs into NO_RAG_DIR if present. Returns count copied."""
    if not LEGACY_DAY1_DIR.exists():
        return 0
    NO_RAG_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in LEGACY_DAY1_DIR.glob("*.html"):
        dst = NO_RAG_DIR / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
            copied += 1
    return copied


def run_condition(
    cases: List[Dict[str, Any]],
    condition: str,
    dest_dir: Path,
) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []
    total = len(cases)
    for i, case in enumerate(cases, 1):
        logger.info("[%d/%d] %s: %s", i, total, condition, case["case_id"])
        recs.append(_run_one_inference(case, condition, dest_dir))
    return recs


# ---------------------------------------------------------------------------
# Scoring (deterministic + judges)
# ---------------------------------------------------------------------------

def score_condition(
    cases: List[Dict[str, Any]],
    inference_dir: Path,
    condition: str,
    inference_records: Optional[List[Dict[str, Any]]] = None,
    run_judges: bool = True,
    cache: Optional[JudgeCache] = None,
) -> List[Dict[str, Any]]:
    rec_map = {r["case_id"]: r for r in (inference_records or [])}
    results: List[Dict[str, Any]] = []
    total = len(cases)
    for i, case in enumerate(cases, 1):
        case_id = case["case_id"]
        html_path = inference_dir / f"{case_id}.html"
        html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
        rec = rec_map.get(case_id, {})
        scored = evaluate_case_deterministic(
            html, case, output_dir=rec.get("output_dir"),
        )
        scored["condition"] = condition
        scored["debug"] = {
            "html_length": len(html),
            "latency_ms": rec.get("latency_ms"),
            "error": rec.get("error"),
        }
        if run_judges and html:
            logger.info("[%d/%d] %s judges: %s", i, total, condition, case_id)
            jud = judge_case(
                html,
                rag_context=case["input"].get("rag_snapshot") or {},
                findings=case["input"]["report_data"].get("raw_pre_findings") or [],
                cache=cache,
            )
            scored["metrics"]["claim_support_rate"] = jud["claim_support_rate"]
            scored["metrics"]["actionability_likert"] = jud["actionability_likert"]
        results.append(scored)
    return results


# ---------------------------------------------------------------------------
# Aggregation & delta
# ---------------------------------------------------------------------------

_METRIC_NAMES = [
    "structure_pass_rate",
    "off_scope_mention_rate",
    "scope_accuracy",
    "numerical_faithfulness",
    "capability_grounding_rate",
    "template_data_accuracy",
    "ndcg_at_5_severity",
    "claim_support_rate",
    "actionability_likert",
]


def _mean(cases: List[Dict[str, Any]], metric: str) -> Optional[float]:
    vals: List[float] = []
    for c in cases:
        m = (c.get("metrics") or {}).get(metric) or {}
        s = m.get("score")
        if isinstance(s, (int, float)):
            vals.append(float(s))
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def aggregate_ablation(
    no_rag: List[Dict[str, Any]],
    with_rag: List[Dict[str, Any]],
) -> Dict[str, Any]:
    table: List[Dict[str, Any]] = []
    for m in _METRIC_NAMES:
        nr = _mean(no_rag, m)
        wr = _mean(with_rag, m)
        delta: Optional[float] = None
        if nr is not None and wr is not None:
            delta = round(wr - nr, 4)
        table.append({
            "metric": m,
            "no_rag": nr,
            "with_rag": wr,
            "delta": delta,
        })
    return {"metrics": table}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--skip-inference-for",
        choices=("no_rag", "with_rag", "both"),
        default=None,
        help="Reuse existing HTML directory for the named condition(s).",
    )
    parser.add_argument(
        "--skip-judges", action="store_true",
        help="Skip LLM-Judge scoring (faster re-runs / offline testing).",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    cases = load_cases(args.cases)
    logger.info("Loaded %d cases", len(cases))

    # Seed no_rag from Day 1 artefacts if available.
    copied = _seed_no_rag_from_legacy()
    if copied:
        logger.info("Seeded NO_RAG_DIR with %d Day-1 HTML files", copied)

    skip = args.skip_inference_for or ""
    no_rag_recs: List[Dict[str, Any]] = []
    with_rag_recs: List[Dict[str, Any]] = []

    if skip not in ("no_rag", "both"):
        logger.info("=== Inference: no_rag (%d cases) ===", len(cases))
        no_rag_recs = run_condition(cases, "no_rag", NO_RAG_DIR)
    else:
        logger.info("Skipping no_rag inference; reusing %s", NO_RAG_DIR)

    if skip not in ("with_rag", "both"):
        logger.info("=== Inference: with_rag (%d cases) ===", len(cases))
        with_rag_recs = run_condition(cases, "with_rag", WITH_RAG_DIR)
    else:
        logger.info("Skipping with_rag inference; reusing %s", WITH_RAG_DIR)

    cache = JudgeCache()
    run_judges = not args.skip_judges

    logger.info("=== Scoring no_rag ===")
    no_rag_scored = score_condition(
        cases, NO_RAG_DIR, "no_rag",
        inference_records=no_rag_recs, run_judges=run_judges, cache=cache,
    )
    logger.info("=== Scoring with_rag ===")
    with_rag_scored = score_condition(
        cases, WITH_RAG_DIR, "with_rag",
        inference_records=with_rag_recs, run_judges=run_judges, cache=cache,
    )

    ablation = aggregate_ablation(no_rag_scored, with_rag_scored)

    payload = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(cases),
        "conditions": {
            "no_rag": {"inference_dir": str(NO_RAG_DIR), "cases": no_rag_scored},
            "with_rag": {"inference_dir": str(WITH_RAG_DIR), "cases": with_rag_scored},
        },
        "ablation": ablation,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or OUT_DIR / f"report_v3_ablation_{ts}.json"
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    latest = OUT_DIR / "report_v3_ablation_latest.json"
    latest.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    # Pretty print the ablation table.
    print("\nAblation results (no_rag -> with_rag, delta):")
    print(f"  {'metric':<30s} {'no_rag':>10s} {'with_rag':>10s} {'delta':>10s}")
    for row in ablation["metrics"]:
        def _fmt(v: Optional[float]) -> str:
            return f"{v:>10.4f}" if isinstance(v, (int, float)) else f"{'n/a':>10s}"
        print(f"  {row['metric']:<30s} {_fmt(row['no_rag'])} "
              f"{_fmt(row['with_rag'])} {_fmt(row['delta'])}")
    print(f"\nArtifact: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
