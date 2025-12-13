import os
import json
import uuid
from datetime import datetime
from typing import Literal, Dict, Any
from typing import List
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv

from AgentState import PDCAState

# Import các agent cũ (không thay đổi)
from agents.environment_agent import EnvironmentAgent
from agents.planning_agent import PlanningAgent
from agents.scanner_agent import ScannerAgent
from agents.monitoring_agent import MonitoringAgent
from agents.risk_evaluation_agent import RiskEvaluationAgent
from agents.remediate_planner_agent import RemediationPlannerAgent
from agents.execution_agent import ExecutionAgent
from agents.rescan_agent import RescanAgent
from agents.analysis_agent import AnalysisAgent
from agents.report_agent import ReportAgent
from agents.shared.normalizer import normalize_results

from agent_tools import ALL_TOOLS  # Import danh sách tool gốc

# Tạo một Dictionary để tra cứu nhanh: { "tên_tool": tool_object }
TOOLS_MAP = {t.name: t for t in ALL_TOOLS}

load_dotenv()
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_API_KEY = "ollama"

# ==============================================================================
# 1. NODES CỐT LÕI (Environment, Planning, Scanning, Monitoring)
# ==============================================================================


def environment_node(state: PDCAState):
    print("\n🟢 [Node: Environment] Fetch AWS context...")
    agent = EnvironmentAgent()
    ctx = agent.get_aws_context()
    return {"aws_context": ctx}


def planning_node(state: PDCAState):
    print("\n🟢 [Node: Planning] Generate Assessment Plan...")
    agent = PlanningAgent(OLLAMA_MODEL, OLLAMA_API_KEY, OLLAMA_BASE_URL)
    raw_plan = agent.run(state["user_request"])

    target_services = raw_plan.get("groups_to_scan", [])
    checks_to_scan = raw_plan.get("checks_to_scan", [])

    if not target_services and not checks_to_scan:
        print(
            "\n❌ [STOP] LỖI PLANNING: Không tìm thấy service AWS nào trong yêu cầu của bạn."
        )
        raise ValueError("Planning Failed: No target services identified.")

    return {
        "assessment_plan": {
            "target_services": target_services,
            "checks_to_scan": checks_to_scan,
            "reasoning": raw_plan.get("reasoning", ""),
        }
    }


def scanning_node(state: PDCAState):
    """Bước 1: Kích hoạt Scan"""
    target_services = state["assessment_plan"].get("target_services", [])
    checks_to_scan = state["assessment_plan"].get("checks_to_scan", [])

    print(f"\n🟢 [Node: Scanning] Triggering scans")
    print(f"   - Services: {target_services}")
    print(f"   - Checks  : {checks_to_scan}")

    if not target_services and not checks_to_scan:
        return {"scan_job_ids": []}

    scanner = ScannerAgent(
        OLLAMA_MODEL,
        OLLAMA_API_KEY,
        OLLAMA_BASE_URL,
    )

    job_ids = scanner.run_batch(
        target_groups=target_services,
        specific_checks=checks_to_scan,
    )

    return {"scan_job_ids": job_ids}


def monitoring_node(state: PDCAState):
    """Bước 2: Vòng lặp theo dõi kết quả"""
    job_ids = state.get("scan_job_ids", [])
    print(f"\n🟢 [Node: Monitoring] Polling results for jobs: {job_ids}")

    if not job_ids:
        return {"raw_findings": []}

    # 1. Thu thập dữ liệu thô (List phẳng)
    monitor = MonitoringAgent(poll_interval=5)  # Giảm interval để test nhanh hơn
    flat_raw_findings = monitor.run(job_ids)

    # 2. Chuẩn hóa dữ liệu (Trả về Dict {metadata, findings})
    normalized_data_package = normalize_results(flat_raw_findings)

    # 3. Side Effect: Lưu file JSON đầy đủ (có metadata) để AnalysisAgent dùng sau này
    # AnalysisAgent thường đọc file này để so sánh
    try:
        with open("data/pre_scan.json", "w", encoding="utf-8") as f:
            json.dump(normalized_data_package, f, indent=2, ensure_ascii=False)
        print("   -> 💾 Saved data/pre_scan.json")
    except Exception as e:
        print(f"   -> ⚠️ Lỗi lưu file: {e}")

    # 4. [QUAN TRỌNG] Cập nhật State
    # State chỉ cần List Findings để truyền cho RiskEvaluationAgent
    # Trích xuất key "findings" từ package đã chuẩn hóa
    clean_findings_list = normalized_data_package.get("findings", [])

    return {"raw_findings": clean_findings_list}


# ==============================================================================
# 2. RISK
# ==============================================================================


def risk_evaluation_node(state: PDCAState):
    print("\n🟢 [Node: Risk Eval] Analyzing risks...")

    risk_agent = RiskEvaluationAgent(OLLAMA_MODEL, OLLAMA_API_KEY, OLLAMA_BASE_URL)
    prioritized = risk_agent.run(state["raw_findings"])

    return {"prioritized_findings": prioritized}


def route_after_risk(state: PDCAState) -> Literal["operational_planning", "report"]:
    fails = [f for f in state["prioritized_findings"] if f.get("status") == "FAIL"]
    if fails:
        print(f"\n⚠️ {len(fails)} FAIL findings → go to remediation planning.")
        return "operational_planning"
    else:
        print("\n✅ No FAIL → go to report.")
        return "report"


# ==============================================================================
# 3. REMEDIATION OPERATIONAL PLANNING
# ==============================================================================


