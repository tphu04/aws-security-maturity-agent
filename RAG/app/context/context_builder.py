"""
ContextBuilder facade.

Delegates to specialized modules:
- IntentDetector: query intent detection, control family inference, entity gating
- CoverageSelector: all item selection (checks, mappings, capabilities)
- BundleFactory: consumer-specific bundle construction + confidence evaluation
- PromptFormatter: prompt-ready context + evidence summary
- _helpers: shared utility functions (compression, extraction, normalization)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.models import (
    ContextBuildData,
    ContextBundleStats,
    ContextDiagnostics,
    ContextPayload,
)
from app.context.coverage_selector import CoverageSelector
from app.context.bundle_factory import BundleFactory
from app.context.prompt_formatter import PromptFormatter
from app.context._helpers import (
    ensure_list,
    ensure_list_of_strings,
    normalize_confidence,
    normalize_warnings,
)


class ContextBuilder:
    """
    Build agent-friendly context packets from a retrieval bundle.

    Expected bundle shape (flexible, best-effort):
    {
        "query": str | None,
        "consumer": "planning" | "risk" | "report",
        "provider": "aws",
        "service": str | None,
        "domain": str | None,
        "check_results": [ ...retrieve result items... ],
        "mapping_results": [ ...mapping items... ],
        "maturity_results": [ ...retrieve result items... ],
        "confidence": "high" | "medium" | "low",
        "review_recommended": bool,
        "warnings": [str, ...],
    }
    """

    def __init__(self) -> None:
        self._coverage_selector = CoverageSelector()
        self._bundle_factory = BundleFactory()
        self._prompt_formatter = PromptFormatter()

    def build(
        self,
        bundle: Dict[str, Any],
        consumer: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> ContextBuildData:
        options = options or {}
        max_context_items = int(options.get("max_context_items", 8))
        max_chars_per_item = int(options.get("max_chars_per_item", 600))
        requested_check_ids = {
            str(x).strip().lower()
            for x in ensure_list_of_strings(bundle.get("requested_check_ids"))
        }

        query = bundle.get("query")
        confidence = normalize_confidence(bundle.get("confidence"))
        review_recommended = bool(bundle.get("review_recommended", False))
        warnings = normalize_warnings(bundle.get("warnings", []))

        check_results = ensure_list(bundle.get("check_results"))
        mapping_results = ensure_list(bundle.get("mapping_results"))
        maturity_results = ensure_list(bundle.get("maturity_results"))

        # --- Selection (delegated to CoverageSelector) ---
        requested_checks, related_checks = self._coverage_selector.select_checks(
            check_results, consumer, confidence, review_recommended,
            warnings, max_chars_per_item, requested_check_ids, query,
        )

        selected_checks = [*requested_checks, *related_checks]

        check_signal = " ".join(filter(None, [
            " ".join(c.check_id for c in selected_checks),
            " ".join(c.service for c in selected_checks if c.service),
            bundle.get("service") or "",
            query or "",
        ]))

        selected_mappings = self._coverage_selector.select_mappings(
            mapping_results, consumer, max_chars_per_item, check_signal,
        )

        selected_capabilities = self._coverage_selector.select_capabilities(
            maturity_results, consumer, confidence, review_recommended,
            warnings, max_chars_per_item, check_signal,
        )

        # --- Bundle construction (delegated to BundleFactory) ---
        risk_bundle = planning_bundle = report_bundle = None
        if consumer == "risk":
            risk_bundle = self._bundle_factory.build_risk_bundle(
                requested_checks, related_checks, selected_mappings, selected_capabilities,
            )
        elif consumer == "planning":
            planning_bundle = self._bundle_factory.build_planning_bundle(
                requested_checks, related_checks, selected_mappings, selected_capabilities,
            )
        elif consumer == "report":
            report_bundle = self._bundle_factory.build_report_bundle(
                requested_checks, related_checks, selected_mappings, selected_capabilities,
            )

        # --- Formatting (delegated to PromptFormatter) ---
        evidence_summary = self._prompt_formatter.build_evidence_summary(
            selected_checks, selected_mappings, selected_capabilities, max_context_items,
        )
        prompt_ready_context = self._prompt_formatter.format(
            consumer, query, requested_checks, related_checks,
            selected_mappings, selected_capabilities,
            confidence, review_recommended, warnings,
        )

        diagnostics = ContextDiagnostics(
            prompt_ready_context=prompt_ready_context,
            bundle_stats=ContextBundleStats(
                check_count=len(selected_checks),
                mapping_count=len(selected_mappings),
                capability_count=len(selected_capabilities),
            ),
            selected_checks=selected_checks,
            selected_mappings=selected_mappings,
            selected_capabilities=selected_capabilities,
            evidence_summary=evidence_summary,
        )

        adjusted_confidence = self._bundle_factory.evaluate_bundle_confidence(
            consumer, query, risk_bundle, report_bundle, planning_bundle, confidence,
        )
        if adjusted_confidence:
            diagnostics.adjusted_confidence = adjusted_confidence

        return ContextBuildData(
            consumer=consumer,
            query=query,
            payload=ContextPayload(
                planning_bundle=planning_bundle,
                risk_bundle=risk_bundle,
                report_bundle=report_bundle,
            ),
            diagnostics=diagnostics,
        )
