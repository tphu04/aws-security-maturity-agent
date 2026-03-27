from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


BASE_URL = "http://127.0.0.1:8000"
CONTEXT_ENDPOINT = f"{BASE_URL}/v1/context/build"
TIMEOUT = 60

ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "benchmark_s3_cases.json"
OUTPUT_PATH = ROOT / "s3_agent_readiness_benchmark_report.json"

READINESS_THRESHOLDS = {
    "planning": {
        "required_check_hit_rate_min": 0.95,
        "service_precision_avg_min": 1.0,
        "required_capability_hit_rate_min": 0.90,
        "forbidden_capability_rate_max": 0.0,
        "empty_bundle_rate_max": 0.0,
    },
    "risk": {
        "primary_check_exact_rate_min": 1.0,
        "required_check_hit_rate_min": 0.95,
        "required_capability_hit_rate_min": 0.90,
        "forbidden_capability_rate_max": 0.0,
        "empty_bundle_rate_max": 0.0,
    },
    "report": {
        "required_check_hit_rate_min": 0.95,
        "required_capability_hit_rate_min": 0.90,
        "forbidden_capability_rate_max": 0.0,
        "empty_bundle_rate_max": 0.0,
        "bundle_completeness_rate_min": 0.95,
        "report_completeness_rate_min": 0.95,
    },
}


def load_cases() -> List[Dict[str, Any]]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("benchmark_s3_cases.json must contain a list")
    return payload


def post_context_build(payload: Dict[str, Any]) -> tuple[int, Dict[str, Any], float]:
    started = time.perf_counter()
    response = requests.post(CONTEXT_ENDPOINT, json=payload, timeout=TIMEOUT)
    latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
    try:
        body = response.json()
    except Exception:
        body = {"_raw_text": response.text}
    return response.status_code, body, latency_ms


def normalize_text_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    output: List[str] = []
    for item in values:
        text = str(item).strip()
        if text:
            output.append(text)
    return output


def extract_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    data = body.get("data", {})
    return data if isinstance(data, dict) else {}


def extract_diagnostics(body: Dict[str, Any]) -> Dict[str, Any]:
    payload = extract_payload(body)
    diagnostics = payload.get("diagnostics", {})
    return diagnostics if isinstance(diagnostics, dict) else {}


