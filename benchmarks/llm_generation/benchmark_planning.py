"""
Generation benchmark core engine for Planning Agent.

Pipeline: Load cases -> Inference (goi agent that) -> Evaluate -> Aggregate -> Save

Su dung: benchmark_planning.py duoc goi tu run_planning_benchmark.py.
Khong chay truc tiep.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.llm_generation.planning_metrics import (
    check_release_criteria,
    compute_planning_correctness,
    evaluate_action_type,
    evaluate_exact_match,
    evaluate_faithfulness,
    evaluate_over_selection_rate,
    evaluate_planning_correctness,
    evaluate_structure,
    evaluate_under_selection_rate,
    mean_of,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BENCHMARK_DIR = Path(__file__).resolve().parent
CASES_FILE = BENCHMARK_DIR / "benchmark_planning_cases.json"
CRITERIA_FILE = BENCHMARK_DIR / "release_criteria_planning.json"
INFERENCE_DIR = BENCHMARK_DIR / "inference_outputs"
OUTPUT_DIR = BENCHMARK_DIR / "benchmark_outputs"


# ---------------------------------------------------------------------------
# Step 1: Load
# ---------------------------------------------------------------------------

def load_cases(path: Optional[str] = None) -> List[Dict]:
    """Load va validate planning test cases."""

    cases_path = Path(path) if path else CASES_FILE
    if not cases_path.exists():
        raise FileNotFoundError(f"Benchmark cases file not found: {cases_path}")

    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("planning_cases", [])
    if not cases:
        raise ValueError("No planning_cases found in benchmark file")

    for i, case in enumerate(cases):
        _validate_case(case, i)

    logger.info("Loaded %d planning test cases from %s", len(cases), cases_path.name)
    return cases


def _validate_case(case: Dict, index: int) -> None:
    """Validate 1 test case co du fields bat buoc."""
    required = ["case_id", "input_type", "input", "expected"]
    for field in required:
        if field not in case:
            raise ValueError(f"Case #{index} missing required field: {field}")

    if "user_request" not in case.get("input", {}):
        raise ValueError(f"Case #{index} ({case['case_id']}): input.user_request missing")
    if "acceptable_output_type" not in case.get("expected", {}):
        raise ValueError(f"Case #{index} ({case['case_id']}): expected.acceptable_output_type missing")


# ---------------------------------------------------------------------------
# Step 2: Inference
# ---------------------------------------------------------------------------

def run_inference(cases: List[Dict], rag_enabled: bool = True) -> List[Dict]:
    """Chay Planning Agent cho tat ca test cases.

    Requires:
    - RAG server running (port 8001) neu rag_enabled=True
    - Ollama running (port 11434) voi model configured
    """
    from pdca.agents.planning_agent import PlanningAgent
    from pdca.agents.shared.rag_client import RAGClient
    from pdca.config import OLLAMA_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL, RAG_API_URL

    # Setup RAG client
    rag_client = None
    if rag_enabled:
        rag_client = RAGClient(base_url=RAG_API_URL)
        if rag_client.is_healthy():
            logger.info("RAG service healthy at %s", RAG_API_URL)
        else:
            logger.warning("RAG service NOT healthy at %s — running without RAG", RAG_API_URL)
            rag_client = None

    outputs = []
    total = len(cases)

    for i, case in enumerate(cases, 1):
        case_id = case["case_id"]
        logger.info("[%d/%d] Running inference: %s", i, total, case_id)

        output = _run_single_inference(case, rag_client)
        outputs.append(output)

        agent_out = output["agent_output"]
        checks = agent_out.get("checks_to_scan", [])
        groups = agent_out.get("groups_to_scan", [])
        error = agent_out.get("error")

        if error:
            logger.info(
                "[%d/%d] %s -> ERROR: %s, latency=%.0fms",
                i, total, case_id, error[:80], output["latency_ms"],
            )
        elif checks:
            logger.info(
                "[%d/%d] %s -> %d checks: %s, latency=%.0fms",
                i, total, case_id, len(checks),
                ", ".join(checks[:3]) + ("..." if len(checks) > 3 else ""),
                output["latency_ms"],
            )
        elif groups:
            logger.info(
                "[%d/%d] %s -> group: %s, latency=%.0fms",
                i, total, case_id, groups, output["latency_ms"],
            )

    return outputs


def _run_single_inference(case: Dict, rag_client) -> Dict:
    """Chay Planning Agent cho 1 test case."""

    from pdca.agents.planning_agent import PlanningAgent
    from pdca.config import OLLAMA_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL

    user_request = case["input"]["user_request"]

    # Tao agent moi cho moi case de reset state
    agent = PlanningAgent(
        model_name=OLLAMA_MODEL,
        api_key=OLLAMA_API_KEY,
        base_url=OLLAMA_BASE_URL,
        rag_client=rag_client,
    )

    start = time.perf_counter()
    try:
        result = agent.run(user_request)
        elapsed = time.perf_counter() - start
        error = None
    except Exception as e:
        elapsed = time.perf_counter() - start
        result = {
            "groups_to_scan": [],
            "checks_to_scan": [],
            "reasoning": "",
            "error": str(e),
        }
        error = str(e)
        logger.error("Inference failed for %s: %s", case["case_id"], e)

    return {
        "case_id": case["case_id"],
        "agent": "planning",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latency_ms": round(elapsed * 1000, 1),
        "agent_output": result,
        "error": error,
    }


def save_inference(outputs: List[Dict], run_dir: Path) -> Path:
    """Luu inference outputs vao file."""
    run_dir.mkdir(parents=True, exist_ok=True)

    filepath = run_dir / "planning_inference.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(outputs, f, indent=2, ensure_ascii=False, default=str)

    # Save metadata
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(outputs),
        "agent": "planning",
    }
    try:
        from pdca.config import OLLAMA_MODEL, RAG_API_URL
        meta["ollama_model"] = OLLAMA_MODEL
        meta["rag_api_url"] = RAG_API_URL
    except ImportError:
        pass

    with open(run_dir / "run_metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    logger.info("Inference saved to %s", filepath)
    return filepath


def load_inference(run_dir: str) -> List[Dict]:
    """Load inference outputs tu file."""
    filepath = Path(run_dir) / "planning_inference.json"
    if not filepath.exists():
        raise FileNotFoundError(f"Inference file not found: {filepath}")

    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Step 3: Evaluate
# ---------------------------------------------------------------------------

def run_evaluation(cases: List[Dict], inferences: List[Dict]) -> List[Dict]:
    """Danh gia tat ca cases tren 4 truc metric."""

    # Map inference by case_id
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
    """Danh gia 1 test case tren ca 4 truc."""

    output = inference["agent_output"]
    expected = case["expected"]
    rag_context = case.get("rag_context_snapshot", {})

    checks = output.get("checks_to_scan", [])
    groups = output.get("groups_to_scan", [])
    reasoning = output.get("reasoning", "") or ""
    relevant = expected.get("relevant_checks", [])
    also_acceptable = expected.get("also_acceptable", [])

    return {
        "case_id": case["case_id"],
        "input_type": case.get("input_type", "unknown"),
        "service": case.get("service", "unknown"),

        # Debug info
        "debug": {
            "user_request": case["input"]["user_request"],
            "expected_service": expected.get("expected_service", ""),
            "expected_type": expected.get("acceptable_output_type", ""),
            "expected_checks": expected.get("relevant_checks", []),
            "also_acceptable": also_acceptable,
            "agent_checks": checks,
            "agent_groups": groups,
            "agent_reasoning": reasoning[:300],
            "agent_error": output.get("error"),
            "inference_error": inference.get("error"),
        },

        # 4 truc metrics
        "structure": evaluate_structure(output),
        "faithfulness": evaluate_faithfulness(
            reasoning=reasoning,
            rag_context=rag_context,
            selected_checks=checks,
        ),
        "correctness": evaluate_planning_correctness(output, expected),
        "completeness": {
            "recall": _extract_recall(output, expected),
            "action_type": evaluate_action_type(output, expected),
        },

        # New selection metrics
        "selection_analysis": {
            "over_selection": evaluate_over_selection_rate(checks, relevant, also_acceptable),
            "under_selection": evaluate_under_selection_rate(checks, relevant),
            "exact_match": evaluate_exact_match(checks, relevant),
        },
    }


def _extract_recall(output: Dict, expected: Dict) -> Optional[float]:
    """Extract recall tu F1 calculation (chi khi specific checks)."""
    checks = output.get("checks_to_scan", [])
    relevant = expected.get("relevant_checks", [])

    if not relevant:
        return None

    if not checks:
        return 0.0

    pred_set = set(c.lower() for c in checks)
    rel_set = set(c.lower() for c in relevant)
    tp = len(pred_set & rel_set)
    fn = len(rel_set - pred_set)

    return round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0


# ---------------------------------------------------------------------------
# Step 4: Aggregate
# ---------------------------------------------------------------------------

def aggregate_results(evaluated_cases: List[Dict], criteria_path: Optional[str] = None) -> Dict:
    """Tong hop ket qua tu tat ca cases thanh summary report."""

    # Phan loai cases theo output type
    specific_cases = [c for c in evaluated_cases if c["correctness"].get("output_type") == "specific_checks"]
    group_cases = [c for c in evaluated_cases if c["correctness"].get("output_type") == "group_scan"]
    error_cases = [c for c in evaluated_cases if c["correctness"].get("output_type") in ("error", "empty")]

    # F1 stats
    f1_values = [c["correctness"]["f1"] for c in specific_cases if c["correctness"].get("f1") is not None]
    f1_mean = round(sum(f1_values) / len(f1_values), 4) if f1_values else 0.0

    # Precision/Recall breakdown
    precision_values = [
        c["correctness"]["check_selection"]["precision"]
        for c in specific_cases
        if c["correctness"].get("check_selection") and c["correctness"]["check_selection"].get("precision") is not None
    ]
    recall_values = [
        c["correctness"]["check_selection"]["recall"]
        for c in specific_cases
        if c["correctness"].get("check_selection") and c["correctness"]["check_selection"].get("recall") is not None
    ]

    # Service accuracy stats
    svc_correct = sum(1 for c in group_cases if c["correctness"].get("service_correct"))
    svc_accuracy = round(svc_correct / len(group_cases), 4) if group_cases else 0.0

    # Planning Correctness composite
    planning_corr = compute_planning_correctness(specific_cases, group_cases)

    # Over-selection rate (chi specific_checks cases co ground truth)
    over_sel_values = [
        c["selection_analysis"]["over_selection"]["over_selection_rate"]
        for c in specific_cases
        if c["selection_analysis"]["over_selection"].get("over_selection_rate") is not None
    ]
    over_sel_mean = round(sum(over_sel_values) / len(over_sel_values), 4) if over_sel_values else 0.0

    # Under-selection rate
    under_sel_values = [
        c["selection_analysis"]["under_selection"]["under_selection_rate"]
        for c in specific_cases
        if c["selection_analysis"]["under_selection"].get("under_selection_rate") is not None
    ]
    under_sel_mean = round(sum(under_sel_values) / len(under_sel_values), 4) if under_sel_values else 0.0

    # Exact Match rate
    em_values = [
        c["selection_analysis"]["exact_match"]["exact_match"]
        for c in specific_cases
        if c["selection_analysis"]["exact_match"].get("exact_match") is not None
    ]
    em_rate = round(sum(1 for v in em_values if v) / len(em_values), 4) if em_values else 0.0

    # Check counts
    pred_vals = [
        c["selection_analysis"]["over_selection"]["total_predicted"]
        for c in specific_cases
        if c["selection_analysis"]["over_selection"].get("total_predicted") is not None
    ]
    rel_vals = [
        c["selection_analysis"]["under_selection"]["total_relevant"]
        for c in specific_cases
        if c["selection_analysis"]["under_selection"].get("total_relevant") is not None
    ]
    avg_pred_checks = round(sum(pred_vals) / len(pred_vals), 2) if pred_vals else 0.0
    avg_gt_checks = round(sum(rel_vals) / len(rel_vals), 2) if rel_vals else 0.0

    # Faithfulness — chi LLM-reasoning cases
    faith_values = [c["faithfulness"]["score"] for c in evaluated_cases if c["faithfulness"].get("method") == "keyword"]
    faith_llm_only = [c["faithfulness"]["score"] for c in evaluated_cases if c["faithfulness"].get("method") == "keyword"]

    # Action type accuracy
    action_correct = sum(1 for c in evaluated_cases if c["completeness"]["action_type"]["correct"])
    action_accuracy = round(action_correct / len(evaluated_cases), 4) if evaluated_cases else 0.0

    summary = {
        "report_type": "planning_generation_benchmark",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(evaluated_cases),

        # Tong hop theo truc
        "structure": {
            "valid_output_rate": mean_of(evaluated_cases, "structure", "valid_output"),
        },
        "faithfulness": {
            "grounded_reasoning_rate": mean_of(evaluated_cases, "faithfulness", "score"),
        },
        "correctness": {
            "check_selection_f1": f1_mean,
            "check_selection_precision": round(sum(precision_values) / len(precision_values), 4) if precision_values else 0.0,
            "check_selection_recall": round(sum(recall_values) / len(recall_values), 4) if recall_values else 0.0,
            "over_selection_rate": over_sel_mean,
            "under_selection_rate": under_sel_mean,
            "exact_match_rate": em_rate,
            "avg_predicted_checks": avg_pred_checks,
            "avg_gt_checks": avg_gt_checks,
            "service_accuracy": svc_accuracy,
            "planning_correctness": planning_corr,
            "specific_cases": len(specific_cases),
            "group_cases": len(group_cases),
            "error_cases": len(error_cases),
        },
        "completeness": {
            "action_type_accuracy": action_accuracy,
        },

        # Breakdown theo input_type
        "by_input_type": _compute_by_input_type(evaluated_cases),

        # Breakdown theo service
        "by_service": _compute_by_service(evaluated_cases),

        # Chi tiet tung case
        "cases": evaluated_cases,
    }

    # Release criteria check
    cpath = Path(criteria_path) if criteria_path else CRITERIA_FILE
    if cpath.exists():
        with open(cpath, encoding="utf-8") as f:
            criteria = json.load(f)
        summary["release_criteria"] = check_release_criteria(summary, criteria)
    else:
        logger.warning("Release criteria file not found: %s", cpath)

    return summary


def _compute_by_input_type(cases: List[Dict]) -> Dict:
    """Breakdown metrics theo input_type."""
    types = {}
    for c in cases:
        t = c.get("input_type", "unknown")
        types.setdefault(t, []).append(c)

    result = {}
    for t, group in types.items():
        specific = [c for c in group if c["correctness"].get("output_type") == "specific_checks"]
        grp = [c for c in group if c["correctness"].get("output_type") == "group_scan"]

        f1_vals = [c["correctness"]["f1"] for c in specific if c["correctness"].get("f1") is not None]
        svc_correct = sum(1 for c in grp if c["correctness"].get("service_correct"))
        action_correct = sum(1 for c in group if c["completeness"]["action_type"]["correct"])

        # New metrics per input_type
        over_vals = [c["selection_analysis"]["over_selection"]["over_selection_rate"]
                     for c in specific if c["selection_analysis"]["over_selection"].get("over_selection_rate") is not None]
        under_vals = [c["selection_analysis"]["under_selection"]["under_selection_rate"]
                      for c in specific if c["selection_analysis"]["under_selection"].get("under_selection_rate") is not None]
        em_vals = [c["selection_analysis"]["exact_match"]["exact_match"]
                   for c in specific if c["selection_analysis"]["exact_match"].get("exact_match") is not None]

        result[t] = {
            "total": len(group),
            "f1_mean": round(sum(f1_vals) / len(f1_vals), 4) if f1_vals else None,
            "service_accuracy": round(svc_correct / len(grp), 4) if grp else None,
            "action_type_accuracy": round(action_correct / len(group), 4) if group else 0.0,
            "faithfulness_mean": mean_of(group, "faithfulness", "score"),
            "over_selection_rate": round(sum(over_vals) / len(over_vals), 4) if over_vals else None,
            "under_selection_rate": round(sum(under_vals) / len(under_vals), 4) if under_vals else None,
            "exact_match_rate": round(sum(1 for v in em_vals if v) / len(em_vals), 4) if em_vals else None,
        }
    return result


def _compute_by_service(cases: List[Dict]) -> Dict:
    """Breakdown metrics theo service."""
    services = {}
    for c in cases:
        svc = c.get("service", "unknown")
        services.setdefault(svc, []).append(c)

    result = {}
    for svc, group in services.items():
        specific = [c for c in group if c["correctness"].get("output_type") == "specific_checks"]
        f1_vals = [c["correctness"]["f1"] for c in specific if c["correctness"].get("f1") is not None]

        result[svc] = {
            "total": len(group),
            "f1_mean": round(sum(f1_vals) / len(f1_vals), 4) if f1_vals else None,
        }
    return result


def save_report(report: Dict, output_dir: Optional[str] = None) -> Path:
    """Luu benchmark report va ban latest."""
    out = Path(output_dir) if output_dir else OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = out / f"planning_benchmark_run_{ts}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    # Ban latest (de dang doc)
    latest = out / "planning_benchmark_latest.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Report saved to %s", filepath)
    return filepath
