import json
import os
import inspect
import markdown
import pdfkit

from datetime import datetime
from typing import List, Dict, Any

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from .base_agent import BaseAgent
from agent_tools import ALL_TOOLS


# ======================================================================
# 1. TEMPLATES TIẾNG VIỆT — PHÂN TÍCH KỸ THUẬT
# ======================================================================

PRE_REMEDIATION_TEMPLATE = """
Bạn là kỹ sư bảo mật AWS. Hãy mô tả trạng thái hệ thống trước remediation.

Dữ liệu:
- Tổng số findings: {total}
- Số FAIL ban đầu: {fail_initial}
- Số PASS ban đầu: {pass_initial}
- Mức độ rủi ro:
  - Critical: {critical}
  - High: {high}
  - Medium: {medium}
  - Low: {low}

Yêu cầu:
- Diễn giải theo góc nhìn kỹ thuật.
- Nhóm các rủi ro theo chủ đề: Access Control, Replication, Logging, Encryption.
- Ghi rõ tác động bảo mật thực tế.
- Viết 5–7 câu.
"""

POST_REMEDIATION_TEMPLATE = """
Bạn là kỹ sư bảo mật AWS. Hãy mô tả trạng thái hệ thống sau remediation.

Dữ liệu:
- Tổng findings đã xử lý: {total}
- FIX thành công: {passed}
- FAIL còn tồn đọng: {failed}

Yêu cầu:
- Đánh giá mức độ cải thiện bảo mật.
- Mô tả những thay đổi kỹ thuật quan trọng đã được xử lý.
- Giải thích nguyên nhân 4 findings không fix được.
- Viết 4–7 câu.
"""

# ---------------- SUCCESS (DEEP ANALYSIS) ----------------

SUCCESS_TECH_TEMPLATE = """
Bạn là kỹ sư bảo mật AWS. Hãy phân tích kỹ thuật chi tiết CHO FINDING ĐÃ FIX THÀNH CÔNG.

### 🎯 Finding (đã dịch): {description_vi}
Resource: `{resource}`
Mức độ: {severity}
Tool sử dụng: `{tool_name}`

Execution Log:
{execution_log}

Yêu cầu phân tích:
1. Mô tả vấn đề gốc và rủi ro bảo mật trước khi sửa.
2. Giải thích rõ tool đã thực hiện bước nào, gọi API nào của AWS.
3. So sánh trạng thái trước và sau remediation.
4. Làm rõ vì sao remediation thành công (theo API response hoặc trạng thái sau sửa).
5. Viết 6–10 câu, kỹ thuật rõ ràng.
"""

# ---------------- FAILED (DEEP ANALYSIS) ----------------

FAILED_TECH_TEMPLATE = """
Bạn là kỹ sư bảo mật AWS. Hãy phân tích chi tiết một remediation đã thất bại.

### ❌ Finding (đã dịch): {description_vi}
Resource: `{resource}`
Mức độ: {severity}
Tool đã chạy: `{tool_name}`

Execution Log:
{execution_log}

Source Code Tool:
{tool_source_code}

Yêu cầu phân tích:
1. Mô tả chính xác logic mà tool cố gắng thực hiện.
2. Nêu nguyên nhân kỹ thuật dẫn đến thất bại (API từ chối, thiếu quyền, thiếu điều kiện, service limitation...).
3. Mô tả trạng thái trước/sau và lý do không thể chuyển sang PASS.
4. Viết các bước remediation thủ công (tối thiểu 3–6 bước).
5. Viết 7–12 câu, kỹ thuật rõ ràng.
"""

# ---------------- RESIDUAL RISK ----------------

RESIDUAL_RISK_TEMPLATE = """
Bạn là kỹ sư bảo mật AWS. Hãy phân tích rủi ro tồn đọng.

Danh sách FAIL:
{failed_items}

Yêu cầu:
- Tóm tắt bản chất rủi ro kỹ thuật.
- Nêu lý do vì sao tool không thể tự động fix.
- Giải thích tác động bảo mật nếu không xử lý tiếp.
- Đề xuất 3–5 bước khắc phục thủ công.
- Viết 5–8 câu.
"""


# ======================================================================
# 2. ReportAgent V7 — FULL TECHNICAL VERSION (VIETNAMESE)
# ======================================================================