def operational_planning_node(state: PDCAState):
    print("\n🟢 [Node: Op. Planning] Building remediation plan...")

    findings = [f for f in state["prioritized_findings"] if f.get("status") == "FAIL"]

    # 1. Lấy aws_context từ State (đã được EnvironmentNode nạp vào từ đầu)
    aws_ctx = state.get("aws_context", {})

    # Khởi tạo Planner
    planner = RemediationPlannerAgent(
        OLLAMA_MODEL, OLLAMA_API_KEY, OLLAMA_BASE_URL, aws_context=aws_ctx
    )

    # Lấy kế hoạch (chỉ là text/json, chưa chạy)
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

    if len(tasks) == 0:
        print("⚠ Không có remediation task nào → bỏ qua giai đoạn remediation.")
        return {
            "remediation_tasks": [],
            "task_execution_plan": {},
            "current_task_index": 0,
        }

    return {
        "remediation_tasks": tasks,
        "task_execution_plan": {},
        "current_task_index": 0,
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
    print("\n🟢 [Node: Execution] Running approved remediation tasks...")

    all_tasks = state.get("remediation_tasks", [])
    decisions = state.get("task_execution_plan", {})
    prioritized_findings = state.get("prioritized_findings", [])

    # Map finding_id -> finding_uid (O(1))
    fid_to_uid_map = {f["finding_id"]: f["finding_uid"] for f in prioritized_findings}

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

    return {
        "execution_logs": execution_logs,
        "pipeline_context": pipeline_context,
    }


# ==============================================================================
# 6. VERIFICATION + REPORT
# ==============================================================================


def verification_node(state: PDCAState):
    print("\n🟢 [Node: Verification] Running post-remediation scan...")

    # 1) Chạy rescan để sinh post_scan.json
    rescan = RescanAgent()
    rescan.run()

    # 2) Gom dữ liệu execution vào pipeline_context đầy đủ
    pipeline_context = _aggregate_pipeline_data(state, state["pipeline_context"])

    # 3) Tạo AnalysisAgent để tạo diff (before/after)
    analyzer = AnalysisAgent("data/pre_scan.json", "data/post_scan.json")
    diff = analyzer.run(pipeline_context=pipeline_context)

    # 4) BỔ SUNG: build report_context từ pre/post/diff
    report_context = analyzer.build_report_context(
        pre_scan=json.load(open("data/pre_scan.json", "r", encoding="utf-8")),
        post_scan=json.load(open("data/post_scan.json", "r", encoding="utf-8")),
        diff_data=diff,
        meta={
            "account_id": state.get("aws_context", {}).get("account_id", "Unknown"),
            "scan_group": state.get("assessment_plan", {}).get(
                "target_services", ["s3"]
            ),
        },
    )

    # 5) Đưa vào state -> để report_node dùng
    return {"verification_results": diff, "report_context": report_context}


def report_node(state: PDCAState):
    print("\n🟢 [Node: Report] Generating final report...")

    # Report context đã build từ AnalysisAgent
    report_context = state.get("report_context")
    if not report_context:
        raise ValueError("❌ Missing report_context in PDCA state")

    meta = {
        "account_id": state.get("aws_context", {}).get("account_id", "Unknown"),
        "scan_scope": state.get("assessment_plan", {}).get("target_services", ["s3"]),
        "date": datetime.now().strftime("%Y-%m-%d"),
    }

    agent = ReportAgent(
        OLLAMA_MODEL,
        OLLAMA_API_KEY,
        OLLAMA_BASE_URL,
        output_path="data/final_report.md",
    )

    path = agent.run(report_context=report_context, meta=meta)

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
    print(f"🕵️  REVIEWING TASK [{idx + 1}/{len(tasks)}]")
    print(f"🆔 Task ID    : {task['task_id']}")

    if finding:
        print(f"🔎 Finding ID : {finding['finding_id']}")
        print(f"🔧 Service    : {finding.get('service', 'N/A')}")
        print(f"📍 Resource   : {finding.get('resource_id', 'N/A')}")
        print(f"🌎 Region     : {finding.get('region', 'N/A')}")
        print(f"⚠️ Severity   : {finding.get('severity', 'N/A')}")
        print(f"📊 Risk Score : {finding.get('risk_score', 'N/A')}")
        print(
            f"📝 Description: {finding.get('description', '')[:200]}..."
        )  # Cắt ngắn nếu quá dài
        print("-" * 5 + " Tool Remediation Info " + "-" * 5)

    print(f"🛠  Tool Name  : {tool_name}")
    print(f"📖 Description: {description}")
    print(f"⚙️  Params     : {task['tool_params']}")
    print(f"🧠 AI Reasoning: {task.get('ai_reasoning', 'N/A')}")
    print("=" * 60)

    # 3. Hỏi User
    print(f"\n👉 Bạn có muốn chạy tool '{task['tool_name']}' không?")
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
    print("🚀 CHÀO MỪNG ĐẾN VỚI HỆ THỐNG PDCA SECURITY AGENT")
    print("=" * 50)

    # [FIX] Cho phép User nhập yêu cầu ban đầu
    user_request_text = input(
        "👉 Nhập yêu cầu của bạn (VD: Scan S3, Check IAM users...): "
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
                print("\n✅ QUY TRÌNH HOÀN TẤT!")
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

            print(f"❌ Error in main loop: {e}")
            traceback.print_exc()  # In chi tiết lỗi để dễ debug
            break


if __name__ == "__main__":
    run_interactive_session()
