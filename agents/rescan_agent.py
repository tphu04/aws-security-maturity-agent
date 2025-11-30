import json
import time
import requests
from agents.shared.normalizer import normalize_results

class RescanAgent:

    def __init__(self, config_path="data/initial_scan_config.json"):
        self.config_path = config_path

    def load_initial_config(self):
        with open(self.config_path, "r") as f:
            return json.load(f)

    def start_job(self, group):
        url = f"http://localhost:8000/scan/check?group={group}"
        resp = requests.get(url).json()
        print(f"[RescanAgent] ▶ start job group {group} -> job_id = {resp.get('job_id')}")
        return resp.get("job_id")

    def poll(self, job_id):
        url = f"http://localhost:8000/job/status?job_id={job_id}"
        while True:
            job = requests.get(url).json()
            st = job.get("status")
            print(f"[RescanAgent] ⏳ job {job_id}: {st}")
            if st in ["completed", "failed"]:
                return job
            time.sleep(3)

    def run(self):
        print("\n========== RESCAN AGENT ==========")
        plan = self.load_initial_config()
        groups = plan.get("groups_to_scan", [])
        print(f"[RescanAgent] 🔁 Đang Rescan các group: {groups}")

        all_job_results = []

        for g in groups:
            job = self.start_job(g)
            result = self.poll(job)
            all_job_results.append(result)

        print("[RescanAgent] 🧹 Chuẩn hoá AFTER scan...")
        after_scan = normalize_results(all_job_results)

        with open("data/post_scan.json", "w") as f:
            json.dump(after_scan, f, indent=2)

        print("[RescanAgent] 💾 Đã tạo file AFTER scan: data/post_scan.json")

        return after_scan
