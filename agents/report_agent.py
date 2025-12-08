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


# ================================================================
# TEMPLATE (GIỮ NGUYÊN)
# ================================================================

PRE_REMEDIATION_TEMPLATE = """
Bạn là kỹ sư bảo mật AWS. Hãy mô tả trạng thái hệ thống trước remediation.

Dữ liệu:
- Tổng số findings: {total}
- Số lượng FAIL Findings ban đầu: {fail_initial}
- Số lượng PASS Findings ban đầu: {pass_initial}
- Mức độ rủi ro:
  - Critical: Có {critical} findings
  - High: có {high} findings
  - Medium: {medium} findings
  - Low: {low} findings

Yêu cầu:
- Diễn giải kỹ thuật, không bịa nội dung.
- Không tạo thêm nhóm rủi ro nếu dữ liệu không có.
- Viết tối đa 6–8 câu.
"""

POST_REMEDIATION_TEMPLATE = """
Bạn là kỹ sư bảo mật AWS. Hãy mô tả trạng thái hệ thống sau remediation.

Dữ liệu:
- Tổng findings đã xử lý: {total}
- FIX thành công: {passed}
- FAIL còn tồn đọng: {failed}

Yêu cầu:
- Đánh giá mức độ cải thiện dựa trên số liệu thực.
- Không bịa lỗi hoặc hành động tool.
- Viết 4–6 câu.
"""

SUCCESS_TECH_TEMPLATE = """
Bạn là chuyên gia AWS, phân tích chi tiết cho FINDING ĐÃ FIX.

### 🎯 Finding: {description_vi}
Resource: `{resource}`
Mức độ: {severity}
Tool sử dụng: `{tool_name}`

Execution Log (Chuẩn hóa):
{execution_log}

Yêu cầu phân tích:
1. Mô tả vấn đề gốc (dựa theo description).
2. Nêu rủi ro bảo mật nếu không xử lý.
3. Tool đã làm gì (dựa theo execution_log & tool logic).
4. So sánh trước và sau remediation.
5. Vì sao remediation thành công (không bịa API).
Viết kỹ thuật, 6–10 câu.
"""

FAILED_TECH_TEMPLATE = """
Bạn là chuyên gia AWS, phân tích chi tiết FINDING KHÔNG FIX ĐƯỢC.

### ❌ Finding: {description_vi}
Resource: `{resource}`
Mức độ: {severity}
Tool chạy: `{tool_name}`

Execution log:
{execution_log}

Source Code Tool:
{tool_source_code}

Yêu cầu:
1. Tool cố gắng làm gì (dựa vào source code).
2. Lý do kỹ thuật khiến remediation thất bại (API deny, thiếu quyền...).
3. Trạng thái trước / sau và vì sao không thể PASS.
4. Đề xuất 3–5 bước fix thủ công.
Viết rõ ràng, không bịa API.
"""

RESIDUAL_RISK_TEMPLATE = """
Bạn là kỹ sư bảo mật AWS. Hãy phân tích rủi ro tồn đọng sau remediation.

Danh sách FAIL còn lại:
{failed_items}

Yêu cầu:
- Rủi ro kỹ thuật thực tế.
- Vì sao tool không thể tự fix.
- Tác động nếu không xử lý.
- Đề xuất 3–5 remediation thủ công.
"""


# ================================================================
# REPORT AGENT (CHỈ FIX LỖI, KHÔNG THAY ĐỔI LỚN)
# ================================================================


