"""RAGQueryPlanner — Phase 3 MVP

Orchestrates the multi-query RAG call for the report agent.

Responsibilities:
- Dedup check_ids (order-preserving) from findings list.
- Build severity_map from findings.
- Derive domains from scope_detector output.
- Execute the call via RAGClient.build_report_context().
- Return a bundle dict compatible with RAGViewFormatter (adds
  capability_themes + remediations to existing rag_context shape).

Legacy mode (MULTI_QUERY_MODE=False):
- Delegates to client.build_context() — old single-query path.
- Returns bundle in existing rag_context shape (no capability_themes/remediations).
- This avoids a duplicate code path in the orchestrator.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RAGQueryPlanner:
    def __init__(self, rag_client: Any) -> None:
        self._client = rag_client

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def plan(
        self,
        findings: List[Dict[str, Any]],
        scope_domains: List[str],
    ) -> Dict[str, Any]:
        """Build a ReportContextRequest-compatible dict from findings + domains.

        Returns a plain dict (not a Pydantic model) to avoid coupling
        pdca-side code to RAG-side Pydantic models.
        """
        check_ids = self._dedup_check_ids(findings)
        severity_map = self._build_severity_map(findings)
        domains = self._dedup_domains(scope_domains)

        return {
            "check_ids": check_ids,
            "domains": domains,
            "severity_map": severity_map,
            "include_q2": True,
            "include_q3": True,
            "top_k_check": 10,
            "top_k_capability": 5,
            "top_k_remediation": 3,
        }

    def execute(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Call build_report_context and normalize to rag_context dict.

        On failure returns an empty dict (same behavior as legacy path).
        """
        result = self._client.build_report_context(
            check_ids=req["check_ids"],
            domains=req["domains"],
            severity_map=req.get("severity_map", {}),
            include_q2=req.get("include_q2", True),
            include_q3=req.get("include_q3", True),
            top_k_check=req.get("top_k_check", 10),
            top_k_capability=req.get("top_k_capability", 5),
            top_k_remediation=req.get("top_k_remediation", 3),
        )

        if result is None:
            logger.warning("RAGQueryPlanner: build_report_context returned None — returning empty bundle")
            return {}

        return self._normalize_bundle(result)

    def execute_legacy(self, check_ids: List[str]) -> Dict[str, Any]:
        """Legacy single-query path — delegates to build_context().

        Returns bundle in existing rag_context shape.
        """
        if not check_ids:
            return {}

        result = None
        for attempt in range(1, 4):
            result = self._client.build_context(
                consumer="report",
                check_ids=check_ids,
                include_mappings=True,
                include_maturity=True,
                top_k=10,
                retrieval_mode="hybrid",
            )
            if result is not None:
                break
            logger.warning("RAGQueryPlanner legacy: attempt %d/3 returned None", attempt)

        if result is None:
            return {}

        bundle = result.get("payload", {}).get("report_bundle", {})
        confidence = (
            bundle.get("confidence")
            or result.get("_meta", {}).get("confidence")
        )
        return {
            "primary_topics": bundle.get("primary_topics", []),
            "key_findings": bundle.get("key_findings", []),
            "control_themes": bundle.get("control_themes", []),
            "recommended_practices": bundle.get("recommended_practices", []),
            "capability_details": bundle.get("capability_details", []),
            "confidence": confidence,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dedup_check_ids(findings: List[Dict[str, Any]]) -> List[str]:
        seen: set = set()
        out: List[str] = []
        for f in findings:
            cid = (f.get("event_code") or f.get("check_id") or f.get("finding_id") or "").strip()
            if cid and cid not in seen:
                seen.add(cid)
                out.append(cid)
        return out

    @staticmethod
    def _build_severity_map(findings: List[Dict[str, Any]]) -> Dict[str, str]:
        sev_map: Dict[str, str] = {}
        for f in findings:
            cid = (f.get("event_code") or f.get("check_id") or "").strip()
            sev = (f.get("severity") or "").strip().upper()
            if cid and sev and cid not in sev_map:
                sev_map[cid] = sev
        return sev_map

    @staticmethod
    def _dedup_domains(scope_domains: List[str]) -> List[str]:
        seen: set = set()
        out: List[str] = []
        for d in scope_domains or []:
            d = d.strip().lower()
            if d and d not in seen:
                seen.add(d)
                out.append(d)
        return out or ["general"]

    @staticmethod
    def _normalize_bundle(result: Dict[str, Any]) -> Dict[str, Any]:
        """Map ReportContextBundle dict → rag_context dict shape.

        Preserves Q1 fields in existing shape AND adds Q2/Q3 fields.
        RAGViewFormatter reads from this dict — it checks for
        capability_themes and remediations when present.
        """
        return {
            # Q1 — existing shape (pass-through)
            "primary_topics": result.get("primary_topics", []),
            "key_findings": result.get("check_findings", []),
            "control_themes": result.get("control_themes", []),
            "recommended_practices": result.get("recommended_practices", []),
            "capability_details": result.get("capability_details", []),
            "confidence": result.get("confidence"),
            # Q2 — NEW
            "capability_themes": result.get("capability_themes", []),
            # Q3 — NEW
            "remediations": result.get("remediations", []),
        }
