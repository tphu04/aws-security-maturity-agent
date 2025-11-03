import threading
from .scanner_agent import ScannerAgent # Import "thợ"

class TaskAssignmentAgent:
    """
    Agent này KHÔNG PHẢI LÀ AI (không kế thừa BaseAgent).
    Nó là một 'doer' (agent thực thi) nhận một kế hoạch (plan)
    và điều phối các 'ScannerAgent' chạy song song để thực hiện kế hoạch đó.
    Đây chính là "Task Assignment Agent" trong sơ đồ.
    """
    def __init__(self, scanner_agent: ScannerAgent):
        """
        Agent này cần một 'ScannerAgent' (AI) để làm việc.
        """
        self.scanner_agent = scanner_agent
        self.thread_safe_job_ids = []
        self.lock = threading.Lock()

    def _run_scan_task(self, scan_prompt: str):
        """
        Hàm private này sẽ được chạy trong một luồng (thread) riêng biệt.
        Nó gọi ScannerAgent và lưu kết quả job_id một cách an toàn.
        """
        job_id = self.scanner_agent.run_scan(scan_prompt)
        if job_id:
            with self.lock: # Khóa lại để tránh 2 luồng cùng ghi 1 lúc
                self.thread_safe_job_ids.append(job_id)
    
    def run(self, plan: dict) -> list:
        """
        Thực thi kế hoạch bằng cách chạy các ScannerAgent song song.
        """
        print(f"--------------------------------------------------")
        print(f"[TaskAssignmentAgent]  executing plan: {plan}")

        groups_to_scan = plan.get("groups_to_scan", [])
        files_to_scan = plan.get("files_to_scan", [])
        
        threads = []
        self.thread_safe_job_ids.clear() # Xóa job_id từ lần chạy trước

        # Tạo luồng cho 'groups'
        for group in groups_to_scan:
            scan_prompt = f"Hãy gọi tool start_scan_by_group cho service '{group}'."
            thread = threading.Thread(target=self._run_scan_task, args=(scan_prompt,))
            threads.append(thread)
            thread.start() # Bắt đầu chạy song song

        # Tạo luồng cho 'files'
        for file in files_to_scan:
            scan_prompt = f"Hãy gọi tool start_scan_by_file cho file '{file}'."
            thread = threading.Thread(target=self._run_scan_task, args=(scan_prompt,))
            threads.append(thread)
            thread.start() # Bắt đầu chạy song song

        # Đợi tất cả các luồng hoàn thành
        print(f"[TaskAssignmentAgent] 🚀 Đã khởi chạy {len(threads)} agent quét song song. Đang đợi...")
        for thread in threads:
            thread.join()

        print(f"[TaskAssignmentAgent] ✅ Các agent quét đã hoàn thành.")
        
        # Trả về danh sách các job_id đã thu thập được
        return self.thread_safe_job_ids