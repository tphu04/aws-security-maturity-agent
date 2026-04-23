import os
import json
import uuid
import time
from datetime import datetime
from typing import Literal, Dict, List, Any
from contextlib import contextmanager

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv

from pdca.state import PDCAState

# Import các agent cũ (không thay đổi)
from pdca.agents.environment_agent import EnvironmentAgent
from pdca.agents.planning_agent import PlanningAgent
from pdca.agents.monitoring_agent import MonitoringAgent
from pdca.agents.risk_evaluation_agent import RiskEvaluationAgent
from pdca.agents.remediate_planner_agent import RemediationPlannerAgent
from pdca.agents.execution_agent import ExecutionAgent
from pdca.agents.scanner_agent import ScannerAgent
from pdca.agents.rescan_agent import RescanAgent
from pdca.agents.analysis_agent import AnalysisAgent
from pdca.agents.report_agent import ReportAgent
from pdca.agents.shared.normalizer import normalize_results
from pdca.agents.shared.rag_client import RAGClient

from pdca.tools import ALL_TOOLS  # Import danh sách tool gốc
from pdca.config import (
    RAG_API_URL,
    SCANNER_API_URL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_API_KEY,
)

# Tạo một Dictionary để tra cứu nhanh: { "tên_tool": tool_object }
TOOLS_MAP = {t.name: t for t in ALL_TOOLS}

load_dotenv()


# ==============================================================================
# 0. UTILS: PERFORMANCE TRACKING & METRICS SAVER
# ==============================================================================


@contextmanager
def measure_time():
    """Đo thời gian thực thi của một block code (tính bằng giây)."""
    start = time.perf_counter()
    yield lambda: time.perf_counter() - start


def update_metrics(current_metrics: Dict, category: str, key: str, value: Any):
    """Cập nhật metrics, value có thể là float hoặc dict detail"""
    if current_metrics is None:
        current_metrics = {"step_duration": {}, "llm_latency": {}, "system_info": {}}

    if category not in current_metrics:
        current_metrics[category] = {}

    if isinstance(value, float):
        current_metrics[category][key] = round(value, 4)
    else:
        current_metrics[category][key] = value

    return current_metrics


def save_performance_metrics(
    metrics: Dict[str, Any], path="data/artifacts/performance_metrics.json"
):
    """Lưu metrics ra file JSON để Report Agent hoặc hệ thống khác sử dụng."""
    try:
        # Tính tổng thời gian hệ thống nếu có start_time
        start_time = metrics.get("system_info", {}).get("start_time")
        if start_time:
            metrics["system_info"]["total_duration"] = round(
                time.time() - start_time, 2
            )

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
        print(f"\n [Metrics] Đã lưu file thống kê hiệu năng tại: {path}")
    except Exception as e:
        print(f" Không thể lưu file metrics: {e}")


