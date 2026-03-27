"""Shared utility functions for the RAG service."""

from __future__ import annotations

from typing import Any, Dict


def mapping_sort_key(item: Dict[str, Any]) -> tuple:
    """Unified sort key for ranking maturity mappings.

    Returns a tuple suitable for ``sorted(..., reverse=True)`` so that
    higher-quality mappings appear first:
      (review_rank, confidence_rank, score, capability_id)

    The *capability_id* tiebreaker ensures deterministic ordering when
    review status, confidence, and score are equal.
    """
    confidence_rank = {
        "high": 3,
        "medium": 2,
        "low": 1,
    }
    review_rank = {
        "approved": 10,
        "reviewed": 5,
        "auto_high": 2,
        "draft": 1,
        "review_required": 0,
        "unreviewed": 0,
    }

    confidence = str(item.get("mapping_confidence", "low")).strip().lower()
    review_status = str(item.get("review_status", "unreviewed")).strip().lower()
    score = float(item.get("score", 0.0) or 0.0)
    capability_id = str(item.get("capability_id", "")).strip().lower()

    return (
        review_rank.get(review_status, 0),
        confidence_rank.get(confidence, 1),
        score,
        capability_id,
    )
