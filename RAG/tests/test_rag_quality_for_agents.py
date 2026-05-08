"""
RAG Quality Evaluation for Agent Consumers
===========================================
Script truy van RAG va danh gia chat luong content tra ve.
Phan tich xem PlanningAgent, RiskEvaluationAgent, ReportAgent
co dung duoc context tu RAG khong.

Usage:
    cd RAG
    python -m tests.test_rag_quality_for_agents
"""

import json
import time
import sys
import os
import statistics
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RAG_BASE_URL = os.getenv("RAG_BASE_URL", "http://localhost:9005")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "debug_outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Test cases: mo phong cac truy van that su tu cac agent
# ---------------------------------------------------------------------------
PLANNING_QUERIES = [
    {
        "case_id": "plan_s3_general",
        "description": "PlanningAgent: User yeu cau kiem tra bao mat S3",
        "query": "check s3 security",
        "service": "s3",
        "expected_service": "s3",
        "min_results": 3,
    },
    {
        "case_id": "plan_iam_access",
        "description": "PlanningAgent: User yeu cau kiem tra IAM access keys",
        "query": "check iam access keys rotation",
        "service": "iam",
        "expected_service": "iam",
        "min_results": 1,
    },
    {
        "case_id": "plan_encryption",
        "description": "PlanningAgent: User hoi ve encryption",
        "query": "check encryption at rest for s3 buckets",
        "service": "s3",
        "expected_service": "s3",
        "min_results": 1,
    },
    {
        "case_id": "plan_public_access",
        "description": "PlanningAgent: User lo ngai public exposure",
        "query": "are my s3 buckets publicly accessible",
        "service": "s3",
        "expected_service": "s3",
        "min_results": 2,
    },
    {
        "case_id": "plan_logging",
        "description": "PlanningAgent: User hoi ve logging",
        "query": "check cloudtrail logging enabled",
        "service": "cloudtrail",
        "expected_service": "cloudtrail",
        "min_results": 1,
    },
]

RISK_CHECK_IDS = [
    {
        "case_id": "risk_s3_public_access",
        "description": "RiskAgent: Finding ve S3 public access block",
        "check_ids": ["check:s3_bucket_level_public_access_block"],
        "expected_fields": ["severity", "title", "check_id"],
        "expected_mapping": True,
    },
    {
        "case_id": "risk_s3_encryption",
        "description": "RiskAgent: Finding ve S3 encryption",
        "check_ids": ["check:s3_bucket_default_encryption"],
        "expected_fields": ["severity", "title", "check_id"],
        "expected_mapping": True,
    },
    {
        "case_id": "risk_s3_secure_transport",
        "description": "RiskAgent: Finding ve HTTPS enforcement",
        "check_ids": ["check:s3_bucket_secure_transport_policy"],
        "expected_fields": ["severity", "title", "check_id"],
        "expected_mapping": True,
    },
    {
        "case_id": "risk_multi_check",
        "description": "RiskAgent: Batch nhieu findings cung luc",
        "check_ids": [
            "check:s3_bucket_level_public_access_block",
            "check:s3_bucket_default_encryption",
            "check:s3_bucket_versioning",
        ],
        "expected_fields": ["severity", "title", "check_id"],
        "expected_mapping": True,
    },
    {
        "case_id": "risk_nonexistent_check",
        "description": "RiskAgent: Check ID khong ton tai (edge case)",
        "check_ids": ["check:nonexistent_fake_check_xyz"],
        "expected_fields": [],
        "expected_mapping": False,
    },
]

