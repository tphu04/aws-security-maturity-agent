import json
import time
# from .base_agent import BaseAgent # <-- KHÔNG KẾ THỪA
from agent_tools import AVAILABLE_FUNCTIONS

class MonitoringAgent: # <-- BỎ (BaseAgent)
    """
    Agent này nhận một danh sách các job ID và theo dõi chúng.
    Nó KHÔNG gọi AI.
    Nó chỉ chạy vòng lặp, gọi tool 'check_job_status' cho đến khi
    tất cả các job hoàn thành, và trả về một DANH SÁCH các kết quả JSON thô.
    """
    
    # (SYSTEM_PROMPT và summarize_results ĐÃ BỊ XÓA)
    
    def __init__(self): # <-- BỎ model_name, api_key, base_url
        self.check_status_tool = AVAILABLE_FUNCTIONS["check_job_status"]

    def run(self, job_ids: list) -> list: # <-- Trả về LIST
        """
        Chạy agent và trả về một danh sách kết quả JSON thô.
        """
        print(f"--------------------------------------------------")
        print(f"[MonitoringAgent] 🤖 Bắt đầu giám sát {len(job_ids)} job(s): {job_ids}")
        active_jobs = set(job_ids)
        completed_job_results = []
        
        while active_jobs:
            jobs_to_remove = set()
            print(f"[MonitoringAgent] ⚙️ Mã điều phối: Đang kiểm tra {len(active_jobs)} job(s) còn lại...")
            
            for job_id in active_jobs:
                status_response_str = self.check_status_tool(job_id=job_id)
                print(f"   <- API trả về (job {job_id}): {status_response_str[:200]}...")
                
                try:
                    status_data = json.loads(status_response_str)
                    job_status = status_data.get("status")

                    if job_status in ["completed", "failed"]:
                        print(f"   -> ✅ Job {job_id} đã kết thúc với trạng thái '{job_status}'.")
                        completed_job_results.append(status_data)
                        jobs_to_remove.add(job_id)
                    elif job_status in ["running", "pending"]:
                        print(f"   -> ⏳ Job {job_id} vẫn đang '{job_status}'...")
                    else:
                        print(f"   -> ❓ Job {job_id} có trạng thái lạ: {status_data}")
                        completed_job_results.append(status_data)
                        jobs_to_remove.add(job_id)
                except json.JSONDecodeError:
                    print(f"   -> ❌ Lỗi: Phản hồi từ job {job_id} không phải JSON.")
                    completed_job_results.append({"status": "failed", "error": "Invalid JSON response from tool", "job_id": job_id})
                    jobs_to_remove.add(job_id)
            
            active_jobs -= jobs_to_remove
            
            if active_jobs:
                print(f"[MonitoringAgent] ⏳ Sẽ kiểm tra lại sau 15 giây...")
                time.sleep(15)
        
        print(f"[MonitoringAgent] 🤖 Tất cả các job đã hoàn thành.")
        
        # Trả về dữ liệu thô
        return completed_job_results