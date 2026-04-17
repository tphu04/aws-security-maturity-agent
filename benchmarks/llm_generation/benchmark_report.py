"""
Report Agent benchmark core engine.

Pipeline: Load cases -> Inference (goi ReportAgent that) -> Evaluate -> Aggregate -> Save

Su dung: benchmark_report.py duoc goi tu run_report_benchmark.py.
Khong chay truc tiep.
"""

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

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.llm_generation.report_metrics import (
    check_release_criteria,
    evaluate_completeness,
    evaluate_correctness,
    evaluate_faithfulness,
    evaluate_structure,
    mean_of,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BENCHMARK_DIR = Path(__file__).resolve().parent
CASES_FILE = BENCHMARK_DIR / "benchmark_report_cases.json"
CRITERIA_FILE = BENCHMARK_DIR / "release_criteria_report.json"
INFERENCE_DIR = BENCHMARK_DIR / "inference_outputs"
OUTPUT_DIR = BENCHMARK_DIR / "benchmark_outputs"


# ---------------------------------------------------------------------------
# Step 1: Load
# ---------------------------------------------------------------------------

def load_cases(path: Optional[str] = None) -> List[Dict]:
    """Load va validate report test cases."""

    cases_path = Path(path) if path else CASES_FILE
    if not cases_path.exists():
        raise FileNotFoundError(f"Benchmark cases file not found: {cases_path}")

    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("report_cases", [])
    if not cases:
        raise ValueError("No report_cases found in benchmark file")

    for i, case in enumerate(cases):
        _validate_case(case, i)

    logger.info("Loaded %d report test cases from %s", len(cases), cases_path.name)
    return cases


def _validate_case(case: Dict, index: int) -> None:
    """Validate 1 test case co du fields bat buoc."""
    required = ["case_id", "input"]
    for field in required:
        if field not in case:
            raise ValueError(f"Case #{index} missing required field: {field}")

    inp = case["input"]
    required_input = ["pre", "post", "environment", "scope",
                      "findings_table", "success_findings",
                      "failed_findings", "manual_findings",
                      "raw_pre_findings"]
    for field in required_input:
        if field not in inp:
            raise ValueError(
                f"Case #{index} ({case['case_id']}): input.{field} missing"
            )


# ---------------------------------------------------------------------------
# Step 2: Inference
# ---------------------------------------------------------------------------

def run_inference(cases: List[Dict]) -> List[Dict]:
    """Chay ReportAgent cho tat ca test cases, tra ve inference outputs.

    Requires: Ollama running (port 11434) voi model configured.
    """
    outputs = []
    total = len(cases)

    for i, case in enumerate(cases, 1):
        case_id = case["case_id"]
        logger.info("[%d/%d] Running inference: %s", i, total, case_id)

        output = _run_single_inference(case)
        outputs.append(output)

        status = "OK" if not output.get("error") else "ERROR"
        logger.info(
            "[%d/%d] %s -> %s, latency=%.0fms",
            i, total, case_id, status, output["latency_ms"],
        )

    return outputs


def _run_single_inference(case: Dict) -> Dict:
    """Chay ReportAgent cho 1 test case."""

    from pdca.agents.report_agent import ReportAgent

    report_data = case["input"]

    # Create temp output directory for each case
    tmp_dir = tempfile.mkdtemp(prefix=f"report_bench_{case['case_id']}_")

    try:
        # Try to use configured LLM, fallback to default Ollama
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
        try:
            result = agent.run(data=report_data)
            elapsed = time.perf_counter() - start
            error = None
        except Exception as e:
            elapsed = time.perf_counter() - start
            result = {}
            error = str(e)
            logger.error("Inference failed for %s: %s", case["case_id"], e)

        # Read HTML output
        html_content = ""
        html_path = result.get("html", "")
        if html_path and os.path.exists(html_path):
            with open(html_path, encoding="utf-8") as f:
                html_content = f.read()

        # Get LLM metrics
        try:
            llm_metrics = agent.get_llm_metrics()
        except Exception:
            llm_metrics = {}

        return {
            "case_id": case["case_id"],
            "agent": "report",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": round(elapsed * 1000, 1),
            "agent_output": {
                "html_content": html_content,
                "output_paths": result,
                "output_dir": tmp_dir,
            },
            "llm_metrics": llm_metrics,
            "error": error,
        }

    except Exception as e:
        return {
            "case_id": case["case_id"],
            "agent": "report",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": 0,
            "agent_output": {"html_content": "", "output_paths": {}, "output_dir": tmp_dir},
            "llm_metrics": {},
            "error": str(e),
        }


def save_inference(outputs: List[Dict], run_dir: Path) -> Path:
    """Luu inference outputs vao file."""
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save HTML files separately (too large for JSON)
    for output in outputs:
        html = output["agent_output"].get("html_content", "")
        if html:
            html_file = run_dir / f"{output['case_id']}.html"
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html)

    # Save inference JSON (without html_content to keep file small)
    outputs_slim = []
    for output in outputs:
        slim = dict(output)
        slim["agent_output"] = {
            k: v for k, v in output["agent_output"].items()
            if k != "html_content"
        }
        slim["agent_output"]["html_file"] = f"{output['case_id']}.html"
        outputs_slim.append(slim)

    filepath = run_dir / "report_inference.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(outputs_slim, f, indent=2, ensure_ascii=False, default=str)

    # Save metadata
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(outputs),
        "agent": "report",
    }
    try:
        from pdca.config import OLLAMA_MODEL
        meta["ollama_model"] = OLLAMA_MODEL
    except ImportError:
        pass

    with open(run_dir / "run_metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    logger.info("Inference saved to %s (%d cases)", run_dir, len(outputs))
    return filepath


def load_inference(run_dir: str) -> List[Dict]:
    """Load inference outputs tu file, including HTML content."""
    run_path = Path(run_dir)
    filepath = run_path / "report_inference.json"
    if not filepath.exists():
        raise FileNotFoundError(f"Inference file not found: {filepath}")

    with open(filepath, encoding="utf-8") as f:
        outputs = json.load(f)

    # Reload HTML content from separate files
    for output in outputs:
        html_file = output["agent_output"].get("html_file", "")
        html_path = run_path / html_file
        if html_path.exists():
            with open(html_path, encoding="utf-8") as f:
                output["agent_output"]["html_content"] = f.read()
        else:
            output["agent_output"]["html_content"] = ""

    return outputs


# ---------------------------------------------------------------------------
# Step 3: Evaluate
# ---------------------------------------------------------------------------

def run_evaluation(cases: List[Dict], inferences: List[Dict]) -> List[Dict]:
    """Danh gia tat ca cases tren 4 truc metric."""

    inf_map = {inf["case_id"]: inf for inf in inferences}

    results = []
    for case in cases:
        case_id = case["case_id"]
        inference = inf_map.get(case_id)
        if not inference:
            logger.warning("No inference found for case %s — skipping", case_id)
            continue

        result = _evaluate_single_case(case, inference)
        results.append(result)

    logger.info("Evaluated %d cases", len(results))
    return results


def _evaluate_single_case(case: Dict, inference: Dict) -> Dict:
    """Danh gia 1 test case tren 4 truc."""

    html = inference["agent_output"].get("html_content", "")
    report_data = case["input"]
    output_dir = inference["agent_output"].get("output_dir")

    # Structure — gate check
    structure = evaluate_structure(html, output_dir=output_dir)

    # If structure gate fails, still evaluate others but flag it
    gate_passed = structure["hard_pass"]

    # Correctness — deterministic data accuracy
    correctness = evaluate_correctness(html, report_data)

    # Faithfulness — numerical claims vs data
    faithfulness = evaluate_faithfulness(html, report_data)

    # Completeness — findings coverage + bypass
    completeness = evaluate_completeness(html, report_data)

    return {
        "case_id": case["case_id"],
        "group": case.get("group", "unknown"),
        "scenario": case.get("scenario", "unknown"),
        "bug_regression": case.get("bug_regression"),

        "debug": {
            "html_length": len(html),
            "gate_passed": gate_passed,
            "inference_error": inference.get("error"),
            "latency_ms": inference.get("latency_ms", 0),
        },

        "structure": structure,
        "correctness": correctness,
        "faithfulness": faithfulness,
        "completeness": completeness,
    }


# ---------------------------------------------------------------------------
# Step 4: Aggregate
# ---------------------------------------------------------------------------

def aggregate_results(evaluated_cases: List[Dict], criteria_path: Optional[str] = None) -> Dict:
    """Tong hop ket qua tu tat ca cases thanh summary report."""

    summary = {
        "report_type": "report_agent_benchmark",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(evaluated_cases),

        # Structure (gate check)
        "structure": {
            "html_valid_rate": mean_of(evaluated_cases, "structure", "html_valid"),
            "section_presence_rate": mean_of(evaluated_cases, "structure", "section_presence_rate"),
            "no_template_leak_rate": mean_of(evaluated_cases, "structure", "no_template_leak"),
            "no_none_display_rate": mean_of(evaluated_cases, "structure", "no_none_display"),
            "cover_page_rate": mean_of(evaluated_cases, "structure", "cover_page_complete"),
            "chart_presence_rate": mean_of(evaluated_cases, "structure", "chart_presence"),
            "gate_pass_rate": mean_of(evaluated_cases, "structure", "hard_pass"),
        },

        # Correctness (deterministic)
        "correctness": {
            "stats_accuracy": mean_of(evaluated_cases, "correctness", "stats_accuracy"),
            "findings_table_accuracy": mean_of(evaluated_cases, "correctness", "findings_table_accuracy"),
            "score_accuracy": mean_of(evaluated_cases, "correctness", "score_accuracy"),
            "status_color_accuracy": mean_of(evaluated_cases, "correctness", "status_color_accuracy"),
        },

        # Faithfulness (numerical, deterministic)
        "faithfulness": {
            "numerical_faithfulness": mean_of(evaluated_cases, "faithfulness", "score"),
        },

        # Completeness
        "completeness": {
            "findings_coverage": mean_of(evaluated_cases, "completeness", "findings_coverage"),
            "conditional_bypass_correctness": mean_of(
                evaluated_cases, "completeness", "conditional_bypass_correctness"
            ),
        },

        # Breakdowns
        "by_group": _compute_by_group(evaluated_cases),
        "by_scenario": _compute_by_scenario(evaluated_cases),

        # Per-case details
        "cases": evaluated_cases,
    }

    # Release criteria
    cpath = Path(criteria_path) if criteria_path else CRITERIA_FILE
    if cpath.exists():
        with open(cpath, encoding="utf-8") as f:
            criteria = json.load(f)
        summary["release_criteria"] = check_release_criteria(summary, criteria)
    else:
        logger.warning("Release criteria file not found: %s", cpath)

    return summary


def _compute_by_group(cases: List[Dict]) -> Dict:
    """Breakdown by group (A_scenario, B_edge_case)."""
    groups = {}
    for c in cases:
        g = c.get("group", "unknown")
        groups.setdefault(g, []).append(c)

    result = {}
    for g, group_cases in groups.items():
        result[g] = {
            "total": len(group_cases),
            "gate_pass_rate": mean_of(group_cases, "structure", "hard_pass"),
            "stats_accuracy": mean_of(group_cases, "correctness", "stats_accuracy"),
            "faithfulness": mean_of(group_cases, "faithfulness", "score"),
            "findings_coverage": mean_of(group_cases, "completeness", "findings_coverage"),
        }
    return result


def _compute_by_scenario(cases: List[Dict]) -> Dict:
    """Breakdown by scenario (standard, all_pass, etc.)."""
    scenarios = {}
    for c in cases:
        s = c.get("scenario", "unknown")
        scenarios.setdefault(s, []).append(c)

    result = {}
    for s, scenario_cases in scenarios.items():
        result[s] = {
            "total": len(scenario_cases),
            "gate_pass_rate": mean_of(scenario_cases, "structure", "hard_pass"),
            "stats_accuracy": mean_of(scenario_cases, "correctness", "stats_accuracy"),
            "faithfulness": mean_of(scenario_cases, "faithfulness", "score"),
            "findings_coverage": mean_of(scenario_cases, "completeness", "findings_coverage"),
        }
    return result


def save_report(report: Dict, output_dir: Optional[str] = None) -> Path:
    """Luu benchmark report va ban latest."""
    out = Path(output_dir) if output_dir else OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = out / f"report_benchmark_run_{ts}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    latest = out / "report_benchmark_latest.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Report saved to %s", filepath)
    return filepath