REPORT_QUERIES = [
    {
        "case_id": "report_s3_overview",
        "description": "ReportAgent: Tong hop bao cao S3",
        "query": "s3 security assessment overview",
        "check_ids": [
            "check:s3_bucket_level_public_access_block",
            "check:s3_bucket_default_encryption",
        ],
        "expected_topics": ["s3"],
        "expected_min_findings": 2,
        "expected_min_practices": 1,
    },
    {
        "case_id": "report_query_only",
        "description": "ReportAgent: Chi dung query, khong co check_ids",
        "query": "s3 bucket security risks and encryption",
        "check_ids": [],
        "expected_topics": ["s3"],
        "expected_min_findings": 1,
        "expected_min_practices": 0,
    },
]


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------
@dataclass
class TestResult:
    case_id: str
    consumer: str
    description: str
    passed: bool
    latency_ms: float
    issues: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentUsabilityVerdict:
    agent_name: str
    can_use_content: bool
    score: float  # 0.0 - 1.0
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _post(endpoint: str, payload: dict, timeout: int = 15) -> Dict[str, Any]:
    url = f"{RAG_BASE_URL}{endpoint}"
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _check_health() -> bool:
    try:
        resp = requests.get(f"{RAG_BASE_URL}/health", timeout=5)
        data = resp.json()
        return data.get("status") == "ok"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 1. PLANNING AGENT TESTS
# ---------------------------------------------------------------------------
def test_planning_queries() -> List[TestResult]:
    """
    PlanningAgent goi /v1/retrieve/checks voi query + service.
    Kiem tra:
    - Co tra ve ket qua khong
    - Ket qua co dung service khong
    - Co doc_id / check_id de extract khong
    - Score co du cao khong
    """
    results = []

    for case in PLANNING_QUERIES:
        issues = []
        details: Dict[str, Any] = {}

        payload = {
            "query": case["query"],
            "service": case.get("service"),
            "top_k": 10,
            "retrieval_mode": "hybrid",
            "debug": True,
        }

        t0 = time.perf_counter()
        try:
            data = _post("/v1/retrieve/checks", payload)
        except Exception as e:
            results.append(TestResult(
                case_id=case["case_id"], consumer="planning",
                description=case["description"], passed=False,
                latency_ms=0, issues=[f"Request failed: {e}"],
            ))
            continue
        latency = (time.perf_counter() - t0) * 1000

        raw_results = data.get("data", {}).get("results", [])
        meta = data.get("meta", {})
        confidence = meta.get("confidence", "unknown")

        details["result_count"] = len(raw_results)
        details["confidence"] = confidence
        details["retrieval_mode"] = payload["retrieval_mode"]

        # --- Check 1: so luong ket qua ---
        if len(raw_results) < case["min_results"]:
            issues.append(
                f"Ket qua qua it: {len(raw_results)} < {case['min_results']} (min)"
            )

        # --- Check 2: service match ---
        service_matched = 0
        service_mismatched = 0
        extractable_ids = []

        for item in raw_results:
            item_meta = item.get("metadata", {})
            item_svc = item_meta.get("service", "").lower()
            doc_id = item.get("doc_id", "")

            if item_svc == case["expected_service"]:
                service_matched += 1
            elif item_svc:
                service_mismatched += 1

            # PlanningAgent can doc_id hoac check_id
            if doc_id:
                extractable_ids.append(doc_id)
            elif item_meta.get("check_id"):
                extractable_ids.append(item_meta["check_id"])

        details["service_matched"] = service_matched
        details["service_mismatched"] = service_mismatched
        details["extractable_check_ids"] = extractable_ids[:5]

        if service_matched == 0 and len(raw_results) > 0:
            issues.append(
                f"Khong co result nao match service '{case['expected_service']}'"
            )

        if service_mismatched > service_matched and len(raw_results) >= 3:
            issues.append(
                f"Da so result sai service: {service_mismatched} sai vs {service_matched} dung"
            )

        # --- Check 3: co check_id de extract khong ---
        if not extractable_ids and len(raw_results) > 0:
            issues.append("Khong extract duoc check_id nao tu results")

        # --- Check 4: score top-1 ---
        if raw_results:
            top_score = raw_results[0].get("score", 0)
            details["top1_score"] = top_score
            if top_score < 0.2:
                issues.append(f"Top-1 score qua thap: {top_score:.3f}")

        # --- Check 5: confidence ---
        if confidence == "low":
            issues.append(f"Confidence = low, PlanningAgent co the fallback group scan")

        passed = len(issues) == 0
        results.append(TestResult(
            case_id=case["case_id"], consumer="planning",
            description=case["description"], passed=passed,
            latency_ms=round(latency, 1), issues=issues, details=details,
        ))

    return results


