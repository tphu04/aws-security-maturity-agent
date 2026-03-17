from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import (
    BM25_INDEX_PATHS,
    CHROMA_COLLECTIONS,
    CORPUS_MATURITY_CAPABILITIES,
    CORPUS_MATURITY_MAPPINGS,
    CORPUS_PROWLER_CHECKS,
    MANIFEST_PATH,
    NORMALIZED_PATHS,
)
from app.core.models import Confidence
from app.indexing.lexical_index import BM25Index
from app.indexing.vector_index import VectorIndex
from app.retrieval.confidence import calculate_confidence
from app.retrieval.router import RouteDecision, SemanticRouter
from app.retrieval.verifier import verify_retrieval


class RetrievalPipeline:
    """
    Orchestrates:
    - routing
    - exact mapping lookup
    - lexical retrieval
    - vector retrieval
    - hybrid merge
    - verification
    - confidence estimation

    Runtime is corpus-aware:
    - check_search / context_build -> prowler_checks
    - maturity_search -> maturity_capabilities
    - mapping_resolution -> maturity_mappings

    Normalized result shape:
    {
        "doc_id": "...",
        "score": 0.87,
        "metadata": {...},
        "matched_by": ["bm25"] | ["vector"] | ["bm25", "vector"] | ["exact_check_id"]
    }
    """

    def __init__(
        self,
        lexical_index: Optional[BM25Index] = None,
        vector_index: Optional[VectorIndex] = None,
        router: Optional[SemanticRouter] = None,
        lexical_indexes: Optional[Dict[str, BM25Index]] = None,
        manifest: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.vector_index = vector_index
        self.router = router or SemanticRouter()

        # Backward compatibility:
        # - old runtime may still pass lexical_index=...
        # - new runtime should prefer lexical_indexes={corpus: BM25Index()}
        if lexical_indexes is not None:
            self.lexical_indexes = lexical_indexes
        else:
            self.lexical_indexes = {}
            if lexical_index is not None:
                self.lexical_indexes[CORPUS_PROWLER_CHECKS] = lexical_index

        self._mapping_index: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self._manifest = manifest if manifest is not None else self._load_manifest()

    # ----------------------------
    # Factory helpers
    # ----------------------------

    @classmethod
    def from_storage(
        cls,
        *,
        vector_index: Optional[VectorIndex] = None,
        router: Optional[SemanticRouter] = None,
    ) -> "RetrievalPipeline":
        lexical_indexes: Dict[str, BM25Index] = {}

        for corpus_name, path in BM25_INDEX_PATHS.items():
            try:
                if Path(path).exists():
                    lexical_indexes[corpus_name] = BM25Index.load(path)
            except Exception:
                # Keep degraded runtime behavior rather than failing constructor.
                continue

        return cls(
            lexical_indexes=lexical_indexes,
            vector_index=vector_index,
            router=router,
        )

    def _load_manifest(self) -> Dict[str, Any]:
        path = Path(MANIFEST_PATH)
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    # ----------------------------
    # Readiness
    # ----------------------------

    def readiness(self) -> Dict[str, Any]:
        lexical_ready_by_corpus = {
            CORPUS_PROWLER_CHECKS: CORPUS_PROWLER_CHECKS in self.lexical_indexes,
            CORPUS_MATURITY_CAPABILITIES: CORPUS_MATURITY_CAPABILITIES
            in self.lexical_indexes,
            CORPUS_MATURITY_MAPPINGS: CORPUS_MATURITY_MAPPINGS in self.lexical_indexes,
        }

        return {
            "lexical_ready": any(lexical_ready_by_corpus.values()),
            "lexical_ready_by_corpus": lexical_ready_by_corpus,
            "vector_ready": self.vector_index is not None,
            "mapping_ready": True,
            "minimal_ready": any(lexical_ready_by_corpus.values()),
            "hybrid_ready": any(lexical_ready_by_corpus.values())
            and self.vector_index is not None,
        }

    def is_ready(self) -> bool:
        # lexical-only remains acceptable degraded runtime
        return any(self.lexical_indexes.values())

    # ----------------------------
    # Public entrypoint
    # ----------------------------

    def retrieve(
        self,
        query: str,
        explicit_type: Optional[str] = None,
        provider: str = "aws",
        service: Optional[str] = None,
        domain: Optional[str] = None,
        top_k: int = 5,
        retrieval_mode: str = "hybrid",
    ) -> Dict[str, Any]:
        if not self.is_ready():
            raise RuntimeError(
                "retrieval pipeline is not ready: at least one lexical index is required"
            )

        route = self.router.route(
            query=query,
            explicit_type=explicit_type,
            provider=provider,
            service=service,
            domain=domain,
        )

        corpus_name = self._corpus_for_route(route)
        collection_name = self._collection_name_for_route(route)

        lexical_results: List[Dict[str, Any]] = []
        vector_results: List[Dict[str, Any]] = []
        vector_error: Optional[str] = None
        search_top_k = max(top_k * 3, 10)

        # mapping resolution stays exact-first by design
        if route.query_type == "mapping_resolution":
            results = self._resolve_mapping_exact(route)

            verification = verify_retrieval(
                route_info=route.__dict__,
                results=results,
                mapping_exists=bool(results),
            )
            confidence = calculate_confidence(
                results=results,
                route_info=route.__dict__,
                verification=verification,
            )

            return self._build_response(
                route=route,
                results=results[: max(1, top_k)],
                verification=verification,
                confidence=confidence,
                degraded=not self.readiness()["hybrid_ready"],
                corpus_name=corpus_name,
                collection_name=collection_name,
                extra_diagnostics={
                    "retrieval_mode": "exact_mapping",
                    "lexical_candidate_count": 0,
                    "vector_candidate_count": 0,
                    "top_lexical_doc_ids": [],
                    "top_vector_doc_ids": [],
                    "used_vector": False,
                    "used_hybrid": False,
                    "vector_error": None,
                },
            )

        if retrieval_mode in {"lexical", "hybrid"}:
            lexical_results = self._run_lexical(route=route, top_k=search_top_k)

        if retrieval_mode in {"vector", "hybrid"}:
            try:
                vector_results = self._run_vector(route=route, top_k=search_top_k)
            except Exception as exc:
                vector_results = []
                vector_error = f"{type(exc).__name__}: {exc}"

        if retrieval_mode == "lexical":
            merged_results = lexical_results[:top_k]
        elif retrieval_mode == "vector":
            merged_results = vector_results[:top_k]
        else:
            merged_results = self._merge_results(
                lexical_results=lexical_results,
                vector_results=vector_results,
                top_k=top_k,
            )

        mapping_exists = None
        if route.query_type in {"check_search", "context_build"}:
            mapping_exists = self._mapping_exists_for_results(merged_results)

        verification = verify_retrieval(
            route_info=route.__dict__,
            results=merged_results,
            mapping_exists=mapping_exists,
        )

        confidence = calculate_confidence(
            results=merged_results,
            route_info=route.__dict__,
            verification=verification,
        )

        return self._build_response(
            route=route,
            results=merged_results,
            verification=verification,
            confidence=confidence,
            degraded=not self.readiness()["hybrid_ready"],
            corpus_name=corpus_name,
            collection_name=collection_name,
            extra_diagnostics={
                "retrieval_mode": retrieval_mode,
                "lexical_candidate_count": len(lexical_results),
                "vector_candidate_count": len(vector_results),
                "top_lexical_doc_ids": [r.get("doc_id") for r in lexical_results[:5]],
                "top_vector_doc_ids": [r.get("doc_id") for r in vector_results[:5]],
                "used_vector": len(vector_results) > 0,
                "used_hybrid": retrieval_mode == "hybrid" and len(vector_results) > 0,
                "vector_error": vector_error,
            },
        )

    # ----------------------------
    # Exact mapping path
    # ----------------------------

    def _resolve_mapping_exact(self, route: RouteDecision) -> List[Dict[str, Any]]:
        if not route.exact_check_id:
            return []

        candidates = self._get_mapping_index().get(route.exact_check_id, [])
        if not candidates:
            return []

        filtered = self._filter_mapping_candidates(route, candidates)
        if not filtered:
            return []

        ranked = sorted(filtered, key=self._mapping_sort_key, reverse=True)
        best = ranked[0]
        metadata = dict(best)
        metadata.setdefault("doc_type", "maturity_mapping")

        return [
            {
                "doc_id": best.get(
                    "doc_id",
                    f"mapping:{route.exact_check_id}:{best.get('capability_id', 'unknown')}",
                ),
                "score": 1.0,
                "metadata": metadata,
                "matched_by": ["exact_mapping"],
            }
        ]

    def _filter_mapping_candidates(
        self,
        route: RouteDecision,
        candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        filtered = list(candidates)

        if route.service:
            route_service = str(route.service).strip().lower()
            filtered = [
                item
                for item in filtered
                if not str(item.get("service", "")).strip()
                or str(item.get("service", "")).strip().lower() == route_service
            ]

        if route.domain:
            route_domain = str(route.domain).strip().lower()
            domain_filtered = [
                item
                for item in filtered
                if str(item.get("domain", "")).strip().lower() == route_domain
            ]
            if domain_filtered:
                filtered = domain_filtered

        return filtered

    @staticmethod
    def _mapping_sort_key(item: Dict[str, Any]) -> tuple:
        confidence_rank = {
            "high": 3,
            "medium": 2,
            "low": 1,
        }
        review_rank = {
            "approved": 3,
            "reviewed": 2,
            "review_required": 1,
            "unreviewed": 0,
        }
        return (
            confidence_rank.get(
                str(item.get("mapping_confidence", "low")).strip().lower(),
                1,
            ),
            review_rank.get(
                str(item.get("review_status", "unreviewed")).strip().lower(),
                0,
            ),
            float(item.get("score", 0.0) or 0.0),
        )

    # ----------------------------
    # Lexical / vector execution
    # ----------------------------

    def _run_lexical(self, route: RouteDecision, top_k: int) -> List[Dict[str, Any]]:
        corpus_name = self._corpus_for_route(route)
        lexical_index = self.lexical_indexes.get(corpus_name)
        if lexical_index is None:
            return []

        exact_check_id = route.exact_check_id if route.requires_exact_lookup else None
        return lexical_index.query(
            query_text=route.normalized_query,
            top_k=top_k,
            filters=route.filters,
            exact_check_id=exact_check_id,
        )

    def _run_vector(self, route: RouteDecision, top_k: int) -> List[Dict[str, Any]]:
        if self.vector_index is None:
            return []

        collection_name = self._collection_name_for_route(route)
        if not collection_name:
            return []

        try:
            return self.vector_index.query(
                name=collection_name,
                query_text=route.normalized_query,
                top_k=top_k,
                filters=route.filters,
            )
        except Exception as exc:
            # Graceful degradation: vector failure should not kill retrieval if lexical works.
            raise RuntimeError(f"vector_search_failed: {exc}") from exc

    @staticmethod
    def _corpus_for_route(route: RouteDecision) -> str:
        if route.query_type == "maturity_search":
            return CORPUS_MATURITY_CAPABILITIES
        if route.query_type == "mapping_resolution":
            return CORPUS_MATURITY_MAPPINGS
        if route.query_type in {"check_search", "context_build"}:
            return CORPUS_PROWLER_CHECKS
        return CORPUS_PROWLER_CHECKS

    def _collection_name_for_route(self, route: RouteDecision) -> Optional[str]:
        corpus_name = self._corpus_for_route(route)

        manifest_collection = (
            self._manifest.get("corpora", {})
            .get(corpus_name, {})
            .get("chroma_collection")
        )
        if manifest_collection:
            return str(manifest_collection)

        return CHROMA_COLLECTIONS.get(corpus_name)

    # ----------------------------
    # Merge
    # ----------------------------

    def _merge_results(
        self,
        lexical_results: List[Dict[str, Any]],
        vector_results: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}

        # BM25-first weighting because technical IDs / exact lexical terms matter a lot here
        lexical_weight = 0.60
        vector_weight = 0.40

        for item in lexical_results:
            doc_id = item["doc_id"]
            merged[doc_id] = {
                "doc_id": doc_id,
                "score": float(item.get("score", 0.0)) * lexical_weight,
                "metadata": item.get("metadata", {}) or {},
                "matched_by": list(item.get("matched_by", []) or []),
                "_raw_lexical_score": float(item.get("score", 0.0)),
                "_raw_vector_score": 0.0,
            }

        for item in vector_results:
            doc_id = item["doc_id"]
            vector_score = float(item.get("score", 0.0))
            if doc_id not in merged:
                merged[doc_id] = {
                    "doc_id": doc_id,
                    "score": vector_score * vector_weight,
                    "metadata": item.get("metadata", {}) or {},
                    "matched_by": list(item.get("matched_by", []) or []),
                    "_raw_lexical_score": 0.0,
                    "_raw_vector_score": vector_score,
                }
            else:
                merged[doc_id]["score"] += vector_score * vector_weight
                merged[doc_id]["_raw_vector_score"] = vector_score
                merged[doc_id]["matched_by"] = sorted(
                    set(merged[doc_id]["matched_by"])
                    | set(item.get("matched_by", []) or [])
                )
                if not merged[doc_id]["metadata"] and item.get("metadata"):
                    merged[doc_id]["metadata"] = item["metadata"]

        results = list(merged.values())
        results.sort(key=lambda x: x["score"], reverse=True)

        trimmed: List[Dict[str, Any]] = []
        for item in results[: max(1, top_k)]:
            trimmed.append(
                {
                    "doc_id": item["doc_id"],
                    "score": round(float(item["score"]), 6),
                    "metadata": item.get("metadata", {}) or {},
                    "matched_by": item.get("matched_by", []) or [],
                }
            )
        return trimmed

    # ----------------------------
    # Mapping support
    # ----------------------------

    def _mapping_exists_for_results(
        self,
        results: List[Dict[str, Any]],
    ) -> Optional[bool]:
        if not results:
            return None
        top1_meta = results[0].get("metadata", {}) or {}
        check_id = str(top1_meta.get("check_id", "")).strip().lower()
        if not check_id:
            return None
        return check_id in self._get_mapping_index()

    def _get_mapping_index(self) -> Dict[str, List[Dict[str, Any]]]:
        if self._mapping_index is not None:
            return self._mapping_index

        path = Path(NORMALIZED_PATHS[CORPUS_MATURITY_MAPPINGS])
        if not path.exists():
            self._mapping_index = {}
            return self._mapping_index

        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        index: Dict[str, List[Dict[str, Any]]] = {}
        for item in payload:
            check_id = str(item.get("check_id", "")).strip().lower()
            if not check_id:
                continue
            index.setdefault(check_id, []).append(item)

        self._mapping_index = index
        return self._mapping_index

    # ----------------------------
    # Response shaping
    # ----------------------------

    def _build_response(
        self,
        route: RouteDecision,
        results: List[Dict[str, Any]],
        verification: Dict[str, Any],
        confidence: Confidence,
        degraded: bool,
        corpus_name: str,
        collection_name: Optional[str],
        extra_diagnostics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        meta = {
            "confidence": (
                confidence.value if hasattr(confidence, "value") else str(confidence)
            ),
            "verification": verification,
            "degraded": degraded,
            "readiness": self.readiness(),
            "index_version": self._manifest.get("index_version", "unknown"),
            "routing": {
                "requires_exact_lookup": route.requires_exact_lookup,
                "exact_check_id": route.exact_check_id,
                "service": route.service,
                "domain": route.domain,
                "provider": route.provider,
                "doc_types": route.doc_types,
                "corpus": corpus_name,
                "collection_name": collection_name,
            },
            "diagnostics": {
                "corpus": corpus_name,
                "collection_name": collection_name,
            },
        }

        if extra_diagnostics:
            meta["diagnostics"].update(extra_diagnostics)

        return {
            "query": route.normalized_query,
            "query_type": route.query_type,
            "filters": route.filters,
            "results": results,
            "meta": meta,
        }
