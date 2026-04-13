# ------------------------------------------------------------
# REPORT_AGENT.PY — Rebuilt (Sprint 2 + Hotfix)
# Clean architecture: validate → derive → LLM → enrich → render
# Input data is READ-ONLY (deep copy in enrich, không mutate)
# ------------------------------------------------------------
import copy
import os
import time
import yaml
from uuid import uuid4
from typing import Dict, Any, List, Optional

from jinja2 import Template
from agents.report_module.llm_writer import LLMWriter
from agents.report_module.exporters import write_file, export_pdf
from agents.report_module.chart_util import make_pass_fail_pie, make_severity_bar


class ReportTimer:
    """Accumulate LLM call durations for metrics."""

    def __init__(self):
        self.total_duration = 0.0
        self.call_history = []

    def record(self, duration: float):
        self.total_duration += duration
        self.call_history.append(duration)


class LLMTimerProxy:
    """Proxy wrapping LLMWriter to measure each call's latency."""

    def __init__(self, target, timer: ReportTimer):
        self._target = target
        self._timer = timer

    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if callable(attr):
            def wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return attr(*args, **kwargs)
                finally:
                    self._timer.record(time.perf_counter() - start)
            return wrapper
        return attr


class ReportAgent:

    def __init__(self, model: Optional[str] = None,
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 output_path: Optional[str] = None,
                 llm_config: Optional[Dict[str, Any]] = None):
        self.timer = ReportTimer()

        # LLM setup (injectable for testing)
        llm_instance = self._create_llm(model, api_key, base_url, llm_config)
        self.llm = LLMTimerProxy(LLMWriter(llm=llm_instance), self.timer)

        # Output paths
        self.output_path = output_path or "reports/final_report.md"
        self.output_dir = os.path.dirname(self.output_path)
        os.makedirs(self.output_dir, exist_ok=True)

    # ----------------------------------------------------------
    # LLM FACTORY
    # ----------------------------------------------------------
    def _create_llm(self, model, api_key, base_url, llm_config):
        """Support injecting LLM instance or auto-create Ollama.
        api_key kept for backward compat with orchestrator constructor call.
        """
        _ = api_key  # reserved for future OpenAI/Claude backends
        if llm_config and "llm" in llm_config:
            return llm_config["llm"]

        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model or "llama3.1",
            base_url=base_url,
            temperature=0.5,
        )

    # ----------------------------------------------------------
    # MAIN — ~30 lines, chỉ điều phối
    # ----------------------------------------------------------
    def run(self, data: dict = None, report_context: dict = None,
            **_kwargs) -> dict:
        """
        INPUT:  data (từ build_report_data) — đầy đủ, read-only
        OUTPUT: {"markdown": path, "html": path, "pdf": path}

        Backward compat: accepts report_context= and meta= kwargs
        from old orchestrator interface.
        """
        # Backward compat: support report_context kwarg
        if data is None:
            if report_context is None:
                raise ValueError("Missing data or report_context")
            data = report_context

        self._validate_input(data)

        # 1. Read input (KHÔNG mutate data)
        pre = data["pre"]
        post = data["post"]
        env = data["environment"]
        scope = data["scope"]

        # 2. Derived data (biến mới)
        pass_findings, fail_findings = self._split_by_status(data["raw_pre_findings"])
        charts = self._make_charts(pre, self.output_dir)
        score = self._calc_score(pre, post)
        report_id = self._make_report_id(scope["date"])

        # 3. LLM content (biến mới)
        llm = self._write_llm_sections(
            data, pre, post, env, scope, pass_findings, fail_findings
        )

        # 4. Enrich findings (COPY, không mutate gốc)
        #    RAG lookup: check_id → {title, severity, risk_summary}
        rag_finding_map = self._build_rag_finding_map(data.get("rag_context", {}))
        success = [self._enrich_success(f, rag_finding_map) for f in data["success_findings"]]
        failed = [self._enrich_failed(f, rag_finding_map) for f in data["failed_findings"]]
        manual = [self._enrich_manual(f, rag_finding_map) for f in data["manual_findings"]]

        # 5. Render
        template_ctx = {
            "env": env,
            "scope": scope,
            "pre": pre,
            "post": post,
            "score": score,
            "report_id": report_id,
            "charts": charts,
            "table": data["findings_table"],
            "success": success,
            "failed": failed,
            "manual": manual,
            "llm": llm,
        }
        return self._render(template_ctx)

    # ----------------------------------------------------------
    # VALIDATION
    # ----------------------------------------------------------
    def _validate_input(self, data: dict):
        required = [
            "pre", "post", "environment", "scope",
            "findings_table", "success_findings",
            "failed_findings", "manual_findings",
            "raw_pre_findings",
        ]
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"ReportAgent missing required keys: {missing}")

    # ----------------------------------------------------------
    # DERIVED DATA
    # ----------------------------------------------------------
    def _split_by_status(self, raw_findings: list):
        """Split raw pre-scan findings into pass/fail lists."""
        pass_list, fail_list = [], []
        for f in raw_findings:
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
        return pass_list, fail_list

    def _make_charts(self, pre: dict, output_dir: str) -> dict:
        """
        Chart và text đọc CÙNG 1 object `pre`.
        Không thể mâu thuẫn (fix BUG-01).
        """
        chart_dir = os.path.join(output_dir, "charts")
        os.makedirs(chart_dir, exist_ok=True)

        sev_path = os.path.join(chart_dir, "severity_bar.png")
        pie_path = os.path.join(chart_dir, "pass_fail_pie.png")

        make_severity_bar(pre["severity"], sev_path)
        make_pass_fail_pie(pre["pass"], pre["fail"], pie_path)

        return {
            "severity": "charts/severity_bar.png",
            "pass_fail": "charts/pass_fail_pie.png",
        }

    def _calc_score(self, pre: dict, post: dict) -> int:
        """Security score 0-100 based on pass ratio, severity, remediation rate."""
        total = post["final_pass"] + post["final_fail"]
        if total == 0:
            return 100

        pass_ratio = post["final_pass"] / total

        sev = pre["severity"]
        max_penalty = total * 10
        actual = (
            sev.get("critical", 0) * 10
            + sev.get("high", 0) * 5
            + sev.get("medium", 0) * 2
            + sev.get("low", 0) * 0.5
        )
        sev_score = 1 - (actual / max(max_penalty, 1))

        rem_rate = post["fixed"] / max(pre["fail"], 1)

        score = pass_ratio * 60 + sev_score * 30 + rem_rate * 10
        return round(min(max(score, 0), 100))

    def _make_report_id(self, date_str: str) -> str:
        clean = date_str.replace("-", "")
        return f"RPT-{clean}-{uuid4().hex[:4].upper()}"

    # ----------------------------------------------------------
    # LLM SECTIONS
    # ----------------------------------------------------------
    def _write_llm_sections(self, data, pre, post, env, scope,
                            pass_findings, fail_findings) -> dict:
        """Gọi LLM cho từng section. Mỗi call có fallback.
        RAG context được inject vào prompts nếu có."""

        # RAG knowledge (empty dict nếu RAG không khả dụng)
        rag = self._build_rag_knowledge(data.get("rag_context", {}))

        # Conditional bypass: không gọi LLM khi data trivial (fix BUG-04)
        if pre["pass"] == 0:
            pass_overview = (
                "Không ghi nhận cấu hình nào đạt chuẩn (PASS) trong phạm vi "
                "đánh giá này. Toàn bộ kiểm tra đều cho kết quả FAIL."
            )
        else:
            pass_overview = self.llm.write_pass_findings_overview(
                self._build_findings_ctx(pass_findings), rag_knowledge=rag
            )

        if pre["fail"] == 0:
            fail_overview = (
                "Toàn bộ các kiểm tra cấu hình đều đạt chuẩn. "
                "Không ghi nhận lỗi bảo mật trong phạm vi đánh giá."
            )
        else:
            fail_overview = self.llm.write_fail_findings_overview(
                self._build_findings_ctx(fail_findings), rag_knowledge=rag
            )

        system_data = self._build_system_data(env, scope)

        # Conditional bypass: all-pass scenario — no findings to analyze
        if pre["fail"] == 0 and post["fixed"] == 0 and post["failed"] == 0:
            exec_summary = (
                f"Đánh giá bảo mật đã được thực hiện trên tài khoản "
                f"{env.get('account_id', 'N/A')} vùng {env.get('region', 'N/A')}. "
                f"Tổng cộng {pre['total']} kiểm tra cấu hình trong phạm vi "
                f"{', '.join(s.upper() for s in scope.get('services', []))}. "
                f"Toàn bộ {pre['pass']} kiểm tra đều đạt chuẩn (PASS). "
                "Không phát hiện lỗi bảo mật nào cần khắc phục."
            )
            post_analysis = (
                "Không có hành động khắc phục nào được thực hiện do toàn bộ "
                "kiểm tra đều đạt chuẩn. Hệ thống duy trì trạng thái bảo mật tốt."
            )
            recommendations = (
                "Hệ thống hiện tại đạt chuẩn bảo mật. Khuyến nghị tiếp tục "
                "giám sát định kỳ và cập nhật cấu hình theo các tiêu chuẩn mới nhất."
            )
        else:
            exec_summary = self.llm.write_exec_summary(
                pre, system_data, scope, rag_knowledge=rag
            )
            post_analysis = self.llm.write_post_remediation_analysis(
                self._build_post_analysis_ctx(data, post)
            )
            recommendations = self.llm.write_post_remediation_recommendations(
                self._build_recommendation_ctx(data, post, pre),
                rag_knowledge=rag,
            )

        return {
            "executive_summary": exec_summary,
            "system_overview": self.llm.write_system_overview(system_data),
            "assessment_goals": self.llm.write_assessment_goals(
                scope.get("user_request", "")
            ),
            "pass_overview": pass_overview,
            "fail_overview": fail_overview,
            "post_analysis": post_analysis,
            "recommendations": recommendations,
        }

    # ----------------------------------------------------------
    # RAG KNOWLEDGE BUILDER
    # ----------------------------------------------------------
    def _build_rag_knowledge(self, rag_context: dict) -> str:
        """Format RAG report_bundle thành text block cho LLM prompt.
        Return empty string nếu không có RAG data."""
        if not rag_context:
            return ""

        parts = []

        # Key findings từ RAG knowledge base
        key_findings = rag_context.get("key_findings", [])
        if key_findings:
            lines = []
            for kf in key_findings[:10]:
                title = kf.get("title", "")
                severity = kf.get("severity", "")
                risk = kf.get("risk_summary", "")
                if title:
                    lines.append(f"- [{severity}] {title}: {risk}")
            if lines:
                parts.append(
                    "KIẾN THỨC BẢO MẬT TỪ CƠ SỞ DỮ LIỆU (RAG):\n"
                    + "\n".join(lines)
                )

        # Control themes / maturity capabilities
        themes = rag_context.get("control_themes", [])
        if themes:
            lines = []
            for t in themes[:5]:
                name = t.get("capability_name", "")
                summary = t.get("summary_short", "")
                if name:
                    lines.append(f"- {name}: {summary}")
            if lines:
                parts.append(
                    "CHỦ ĐỀ KIỂM SOÁT BẢO MẬT:\n"
                    + "\n".join(lines)
                )

        # Recommended practices
        practices = rag_context.get("recommended_practices", [])
        if practices:
            lines = [f"- {p}" for p in practices[:5] if p]
            if lines:
                parts.append(
                    "THỰC HÀNH KHUYẾN NGHỊ:\n"
                    + "\n".join(lines)
                )

        if not parts:
            return ""

        return "\n\n".join(parts)

    def _build_system_data(self, env, scope):
        return {
            "account_id": env["account_id"],
            "region": env["region"],
            "scan_scope": scope["services"],
            "date": scope["date"],
            "total_buckets": len(env.get("buckets", [])),
            "bucket_list": env.get("buckets", []),
        }

    def _build_findings_ctx(self, findings: list) -> dict:
        """Build LLM context for a group of findings (PASS or FAIL)."""
        by_sev, by_code = {}, {}
        for f in findings:
            s = (f.get("severity") or "").lower()
            by_sev[s] = by_sev.get(s, 0) + 1
            ec = f.get("event_code", "unknown")
            by_code[ec] = by_code.get(ec, 0) + 1
        return {
            "total": len(findings),
            "by_severity": by_sev,
            "by_event_code": by_code,
            "items": findings,
        }

    def _build_post_analysis_ctx(self, data, post):
        return {
            "post_summary": post,
            "fixed_findings": [
                {
                    "finding_id": f.get("finding_id"),
                    "description": f.get("description"),
                    "resource": f.get("resource"),
                    "action": f.get("action"),
                }
                for f in data["success_findings"]
            ],
            "manual_findings": [
                {
                    "finding_id": f.get("finding_id"),
                    "description": f.get("description"),
                    "manual_reason": f.get("manual_reason"),
                }
                for f in data["manual_findings"]
            ],
            "failed_findings": [
                {
                    "finding_id": f.get("finding_id"),
                    "description": f.get("description"),
                }
                for f in data["failed_findings"]
            ],
        }

    def _build_recommendation_ctx(self, _data, post, pre):
        return {
            "post_summary": post,
            "remediation_outcome": {
                "auto_fix_success": post["fixed"],
                "auto_fix_failed": post["failed"],
                "manual_required": post["manual"],
            },
            "severity_before": pre["severity"],
        }

    # ----------------------------------------------------------
    # RAG FINDING MAP
    # ----------------------------------------------------------
    def _build_rag_finding_map(self, rag_context: dict) -> dict:
        """Build check_id → RAG finding lookup."""
        result = {}
        for kf in rag_context.get("key_findings", []):
            cid = kf.get("check_id", "")
            if cid:
                result[cid] = kf
        return result

    # ----------------------------------------------------------
    # ENRICH FINDINGS (COPY — KHÔNG MUTATE GỐC)
    # ----------------------------------------------------------
    def _enrich_success(self, f: dict, rag_map: dict = None) -> dict:
        enriched = copy.deepcopy(f)
        enriched["execution_log"] = yaml.safe_dump(
            f.get("execution_output", {}), allow_unicode=True
        )
        # Fix BUG-02: fallback title khi action is None
        enriched["display_title"] = (
            f.get("action") or f.get("description") or "Remediation Action"
        )
        # RAG: inject official risk description nếu có
        rag_map = rag_map or {}
        check_id = f.get("event_code") or f.get("finding_id", "")
        rag_risk = rag_map.get(check_id, {}).get("risk_summary", "")

        enriched["llm_detail"] = self.llm.write_pass_remediation_detail(
            action=f.get("action") or "N/A",
            resource=f.get("resource") or "N/A",
            before=f.get("before", {}),
            after=f.get("after", {}),
            tool_code=f.get("tool_code"),
            tool_description=f.get("tool_description"),
            rag_risk=rag_risk,
        )
        return enriched

    def _enrich_failed(self, f: dict, rag_map: dict = None) -> dict:
        enriched = copy.deepcopy(f)
        enriched["execution_log"] = yaml.safe_dump(
            f.get("execution_output", {}), allow_unicode=True
        )
        enriched["display_title"] = (
            f.get("action") or f.get("description") or "Remediation Action"
        )

        rag_map = rag_map or {}
        check_id = f.get("event_code") or f.get("finding_id", "")
        rag_risk = rag_map.get(check_id, {}).get("risk_summary", "")

        enriched["llm_detail"] = self.llm.write_fail_remediation_detail(
            action=f.get("action") or "N/A",
            resource=f.get("resource") or "N/A",
            before=f.get("before", {}),
            after=f.get("after", {}),
            execution_status=f.get("execution_status"),
            execution_output=f.get("execution_output"),
            execution_error=(
                f.get("execution_error") or f.get("error") or f.get("exception")
            ),
            execution_timing=f.get("execution_timing"),
            tool_code=f.get("tool_code"),
            tool_description=f.get("tool_description"),
            rag_risk=rag_risk,
        )
        return enriched

    def _enrich_manual(self, f: dict, rag_map: dict = None) -> dict:
        enriched = copy.deepcopy(f)

        rag_map = rag_map or {}
        check_id = f.get("event_code") or f.get("finding_id", "")
        rag_finding = rag_map.get(check_id, {})

        enriched["llm_manual_guide"] = self.llm.write_manual_guide(
            f, rag_context=rag_finding
        )
        return enriched

    # ----------------------------------------------------------
    # RENDER
    # ----------------------------------------------------------
    def _render(self, ctx: dict) -> dict:
        from agents.report_module.template import REPORT_TEMPLATE

        md_path = self.output_path
        html_path = os.path.join(self.output_dir, "final_report.html")
        pdf_path = os.path.join(self.output_dir, "final_report.pdf")

        # Render full HTML template
        html = Template(REPORT_TEMPLATE).render(**ctx)
        write_file(html_path, html)

        # Markdown: giữ HTML cho Sprint 2, có thể dùng html2text sau
        write_file(md_path, html)

        # PDF export
        pdf_result = export_pdf(html, pdf_path)

        return {
            "markdown": md_path,
            "html": html_path,
            "pdf": pdf_path if pdf_result else None,
        }

    # ----------------------------------------------------------
    # METRICS (giữ nguyên interface cho orchestrator)
    # ----------------------------------------------------------
    def get_llm_metrics(self) -> Dict[str, Any]:
        return {
            "total_latency": round(self.timer.total_duration, 4),
            "call_history": [round(t, 4) for t in self.timer.call_history],
            "call_count": len(self.timer.call_history),
        }