# ---------------------------------------------------------------------------
# 2. RISK AGENT TESTS
# ---------------------------------------------------------------------------
def test_risk_context_build() -> List[TestResult]:
    """
    RiskEvaluationAgent goi /v1/context/build voi consumer="risk".
    Kiem tra:
    - risk_bundle co ton tai khong
    - related_findings co du fields (check_id, severity, title)
    - control_mapping co data mapping khong
    - maturity_context co cung cap guidance khong
    """
    results = []

    for case in RISK_CHECK_IDS:
        issues = []
        details: Dict[str, Any] = {}

        payload = {
            "consumer": "risk",
            "check_ids": case["check_ids"],
            "include_mappings": True,
            "debug": True,
        }

        t0 = time.perf_counter()
        try:
            data = _post("/v1/context/build", payload)
        except Exception as e:
            results.append(TestResult(
                case_id=case["case_id"], consumer="risk",
                description=case["description"], passed=False,
                latency_ms=0, issues=[f"Request failed: {e}"],
            ))
            continue
        latency = (time.perf_counter() - t0) * 1000

        status = data.get("status", "unknown")
        meta = data.get("meta", {})
        confidence = meta.get("confidence", "unknown")
        payload_data = data.get("data", {}).get("payload", {})
        risk_bundle = payload_data.get("risk_bundle", {})

        details["status"] = status
        details["confidence"] = confidence

        # --- Edge case: nonexistent check ---
        if case["case_id"] == "risk_nonexistent_check":
            # Mong doi: khong co primary_finding, confidence thap
            if risk_bundle.get("primary_finding"):
                issues.append("Tra ve primary_finding cho check khong ton tai!")
            if confidence == "high":
                issues.append("Confidence = high cho check khong ton tai!")
            passed = len(issues) == 0
            results.append(TestResult(
                case_id=case["case_id"], consumer="risk",
                description=case["description"], passed=passed,
                latency_ms=round(latency, 1), issues=issues, details=details,
            ))
            continue

        # --- Check 1: risk_bundle ton tai ---
        if not risk_bundle:
            issues.append("risk_bundle rong hoac khong ton tai")
            results.append(TestResult(
                case_id=case["case_id"], consumer="risk",
                description=case["description"], passed=False,
                latency_ms=round(latency, 1), issues=issues, details=details,
            ))
            continue

        # --- Check 2: related_findings ---
        related = risk_bundle.get("related_findings", [])
        details["related_findings_count"] = len(related)

        if not related:
            issues.append("related_findings rong — RiskAgent khong co data check nao")
        else:
            for expected_field in case["expected_fields"]:
                sample = related[0]
                if expected_field not in sample or sample[expected_field] is None:
                    issues.append(
                        f"related_findings[0] thieu field '{expected_field}' "
                        f"— RiskAgent khong doc duoc severity/title"
                    )

        # --- Check 3: primary_finding ---
        primary = risk_bundle.get("primary_finding")
        details["has_primary_finding"] = primary is not None
        if primary:
            details["primary_check_id"] = primary.get("check_id")
            details["primary_severity"] = primary.get("severity")
            details["has_description"] = primary.get("description") is not None
            details["has_risk"] = primary.get("risk") is not None
            details["has_remediation"] = primary.get("remediation") is not None
        else:
            issues.append("primary_finding = null — RiskAgent mat finding chinh")

        # --- Check 4: control_mapping ---
        mappings = risk_bundle.get("control_mapping", [])
        details["mapping_count"] = len(mappings)

        if case["expected_mapping"] and not mappings:
            issues.append(
                "control_mapping rong — RiskAgent khong co compliance info"
            )

        if mappings:
            sample_mapping = mappings[0]
            for key in ["check_id", "capability_id"]:
                if key not in sample_mapping:
                    issues.append(f"control_mapping[0] thieu '{key}'")

        # --- Check 5: maturity_context ---
        maturity = risk_bundle.get("maturity_context", [])
        details["maturity_count"] = len(maturity)
        if maturity:
            sample_cap = maturity[0]
            for key in ["capability_id", "capability_name"]:
                if key not in sample_cap or not sample_cap[key]:
                    issues.append(f"maturity_context[0] thieu '{key}'")

        # --- Check 6: RiskAgent co the xay dung rag_context_map khong? ---
        # Simulate logic giong RiskEvaluationAgent._fetch_risk_context_batch
        context_map = {}
        for f in related:
            cid = f.get("check_id")
            if cid:
                clean_id = str(cid).replace("check:", "")
                context_map[clean_id] = {
                    "severity": f.get("severity"),
                    "title": f.get("title"),
                    "mappings": [],
                }
        for m in mappings:
            cid = m.get("check_id")
            clean_id = str(cid).replace("check:", "")
            if clean_id in context_map:
                context_map[clean_id]["mappings"].append(m.get("capability_id"))

        details["simulated_context_map_keys"] = list(context_map.keys())

        if not context_map and case["expected_mapping"]:
            issues.append(
                "Simulate RiskAgent context_map rong — agent se khong co RAG data"
            )

        # Kiem tra chat luong context_map
        for cid, ctx in context_map.items():
            if not ctx.get("severity"):
                issues.append(f"context_map[{cid}] thieu severity")
            if not ctx.get("title"):
                issues.append(f"context_map[{cid}] thieu title")

        passed = len(issues) == 0
        results.append(TestResult(
            case_id=case["case_id"], consumer="risk",
            description=case["description"], passed=passed,
            latency_ms=round(latency, 1), issues=issues, details=details,
        ))

    return results


