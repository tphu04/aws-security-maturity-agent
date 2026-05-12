"""rag_enrich_node — multi-query RAG enrichment giữa risk_evaluation và operational_planning.

Phase D-web1: port từ legacy `pdca/api/run_orchestrator._phase_rag_enrich`
sang LangGraph node để:
  1. Persist enrichment vào checkpointer (state.rag_bundle survives restart).
  2. operational_planning đọc rag_bundle để gắn ragSteps/ragEffort vào tasks.
  3. report_node truyền rag_bundle vào ReportDataBuilder.
  4. FE ToolTracePanel "Knowledge" tab render từ state.rag_bundle.

Soft-fail: RAG offline / timeout → emit empty bundle, không raise.
Skip: không có FAIL findings → no-op (state delta = {}).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig

from pdca.agents.shared.rag_client import RAGClient
from pdca.config import settings
from pdca.graph._tracing_helpers import flush_at_node, node_span
from pdca.graph.state import PDCAState

logger = logging.getLogger(__name__)


def rag_enrich_node(state: PDCAState, config: RunnableConfig) -> dict:
    """Multi-query RAG bundle: report_context (Q1+Q2+Q3) + resolve_mapping per check.

    Reads:  state.prioritized_findings (FAIL filter)
    Writes: state.rag_bundle, state.prioritized_findings (enriched per-finding)
    """
    run_id = state.get("run_id", "")

    findings = state.get("prioritized_findings") or []
    fails = [f for f in findings if f.get("status") == "FAIL"]

    if not fails:
        logger.info(
            "rag_enrich skipped — no FAIL findings",
            extra={"run_id": run_id},
        )
        return {}

    if not state.get("rag_available", False):
        logger.info(
            "rag_enrich skipped — RAG unavailable",
            extra={"run_id": run_id},
        )
        return {"rag_bundle": {"capability_themes": [], "remediation_guides": [],
                                "control_mappings": {}, "confidence": "unavailable"}}

    unique_check_ids = sorted({_check_id(f) for f in fails if _check_id(f)})
    domains = sorted({(f.get("service") or "").lower() for f in fails if f.get("service")})

    sev_map: Dict[str, str] = {}
    for f in fails:
        cid = _check_id(f)
        s = (f.get("severity") or "").upper()
        if s in ("CRITICAL", "HIGH", "MEDIUM", "LOW") and cid and cid not in sev_map:
            sev_map[cid] = s

    with node_span("rag_enrich", run_id) as sp:
        client = RAGClient(base_url=settings.rag_api_url)

        rag_request: Dict[str, Any] = {
            "endpoint": "/v1/retrieve/report_context",
            "check_ids": unique_check_ids,
            "domains": domains,
            "severity_map": sev_map,
            "include_q2": True,
            "include_q3": True,
            "top_k_check": 10,
            "top_k_capability": 5,
            "top_k_remediation": 3,
        }
        bundle: Dict[str, Any] = {}
        try:
            bundle = client.build_report_context(
                check_ids=unique_check_ids,
                domains=domains,
                severity_map=sev_map,
                include_q2=True,
                include_q3=True,
                top_k_check=10,
                top_k_capability=5,
                top_k_remediation=3,
            ) or {}
        except Exception as e:
            logger.warning(
                "build_report_context failed",
                extra={"run_id": run_id, "error": str(e)},
            )

        mappings: Dict[str, Any] = {}
        mapping_trace: List[Dict[str, Any]] = []
        for cid in unique_check_ids:
            try:
                f0 = next((x for x in fails if _check_id(x) == cid), {})
                m = client.resolve_mapping(
                    check_id=cid,
                    service=f0.get("service") or None,
                ) or {}
                if m:
                    mappings[cid] = m.get("data") or m
                    selected = mappings[cid]
                    mapping_trace.append({
                        "endpoint": "/v1/resolve/mapping",
                        "check_id": cid,
                        "service": f0.get("service") or None,
                        "selected_capability_id": (
                            selected.get("capability_id")
                            or (selected.get("mapping") or {}).get("capability_id")
                        ) if isinstance(selected, dict) else None,
                        "status": "success",
                    })
            except Exception:
                mapping_trace.append({
                    "endpoint": "/v1/resolve/mapping",
                    "check_id": cid,
                    "status": "failed",
                })
                pass

        # Index for per-finding enrichment.
        check_index: Dict[str, Dict[str, Any]] = {}
        for cf in (bundle.get("check_findings") or []):
            cid = cf.get("check_id") or (cf.get("metadata") or {}).get("check_id")
            if cid:
                check_index[cid] = cf

        rem_index: Dict[str, Dict[str, Any]] = {}
        for rg in (bundle.get("remediations") or []):
            cid = rg.get("check_id")
            if cid:
                rem_index[cid] = rg

        enriched_count = 0
        enriched_findings: List[Dict[str, Any]] = []
        for f in findings:
            f2 = dict(f)
            cid = _check_id(f2)
            if f2.get("status") == "FAIL" and cid:
                cf = check_index.get(cid) or {}
                md = cf.get("metadata") or cf
                if md:
                    f2["compliance"] = md.get("keywords") or md.get("compliance") or []
                    f2["risk_from_rag"] = (md.get("risk") or "")[:300]
                    f2["remediation_recommendation"] = md.get("remediation_recommendation") or ""
                    f2["remediation_url"] = md.get("remediation_url") or ""
                    f2["rag_title"] = md.get("title") or ""
                    rag_sev = (md.get("severity") or "").lower()
                    if rag_sev in ("critical", "high", "medium", "low", "info"):
                        f2["severity"] = rag_sev
                    enriched_count += 1
                rg = rem_index.get(cid)
                if rg:
                    f2["remediation_guide"] = rg
                m = mappings.get(cid)
                if m:
                    f2["control_mappings"] = m
            enriched_findings.append(f2)

        themes = _document_backed_themes(bundle.get("capability_themes") or [])
        guides = list(rem_index.values())
        confidence = bundle.get("confidence") or "unknown"

        sp.update(
            output={
                "fail_count": len(fails),
                "unique_check_ids": len(unique_check_ids),
                "themes": len(themes),
                "guides": len(guides),
                "mappings": len(mappings),
                "enriched": enriched_count,
                "confidence": confidence,
            }
        )
        flush_at_node()

    logger.info(
        "rag_enrich done",
        extra={
            "run_id": run_id,
            "enriched": enriched_count,
            "themes": len(themes),
            "guides": len(guides),
        },
    )

    return {
        "rag_bundle": {
            "capability_themes": themes,
            "remediation_guides": guides,
            "control_mappings": mappings,
            "confidence": confidence,
            "diagnostics": bundle.get("diagnostics") or {},
            "trace": {
                "report_context_request": rag_request,
                "resolve_mapping_requests": mapping_trace,
                "response_counts": {
                    "check_findings": len(bundle.get("check_findings") or []),
                    "capability_themes": len(themes),
                    "remediation_guides": len(guides),
                    "control_mappings": len(mappings),
                },
            },
        },
        "prioritized_findings": enriched_findings,
    }


def _check_id(f: Dict[str, Any]) -> str:
    """Extract Prowler check_id from a finding (PDCAState shape)."""
    return str(
        f.get("event_code")
        or f.get("check_id")
        or (f.get("metadata") or {}).get("event_code")
        or ""
    )


def _document_backed_themes(themes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only concise capability context with explicit citations.

    This protects the UI/report from older RAG service versions that returned
    broad domain snippets and long common_pitfalls for queries like "s3".
    """
    out: List[Dict[str, Any]] = []
    for t in themes:
        if not isinstance(t, dict):
            continue
        citations = t.get("citations") or []
        if not citations or not any((c or {}).get("url") for c in citations if isinstance(c, dict)):
            continue
        narrative = " ".join(str(t.get("narrative") or "").split())
        if not narrative:
            continue
        if len(narrative) > 360:
            narrative = narrative[:357].rstrip() + "..."
        out.append({
            "domain": t.get("domain") or "general",
            "narrative": narrative,
            "common_pitfalls": [],
            "baselines": [],
            "citations": citations[:3],
        })
    return out[:5]
