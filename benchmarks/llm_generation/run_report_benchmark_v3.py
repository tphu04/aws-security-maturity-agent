"""CLI entry for Report Agent Evaluation v3 (deterministic pass).

Usage
-----
    python -m benchmarks.llm_generation.run_report_benchmark_v3 \
        [--cases PATH] [--mode {full,inference,metrics-only}] \
        [--inference-dir PATH] [--out PATH]

Modes
-----
full         Run the Report Agent on every case, then score. Default.
inference    Only run inference; write HTMLs to ``--inference-dir``.
metrics-only Skip inference; expect ``--inference-dir/<case_id>.html``
             to already exist. Useful for quick re-scoring.

Only the 7 deterministic metrics run here. LLM-judge (Day 2) is a
separate entry-point — it reads the same inference artefacts.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.llm_generation.report_metrics_v3 import (  # noqa: E402
    aggregate,
    evaluate_case_deterministic,
)

logger = logging.getLogger(__name__)

BENCHMARK_DIR = Path(__file__).resolve().parent
DEFAULT_CASES = BENCHMARK_DIR / "benchmark_report_cases_v3.json"
DEFAULT_CRITERIA = BENCHMARK_DIR / "release_criteria_report_v3.json"
OUTPUT_DIR = BENCHMARK_DIR / "benchmark_outputs"
DEFAULT_INFERENCE_DIR = BENCHMARK_DIR / "inference_outputs" / "report_v3"


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------

def load_cases(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if not cases:
        raise SystemExit(f"No cases found in {path}")
    for i, c in enumerate(cases):
        if "case_id" not in c or "input" not in c:
            raise SystemExit(f"Case #{i} is missing case_id/input")
        if "report_data" not in c["input"]:
            raise SystemExit(
                f"Case {c['case_id']} missing input.report_data — is this v3 schema?"
            )
    return cases


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def _run_inference_for_case(
    case: Dict[str, Any],
    inference_dir: Path,
) -> Dict[str, Any]:
    """Run the Report Agent once; persist HTML to ``inference_dir``."""
    from pdca.agents.report_agent import ReportAgent

    inference_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix=f"report_v3_{case['case_id']}_")
    report_data = case["input"]["report_data"]

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
        except Exception as e:  # pragma: no cover - depends on Ollama
            error = str(e)
            logger.exception("Inference failed for %s", case["case_id"])
        latency_ms = (time.perf_counter() - start) * 1000

        html_path = result.get("html", "") if isinstance(result, dict) else ""
        html_content = ""
        if html_path and os.path.exists(html_path):
            with open(html_path, encoding="utf-8") as f:
                html_content = f.read()

        dest = inference_dir / f"{case['case_id']}.html"
        dest.write_text(html_content, encoding="utf-8")

        try:
            llm_metrics = agent.get_llm_metrics()
        except Exception:
            llm_metrics = {}

        return {
            "case_id": case["case_id"],
            "latency_ms": round(latency_ms, 1),
            "html_path": str(dest),
            "output_dir": tmp_dir,
            "llm_metrics": llm_metrics,
            "error": error,
        }
    except Exception as e:
        return {
            "case_id": case["case_id"],
            "latency_ms": 0.0,
            "html_path": "",
            "output_dir": tmp_dir,
            "llm_metrics": {},
            "error": str(e),
        }


def run_inference(
    cases: List[Dict[str, Any]],
    inference_dir: Path,
) -> List[Dict[str, Any]]:
    outs: List[Dict[str, Any]] = []
    total = len(cases)
    for i, case in enumerate(cases, 1):
        logger.info("[%d/%d] inference %s", i, total, case["case_id"])
        outs.append(_run_inference_for_case(case, inference_dir))
    return outs


def _load_html(case_id: str, inference_dir: Path) -> tuple:
    """Return (html_text, status). ``status`` is one of:
    ``"ok"`` (file exists, non-empty), ``"empty"`` (file exists but 0 bytes),
    ``"missing"`` (no file for this case in ``inference_dir``).
    """
    path = inference_dir / f"{case_id}.html"
    if not path.exists():
        return "", "missing"
    text = path.read_text(encoding="utf-8")
    return text, ("ok" if text.strip() else "empty")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_all(
    cases: List[Dict[str, Any]],
    inference_dir: Path,
    inference_records: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    rec_map: Dict[str, Dict[str, Any]] = {}
    if inference_records:
        rec_map = {r["case_id"]: r for r in inference_records}

    results: List[Dict[str, Any]] = []
    missing: List[str] = []
    empty: List[str] = []
    for case in cases:
        html, status = _load_html(case["case_id"], inference_dir)
        if status == "missing":
            missing.append(case["case_id"])
        elif status == "empty":
            empty.append(case["case_id"])
        rec = rec_map.get(case["case_id"], {})
        output_dir = rec.get("output_dir")
        scored = evaluate_case_deterministic(html, case, output_dir=output_dir)
        scored["debug"] = {
            "html_length": len(html),
            "html_status": status,
            "latency_ms": rec.get("latency_ms"),
            "error": rec.get("error"),
        }
        results.append(scored)

    if missing:
        logger.warning(
            "%d/%d cases have NO inference HTML in %s (missing: %s). "
            "Metric scores for these cases reflect empty output.",
            len(missing), len(cases), inference_dir,
            ", ".join(missing[:5]) + ("..." if len(missing) > 5 else ""),
        )
    if empty:
        logger.warning(
            "%d/%d cases have EMPTY inference HTML (likely inference errored): %s",
            len(empty), len(cases),
            ", ".join(empty[:5]) + ("..." if len(empty) > 5 else ""),
        )
    return results


# ---------------------------------------------------------------------------
# Release criteria
# ---------------------------------------------------------------------------

def check_release(summary: Dict[str, Any], criteria_path: Path) -> Dict[str, Any]:
    criteria = json.loads(criteria_path.read_text(encoding="utf-8"))
    overall = summary["overall"]

    checks: List[Dict[str, Any]] = []
    all_pass = True

    def _check(name: str, threshold: float, op: str) -> None:
        nonlocal all_pass
        metric = name.rsplit("_", 1)[0]  # "foo_min" → "foo"
        actual = (overall.get(metric) or {}).get("mean")
        if actual is None:
            ok = False
        else:
            ok = actual >= threshold if op == "min" else actual <= threshold
        if not ok:
            all_pass = False
        checks.append({
            "criterion": name,
            "threshold": threshold,
            "actual": actual,
            "passed": ok,
        })

    for key, thr in (criteria.get("hard") or {}).items():
        op = "max" if key.endswith("_max") else "min"
        _check(key, thr, op)

    soft_checks: List[Dict[str, Any]] = []
    for key, thr in (criteria.get("soft") or {}).items():
        op = "max" if key.endswith("_max") else "min"
        metric = key.rsplit("_", 1)[0]
        actual = (overall.get(metric) or {}).get("mean")
        if actual is None:
            passed = None
        else:
            passed = actual >= thr if op == "min" else actual <= thr
        soft_checks.append({
            "criterion": key,
            "threshold": thr,
            "actual": actual,
            "passed": passed,
        })

    return {
        "verdict": "PASS" if all_pass else "FAIL",
        "hard_checks": checks,
        "soft_checks": soft_checks,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA)
    parser.add_argument(
        "--mode",
        choices=("full", "inference", "metrics-only"),
        default="full",
    )
    parser.add_argument("--inference-dir", type=Path, default=DEFAULT_INFERENCE_DIR)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    cases = load_cases(args.cases)
    logger.info("Loaded %d cases from %s", len(cases), args.cases)

    inference_records: Optional[List[Dict[str, Any]]] = None
    if args.mode in ("full", "inference"):
        inference_records = run_inference(cases, args.inference_dir)
    if args.mode == "inference":
        logger.info("Inference-only run finished. HTMLs in %s", args.inference_dir)
        return 0

    scored = score_all(cases, args.inference_dir, inference_records)
    summary = aggregate(scored)
    release = check_release(summary, args.criteria)

    payload = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(cases),
        "inference_dir": str(args.inference_dir),
        "summary": summary,
        "release": release,
        "cases": scored,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = OUTPUT_DIR / f"report_v3_deterministic_{ts}.json"
    out_path = args.out or default_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    latest = OUTPUT_DIR / "report_v3_latest.json"
    latest.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    print(json.dumps(
        {
            "verdict": release["verdict"],
            "overall": {k: v.get("mean") for k, v in summary["overall"].items()},
        },
        indent=2, ensure_ascii=False,
    ))
    print(f"Detailed output: {out_path}")
    return 0 if release["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
