"""ReportDataBuilder — orchestrate report context (Phase B12).

Responsibilities:
- Build report-shaped context dict từ analysis + aws + plan + user_request
  (move từ orchestrator.build_report_data + _extract_post_findings).
- Fetch RAG bundle qua `RAGQueryPlanner` (single source of truth cho retrieval
  — không duplicate logic gọi RAG client).
- Graceful degradation: rag_client = None / RAG fail → trả `{}` cho rag_context.

Phân chia trách nhiệm:
- `RAGQueryPlanner`: thuần fetch (đã có sẵn — gọi RAGClient, normalize bundle).
- `ReportDataBuilder` (file này): chọn path multi/legacy, gọi planner, ghép
  vào context dict, xử lý exception.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pdca.agents.report_module.rag_query_planner import RAGQueryPlanner
from pdca.agents.report_module.scope_detector import detect_scope
from pdca.config import settings
from pdca.observability.logger import get_logger

logger = get_logger(__name__)


class ReportDataBuilder:
    """Orchestrate context building cho ReportAgent."""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    @classmethod
    def build(
        cls,
        state_data: Dict[str, Any],
        rag_client: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Build full report context dict from state-shaped input.

        Args:
            state_data: dict với các keys:
                - analysis_results (dict | None)  — từ verification_node
                - raw_findings (list)             — fallback khi không có analysis
                - aws_context (dict)
                - assessment_plan (dict)
                - user_request (str)
            rag_client: optional `RAGClient` instance. None → skip RAG fetch.

        Returns:
            dict ready cho `ReportAgent.run(data=...)`.
        """
        analysis = state_data.get("analysis_results") or cls._fallback_analysis(
            state_data.get("raw_findings", []) or []
        )

        ctx = cls.build_context(
            analysis=analysis,
            aws_context=state_data.get("aws_context") or {},
            plan=state_data.get("assessment_plan") or {},
            user_request=state_data.get("user_request", ""),
        )

        scope_info = detect_scope(
            findings=ctx.get("raw_pre_findings", []),
            env=ctx.get("environment"),
            services_hint=ctx.get("scope", {}).get("services"),
        )
        ctx["scope_info"] = scope_info

        ctx["rag_context"] = cls._fetch_rag(
            rag_client=rag_client,
            findings=ctx.get("raw_pre_findings", []),
            scope_info=scope_info,
        )
        return ctx

    # ------------------------------------------------------------------
    # Context shaping (moved from orchestrator)
    # ------------------------------------------------------------------
    @classmethod
    def build_context(
        cls,
        analysis: dict,
        aws_context: dict,
        plan: dict,
        user_request: str,
    ) -> Dict[str, Any]:
        """Pure function — không side effect, không truy cập file/RAG.

        Maps:
        - analysis  → pre/post stats, findings, table
        - aws_context → environment info (account, region, buckets)
        - plan → scan scope (target services)
        - user_request → scope context
        """
        pre = analysis.get("pre_stats", {})
        post_stats = analysis.get("post_stats", {})
        rem = analysis.get("remediation_stats", {})

        # Resolve scope services with explicit fallback chain (review fix).
        # Plans coming từ PlanningAgent có cả `target_services` (alias mới) và
        # `groups_to_scan` (legacy). Plans được persist qua `save_scan_config`
        # → JSON chỉ có `groups_to_scan` (xem orchestrator.save_scan_config).
        # Trước đây fallback `plan.get("target_services", ["s3"])` silent default
        # về S3 khi caller truyền plan kiểu legacy → report scope bị sai. Pattern
        # này khớp với `rescan_agent.run()` (cùng file `initial_scan_config.json`).
        # Empty list = planning lỗi/no-op → giữ nguyên empty (không silent default).
        services = plan.get("target_services")
        if services is None:
            services = plan.get("groups_to_scan")
        if services is None:
            services = ["s3"]

        return {
            "pre": {
                "total": pre.get("total", 0),
                "pass": pre.get("pass", 0),
                "fail": pre.get("fail", 0),
                "severity": pre.get(
                    "severity",
                    {"critical": 0, "high": 0, "medium": 0, "low": 0},
                ),
            },
            "post": {
                "initial_pass": pre.get("pass", 0),
                "initial_fail": pre.get("fail", 0),
                "final_pass": post_stats.get("pass", 0),
                "final_fail": post_stats.get("fail", 0),
                "fixed": rem.get("fixed", 0),
                "failed": rem.get("failed", 0),
                "manual": rem.get("manual", 0),
            },
            "findings_table": analysis.get("findings_table", []),
            "success_findings": analysis.get("success_findings", []),
            "failed_findings": analysis.get("failed_findings", []),
            "manual_findings": analysis.get("manual_findings", []),
            "raw_pre_findings": analysis.get("raw_pre_findings", []),
            "raw_post_findings": cls._extract_post_findings(analysis),
            "environment": {
                "account_id": aws_context.get("account_id", "Unknown"),
                "region": aws_context.get("region", "us-east-1"),
                "buckets": aws_context.get("buckets", []),
            },
            "scope": {
                "services": services,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "user_request": user_request,
            },
        }

    @staticmethod
    def _extract_post_findings(analysis: dict) -> List[Dict[str, Any]]:
        """Tạo post-scan findings list từ findings_table."""
        post_findings = []
        for row in analysis.get("findings_table", []):
            post_findings.append({
                "event_code": row.get("check_id", ""),
                "status": row.get("after", "UNKNOWN"),
                "severity": row.get("severity", ""),
                "resource_id": row.get("resource", ""),
                "service": row.get("service", ""),
                "change": row.get("change", ""),
            })
        return post_findings

    # ------------------------------------------------------------------
    # RAG fetch — delegate to RAGQueryPlanner, no duplicate fetch logic
    # ------------------------------------------------------------------
    @staticmethod
    def _fetch_rag(
        rag_client: Optional[Any],
        findings: List[Dict[str, Any]],
        scope_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Choose multi/legacy path, delegate fetch to RAGQueryPlanner.

        Trả `{}` khi rag_client = None hoặc bất kỳ exception nào — caller
        (report layer) đã handle empty rag_context (LLM thuần).
        """
        if rag_client is None:
            logger.info("ReportDataBuilder: rag_client=None — skip RAG fetch")
            return {}

        try:
            planner = RAGQueryPlanner(rag_client)
            if settings.multi_query_mode:
                logger.info("ReportDataBuilder: RAG mode = MULTI_QUERY")
                req = planner.plan(findings, scope_info.get("service_list", []))
                return planner.execute(req) or {}
            else:
                logger.info("ReportDataBuilder: RAG mode = LEGACY")
                check_ids = planner._dedup_check_ids(findings)
                return planner.execute_legacy(check_ids) or {}
        except Exception as e:
            logger.warning("ReportDataBuilder: RAG fetch failed, degrading",
                           extra={"error_type": type(e).__name__, "error": str(e)})
            return {}

    # ------------------------------------------------------------------
    # Fallback analysis (no-FAIL → skip verification path)
    # ------------------------------------------------------------------
    @staticmethod
    def _fallback_analysis(pre_findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build minimal analysis dict khi state không có analysis_results.

        Reuse từ orchestrator.report_node fallback (no FAIL findings → skip
        verification → analysis_results=None).
        """
        sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in pre_findings:
            s = (f.get("severity") or "").lower()
            if s in sev:
                sev[s] += 1
        pass_count = sum(1 for f in pre_findings if f.get("status") == "PASS")
        fail_count = sum(1 for f in pre_findings if f.get("status") == "FAIL")
        return {
            "pre_stats": {
                "total": len(pre_findings),
                "pass": pass_count,
                "fail": fail_count,
                "severity": sev,
            },
            "post_stats": {"pass": pass_count, "fail": fail_count},
            "remediation_stats": {"fixed": 0, "failed": 0, "manual": 0},
            "success_findings": [],
            "failed_findings": [],
            "manual_findings": [],
            "findings_table": [],
            "raw_pre_findings": pre_findings,
        }