class ReportAgent(BaseAgent):

    def __init__(
        self, model_name, api_key, base_url, output_path="data/final_report.md"
    ):
        super().__init__(model_name, api_key, base_url)
        self.output_path = output_path

        self.llm = ChatOllama(model=model_name, base_url=base_url, temperature=0.1)

        # Prompt chains
        self.pre_chain = (
            ChatPromptTemplate.from_template(PRE_REMEDIATION_TEMPLATE)
            | self.llm
            | StrOutputParser()
        )
        self.post_chain = (
            ChatPromptTemplate.from_template(POST_REMEDIATION_TEMPLATE)
            | self.llm
            | StrOutputParser()
        )
        self.success_chain = (
            ChatPromptTemplate.from_template(SUCCESS_TECH_TEMPLATE)
            | self.llm
            | StrOutputParser()
        )
        self.fail_chain = (
            ChatPromptTemplate.from_template(FAILED_TECH_TEMPLATE)
            | self.llm
            | StrOutputParser()
        )
        self.residual_chain = (
            ChatPromptTemplate.from_template(RESIDUAL_RISK_TEMPLATE)
            | self.llm
            | StrOutputParser()
        )

        self.tool_source = self._load_tool_sources()

    # ==================================================================
    # MAIN EXECUTION
    # ==================================================================

    def run(self, diff_data: List[Dict], meta: Dict) -> str:
        normalized = self._normalize(diff_data)
        classified = self._classify_findings(normalized)

        pre_summary = self._generate_pre_summary(classified)
        post_summary = self._generate_post_summary(classified)

        success_section = self._generate_success_analysis(classified)
        fail_section = self._generate_fail_analysis(classified)
        residual_risk = self._generate_residual_risk(classified)

        md = self._render_markdown(
            meta,
            classified,
            pre_summary,
            post_summary,
            success_section,
            fail_section,
            residual_risk,
        )

        self._save_report(md)

        # Xuất PDF kèm theo
        pdf_path = self.output_path.replace(".md", ".pdf")
        self._export_pdf(self.output_path, pdf_path)

        return md

    # ==================================================================
    # NORMALIZE
    # ==================================================================
    def _normalize(self, diff_data):
        normalized = []
        for item in diff_data:
            norm = {
                "finding_id": item.get("finding_id"),
                "resource_id": item.get("resource_id"),
                "description": item.get("description", "").strip(),
                "status": item.get("status"),
                "change": (item.get("change") or "").lower(),
                "tool_name": item.get("tool_name") or "unknown_tool",
            }

            # Severity normalize
            sev = str(item.get("severity", "Low")).lower()
            sev_map = {
                "critical": "Critical",
                "high": "High",
                "medium": "Medium",
                "low": "Low",
            }
            norm["severity"] = sev_map.get(sev, "Low")

            # Exec output
            exec_raw = item.get("execution_output")
            if isinstance(exec_raw, dict):
                norm["execution_output"] = json.dumps(exec_raw)
            else:
                try:
                    norm["execution_output"] = json.dumps(json.loads(exec_raw))
                except:
                    norm["execution_output"] = json.dumps({"raw": exec_raw})

            normalized.append(norm)

        return normalized

    # ==================================================================
    # CLASSIFY FINDINGS
    # ==================================================================
    def _classify_findings(self, items):
        passed, failed, unchanged = [], [], []

        for item in items:
            change = item["change"]
            status = item["status"]

            if change == "fixed":
                passed.append(item)
                continue

            if change == "unchanged" and status == "FAIL":
                failed.append(item)
                continue

            if change == "unchanged" and status == "PASS":
                unchanged.append(item)
                continue

            if status == "FAIL":
                failed.append(item)
            else:
                unchanged.append(item)

        return {"passed": passed, "failed": failed, "unchanged": unchanged}

    # ==================================================================
    # TRANSLATE FINDING TITLES
    # ==================================================================
    def _translate_finding_title(self, desc: str):
        mapping = {
            "cross-region replication": "kiểm tra xem bucket có bật Cross-Region Replication (CRR) hay không",
            "secure transport": "bắt buộc sử dụng HTTPS (SecureTransport)",
            "logging": "kiểm tra cấu hình Server Access Logging",
            "event notifications": "kiểm tra cấu hình Event Notifications",
            "lifecycle": "kiểm tra cấu hình Lifecycle",
            "encryption": "kiểm tra mã hóa S3",
            "public": "kiểm tra quyền Public Access",
            "acl": "kiểm tra ACL và quyền truy cập",
        }

        for eng, vi in mapping.items():
            if eng in desc.lower():
                return vi

        return desc

    # ==================================================================
    # PRE / POST SUMMARY
    # ==================================================================
    def _generate_pre_summary(self, classified):
        total = (
            len(classified["passed"])
            + len(classified["failed"])
            + len(classified["unchanged"])
        )
        fail_initial = len(classified["failed"]) + len(classified["unchanged"])
        pass_initial = len(classified["passed"])

        sev_count = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        for item in classified["failed"] + classified["unchanged"]:
            sev_count[item["severity"]] += 1

        return self.pre_chain.invoke(
            {
                "total": total,
                "fail_initial": fail_initial,
                "pass_initial": pass_initial,
                "critical": sev_count["Critical"],
                "high": sev_count["High"],
                "medium": sev_count["Medium"],
                "low": sev_count["Low"],
            }
        )

    def _generate_post_summary(self, classified):
        return self.post_chain.invoke(
            {
                "total": len(classified["passed"]) + len(classified["failed"]),
                "passed": len(classified["passed"]),
                "failed": len(classified["failed"]),
            }
        )

    # ==================================================================
    # SUCCESSFUL REMEDIATIONS — DEEP TECHNICAL ANALYSIS
    # ==================================================================
    def _generate_success_analysis(self, classified):
        if not classified["passed"]:
            return "_Không có remediation thành công._"

        sections = []

        for item in classified["passed"]:

            desc_vi = self._translate_finding_title(item["description"])

            prompt = {
                "description_vi": desc_vi,
                "resource": item["resource_id"],
                "severity": item["severity"],
                "tool_name": item["tool_name"],
                "execution_log": item["execution_output"],
                "extra": "Remediation thành công, trạng thái post-scan PASS.",
            }

            analysis = self.success_chain.invoke(prompt)
            sections.append(f"## {desc_vi}\n{analysis}")

        return "\n\n".join(sections)

    # ==================================================================
    # FAILED REMEDIATIONS — DEEP TECHNICAL ANALYSIS
    # ==================================================================
    def _generate_fail_analysis(self, classified):
        if not classified["failed"]:
            return "_Không còn lỗi remediation thất bại._"

        sections = []

        for item in classified["failed"]:
            desc_vi = self._translate_finding_title(item["description"])

            prompt = {
                "description_vi": desc_vi,
                "resource": item["resource_id"],
                "severity": item["severity"],
                "tool_name": item["tool_name"],
                "execution_log": item["execution_output"],
                "tool_source_code": self.tool_source.get(
                    item["tool_name"], "# Source not found"
                ),
            }

            analysis = self.fail_chain.invoke(prompt)
            sections.append(f"## {desc_vi}\n{analysis}")

        return "\n\n".join(sections)

    # ==================================================================
    # RESIDUAL RISK SUMMARY
    # ==================================================================
    def _generate_residual_risk(self, classified):
        if not classified["failed"]:
            return "_Không còn rủi ro tồn đọng._"

        bullets = [
            f"- {self._translate_finding_title(i['description'])}"
            for i in classified["failed"]
        ]

        return self.residual_chain.invoke({"failed_items": "\n".join(bullets)})

    # ==================================================================
    # LOAD TOOL SOURCE CODE
    # ==================================================================
    def _load_tool_sources(self):
        mp = {}
        for tool in ALL_TOOLS:
            try:
                func = tool.func if hasattr(tool, "func") else tool
                name = tool.name if hasattr(tool, "name") else tool.__name__
                mp[name] = inspect.getsource(func)
            except:
                mp[name] = "# Source unavailable"
        return mp

    # ==================================================================
    # RENDER MARKDOWN REPORT
    # ==================================================================
    def _render_markdown(self, meta, classified, pre, post, success, fail, residual):
        return f"""
# 🛡️ BÁO CÁO REMEDIATION AWS — KỸ THUẬT
**Tài khoản AWS:** `{meta.get("account_id")}`
**Nhóm dịch vụ:** {meta.get("scan_group")}
**Ngày tạo:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

# 1. Tổng quan trước khi Remediation
{pre}

---

# 2. Tổng quan sau Remediation
{post}

---

# 3. Các Remediation thành công (Phân tích kỹ thuật chi tiết)
{success}

---

# 4. Các Remediation thất bại (Phân tích kỹ thuật sâu)
{fail}

---

# 5. Tổng hợp rủi ro tồn đọng
{residual}

---

*Báo cáo được sinh tự động bởi ReportAgent*
"""

    # ==================================================================
    # SAVE REPORT
    # ==================================================================
    def _save_report(self, content: str):
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(content)

    # ==================================================================
    # EXPORT PDF (Markdown → HTML → PDF)
    # ==================================================================
    def _export_pdf(self, md_path: str, pdf_path: str):
        # Load markdown
        with open(md_path, "r", encoding="utf-8") as f:
            md_text = f.read()

        # Convert markdown → HTML
        html = markdown.markdown(
            md_text,
            extensions=["fenced_code", "tables"]
        )

        # CSS đẹp hơn cho PDF
        css = """
        body { font-family: Arial, sans-serif; padding: 30px; line-height: 1.6; }
        h1, h2, h3 { color: #0057ff; }
        pre { background: #f4f4f4; padding: 10px; border-radius: 5px; }
        code { font-size: 13px; }
        """

        html_final = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>{css}</style>
        </head>
        <body>{html}</body>
        </html>
        """

        # Lưu tạm file HTML
        temp_html = "data/temp_report.html"
        with open(temp_html, "w", encoding="utf-8") as f:
            f.write(html_final)

        # ⚠️ FIX CHO WINDOWS — chỉ đường dẫn tuyệt đối tới wkhtmltopdf.exe
        wkhtml_path = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
        config = pdfkit.configuration(wkhtmltopdf=wkhtml_path)

        # Convert HTML → PDF
        pdfkit.from_file(temp_html, pdf_path, configuration=config)
        print(f"[✔] Đã xuất PDF tại: {pdf_path}")