class ReportAgent(BaseAgent):

    def __init__(self, model, api_key, base_url, output_path="data/final_report.md"):
        super().__init__(model, api_key, base_url)
        self.output_path = output_path

        self.llm = ChatOllama(model=model, base_url=base_url, temperature=0.1)

        # prompt chains
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

    # ------------------------------------------------------------
    # MAIN RUN
    # ------------------------------------------------------------
    def run(self, pre_scan: Dict, diff_data: Any, meta: Dict) -> str:

        # 🔥 FIX: diff_data có thể là dict → lấy trường hợp chuẩn: diff_data["results"]
        if isinstance(diff_data, dict) and "results" in diff_data:
            diff_data = diff_data["results"]

        if not isinstance(diff_data, list):
            diff_data = []

        self.pre_scan = pre_scan

        normalized = self._normalize(diff_data)
        classified = self._classify_findings(normalized)

        pre_summary = self._generate_pre_summary()
        post_summary = self._generate_post_summary(classified)

        success_section = self._generate_success_analysis(classified)
        fail_section = self._generate_fail_analysis(classified)
        residual_risk = self._generate_residual_risk(classified)

        md = self._render_markdown(
            meta,
            pre_summary,
            post_summary,
            success_section,
            fail_section,
            residual_risk,
        )

        self._save_report(md)
        self._export_pdf(self.output_path, self.output_path.replace(".md", ".pdf"))

        return md

    # ------------------------------------------------------------
    # NORMALIZER (CHỈ FIX LỖI)
    # ------------------------------------------------------------
    def _normalize(self, diff_data):
        normalized = []

        for item in diff_data:
            out = {
                "finding_id": item.get("finding_id"),
                "resource_id": item.get("resource_id"),
                "description": item.get("description", ""),
                "severity": item.get("severity", "Low"),
                "status": item.get("after_status", item.get("status", "PASS")),
                "change": (item.get("change") or "").lower(),
                "tool_name": item.get("tool_name", "unknown_tool"),
            }

            # 🔥 FIX: Log có thể là None
            log_raw = item.get("execution_output", {})
            try:
                out["execution_output"] = json.dumps(
                    log_raw, indent=2, ensure_ascii=False
                )
            except:
                out["execution_output"] = str(log_raw)

            normalized.append(out)

        return normalized

    # ------------------------------------------------------------
    # CLASSIFIER
    # ------------------------------------------------------------
    def _classify_findings(self, items):
        passed, failed, unchanged = [], [], []

        for it in items:
            ch = it["change"]
            st = it["status"]

            if ch in ["fixed", "improved"]:
                passed.append(it)
            elif ch in ["regressed", "error"]:
                failed.append(it)
            elif ch in ["unchanged", "no_change"]:
                if st == "FAIL":
                    failed.append(it)
                else:
                    unchanged.append(it)
            else:
                if st == "FAIL":
                    failed.append(it)
                else:
                    unchanged.append(it)

        return {"passed": passed, "failed": failed, "unchanged": unchanged}

    # ------------------------------------------------------------
    # PRE SUMMARY
    # ------------------------------------------------------------
    def _generate_pre_summary(self):
        findings = self.pre_scan.get("findings", [])

        total = len(findings)
        fail_initial = sum(1 for f in findings if f["status"] == "FAIL")
        pass_initial = sum(1 for f in findings if f["status"] == "PASS")

        sev_count = {
            "critical": sum(1 for f in findings if f["severity"].lower() == "critical"),
            "high": sum(1 for f in findings if f["severity"].lower() == "high"),
            "medium": sum(1 for f in findings if f["severity"].lower() == "medium"),
            "low": sum(1 for f in findings if f["severity"].lower() == "low"),
        }

        return self.pre_chain.invoke(
            {
                "total": total,
                "fail_initial": fail_initial,
                "pass_initial": pass_initial,
                **sev_count,
            }
        )

    # ------------------------------------------------------------
    # POST SUMMARY
    # ------------------------------------------------------------
    def _generate_post_summary(self, classified):
        return self.post_chain.invoke(
            {
                "total": len(classified["passed"]) + len(classified["failed"]),
                "passed": len(classified["passed"]),
                "failed": len(classified["failed"]),
            }
        )

    # ------------------------------------------------------------
    # FINDING TRANSLATE
    # ------------------------------------------------------------
    def _translate(self, desc, fid=None):
        desc_low = desc.lower()

        mapping = {
            "cross-region": "Kiểm tra Cross-Region Replication",
            "secure transport": "Bắt buộc sử dụng HTTPS",
            "logging": "Kiểm tra Server Access Logging",
            "lifecycle": "Kiểm tra Lifecycle",
            "kms": "Kiểm tra KMS Encryption",
            "public access": "Kiểm tra Public Access",
            "mfa delete": "Kiểm tra MFA Delete",
        }

        for k, v in mapping.items():
            if k in desc_low:
                return v

        return desc

    # ------------------------------------------------------------
    # SUCCESS SECTION
    # ------------------------------------------------------------
    def _generate_success_analysis(self, classified):
        if not classified["passed"]:
            return "_Không có remediation thành công._"

        sections = []
        for it in classified["passed"]:
            desc_vi = self._translate(it["description"], it["finding_id"])
            txt = self.success_chain.invoke(
                {
                    "description_vi": desc_vi,
                    "resource": it["resource_id"],
                    "severity": it["severity"],
                    "tool_name": it["tool_name"],
                    "execution_log": it["execution_output"],
                }
            )
            sections.append(f"## {desc_vi}\n{txt}")

        return "\n\n".join(sections)

    # ------------------------------------------------------------
    # FAILED SECTION
    # ------------------------------------------------------------
    def _generate_fail_analysis(self, classified):
        if not classified["failed"]:
            return "_Không còn remediation thất bại._"

        sections = []
        for it in classified["failed"]:
            desc_vi = self._translate(it["description"], it["finding_id"])

            tool_code = self.tool_source.get(it["tool_name"], "# Source not found")

            txt = self.fail_chain.invoke(
                {
                    "description_vi": desc_vi,
                    "resource": it["resource_id"],
                    "severity": it["severity"],
                    "tool_name": it["tool_name"],
                    "execution_log": it["execution_output"],
                    "tool_source_code": tool_code,
                }
            )
            sections.append(f"## {desc_vi}\n{txt}")

        return "\n\n".join(sections)

    # ------------------------------------------------------------
    # RESIDUAL RISK
    # ------------------------------------------------------------
    def _generate_residual_risk(self, classified):
        if not classified["failed"]:
            return "_Không còn rủi ro tồn đọng._"

        bullets = "\n".join(
            [
                f"- {self._translate(it['description'], it['finding_id'])}"
                for it in classified["failed"]
            ]
        )
        return self.residual_chain.invoke({"failed_items": bullets})

    # ------------------------------------------------------------
    # TOOL SOURCE
    # ------------------------------------------------------------
    def _load_tool_sources(self):
        mp = {}
        for t in ALL_TOOLS:
            try:
                func = t.func if hasattr(t, "func") else t
                name = t.name if hasattr(t, "name") else t.__name__
                mp[name] = inspect.getsource(func)
            except:
                mp[name] = "# Source unavailable"
        return mp

    # ------------------------------------------------------------
    # RENDER MARKDOWN
    # ------------------------------------------------------------
    def _render_markdown(self, meta, pre, post, success, fail, residual):
        return f"""
# 🛡️ BÁO CÁO REMEDIATION AWS — KỸ THUẬT
**Tài khoản AWS:** `{meta.get("account_id")}`
**Nhóm dịch vụ:** {meta.get("scan_group")}
**Ngày tạo:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

# 1. Tổng quan trước Remediation
{pre}

---

# 2. Tổng quan sau Remediation
{post}

---

# 3. Các Remediation thành công
{success}

---

# 4. Các Remediation thất bại
{fail}

---

# 5. Rủi ro tồn đọng
{residual}

---
*Generated automatically by PDCA Security Agent*
"""

    # ------------------------------------------------------------
    # SAVE
    # ------------------------------------------------------------
    def _save_report(self, md):
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(md)

    # ------------------------------------------------------------
    # EXPORT PDF (FIX: fallback nếu không có wkhtmltopdf)
    # ------------------------------------------------------------
    def _export_pdf(self, md_path, pdf_path):
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                md = f.read()

            html = markdown.markdown(md, extensions=["fenced_code", "tables"])

            wrapper = f"""
            <html>
            <head><meta charset="utf-8"><style>
            body {{ font-family: Arial; padding: 30px; }}
            h1,h2,h3 {{ color: #0057ff; }}
            pre {{ background: #f4f4f4; padding: 10px; }}
            </style></head>
            <body>{html}</body>
            </html>
            """

            tmp_html = "data/temp_report.html"
            with open(tmp_html, "w", encoding="utf-8") as f:
                f.write(wrapper)

            # 🔥 FIX: thử tìm wkhtmltopdf, nếu không có thì bỏ qua PDF
            possible_paths = [
                r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
                r"/usr/local/bin/wkhtmltopdf",
                r"/usr/bin/wkhtmltopdf",
            ]

            wk_path = next((p for p in possible_paths if os.path.exists(p)), None)
            if wk_path is None:
                print("⚠️ wkhtmltopdf không có trong hệ thống → bỏ qua PDF.")
                return

            cfg = pdfkit.configuration(wkhtmltopdf=wk_path)
            pdfkit.from_file(tmp_html, pdf_path, configuration=cfg)

        except Exception as e:
            print(f"⚠️ PDF export failed: {e}")
