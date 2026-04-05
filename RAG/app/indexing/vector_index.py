from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import CHROMA_DIR, EMBEDDING_MODEL

try:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    _CHROMADB_AVAILABLE = True
except ImportError:  # pragma: no cover
    chromadb = None
    SentenceTransformerEmbeddingFunction = None
    _CHROMADB_AVAILABLE = False


class VectorIndex:
    """
    Chroma-backed vector index.

    Expected input doc shape:
    {
        "doc_id": "capability:public_data_exposure_prevention",
        "text": "... canonical retrieval text ...",
        "metadata": {
            "doc_type": "maturity_capability",
            "domain": "Data Protection",
            "provider": "aws"
        }
    }

    Note:
    - This class currently uses Chroma persistent collections.
    - `embedding_model` is tracked as configuration intent.
    - If you want strict control over the embedding backend, bind an explicit
      embedding function at collection creation time in a later step.
    """

    def __init__(
        self,
        persist_dir: Optional[Path] = None,
        embedding_model: Optional[str] = None,
    ) -> None:
        if not _CHROMADB_AVAILABLE:
            raise RuntimeError(
                "ChromaDB is not installed. Install it before using VectorIndex."
            )

        self.persist_dir = Path(persist_dir or CHROMA_DIR)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.embedding_model = embedding_model or EMBEDDING_MODEL
        # Suppress noisy model-loading logs (progress bar, LOAD REPORT)
        _loggers_to_quiet = [
            "sentence_transformers",
            "transformers",
            "transformers.utils.loading_report",
            "torch",
        ]
        _prev_levels = {n: logging.getLogger(n).level for n in _loggers_to_quiet}
        for n in _loggers_to_quiet:
            logging.getLogger(n).setLevel(logging.ERROR)
        _prev_tqdm = os.environ.get("TQDM_DISABLE")
        os.environ["TQDM_DISABLE"] = "1"

        self._embedding_fn = SentenceTransformerEmbeddingFunction(
            model_name=self.embedding_model
        )

        # Restore original log levels and tqdm state
        for n, lvl in _prev_levels.items():
            logging.getLogger(n).setLevel(lvl)
        if _prev_tqdm is None:
            os.environ.pop("TQDM_DISABLE", None)
        else:
            os.environ["TQDM_DISABLE"] = _prev_tqdm
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))

    # ----------------------------
    # Helpers
    # ----------------------------

    def _normalize_metadata(self, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in (metadata or {}).items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                normalized[key] = value
            else:
                normalized[key] = str(value)
        return normalized

    def _build_where(
        self, filters: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not filters:
            return None

        clauses: List[Dict[str, Any]] = []
        for key, value in filters.items():
            if value is None:
                continue
            clauses.append({key: {"$eq": value}})

        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    @staticmethod
    def _distance_to_score(distance: Optional[float]) -> float:
        """
        Convert distance to a normalized similarity-like score.
        Lower distance => higher score.
        """
        if distance is None:
            return 0.0
        return 1.0 / (1.0 + float(distance))

    # ----------------------------
    # Collection lifecycle
    # ----------------------------

    def delete_collection(self, name: str) -> None:
        try:
            self.client.delete_collection(name=name)
        except Exception:
            # Safe to ignore if collection does not exist.
            pass

    def get_collection(self, name: str):
        return self.client.get_collection(
            name=name, embedding_function=self._embedding_fn
        )

    def build_collection(self, name: str, docs: List[Dict[str, Any]]):
        """
        Recreate collection from scratch.
        """
        if not name or not name.strip():
            raise ValueError("collection name must not be empty")
        if not docs:
            raise ValueError("docs must not be empty")

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for doc in docs:
            doc_id = doc.get("doc_id")
            if not doc_id:
                raise ValueError("missing doc_id in vector build doc")

            text = str(doc.get("text", "") or "").strip()
            metadata = self._normalize_metadata(doc.get("metadata", {}))

            ids.append(str(doc_id))
            documents.append(text)
            metadatas.append(metadata)

        self.delete_collection(name)
        collection = self.client.create_collection(
            name=name, embedding_function=self._embedding_fn
        )
        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        return collection

    # ----------------------------
    # Query
    # ----------------------------

    def query(
        self,
        name: str,
        query_text: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Returns normalized retrieval results:
        [
            {
                "doc_id": "...",
                "score": 0.84,
                "metadata": {...},
                "matched_by": ["vector"]
            }
        ]
        """
        if not query_text or not query_text.strip():
            return []

        collection = self.get_collection(name)
        where = self._build_where(filters)

        raw = collection.query(
            query_texts=[query_text],
            n_results=max(1, top_k),
            where=where,
        )

        ids = raw.get("ids", [[]])
        metadatas = raw.get("metadatas", [[]])
        distances = raw.get("distances", [[]])

        first_ids = ids[0] if ids else []
        first_metadatas = metadatas[0] if metadatas else []
        first_distances = distances[0] if distances else []

        results: List[Dict[str, Any]] = []
        for idx, doc_id in enumerate(first_ids):
            metadata = first_metadatas[idx] if idx < len(first_metadatas) else {}
            distance = first_distances[idx] if idx < len(first_distances) else None

            results.append(
                {
                    "doc_id": doc_id,
                    "score": self._distance_to_score(distance),
                    "metadata": metadata or {},
                    "matched_by": ["vector"],
                }
            )

        return results
