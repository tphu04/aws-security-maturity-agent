import os
import json
import threading
from dotenv import load_dotenv
from agents.planning_agent import PlanningAgent
from agents.task_assignment_agent import TaskAssignmentAgent
from agents.scanner_agent import ScannerAgent
from agents.monitoring_agent import MonitoringAgent

# from agents.remediate_agent import RemediateAgent
from agents.remediate_dev import RemediateAgent
from agents.assessment_agent import AssessmentAgent
from agents.risk_evaluation_agent import RiskEvaluationAgent
from agents.shared.normalizer import normalize_results
from agents.rescan_agent import RescanAgent
from agents.analysis_agent import AnalysisAgent
from agents.report_agent import ReportAgent


# --- Cấu hình OLLAMA (Giữ nguyên) ---
load_dotenv()
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_API_KEY = "ollama"
print(f"Đang sử dụng model Ollama: {OLLAMA_MODEL} tại {OLLAMA_BASE_URL}")
print("Hãy chắc chắn Ollama server và API server (uvicorn) đều đang chạy...")


# --- HÀM HELPER: Ánh xạ Service AWS sang Domain SMM --- (MỚI)
def map_aws_service_to_smm_domain(service_groups: list) -> list:
    """
    Ánh xạ các group service được quét (ví dụ: ['s3', 'iam'])
    sang các Domain SMM cần đánh giá.
    """
    mapping = {
        "iam": "Identity and Access Management",
        "s3": "Data Protection",
        "ec2": "Infrastructure Protection",
        "cloudtrail": "Security Assurance",
        "guardduty": "Threat Detection",
        # Bạn có thể thêm các mapping khác tại đây
    }

    domains = set()
    for group in service_groups:
        domain = mapping.get(group.lower())
        if domain:
            domains.add(domain)

    # Nếu không quét service cụ thể, mặc định kiểm tra IAM
    if not domains:
        domains.add("Identity and Access Management")

    return list(domains)


