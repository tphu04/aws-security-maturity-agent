# ------------------------------------------------------------
# REPORT_AGENT.PY — Rebuilt (Sprint 2 + Hotfix)
# Clean architecture: validate → derive → LLM → enrich → render
# Input data is READ-ONLY (deep copy in enrich, không mutate)
# ------------------------------------------------------------
import copy
import json
import logging
import os
import time
import yaml

logger = logging.getLogger(__name__)
from uuid import uuid4
from typing import Dict, Any, Optional

from jinja2 import Template
from pdca.agents.report_module.llm_writer import LLMWriter
from pdca.agents.report_module.exporters import write_file, export_pdf
from pdca.agents.report_module.chart_util import (
    make_pass_fail_pie, make_severity_bar,
    make_domain_radar, make_stage_progress, make_maturity_delta_chart,
)
from pdca.agents.report_module.scope_detector import (
    detect_scope, is_valid_resource,
)
from pdca.agents.report_module.rag_formatter import RAGViewFormatter
from pdca.agents.report_module.validators import (
    ReportValidator, build_evidence, ValidationIssue,
)

# Mode selection thresholds (percentage-based for service-scoped assessment)
FULL_MIN_DOMAINS = 3
FULL_MIN_COVERAGE_PCT = 60.0   # >=60% of scoped capabilities assessed
PARTIAL_MIN_COVERAGE_PCT = 20.0  # >=20% of scoped capabilities assessed
PARTIAL_MIN_CAPABILITIES = 3


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
                 llm_config: Optional[Dict[str, Any]] = None,
                 callbacks: Optional[list] = None):
        self.timer = ReportTimer()
        # Phase B10: callbacks (Langfuse handler) propagate xuống LLMWriter
        # → ChatOllama. Mặc định [] khi caller không truyền.
        self.callbacks = list(callbacks or [])
        # Populated by ``_write_llm_sections`` so ``_render`` can emit
        # ``validation_report.json`` next to the HTML output. Reset on
        # every ``run()`` call.
        self._validation_issues: list[ValidationIssue] = []
        self._validation_sections_run: list[str] = []

        # LLM setup (injectable for testing)
        llm_instance = self._create_llm(model, api_key, base_url, llm_config)
        self.llm = LLMTimerProxy(
            LLMWriter(llm=llm_instance, callbacks=self.callbacks),
            self.timer,
        )

        # Output paths
        self.output_path = output_path or "reports/final_report.md"
        self.output_dir = os.path.dirname(self.output_path)
        os.makedirs(self.output_dir, exist_ok=True)

    # ----------------------------------------------------------
    # LLM FACTORY
    # ----------------------------------------------------------
    def _create_llm(self, model, api_key, base_url, llm_config):
        """Support injecting LLM instance or auto-create Ollama.

        Phase B10: nếu auto-create, propagate self.callbacks xuống ChatOllama.
        api_key kept for backward compat with orchestrator constructor call.
        """
        _ = api_key  # reserved for future OpenAI/Claude backends
        if llm_config and "llm" in llm_config:
            return llm_config["llm"]

        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model or "gemma3:4b",
            base_url=base_url,
            temperature=0.5,
            callbacks=self.callbacks,
        )

    # ----------------------------------------------------------
    # MAIN — ~30 lines, chỉ điều phối
    # ----------------------------------------------------------
    def run(self, data: dict = None, report_context: dict = None,
            **_kwargs) -> dict:
        """Thin orchestration: normalize input → build template ctx → render.

        INPUT:  data (từ ReportDataBuilder.build) — đầy đủ, read-only
        OUTPUT: {"markdown": path, "html": path, "pdf": path}

        Backward compat: accepts `report_context=` kwarg from old
        orchestrator interface.
        """
        data = self._normalize_input(data, report_context)
        self._validate_input(data)
        self._reset_validation_state()
        template_ctx = self._build_template_context(data)
        return self._render(template_ctx)

    # ----------------------------------------------------------
    # INPUT NORMALIZATION
    # ----------------------------------------------------------
    @staticmethod
    def _normalize_input(data: Optional[dict],
                         report_context: Optional[dict]) -> dict:
        if data is not None:
            return data
        if report_context is None:
            raise ValueError("Missing data or report_context")
        return report_context

    def _reset_validation_state(self) -> None:
        # Reset per-run so a prior job doesn't leak issues into next render.
        self._validation_issues = []
        self._validation_sections_run = []

    # ----------------------------------------------------------
    # TEMPLATE CONTEXT BUILDER
    # ----------------------------------------------------------
    def _build_template_context(self, data: dict) -> dict:
        """Compose tất cả derived data + LLM content + enriched findings
        thành template_ctx cho `_render()`.

        Phase B10 review: extract khỏi `run()` để giữ run() thuần
        orchestration. Mọi side effect (LLM, chart) gom ở đây để render
        path không bao giờ trigger LLM call.
        """
        pre = data["pre"]
        post = data["post"]
        env = data["environment"]
        scope = data["scope"]

        # Scope: prefer pre-computed (orchestrator/builder), else derive
        # tại chỗ để agent vẫn callable trong unit test isolation.
        scope_info = data.get("scope_info") or detect_scope(
            findings=data.get("raw_pre_findings") or [],
            env=env,
            services_hint=scope.get("services") if isinstance(scope, dict) else None,
        )

        # RAG context: ReportAgent KHÔNG fetch (Phase B12 fix). Caller
        # phải pre-compute qua ReportDataBuilder.build() và truyền vào
        # `data["rag_context"]`. Empty dict = LLM-pure path.
        rag_ctx = data.get("rag_context") or {}
        data = {**data, "rag_context": rag_ctx}

        maturity = data.get("maturity_assessment")
        maturity_delta = data.get("maturity_delta")
        report_mode = self._determine_report_mode(maturity)

        # Derived data + charts
        pass_findings, fail_findings = self._split_by_status(data["raw_pre_findings"])
        charts = self._make_charts(pre, self.output_dir)

        maturity_charts: dict = {}
        if maturity and report_mode in ("full", "partial"):
            maturity_charts = self._make_maturity_charts(
                maturity, report_mode, self.output_dir,
            )
        if maturity_delta and report_mode in ("full", "partial"):
            maturity_charts.update(
                self._make_post_remediation_charts(maturity_delta, self.output_dir)
            )

        # Score: maturity-based khi có, fallback sang pass/fail percent
        if maturity and report_mode in ("full", "partial"):
            score = round(maturity["overall_score"])
        else:
            score = self._calc_score(pre, post)

        fix_metrics = self._compute_fix_metrics(data)
        residual_risks = self._classify_residual_risks(data)
        report_id = self._make_report_id(scope["date"])

        # LLM content (3 groups: pre-remediation, maturity, post-remediation)
        llm = self._write_llm_sections(
            data, pre, post, env, scope, pass_findings, fail_findings,
            scope_info=scope_info,
        )
        if maturity and report_mode in ("full", "partial"):
            llm.update(self._write_maturity_llm_sections(maturity, report_mode))
        llm.update(self._write_post_remediation_llm_sections(
            fix_metrics, residual_risks, maturity_delta, report_mode,
        ))

        # Enrich findings (immutable copies)
        rag_finding_map = self._build_rag_finding_map(rag_ctx)
        success = [self._enrich_success(f, rag_finding_map)
                   for f in data["success_findings"]]
        failed = [self._enrich_failed(f, rag_finding_map)
                  for f in data["failed_findings"]]
        manual = [self._enrich_manual(f, rag_finding_map)
                  for f in data["manual_findings"]]

        return {
            "env": env, "scope": scope, "scope_info": scope_info,
            "pre": pre, "post": post,
            "score": score, "report_id": report_id,
            "charts": charts, "table": data["findings_table"],
            "unchanged_count": sum(
                1 for r in data["findings_table"] if r["change"] == "Unchanged"
            ),
            "success": success, "failed": failed, "manual": manual,
            "llm": llm,
            "maturity": maturity,
            "maturity_post": data.get("maturity_post"),
            "maturity_delta": maturity_delta,
            "maturity_charts": maturity_charts,
            "report_mode": report_mode,
            "fix_metrics": fix_metrics,
            "residual_risks": residual_risks,
        }

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
    # MODE SELECTION (Phase 5 — Task 5.1)
    # ----------------------------------------------------------
    def _determine_report_mode(self, maturity: dict | None) -> str:
        """Determine report mode based on maturity coverage.

        Uses percentage-based thresholds relative to scoped capabilities
        (service-scoped) instead of fixed absolute numbers.
        """
        if maturity is None:
            return "focused"

        coverage = maturity.get("coverage", {})
        assessed = coverage.get("assessed", 0) + coverage.get("partial", 0)
        coverage_pct = coverage.get("mapping_coverage_pct", 0.0)

        domains_with_data = sum(
            1 for d in maturity.get("domains", {}).values()
            if any(c["status"] in ("assessed", "partial")
                   for c in d.get("capabilities", []))
        )

        if (domains_with_data >= FULL_MIN_DOMAINS
                and coverage_pct >= FULL_MIN_COVERAGE_PCT):
            return "full"
        elif (domains_with_data >= 1
              and coverage_pct >= PARTIAL_MIN_COVERAGE_PCT
              and assessed >= PARTIAL_MIN_CAPABILITIES):
            return "partial"
        else:
            return "focused"

    # ----------------------------------------------------------
    # FIX METRICS & RESIDUAL RISKS (Phase 5 — Task 5.2)
    # ----------------------------------------------------------
    def _compute_fix_metrics(self, data: dict) -> dict:
        """Compute remediation effectiveness metrics."""
        pre = data["pre"]
        post = data["post"]

        total_findings = pre["total"]
        total_fail = pre["fail"]
        fixed = post["fixed"]
        failed_fix = post["failed"]
        manual = post["manual"]

        fix_rate = (fixed / total_fail * 100) if total_fail > 0 else 0.0
        auto_attempts = fixed + failed_fix
        auto_success_rate = (fixed / auto_attempts * 100) if auto_attempts > 0 else 0.0

        residual_fail = post["final_fail"]
        residual_rate = (residual_fail / total_findings * 100) if total_findings > 0 else 0.0

        pre_pass_rate = (pre["pass"] / pre["total"] * 100) if pre["total"] > 0 else 0.0
        post_pass_rate = (post["final_pass"] / pre["total"] * 100) if pre["total"] > 0 else 0.0

        return {
            "total_findings": total_findings,
            "total_fail_pre": total_fail,
            "fixed": fixed,
            "failed_fix": failed_fix,
            "manual": manual,
            "fix_rate_pct": round(fix_rate, 1),
            "auto_success_rate_pct": round(auto_success_rate, 1),
            "residual_fail": residual_fail,
            "residual_rate_pct": round(residual_rate, 1),
            "pre_pass_rate_pct": round(pre_pass_rate, 1),
            "post_pass_rate_pct": round(post_pass_rate, 1),
            "pass_rate_delta": round(post_pass_rate - pre_pass_rate, 1),
        }

    def _classify_residual_risks(self, data: dict) -> dict:
        """Classify findings still FAIL after remediation."""
        residual = {
            "auto_fix_failed": [],
            "manual_required": [],
            "unchanged": [],
        }

        for finding in data.get("findings_table", []):
            if finding.get("after") != "FAIL":
                continue
            entry = {
                "check_id": finding.get("check_id", ""),
                "finding": finding.get("finding", ""),
                "service": finding.get("service", ""),
                "severity": finding.get("severity", ""),
                "resource": finding.get("resource", ""),
                "change": finding.get("change", ""),
            }
            change = finding.get("change", "")
            if "RemediationFailed" in change:
                residual["auto_fix_failed"].append(entry)
            elif "ManualRequired" in change:
                residual["manual_required"].append(entry)
            else:
                residual["unchanged"].append(entry)

        residual["severity_breakdown"] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for category in ["auto_fix_failed", "manual_required", "unchanged"]:
            for item in residual[category]:
                sev = item["severity"].lower()
                if sev in residual["severity_breakdown"]:
                    residual["severity_breakdown"][sev] += 1

        residual["total"] = sum(len(v) for k, v in residual.items() if isinstance(v, list))
        return residual

    # ----------------------------------------------------------
    # MATURITY CHARTS (Phase 5 — Task 5.3)
    # ----------------------------------------------------------
    def _make_maturity_charts(self, maturity, report_mode, output_dir):
        """Generate maturity assessment charts."""
        chart_dir = os.path.join(output_dir, "charts")
        os.makedirs(chart_dir, exist_ok=True)
        result = {}

        domain_scores = {
            d["display_name"]: d["score"]
            for d in maturity["domains"].values()
        }

        if report_mode == "full":
            radar_path = os.path.join(chart_dir, "maturity_radar.png")
            make_domain_radar(domain_scores, radar_path)
            result["radar"] = "charts/maturity_radar.png"

        stage_path = os.path.join(chart_dir, "stage_progress.png")
        make_stage_progress(maturity, stage_path)
        result["stage_progress"] = "charts/stage_progress.png"

        return result

    def _make_post_remediation_charts(self, maturity_delta, output_dir):
        """Generate maturity delta chart — skipped when overall delta is zero
        (chart adds no information in that case).
        """
        if not maturity_delta:
            return {}
        overall = maturity_delta.get("overall") or {}
        if overall.get("score_delta", 0) == 0:
            return {}

        chart_dir = os.path.join(output_dir, "charts")
        os.makedirs(chart_dir, exist_ok=True)

        delta_path = os.path.join(chart_dir, "maturity_delta.png")
        make_maturity_delta_chart(maturity_delta, delta_path)
        return {"maturity_delta": "charts/maturity_delta.png"}

    # ----------------------------------------------------------
    # MATURITY LLM SECTIONS (Phase 5 — Task 5.4)
    # ----------------------------------------------------------
    def _write_maturity_llm_sections(self, maturity, report_mode):
        """Generate LLM narrative sections for maturity assessment."""
        sections = {}

        sections["maturity_overview"] = self.llm.write_maturity_overview(maturity)

        sections["domain_assessments"] = {}
        for domain_id, ddata in maturity["domains"].items():
            if report_mode == "partial":
                has_data = any(
                    c["status"] in ("assessed", "partial")
                    for c in ddata.get("capabilities", [])
                )
                if not has_data:
                    continue
            sections["domain_assessments"][domain_id] = (
                self.llm.write_domain_assessment(ddata["display_name"], ddata)
            )

        sections["maturity_roadmap"] = self.llm.write_maturity_roadmap(maturity)
        return sections

    def _write_post_remediation_llm_sections(self, fix_metrics, residual_risks,
                                              maturity_delta, report_mode):
        """Generate LLM narrative sections for post-remediation analysis."""
        sections = {}

        sections["post_remediation_analysis"] = self.llm.write_post_remediation_analysis_v2(
            fix_metrics=fix_metrics,
            residual_risks=residual_risks,
            maturity_delta=maturity_delta,
            report_mode=report_mode,
        )

        sections["action_plan"] = self.llm.write_action_plan(
            residual_risks=residual_risks,
            maturity_delta=maturity_delta,
        )

        return sections

    # ----------------------------------------------------------
    # VALIDATION (Phase 5)
    # ----------------------------------------------------------
    def _build_validator(self, *, pre, post, env, scope_info, rag_context,
                          raw_findings) -> ReportValidator:
        """Construct the :class:`ReportValidator` used to gate LLM
        sections before render. Evidence is assembled by
        :func:`build_evidence` from the already-validated input data.
        """
        evidence = build_evidence(
            findings=raw_findings,
            pre=pre,
            post=post,
            scope=scope_info,
            env=env,
            rag_context=rag_context or {},
        )
        return ReportValidator(scope=scope_info, evidence=evidence)

    def _validate_section(self, section: str, text: str,
                           validator: ReportValidator,
                           fallback: str = "") -> str:
        """Validate a single section's text. When the validator flags
        issues, record them and fall back to ``fallback`` — keeps the
        rendered report grounded even if the LLM went off the rails.

        Empty / None text passes through unchanged (nothing to gate).
        """
        if not text or not text.strip():
            return text
        self._validation_sections_run.append(section)
        result = validator.validate(text, section)
        if result.ok:
            return text
        self._validation_issues.extend(result.issues)
        logger.warning(
            "[ReportValidator] section=%s rejected: %s",
            section,
            [(i.kind, i.evidence) for i in result.issues[:5]],
        )
        return fallback if fallback else text

    def _validate_sections_pre_render(self, sections: dict,
                                       validator: ReportValidator,
                                       fallbacks: dict) -> dict:
        """Run validator on each LLM section in ``sections``. Sections
        that fail validation are replaced with ``fallbacks[section]``.
        """
        if validator is None:
            return sections
        gated: dict = {}
        for name, text in sections.items():
            gated[name] = self._validate_section(
                name, text, validator,
                fallback=fallbacks.get(name, ""),
            )
        return gated

    # ----------------------------------------------------------
    # LLM SECTIONS
    # ----------------------------------------------------------
    def _write_llm_sections(self, data, pre, post, env, scope,
                            pass_findings, fail_findings,
                            scope_info: Optional[Dict[str, Any]] = None) -> dict:
        """Gọi LLM cho từng section. Mỗi call có fallback.
        RAG context được inject vào prompts nếu có."""

        # Defensive default: unit tests may call this helper directly
        # without a pre-computed scope.
        if scope_info is None:
            scope_info = detect_scope(
                findings=data.get("raw_pre_findings") or [],
                env=env,
                services_hint=scope.get("services") if isinstance(scope, dict) else None,
            )

        # Sort fail_findings by severity so LLM and RAG formatter both see
        # critical → high → medium → low order. Fixes ndcg@5 worst case where
        # reversed input produced a severity-order score of 0.7489.
        _SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        fail_findings = sorted(
            fail_findings or [],
            key=lambda f: _SEV_RANK.get(
                (f.get("severity") or "").strip().lower(), 4
            ),
        )

        # RAG view formatter — one instance, four per-section views. The
        # formatter handles the empty-context case internally (every view
        # returns "" when there is no data).
        rag_context = data.get("rag_context", {}) or {}
        rag_views = RAGViewFormatter(rag_context, scope_info)
        rag_exec = rag_views.for_executive()
        rag_sys  = rag_views.for_system_overview()
        rag_pass = rag_views.for_pass_analysis()
        rag_fail = rag_views.for_fail_analysis()
        rag_reco = rag_views.for_recommendations()
        # Legacy flat blob — kept for LLM writers that have not been
        # migrated to a dedicated view yet (manual guide, pass/fail
        # remediation details fetched per finding via ``for_per_finding``).
        rag = self._build_rag_knowledge(rag_context)

        # Conditional bypass: không gọi LLM khi data trivial (fix BUG-04)
        if pre["pass"] == 0:
            pass_overview = (
                "Không ghi nhận cấu hình nào đạt chuẩn (PASS) trong phạm vi "
                "đánh giá này. Toàn bộ kiểm tra đều cho kết quả FAIL."
            )
        else:
            pass_overview = self.llm.write_pass_findings_overview(
                self._build_findings_ctx(pass_findings), rag_knowledge=rag_pass
            )

        if pre["fail"] == 0:
            fail_overview = (
                "Toàn bộ các kiểm tra cấu hình đều đạt chuẩn. "
                "Không ghi nhận lỗi bảo mật trong phạm vi đánh giá."
            )
        else:
            fail_overview = self.llm.write_fail_findings_overview(
                self._build_findings_ctx(fail_findings), rag_knowledge=rag_fail
            )

        # Pass ALL findings (pass+fail simplified copies) so resource count
        # can fall back to distinct resources when env.buckets is empty.
        system_data = self._build_system_data(
            env, scope, scope_info,
            findings=(pass_findings or []) + (fail_findings or []),
        )

        # Conditional bypass: all-pass scenario — no findings to analyze
        if pre["fail"] == 0 and post["fixed"] == 0 and post["failed"] == 0:
            service_summary = ", ".join(
                s.upper() for s in (scope.get("services") or [])
            ) or scope_info.get("service_display", "AWS Infrastructure")
            exec_summary = (
                f"Đánh giá bảo mật đã được thực hiện trên tài khoản "
                f"{env.get('account_id', 'N/A')} vùng {env.get('region', 'N/A')}. "
                f"Tổng cộng {pre['total']} kiểm tra cấu hình trong phạm vi "
                f"{service_summary}. "
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
                pre, system_data, scope, scope_info=scope_info,
                rag_knowledge=rag_exec,
                fail_findings=fail_findings,
            )
            post_analysis = self.llm.write_post_remediation_analysis(
                self._build_post_analysis_ctx(data, post)
            )
            # Collect names of capabilities still failing (post-remediation)
            # so the prompt can anchor recommendations on real gaps, not
            # on capabilities already passing.
            failing_caps = self._collect_failing_capability_names(data)
            recommendations = self.llm.write_post_remediation_recommendations(
                self._build_recommendation_ctx(data, post, pre),
                rag_knowledge=rag_reco,
                failing_capabilities=failing_caps,
            )

        sections = {
            "executive_summary": exec_summary,
            "system_overview": self.llm.write_system_overview(
                system_data, scope_info=scope_info, rag_knowledge=rag_sys,
            ),
            "assessment_goals": self.llm.write_assessment_goals(
                scope.get("user_request", "")
            ),
            "pass_overview": pass_overview,
            "fail_overview": fail_overview,
            "post_analysis": post_analysis,
            "recommendations": recommendations,
        }

        # Phase 5 — Output Validation Gate.
        # Validator runs on every LLM-authored section; sections that
        # violate scope/fact/grounding rules fall back to the deterministic
        # template strings defined above, so the rendered HTML is always
        # grounded even if the LLM drifts.
        raw_findings = (
            (data.get("raw_pre_findings") or [])
            + (pass_findings or []) + (fail_findings or [])
        )
        validator = self._build_validator(
            pre=pre, post=post, env=env, scope_info=scope_info,
            rag_context=rag_context,
            raw_findings=raw_findings,
        )
        fallbacks = self._make_section_fallbacks(
            pre=pre, post=post, scope_info=scope_info,
        )
        gated = self._validate_sections_pre_render(sections, validator, fallbacks)
        return gated

    # Deterministic per-section fallbacks used when the validator
    # rejects a piece of LLM output. Keep them short, factual, and
    # free of any service-specific wording so they never themselves
    # trigger the validator on re-run.
    def _make_section_fallbacks(self, *, pre, post, scope_info) -> dict:
        service = scope_info.get("service_display", "AWS Infrastructure")
        term_p = scope_info.get("resource_term_plural", "resources")
        total = pre.get("total", 0)
        fail = pre.get("fail", 0)
        passed = pre.get("pass", 0)
        return {
            "executive_summary": (
                f"<p>Đánh giá bảo mật {service} đã hoàn tất với "
                f"{total} findings ({passed} PASS, {fail} FAIL). "
                "Chi tiết xem phần bên dưới.</p>"
            ),
            "system_overview": (
                f"<p>Hệ thống gồm các {term_p} trong phạm vi {service}.</p>"
            ),
            "assessment_goals": (
                "<p>Mục tiêu: rà soát tư thế bảo mật, phát hiện cấu hình "
                "không đạt chuẩn và đề xuất khắc phục.</p>"
            ),
            "pass_overview": (
                f"<p>Có {passed} cấu hình đạt chuẩn. Chi tiết ở bảng findings.</p>"
            ),
            "fail_overview": (
                f"<p>Có {fail} cấu hình không đạt chuẩn. Chi tiết ở bảng findings.</p>"
            ),
            "post_analysis": (
                "<p>Kết quả khắc phục đã được ghi nhận. "
                "Chi tiết các số liệu xem bảng ở phần trên.</p>"
            ),
            "recommendations": (
                "<p>Khuyến nghị chi tiết dựa trên findings và mức độ nghiêm trọng "
                "đã được liệt kê trong bảng khắc phục.</p>"
            ),
        }

    @staticmethod
    def _collect_failing_capability_names(data: dict) -> list[str]:
        """Return the display names of capabilities that are still FAIL
        after remediation. Prefers POST maturity (ground truth for current
        state); falls back to residual finding list.
        """
        names: list[str] = []
        post_maturity = data.get("maturity_post") or data.get("maturity_assessment")
        if post_maturity:
            for d_info in post_maturity.get("domains", {}).values():
                for c in d_info.get("capabilities", []):
                    if c.get("fail_count", 0) > 0:
                        n = c.get("capability_name")
                        if n and n not in names:
                            names.append(n)
        if not names:
            # Fallback: unique finding titles from failed/manual groups
            seen = set()
            for group in ("failed_findings", "manual_findings"):
                for f in data.get(group, []) or []:
                    title = f.get("description") or f.get("finding", "")
                    title = title.strip()
                    if title and title not in seen:
                        seen.add(title)
                        names.append(title)
        return names[:12]

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
                severity = (kf.get("severity", "") or "N/A").upper()
                risk = kf.get("risk_summary", "")
                if title:
                    # Use parens (not brackets): `_clean` in LLMWriter strips
                    # anything inside [...] as a stray placeholder, which
                    # silently ate the severity label in previous revisions.
                    lines.append(f"- ({severity}) {title}: {risk}")
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

    def _build_system_data(self, env, scope, scope_info: Dict[str, Any],
                           findings=None):
        """Build context for system overview prompts (scope-aware).

        Resource counting is service-aware: for S3 scopes the count is
        the number of distinct buckets in the findings (or ``env.buckets``
        when populated), for other services it is the number of distinct
        resources of that service type.

        Account-level Prowler checks (e.g. ``*_account_level_*``) carry the
        account ID in ``resource`` — ``is_valid_resource`` drops those so
        they are not counted as real resources.
        """
        account_id = str(env.get("account_id", "")).strip()
        primary_service = scope_info.get("primary_service")

        # Env may list resources under a service-specific key (``buckets`` is
        # the only one the current EnvironmentAgent populates). Fall back to
        # that S3 key when the scope is S3 so historical data still works.
        env_resources: list = []
        if primary_service == "s3":
            env_resources = env.get("buckets") or []
        else:
            # Convention for future env agents: ``resources`` is a generic
            # list; service-prefixed keys (e.g. ``iam_entities``) win when set.
            svc_key = f"{primary_service}s" if primary_service else None
            if svc_key and env.get(svc_key):
                env_resources = env.get(svc_key) or []
            else:
                env_resources = env.get("resources") or []

        distinct_resources: set[str] = set()
        if findings:
            for f in findings:
                res = f.get("resource") or f.get("resource_id")
                finding_service = (
                    (f.get("service") or primary_service or "").lower()
                    or None
                )
                if is_valid_resource(res, finding_service, account_id):
                    distinct_resources.add(res)

        if env_resources:
            total_resources = len(env_resources)
            resource_list = list(env_resources)
            source = "env"
        elif distinct_resources:
            total_resources = len(distinct_resources)
            resource_list = sorted(distinct_resources)
            source = "findings"
        else:
            total_resources = 0
            resource_list = []
            source = "none"

        return {
            "account_id": env["account_id"],
            "region": env["region"],
            "scan_scope": scope["services"],
            "date": scope["date"],
            # Scope-aware fields (new canonical names):
            "primary_service": primary_service,
            "service_display": scope_info.get("service_display"),
            "is_multi_service": scope_info.get("is_multi_service", False),
            "resource_term": scope_info.get("resource_term"),
            "resource_term_plural": scope_info.get("resource_term_plural"),
            "total_resources": total_resources,
            "resource_list": resource_list,
            "resource_count_source": source,
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
        from pdca.agents.report_module.template import REPORT_TEMPLATE

        md_path = self.output_path
        html_path = os.path.join(self.output_dir, "final_report.html")
        pdf_path = os.path.join(self.output_dir, "final_report.pdf")
        validation_path = os.path.join(self.output_dir, "validation_report.json")

        # Render full HTML template
        html = Template(REPORT_TEMPLATE).render(**ctx)
        write_file(html_path, html)

        # Markdown: giữ HTML cho Sprint 2, có thể dùng html2text sau
        write_file(md_path, html)

        # PDF export
        pdf_result = export_pdf(html, pdf_path)

        # Phase 5 — dump validation report alongside the rendered output.
        # Always written (even when zero issues) so downstream tooling
        # can rely on the file existing for every job.
        self._write_validation_report(validation_path)

        return {
            "markdown": md_path,
            "html": html_path,
            "pdf": pdf_path if pdf_result else None,
            "validation_report": validation_path,
        }

    def _write_validation_report(self, path: str) -> None:
        """Persist the list of ValidationIssues encountered during the
        current run. Format is stable so thesis tooling can diff
        before/after runs.
        """
        issues = [i.to_dict() for i in self._validation_issues]
        summary: dict = {}
        for i in self._validation_issues:
            summary[i.kind] = summary.get(i.kind, 0) + 1
        payload = {
            "sections_validated": list(self._validation_sections_run),
            "issue_count": len(issues),
            "summary": summary,
            "issues": issues,
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.warning("Failed to write validation report to %s: %s", path, e)

    # ----------------------------------------------------------
    # METRICS (giữ nguyên interface cho orchestrator)
    # ----------------------------------------------------------
    def get_llm_metrics(self) -> Dict[str, Any]:
        return {
            "total_latency": round(self.timer.total_duration, 4),
            "call_history": [round(t, 4) for t in self.timer.call_history],
            "call_count": len(self.timer.call_history),
        }
