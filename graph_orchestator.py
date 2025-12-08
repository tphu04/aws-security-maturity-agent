import os
import json
import uuid
import time
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

    target_services = raw_plan.get("target_services", [])

    if not target_services:
        print(
            "\n❌ [STOP] LỖI PLANNING: Không tìm thấy service AWS nào trong yêu cầu của bạn."
        )
        print(
            "   -> Gợi ý: Hãy nhập rõ ràng hơn (VD: 'Scan S3', 'Kiểm tra IAM', 'Full scan')."
        )

        # Raise Exception để Main Loop bắt được và dừng chương trình ngay lập tức
        raise ValueError("Planning Failed: No target services identified.")

    return {
        "assessment_plan": {
            "target_services": target_services,
            "reasoning": raw_plan.get("reasoning", "User request based"),
        }
    }


def scanning_node(state: PDCAState):
    """Bước 1: Kích hoạt Scan song song"""
    target_services = state["assessment_plan"].get("target_services", [])

    print(f"\n🟢 [Node: Scanning] Triggering parallel scans for: {target_services}")

    if not target_services:
        return {"scan_job_ids": []}

    # Khởi tạo ScannerAgent
    scanner = ScannerAgent(max_workers=5)

    # Gọi hàm run_batch để lấy list job IDs
    job_ids = scanner.run_batch(groups=target_services)

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
    planner = RemediationPlannerAgent(OLLAMA_MODEL, OLLAMA_API_KEY, OLLAMA_BASE_URL, aws_context=aws_ctx)

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

    return {}


def route_review_next_task(state: PDCAState) -> Literal["review_task", "execution"]:
    """
    Logic quyết định đi đâu tiếp theo:
    - Nếu index < tổng số task => Vẫn còn task chưa duyệt => Quay lại 'review_task'
    - Nếu index == tổng số task => Đã duyệt xong hết => Sang 'execution'
    """
    idx = state["current_task_index"]
    total = len(state["remediation_tasks"])

    if total == 0:
        return "execution"

    if idx < total:
        return "review_task"  # Tạo vòng lặp
    else:
        return "execution"  # Thoát vòng lặp, chạy Execution Agent


# ==============================================================================
# 5. EXECUTION NODE (Chỉ chạy tasks được approve)
# ==============================================================================


def execution_node(state: PDCAState):
    print("\n🚀 [Node: Execution] Running approved tasks...")

    tasks = state["remediation_tasks"]
    decisions = state["task_execution_plan"]

    # 1. Lấy Context từ State (đã được EnvironmentNode lấy từ đầu)
    # Đây chính là cách tận dụng EnvironmentAgent ban đầu
    aws_ctx = state.get("aws_context", {})

    # 2. Truyền context vào ExecutionAgent
    executor = ExecutionAgent(aws_context=aws_ctx)

    # 3. Chạy toàn bộ tasks
    exec_logs = executor.execute_all(tasks, decisions)

    return {"execution_logs": exec_logs}


# ==============================================================================
# 6. VERIFICATION + REPORT
# ==============================================================================


def verification_node(state: PDCAState):
    print("\n🟢 [Node: Verification] Running post-remediation scan...")

    rescan = RescanAgent()
    rescan.run()

    pipeline_context = _aggregate_pipeline_data(state)

    analyzer = AnalysisAgent("data/pre_scan.json", "data/post_scan.json")
    diff = analyzer.run(pipeline_context=pipeline_context)

    return {"verification_results": diff}


def report_node(state: PDCAState):
    print("\n🟢 [Node: Report] Generating final report...")

    diff = state.get("verification_results", {})  # List[Dict]

    pre_scan = json.load(open("data/pre_scan.json", "r", encoding="utf-8"))

    agent = ReportAgent(
        OLLAMA_MODEL,
        OLLAMA_API_KEY,
        OLLAMA_BASE_URL,
        output_path="data/final_report.md",
    )

    meta = {
        # Đảm bảo aws_context không None, nếu lỗi thì fallback về {}
        "account_id": state.get("aws_context", {}).get("account_id", "Unknown"),
        "scan_group": state.get("assessment_plan", {}).get("target_services", []),
    }

    # Gọi hàm run (thay vì generate)
    path = agent.run(pre_scan, diff, meta)

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
    tasks = state["remediation_tasks"]
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
    choice = (
        input("   [Y]es (Chạy) / [D]ry-run (Chạy thử) / [N]o (Bỏ qua): ")
        .strip()
        .lower()
    )

    decision = "skip"
    if choice in ["y", "yes"]:
        decision = "approve"
    elif choice in ["d", "dry"]:
        decision = "dry"

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
def _aggregate_pipeline_data(state: PDCAState) -> List[Dict]:
    """
    Hàm này đóng vai trò 'Data Lake':
    Nó join 3 bảng dữ liệu trong State lại với nhau:
    1. prioritized_findings (Risk Score, Reasoning)
    2. remediation_tasks (Tool Name, Params, Task ID)
    3. execution_logs (Output thực tế, Status)
    """
    
    # 1. Tạo Map cho Execution Logs: Task ID -> Log Output
    # Để biết Task nào sinh ra Log nào
    logs_map = {
        log["task_id"]: log 
        for log in state.get("execution_logs", [])
    }

    # 2. Tạo Map cho Remediation Tasks: Finding ID -> Task Info + Log Info
    # Để biết Finding nào được xử lý bởi Task nào
    tasks_map = {}
    for task in state.get("remediation_tasks", []):
        t_id = task["task_id"]
        f_id = task["finding_id"]
        
        # Lấy log tương ứng với task này (nếu có)
        exec_log = logs_map.get(t_id, {})
        
        tasks_map[f_id] = {
            "tool_name": task["tool_name"],
            "tool_params": task["tool_params"],
            "planner_reasoning": task["ai_reasoning"], # Lý do chọn tool
            "execution_status": exec_log.get("status", "not_run"),
            "execution_output": exec_log.get("output", {}), # Output quan trọng để report đọc
            "execution_error": exec_log.get("error", None)
        }

    # 3. Enrich Findings ban đầu
    # Duyệt qua danh sách finding đã được Risk Agent chấm điểm
    enriched_context = []
    for finding in state.get("prioritized_findings", []):
        f_id = finding.get("finding_id")
        
        # Lấy thông tin task tương ứng (nếu finding này được fix)
        task_info = tasks_map.get(f_id, {})
        
        # Tạo object chứa ĐỦ MỌI THỨ
        context_item = {
            "finding_uid": finding.get("finding_uid"), # Key để AnalysisAgent map diff
            "finding_id": f_id,
            # Dữ liệu từ Risk Agent
            "risk_score": finding.get("risk_score", 0),
            "severity": finding.get("severity", "Medium"),
            "reasoning": finding.get("reasoning", ""), 
            # Dữ liệu từ Planner & Execution (Merge vào)
            **task_info 
        }
        enriched_context.append(context_item)
        
    return enriched_context


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
    initial_input = {"user_request": user_request_text, "cycle_iteration": 0}
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
