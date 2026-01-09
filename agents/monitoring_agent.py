# agents/monitoring_agent.py
import json
import time
from typing import List, Dict, Any
from agent_tools import AVAILABLE_FUNCTIONS


class MonitoringAgent:
    def __init__(self, poll_interval=15):
        self.check_status_tool = AVAILABLE_FUNCTIONS["check_job_status"]
        self.poll_interval = poll_interval

    def run(self, job_ids: list) -> List[Dict[str, Any]]:
        print(f"--------------------------------------------------")
        print(f"[MonitoringModule] Bắt đầu giám sát {len(job_ids)} job(s)")

        active_jobs = set(job_ids)
        all_findings = []  # List phẳng chứa findings

        while active_jobs:
            jobs_to_remove = set()

            for job_id in active_jobs:
                try:
                    response_raw = self.check_status_tool.invoke({"job_id": job_id})

                    # 1. Parse JSON String nếu cần
                    if isinstance(response_raw, str):
                        tool_output = json.loads(response_raw)
                    else:
                        tool_output = response_raw

                    # --- ĐOẠN SỬA QUAN TRỌNG ---
                    # Tool trả về: {"success": True, "data": {...API RESPONSE...}}
                    # Nên ta cần lấy API Response từ key "data"
                    api_response = tool_output.get("data", tool_output)

                    job_status = api_response.get("status")
                    # ---------------------------

                    if job_status == "completed":
                        print(f"   -> Job {job_id} hoàn tất.")

                        # Lấy result từ api_response (không phải từ tool_output gốc)
                        job_result = api_response.get("result", [])

                        # FLATTEN: Luôn add vào list chung
                        if isinstance(job_result, list):
                            all_findings.extend(job_result)
                        elif job_result:
                            all_findings.append(job_result)

                        jobs_to_remove.add(job_id)

                    elif job_status == "failed":
                        print(f"   -> ❌ Job {job_id} thất bại.")
                        jobs_to_remove.add(job_id)

                except Exception as e:
                    print(f"   -> ❌ Lỗi check job {job_id}: {e}")

            active_jobs -= jobs_to_remove

            if active_jobs:
                time.sleep(self.poll_interval)

        print(f"[MonitoringModule] Thu thập tổng cộng {len(all_findings)} findings.")
        return all_findings
