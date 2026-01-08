import threading
import json
# Import trực tiếp các tool để gọi thẳng
from agent_tools import start_scan_by_group, start_scan_by_file, start_scan_by_check_ids

class TaskAssignmentAgent:
    """
    Phiên bản Deterministic (Tất định):
    Gọi tool trực tiếp thay vì nhờ AI suy luận.
    Đã fix lỗi trích xuất Job ID từ cấu trúc dữ liệu lồng nhau.
    """
    def __init__(self, scanner_agent=None):
        self.scanner_agent = scanner_agent
        self.thread_safe_job_ids = []
        self.lock = threading.Lock()

    def _extract_job_id(self, result):
        """
        Helper tách Job ID từ kết quả tool.
        Hỗ trợ 2 định dạng:
        1. {"job_id": "abc"} (API gốc)
        2. {"success": True, "data": {"job_id": "abc"}} (Tool Wrapper)
        """
        try:
            # 1. Parse JSON string nếu cần
            if isinstance(result, str):
                data = json.loads(result)
            else:
                data = result
            
            if not isinstance(data, dict):
                return None

            # 2. Case A: Key nằm ngay ngoài cùng
            if "job_id" in data:
                return data["job_id"]
            if "id" in data: # Fallback
                return data["id"]
            
            # 3. Case B: Key nằm trong 'data' (do agent_tools bọc lại)
            if "data" in data and isinstance(data["data"], dict):
                inner_data = data["data"]
                return inner_data.get("job_id") or inner_data.get("id")
                
        except Exception as e:
            print(f"[TaskExecutor] ❌ Error extracting job_id: {e}")
            
        return None

    def _execute_tool_thread(self, tool_func, **kwargs):
        """
        Chạy tool trong luồng riêng và lưu Job ID an toàn.
        """
        try:
            # Gọi tool trực tiếp thông qua .invoke()
            response = tool_func.invoke(kwargs)
            
            # Debug log (nếu cần xem response thực tế)
            # print(f"DEBUG TOOL RESPONSE: {response}")

            job_id = self._extract_job_id(response)
            
            if job_id:
                with self.lock:
                    self.thread_safe_job_ids.append(job_id)
            else:
                print(f"[TaskExecutor] ⚠️ Warning: Không lấy được Job ID từ tool {tool_func.name}")
                print(f"   -> Response nhận được: {str(response)[:100]}...") # In 100 ký tự đầu để debug
                
        except Exception as e:
            print(f"[TaskExecutor] ❌ Lỗi khi chạy tool: {e}")

    def run(self, plan: dict) -> list:
        print(f"--------------------------------------------------")
        print(f"[TaskAssignmentAgent]  Executing plan (Direct Mode)...")

        groups = plan.get("groups_to_scan", [])
        files = plan.get("files_to_scan", [])
        checks = plan.get("checks_to_scan", [])
        
        threads = []
        self.thread_safe_job_ids.clear()

        # 1. Xử lý Quét Group
        for group in groups:
            t = threading.Thread(
                target=self._execute_tool_thread, 
                args=(start_scan_by_group,), 
                kwargs={"group": group}
            )
            threads.append(t)
            t.start()

        # 2. Xử lý Quét File
        for file in files:
            t = threading.Thread(
                target=self._execute_tool_thread, 
                args=(start_scan_by_file,), 
                kwargs={"filename": file}
            )
            threads.append(t)
            t.start()

        # 3. Xử lý Quét Check Cụ thể
        if checks:
            checks_str = ",".join(checks)
            print(f"[TaskAssignmentAgent] 🎯 Executing Specific Scan: {checks_str}")
            t = threading.Thread(
                target=self._execute_tool_thread, 
                args=(start_scan_by_check_ids,), 
                kwargs={"check_ids": checks_str}
            )
            threads.append(t)
            t.start()

        # Đợi các luồng hoàn tất
        if threads:
            print(f"[TaskAssignmentAgent] 🚀 Đang chạy {len(threads)} tác vụ quét song song...")
            for t in threads:
                t.join()
            print(f"[TaskAssignmentAgent] ✅ Tất cả tác vụ quét đã hoàn thành.")
        else:
            print(f"[TaskAssignmentAgent] ⚠️ Không có gì để quét (Plan rỗng).")

        return self.thread_safe_job_ids