"""
Intent detection for context building.

Identifies semantic intents in queries via keyword cluster matching
and infers control families from text using control intent markers.
"""
from __future__ import annotations

from typing import Any, List, Optional, Set

from app.core.constants import (
    CONTROL_INTENT_CLUSTERS,
    PRODUCT_ENTITY_GATES,
    QUERY_INTENT_CLUSTERS,
)


class IntentDetector:
    """
    Detects query-level intents and control family signals.

    - Query intents use short keywords (e.g. "encrypt", "public") for
      broad intent classification.
    - Control families use longer phrases (e.g. "encryption at rest",
      "public access") for fine-grained control family matching.
    """

    def detect_query_intents(self, query: Optional[str]) -> List[str]:
        """
        Identify distinct semantic intents present in the query.

        Returns a list of active intent names (e.g. ["encryption", "public_access"]).
        """
        if not query:
            return []
        q = query.lower()
        active: List[str] = []
        for intent_name, keywords in QUERY_INTENT_CLUSTERS.items():
            if any(kw in q for kw in keywords):
                active.append(intent_name)
        return active

    def infer_control_families(self, text: str) -> Set[str]:
        """
        Infer which control families are represented in the given text.

        Uses longer marker phrases from CONTROL_INTENT_CLUSTERS.
        """
        normalized = (text or "").lower()
        families: Set[str] = set()
        for family, markers in CONTROL_INTENT_CLUSTERS.items():
            if any(marker in normalized for marker in markers):
                families.add(family)
        return families

    def mapping_passes_entity_gate(
        self,
        check_id: str,
        capability_id: str,
        capability_name: Optional[str],
        mapping_confidence: Any,
        mapping_type: Any,
        review_status: Any,
        check_signal: str,
    ) -> bool:
        """
        Returns False if the capability contains a product-specific entity
        that requires matching signals in the check, but no such signals exist.
        Also rejects weak-quality mappings.
        """
        cap_text = " ".join(filter(None, [capability_id, capability_name or ""])).lower()
        check_text = check_signal.lower()

        for entity_token, required_signals in PRODUCT_ENTITY_GATES.items():
            if entity_token in cap_text:
                if not any(sig in check_text for sig in required_signals):
                    return False

        capability_families = self.infer_control_families(cap_text)
        check_families = self.infer_control_families(check_text)
        if capability_families and check_families and not (
            capability_families & check_families
        ):
            return False

        conf = _maybe_str(mapping_confidence).lower()
        mtype = _maybe_str(mapping_type).lower()
        rstatus = _maybe_str(review_status).lower()

        is_weak_quality = (
            conf == "low"
            and mtype in {"weak", "indirect", "fuzzy", "tentative", "unconfirmed"}
            and rstatus in {"draft", "review_required", "pending"}
        )
        if is_weak_quality:
            return False

        return True

    def capability_domain_mismatch(
        self,
        capability_id: str,
        capability_name: Optional[str],
        check_context: str,
    ) -> bool:
        """
        Returns True if the capability has a product-specific entity
        that is NOT supported by the check context.
        """
        cap_text = " ".join(filter(None, [capability_id, capability_name or ""])).lower()
        check_text = check_context.lower()

        for entity_token, required_signals in PRODUCT_ENTITY_GATES.items():
            if entity_token in cap_text:
                if not any(sig in check_text for sig in required_signals):
                    return True

        capability_families = self.infer_control_families(cap_text)
        check_families = self.infer_control_families(check_text)
        if capability_families and check_families and not (
            capability_families & check_families
        ):
            return True

        return False


def _maybe_str(value: Any) -> str:
    """Safe string conversion."""
    if value is None:
        return ""
    text = str(value).strip()
    return text or ""
