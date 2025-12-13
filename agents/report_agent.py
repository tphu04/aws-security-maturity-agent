# ------------------------------------------------------------
# REPORT_AGENT.PY — FIXED VERSION
# ------------------------------------------------------------
from jinja2 import Template
from agents.report_module.exporters import write_file, render_html, export_pdf
from agents.report_module.template_markdown import REPORT_TEMPLATE
from agents.report_module.llm_writer import LLMWriter
import os
import yaml
import re
import inspect
from agent_tools import ALL_TOOLS
from datetime import datetime
from agents.report_module.chart_util import make_pass_fail_pie, make_severity_bar


class ReportAgent:

    def __init__(
        self,
        model=None,
        api_key=None,
        base_url=None,
        output_path=None,
        output_dir=None,
        llm_config=None,
    ):

        # LLM config fallback
        if llm_config is None:
            llm_config = {"model": model, "api_key": api_key, "base_url": base_url}

        self.llm = LLMWriter(**llm_config)

        # ================================
        #  CHUẨN HÓA OUTPUT PATH & FOLDER
        # ================================
        self.output_path = output_path or "reports/final_report.md"
        self.output_dir = os.path.dirname(self.output_path)

        os.makedirs(self.output_dir, exist_ok=True)

        # Các file xuất ra
        self.md_path = self.output_path
        self.html_path = os.path.join(self.output_dir, "final_report.html")
        self.pdf_path = os.path.join(self.output_dir, "final_report.pdf")

    # ------------------------------------------------------------
    def _normalize_table(self, table):
        """
        Ensure findings_summary is ALWAYS list-of-dict.
        Fix lỗi bảng bị phá → HTML không render table.
        """
        clean = []

        for i, row in enumerate(table):
            # Case 1: already dict
            if isinstance(row, dict):
                clean.append(row)
                continue

            # Case 2: tuple/list
            if isinstance(row, (list, tuple)):
                if len(row) >= 8:
                    clean.append(
                        {
                            "stt": row[0],
                            "finding": row[1],
                            "service": row[2],
                            "resource": row[3],
                            "severity": row[4],
                            "before": row[5],
                            "after": row[6],
                            "change": row[7],
                        }
                    )
                    continue

            # Case 3: raw markdown string: "| 1 | .... |"
            if isinstance(row, str):
                parts = [p.strip() for p in row.strip().strip("|").split("|")]
                if len(parts) >= 8:
                    clean.append(
                        {
                            "stt": parts[0],
                            "finding": parts[1],
                            "service": parts[2],
                            "resource": parts[3],
                            "severity": parts[4],
                            "before": parts[5],
                            "after": parts[6],
                            "change": parts[7],
                        }
                    )
                else:
                    print("⚠ Skipped malformed row:", row)
                continue

            print("⚠ Unknown row format:", row)

        return clean

    # ------------------------------------------------------------
    def run(self, ctx=None, report_context=None, meta=None):

        # BACKWARD COMPAT
        if ctx is None:
            if report_context is None:
                raise ValueError("Missing ctx or report_context")
            ctx = report_context
            # Merge meta vào ctx để không mất thông tin
            if meta:
                if "meta" not in ctx or ctx["meta"] is None:
                    ctx["meta"] = meta
                else:
                    # Merge WITHOUT overwriting existing keys unless new meta provides them
                    for k, v in meta.items():
                        if v is not None:
                            ctx["meta"][k] = v

        # PRE / POST
        pre = ctx.get("pre_remediation_data", {})
        post = ctx.get("post_remediation_data", {})

        pre_findings = ctx.get("raw_pre_findings", [])
        summary, pass_list, fail_list, pass_ctx, fail_ctx = (
            self._build_pre_overview_data(pre_findings)
        )

        # Lưu vào ctx nếu muốn template dùng
        ctx["pre_summary"] = summary
        ctx["pre_pass_ctx"] = pass_ctx
        ctx["pre_fail_ctx"] = fail_ctx

        # ======================================
        # GENERATE CHARTS
        # ======================================
        chart_dir = os.path.join(self.output_dir, "charts")
        os.makedirs(chart_dir, exist_ok=True)

        severity_chart_path = os.path.join(chart_dir, "severity_bar.png")
        passfail_chart_path = os.path.join(chart_dir, "pass_fail_pie.png")

        # Data nguồn
        sev = summary["severity_breakdown"]
        p = summary["total_pass"]
        f = summary["total_fail"]

        make_severity_bar(sev, severity_chart_path)
        make_pass_fail_pie(p, f, passfail_chart_path)

        # Gắn vào context
        # Gắn path thực để lưu file
        ctx["chart_severity_real"] = severity_chart_path
        ctx["chart_pass_fail_real"] = passfail_chart_path

        # Gắn path tương đối cho HTML / PDF
        ctx["chart_severity"] = "charts/severity_bar.png"
        ctx["chart_pass_fail"] = "charts/pass_fail_pie.png"

        post_fixed = {
            "initial_pass": post.get("initial_pass", 0),
            "initial_fail": post.get("initial_fail", 0),
            "final_pass": post.get("final_pass", 0),
            "final_fail": post.get("final_fail", 0),
            "fixed": post.get("fixed", 0),
            "failed": post.get("failed", 0),
            "manual": post.get("manual", 0),
        }

        severity_after = self._build_severity_after(ctx)

        llm_post_ctx = self._build_llm_post_analysis_context(
            ctx=ctx,
            post_fixed=post_fixed,
            severity_after=severity_after,
        )

        post_remediation_analysis = self.llm.write_post_remediation_analysis(
            llm_post_ctx
        )

        ctx["post_remediation_analysis"] = post_remediation_analysis

        recommendation_ctx = self._build_llm_recommendation_context(
            ctx=ctx,
            post_fixed=post_fixed,
            severity_after=severity_after,
        )

        post_remediation_recommendations = (
            self.llm.write_post_remediation_recommendations(recommendation_ctx)
        )

        ctx["post_remediation_recommendations"] = post_remediation_recommendations

        # ------------------------------------------------------------
        # BUILD SYSTEM OVERVIEW DATA (BEST PRACTICE VERSION)
        # ------------------------------------------------------------

        aws_ctx = ctx.get("aws_context", {})  # EnvironmentAgent output
        buckets = aws_ctx.get("buckets", [])
        region = aws_ctx.get("region", "us-east-1")

        system_overview_data = {
            "account_id": meta.get("account_id", "Unknown"),
            "region": region,
            "scan_scope": meta.get("scan_group", ["s3"]),
            "date": datetime.now().strftime("%Y-%m-%d"),
            # Tài nguyên thực tế
            "resources": {
                "total_buckets": len(buckets),
                "bucket_list": buckets,
            },
            # Công cụ được sử dụng trong pipeline
            "tools_used": [
                "Prowler",
                "AWS SDK (boto3)",
                "PDCA Security Agent",
            ],
            # Mục tiêu bảo mật cốt lõi (chỉ giữ keywords, không đưa narrative)
            "security_goals": [
                "Access control",
                "Data encryption",
                "Public exposure prevention",
                "Data resilience",
                "Compliance with AWS Well-Architected",
            ],
            # Phạm vi đánh giá (chỉ liệt kê facts, bỏ narrative)
            "assessment_scope": [
                "Access control review",
                "Bucket policy evaluation",
                "Encryption verification (SSE, KMS, SecureTransport)",
                "Resilience features (Versioning, MFA Delete, Replication)",
                "Automation pipeline remediation",
            ],
        }

        # Gắn vào ctx để ReportAgent sử dụng
        ctx["system_overview_data"] = system_overview_data
        system_overview_text = self.llm.write_system_overview(system_overview_data)

        ctx["pass_overview"] = self.llm.write_pass_findings_overview(pass_ctx)
        ctx["fail_overview"] = self.llm.write_fail_findings_overview(fail_ctx)

        # ------------------------------------------------------------
        # ENRICH FINDINGS
        # ------------------------------------------------------------
        for f in ctx["success_findings"]:
            f["execution_log"] = yaml.safe_dump(
                f.get("execution_output", {}), allow_unicode=True
            )

            # BEFORE / AFTER CHO REMEDIATION
            before = f.get("before") or {"status": f.get("before_status")}
            after = f.get("after") or {"status": f.get("after_status")}

            action = f.get("action") or f.get("execution_output", {}).get("action")
            resource = f.get("resource") or f.get("execution_output", {}).get(
                "resource"
            )

            tool_code = f.get("tool_code")
            tool_description = f.get("tool_description")

            f["llm_detail"] = self.llm.write_pass_remediation_detail(
                action=action,
                resource=resource,
                before=before,
                after=after,
                tool_code=tool_code,
                tool_description=tool_description,
            )

        for f in ctx["failed_findings"]:
            # log raw execution payload (giữ để debug)
            f["execution_log"] = yaml.safe_dump(
                f.get("execution_output", {}), allow_unicode=True
            )

            # BEFORE/AFTER (ngắn gọn, không cứng)
            before = f.get("before") or {"status": f.get("before_status")}
            after = f.get("after") or {"status": f.get("after_status")}

            # action/resource fallback từ execution_output
            action = f.get("action") or f.get("execution_output", {}).get("action")
            resource = f.get("resource") or f.get("execution_output", {}).get(
                "resource"
            )

            # execution error (đúng field)
            execution_error = (
                f.get("execution_error") or f.get("error") or f.get("exception")
            )

            tool_code = f.get("tool_code")
            tool_description = f.get("tool_description")

            f["llm_detail"] = self.llm.write_fail_remediation_detail(
                action=action,
                resource=resource,
                before=before,
                after=after,
                execution_status=f.get("execution_status"),
                execution_output=f.get("execution_output"),
                execution_error=execution_error,
                execution_timing=f.get("execution_timing"),
                tool_code=tool_code,
                tool_description=tool_description,
            )

        for f in ctx["manual_findings"]:
            f["llm_manual_guide"] = self.llm.write_manual_guide(f)

        # ------------------------------------------------------------
        # LLM – high-level sections
        # ------------------------------------------------------------
        llm_output = {
            "executive_summary": self.llm.write_exec_summary(
                pre, ctx.get("system_overview_data", {}), ctx.get("meta", {})
            ),
            "assessment_goals": self.llm.write_assessment_goals(
                ctx.get("meta", {}).get("user_input", "")
            ),
        }

        # ------------------------------------------------------------
        # NORMALIZE TABLE (MAIN FIX)
        # ------------------------------------------------------------
        clean_table = self._normalize_table(ctx["findings_summary"])

        # ------------------------------------------------------------
        # CONTEXT FOR TEMPLATE
        # ------------------------------------------------------------

        template_ctx = {
            "sys": ctx["system_overview_data"],
            "system_overview_text": system_overview_text,
            "summary": summary,
            "pre": pre,
            "post": post_fixed,
            "table": clean_table,
            "success": ctx["success_findings"],
            "failed": ctx["failed_findings"],
            "manual": ctx["manual_findings"],
            "pass_overview": ctx["pass_overview"],
            "fail_overview": ctx["fail_overview"],
            "post_remediation_analysis": ctx.get("post_remediation_analysis", ""),
            "post_remediation_recommendations": ctx.get(
                "post_remediation_recommendations", ""
            ),
            "llm": llm_output,
            "meta": ctx.get("meta", {}),
            "chart_severity": ctx.get("chart_severity", ""),
            "chart_pass_fail": ctx.get("chart_pass_fail", ""),
        }

        # ------------------------------------------------------------
        # RENDER MARKDOWN + HTML
        # ------------------------------------------------------------
        markdown = Template(REPORT_TEMPLATE).render(**template_ctx)
        write_file(self.md_path, markdown)

        html = render_html(markdown)

        # CSS nâng cao cho giao diện đẹp, bảng chuẩn Dashboard, hỗ trợ PDF
        border_css = """
        <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
        }
        h1, h2, h3 { color: #2c3e50; }
        h1 { border-bottom: 2px solid #2c3e50; padding-bottom: 10px; margin-bottom: 30px; }
        h2 { border-bottom: 1px solid #eee; padding-bottom: 8px; margin-top: 40px; }

        /* Bảng đẹp (Styled Table) */
        .styled-table {
            border-collapse: collapse;
            margin: 25px 0;
            font-size: 0.9em;
            font-family: sans-serif;
            min-width: 400px;
            width: 100%;
            box-shadow: 0 0 20px rgba(0, 0, 0, 0.15);
        }
        .styled-table thead tr {
            background-color: #009879;
            color: #ffffff;
            text-align: left;
        }
        .styled-table th, .styled-table td {
            padding: 12px 15px;
            border: 1px solid #dddddd;
        }
        .styled-table tbody tr {
            border-bottom: 1px solid #dddddd;
        }
        .styled-table tbody tr:nth-of-type(even) {
            background-color: #f3f3f3;
        }
        .styled-table tbody tr:last-of-type {
            border-bottom: 2px solid #009879;
        }

        /* Blockquote đẹp */
        blockquote {
            background: #f9f9f9;
            border-left: 5px solid #ccc;
            margin: 1.5em 10px;
            padding: 0.5em 10px;
        }

        /* Code block */
        pre {
            background: #f4f4f4;
            border: 1px solid #ddd;
            border-left: 3px solid #f36d33;
            color: #666;
            page-break-inside: avoid;
            font-family: monospace;
            font-size: 15px;
            line-height: 1.6;
            margin-bottom: 1.6em;
            max-width: 100%;
            overflow: auto;
            padding: 1em 1.5em;
            display: block;
            word-wrap: break-word;
        }
        </style>
        """

        html = border_css + html

        # Clean artifacts
        html = re.sub(r"<IMAGE FOR PAGE:[^>]*>", "", html)

        write_file(self.html_path, html)

        # ------------------------------------------------------------
        # EXPORT PDF
        # ------------------------------------------------------------
        export_pdf(html, self.pdf_path)

        return {
            "markdown": self.md_path,
            "html": self.html_path,
            "pdf": self.pdf_path,
        }

    # ------------------------------------------------------------
    # BUILD PRE-REMEDIATION OVERVIEW (PASS / FAIL / SUMMARY)
    # ------------------------------------------------------------
    def _build_pre_overview_data(self, pre_scan_findings):
        pass_list = []
        fail_list = []
        sev_count = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for f in pre_scan_findings:
            severity = f.get("severity", "").lower()
            if severity in sev_count:
                sev_count[severity] += 1

            simplified = {
                "finding_id": f.get("finding_id"),
                "event_code": f.get("event_code"),
                "description": f.get("description"),
                "severity": f.get("severity"),
                "resource": f.get("resource_id"),
            }

            if f.get("status") == "PASS":
                pass_list.append(simplified)
            else:
                fail_list.append(simplified)

        summary = {
            "total_findings": len(pre_scan_findings),
            "total_pass": len(pass_list),
            "total_fail": len(fail_list),
            "severity_breakdown": sev_count,
        }

        # Tạo summary cho PASS
        pass_context = {
            "total": len(pass_list),
            "by_severity": {
                "critical": sum(
                    1 for f in pass_list if f["severity"].lower() == "critical"
                ),
                "high": sum(1 for f in pass_list if f["severity"].lower() == "high"),
                "medium": sum(
                    1 for f in pass_list if f["severity"].lower() == "medium"
                ),
                "low": sum(1 for f in pass_list if f["severity"].lower() == "low"),
            },
            "by_event_code": {},
            "items": pass_list,
        }

        for f in pass_list:
            ec = f["event_code"]
            pass_context["by_event_code"][ec] = (
                pass_context["by_event_code"].get(ec, 0) + 1
            )

        # Summary cho FAIL
        fail_context = {
            "total": len(fail_list),
            "by_severity": {
                "critical": sum(
                    1 for f in fail_list if f["severity"].lower() == "critical"
                ),
                "high": sum(1 for f in fail_list if f["severity"].lower() == "high"),
                "medium": sum(
                    1 for f in fail_list if f["severity"].lower() == "medium"
                ),
                "low": sum(1 for f in fail_list if f["severity"].lower() == "low"),
            },
            "by_event_code": {},
            "items": fail_list,
        }

        for f in fail_list:
            ec = f["event_code"]
            fail_context["by_event_code"][ec] = (
                fail_context["by_event_code"].get(ec, 0) + 1
            )

        return summary, pass_list, fail_list, pass_context, fail_context

    def _build_llm_post_analysis_context(self, ctx, post_fixed, severity_after):
        """
        Build dataset CHUẨN để LLM phân tích mức 3.
        Tuyệt đối không gửi raw findings / raw diff.
        """
        return {
            "post_summary": post_fixed,
            "severity_after": severity_after,
            "fixed_findings": [
                {
                    "finding_id": f.get("finding_id"),
                    "description": f.get("description"),
                    "resource": f.get("resource"),
                    "action": f.get("action"),
                }
                for f in ctx.get("success_findings", [])
            ],
            "manual_findings": [
                {
                    "finding_id": f.get("finding_id"),
                    "description": f.get("description"),
                    "resource": f.get("resource"),
                    "manual_reason": f.get("manual_reason"),
                }
                for f in ctx.get("manual_findings", [])
            ],
            "failed_findings": [
                {
                    "finding_id": f.get("finding_id"),
                    "description": f.get("description"),
                    "resource": f.get("resource"),
                }
                for f in ctx.get("failed_findings", [])
            ],
            "automation_coverage": {
                "auto_fixed": post_fixed.get("fixed", 0),
                "manual_required": post_fixed.get("manual", 0),
                "failed": post_fixed.get("failed", 0),
            },
            "definitions": {
                "manual_findings_are_subset_of_fail": True,
                "failed_remediation_means_tool_executed_but_still_fail": True,
                "manual_findings_mean_no_auto_remediation_attempted": True,
            },
        }

    def _build_llm_recommendation_context(self, ctx, post_fixed, severity_after):
        """
        Build context CHUẨN để LLM viết mục Recommendations (Section 8).

        Nguyên tắc:
        - Chỉ dựa trên kết quả post-remediation
        - Không cho LLM phân tích lại hay suy diễn
        - Ép focus vào bước tiếp theo (next actions)
        """

        auto_fix_success = post_fixed.get("fixed", 0)
        auto_fix_failed = post_fixed.get("failed", 0)
        manual_required = post_fixed.get("manual", 0)

        # Xác định trạng thái remediation tổng thể
        remediation_profile = {
            "auto_fix_success": auto_fix_success,
            "auto_fix_failed": auto_fix_failed,
            "manual_required": manual_required,
            "manual_only": (
                auto_fix_success == 0 and auto_fix_failed == 0 and manual_required > 0
            ),
        }

        # Nhóm bản chất manual findings (rút gọn, không kỹ thuật)
        manual_characteristics = []

        for f in ctx.get("manual_findings", []):
            reason = (f.get("manual_reason") or "").lower()

            if "root" in reason or "mfa" in reason:
                manual_characteristics.append("high_privilege_requirement")
            elif "replication" in reason or "architecture" in reason:
                manual_characteristics.append("architectural_dependency")
            else:
                manual_characteristics.append("operational_constraint")

        manual_characteristics = list(set(manual_characteristics))

        return {
            "post_summary": {
                "initial_pass": post_fixed.get("initial_pass"),
                "initial_fail": post_fixed.get("initial_fail"),
                "final_pass": post_fixed.get("final_pass"),
                "final_fail": post_fixed.get("final_fail"),
            },
            "remediation_outcome": remediation_profile,
            "manual_characteristics": manual_characteristics,
            "severity_after": severity_after,
            "logic_constraints": {
                "manual_is_subset_of_fail": True,
                "no_failed_auto_remediation": auto_fix_failed == 0,
                "recommendations_should_focus_on_governance_and_process": True,
            },
        }

    def _build_severity_after(self, ctx):
        severity_after = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for row in ctx.get("findings_summary", []):
            if row.get("after") == "FAIL":
                sev = row.get("severity", "").lower()
                if sev in severity_after:
                    severity_after[sev] += 1

        return severity_after
