"""
Prompt-ready context formatting for context building.

Formats selected checks, mappings, and capabilities into
human/LLM-readable prompt context blocks.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.core.models import (
    Confidence,
    ContextEvidenceItem,
    PromptReadyContext,
    SelectedCapabilityContext,
    SelectedCheckContext,
    SelectedMappingContext,
)


class PromptFormatter:
    """
    Formats context data into prompt-ready text blocks
    and evidence summaries.
    """

    def format(
        self,
        consumer: str,
        query: Optional[str],
        requested_checks: Sequence[SelectedCheckContext],
        related_checks: Sequence[SelectedCheckContext],
        selected_mappings: Sequence[SelectedMappingContext],
        selected_capabilities: Sequence[SelectedCapabilityContext],
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
    ) -> PromptReadyContext:
        """Build a PromptReadyContext with header, evidence, and guidance."""
        header_lines = [
            f"Context consumer: {consumer}",
            f"Primary query: {query or '(not provided)'}",
            f"Overall retrieval confidence: {confidence.value}",
            f"Review recommended: {'true' if review_recommended else 'false'}",
        ]
        if warnings:
            header_lines.append(f"Warnings: {', '.join(warnings)}")

        evidence_sections: List[str] = []

        if requested_checks:
            check_lines = ["[Requested Checks]"]
            for item in requested_checks:
                line = f"- {item.check_id}"
                if item.service:
                    line += f" (service: {item.service})"
                if item.short_text:
                    line += f": {item.short_text}"
                check_lines.append(line)
            evidence_sections.append("\n".join(check_lines))

        if related_checks:
            related_lines = ["[Related Checks]"]
            for item in related_checks:
                line = f"- {item.check_id}"
                if item.service:
                    line += f" (service: {item.service})"
                if item.short_text:
                    line += f": {item.short_text}"
                related_lines.append(line)
            evidence_sections.append("\n".join(related_lines))

        if selected_mappings:
            mapping_lines = ["[Selected Mappings]"]
            for item in selected_mappings:
                line = f"- {item.check_id} -> {item.capability_id}"
                if item.mapping_confidence:
                    line += f" (mapping_confidence: {item.mapping_confidence.value})"
                if item.rationale:
                    line += f": {item.rationale}"
                mapping_lines.append(line)
            evidence_sections.append("\n".join(mapping_lines))

        if selected_capabilities:
            capability_lines = ["[Selected Capabilities]"]
            for item in selected_capabilities:
                label = item.capability_name or item.capability_id
                line = f"- {label}"
                if item.short_text:
                    line += f": {item.short_text}"
                capability_lines.append(line)
            evidence_sections.append("\n".join(capability_lines))

        guidance_block = self._build_guidance_block(
            consumer=consumer,
            confidence=confidence,
            review_recommended=review_recommended,
            warnings=warnings,
        )

        return PromptReadyContext(
            header="\n".join(header_lines),
            evidence_block="\n\n".join(evidence_sections).strip(),
            guidance_block=guidance_block,
        )

    def build_evidence_summary(
        self,
        selected_checks: Sequence[SelectedCheckContext],
        selected_mappings: Sequence[SelectedMappingContext],
        selected_capabilities: Sequence[SelectedCapabilityContext],
        max_context_items: int,
    ) -> List[ContextEvidenceItem]:
        """Build a list of evidence items for diagnostics."""
        items: List[ContextEvidenceItem] = []

        for check in selected_checks:
            items.append(
                ContextEvidenceItem(
                    doc_id=check.doc_id,
                    source_type=str(
                        check.metadata.get("source_type", "retrieval_result")
                    ),
                    doc_type="prowler_check",
                    title=check.title or check.check_id,
                    short_text=check.short_text,
                    why_selected="Selected as a primary technical control/check match.",
                    score=check.score,
                    confidence=check.confidence,
                    metadata=check.metadata,
                )
            )

        for mapping in selected_mappings:
            items.append(
                ContextEvidenceItem(
                    doc_id=f"mapping:{mapping.check_id}:{mapping.capability_id}",
                    source_type="mapping",
                    doc_type="maturity_mapping",
                    title=f"{mapping.check_id} -> {mapping.capability_id}",
                    short_text=mapping.rationale
                    or "Mapping links the check to a maturity capability.",
                    why_selected="Selected to connect technical findings with maturity guidance.",
                    score=None,
                    confidence=mapping.mapping_confidence,
                    metadata=mapping.metadata,
                )
            )

        for capability in selected_capabilities:
            items.append(
                ContextEvidenceItem(
                    doc_id=capability.doc_id,
                    source_type=str(
                        capability.metadata.get("source_type", "retrieval_result")
                    ),
                    doc_type="maturity_capability",
                    title=capability.capability_name or capability.capability_id,
                    short_text=capability.short_text,
                    why_selected="Selected as supporting control and best-practice context.",
                    score=capability.score,
                    confidence=capability.confidence,
                    metadata=capability.metadata,
                )
            )

        return items[:max_context_items]

    def _build_guidance_block(
        self,
        consumer: str,
        confidence: Confidence,
        review_recommended: bool,
        warnings: Sequence[str],
    ) -> str:
        base_lines: List[str] = []

        if consumer == "planning":
            base_lines.append(
                "Use the selected checks to decide which checks or services should be scanned next."
            )
            base_lines.append(
                "Prefer exact or top-ranked check matches as anchors for planning."
            )
        elif consumer == "risk":
            base_lines.append(
                "Use the selected checks as primary technical evidence for the finding."
            )
            base_lines.append(
                "Use mappings and capabilities as supporting control context for risk analysis."
            )
        else:
            base_lines.append(
                "Use the selected checks as factual technical evidence in the report."
            )
            base_lines.append(
                "Use mappings and capabilities to explain control intent, best practices, and remediation direction."
            )

        if confidence == Confidence.low or review_recommended:
            base_lines.append(
                "Do not make overly certain claims. Phrase conclusions carefully and acknowledge uncertainty where needed."
            )

        if warnings:
            base_lines.append(
                f"Pay attention to these warnings: {', '.join(warnings)}."
            )

        return "\n".join(base_lines)
