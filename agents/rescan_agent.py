import json
import time
import requests
from agents.shared.normalizer import normalize_results


class RescanAgent:

    def __init__(self, config_path="data/initial_scan_config.json"):
        self.config_path = config_path

    def load_initial_config(self):
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"groups_to_scan": []}

    def start_job(self, group):
        try:
            url = f"http://localhost:8000/scan/check?group={group}"
            resp = requests.get(url).json()
            return resp.get("job_id")
        except Exception as e:
            print(f"\n[RescanAgent] ❌ Lỗi kết nối API: {e}")
            return None

    def poll(self, job_id):
        url = f"http://localhost:8000/job/status?job_id={job_id}"
        while True:
            try:
                job = requests.get(url).json()
                if job.get("status") in ["completed", "failed"]:
                    return job
                time.sleep(2)
            except:
                return None

    def run(self):
        print("\n" + "=" * 40)
        print("🔄 RESCAN PHASE (Verifying fixes)")
        print("=" * 40)

        plan = self.load_initial_config()
        groups = plan.get("groups_to_scan", []) or plan.get("target_services", [])

        all_raw_findings = []
        total_groups = len(groups)

        for i, g in enumerate(groups, 1):
            # In trạng thái đang chạy (ghi đè dòng cũ để gọn màn hình)
            print(f"[{i}/{total_groups}] Scanning group '{g}'...", end="\r")

            job_id = self.start_job(g)
            if not job_id:
                print(f"\n   ❌ '{g}': Không thể khởi tạo scan.")
                continue

            job_data = self.poll(job_id)

            # Xóa dòng "Scanning..." cũ bằng khoảng trắng trước khi in kết quả
            print(f"{' ' * 60}", end="\r")

            if job_data and job_data.get("status") == "completed":
                findings = job_data.get("result", [])
                if isinstance(findings, list):
                    all_raw_findings.extend(findings)
                    # Chỉ in thông báo thành công đơn giản
                    print(f"   ✅ Group '{g}': Scan hoàn tất.")
                else:
                    print(f"   ⚠️ Group '{g}': Lỗi format dữ liệu.")
            else:
                print(f"   ❌ Group '{g}': Scan thất bại.")

        # --- LƯU KẾT QUẢ ĐỂ ANALYSIS AGENT XỬ LÝ ---
        norm_data = normalize_results(all_raw_findings)

        with open("data/post_scan.json", "w", encoding="utf-8") as f:
            json.dump(norm_data, f, indent=2, ensure_ascii=False)

        print("-" * 40)
        print(f"[RescanAgent] 💾 Dữ liệu đã lưu vào 'data/post_scan.json'")
        print(f"[RescanAgent] 🏁 Chuyển sang Analysis Agent để so sánh.")

        return norm_data