# ---------------------------------------------------------------------------
# 3. REPORT AGENT TESTS
# ---------------------------------------------------------------------------
def test_report_context_build() -> List[TestResult]:
    """
    ReportAgent nhan data da aggregated, nhung context tu RAG
    co the dung de lam giau report (qua endpoint context/build consumer="report").
    Kiem tra:
    - report_bundle co key_findings, primary_topics, control_themes
    - recommended_practices co noi dung khong
    """
    results = []

    for case in REPORT_QUERIES:
        issues = []
        details: Dict[str, Any] = {}

        payload: Dict[str, Any] = {
            "consumer": "report",
            "debug": True,
        }
        if case.get("query"):
            payload["query"] = case["query"]
        if case.get("check_ids"):
            payload["check_ids"] = case["check_ids"]

        t0 = time.perf_counter()
        try:
            data = _post("/v1/context/build", payload)
        except Exception as e:
            results.append(TestResult(
                case_id=case["case_id"], consumer="report",
                description=case["description"], passed=False,
                latency_ms=0, issues=[f"Request failed: {e}"],
            ))
            continue
        latency = (time.perf_counter() - t0) * 1000

        payload_data = data.get("data", {}).get("payload", {})
        report_bundle = payload_data.get("report_bundle", {})
        meta = data.get("meta", {})

        details["confidence"] = meta.get("confidence", "unknown")
        details["status"] = data.get("status", "unknown")

        if not report_bundle:
            issues.append("report_bundle rong hoac khong ton tai")
            results.append(TestResult(
                case_id=case["case_id"], consumer="report",
                description=case["description"], passed=False,
                latency_ms=round(latency, 1), issues=issues, details=details,
            ))
            continue

        # --- Check 1: primary_topics ---
        topics = report_bundle.get("primary_topics", [])
        details["primary_topics"] = topics
        if case.get("expected_topics"):
            for t in case["expected_topics"]:
                if t not in topics:
                    issues.append(f"primary_topics thieu '{t}'")

        # --- Check 2: key_findings ---
        findings = report_bundle.get("key_findings", [])
        details["key_findings_count"] = len(findings)
        if len(findings) < case.get("expected_min_findings", 1):
            issues.append(
                f"key_findings chi co {len(findings)}, can >= {case['expected_min_findings']}"
            )
        if findings:
            sample = findings[0]
            for key in ["check_id", "title", "severity"]:
                if not sample.get(key):
                    issues.append(f"key_findings[0] thieu '{key}'")
            if sample.get("risk_summary"):
                details["sample_risk_summary_len"] = len(sample["risk_summary"])

        # --- Check 3: control_themes ---
        themes = report_bundle.get("control_themes", [])
        details["control_themes_count"] = len(themes)
        if themes:
            for theme in themes:
                if not theme.get("capability_name"):
                    issues.append("control_themes co item thieu capability_name")
                    break

        # --- Check 4: recommended_practices ---
        practices = report_bundle.get("recommended_practices", [])
        details["recommended_practices_count"] = len(practices)
        if len(practices) < case.get("expected_min_practices", 0):
            issues.append(
                f"recommended_practices chi co {len(practices)}, "
                f"can >= {case['expected_min_practices']}"
            )
        if practices:
            avg_len = statistics.mean([len(p) for p in practices])
            details["avg_practice_length"] = round(avg_len, 1)
            if avg_len < 10:
                issues.append("recommended_practices qua ngan, khong co gia tri")

        passed = len(issues) == 0
        results.append(TestResult(
            case_id=case["case_id"], consumer="report",
            description=case["description"], passed=passed,
            latency_ms=round(latency, 1), issues=issues, details=details,
        ))

    return results