def save_scan_configuration(
    plan_data: Dict[str, Any], path="data/artifacts/initial_scan_config.json"
):
    """
    Lưu plan từ PlanningAgent vào file JSON để RescanAgent dùng lại ở bước Verification.
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # Chuẩn hóa format dữ liệu mà RescanAgent mong đợi
        config_data = {
            "groups_to_scan": plan_data.get("groups_to_scan", []),
            "checks_to_scan": plan_data.get("checks_to_scan", []),
            "reasoning": plan_data.get("reasoning", ""),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        print(f"   [System]  Configuration saved to {path}")
    except Exception as e:
        print(f"    Failed to save scan config: {e}")


# ==============================================================================
# 1. NODES CỐT LÕI (Environment, Planning, Scanning, Monitoring)
# ==============================================================================


def environment_node(state: PDCAState):
    print("\n [Node: Environment] Fetch AWS context...")
    metrics = state.get(
        "performance_metrics",
        {"step_duration": {}, "llm_latency": {}, "system_info": {}},
    )

    with measure_time() as timer:
        agent = EnvironmentAgent()
        ctx = agent.get_aws_context()

    print(f"   AWS Context: Account {ctx.get('account_id')}, Region {ctx.get('region')}")

    # RAG Health Check (SLICE-0.3)
    rag_client = RAGClient(base_url=RAG_API_URL, timeout=3.0)
    rag_available = rag_client.is_healthy()
    if rag_available:
        print("   RAG Service: Available")
    else:
        print("   RAG Service: Unavailable — pipeline will run in degraded mode")

    metrics = update_metrics(metrics, "step_duration", "environment_setup", timer())
    return {"aws_context": ctx, "rag_available": rag_available, "performance_metrics": metrics}


def planning_node(state: PDCAState):
    """
    Node lập kế hoạch (V2): RAG-first, LLM-conditional.
    Nhận yêu cầu từ user → PlanningAgent → assessment plan cho scanning_node.
    """
    user_request = state["user_request"]
    print(f"\n [Node: Planning] Analyzing: {user_request}")
    metrics = state.get(
        "performance_metrics",
        {"step_duration": {}, "llm_latency": {}, "system_info": {}},
    )

    # Chỉ tạo RAGClient nếu RAG service available (từ environment_node)
    rag_client = None
    if state.get("rag_available", False):
        rag_client = RAGClient(base_url=RAG_API_URL)
    else:
        print("   RAG unavailable — planning in degraded mode")

    agent = PlanningAgent(
        model_name=OLLAMA_MODEL,
        api_key=OLLAMA_API_KEY,
        base_url=OLLAMA_BASE_URL,
        rag_client=rag_client,
    )

    with measure_time() as timer:
        plan_result = agent.run(user_request)

    # Handle V2 explicit errors (no silent S3 default)
    if plan_result.get("error"):
        print(f"   Planning WARNING: {plan_result['error']}")

    checks_count = len(plan_result.get("checks_to_scan", []))
    groups_count = len(plan_result.get("groups_to_scan", []))
    print(f"   Result: {checks_count} checks, {groups_count} groups")

    # Save config cho RescanAgent (verification phase)
    save_scan_configuration(plan_result)

    metrics = update_metrics(metrics, "step_duration", "planning_node", timer())

    return {
        "assessment_plan": plan_result,
        "performance_metrics": metrics,
    }

def scanning_node(state: PDCAState):
    plan = state.get("assessment_plan", {})
    target_groups = plan.get("groups_to_scan", [])
    checks_to_scan = plan.get("checks_to_scan", [])

    print(f"\n [Node: Scanning] Triggering scans: groups={target_groups}, checks={checks_to_scan}")
    metrics = state.get("performance_metrics", {})

    scanner = ScannerAgent(OLLAMA_MODEL, OLLAMA_API_KEY, OLLAMA_BASE_URL)

    with measure_time() as timer:
        job_ids = scanner.run_batch(
            target_groups=target_groups,
            specific_checks=checks_to_scan
        )

    # 2. GHI NHẬN THỜI GIAN CHẠY NODE
    metrics = update_metrics(metrics, "step_duration", "scanning_trigger", timer())
    
    # 3. MÔ PHỎNG LẠI LLM METRICS (Để giữ nguyên cấu trúc metrics, tránh lỗi ở các node sau)
    # Vì bước này chỉ chạy code thuần, LLM latency = 0
    mock_llm_metrics = {
        "total_latency": 0.0,
        "call_history": [],
        "call_count": 0
    }
    metrics = update_metrics(metrics, "llm_latency", "scanner_agent", mock_llm_metrics)

    return {"scan_job_ids": job_ids, "performance_metrics": metrics}
def monitoring_node(state: PDCAState):
    job_ids = state.get("scan_job_ids", [])
    print(f"\n [Node: Monitoring] Polling results for jobs: {job_ids}")
    metrics = state.get("performance_metrics", {})

    if not job_ids:
        return {"raw_findings": []}

    with measure_time() as timer:
        monitor = MonitoringAgent(poll_interval=5)
        flat_raw_findings = monitor.run(job_ids)
        normalized_data_package = normalize_results(flat_raw_findings)
        try:
            with open("data/artifacts/pre_scan.json", "w", encoding="utf-8") as f:
                json.dump(normalized_data_package, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f" Save error: {e}")

    clean_findings_list = normalized_data_package.get("findings", [])

    metrics = update_metrics(metrics, "step_duration", "monitoring_wait", timer())

    return {"raw_findings": clean_findings_list, "performance_metrics": metrics}


# ==============================================================================
# 2. RISK
# ==============================================================================


def risk_evaluation_node(state: PDCAState):
    print("\n [Node: Risk Eval] Analyzing risks...")
    metrics = state.get("performance_metrics", {})

    # Init shared RAGClient (SLICE-2.1)
    rag_client = RAGClient(base_url=RAG_API_URL)
    risk_agent = RiskEvaluationAgent(OLLAMA_MODEL, OLLAMA_API_KEY, OLLAMA_BASE_URL, rag_client=rag_client)

    # 1. Đo tổng thời gian Node
    with measure_time() as timer:
        prioritized = risk_agent.run(state["raw_findings"])

    # 2. Lấy chi tiết thời gian AI suy nghĩ
    llm_metrics = risk_agent.get_llm_metrics()

    # 3. Update Metrics
    metrics = update_metrics(metrics, "step_duration", "risk_evaluation_node", timer())
    metrics = update_metrics(
        metrics, "llm_latency", "risk_evaluation_agent", llm_metrics
    )

    return {"prioritized_findings": prioritized, "performance_metrics": metrics}


def route_after_risk(state: PDCAState) -> Literal["operational_planning", "report"]:
    fails = [f for f in state["prioritized_findings"] if f.get("status") == "FAIL"]
    if fails:
        print(f"\n {len(fails)} FAIL findings → go to remediation planning.")
        return "operational_planning"
    else:
        print("\n No FAIL → go to report.")
        return "report"
    

# ==============================================================================
# 3. REMEDIATION OPERATIONAL PLANNING
# ==============================================================================


def operational_planning_node(state: PDCAState):
    print("\n [Node: Op. Planning] Building remediation plan...")
    metrics = state.get("performance_metrics", {})

    aws_ctx = state.get("aws_context", {})
    planner = RemediationPlannerAgent(
        OLLAMA_MODEL, OLLAMA_API_KEY, OLLAMA_BASE_URL, aws_context=aws_ctx
    )

    # 1. Đo tổng thời gian Node
    with measure_time() as timer:
        findings = [
            f for f in state["prioritized_findings"] if f.get("status") == "FAIL"
        ]
        generated_plans = planner.plan_remediation(findings)

        tasks = []

        for i, plan in enumerate(generated_plans, 1):
            tasks.append(
                {
                    "task_id": f"task_{i}",
                    "finding_id": plan["finding_id"],
                    "tool_name": plan["tool_id"],
                    "tool_params": plan["params"],
                    "description": plan.get("description", ""),
                    "priority": 1,
                    "ai_reasoning": plan.get("reasoning", ""),
                    "manual_required": plan.get("manual_required", False),
                }
            )

    llm_metrics = planner.get_llm_metrics()

    metrics = update_metrics(
        metrics, "step_duration", "operational_planning_node", timer()
    )
    metrics = update_metrics(
        metrics, "llm_latency", "remediation_planner_agent", llm_metrics
    )

    if len(tasks) == 0:
        return {
            "remediation_tasks": [],
            "task_execution_plan": {},
            "current_task_index": 0,
            "performance_metrics": metrics,
        }

    return {
        "remediation_tasks": tasks,
        "task_execution_plan": {},
        "current_task_index": 0,
        "performance_metrics": metrics,
    }


# ==============================================================================
# 4. REVIEW TASK NODE (HITL PER-TASK)
# ==============================================================================


def review_task_node(state: PDCAState):

    return {"_hitl_pause": True}


def route_review_next_task(state: PDCAState) -> Literal["review_task", "execution"]:
    """
    Logic quyết định đi đâu tiếp theo:
    - Nếu index < tổng số task => Vẫn còn task chưa duyệt => Quay lại 'review_task'
    - Nếu index == tổng số task => Đã duyệt xong hết => Sang 'execution'
    """
    tasks = [t for t in state["remediation_tasks"] if not t.get("manual_required")]

    if not tasks:
        state["current_task_index"] = 0
        return "execution"

    idx = state.get("current_task_index", 0)

    if idx >= len(tasks):
        state["current_task_index"] = 0
        return "execution"

    return "review_task"


# ==============================================================================
# 5. EXECUTION NODE (Chỉ chạy tasks được approve)
# ==============================================================================


def execution_node(state: PDCAState):
    print("\n [Node: Execution] Running approved remediation tasks...")
    metrics = state.get("performance_metrics", {})

    with measure_time() as timer:
        all_tasks = state.get("remediation_tasks", [])
        decisions = state.get("task_execution_plan", {})
        prioritized_findings = state.get("prioritized_findings", [])

        # Map finding_id -> finding_uid (O(1))
        fid_to_uid_map = {
            f["finding_id"]: f["finding_uid"] for f in prioritized_findings
        }

        # Tách tasks
        manual_tasks = [t for t in all_tasks if t.get("manual_required", False)]
        auto_tasks = [t for t in all_tasks if not t.get("manual_required", False)]

        # Map task_id -> finding_id (cho auto logs)
        task_to_finding = {t["task_id"]: t["finding_id"] for t in all_tasks}

        pipeline_context = []
        execution_logs = []

        # --- 1) XỬ LÝ MANUAL ---
        for t in manual_tasks:
            finding_uid = fid_to_uid_map.get(t["finding_id"])

            # [FIX] Tạo log object chuẩn để đồng bộ
            manual_log = {
                "task_id": t["task_id"],
                "tool_name": t["tool_name"],
                "status": "manual_required",
                "output": {
                    "status": "manual_required",
                    "message": "Requires manual steps.",
                },
                "error": None,
            }
            execution_logs.append(manual_log)

            pipeline_context.append(
                {
                    "task_id": t["task_id"],
                    "finding_uid": finding_uid,
                    "tool_name": t["tool_name"],
                    "tool_params": t["tool_params"],
                    "planner_reasoning": t.get("ai_reasoning"),
                    "manual_required": True,
                    "execution_status": "manual_required",
                    "execution_output": manual_log["output"],
                    "execution_error": None,
                }
            )

        # --- 2) XỬ LÝ AUTO ---
        if auto_tasks:
            aws_ctx = state.get("aws_context", {})
            executor = ExecutionAgent(aws_context=aws_ctx)

            auto_tasks_filtered = [
                t for t in auto_tasks if decisions.get(t["task_id"]) == "approve"
            ]
            auto_logs = executor.execute_all(auto_tasks_filtered, decisions)
            execution_logs.extend(auto_logs)

            task_obj_map = {t["task_id"]: t for t in auto_tasks}

            for log in auto_logs:
                task_id = log["task_id"]
                finding_id = task_to_finding.get(task_id)
                finding_uid = fid_to_uid_map.get(finding_id)
                task_info = task_obj_map.get(task_id)

                pipeline_context.append(
                    {
                        "task_id": task_id,  # <--- [FIX QUAN TRỌNG] Thêm task_id
                        "finding_uid": finding_uid,
                        "tool_name": log["tool_name"],
                        "tool_params": task_info["tool_params"] if task_info else {},
                        "planner_reasoning": (
                            task_info.get("ai_reasoning") if task_info else None
                        ),
                        "manual_required": False,
                        "execution_status": (
                            "failed"
                            if log.get("status") == "error"
                            else log.get("status", "not_run")
                        ),
                        "execution_output": log.get("output", {}),
                        "execution_error": log.get("error", None),
                        "execution_timing": {
                            "started_at": log.get("started_at"),
                            "ended_at": log.get("ended_at"),
                            "duration": log.get("duration"),
                        },
                    }
                )

    metrics = update_metrics(metrics, "step_duration", "execution_node", timer())

    return {
        "execution_logs": execution_logs,
        "pipeline_context": pipeline_context,  # (Nhớ gán đúng biến pipeline_context đã tạo ở trên)
        "performance_metrics": metrics,
    }


# ==============================================================================
# 6. VERIFICATION + REPORT
# ==============================================================================


def verification_node(state: PDCAState):
    print("\n [Node: Verification] Running post-remediation scan...")
    metrics = state.get("performance_metrics", {})

    with measure_time() as timer:
        # 1) Chạy rescan để sinh post_scan.json
        rescan = RescanAgent()
        rescan.run()

        # 2) Đọc file 1 LẦN DUY NHẤT
        with open("data/artifacts/pre_scan.json", "r", encoding="utf-8") as fp:
            pre_scan = json.load(fp)
        with open("data/artifacts/post_scan.json", "r", encoding="utf-8") as fp:
            post_scan = json.load(fp)

        # 3) Gom dữ liệu execution vào pipeline_context đầy đủ
        pipeline_context = _aggregate_pipeline_data(state, state["pipeline_context"])

        # 4) AnalysisAgent nhận data trực tiếp — không đọc file lại
        analyzer = AnalysisAgent()
        analysis_results = analyzer.run(
            pre_scan=pre_scan,
            post_scan=post_scan,
            pipeline_context=pipeline_context,
        )

    metrics = update_metrics(metrics, "step_duration", "verification_node", timer())

    return {
        "verification_results": analysis_results.get("diff_result", []),
        "analysis_results": analysis_results,
        "performance_metrics": metrics,
    }


def build_report_data(analysis: dict, aws_context: dict,
                      plan: dict, user_request: str) -> dict:
    """
    Hàm THUẦN TÚY — không side effect, không truy cập file.
    NƠI DUY NHẤT biết "report cần gì, state có gì".
    Testable: truyền mock data vào, verify output.

    Maps:
    - analysis  → pre/post stats, findings, table
    - aws_context → environment info (account, region, buckets)
    - plan → scan scope (target services)
    - user_request → scope context
    """
    pre = analysis.get("pre_stats", {})
    post_stats = analysis.get("post_stats", {})
    rem = analysis.get("remediation_stats", {})

    return {
        # --- Số liệu (đã tính bởi AnalysisAgent, KHÔNG tính lại) ---
        "pre": {
            "total": pre.get("total", 0),
            "pass": pre.get("pass", 0),
            "fail": pre.get("fail", 0),
            "severity": pre.get("severity", {"critical": 0, "high": 0, "medium": 0, "low": 0}),
        },
        "post": {
            "initial_pass": pre.get("pass", 0),
            "initial_fail": pre.get("fail", 0),
            "final_pass": post_stats.get("pass", 0),
            "final_fail": post_stats.get("fail", 0),
            "fixed": rem.get("fixed", 0),
            "failed": rem.get("failed", 0),
            "manual": rem.get("manual", 0),
        },

        # --- Findings ---
        "findings_table": analysis.get("findings_table", []),
        "success_findings": analysis.get("success_findings", []),
        "failed_findings": analysis.get("failed_findings", []),
        "manual_findings": analysis.get("manual_findings", []),
        "raw_pre_findings": analysis.get("raw_pre_findings", []),
        "raw_post_findings": _extract_post_findings(analysis),

        # --- Environment (từ state, KHÔNG từ AnalysisAgent) ---
        "environment": {
            "account_id": aws_context.get("account_id", "Unknown"),
            "region": aws_context.get("region", "us-east-1"),
            "buckets": aws_context.get("buckets", []),
        },

        # --- Scope (từ state, KHÔNG từ AnalysisAgent) ---
        "scope": {
            "services": plan.get("target_services", ["s3"]),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "user_request": user_request,
        },
    }


def _extract_post_findings(analysis: dict) -> list:
    """
    Tạo danh sách findings dựa trên post-scan results.
    Mỗi finding có event_code và status (PASS/FAIL) từ KẾT QUẢ SAU remediation.
    Pure function — không side effect.
    """
    post_findings = []
    for row in analysis.get("findings_table", []):
        post_findings.append({
            "event_code": row.get("check_id", ""),
            "status": row.get("after", "UNKNOWN"),
            "severity": row.get("severity", ""),
            "resource_id": row.get("resource", ""),
            "service": row.get("service", ""),
            "change": row.get("change", ""),
        })
    return post_findings


def _fetch_rag_for_report(raw_pre_findings: list,
                          rag_available: bool = False) -> dict:
    """
    Gọi RAG API lấy security knowledge cho report.
    Graceful degradation: RAG down → return empty dict → report vẫn hoạt động.

    Returns:
        {
            "primary_topics":        [str],
            "key_findings":          [{check_id, title, severity, risk_summary,
                                       remediation}],
            "control_themes":        [{capability_id, capability_name,
                                       summary_short}],
            "recommended_practices": [str],
            "capability_details":    [{capability_id, capability_name, summary,
                                       risk_explanation, recommendation,
                                       guidance_questions, url}],
            "confidence":            "high" | "medium" | "low" | None,
        }
        hoặc {} nếu RAG không khả dụng.
    """
    if not rag_available:
        print("[report_node] RAG not available — report sẽ dùng LLM thuần")
        return {}

    try:
        from pdca.agents.shared.rag_client import RAGClient
        rag = RAGClient(base_url=RAG_API_URL, timeout=30.0, max_retries=3)

        # Extract unique check_ids từ findings
        check_ids = list({
            f.get("event_code") or f.get("finding_id", "")
            for f in raw_pre_findings
        } - {""})

        if not check_ids:
            return {}

        # App-level retry loop because urllib3 Retry does not always cover
        # ConnectionError on fresh sessions under Windows TCP conditions.
        result = None
        for attempt in range(1, 4):
            result = rag.build_context(
                consumer="report",
                check_ids=check_ids,
                include_mappings=True,
                include_maturity=True,
                top_k=10,
                retrieval_mode="hybrid",
            )
            if result is not None:
                break
            print(f"[report_node] RAG attempt {attempt}/3 returned None — retrying...")
            time.sleep(0.5 * attempt)

        if result is None:
            print(
                f"[report_node] RAG build_context returned None. "
                f"Requested {len(check_ids)} check_ids (first 5: {check_ids[:5]}). "
                f"See RAG server log / rag_client warnings for the error code."
            )
            try:
                debug_dump = {
                    "consumer": "report",
                    "check_ids_requested": check_ids,
                    "include_mappings": True,
                    "include_maturity": True,
                }
                os.makedirs("data/artifacts", exist_ok=True)
                with open("data/artifacts/rag_debug_last.json", "w", encoding="utf-8") as f:
                    json.dump(debug_dump, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            return {}

        # Extract report_bundle từ response
        bundle = result.get("payload", {}).get("report_bundle", {})
        confidence = (
            bundle.get("confidence")
            or result.get("_meta", {}).get("confidence")
        )

        context = {
            "primary_topics": bundle.get("primary_topics", []),
            "key_findings": bundle.get("key_findings", []),
            "control_themes": bundle.get("control_themes", []),
            "recommended_practices": bundle.get("recommended_practices", []),
            "capability_details": bundle.get("capability_details", []),
            "confidence": confidence,
        }

        finding_count = len(context["key_findings"])
        theme_count = len(context["control_themes"])
        detail_count = len(context["capability_details"])
        print(
            f"[report_node] RAG context: {finding_count} findings, "
            f"{theme_count} themes, {detail_count} capability_details, "
            f"confidence={confidence}"
        )

        return context

    except Exception as e:
        print(f"[report_node] RAG query failed: {e} — report sẽ dùng LLM thuần")
        return {}


def report_node(state: PDCAState):
    print("\n [Node: Report] Generating final report...")
    metrics = state.get("performance_metrics", {})

    # Lấy analysis_results từ state (single source of truth)
    analysis = state.get("analysis_results")

    # Trường hợp no FAIL → skip verification → không có analysis_results
    # Build analysis tối thiểu từ raw_findings đã có trong state (KHÔNG đọc file lại)
    if not analysis:
        pre_findings = state.get("raw_findings", [])
        sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in pre_findings:
            s = (f.get("severity") or "").lower()
            if s in sev:
                sev[s] += 1

        pass_count = sum(1 for f in pre_findings if f.get("status") == "PASS")
        fail_count = sum(1 for f in pre_findings if f.get("status") == "FAIL")

        analysis = {
            "pre_stats": {
                "total": len(pre_findings),
                "pass": pass_count,
                "fail": fail_count,
                "severity": sev,
            },
            "post_stats": {"pass": pass_count, "fail": fail_count},
            "remediation_stats": {"fixed": 0, "failed": 0, "manual": 0},
            "success_findings": [],
            "failed_findings": [],
            "manual_findings": [],
            "findings_table": [],
            "raw_pre_findings": pre_findings,
        }

    # Gom data 1 NƠI DUY NHẤT qua hàm thuần túy
    report_data = build_report_data(
        analysis=analysis,
        aws_context=state.get("aws_context") or {},
        plan=state.get("assessment_plan") or {},
        user_request=state.get("user_request", ""),
    )

    # --- Scope detection (Phase 1 — de-S3 bias) ---
    # Compute before RAG so the scope is available for any upstream consumer
    # that may want it later (e.g. the upcoming validator in Phase 5).
    from pdca.agents.report_module.scope_detector import detect_scope
    report_data["scope_info"] = detect_scope(
        findings=report_data.get("raw_pre_findings", []),
        env=report_data.get("environment"),
        services_hint=report_data.get("scope", {}).get("services"),
    )

    # --- RAG Context: enrich report với security knowledge ---
    rag_context = _fetch_rag_for_report(
        report_data.get("raw_pre_findings", []),
        rag_available=state.get("rag_available", False),
    )
    report_data["rag_context"] = rag_context

    # --- Maturity Assessment ---
    try:
        from pdca.agents.report_module.maturity_engine import MaturityEngine
        engine = MaturityEngine(
            mappings_path="RAG/data/normalized/maturity_mappings.json",
            capabilities_path="RAG/data/normalized/maturity_capabilities.json",
        )

        # Scanned services from scope
        scanned_services = report_data.get("scope", {}).get("services", [])

        # Pre-remediation maturity
        maturity_pre = engine.assess(
            report_data.get("raw_pre_findings", []),
            scanned_services=scanned_services,
        )
        report_data["maturity_assessment"] = maturity_pre

        # Post-remediation maturity (if post data available)
        raw_post = report_data.get("raw_post_findings")
        if raw_post:
            maturity_post = engine.assess(raw_post, scanned_services=scanned_services)
            report_data["maturity_post"] = maturity_post
            report_data["maturity_delta"] = engine.compute_delta(maturity_pre, maturity_post)
        else:
            report_data["maturity_post"] = None
            report_data["maturity_delta"] = None

        print(f"[report_node] Maturity PRE: score={maturity_pre['overall_score']:.1f}, "
              f"stage={maturity_pre['overall_stage_label']}")
        if report_data["maturity_delta"]:
            d = report_data["maturity_delta"]["overall"]
            print(f"[report_node] Maturity POST: score={d['post_score']:.1f}, "
                  f"delta={d['score_delta']:+.1f}")
    except Exception as e:
        print(f"[report_node] Maturity assessment failed: {e}")
        report_data["maturity_assessment"] = None
        report_data["maturity_post"] = None
        report_data["maturity_delta"] = None

    agent = ReportAgent(
        OLLAMA_MODEL,
        OLLAMA_API_KEY,
        OLLAMA_BASE_URL,
        output_path="data/artifacts/final_report.md",
    )

    with measure_time() as timer:
        path = agent.run(report_context=report_data)

    llm_metrics = agent.get_llm_metrics()

    metrics = update_metrics(metrics, "step_duration", "report_node", timer())
    metrics = update_metrics(metrics, "llm_latency", "report_agent", llm_metrics)

    save_performance_metrics(metrics)

    return {"final_report": path}


# ==============================================================================
# 7. GRAPH BUILDING
# ==============================================================================


def build_graph():
    wf = StateGraph(PDCAState)

    wf.add_node("environment", environment_node)
    wf.add_node("planning", planning_node)
    wf.add_node("scanning", scanning_node)
    wf.add_node("monitoring", monitoring_node)
    wf.add_node("risk_evaluation", risk_evaluation_node)

    wf.add_node("operational_planning", operational_planning_node)
    wf.add_node("review_task", review_task_node)
    wf.add_node("execution", execution_node)

    wf.add_node("verification", verification_node)
    wf.add_node("report", report_node)

    # Edges
    wf.add_edge(START, "environment")
    wf.add_edge("environment", "planning")
    wf.add_edge("planning", "scanning")
    wf.add_edge("scanning", "monitoring")
    wf.add_edge("monitoring", "risk_evaluation")

    wf.add_conditional_edges(
        "risk_evaluation",
        route_after_risk,
        {"operational_planning": "operational_planning", "report": "report"},
    )

    # Operational planning → review_task
    wf.add_edge("operational_planning", "review_task")

    # Review task → (loop or execution)
    wf.add_conditional_edges(
        "review_task",
        route_review_next_task,
        {
            "review_task": "review_task",
            "execution": "execution",
        },
    )

    wf.add_edge("execution", "verification")
    wf.add_edge("verification", "report")
    wf.add_edge("report", END)

    checkpointer = MemorySaver()
    return wf.compile(checkpointer=checkpointer, interrupt_before=["review_task"])


# ==============================================================================
# 8. RUNTIME (HUMAN-IN-THE-LOOP HANDLER)
# ==============================================================================


# ==============================================================================
# HÀM XỬ LÝ TƯƠNG TÁC NGƯỜI DÙNG (Client Side Logic)
# ==============================================================================
def handle_task_review_interaction(app, config):
    """
    Hàm này được gọi KHI graph đang dừng.
    [CẬP NHẬT] Bây giờ hàm này sẽ phụ trách in thông tin chi tiết của task
    trước khi hỏi người dùng.
    """
    # 1. Lấy State
    snapshot = app.get_state(config)
    state = snapshot.values

    idx = state["current_task_index"]
    tasks = [
        t for t in state["remediation_tasks"] if not t.get("manual_required", False)
    ]
    prioritized_findings = state.get("prioritized_findings", [])

    # Kiểm tra an toàn
    if idx >= len(tasks):
        return

    task = tasks[idx]
    tool_name = task["tool_name"]

    # 2. HIỂN THỊ THÔNG TIN CHI TIẾT (Logic được chuyển từ Node ra đây)
    tool_obj = TOOLS_MAP.get(tool_name)
    description = tool_obj.description if tool_obj else "⚠️ Không tìm thấy mô tả tool."

    finding_id = task["finding_id"]
    finding = next(
        (f for f in prioritized_findings if f["finding_id"] == finding_id),
        None,
    )

    print("\n" + "=" * 60)
    print(f"  REVIEWING TASK [{idx + 1}/{len(tasks)}]")
    print(f" Task ID    : {task['task_id']}")

    if finding:
        print(f" Finding ID : {finding['finding_id']}")
        print(f" Service    : {finding.get('service', 'N/A')}")
        print(f" Resource   : {finding.get('resource_id', 'N/A')}")
        print(f" Region     : {finding.get('region', 'N/A')}")
        print(f" Severity   : {finding.get('severity', 'N/A')}")
        # --- CHÈN 2 DÒNG NÀY VÀO ĐÂY ---
        compliance = finding.get('compliance', [])
        print(f" Compliance : {', '.join(compliance) if compliance else 'N/A'}")
        print(f" Service    : {finding.get('service', 'N/A')}")
        print(f" Risk Score : {finding.get('risk_score', 'N/A')}")
        print(
            f" Description: {finding.get('description', '')[:200]}..."
        )  # Cắt ngắn nếu quá dài
        print("-" * 5 + " Tool Remediation Info " + "-" * 5)

    print(f"  Tool Name  : {tool_name}")
    print(f"  Description: {description}")
    print(f"  Params     : {task['tool_params']}")
    print(f"  AI Reasoning: {task.get('ai_reasoning', 'N/A')}")
    print("=" * 60)

    # 3. Hỏi User
    print(f"\n Bạn có muốn chạy tool '{task['tool_name']}' không?")
    choice = input("   [Y]es (Chạy) / [N]o (Bỏ qua): ").strip().lower()

    decision = "skip"
    if choice in ["y", "yes"]:
        decision = "approve"

    print(f"   -> Đã lưu: {decision.upper()}")

    # 4. CẬP NHẬT STATE
    current_plan = state.get("task_execution_plan", {})
    current_plan[task["task_id"]] = decision

    app.update_state(
        config,
        {
            "task_execution_plan": current_plan,
            "current_task_index": idx + 1,
        },
    )


# ========= HELPER FUNCTIONS ========
def _aggregate_pipeline_data(state: PDCAState, pipeline_context: List[Dict]):
    """
    Hàm này đóng vai trò 'Data Lake':
    Nó join 3 bảng dữ liệu trong State lại với nhau:
    1. prioritized_findings (Risk Score, Reasoning)
    2. remediation_tasks (Tool Name, Params, Task ID)
    3. execution_logs (Output thực tế, Status)
    """

    remediation_tasks = state.get("remediation_tasks", [])
    execution_logs = state.get("execution_logs", [])
    prioritized = state.get("prioritized_findings", [])

    # Map Lookup
    fid_to_uid = {f["finding_id"]: f["finding_uid"] for f in prioritized}
    tid_to_log = {l["task_id"]: l for l in execution_logs}

    # [FIX QUAN TRỌNG] Map theo task_id thay vì finding_uid
    # Để tránh mất dữ liệu nếu 1 finding có nhiều task
    tid_to_ctx = {c["task_id"]: c for c in pipeline_context if c.get("task_id")}

    final_results_list = []

    for task in remediation_tasks:
        t_id = task["task_id"]
        f_id = task["finding_id"]
        f_uid = fid_to_uid.get(f_id)

        if not f_uid:
            continue

        # Ưu tiên lấy từ pipeline_context qua task_id
        ctx = tid_to_ctx.get(t_id)
        exec_log = tid_to_log.get(t_id)

        if ctx:
            final_status = ctx["execution_status"]
            final_output = ctx["execution_output"]
            final_error = ctx.get("execution_error")
            manual = ctx["manual_required"]
        else:
            # Fallback (Phòng hờ)
            final_status = exec_log.get("status", "not_run") if exec_log else "not_run"
            final_output = exec_log.get("output", {}) if exec_log else {}
            final_error = exec_log.get("error") if exec_log else None
            manual = task.get("manual_required", False)

        entry = {
            "finding_uid": f_uid,
            "task_id": t_id,
            "tool_name": task["tool_name"],
            "tool_params": task["tool_params"],
            "planner_reasoning": task.get("ai_reasoning"),
            "manual_required": manual,
            "execution_status": final_status,
            "execution_output": final_output,
            "execution_error": final_error,
            "execution_timing": ctx.get("execution_timing") if ctx else None,
        }

        final_results_list.append(entry)

    return final_results_list


# ==============================================================================
# MAIN LOOP
# ==============================================================================
def run_interactive_session():
    app = build_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("\n" + "=" * 50)
    print(" CHÀO MỪNG ĐẾN VỚI HỆ THỐNG PDCA SECURITY AGENT")
    print("=" * 50)

    # [FIX] Cho phép User nhập yêu cầu ban đầu
    user_request_text = input(
        " Nhập yêu cầu của bạn (VD: Scan S3, Check IAM users...): "
    ).strip()

    if not user_request_text:
        user_request_text = (
            "Scan my AWS environment"  # Giá trị mặc định nếu user lười nhập
        )
        print(f"   (Dùng mặc định: '{user_request_text}')")

    # Init state với input thực tế
    initial_input = {
        "user_request": user_request_text,
        "cycle_iteration": 0,
        "meta": {"user_input": user_request_text},
        "performance_metrics": {
            "step_duration": {},
            "llm_latency": {},
            "system_info": {"start_time": time.time()},
        },
    }
    current_input = initial_input

    while True:
        try:
            # Chạy graph cho đến khi gặp interrupt hoặc kết thúc
            for event in app.stream(current_input, config=config):
                pass

            # Kiểm tra trạng thái sau khi graph dừng
            snapshot = app.get_state(config)

            # Nếu graph đã chạy xong hết (không còn next node) -> BREAK
            if not snapshot.next:
                print("\n QUY TRÌNH HOÀN TẤT!")
                break

            # Nếu next node là "review_task", nghĩa là graph đang chờ user duyệt
            if snapshot.next[0] == "review_task":
                # Gọi hàm xử lý input duyệt task (Hàm này đã có input() bên trong)
                handle_task_review_interaction(app, config)
                current_input = None
            else:
                current_input = None

        except Exception as e:
            import traceback

            print(f" Error in main loop: {e}")
            traceback.print_exc()  # In chi tiết lỗi để dễ debug
            break


if __name__ == "__main__":
    run_interactive_session()