def main():
    print("=" * 50)
    print("Chào mừng đến với AWS Security Agent (v4 - Maturity Assessment)")
    print("=" * 50)
    user_prompt = input("Tôi có thể giúp gì cho bạn? (ví dụ: quét s3 và iam) \n> ")

    if not user_prompt:
        print("Không có yêu cầu. Tạm biệt.")
        return

    # --- BƯỚC 1: PlanningAgent (Lập kế hoạch) ---
    planning_agent = PlanningAgent(
        model_name=OLLAMA_MODEL, api_key=OLLAMA_API_KEY, base_url=OLLAMA_BASE_URL
    )
    plan = planning_agent.run(user_prompt)

    if not plan.get("groups_to_scan") and not plan.get("files_to_scan"):
        print("\n[MainAgent] ❌ Agent lập kế hoạch không tạo được plan. Kết thúc.")
        return
    print(f"\n[MainAgent] 📋 Kế hoạch: {plan}")

    # --- SAVE INITIAL SCAN CONFIG (for rescan later) ---
    os.makedirs("data", exist_ok=True)
    with open("data/initial_scan_config.json", "w") as f:
        json.dump(plan, f, indent=2)
    print(
        "[MainAgent] 💾 Đã lưu cấu hình quét ban đầu vào data/initial_scan_config.json"
    )

    # --- BƯỚC 2: TaskAssignmentAgent (Giao việc) ---
    scanner_agent = ScannerAgent(
        model_name=OLLAMA_MODEL, api_key=OLLAMA_API_KEY, base_url=OLLAMA_BASE_URL
    )
    task_assignment_agent = TaskAssignmentAgent(scanner_agent)
    job_ids = task_assignment_agent.run(plan)

    if not job_ids:
        print("\n[MainAgent] ❌ Không có job nào được tạo. Kết thúc.")
        return
    print(f"\n[MainAgent] ✅ Đã tạo thành công {len(job_ids)} job(s): {job_ids}")

    # --- BƯỚC 3: MonitoringAgent (Thu thập kết quả) ---
    monitoring_agent = MonitoringAgent()
    structured_report_data = monitoring_agent.run(job_ids)

    print("[MainAgent] 🧹 Chuẩn hoá BEFORE scan...")
    before_scan = normalize_results(structured_report_data)

    with open("data/pre_scan.json", "w") as f:
        json.dump(before_scan, f, indent=2)

    print("[MainAgent] 💾 Đã tạo file BEFORE scan: data/pre_scan.json")

    # 4. ---- BƯỚC 4: Phân tích rủi ro (RiskEvaluationAgent) ----
    print("\n[MainAgent] 🤖 Đang gọi RiskEvaluationAgent để phân tích rủi ro...")
    risk_agent = RiskEvaluationAgent(
        model_name=OLLAMA_MODEL, api_key=OLLAMA_API_KEY, base_url=OLLAMA_BASE_URL
    )
    # Danh sách findings đã có "severity" và "risk_score"
    enriched_findings = risk_agent.run(structured_report_data)

    # 5. ---- BƯỚC 5: (LOGIC MỚI) ĐÁNH GIÁ SMM (AssessmentAgent) ----
    # AssessmentAgent sẽ nhận 'enriched_findings' và thêm 'smm_assessment' vào

    print("\n" + "=" * 15 + " ĐÁNH GIÁ SMM (TỪNG FINDING) " + "=" * 15)
    assessment_agent = AssessmentAgent(
        model_name=OLLAMA_MODEL, api_key=OLLAMA_API_KEY, base_url=OLLAMA_BASE_URL
    )

    # Hàm run mới nhận list finding và trả về list đã được "làm giàu" thêm
    final_findings = assessment_agent.run(enriched_findings)

    # # 6. ---- BƯỚC 6: In Báo cáo Cuối cùng ----
    # # Bây giờ in kết quả cuối cùng, đã bao gồm cả Risk Score VÀ SMM Assessment
    # print("\n\n--- BÁO CÁO CUỐI CÙNG (Risk + SMM Assessment) ---")
    # print(json.dumps(final_findings, indent=2, ensure_ascii=False))
    # print("=" * 70)
    # # --- BƯỚC 7: REMEDIATE (SỬA LỖI) ---
    # if final_findings:
    #     print("\n" + "=" * 15 + " BẮT ĐẦU QUY TRÌNH SỬA LỖI (INTERACTIVE) " + "=" * 15)

    #     remediate_agent = RemediateAgent(
    #         model_name=OLLAMA_MODEL, api_key=OLLAMA_API_KEY, base_url=OLLAMA_BASE_URL
    #     )

    #     # 1. Nhờ AI lập kế hoạch tổng thể trước
    #     remediation_plan_str = remediate_agent.recommend_fixes(final_assessed_findings)

    #     try:
    #         remediation_plan = json.loads(remediation_plan_str)
    #     except Exception:
    #         remediation_plan = []

    #     if remediation_plan:
    #         total_tasks = len(remediation_plan)
    #         print(f"\n[MainAgent] 📋 AI đã tìm thấy {total_tasks} vấn đề cần xử lý.")
    #         print("Hệ thống sẽ duyệt qua từng lỗi để bạn quyết định.\n")

    #         # 2. VÒNG LẶP HỎI TỪNG CÁI (Interactive Loop)
    #         for index, task in enumerate(remediation_plan, 1):
    #             # Lấy thông tin chi tiết
    #             tool_name = task.get("tool_to_call")
    #             params = task.get("tool_parameters", {})
    #             if not params:
    #                 params = task  # Fallback

    #             bucket_name = params.get("bucket_name", "N/A")
    #             finding_id = params.get("finding_id", "Unknown ID")

    #             # In ra giao diện thẻ bài
    #             print("-" * 60)
    #             print(f"🔴 VẤN ĐỀ #{index}/{total_tasks}")
    #             print(f"   • Tài nguyên: {bucket_name}")
    #             print(f"   • Mã lỗi    : {finding_id}")
    #             print(f"🛠️ GIẢI PHÁP ĐỀ XUẤT:")
    #             print(f"   • Công cụ   : {tool_name}")
    #             print("-" * 60)

    #             # 3. Hỏi người dùng
    #             while True:
    #                 user_choice = (
    #                     input(">>> Bạn có muốn thực thi sửa lỗi này không? (y/n): ")
    #                     .strip()
    #                     .lower()
    #                 )
    #                 if user_choice in ["y", "yes"]:
    #                     # Gọi Agent thực thi ĐÚNG 1 TASK này
    #                     # Truyền vào list chứa 1 phần tử [task]
    #                     remediate_agent.execute_fixes([task])
    #                     break
    #                 elif user_choice in ["n", "no"]:
    #                     print("   -> ⏩ Đã bỏ qua (Skipped).")
    #                     break
    #                 else:
    #                     print("   (Vui lòng nhập 'y' để đồng ý hoặc 'n' để bỏ qua)")

    #         print("-" * 60)
    #         print("[MainAgent] ✅ Đã duyệt xong danh sách.")

    #     else:
    #         print("[MainAgent] ✅ Không có hành động nào được đề xuất.")

    # print("\n[MainAgent]🏁 Hoàn tất toàn bộ quy trình.")

    # ==========================================================
    # 6) REMEDIATION STAGE (Template-Based)
    # ==========================================================

    print("\n=================== REMEDIATION MODE =====================")
    remediate_agent = RemediateAgent(
        model_name=OLLAMA_MODEL, api_key=OLLAMA_API_KEY, base_url=OLLAMA_BASE_URL
    )

    # ---- Step 1: Ask LLM to plan remediation (tool_id + params) ----
    plans = remediate_agent.recommend_fixes(final_findings)

    if not plans:
        print("Không có đề xuất sửa lỗi.")
        return

    print(f"\n📌 LLM đã xác định {len(plans)} vấn đề có thể remediate.")
    print(json.dumps(plans, indent=2, ensure_ascii=False))

    # ---- Step 2: Duyệt từng remediation task ----
    for idx, task in enumerate(plans, start=1):
        tool_id = task.get("tool_id")
        params = task.get("params", {})

        print("\n--------------------------------------------------------")
        print(f"🔧 Remediation #{idx}")
        print(f"📦 Tool      : {tool_id}")
        print(f"🎯 Resource  : {params}")
        print("--------------------------------------------------------")

        while True:
            choice = (
                input(">>> Thực thi task này? (y = Yes, d = Dry-run, n = Skip): ")
                .strip()
                .lower()
            )
            if choice in ["y", "yes"]:
                package = remediate_agent.build_action_package(tool_id, params)
                result = remediate_agent.executor.execute(package, dry_run=False)
                print("✅ Kết quả:", json.dumps(result, indent=2))
                break
            elif choice == "d":
                package = remediate_agent.build_action_package(tool_id, params)
                result = remediate_agent.executor.execute(package, dry_run=True)
                print("🧪 Dry-run:", json.dumps(result, indent=2))
                break
            elif choice in ["n", "no"]:
                print("⏭️ Skip.")
                break
            else:
                print("Vui lòng nhập y / d / n.")

    print("\n🎉 Hoàn tất quy trình Remediation.")
    print("===========================================================\n")

    # ==========================================================
    # 8) RESCAN AGENT – Quét lại sau remediation
    # ==========================================================
    print("\n=================== RESCAN MODE =====================")
    rescan_agent = RescanAgent()
    rescan_agent.run()  # tạo file post_scan.json

    # ==========================================================
    # 9) ANALYSIS AGENT – So sánh BEFORE vs AFTER
    # ==========================================================
    print("\n=================== ANALYSIS MODE =====================")
    analysis_agent = AnalysisAgent(
        before_path="data/pre_scan.json", after_path="data/post_scan.json"
    )

    diff = analysis_agent.run()

    with open("data/analysis_diff.json", "w") as f:
        json.dump(diff, f, indent=2)

    print("[MainAgent] 📊 Đã lưu file phân tích BEFORE/AFTER: data/analysis_diff.json")
    print("===========================================================\n")

    # ==========================================================
    # 10) REPORT AGENT – Tổng hợp báo cáo tiếng Việt
    # ==========================================================
    print("\n=================== REPORT MODE =====================")

    report_agent = ReportAgent(
        model_name=OLLAMA_MODEL,
        api_key=OLLAMA_API_KEY,
        base_url=OLLAMA_BASE_URL,
        output_path="data/final_report.md",
    )

    meta = {
        "account_id": os.environ.get("AWS_ACCOUNT_ID", "unknown"),
        "scan_group": plan.get("groups_to_scan"),
    }

    report_path = report_agent.run(diff, meta)
    print(f"[MainAgent] 📄 Báo cáo đã được tạo: {report_path}")


if __name__ == "__main__":
    main()
