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
            return {"groups_to_scan": [], "checks_to_scan": []}

    def start_job(self, group):
        """Khởi tạo job scan theo Group (VD: s3, iam)"""
        try:
            url = f"http://localhost:8000/scan/check?group={group}"
            resp = requests.get(url).json()
            return resp.get("job_id")
        except Exception as e:
            print(f"\n[RescanAgent] ❌ Lỗi kết nối API (Group): {e}")
            return None

    def start_specific_job(self, check_ids_list):
        """Khởi tạo job scan theo danh sách Check ID cụ thể"""
        try:
            # Chuyển list thành chuỗi cách nhau bởi dấu phẩy
            # VD: ['check_1', 'check_2'] -> 'check_1,check_2'
            ids_str = ",".join(check_ids_list)
            url = f"http://localhost:8000/scan/specific?check_ids={ids_str}"
            resp = requests.get(url).json()
            return resp.get("job_id")
        except Exception as e:
            print(f"\n[RescanAgent] ❌ Lỗi kết nối API (Specific): {e}")
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

        # Lấy thông tin từ file config
        groups = plan.get("groups_to_scan", []) or plan.get("target_services", [])
        specific_checks = plan.get("checks_to_scan", [])

        all_raw_findings = []

        # --- CASE 1: Ưu tiên Scan theo Specific Checks (Nếu có) ---
        if specific_checks:
            print(
                f"[RescanAgent] Phát hiện chế độ Specific Checks ({len(specific_checks)} checks)."
            )
            print(f"Scanning checks: {specific_checks}...", end="\r")

            job_id = self.start_specific_job(specific_checks)
            if job_id:
                job_data = self.poll(job_id)
                # Xóa dòng đang chạy
                print(f"{' ' * 80}", end="\r")

                if job_data and job_data.get("status") == "completed":
                    findings = job_data.get("result", [])
                    all_raw_findings.extend(findings)
                    print(f"   ✅ Specific Scan: Hoàn tất ({len(findings)} findings).")
                else:
                    print(f"   ❌ Specific Scan: Thất bại.")
            else:
                print(f"   ❌ Không thể khởi tạo Specific Scan.")

        # --- CASE 2: Scan theo Groups (Nếu không có specific checks hoặc muốn chạy bổ sung) ---
        elif groups:
            total_groups = len(groups)
            for i, g in enumerate(groups, 1):
                print(f"[{i}/{total_groups}] Scanning group '{g}'...", end="\r")

                job_id = self.start_job(g)
                if not job_id:
                    print(f"\n   ❌ '{g}': Không thể khởi tạo scan.")
                    continue

                job_data = self.poll(job_id)
                print(f"{' ' * 60}", end="\r")

                if job_data and job_data.get("status") == "completed":
                    findings = job_data.get("result", [])
                    if isinstance(findings, list):
                        all_raw_findings.extend(findings)
                        print(f"   ✅ Group '{g}': Scan hoàn tất.")
                    else:
                        print(f"   ⚠️ Group '{g}': Lỗi format dữ liệu.")
                else:
                    print(f"   ❌ Group '{g}': Scan thất bại.")

        else:
            print(
                "   ⚠️ Không tìm thấy cấu hình quét (groups hoặc checks) trong initial_scan_config.json"
            )

        # --- LƯU KẾT QUẢ ---
        norm_data = normalize_results(all_raw_findings)

        with open("data/post_scan.json", "w", encoding="utf-8") as f:
            json.dump(norm_data, f, indent=2, ensure_ascii=False)

        print("-" * 40)
        print(f"[RescanAgent] 💾 Dữ liệu đã lưu vào 'data/post_scan.json'")
        print(f"[RescanAgent] 🏁 Chuyển sang Analysis Agent để so sánh.")

        return norm_data