# ---------------------------------------------------------------------------
# 4. CROSS-CONSUMER CONSISTENCY TEST
# ---------------------------------------------------------------------------
def test_cross_consumer_consistency() -> List[TestResult]:
    """
    Gui cung 1 check_ids cho ca 3 consumers, kiem tra:
    - Ca 3 deu tra ve data
    - Check IDs xuat hien nhat quan
    - Confidence khong chenh lech qua lon
    """
    results = []
    shared_check_ids = [
        "check:s3_bucket_level_public_access_block",
        "check:s3_bucket_default_encryption",
    ]

    consumer_responses: Dict[str, Dict[str, Any]] = {}

    for consumer in ["planning", "risk", "report"]:
        payload = {
            "consumer": consumer,
            "check_ids": shared_check_ids,
            "include_mappings": True,
            "debug": True,
        }

        t0 = time.perf_counter()
        try:
            data = _post("/v1/context/build", payload)
            consumer_responses[consumer] = data
        except Exception as e:
            consumer_responses[consumer] = {"error": str(e)}
        latency = (time.perf_counter() - t0) * 1000

    issues = []
    details: Dict[str, Any] = {}

    # Check 1: tat ca consumers deu tra ve thanh cong
    for consumer, resp in consumer_responses.items():
        if "error" in resp:
            issues.append(f"{consumer}: Request failed — {resp['error']}")
        else:
            status = resp.get("status", "unknown")
            conf = resp.get("meta", {}).get("confidence", "unknown")
            details[f"{consumer}_status"] = status
            details[f"{consumer}_confidence"] = conf

            if status == "error":
                issues.append(f"{consumer}: status = error")

    # Check 2: bundle key phai ton tai
    if "error" not in consumer_responses.get("planning", {}):
        pb = (consumer_responses["planning"]
              .get("data", {}).get("payload", {}).get("planning_bundle"))
        if not pb:
            issues.append("planning: planning_bundle khong ton tai")
        else:
            details["planning_findings_count"] = len(pb.get("related_findings", []))

    if "error" not in consumer_responses.get("risk", {}):
        rb = (consumer_responses["risk"]
              .get("data", {}).get("payload", {}).get("risk_bundle"))
        if not rb:
            issues.append("risk: risk_bundle khong ton tai")
        else:
            details["risk_findings_count"] = len(rb.get("related_findings", []))
            details["risk_mappings_count"] = len(rb.get("control_mapping", []))

    if "error" not in consumer_responses.get("report", {}):
        rpb = (consumer_responses["report"]
               .get("data", {}).get("payload", {}).get("report_bundle"))
        if not rpb:
            issues.append("report: report_bundle khong ton tai")
        else:
            details["report_findings_count"] = len(rpb.get("key_findings", []))
            details["report_themes_count"] = len(rpb.get("control_themes", []))

    # Check 3: confidence consistency
    confidences = []
    conf_rank = {"high": 3, "medium": 2, "low": 1}
    for consumer in ["planning", "risk", "report"]:
        c = details.get(f"{consumer}_confidence", "unknown")
        if c in conf_rank:
            confidences.append(conf_rank[c])

    if len(confidences) >= 2:
        gap = max(confidences) - min(confidences)
        details["confidence_gap"] = gap
        if gap > 1:
            issues.append(
                f"Confidence chenh lech lon giua consumers (gap={gap})"
            )

    passed = len(issues) == 0
    results.append(TestResult(
        case_id="cross_consumer_consistency",
        consumer="all",
        description="Nhat quan du lieu giua 3 consumers voi cung check_ids",
        passed=passed,
        latency_ms=0,
        issues=issues,
        details=details,
    ))

    return results


