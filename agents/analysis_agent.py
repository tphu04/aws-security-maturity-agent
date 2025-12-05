import json
import os
from typing import List, Dict, Any


class AnalysisAgent:
    """
    AnalysisAgent (The Aggregator)
    ------------------------------
    Nhiệm vụ:
    1. So sánh Pre-scan vs Post-scan để xác định trạng thái (Fixed, Unchanged, New).
    2. HỢP NHẤT (Merge) metadata từ các Agent trước (Risk Score, Tool Name, Execution Logs).
    3. Xuất ra file 'analysis_diff.json' đầy đủ để ReportAgent đọc.
    """

    def __init__(
        self, before_path="data/pre_scan.json", after_path="data/post_scan.json"
    ):
        self.before_path = before_path
        self.after_path = after_path

    def load(self):
        """Load dữ liệu scan thô từ file"""
        if not os.path.exists(self.before_path) or not os.path.exists(self.after_path):
            print("[AnalysisAgent] ⚠️ Warning: Scan files not found.")
            return [], []

        with open(self.before_path, "r", encoding="utf-8") as f:
            before = json.load(f).get("findings", [])
        with open(self.after_path, "r", encoding="utf-8") as f:
            after = json.load(f).get("findings", [])
        return before, after

    def run(self, pipeline_context: List[Dict] = None) -> List[Dict]:
        """
        Thực hiện so sánh và làm giàu dữ liệu.

        Args:
            pipeline_context: List chứa metadata từ các bước trước (Risk, Plan, Execute).
                              Được truyền vào từ Graph Orchestrator.
        """
        before, after = self.load()
        pipeline_context = pipeline_context or []

        print(f"\n[AnalysisAgent] 🤖 Aggregating data...")
        print(f"   - Pre-scan findings : {len(before)}")
        print(f"   - Post-scan findings: {len(after)}")
        print(f"   - Pipeline Context  : {len(pipeline_context)} items merged.")

        # 1. Map dữ liệu để so sánh nhanh
        before_map = {f["finding_uid"]: f for f in before}
        after_map = {f["finding_uid"]: f for f in after}

        # 2. Map Context từ Pipeline (Risk -> Plan -> Execute)
        # Key là finding_uid để khớp chính xác với finding
        context_map = {}
        for item in pipeline_context:
            uid = item.get("finding_uid")
            if uid:
                context_map[uid] = item

        diff_result = []

        # ---------------------------------------------------------
        # 3. CORE LOGIC: Check Findings & MERGE METADATA
        # ---------------------------------------------------------
        for uid, bf in before_map.items():
            af = after_map.get(uid)

            # Lấy dữ liệu context tương ứng cho finding này
            ctx = context_map.get(uid, {})

            # Khởi tạo entry mới từ finding gốc (Pre-scan)
            entry = bf.copy()
            entry["before_status"] = bf["status"]

            # === [DATA ENRICHMENT ZONE] Nạp dữ liệu từ các Agent trước ===
            # Từ RiskEvaluationAgent
            entry["risk_score"] = ctx.get("risk_score", 0)
            entry["ai_severity"] = ctx.get(
                "severity", bf.get("severity")
            )  # Ưu tiên AI severity
            entry["ai_reasoning"] = ctx.get("reasoning", "No AI reasoning available.")

            # Từ RemediationPlannerAgent
            entry["tool_name"] = ctx.get("tool_name")  # Tên tool đã dùng
            entry["tool_params"] = ctx.get("tool_params")  # Tham số tool
            entry["planner_reasoning"] = ctx.get(
                "planner_reasoning"
            )  # Tại sao chọn tool này

            # Từ ExecutionAgent
            entry["execution_status"] = ctx.get("execution_status")
            entry["execution_output"] = ctx.get(
                "execution_output"
            )  # Log output quan trọng
            entry["execution_error"] = ctx.get("execution_error")
            # =============================================================

            # Logic Diff trạng thái (Fixed / Unchanged / StatusChanged)
            if not af:
                # Finding không còn trong Post-scan => Đã fix
                entry.update({"change": "Fixed", "after_status": "FIXED"})

            elif bf["status"] != af["status"]:
                # Trạng thái thay đổi
                # Nếu chuyển sang PASS => Fixed
                if af["status"] == "PASS":
                    entry.update({"change": "Fixed", "after_status": "PASS"})
                else:
                    entry.update(
                        {"change": "StatusChanged", "after_status": af["status"]}
                    )

            else:
                # Trạng thái y nguyên
                entry.update({"change": "Unchanged", "after_status": af["status"]})

            diff_result.append(entry)

        # ---------------------------------------------------------
        # 4. Check New Findings (Regression)
        # ---------------------------------------------------------
        for uid, af in after_map.items():
            if uid not in before_map and af["status"] == "FAIL":
                # Đây là lỗi mới xuất hiện sau khi fix
                entry = af.copy()
                entry.update(
                    {
                        "change": "NewIssue",
                        "before_status": "N/A",
                        "after_status": af["status"],
                        "ai_reasoning": "New regression issue detected post-scan.",
                    }
                )
                diff_result.append(entry)

        # ---------------------------------------------------------
        # 5. Lưu file kết quả giàu dữ liệu
        # ---------------------------------------------------------
        output_file = "data/analysis_diff.json"
        os.makedirs("data", exist_ok=True)

        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(diff_result, f, indent=2, ensure_ascii=False)
            print(f"   ✅ Enriched analysis saved to: {output_file}")
        except Exception as e:
            print(f"   ❌ Error saving analysis file: {e}")

        # ---------------------------------------------------------
        # 6. In thống kê nhanh (Console Output)
        # ---------------------------------------------------------
        fixed = sum(1 for d in diff_result if d.get("change") == "Fixed")
        unchanged = sum(
            1
            for d in diff_result
            if d.get("change") == "Unchanged" and d.get("before_status") == "FAIL"
        )
        new_issues = sum(1 for d in diff_result if d.get("change") == "NewIssue")

        print("=" * 40)
        print("📈 ANALYSIS COMPARISON RESULT")
        print("=" * 40)
        print(f"   ✅ FIXED (Success) : {fixed}")
        print(f"   ⚠️ UNCHANGED (Fail): {unchanged}")
        print(f"   🚨 REGRESSION (New): {new_issues}")
        print("=" * 40)

        return diff_result
