"""
Generation benchmark core engine for Risk Evaluation Agent.

Pipeline: Load cases -> Inference (goi agent that) -> Evaluate -> Aggregate -> Save

Su dung: benchmark_generation.py duoc goi tu run_gen_benchmark.py.
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

from benchmarks.llm_generation.gen_metrics import (
    check_release_criteria,
    compute_accuracy,
    compute_qwk,
    evaluate_completeness,
    evaluate_faithfulness,
    evaluate_risk_correctness,
    evaluate_structure,
    mean_of,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BENCHMARK_DIR = Path(__file__).resolve().parent
CASES_FILE = BENCHMARK_DIR / "benchmark_gen_cases.json"
CRITERIA_FILE = BENCHMARK_DIR / "release_criteria_gen.json"
INFERENCE_DIR = BENCHMARK_DIR / "inference_outputs"
OUTPUT_DIR = BENCHMARK_DIR / "benchmark_outputs"


# ---------------------------------------------------------------------------
# Step 1: Load
# ---------------------------------------------------------------------------

def load_cases(path: Optional[str] = None) -> List[Dict]:
    """Load va validate risk test cases."""

    cases_path = Path(path) if path else CASES_FILE
    if not cases_path.exists():
        raise FileNotFoundError(f"Benchmark cases file not found: {cases_path}")

    with open(cases_path, encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("risk_cases", [])
    if not cases:
        raise ValueError("No risk_cases found in benchmark file")

    # Validate schema toi gian
    for i, case in enumerate(cases):
        _validate_case(case, i)

    logger.info("Loaded %d risk test cases from %s", len(cases), cases_path.name)
    return cases


def _validate_case(case: Dict, index: int) -> None:
    """Validate 1 test case co du fields bat buoc."""
    required = ["case_id", "category", "service", "input", "expected"]
    for field in required:
        if field not in case:
            raise ValueError(f"Case #{index} missing required field: {field}")

    if "finding" not in case.get("input", {}):
        raise ValueError(f"Case #{index} ({case['case_id']}): input.finding missing")
    if "ai_severity" not in case.get("expected", {}):
        raise ValueError(f"Case #{index} ({case['case_id']}): expected.ai_severity missing")


# ---------------------------------------------------------------------------
# Step 2: Inference
# ---------------------------------------------------------------------------

def run_inference(cases: List[Dict], rag_enabled: bool = True) -> List[Dict]:
    """Chay Risk Agent cho tat ca test cases, tra ve inference outputs.

    Requires:
    - RAG server running (port 8001) neu rag_enabled=True
    - Ollama running (port 11434) voi model configured
    """
    from pdca.agents.risk_evaluation_agent import RiskEvaluationAgent
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

        logger.info(
            "[%d/%d] %s -> severity=%s, score=%s, latency=%.0fms",
            i, total, case_id,
            output["agent_output"].get("severity", "?"),
            output["agent_output"].get("risk_score", "?"),
            output["latency_ms"],
        )

    return outputs


def _run_single_inference(case: Dict, rag_client) -> Dict:
    """Chay Risk Agent cho 1 test case."""

    from pdca.agents.risk_evaluation_agent import RiskEvaluationAgent
    from pdca.config import OLLAMA_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL

    finding = case["input"]["finding"]

    # Tao agent moi cho moi case de reset cache
    agent = RiskEvaluationAgent(
        model_name=OLLAMA_MODEL,
        api_key=OLLAMA_API_KEY,
        base_url=OLLAMA_BASE_URL,
        rag_client=rag_client,
    )

    start = time.perf_counter()
    try:
        results = agent.run([finding])
        elapsed = time.perf_counter() - start

        # Agent tra ve list — lay phan tu dau tien
        scored = results[0] if results else {}
        error = None
    except Exception as e:
        elapsed = time.perf_counter() - start
        scored = {}
        error = str(e)
        logger.error("Inference failed for %s: %s", case["case_id"], e)

    # Extract agent output — field names theo actual agent code
    agent_output = {
        "severity": scored.get("severity"),
        "risk_score": scored.get("risk_score"),
        "reasoning": scored.get("reasoning", ""),
        "compliance": scored.get("compliance", []),
        "prowler_severity": scored.get("prowler_severity"),
    }

    try:
        llm_metrics = agent.get_llm_metrics()
    except Exception:
        llm_metrics = {}

    return {
        "case_id": case["case_id"],
        "agent": "risk_evaluation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latency_ms": round(elapsed * 1000, 1),
        "agent_output": agent_output,
        "rag_context_used": case.get("rag_context_snapshot", {}),
        "llm_metrics": llm_metrics,
        "error": error,
    }


def save_inference(outputs: List[Dict], run_dir: Path) -> Path:
    """Luu inference outputs vao file."""
    run_dir.mkdir(parents=True, exist_ok=True)

    filepath = run_dir / "risk_inference.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(outputs, f, indent=2, ensure_ascii=False, default=str)

    # Save metadata
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(outputs),
        "agent": "risk_evaluation",
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
    filepath = Path(run_dir) / "risk_inference.json"
    if not filepath.exists():
        raise FileNotFoundError(f"Inference file not found: {filepath}")

    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Step 3: Evaluate
# ---------------------------------------------------------------------------

def run_evaluation(cases: List[Dict], inferences: List[Dict], ollama_url: Optional[str] = None) -> List[Dict]:
    """Danh gia tat ca cases tren 4 truc metric.

    ollama_url: neu cung cap, faithfulness se dung claim-based embedding verification.
                neu None, fallback ve rule-based heuristic.
    """
    # Auto-detect Ollama neu khong truyen
    if ollama_url is None:
        try:
            from pdca.config import OLLAMA_BASE_URL
            ollama_url = OLLAMA_BASE_URL
        except ImportError:
            ollama_url = "http://localhost:11434"

    # Map inference by case_id
    inf_map = {inf["case_id"]: inf for inf in inferences}

    results = []
    for case in cases:
        case_id = case["case_id"]
        inference = inf_map.get(case_id)
        if not inference:
            logger.warning("No inference found for case %s — skipping", case_id)
            continue

        result = _evaluate_single_case(case, inference, ollama_url=ollama_url)
        results.append(result)

    logger.info("Evaluated %d cases", len(results))
    return results


def _evaluate_single_case(case: Dict, inference: Dict, ollama_url: Optional[str] = None) -> Dict:
    """Danh gia 1 test case tren ca 4 truc."""

    output = inference["agent_output"]
    expected = case["expected"]
    context = case.get("rag_context_snapshot", {})
    finding = case["input"]["finding"]

    reasoning = output.get("reasoning", "") or ""

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "service": case["service"],

        # Debug info — du thong tin de doc 1 case ma khong can mo file khac
        "debug": {
            "input_check": finding.get("event_code", ""),
            "input_description": finding.get("description", ""),
            "rag_severity": context.get("official_severity"),
            "rag_mappings": context.get("compliance_mappings", []),
            "agent_severity": output.get("severity"),
            "agent_score": output.get("risk_score"),
            "agent_reasoning": reasoning[:300],
            "expected_severity": expected["ai_severity"],
            "inference_error": inference.get("error"),
        },

        # 4 truc metrics
        "structure": evaluate_structure(output),
        "faithfulness": evaluate_faithfulness(
            reasoning, context, finding=finding, ollama_url=ollama_url,
        ),
        "correctness": evaluate_risk_correctness(
            predicted_severity=output.get("severity"),
            expected_severity=expected["ai_severity"],
            predicted_score=output.get("risk_score"),
            expected_score_range=expected.get("ai_risk_score_range"),
        ),
        "completeness": evaluate_completeness(
            reasoning=reasoning,
            required_evidence=expected.get("required_evidence", []),
        ),
    }


# ---------------------------------------------------------------------------
# Step 4: Aggregate
# ---------------------------------------------------------------------------

def aggregate_results(evaluated_cases: List[Dict], criteria_path: Optional[str] = None) -> Dict:
    """Tong hop ket qua tu tat ca cases thanh summary report."""

    summary = {
        "report_type": "generation_benchmark",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(evaluated_cases),

        # Tong hop theo truc
        "structure": {
            "json_parse_rate": mean_of(evaluated_cases, "structure", "json_parseable"),
            "schema_compliance_rate": mean_of(evaluated_cases, "structure", "schema_valid"),
            "internal_consistency_rate": mean_of(evaluated_cases, "structure", "severity_score_consistent"),
        },
        "faithfulness": {
            "mean": mean_of(evaluated_cases, "faithfulness", "score"),
        },
        "correctness": {
            "severity_accuracy": compute_accuracy(evaluated_cases),
            "severity_qwk": compute_qwk(evaluated_cases),
        },
        "completeness": {
            "evidence_coverage_mean": mean_of(evaluated_cases, "completeness", "score"),
        },

        # Breakdown theo category
        "by_category": _compute_by_category(evaluated_cases),

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


def _compute_by_category(cases: List[Dict]) -> Dict:
    """Breakdown metrics theo category (exact, paraphrase, etc.)."""
    categories = {}
    for c in cases:
        cat = c.get("category", "unknown")
        categories.setdefault(cat, []).append(c)

    result = {}
    for cat, group in categories.items():
        result[cat] = {
            "total": len(group),
            "severity_accuracy": compute_accuracy(group),
            "faithfulness_mean": mean_of(group, "faithfulness", "score"),
            "completeness_mean": mean_of(group, "completeness", "score"),
        }
    return result


def _compute_by_service(cases: List[Dict]) -> Dict:
    """Breakdown metrics theo service (s3, iam, ec2, etc.)."""
    services = {}
    for c in cases:
        svc = c.get("service", "unknown")
        services.setdefault(svc, []).append(c)

    result = {}
    for svc, group in services.items():
        result[svc] = {
            "total": len(group),
            "severity_accuracy": compute_accuracy(group),
        }
    return result


def save_report(report: Dict, output_dir: Optional[str] = None) -> Path:
    """Luu benchmark report va ban latest."""
    out = Path(output_dir) if output_dir else OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = out / f"gen_benchmark_run_{ts}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    # Copy to latest
    latest = out / "gen_benchmark_latest.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Report saved to %s", filepath)
    return filepath
