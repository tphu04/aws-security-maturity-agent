import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from .base_agent import BaseAgent


class ReportAgent(BaseAgent):
    """
    ReportAgent v2 (FIXED)
    ---------------------------------------
    - Hoàn toàn dựa vào data thật từ analysis_diff.json
    - Không bịa nội dung
    - LLM chỉ viết narrative dựa trên các số liệu đã tính
    - Xuất báo cáo dạng Markdown
    """

    SYSTEM_PROMPT = """
Bạn là ReportWriter AI. 
Nhiệm vụ:
- Ghi nhận dữ liệu thống kê (không thay đổi số liệu)
- Viết phần tóm tắt ngắn gọn, khách quan, KHÔNG được bịa thêm findings hoặc status.
- Không tự tạo thêm remediation. Không suy diễn phần "đã cải thiện".

Chỉ được dùng các số liệu do hệ thống cung cấp:
- improved_count
- unchanged_count
- regressions_count
- total
- failed_items (danh sách FAIL còn tồn tại)
    """

    def __init__(self, model_name, api_key, base_url):
        super().__init__(model_name, api_key, base_url)

    # ======================================================
    # Load diff file
    # ======================================================
    def load_diff(self, path: str = "data/analysis_diff.json") -> List[Dict[str, Any]]:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"[ReportAgent] Không tìm thấy file diff: {path}")

        with p.open("r", encoding="utf-8") as f:
            return json.load(f)

    # ======================================================
    # Generate Report
    # ======================================================
    def generate(self, diff_path="data/analysis_diff.json") -> str:
        print("[ReportAgent] 📄 Generating final report...")

        diff = self.load_diff(diff_path)

        # ===============================
        # Tính toán BEFORE/AFTER thật
        # ===============================
        total = len(diff)
        improved = [d for d in diff if d["before"] == "FAIL" and d["after"] == "PASS"]
        unchanged = [d for d in diff if d["change"] == "Unchanged"]
        regressions = [
            d for d in diff if d["before"] == "PASS" and d["after"] == "FAIL"
        ]
        still_fail = [d for d in diff if d["after"] == "FAIL"]

        improved_count = len(improved)
        unchanged_count = len(unchanged)
        regressions_count = len(regressions)
        still_fail_count = len(still_fail)

        # ===============================
        # Gửi dữ liệu thật cho LLM để
        # viết phần narrative
        # ===============================
        stats_context = {
            "total": total,
            "improved_count": improved_count,
            "unchanged_count": unchanged_count,
            "regressions_count": regressions_count,
            "still_fail": [x["finding_uid"] for x in still_fail],
        }

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(stats_context, indent=2, ensure_ascii=False),
            },
        ]

        # Narrative từ LLM (dựa hoàn toàn trên số liệu thật)
        try:
            llm_resp = self.call_llm(messages)
            narrative = (
                llm_resp.content
                if isinstance(llm_resp.content, str)
                else str(llm_resp.content)
            )
        except Exception as e:
            narrative = f"(LLM narrative unavailable: {e})"

        # ===============================
        # Build Markdown Report
        # ===============================
        now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        md_lines = [
            "# 🛡️ AWS Security Assessment Report",
            f"**Thời gian:** {now_utc}",
            "---",
            "## 📊 Tóm tắt BEFORE / AFTER",
            f"- Tổng findings: **{total}**",
            f"- Đã cải thiện (FAIL → PASS): **{improved_count}**",
            f"- Không thay đổi: **{unchanged_count}**",
            f"- Bị tệ hơn (PASS → FAIL): **{regressions_count}**",
            f"- Vẫn còn FAIL: **{still_fail_count}**",
            "---",
            "## 📝 Phân tích tổng quan",
            narrative,
            "---",
            "## 📋 Bảng chi tiết",
            "| UID | BEFORE | AFTER | Change |",
            "|------|--------|--------|--------|",
        ]

        for item in diff:
            uid = item["finding_uid"]
            before = item["before"]
            after = item["after"]
            change = item["change"]
            md_lines.append(f"| `{uid}` | {before} | {after} | **{change}** |")

        report_md = "\n".join(md_lines)

        # Xuất ra file
        output_path = "final_report.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report_md)

        print(f"[ReportAgent] ✅ Report saved to {output_path}")
        return output_path
