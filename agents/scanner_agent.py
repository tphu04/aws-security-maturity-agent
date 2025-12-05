import json
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import tools từ file tool registry của bạn
from agent_tools import start_scan_by_group, start_scan_by_file


class ScannerAgent:
    """
    ScannerAgent chịu trách nhiệm kích hoạt Prowler Scan song song.
    Sử dụng ThreadPoolExecutor để tối ưu tốc độ gọi API.
    """

    def __init__(self, max_workers: int = 5):
        """
        :param max_workers: Số luồng tối đa chạy đồng thời (Mặc định 5).
        """
        self.max_workers = max_workers

    def _trigger_group_scan(self, group: str) -> Optional[str]:
        """Hàm helper chạy trong 1 luồng riêng lẻ để gọi Tool"""
        try:
            print(f"   [Scanner-Thread] ⚡️ Đang kích hoạt scan cho Group: {group}")
            # Gọi tool thông qua .invoke() (LangChain standard)
            result_json = start_scan_by_group.invoke({"group": group})
            return self._extract_job_id(result_json)
        except Exception as e:
            print(f"   [Scanner-Thread] ❌ Lỗi quét group '{group}': {e}")
            return None

    def _trigger_file_scan(self, filename: str) -> Optional[str]:
        """Hàm helper cho file scan"""
        try:
            print(f"   [Scanner-Thread] ⚡️ Đang kích hoạt scan cho File: {filename}")
            result_json = start_scan_by_file.invoke({"filename": filename})
            return self._extract_job_id(result_json)
        except Exception as e:
            print(f"   [Scanner-Thread] ❌ Lỗi quét file '{filename}': {e}")
            return None

    def run_batch(self, groups: List[str] = None, files: List[str] = None) -> List[str]:
        """
        Chạy song song việc kích hoạt scan cho danh sách groups và files.
        Trả về danh sách Job IDs.
        """
        job_ids = []
        groups = groups or []
        files = files or []

        total_tasks = len(groups) + len(files)
        if total_tasks == 0:
            return []

        print(
            f"[ScannerAgent] 🚀 Bắt đầu kích hoạt {total_tasks} jobs song song (Max workers: {self.max_workers})..."
        )

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []

            # 1. Submit Group Tasks
            for group in groups:
                futures.append(executor.submit(self._trigger_group_scan, group))

            # 2. Submit File Tasks (nếu có)
            for filename in files:
                futures.append(executor.submit(self._trigger_file_scan, filename))

            # 3. Thu thập kết quả
            for future in as_completed(futures):
                job_id = future.result()
                if job_id:
                    print(f"   [ScannerAgent] ✅ Job Created: {job_id}")
                    job_ids.append(job_id)

        print(
            f"[ScannerAgent] 🏁 Hoàn tất kích hoạt. Tổng cộng {len(job_ids)} jobs đang chạy."
        )
        return job_ids

    def _extract_job_id(self, tool_output) -> Optional[str]:
        """Parse response từ API server để lấy job_id"""
        try:
            # 1. Parse string nếu cần
            if isinstance(tool_output, str):
                data = json.loads(tool_output)
            else:
                data = tool_output

            if isinstance(data, dict):
                # --- ĐOẠN SỬA ---
                # Kiểm tra xem dữ liệu có nằm trong key "data" không (do cấu trúc mới của agent_tools)
                inner_data = data.get("data", data)

                # Ưu tiên lấy từ inner_data (cấu trúc mới), nếu không được thì fallback về data (cấu trúc cũ)
                job_id = (
                    inner_data.get("job_id")
                    or inner_data.get("id")
                    or data.get("job_id")
                )
                return job_id
                # ----------------

        except Exception as e:
            print(f"   [ScannerAgent] ⚠️ Parse error: {e}")
        return None