# ---------------------------------------------------------------------------
# 5. LATENCY BENCHMARK
# ---------------------------------------------------------------------------
def test_latency() -> List[TestResult]:
    """Do latency trung binh cua cac endpoint."""
    results = []
    MAX_MS = 2000  # 2 giay la qua cham

    # /v1/retrieve/checks
    latencies = []
    for _ in range(3):
        t0 = time.perf_counter()
        try:
            _post("/v1/retrieve/checks", {
                "query": "s3 public access", "top_k": 5,
                "retrieval_mode": "hybrid",
            })
            latencies.append((time.perf_counter() - t0) * 1000)
        except Exception:
            pass

    issues = []
    if latencies:
        avg = statistics.mean(latencies)
        if avg > MAX_MS:
            issues.append(f"retrieve/checks avg latency = {avg:.0f}ms > {MAX_MS}ms")
        results.append(TestResult(
            case_id="latency_retrieve_checks", consumer="all",
            description="Latency trung binh /v1/retrieve/checks",
            passed=len(issues) == 0,
            latency_ms=round(avg, 1),
            issues=issues,
            details={"latencies_ms": [round(l, 1) for l in latencies]},
        ))

    # /v1/context/build
    latencies2 = []
    for _ in range(3):
        t0 = time.perf_counter()
        try:
            _post("/v1/context/build", {
                "consumer": "risk",
                "check_ids": ["check:s3_bucket_default_encryption"],
                "include_mappings": True,
            })
            latencies2.append((time.perf_counter() - t0) * 1000)
        except Exception:
            pass

    issues2 = []
    if latencies2:
        avg2 = statistics.mean(latencies2)
        if avg2 > MAX_MS:
            issues2.append(f"context/build avg latency = {avg2:.0f}ms > {MAX_MS}ms")
        results.append(TestResult(
            case_id="latency_context_build", consumer="all",
            description="Latency trung binh /v1/context/build",
            passed=len(issues2) == 0,
            latency_ms=round(avg2, 1),
            issues=issues2,
            details={"latencies_ms": [round(l, 1) for l in latencies2]},
        ))

    return results


