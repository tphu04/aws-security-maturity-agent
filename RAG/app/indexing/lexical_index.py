from __future__ import annotations

import math
import pickle
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# from app.core.config import BM25_INDEX_PATH
from app.ingestion.normalizers import normalize_query, tokenize


def _normalize_identifier_like(value: Optional[str]) -> str:
    text = normalize_query(str(value or "")).replace("-", "_").strip("_ ")
    while "__" in text:
        text = text.replace("__", "_")
    return text


def _identifier_tokens(value: str) -> List[str]:
    normalized = _normalize_identifier_like(value)
    return [p for p in normalized.split("_") if p]


def _is_subsequence(shorter: List[str], longer: List[str]) -> bool:
    if not shorter or not longer or len(shorter) > len(longer):
        return False
    start = 0
    for token in shorter:
        try:
            idx = longer.index(token, start)
        except ValueError:
            return False
        start = idx + 1
    return True


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

        self.doc_texts: Dict[str, str] = {}
        self.doc_metadata: Dict[str, Dict[str, Any]] = {}

        self.doc_freq: Dict[str, int] = defaultdict(int)
        self.doc_lengths: Dict[str, int] = {}
        self.term_freq: Dict[str, Counter[str]] = {}

        self.check_id_to_doc_id: Dict[str, str] = {}
        self.capability_id_to_doc_ids: Dict[str, List[str]] = defaultdict(list)

        self.N: int = 0
        self.avgdl: float = 0.0

    def reset(self) -> None:
        self.doc_texts.clear()
        self.doc_metadata.clear()
        self.doc_freq = defaultdict(int)
        self.doc_lengths.clear()
        self.term_freq.clear()
        self.check_id_to_doc_id.clear()
        self.capability_id_to_doc_ids = defaultdict(list)
        self.N = 0
        self.avgdl = 0.0

    def _register_exact_keys(self, doc_id: str, metadata: Dict[str, Any]) -> None:
        check_id = metadata.get("check_id")
        if check_id:
            normalized_check_id = _normalize_identifier_like(str(check_id))
            if normalized_check_id:
                self.check_id_to_doc_id[normalized_check_id] = doc_id

        capability_id = metadata.get("capability_id")
        if capability_id:
            normalized_capability_id = _normalize_identifier_like(str(capability_id))
            if normalized_capability_id:
                self.capability_id_to_doc_ids[normalized_capability_id].append(doc_id)

        capability_name = metadata.get("capability_name") or metadata.get("title")
        if capability_name:
            normalized_capability_name = _normalize_identifier_like(
                str(capability_name)
            )
            if normalized_capability_name:
                self.capability_id_to_doc_ids[normalized_capability_name].append(doc_id)

    def build(self, docs: List[Dict[str, Any]]) -> None:
        self.reset()

        for doc in docs:
            doc_id = doc.get("doc_id")
            if not doc_id:
                raise ValueError("missing doc_id in BM25 build doc")

            text = str(doc.get("text", "") or "").strip()
            metadata = dict(doc.get("metadata", {}) or {})

            self.doc_texts[doc_id] = text
            self.doc_metadata[doc_id] = metadata
            self._register_exact_keys(doc_id, metadata)

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
        self.build(docs)

    def save(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as f:
            pickle.dump(self, f)
        return target

    @classmethod
    def load(cls, path: Path | str) -> "BM25Index":
        source = Path(path)
        with source.open("rb") as f:
            obj = pickle.load(f)

        if hasattr(obj, "__dict__"):
            state = dict(obj.__dict__)
        elif isinstance(obj, dict):
            state = dict(obj)
        else:
            raise TypeError("pickle does not contain a compatible BM25Index payload")

        instance = cls()
        for key, value in state.items():
            setattr(instance, key, value)

        if not hasattr(instance, "doc_texts") or instance.doc_texts is None:
            instance.doc_texts = {}
        if not hasattr(instance, "doc_metadata") or instance.doc_metadata is None:
            instance.doc_metadata = {}
        if not hasattr(instance, "doc_freq") or instance.doc_freq is None:
            instance.doc_freq = defaultdict(int)
        elif not isinstance(instance.doc_freq, defaultdict):
            instance.doc_freq = defaultdict(int, instance.doc_freq)

        if not hasattr(instance, "doc_lengths") or instance.doc_lengths is None:
            instance.doc_lengths = {}
        if not hasattr(instance, "term_freq") or instance.term_freq is None:
            instance.term_freq = {}

        if (
            not hasattr(instance, "check_id_to_doc_id")
            or instance.check_id_to_doc_id is None
        ):
            instance.check_id_to_doc_id = {}

        if (
            not hasattr(instance, "capability_id_to_doc_ids")
            or instance.capability_id_to_doc_ids is None
        ):
            instance.capability_id_to_doc_ids = defaultdict(list)
        elif not isinstance(instance.capability_id_to_doc_ids, defaultdict):
            instance.capability_id_to_doc_ids = defaultdict(
                list, instance.capability_id_to_doc_ids
            )

        if not hasattr(instance, "N") or instance.N is None:
            instance.N = len(instance.doc_texts or {})
        if not hasattr(instance, "avgdl") or instance.avgdl is None:
            total_length = sum((instance.doc_lengths or {}).values())
            instance.avgdl = (total_length / instance.N) if instance.N else 0.0

        instance.check_id_to_doc_id.clear()
        instance.capability_id_to_doc_ids.clear()
        for doc_id, metadata in (instance.doc_metadata or {}).items():
            instance._register_exact_keys(doc_id, metadata)

        return instance

    def _idf(self, term: str) -> float:
        df = self.doc_freq.get(term, 0)
        return math.log(1 + (self.N - df + 0.5) / (df + 0.5)) if self.N > 0 else 0.0

    def _score(self, query_terms: List[str], doc_id: str) -> float:
        if doc_id not in self.term_freq:
            return 0.0

        score = 0.0
        tf = self.term_freq[doc_id]
        dl = self.doc_lengths.get(doc_id, 0)

        for term in query_terms:
            f = tf.get(term, 0)
            if f <= 0:
                continue

            idf = self._idf(term)
            denom = (
                f + self.k1 * (1 - self.b + self.b * (dl / self.avgdl))
                if self.avgdl > 0
                else 1.0
            )
            score += idf * ((f * (self.k1 + 1)) / denom)

        return score

    def _matches_filters(self, doc_id: str, filters: Optional[Dict[str, Any]]) -> bool:
        if not filters:
            return True

        metadata = self.doc_metadata.get(doc_id, {})
        for key, expected in filters.items():
            if expected is None:
                continue
            actual = metadata.get(key)
            if str(actual).strip().lower() != str(expected).strip().lower():
                return False
        return True

    def _best_structural_capability_match(
        self,
        normalized_capability_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        query_tokens = _identifier_tokens(normalized_capability_id)
        if not query_tokens:
            return None

        candidates: List[Tuple[int, int, str]] = []

        for key, doc_ids in self.capability_id_to_doc_ids.items():
            key_tokens = _identifier_tokens(key)
            if not key_tokens:
                continue

            relation_rank: Optional[int] = None

            if key == normalized_capability_id:
                relation_rank = 4
            elif key.startswith(normalized_capability_id):
                relation_rank = 3
            elif key.endswith(normalized_capability_id):
                relation_rank = 2
            elif _is_subsequence(query_tokens, key_tokens):
                relation_rank = 1

            if relation_rank is None:
                continue

            for doc_id in doc_ids:
                if not self._matches_filters(doc_id, filters):
                    continue
                candidates.append((relation_rank, -len(key_tokens), doc_id))

        if not candidates:
            return None

        candidates.sort(reverse=True)
        return candidates[0][2]

    def _exact_capability_doc_id(
        self,
        exact_capability_id: Optional[str],
        filters: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if not exact_capability_id:
            return None

        normalized_capability_id = _normalize_identifier_like(exact_capability_id)
        if not normalized_capability_id:
            return None

        direct_doc_ids = self.capability_id_to_doc_ids.get(normalized_capability_id, [])
        for doc_id in direct_doc_ids:
            if self._matches_filters(doc_id, filters):
                return doc_id

        return self._best_structural_capability_match(
            normalized_capability_id=normalized_capability_id,
            filters=filters,
        )

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        exact_check_id: Optional[str] = None,
        exact_capability_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if self.N <= 0:
            return []

        if exact_check_id:
            normalized_check_id = _normalize_identifier_like(exact_check_id)
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

        if exact_capability_id:
            matched_doc_id = self._exact_capability_doc_id(
                exact_capability_id=exact_capability_id,
                filters=filters,
            )
            if matched_doc_id:
                return [
                    {
                        "doc_id": matched_doc_id,
                        "score": 1.0,
                        "metadata": self.doc_metadata.get(matched_doc_id, {}),
                        "matched_by": ["exact_capability_id"],
                    }
                ]

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