def extract_checks(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    diagnostics = extract_diagnostics(body)
    values = diagnostics.get("selected_checks", [])
    return values if isinstance(values, list) else []


def extract_mappings(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    diagnostics = extract_diagnostics(body)
    values = diagnostics.get("selected_mappings", [])
    return values if isinstance(values, list) else []


def extract_capabilities(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    diagnostics = extract_diagnostics(body)
    values = diagnostics.get("selected_capabilities", [])
    return values if isinstance(values, list) else []


def extract_prompt_context(body: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = extract_diagnostics(body)
    context = diagnostics.get("prompt_ready_context", {})
    return context if isinstance(context, dict) else {}


def first_match_rank(values: List[str], expected_any: List[str]) -> Optional[int]:
    expected = {item.strip() for item in expected_any if str(item).strip()}
    if not expected:
        return None
    for index, value in enumerate(values, start=1):
        if value in expected:
            return index
    return None


def reciprocal_rank(rank: Optional[int]) -> float:
    if not rank or rank <= 0:
        return 0.0
    return round(1.0 / rank, 4)


def calc_service_precision(
    checks: List[Dict[str, Any]], allowed_services: List[str]
) -> Optional[float]:
    if not allowed_services:
        return None
    if not checks:
        return 0.0
    allowed = {item.lower() for item in allowed_services}
    hits = 0
    total = 0
    for item in checks:
        service = str(item.get("service", "")).strip().lower()
        if not service:
            continue
        total += 1
        if service in allowed:
            hits += 1
    if total == 0:
        return 0.0
    return round(hits / total, 4)


def count_non_empty(values: List[Any]) -> int:
    return sum(1 for item in values if item)


def evaluate_case(case: Dict[str, Any]) -> Dict[str, Any]:
    request_payload = case["request"]
    expectations = case["expectations"]

    http_status, body, latency_ms = post_context_build(request_payload)

    checks = extract_checks(body)
    mappings = extract_mappings(body)
    capabilities = extract_capabilities(body)
    prompt_context = extract_prompt_context(body)
    payload = extract_payload(body).get("payload", {}) or {}
    meta = body.get("meta", {}) or {}

    selected_check_ids = normalize_text_list(
        [item.get("check_id") for item in checks]
    )
    selected_capability_ids = normalize_text_list(
        [item.get("capability_id") for item in capabilities]
    )
    selected_mapping_capability_ids = normalize_text_list(
        [item.get("capability_id") for item in mappings]
    )

    required_check_ids_any = normalize_text_list(
        expectations.get("required_check_ids_any", [])
    )
    required_capability_ids_any = normalize_text_list(
        expectations.get("required_capability_ids_any", [])
    )
    forbidden_capability_ids = set(
        normalize_text_list(expectations.get("forbidden_capability_ids", []))
    )

    required_check_rank = first_match_rank(
        selected_check_ids, required_check_ids_any
    )
    required_capability_rank = first_match_rank(
        selected_capability_ids + selected_mapping_capability_ids,
        required_capability_ids_any,
    )

    primary_check_id = None
    if case["consumer"] == "risk":
        risk_bundle = payload.get("risk_bundle") or {}
        primary = risk_bundle.get("primary_finding") or {}
        primary_check_id = primary.get("check_id")

    report_bundle = payload.get("report_bundle") or {}
    report_topics = normalize_text_list(report_bundle.get("primary_topics", []))
    report_findings = report_bundle.get("key_findings", [])
    report_themes = report_bundle.get("control_themes", [])
    recommended_practices = normalize_text_list(
        report_bundle.get("recommended_practices", [])
    )

    forbidden_hits = sorted(
        forbidden_capability_ids.intersection(
            selected_capability_ids + selected_mapping_capability_ids
        )
    )

    min_check_count = int(expectations.get("min_check_count", 0))
    min_mapping_count = int(expectations.get("min_mapping_count", 0))
    min_capability_count = int(expectations.get("min_capability_count", 0))

    bundle_non_empty = count_non_empty([checks, mappings, capabilities]) > 0
    bundle_completeness_ok = (
        len(checks) >= min_check_count
        and len(mappings) >= min_mapping_count
        and len(capabilities) >= min_capability_count
    )

    report_completeness_ok = True
    if case["consumer"] == "report":
        report_completeness_ok = (
            len(report_topics) >= int(expectations.get("min_report_topics", 0))
            and len(report_findings)
            >= int(expectations.get("min_report_findings", 0))
            and len(report_themes) >= int(expectations.get("min_report_themes", 0))
            and len(recommended_practices)
            >= int(expectations.get("min_recommended_practices", 0))
        )

    case_pass = (
        http_status == 200
        and body.get("status") in {"success", "partial"}
        and required_check_rank is not None
        and required_capability_rank is not None
        and not forbidden_hits
        and bundle_non_empty
        and bundle_completeness_ok
        and report_completeness_ok
    )

    expected_primary_check_id = expectations.get("expected_primary_check_id")
    primary_check_match = (
        primary_check_id == expected_primary_check_id
        if expected_primary_check_id
        else None
    )

    warning_messages = normalize_text_list(
        [
            item.get("message")
            for item in body.get("errors", [])
            if item.get("code") == "RETRIEVAL_WARNING"
        ]
    )

    return {
        "id": case["id"],
        "consumer": case["consumer"],
        "request": request_payload,
        "http_status": http_status,
        "response_status": body.get("status"),
        "latency_ms": latency_ms,
        "confidence": meta.get("confidence"),
        "review_recommended": meta.get("review_recommended"),
        "selected_check_ids": selected_check_ids,
        "selected_capability_ids": selected_capability_ids,
        "selected_mapping_capability_ids": selected_mapping_capability_ids,
        "required_check_rank": required_check_rank,
        "required_check_mrr": reciprocal_rank(required_check_rank),
        "required_check_hit": required_check_rank is not None,
        "required_capability_rank": required_capability_rank,
        "required_capability_hit": required_capability_rank is not None,
        "primary_check_id": primary_check_id,
        "primary_check_match": primary_check_match,
        "service_precision": calc_service_precision(
            checks, normalize_text_list(expectations.get("allowed_services", []))
        ),
        "forbidden_capability_hits": forbidden_hits,
        "bundle_non_empty": bundle_non_empty,
        "bundle_completeness_ok": bundle_completeness_ok,
        "report_completeness_ok": report_completeness_ok,
        "prompt_ready_header": prompt_context.get("header"),
        "prompt_ready_guidance": prompt_context.get("guidance_block"),
        "warnings": warning_messages,
        "counts": {
            "checks": len(checks),
            "mappings": len(mappings),
            "capabilities": len(capabilities),
            "report_topics": len(report_topics),
            "report_findings": len(report_findings),
            "report_themes": len(report_themes),
            "recommended_practices": len(recommended_practices),
        },
        "expectations": expectations,
        "case_pass": case_pass,
        "raw_response": body,
    }


def average(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(statistics.mean(values), 4)


def summarize_consumer(rows: List[Dict[str, Any]], consumer: str) -> Dict[str, Any]:
    scoped = [row for row in rows if row["consumer"] == consumer]
    total = len(scoped)
    if total == 0:
        return {"total_cases": 0}

    summary = {
        "total_cases": total,
        "http_200_rate": round(
            sum(1 for row in scoped if row["http_status"] == 200) / total, 4
        ),
        "case_pass_rate": round(
            sum(1 for row in scoped if row["case_pass"]) / total, 4
        ),
        "required_check_hit_rate": round(
            sum(1 for row in scoped if row["required_check_hit"]) / total, 4
        ),
        "required_check_mrr_avg": average(
            [row["required_check_mrr"] for row in scoped]
        ),
        "required_capability_hit_rate": round(
            sum(1 for row in scoped if row["required_capability_hit"]) / total, 4
        ),
        "service_precision_avg": average(
            [
                row["service_precision"]
                for row in scoped
                if row["service_precision"] is not None
            ]
        ),
        "forbidden_capability_rate": round(
            sum(1 for row in scoped if row["forbidden_capability_hits"]) / total, 4
        ),
        "empty_bundle_rate": round(
            sum(1 for row in scoped if not row["bundle_non_empty"]) / total, 4
        ),
        "bundle_completeness_rate": round(
            sum(1 for row in scoped if row["bundle_completeness_ok"]) / total, 4
        ),
        "review_recommended_rate": round(
            sum(1 for row in scoped if row["review_recommended"] is True) / total, 4
        ),
        "average_latency_ms": round(
            statistics.mean([row["latency_ms"] for row in scoped]), 2
        ),
        "confidence_distribution": {
            key: sum(1 for row in scoped if row["confidence"] == key)
            for key in ["high", "medium", "low"]
        },
        "warning_counts": {},
        "primary_check_exact_rate": None,
        "report_completeness_rate": None,
    }

    warnings: Dict[str, int] = {}
    for row in scoped:
        for warning in row["warnings"]:
            warnings[warning] = warnings.get(warning, 0) + 1
    summary["warning_counts"] = warnings

    if consumer == "risk":
        summary["primary_check_exact_rate"] = round(
            sum(1 for row in scoped if row["primary_check_match"] is True) / total, 4
        )

    if consumer == "report":
        summary["report_completeness_rate"] = round(
            sum(1 for row in scoped if row["report_completeness_ok"]) / total, 4
        )

    return summary


def compute_readiness(summary: Dict[str, Any], consumer: str) -> Dict[str, Any]:
    thresholds = READINESS_THRESHOLDS[consumer]
    blockers: List[str] = []

    def below(metric: str, expected: float, actual: Optional[float]) -> None:
        if actual is None or actual < expected:
            blockers.append(f"{metric}={actual} < {expected}")

    def above(metric: str, expected: float, actual: Optional[float]) -> None:
        if actual is None or actual > expected:
            blockers.append(f"{metric}={actual} > {expected}")

    below(
        "required_check_hit_rate",
        thresholds["required_check_hit_rate_min"],
        summary.get("required_check_hit_rate"),
    )
    below(
        "required_capability_hit_rate",
        thresholds["required_capability_hit_rate_min"],
        summary.get("required_capability_hit_rate"),
    )
    above(
        "forbidden_capability_rate",
        thresholds["forbidden_capability_rate_max"],
        summary.get("forbidden_capability_rate"),
    )
    above(
        "empty_bundle_rate",
        thresholds["empty_bundle_rate_max"],
        summary.get("empty_bundle_rate"),
    )

    if "service_precision_avg_min" in thresholds:
        below(
            "service_precision_avg",
            thresholds["service_precision_avg_min"],
            summary.get("service_precision_avg"),
        )

    if "primary_check_exact_rate_min" in thresholds:
        below(
            "primary_check_exact_rate",
            thresholds["primary_check_exact_rate_min"],
            summary.get("primary_check_exact_rate"),
        )

    if "bundle_completeness_rate_min" in thresholds:
        below(
            "bundle_completeness_rate",
            thresholds["bundle_completeness_rate_min"],
            summary.get("bundle_completeness_rate"),
        )

    if "report_completeness_rate_min" in thresholds:
        below(
            "report_completeness_rate",
            thresholds["report_completeness_rate_min"],
            summary.get("report_completeness_rate"),
        )

    status = "ready" if not blockers else "blocked"
    return {
        "status": status,
        "blockers": blockers,
        "thresholds": thresholds,
    }


def build_report(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    consumers = sorted({row["consumer"] for row in rows})
    summaries = {consumer: summarize_consumer(rows, consumer) for consumer in consumers}
    readiness = {
        consumer: compute_readiness(summaries[consumer], consumer)
        for consumer in consumers
    }
    return {
        "benchmark_name": "s3_agent_readiness",
        "base_url": BASE_URL,
        "endpoint": CONTEXT_ENDPOINT,
        "generated_from": str(CASES_PATH),
        "total_cases": len(rows),
        "consumer_summaries": summaries,
        "consumer_readiness": readiness,
        "cases": rows,
    }


def print_report(report: Dict[str, Any]) -> None:
    print("=" * 100)
    print("S3 AGENT READINESS BENCHMARK")
    print("=" * 100)
    print(f"Base URL    : {report['base_url']}")
    print(f"Endpoint    : {report['endpoint']}")
    print(f"Cases       : {report['total_cases']}")

    for consumer, summary in report["consumer_summaries"].items():
        readiness = report["consumer_readiness"][consumer]
        print("\n" + "-" * 100)
        print(f"{consumer.upper()} | readiness={readiness['status']}")
        print("-" * 100)
        print(f"required_check_hit_rate   : {summary.get('required_check_hit_rate')}")
        print(f"required_check_mrr_avg    : {summary.get('required_check_mrr_avg')}")
        print(f"required_capability_hit   : {summary.get('required_capability_hit_rate')}")
        print(f"service_precision_avg     : {summary.get('service_precision_avg')}")
        print(f"forbidden_capability_rate : {summary.get('forbidden_capability_rate')}")
        print(f"empty_bundle_rate         : {summary.get('empty_bundle_rate')}")
        print(f"bundle_completeness_rate  : {summary.get('bundle_completeness_rate')}")
        print(f"review_recommended_rate   : {summary.get('review_recommended_rate')}")
        print(f"average_latency_ms        : {summary.get('average_latency_ms')}")
        if summary.get("primary_check_exact_rate") is not None:
            print(
                f"primary_check_exact_rate  : {summary.get('primary_check_exact_rate')}"
            )
        if summary.get("report_completeness_rate") is not None:
            print(
                f"report_completeness_rate  : {summary.get('report_completeness_rate')}"
            )
        print(f"confidence_distribution   : {summary.get('confidence_distribution')}")
        print(f"warning_counts            : {summary.get('warning_counts')}")
        if readiness["blockers"]:
            print("blockers:")
            for blocker in readiness["blockers"]:
                print(f"  - {blocker}")


def main() -> None:
    cases = load_cases()
    rows = [evaluate_case(case) for case in cases]
    report = build_report(rows)
    OUTPUT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print_report(report)
    print(f"\n[saved] {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