# ---------------------------------------------------------------------------
# AGENT USABILITY ANALYSIS
# ---------------------------------------------------------------------------
def analyze_agent_usability(all_results: List[TestResult]) -> List[AgentUsabilityVerdict]:
    """
    Phan tich tong hop: moi agent co dung duoc content RAG khong?
    """
    verdicts = []

    for agent_name, consumer_key in [
        ("PlanningAgent", "planning"),
        ("RiskEvaluationAgent", "risk"),
        ("ReportAgent", "report"),
    ]:
        agent_tests = [r for r in all_results if r.consumer == consumer_key]
        if not agent_tests:
            verdicts.append(AgentUsabilityVerdict(
                agent_name=agent_name, can_use_content=False, score=0.0,
                weaknesses=["Khong co test nao duoc chay"],
            ))
            continue

        passed_count = sum(1 for r in agent_tests if r.passed)
        total_count = len(agent_tests)
        score = passed_count / total_count if total_count > 0 else 0.0

        strengths = []
        weaknesses = []
        recommendations = []

        all_issues = []
        for r in agent_tests:
            all_issues.extend(r.issues)

        # --- PlanningAgent specific ---
        if consumer_key == "planning":
            service_issues = [i for i in all_issues if "service" in i.lower()]
            id_issues = [i for i in all_issues if "check_id" in i.lower()]
            result_issues = [i for i in all_issues if "ket qua" in i.lower() or "result" in i.lower()]

            if not service_issues:
                strengths.append(
                    "Service filter hoat dong tot — "
                    "PlanningAgent nhan dung service checks"
                )
            else:
                weaknesses.append(
                    f"Service filter yeu: {len(service_issues)} loi — "
                    "PlanningAgent co the chon sai checks"
                )
                recommendations.append(
                    "Tang trong so service filter trong hybrid merge "
                    "hoac them hard filter o pipeline level"
                )

            if not id_issues:
                strengths.append(
                    "Check IDs extract duoc tu moi result — "
                    "PlanningAgent co the tao assessment_plan"
                )
            else:
                weaknesses.append(
                    "Mot so result khong co doc_id/check_id — "
                    "PlanningAgent mat check"
                )

            if not result_issues:
                strengths.append(
                    "So luong ket qua du cho PlanningAgent chon loc"
                )

        # --- RiskEvaluationAgent specific ---
        elif consumer_key == "risk":
            mapping_issues = [i for i in all_issues if "mapping" in i.lower() or "compliance" in i.lower()]
            severity_issues = [i for i in all_issues if "severity" in i.lower()]
            primary_issues = [i for i in all_issues if "primary" in i.lower()]
            context_issues = [i for i in all_issues if "context_map" in i.lower()]

            if not severity_issues:
                strengths.append(
                    "Severity data co san trong risk_bundle.related_findings — "
                    "RiskAgent dung de so sanh voi Prowler severity"
                )
            else:
                weaknesses.append(
                    "Thieu severity data — RiskAgent phai doan severity, "
                    "lam giam do chinh xac risk_score"
                )

            if not mapping_issues:
                strengths.append(
                    "control_mapping co data — "
                    "RiskAgent biet duoc finding vi pham compliance nao (CIS, PCI-DSS...)"
                )
            else:
                weaknesses.append(
                    f"Mapping yeu: {len(mapping_issues)} loi — "
                    "RiskAgent thieu compliance context, ai_reasoning se khong nhac toi frameworks"
                )
                recommendations.append(
                    "Kiem tra lai maturity_mappings.json — dam bao mapping "
                    "da duoc curate cho cac check pho bien"
                )

            if not primary_issues:
                strengths.append(
                    "primary_finding co day du (description, risk, remediation) — "
                    "RiskAgent co the hieu sau ve vulnerability"
                )

            if not context_issues:
                strengths.append(
                    "Simulated context_map build thanh cong — "
                    "RiskAgent._fetch_risk_context_batch se parse dung"
                )

        # --- ReportAgent specific ---
        elif consumer_key == "report":
            topic_issues = [i for i in all_issues if "topic" in i.lower()]
            finding_issues = [i for i in all_issues if "finding" in i.lower()]
            practice_issues = [i for i in all_issues if "practice" in i.lower()]
            theme_issues = [i for i in all_issues if "theme" in i.lower()]

            if not finding_issues:
                strengths.append(
                    "key_findings co du data — "
                    "ReportAgent co the tong hop findings vao report"
                )
            else:
                weaknesses.append(
                    "key_findings thieu hoac khong du — "
                    "ReportAgent se thieu technical evidence trong report"
                )

            if not topic_issues:
                strengths.append(
                    "primary_topics chinh xac — "
                    "ReportAgent biet report ve service nao"
                )

            if not practice_issues:
                strengths.append(
                    "recommended_practices co san — "
                    "ReportAgent co the dua vao phan Recommendations"
                )
            else:
                weaknesses.append(
                    "recommended_practices thieu — "
                    "ReportAgent phai tu tao recommendations, co the khong sat thuc te"
                )
                recommendations.append(
                    "Bo sung recommended_practices vao maturity_capabilities.json "
                    "hoac fallback tu remediation text trong checks"
                )

            if not theme_issues:
                strengths.append(
                    "control_themes co san — "
                    "ReportAgent co the viet phan control framework alignment"
                )

        can_use = score >= 0.6
        verdicts.append(AgentUsabilityVerdict(
            agent_name=agent_name,
            can_use_content=can_use,
            score=round(score, 2),
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=recommendations,
        ))

    return verdicts


