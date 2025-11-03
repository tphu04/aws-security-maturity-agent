import os
import json
import threading
from dotenv import load_dotenv
from agents.planning_agent import PlanningAgent           
from agents.task_assignment_agent import TaskAssignmentAgent 
from agents.scanner_agent import ScannerAgent 
from agents.monitoring_agent import MonitoringAgent
from agents.remediate_agent import RemediateAgent 
# from agents.reporting_agent import ReportingAgent # <-- Tạm thời không cần
from agents.base_agent import BaseAgent 

# -------------------------------------------------------------------
# BƯỚC 1: CẤU HÌNH CLIENT
# -------------------------------------------------------------------

load_dotenv()
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_API_KEY = "ollama" # Giá trị giả

print(f"Đang sử dụng model Ollama: {OLLAMA_MODEL} tại {OLLAMA_BASE_URL}")
print("Hãy chắc chắn Ollama server và API server (uvicorn) đều đang chạy...")

# -------------------------------------------------------------------
# BƯỚC 2: HÀM MAIN ĐIỀU PHỐI (ORCHESTRATOR)
# -------------------------------------------------------------------

def main():
    print("="*50)
    print("🤖 Chào mừng đến với AWS Security Agent (v4 - Báo cáo đơn giản)")
    print("="*50)
    user_prompt = input("Tôi có thể giúp gì cho bạn? (ví dụ: quét s3 và iam) \n> ")

    if not user_prompt:
        print("Không có yêu cầu. Tạm biệt.")
        return

    # --- BƯỚC 1: Gọi PlanningAgent (Lập kế hoạch) ---
    planning_agent = PlanningAgent(
        model_name=OLLAMA_MODEL, 
        api_key=OLLAMA_API_KEY, 
        base_url=OLLAMA_BASE_URL
    )
    plan = planning_agent.run(user_prompt)

    if not plan.get("groups_to_scan") and not plan.get("files_to_scan"):
        print("\n[MainAgent] ❌ Agent lập kế hoạch không tạo được plan. Kết thúc.")
        return
    print(f"\n[MainAgent] 📋 Kế hoạch: {plan}")

    # --- BƯỚC 2: Gọi TaskAssignmentAgent (Giao việc) ---
    scanner_agent = ScannerAgent(
        model_name=OLLAMA_MODEL, 
        api_key=OLLAMA_API_KEY, 
        base_url=OLLAMA_BASE_URL
    )
    task_assignment_agent = TaskAssignmentAgent(scanner_agent)
    job_ids = task_assignment_agent.run(plan)
    
    if not job_ids:
        print("\n[MainAgent] ❌ Không có job nào được tạo. Kết thúc.")
        return
    print(f"\n[MainAgent] ✅ Đã tạo thành công {len(job_ids)} job(s): {job_ids}")

    # --- BƯỚC 3: Gọi MonitoringAgent (Thu thập kết quả) ---
    monitoring_agent = MonitoringAgent() # Không cần model
    structured_report_data = monitoring_agent.run(job_ids)
    
    print("\n" + "="*20 + " BÁO CÁO CẤU TRÚC (Kết quả quét) " + "="*20)
    print(json.dumps(structured_report_data, indent=2, ensure_ascii=False))
    print("="*65)
    
    # ---- BƯỚC 4: GỌI REMEDIATE AGENT (Analyze/Recommend) ----
    print("\n[MainAgent] 🤖 Đang gọi RemediateAgent để phân tích và báo cáo...")
    remediate_agent = RemediateAgent(
        model_name=OLLAMA_MODEL, 
        api_key=OLLAMA_API_KEY, 
        base_url=OLLAMA_BASE_URL
    )
    
    # Đây giờ là BÁO CÁO VĂN BẢN cuối cùng (Final Report)
    final_report = remediate_agent.recommend_fixes(structured_report_data)
    
    # In báo cáo cuối cùng
    print("\n" + "="*20 + " KẾ HOẠCH SỬA LỖI ĐỀ XUẤT (Báo cáo cuối) " + "="*20)
    print(final_report)
    print("="*70)
    
    # ---- BƯỚC 5 & 6 (TẠM TẮT) ----
    # Vì BƯỚC 4 đã là báo cáo cuối cùng, chúng ta không cần
    # bước thực thi (Execute) hoặc báo cáo (Reporting) nữa.

if __name__ == "__main__":
    main()

