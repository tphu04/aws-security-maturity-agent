import os
import json
import threading
from dotenv import load_dotenv
from agents.planning_agent import PlanningAgent           
from agents.task_assignment_agent import TaskAssignmentAgent 
from agents.scanner_agent import ScannerAgent 
from agents.monitoring_agent import MonitoringAgent
from agents.remediate_agent import RemediateAgent
from agents.reporting_agent import ReportingAgent 
from agents.assessment_agent import AssessmentAgent 

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
    print("="*50)
    print("🤖 Chào mừng đến với AWS Security Agent (v4 - Maturity Assessment)")
    print("="*50)
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
    
    print("\n" + "="*20 + " BÁO CÁO CẤU TRÚC (Kết quả quét) " + "="*20)
    print(json.dumps(structured_report_data, indent=2, ensure_ascii=False))
    print("="*65)

    # ---- BƯỚC 4: REMEDIATE AGENT (Recommend) ----
    print("\n[MainAgent] 🤖 Đang gọi RemediateAgent để lập kế hoạch sửa lỗi...")
    remediate_agent = RemediateAgent(
        model_name=OLLAMA_MODEL, api_key=OLLAMA_API_KEY, base_url=OLLAMA_BASE_URL
    )
    remediation_plan_str = remediate_agent.recommend_fixes(structured_report_data)
    
    # ---- BƯỚC 5: (MỚI) ĐÁNH GIÁ ĐỘ TRƯỞNG THÀNH (AssessmentAgent) ----
    
    print("\n" + "="*15 + " ĐÁNH GIÁ ĐỘ TRƯỞNG THÀNH (MATURITY ASSESSMENT) " + "="*15)
    
    # --- THAY ĐỔI Ở ĐÂY ---
    # Lấy các Domain cần đánh giá từ Plan của người dùng
    domains_to_assess = map_aws_service_to_smm_domain(plan.get("groups_to_scan", []))
    
    if not domains_to_assess:
        print("[MainAgent] ℹ️ Không có Domain nào để đánh giá (Chỉ quét file tùy chỉnh?). Bỏ qua bước này.")
        domains_to_assess = []
        
    assessment_agent = AssessmentAgent(
        model_name=OLLAMA_MODEL, 
        api_key=OLLAMA_API_KEY, 
        base_url=OLLAMA_BASE_URL
    )
    
    assessment_reports = []

    for domain in domains_to_assess:
        maturity_report = assessment_agent.run_assessment(
            structured_report_data, 
            domain
        )
        assessment_reports.append(f"\n--- BÁO CÁO ĐÁNH GIÁ DOMAIN: {domain} ---\n{maturity_report}")

    print("\n" + "\n".join(assessment_reports))
    print("="*70)

    # ---- BƯỚC 6: BÁO CÁO TỔNG KẾT (ReportingAgent) ----
    
    # (Bỏ qua BƯỚC THỰC THI (Execute) cho Remediate để giữ flow sạch)
    execution_results = [] 
    
    print("\n[MainAgent] 🤖 Yêu cầu ReportingAgent tóm tắt TOÀN BỘ quá trình...")
    
    reporting_agent = ReportingAgent(
        model_name=OLLAMA_MODEL, 
        api_key=OLLAMA_API_KEY, 
        base_url=OLLAMA_BASE_URL
    )
    
    final_report = reporting_agent.run(
        scan_results=structured_report_data,
        remediation_results=execution_results
    )
    
    print("\n" + "="*20 + " BÁO CÁO TỔNG KẾT CUỐI CÙNG " + "="*20)
    print(final_report)
    print("="*70)


if __name__ == "__main__":
    main()