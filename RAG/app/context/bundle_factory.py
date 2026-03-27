"""
Bundle construction for context building.

Builds consumer-specific bundles (risk, planning, report) and
evaluates bundle-level confidence adjustments.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.core.models import (
    Confidence,
    SelectedCapabilityContext,
    SelectedCheckContext,
    SelectedMappingContext,
)
from app.context.intent_detector import IntentDetector


class BundleFactory:
    """
    Builds consumer-specific context bundles from selected checks,
    mappings, and capabilities.
    """

    def __init__(self) -> None:
        self._intent_detector = IntentDetector()

    def build(
        self,
        consumer: str,
        requested_checks: Sequence[SelectedCheckContext],
        related_checks: Sequence[SelectedCheckContext],
        selected_mappings: Sequence[SelectedMappingContext],
        selected_capabilities: Sequence[SelectedCapabilityContext],
    ) -> Dict[str, Any]:
        """Dispatch to the appropriate bundle builder by consumer type."""
        if consumer == "risk":
            return self.build_risk_bundle(
                requested_checks, related_checks,
                selected_mappings, selected_capabilities,
            )
        elif consumer == "planning":
            return self.build_planning_bundle(
                requested_checks, related_checks,
                selected_mappings, selected_capabilities,
            )
        elif consumer == "report":
            return self.build_report_bundle(
                requested_checks, related_checks,
                selected_mappings, selected_capabilities,
            )
        return {}

    def build_risk_bundle(
        self,
        requested_checks: Sequence[SelectedCheckContext],
        related_checks: Sequence[SelectedCheckContext],
        selected_mappings: Sequence[SelectedMappingContext],
        selected_capabilities: Sequence[SelectedCapabilityContext],
    ) -> Dict[str, Any]:
        """
        Risk bundle: broader context, mappings, and related findings
        to help evaluate the impact of a violation.
        """
        primary_finding: Optional[Dict[str, Any]] = None

        if requested_checks:
            primary_finding = _normalize_check_item(
                requested_checks[0], include_remediation=True
            )

        related_findings: List[Dict[str, Any]] = [
            {
                "check_id": item.check_id,
                "service": item.service,
                "title": item.title,
                "severity": _ensure_dict(item.metadata).get("severity"),
            }
            for item in related_checks
        ]

        control_mapping: List[Dict[str, Any]] = []
        for item in selected_mappings:
            confidence_val = (
                item.mapping_confidence.value
                if hasattr(item.mapping_confidence, "value")
                else item.mapping_confidence
            )
            control_mapping.append(
                {
                    "check_id": item.check_id,
                    "capability_id": item.capability_id,
                    "mapping_confidence": confidence_val,
                }
            )

        maturity_context: List[Dict[str, Any]] = [
            {
                "capability_id": item.capability_id,
                "capability_name": item.capability_name,
                "short_text": item.short_text,
            }
            for item in selected_capabilities
        ]

        return {
            "primary_finding": primary_finding,
            "related_findings": related_findings,
            "control_mapping": control_mapping,
            "maturity_context": maturity_context,
        }

    def build_planning_bundle(
        self,
        requested_checks: Sequence[SelectedCheckContext],
        related_checks: Sequence[SelectedCheckContext],
        selected_mappings: Sequence[SelectedMappingContext],
        selected_capabilities: Sequence[SelectedCapabilityContext],
    ) -> Dict[str, Any]:
        """
        Planning bundle: check metadata (ID, service, severity)
        useful for determining scope and relevance.
        """
        related_findings: List[Dict[str, Any]] = []

        all_checks = list(requested_checks) + list(related_checks)
        seen_checks: set[str] = set()

        for item in all_checks:
            if item.check_id in seen_checks:
                continue
            seen_checks.add(item.check_id)
            meta = _ensure_dict(item.metadata)
            related_findings.append(
                {
                    "check_id": item.check_id,
                    "service": item.service,
                    "title": item.title,
                    "severity": meta.get("severity"),
                }
            )

        control_mapping_ids = [
            item.capability_id
            for item in selected_mappings
            if item.capability_id
        ]
        maturity_capability_ids = [
            item.capability_id
            for item in selected_capabilities
            if item.capability_id
        ]

        return {
            "related_findings": related_findings,
            "control_mapping_ids": control_mapping_ids,
            "maturity_capability_ids": maturity_capability_ids,
        }

    def build_report_bundle(
        self,
        requested_checks: Sequence[SelectedCheckContext],
        related_checks: Sequence[SelectedCheckContext],
        selected_mappings: Sequence[SelectedMappingContext],
        selected_capabilities: Sequence[SelectedCapabilityContext],
    ) -> Dict[str, Any]:
        """
        Report bundle: aggregated themes, key findings, and
        consolidated recommended practices for narrative generation.
        """
        all_checks = list(requested_checks) + list(related_checks)
        seen_checks: set[str] = set()
        key_findings: List[Dict[str, Any]] = []
        primary_topics_set: set[str] = set()

        for item in all_checks:
            if item.check_id in seen_checks:
                continue
            seen_checks.add(item.check_id)

            if item.service:
                primary_topics_set.add(item.service.lower())

            meta = _ensure_dict(item.metadata)
            risk_summary = _truncate_text(
                meta.get("risk") or meta.get("description")
            )

            key_findings.append({
                "check_id": item.check_id,
                "title": item.title,
                "severity": meta.get("severity"),
                "risk_summary": risk_summary,
            })

        primary_topics = sorted(list(primary_topics_set))

        control_themes: List[Dict[str, Any]] = []
        practices_set: set[str] = set()

        for item in selected_capabilities:
            meta = _ensure_dict(item.metadata)
            control_themes.append({
                "capability_id": item.capability_id,
                "capability_name": item.capability_name,
                "summary_short": _truncate_text(meta.get("summary")) or "",
            })

            raw_practices = meta.get("recommended_practices") or []
            for p in raw_practices:
                practices_set.add(p)

        if not control_themes and selected_mappings:
            for mapping in selected_mappings:
                control_themes.append({
                    "capability_id": mapping.capability_id,
                    "capability_name": mapping.capability_name,
                    "summary_short": _truncate_text(mapping.rationale) or "",
                })

        if not practices_set and selected_mappings:
            for mapping in selected_mappings:
                if mapping.rationale:
                    practices_set.add(mapping.rationale)

        if not practices_set and all_checks:
            for item in all_checks:
                meta = _ensure_dict(item.metadata)
                raw_practices = meta.get("recommended_practices") or []
                for p in raw_practices:
                    practices_set.add(p)

        if not practices_set and all_checks:
            for item in all_checks:
                meta = _ensure_dict(item.metadata)
                remediation = meta.get("remediation")
                if remediation:
                    practices_set.add(remediation)

        recommended_practices = [
            _truncate_text(p, 150)
            for p in sorted(list(practices_set))
        ][:5]

        return {
            "primary_topics": primary_topics,
            "key_findings": key_findings,
            "control_themes": control_themes,
            "recommended_practices": recommended_practices,
        }

    def evaluate_bundle_confidence(
        self,
        consumer: str,
        query: Optional[str],
        risk_bundle: Optional[Dict[str, Any]],
        report_bundle: Optional[Dict[str, Any]],
        planning_bundle: Optional[Dict[str, Any]],
        retrieval_confidence: Confidence,
    ) -> Optional[str]:
        """
        Evaluate confidence based on actual payload quality.
        Returns a confidence string or None if unchanged.
        """
        base_conf = str(
            retrieval_confidence.value
            if hasattr(retrieval_confidence, "value")
            else retrieval_confidence
        ).lower()

        if consumer == "risk" and risk_bundle:
            if not risk_bundle.get("primary_finding"):
                return "low"
            if not risk_bundle.get("control_mapping") and not risk_bundle.get(
                "maturity_context"
            ):
                if base_conf == "high":
                    return "medium"
            return base_conf

        elif consumer == "report" and report_bundle:
            if not report_bundle.get("key_findings") or not report_bundle.get(
                "primary_topics"
            ):
                return "low"
            if not report_bundle.get(
                "control_themes"
            ) or not report_bundle.get("recommended_practices"):
                if base_conf == "high":
                    return "medium"
            return base_conf

        elif consumer == "planning" and planning_bundle:
            findings = planning_bundle.get("related_findings") or []
            if not findings:
                return "low"

            intents = self._intent_detector.detect_query_intents(query or "")
            services_covered = {
                f.get("service") for f in findings if f.get("service")
            }

            if len(intents) > 1 and len(services_covered) <= 1:
                if base_conf == "high":
                    return "medium"
            return base_conf

        return base_conf


# ============================================================
# Module-level helpers
# ============================================================

def _ensure_dict(value: object) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _truncate_text(
    text: Optional[str], max_length: int = 200
) -> Optional[str]:
    if not text:
        return None
    return text[:max_length] + "..." if len(text) > max_length else text


def _normalize_check_item(
    item: SelectedCheckContext,
    include_remediation: bool = True,
) -> Dict[str, Any]:
    """
    Shared transform from SelectedCheckContext -> bundle-ready dict.
    """
    meta = _ensure_dict(item.metadata)
    return {
        "check_id": item.check_id,
        "service": item.service,
        "title": item.title,
        "severity": meta.get("severity"),
        "description": meta.get("description") or None,
        "risk": meta.get("risk") or None,
        "remediation": (
            meta.get("remediation") or None if include_remediation else None
        ),
    }