# ---------------------------------------------------------------------------
# REPORT GENERATION
# ---------------------------------------------------------------------------
def print_report(
    all_results: List[TestResult],
    verdicts: List[AgentUsabilityVerdict],
):
    print("\n" + "=" * 72)
    print("   RAG QUALITY EVALUATION FOR AGENT CONSUMERS")
    print("=" * 72)

    # --- Per-test results ---
    consumers = ["planning", "risk", "report", "all"]
    for consumer in consumers:
        tests = [r for r in all_results if r.consumer == consumer]
        if not tests:
            continue

        label = {
            "planning": "PLANNING AGENT",
            "risk": "RISK EVALUATION AGENT",
            "report": "REPORT AGENT",
            "all": "CROSS-CUTTING / LATENCY",
        }[consumer]

        print(f"\n--- {label} ---")
        for r in tests:
            status = "PASS" if r.passed else "FAIL"
            print(f"  [{status}] {r.case_id} ({r.latency_ms:.0f}ms)")
            print(f"         {r.description}")
            if r.issues:
                for issue in r.issues:
                    print(f"         ! {issue}")
            for key in ["result_count", "confidence", "related_findings_count",
                         "mapping_count", "maturity_count", "key_findings_count",
                         "recommended_practices_count"]:
                if key in r.details:
                    print(f"         > {key}: {r.details[key]}")

    # --- Summary ---
    total = len(all_results)
    passed = sum(1 for r in all_results if r.passed)
    failed = total - passed
    print(f"\n{'=' * 72}")
    print(f"TONG KET: {passed}/{total} passed, {failed} failed")
    print(f"{'=' * 72}")

    # --- Agent Usability Verdicts ---
    print(f"\n{'=' * 72}")
    print("   PHAN TICH KHA NANG SU DUNG RAG CONTENT CHO TUNG AGENT")
    print(f"{'=' * 72}")

    for v in verdicts:
        usable = "CO THE DUNG" if v.can_use_content else "CHUA DU TOT"
        print(f"\n  [{usable}] {v.agent_name} (score: {v.score:.0%})")

        if v.strengths:
            print("    Diem manh:")
            for s in v.strengths:
                print(f"      + {s}")

        if v.weaknesses:
            print("    Diem yeu:")
            for w in v.weaknesses:
                print(f"      - {w}")

        if v.recommendations:
            print("    Khuyen nghi:")
            for rec in v.recommendations:
                print(f"      >> {rec}")

    print()


def save_json_report(
    all_results: List[TestResult],
    verdicts: List[AgentUsabilityVerdict],
):
    report = {
        "timestamp": datetime.now().isoformat(),
        "rag_base_url": RAG_BASE_URL,
        "summary": {
            "total_tests": len(all_results),
            "passed": sum(1 for r in all_results if r.passed),
            "failed": sum(1 for r in all_results if not r.passed),
        },
        "test_results": [asdict(r) for r in all_results],
        "agent_verdicts": [asdict(v) for v in verdicts],
    }

    output_path = os.path.join(OUTPUT_DIR, "rag_quality_report.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"JSON report saved: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print("Checking RAG service health...")
    if not _check_health():
        print(f"RAG service khong san sang tai {RAG_BASE_URL}")
        print("Hay chay: cd RAG && uvicorn app.main:app --port 9005")
        sys.exit(1)
    print(f"RAG service OK ({RAG_BASE_URL})")

    all_results: List[TestResult] = []

    print("\n[1/5] Testing PlanningAgent queries...")
    all_results.extend(test_planning_queries())

    print("[2/5] Testing RiskAgent context build...")
    all_results.extend(test_risk_context_build())

    print("[3/5] Testing ReportAgent context build...")
    all_results.extend(test_report_context_build())

    print("[4/5] Testing cross-consumer consistency...")
    all_results.extend(test_cross_consumer_consistency())

    print("[5/5] Testing latency...")
    all_results.extend(test_latency())

    # Analyze
    verdicts = analyze_agent_usability(all_results)

    # Output
    print_report(all_results, verdicts)
    save_json_report(all_results, verdicts)


if __name__ == "__main__":
    main()
