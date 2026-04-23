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

        Quality gates (Phase 3 rebuild):
          - ``key_findings`` sorted by severity (critical -> low).
          - ``control_themes`` filtered to mappings with confidence >= medium.
          - ``recommended_practices`` sourced from ``remediation_recommendation``
            (human-readable guidance). No fallback to raw ``remediation`` code
            blocks or to ``mapping.rationale`` — both leak structured/noisy
            text into the prompt.
          - ``capability_details`` surfaces the rich maturity payload so the
            report prompts can ground wording against the actual doc.
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
            risk_summary = _truncate_at_sentence(
                meta.get("risk") or meta.get("description"),
                max_chars=300,
            )

            key_findings.append({
                "check_id": item.check_id,
                "title": item.title,
                "severity": meta.get("severity"),
                "risk_summary": risk_summary,
            })

        key_findings.sort(key=lambda f: _severity_rank(f.get("severity")))
        primary_topics = sorted(list(primary_topics_set))

        # Only mappings at medium+ confidence are allowed to flow into the
        # report. Unreviewed/low-confidence links are the exact hallucination
        # vector we want to keep out.
        confident_mappings = _filter_confident_mappings(
            selected_mappings, min_level="medium"
        )
        allowed_capability_ids = {m.capability_id for m in confident_mappings if m.capability_id}

        control_themes: List[Dict[str, Any]] = []
        capability_details: List[Dict[str, Any]] = []
        practices: List[str] = []
        seen_capabilities: set[str] = set()

        for item in selected_capabilities:
            if item.capability_id in seen_capabilities:
                continue
            seen_capabilities.add(item.capability_id)

            # When we *have* confident mappings, stay within them so the
            # report never leans on a capability the retrieval layer
            # surfaced via a low-confidence link. When no confident
            # mapping exists (e.g. pure semantic query with no findings),
            # fall back to the full capability list.
            if allowed_capability_ids and item.capability_id not in allowed_capability_ids:
                continue

            meta = _ensure_dict(item.metadata)
            summary = _truncate_at_sentence(
                meta.get("summary") or item.short_text, max_chars=500
            ) or ""

            control_themes.append({
                "capability_id": item.capability_id,
                "capability_name": item.capability_name,
                "summary_short": summary,
            })

            capability_details.append({
                "capability_id": item.capability_id,
                "capability_name": item.capability_name or "Unknown capability",
                "domain": meta.get("domain") or item.domain,
                "stage": meta.get("stage"),
                "summary": summary or (item.capability_name or item.capability_id),
                "risk_explanation": _truncate_at_sentence(
                    meta.get("risk_explanation"), max_chars=500
                ),
                "recommendation": _truncate_at_sentence(
                    meta.get("guidance"), max_chars=500
                ),
                "guidance_questions": _split_guidance_questions(
                    meta.get("how_to_check")
                ),
                "url": meta.get("source_uri") or meta.get("url"),
            })

            for p in meta.get("recommended_practices") or []:
                if isinstance(p, str) and p.strip():
                    practices.append(p.strip())

        # Augment practices with finding-level remediation_recommendation
        # (Phase 2 surfaced this field into rich metadata). This is the
        # preferred source: it is already sentence-cleaned by the
        # normalizer and never contains raw CLI/YAML code blocks.
        for item in all_checks:
            meta = _ensure_dict(item.metadata)
            rec = meta.get("remediation_recommendation")
            if isinstance(rec, str) and rec.strip():
                practices.append(rec.strip())

        seen_practices: set[str] = set()
        recommended_practices: List[str] = []
        for p in practices:
            truncated = _truncate_at_sentence(p, max_chars=240)
            if not truncated or truncated in seen_practices:
                continue
            seen_practices.add(truncated)
            recommended_practices.append(truncated)
            if len(recommended_practices) >= 8:
                break

        return {
            "primary_topics": primary_topics,
            "key_findings": key_findings,
            "control_themes": control_themes,
            "recommended_practices": recommended_practices,
            "capability_details": capability_details,
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
            # capability_details is the richest signal for report-grade
            # grounding. Missing it means the prompt will lean on
            # findings-only context — confidence must reflect that.
            if not report_bundle.get("capability_details"):
                return "low"
            practices = report_bundle.get("recommended_practices") or []
            themes = report_bundle.get("control_themes") or []
            if not themes or len(practices) < 3:
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


_SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "informational": 4,
    "info": 4,
}


def _severity_rank(severity: Optional[str]) -> int:
    """Ordinal rank for sorting (0 = most severe). Unknown severities sink."""
    return _SEVERITY_RANK.get((severity or "").strip().lower(), 99)


_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _filter_confident_mappings(
    mappings: Sequence[SelectedMappingContext],
    min_level: str = "medium",
) -> List[SelectedMappingContext]:
    """Keep mappings whose confidence >= ``min_level``.

    Mappings without a confidence value are dropped because an unreviewed
    link between a check and a capability is exactly the kind of
    ungrounded claim we want to keep out of the report.
    """
    threshold = _CONFIDENCE_RANK.get(min_level, 1)
    kept: List[SelectedMappingContext] = []
    for m in mappings:
        conf = m.mapping_confidence
        if conf is None:
            continue
        value = conf.value if hasattr(conf, "value") else conf
        if _CONFIDENCE_RANK.get(str(value).lower(), -1) >= threshold:
            kept.append(m)
    return kept


_SENTENCE_BREAKS = (". ", "; ", ", ")


def _truncate_at_sentence(
    text: Optional[str], max_chars: int = 500
) -> Optional[str]:
    """Truncate at a sentence boundary (. ; ,) close to ``max_chars`` rather
    than mid-word, so prompt injection never cuts a thought in half."""
    if not text:
        return None
    text = text.strip()
    if len(text) <= max_chars:
        return text

    window = text[:max_chars]
    best = -1
    for brk in _SENTENCE_BREAKS:
        idx = window.rfind(brk)
        if idx > best:
            best = idx + len(brk) - 1  # keep the punctuation, drop trailing space
    if best <= 0:
        # No boundary found — fall back to word boundary to avoid mid-word cut.
        best = window.rfind(" ")
        if best <= 0:
            return window.rstrip() + "..."
    return text[:best + 1].rstrip() + "..."


def _split_guidance_questions(text: Optional[str]) -> List[str]:
    """Split a how_to_check blob into assessment questions.

    Capability docs often encode guidance as numbered/bulleted lists or
    question sentences. This helper extracts each actionable line so
    report prompts can present them as a checklist rather than prose.
    """
    if not text or not isinstance(text, str):
        return []
    raw = text.replace("\r", "\n")
    lines: List[str] = []
    for line in raw.split("\n"):
        s = line.strip().lstrip("-*•").lstrip("0123456789.)").strip()
        if len(s) >= 5:
            lines.append(s)
    if not lines and "?" in raw:
        lines = [q.strip() + "?" for q in raw.split("?") if q.strip()]
    return lines[:6]


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
