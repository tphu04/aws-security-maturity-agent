from __future__ import annotations

import math
import pickle
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import BM25_INDEX_PATH
from app.ingestion.normalizers import normalize_query, tokenize


class BM25Index:
    """
    Lightweight BM25 index for lexical retrieval.

    Expected input doc shape:
    {
        "doc_id": "check:s3_account_level_public_access_blocks",
        "text": "... canonical retrieval text ...",
        "metadata": {
            "check_id": "s3_account_level_public_access_blocks",
            "service": "s3",
            "provider": "aws",
            "doc_type": "prowler_check"
        }
    }
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

        self.doc_texts: Dict[str, str] = {}
        self.doc_metadata: Dict[str, Dict[str, Any]] = {}

        self.doc_freq: Dict[str, int] = defaultdict(int)
        self.doc_lengths: Dict[str, int] = {}
        self.term_freq: Dict[str, Counter[str]] = {}

        # Exact lookup map for technical identifiers like check_id
        self.check_id_to_doc_id: Dict[str, str] = {}

        self.N: int = 0
        self.avgdl: float = 0.0

    # ----------------------------
    # Build / persistence
    # ----------------------------

    def reset(self) -> None:
        self.doc_texts.clear()
        self.doc_metadata.clear()
        self.doc_freq = defaultdict(int)
        self.doc_lengths.clear()
        self.term_freq.clear()
        self.check_id_to_doc_id.clear()
        self.N = 0
        self.avgdl = 0.0

    def build(self, docs: List[Dict[str, Any]]) -> None:
        """
        Rebuild index from scratch.
        """
        self.reset()

        for doc in docs:
            doc_id = doc.get("doc_id")
            if not doc_id:
                raise ValueError("missing doc_id in BM25 build doc")

            text = str(doc.get("text", "") or "").strip()
            metadata = dict(doc.get("metadata", {}) or {})

            self.doc_texts[doc_id] = text
            self.doc_metadata[doc_id] = metadata

            check_id = metadata.get("check_id")
            if check_id:
                normalized_check_id = normalize_query(str(check_id)).replace("-", "_")
                self.check_id_to_doc_id[normalized_check_id] = doc_id

            tokens = tokenize(text)
            self.doc_lengths[doc_id] = len(tokens)

            tf = Counter(tokens)
            self.term_freq[doc_id] = tf

            for term in tf.keys():
                self.doc_freq[term] += 1

        self.N = len(self.doc_texts)
        total_length = sum(self.doc_lengths.values())
        self.avgdl = (total_length / self.N) if self.N > 0 else 0.0

    def add_documents(self, docs: List[Dict[str, Any]]) -> None:
        """
        Kept for backwards compatibility.
        This method rebuilds the index from scratch to avoid accidental state accumulation.
        """
        self.build(docs)

    def save(self, path: Optional[Path] = None) -> Path:
        target = Path(path or BM25_INDEX_PATH)
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "k1": self.k1,
            "b": self.b,
            "doc_texts": self.doc_texts,
            "doc_metadata": self.doc_metadata,
            "doc_freq": dict(self.doc_freq),
            "doc_lengths": self.doc_lengths,
            "term_freq": {k: dict(v) for k, v in self.term_freq.items()},
            "check_id_to_doc_id": self.check_id_to_doc_id,
            "N": self.N,
            "avgdl": self.avgdl,
        }

        with target.open("wb") as f:
            pickle.dump(payload, f)

        return target

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "BM25Index":
        target = Path(path or BM25_INDEX_PATH)
        if not target.exists():
            raise FileNotFoundError(f"BM25 index file not found: {target}")

        with target.open("rb") as f:
            payload = pickle.load(f)

        index = cls(k1=payload.get("k1", 1.5), b=payload.get("b", 0.75))
        index.doc_texts = payload.get("doc_texts", {})
        index.doc_metadata = payload.get("doc_metadata", {})
        index.doc_freq = defaultdict(int, payload.get("doc_freq", {}))
        index.doc_lengths = payload.get("doc_lengths", {})
        index.term_freq = {
            doc_id: Counter(tf_map)
            for doc_id, tf_map in payload.get("term_freq", {}).items()
        }
        index.check_id_to_doc_id = payload.get("check_id_to_doc_id", {})
        index.N = payload.get("N", 0)
        index.avgdl = payload.get("avgdl", 0.0)
        return index

    # ----------------------------
    # BM25 internals
    # ----------------------------

    def _idf(self, term: str) -> float:
        df = self.doc_freq.get(term, 0)
        if df <= 0 or self.N <= 0:
            return 0.0
        return math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)

    def _score(self, query_terms: List[str], doc_id: str) -> float:
        tf_map = self.term_freq.get(doc_id)
        if not tf_map:
            return 0.0

        dl = self.doc_lengths.get(doc_id, 0)
        avgdl = self.avgdl or 1.0

        score = 0.0
        for term in query_terms:
            tf = tf_map.get(term, 0)
            if tf <= 0:
                continue

            idf = self._idf(term)
            numerator = tf * (self.k1 + 1.0)
            denominator = tf + self.k1 * (1.0 - self.b + self.b * (dl / avgdl))
            score += idf * (numerator / denominator)

        return score

    def _matches_filters(self, doc_id: str, filters: Optional[Dict[str, Any]]) -> bool:
        if not filters:
            return True

        metadata = self.doc_metadata.get(doc_id, {})
        for key, expected in filters.items():
            if expected is None:
                continue

            actual = metadata.get(key)
            if actual is None:
                return False

            if str(actual).strip().lower() != str(expected).strip().lower():
                return False

        return True

    # ----------------------------
    # Query
    # ----------------------------

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        exact_check_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Returns normalized retrieval results:
        [
            {
                "doc_id": "...",
                "score": 0.91,
                "metadata": {...},
                "matched_by": ["exact_check_id"] | ["bm25"]
            }
        ]
        """
        if self.N <= 0:
            return []

        # 1) exact lookup first
        if exact_check_id:
            normalized_check_id = normalize_query(exact_check_id).replace("-", "_")
            matched_doc_id = self.check_id_to_doc_id.get(normalized_check_id)

            if matched_doc_id and self._matches_filters(matched_doc_id, filters):
                return [
                    {
                        "doc_id": matched_doc_id,
                        "score": 1.0,
                        "metadata": self.doc_metadata.get(matched_doc_id, {}),
                        "matched_by": ["exact_check_id"],
                    }
                ]

        # 2) BM25 lexical retrieval
        query_terms = tokenize(query_text)
        if not query_terms:
            return []

        candidates: List[Dict[str, Any]] = []
        for doc_id in self.doc_texts.keys():
            if not self._matches_filters(doc_id, filters):
                continue

            score = self._score(query_terms, doc_id)
            if score <= 0:
                continue

            candidates.append(
                {
                    "doc_id": doc_id,
                    "score": score,
                    "metadata": self.doc_metadata.get(doc_id, {}),
                    "matched_by": ["bm25"],
                }
            )

        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates[: max(1, top_k)]
