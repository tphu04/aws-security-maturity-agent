"""
Cross-encoder reranker for hybrid retrieval pipeline.

Replaces handcrafted scoring heuristics (intent_bonus, check_id_intent_boost,
product_penalty) with a learned cross-encoder model that scores (query, passage)
pairs directly.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2  (~22 MB, ~5 ms per pair)
Output: sigmoid-normalized scores in [0, 1]
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Singleton cross-encoder reranker.

    The model is loaded lazily on first use and cached for subsequent calls.
    """

    _instance: ClassVar[Optional["CrossEncoderReranker"]] = None
    _model_name: ClassVar[Optional[str]] = None

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        logger.info("Loading cross-encoder model: %s", model_name)
        self._model = CrossEncoder(model_name)
        CrossEncoderReranker._model_name = model_name

    @classmethod
    def get_instance(cls, model_name: str) -> "CrossEncoderReranker":
        if cls._instance is None or cls._model_name != model_name:
            cls._instance = cls(model_name)
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_n: int = 20,
    ) -> List[Dict[str, Any]]:
        """Rerank *candidates* by cross-encoder relevance to *query*.

        Each candidate dict must already be hydrated (``metadata.retrieval_text``
        available).  Returns a **new list** sorted by cross-encoder score,
        truncated to *top_n*.
        """
        if not candidates:
            return []

        pairs = [(query, self._extract_passage(c)) for c in candidates]

        raw_scores = self._model.predict(pairs)
        # Sigmoid → [0, 1]
        scores = 1.0 / (1.0 + np.exp(-np.asarray(raw_scores, dtype=np.float64)))

        for candidate, score in zip(candidates, scores):
            candidate["score"] = float(score)

        candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return candidates[:top_n]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_passage(candidate: Dict[str, Any]) -> str:
        """Build the passage string the cross-encoder will score against."""
        meta = candidate.get("metadata") or {}

        retrieval_text = meta.get("retrieval_text")
        if retrieval_text and str(retrieval_text).strip():
            return str(retrieval_text).strip()

        # Fallback: concatenate available text fields
        parts = [
            meta.get("title", ""),
            meta.get("description", ""),
            meta.get("summary", ""),
        ]
        fallback = " ".join(str(p) for p in parts if p).strip()
        return fallback or candidate.get("doc_id", "")
