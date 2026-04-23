from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
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
    load_scoring_config,
)
from app.core.constants import PRODUCT_ENTITY_GATES
from app.core.models import Confidence
from app.core.utils import mapping_sort_key
from app.indexing.lexical_index import BM25Index
from app.indexing.vector_index import VectorIndex
from app.retrieval.confidence import calculate_confidence
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.router import RouteDecision, SemanticRouter
from app.retrieval.verifier import verify_retrieval

logger = logging.getLogger(__name__)


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
        lexical_indexes: Optional[Dict[str, BM25Index]] = None,
        vector_index: Optional[VectorIndex] = None,
        router: Optional[SemanticRouter] = None,
        manifest: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.vector_index = vector_index
        self.router = router or SemanticRouter()
        self.lexical_indexes = lexical_indexes or {}
        self._mapping_index: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self._manifest = manifest if manifest is not None else self._load_manifest()
        self._doc_store: Optional[Dict[str, Dict[str, Any]]] = None
        self._scoring = load_scoring_config()

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

    def _get_doc_store(self) -> Dict[str, Dict[str, Any]]:
        if self._doc_store is not None:
            return self._doc_store

        store: Dict[str, Dict[str, Any]] = {}

        for _, path in NORMALIZED_PATHS.items():
            p = Path(path)
            if not p.exists():
                continue

            try:
                with p.open("r", encoding="utf-8") as f:
                    payload = json.load(f)

                if isinstance(payload, list):
                    for item in payload:
                        if not isinstance(item, dict):
                            continue
                        doc_id = str(item.get("doc_id", "")).strip()
                        if doc_id:
                            store[doc_id] = item
            except Exception:
                # degraded runtime: skip bad file rather than failing retrieval
                continue

        self._doc_store = store
        return self._doc_store

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

        # --- Auto-translate non-English queries ---
        from app.retrieval.query_translator import maybe_translate_query

        effective_query, was_translated = maybe_translate_query(query)
        original_query = query if was_translated else None

        route = self.router.route(
            query=effective_query,
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
        search_top_k = max(
            top_k * self._scoring["search_top_k_multiplier"],
            self._scoring["search_top_k_minimum"],
        )

        # mapping resolution stays exact-first by design
        if route.query_type == "mapping_resolution":
            results = self._resolve_mapping_exact(route)
            results = self._hydrate_results(results)

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

        # maturity capability lookup should also prefer exact capability_id
        if route.query_type == "maturity_search" and route.exact_capability_id:
            results = self._resolve_maturity_exact(route)
            results = self._hydrate_results(results)

            verification = verify_retrieval(
                route_info=route.__dict__,
                results=results,
                mapping_exists=None,
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
                    "retrieval_mode": "exact_maturity",
                    "lexical_candidate_count": len(results),
                    "vector_candidate_count": 0,
                    "top_lexical_doc_ids": [r.get("doc_id") for r in results[:5]],
                    "top_vector_doc_ids": [],
                    "used_vector": False,
                    "used_hybrid": False,
                    "vector_error": None,
                },
            )

        # ----- LLM query expansion (rewrite + HyDE) -----
        hyde_text: Optional[str] = None
        rewrite_variants: List[str] = []

        if retrieval_mode in ("hybrid", "vector") and not route.requires_exact_lookup:
            from app.retrieval.hyde import maybe_generate_hyde
            from app.retrieval.query_rewriter import maybe_rewrite_query

            # Launch rewrite + HyDE concurrently (both are LLM calls)
            with ThreadPoolExecutor(max_workers=2) as exp_pool:
                hyde_fut = exp_pool.submit(
                    maybe_generate_hyde,
                    query=route.normalized_query,
                    requires_exact_lookup=route.requires_exact_lookup,
                )
                rw_fut = exp_pool.submit(
                    maybe_rewrite_query,
                    query=route.normalized_query,
                    requires_exact_lookup=route.requires_exact_lookup,
                )
                hyde_text = hyde_fut.result()
                rewrite_variants = rw_fut.result()

        # ----- Multi-query BM25: original + rewrite variants -----
        if retrieval_mode == "hybrid":
            with ThreadPoolExecutor(max_workers=2 + len(rewrite_variants)) as executor:
                # Original BM25 search
                lex_future = executor.submit(
                    self._run_lexical, route=route, top_k=search_top_k
                )
                # Vector search (with HyDE override if available)
                vec_future = executor.submit(
                    self._run_vector,
                    route=route,
                    top_k=search_top_k,
                    query_override=hyde_text,
                )
                # Additional BM25 searches for rewrite variants
                rw_lex_futures = [
                    executor.submit(
                        self._run_lexical_with_query,
                        route=route,
                        query_text=variant,
                        top_k=search_top_k,
                    )
                    for variant in rewrite_variants
                ]

                lexical_results = lex_future.result()
                try:
                    vector_results = vec_future.result()
                except Exception as exc:
                    vector_results = []
                    vector_error = f"{type(exc).__name__}: {exc}"

                # Merge rewrite BM25 results into lexical_results
                for rw_fut in rw_lex_futures:
                    try:
                        rw_results = rw_fut.result()
                        lexical_results = self._merge_lexical_variants(
                            lexical_results, rw_results
                        )
                    except Exception:
                        pass

        elif retrieval_mode == "lexical":
            lexical_results = self._run_lexical(route=route, top_k=search_top_k)
            # Also run rewrite variants for lexical-only mode
            for variant in rewrite_variants:
                try:
                    rw_results = self._run_lexical_with_query(
                        route=route, query_text=variant, top_k=search_top_k
                    )
                    lexical_results = self._merge_lexical_variants(
                        lexical_results, rw_results
                    )
                except Exception:
                    pass
        elif retrieval_mode == "vector":
            try:
                vector_results = self._run_vector(
                    route=route, top_k=search_top_k, query_override=hyde_text,
                )
            except Exception as exc:
                vector_results = []
                vector_error = f"{type(exc).__name__}: {exc}"

        if retrieval_mode == "lexical":
            merged_results = self._hydrate_results(lexical_results[:top_k])
            reranker_diag = {}
        elif retrieval_mode == "vector":
            merged_results = self._hydrate_results(vector_results[:top_k])
            reranker_diag = {}
        else:
            merged_results, reranker_diag = self._merge_results(
                lexical_results=lexical_results,
                vector_results=vector_results,
                top_k=top_k,
                query=route.normalized_query,
                preferred_service=route.service,
                preferred_domain=route.domain,
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
                "hyde_used": hyde_text is not None,
                "rewrite_variants": rewrite_variants if rewrite_variants else None,
                "translated_from": original_query,
                **reranker_diag,
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

        ranked = sorted(filtered, key=mapping_sort_key, reverse=True)
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


    # ----------------------------
    # Lexical / vector execution
    # ----------------------------

    def _run_lexical(self, route: RouteDecision, top_k: int) -> List[Dict[str, Any]]:
        corpus_name = self._corpus_for_route(route)
        lexical_index = self.lexical_indexes.get(corpus_name)
        if lexical_index is None:
            return []

        exact_check_id = route.exact_check_id if route.requires_exact_lookup else None
        exact_capability_id = (
            route.exact_capability_id if route.requires_exact_lookup else None
        )

        return lexical_index.query(
            query_text=route.normalized_query,
            top_k=top_k,
            filters=route.filters,
            exact_check_id=exact_check_id,
            exact_capability_id=exact_capability_id,
        )

    def _run_lexical_with_query(
        self, route: RouteDecision, query_text: str, top_k: int,
    ) -> List[Dict[str, Any]]:
        """Run BM25 search with an explicit query string (for rewrite variants)."""
        corpus_name = self._corpus_for_route(route)
        lexical_index = self.lexical_indexes.get(corpus_name)
        if lexical_index is None:
            return []
        return lexical_index.query(
            query_text=query_text,
            top_k=top_k,
            filters=route.filters,
        )

    @staticmethod
    def _merge_lexical_variants(
        primary: List[Dict[str, Any]],
        additional: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Merge additional BM25 results into primary list.

        Keeps the primary order intact.  Appends any new doc_ids from
        *additional* that are not already in *primary*, with a small score
        discount (×0.8) to rank them below primary hits for the same doc.
        """
        seen = {item["doc_id"] for item in primary if item.get("doc_id")}
        for item in additional:
            doc_id = item.get("doc_id")
            if doc_id and doc_id not in seen:
                seen.add(doc_id)
                discounted = dict(item)
                discounted["score"] = float(item.get("score", 0)) * 0.8
                discounted.setdefault("matched_by", [])
                if "bm25_rewrite" not in discounted["matched_by"]:
                    discounted["matched_by"] = list(discounted["matched_by"]) + [
                        "bm25_rewrite"
                    ]
                primary.append(discounted)
        return primary

    def _run_vector(
        self,
        route: RouteDecision,
        top_k: int,
        query_override: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if self.vector_index is None:
            return []

        collection_name = self._collection_name_for_route(route)
        if not collection_name:
            return []

        query_text = query_override or route.normalized_query

        try:
            return self.vector_index.query(
                name=collection_name,
                query_text=query_text,
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

    def _rrf(self, rank: int) -> float:
        k = self._scoring["rrf"]["k"]
        return 1.0 / (k + rank)

    @staticmethod
    def _has_exact_match(item: Dict[str, Any]) -> bool:
        matched_by = set(item.get("matched_by", []) or [])
        return bool(
            {"exact_check_id", "exact_capability_id", "exact_mapping"} & matched_by
        )

    def _metadata_bonus(
        self,
        metadata: Dict[str, Any],
        preferred_service: Optional[str],
        preferred_domain: Optional[str],
    ) -> float:
        bonus = 0.0
        meta_cfg = self._scoring["metadata_bonus"]

        if preferred_service:
            actual_service = str(metadata.get("service", "") or "").strip().lower()
            if (
                actual_service
                and actual_service == str(preferred_service).strip().lower()
            ):
                bonus += meta_cfg["service_match"]

        if preferred_domain:
            actual_domain = str(metadata.get("domain", "") or "").strip().lower()
            if actual_domain and actual_domain == str(preferred_domain).strip().lower():
                bonus += meta_cfg["domain_match"]

        return bonus

    @staticmethod
    def _extract_rich_metadata(doc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            # common
            "doc_id": doc.get("doc_id"),
            "doc_type": doc.get("doc_type"),
            "provider": doc.get("provider"),
            "service": doc.get("service"),
            "domain": doc.get("domain"),
            "capability_id": doc.get("capability_id"),
            "capability_name": doc.get("capability_name"),
            "check_id": doc.get("check_id"),
            "source_name": doc.get("source_name"),
            "source_type": doc.get("source_type"),
            "index_version": doc.get("index_version"),
            "retrieval_text": doc.get("retrieval_text"),
            "embedding_text": doc.get("embedding_text"),
            "reranker_text": doc.get("reranker_text"),

            # prowler_check
            "title": doc.get("title"),
            "severity": doc.get("severity"),
            "description": doc.get("description"),
            "risk": doc.get("risk"),
            "remediation": doc.get("remediation"),
            "remediation_recommendation": doc.get("remediation_recommendation"),
            "remediation_url": doc.get("remediation_url"),
            "resource_type": doc.get("resource_type"),
            "keywords": doc.get("keywords"),
            "synonyms": doc.get("synonyms"),

            # maturity_capability
            "stage": doc.get("stage"),
            "summary": doc.get("summary"),
            "risk_explanation": doc.get("risk_explanation"),
            "guidance": doc.get("guidance"),
            "how_to_check": doc.get("how_to_check"),
            "recommended_practices": doc.get("recommended_practices"),

            # maturity_mapping
            "mapping_confidence": doc.get("mapping_confidence"),
            "mapping_reason": doc.get("mapping_reason"),
            "review_status": doc.get("review_status"),
            "mapping_type": doc.get("mapping_type"),
            "assessment_weight_hint": doc.get("assessment_weight_hint"),
            "report_note": doc.get("report_note"),
        }

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

    @staticmethod
    def _doc_signal_text(metadata: Dict[str, Any]) -> str:
        return " ".join(
            str(metadata.get(key) or "")
            for key in (
                "check_id",
                "capability_id",
                "service",
                "domain",
                "title",
                "description",
                "risk",
                "remediation",
                "summary",
                "guidance",
                "how_to_check",
                "mapping_reason",
            )
        ).lower()

    @staticmethod
    def _product_gate_pass(query: str, metadata: Dict[str, Any]) -> bool:
        """Return True if the candidate is allowed (no entity gate violation)."""
        query_text = (query or "").lower()
        doc_text = RetrievalPipeline._doc_signal_text(metadata)
        for entity_token, required_signals in PRODUCT_ENTITY_GATES.items():
            if entity_token in doc_text and not any(
                signal in query_text for signal in required_signals
            ):
                return False
        return True

    def _merge_results(
        self,
        lexical_results: List[Dict[str, Any]],
        vector_results: List[Dict[str, Any]],
        top_k: int,
        query: str,
        preferred_service: Optional[str] = None,
        preferred_domain: Optional[str] = None,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Merge lexical + vector candidates via hybrid fusion, then cross-encoder rerank.

        Flow:
        1. Hybrid fusion — RRF (rank-only) or RSF (rank + normalized score)
        2. Separate exact matches (score = exact_match_bonus, skip reranking)
        3. Product gate filter (binary — remove violating candidates)
        4. Hydrate candidates (load retrieval_text for cross-encoder)
        5. Cross-encoder rerank non-exact candidates
        6. Add metadata bonus on top of cross-encoder scores
        7. Prepend exact matches, truncate to top_k

        Returns:
            Tuple of (merged results, reranker diagnostics dict).
        """
        # ---- Step 1: Hybrid fusion (RRF or RSF) ----
        merged: Dict[str, Dict[str, Any]] = {}

        lexical_rank_map = {
            item["doc_id"]: rank
            for rank, item in enumerate(lexical_results, start=1)
            if item.get("doc_id")
        }
        vector_rank_map = {
            item["doc_id"]: rank
            for rank, item in enumerate(vector_results, start=1)
            if item.get("doc_id")
        }

        # Build raw-score lookup for RSF
        lexical_score_map = {
            item["doc_id"]: float(item.get("score", 0))
            for item in lexical_results
            if item.get("doc_id")
        }
        vector_score_map = {
            item["doc_id"]: float(item.get("score", 0))
            for item in vector_results
            if item.get("doc_id")
        }

        all_doc_ids = list(
            dict.fromkeys(
                list(lexical_rank_map.keys()) + list(vector_rank_map.keys())
            )
        )

        # RSF: normalize BM25 scores to [0, 1] via min-max
        fusion_cfg = self._scoring.get("fusion", {})
        fusion_method = fusion_cfg.get("method", "rrf")
        alpha = float(fusion_cfg.get("alpha", 0.7))

        lex_scores = list(lexical_score_map.values())
        lex_min = min(lex_scores) if lex_scores else 0.0
        lex_max = max(lex_scores) if lex_scores else 1.0
        lex_range = lex_max - lex_min if lex_max > lex_min else 1.0

        for doc_id in all_doc_ids:
            lexical_item = next(
                (x for x in lexical_results if x.get("doc_id") == doc_id), None
            )
            vector_item = next(
                (x for x in vector_results if x.get("doc_id") == doc_id), None
            )

            metadata: Dict[str, Any] = {}
            matched_by: set[str] = set()

            if lexical_item:
                metadata = lexical_item.get("metadata", {}) or {}
                matched_by.update(lexical_item.get("matched_by", []) or [])
            if vector_item:
                if not metadata:
                    metadata = vector_item.get("metadata", {}) or {}
                matched_by.update(vector_item.get("matched_by", []) or [])

            rrf_score = 0.0
            if doc_id in lexical_rank_map:
                rrf_score += self._rrf(lexical_rank_map[doc_id])
            if doc_id in vector_rank_map:
                rrf_score += self._rrf(vector_rank_map[doc_id])

            # Compute final fusion score
            if fusion_method == "rsf":
                max_norm_score = 0.0
                if doc_id in lexical_score_map:
                    max_norm_score = max(
                        max_norm_score,
                        (lexical_score_map[doc_id] - lex_min) / lex_range,
                    )
                if doc_id in vector_score_map:
                    # Vector scores are already in [0, 1]
                    max_norm_score = max(
                        max_norm_score, vector_score_map[doc_id]
                    )
                fusion_score = alpha * rrf_score + (1 - alpha) * max_norm_score
            else:
                fusion_score = rrf_score

            is_exact = False
            if lexical_item and self._has_exact_match(lexical_item):
                is_exact = True
            if vector_item and self._has_exact_match(vector_item):
                is_exact = True

            merged[doc_id] = {
                "doc_id": doc_id,
                "score": fusion_score,
                "metadata": metadata,
                "matched_by": sorted(matched_by),
                "_is_exact": is_exact,
            }

        # ---- Step 2: Separate exact matches ----
        exact_match_bonus = self._scoring["exact_match_bonus"]
        exact_results = []
        semantic_candidates = []

        for item in merged.values():
            if item.pop("_is_exact", False):
                item["score"] = exact_match_bonus
                exact_results.append(item)
            else:
                semantic_candidates.append(item)

        # ---- Step 3: Product gate filter ----
        if self._scoring.get("product_gate") == "filter":
            before_count = len(semantic_candidates)
            semantic_candidates = [
                c for c in semantic_candidates
                if self._product_gate_pass(query, c.get("metadata", {}))
            ]
            filtered_count = before_count - len(semantic_candidates)
            if filtered_count:
                logger.debug(
                    "Product gate filtered %d candidates", filtered_count
                )

        # ---- Step 4: Hydrate candidates ----
        exact_results = self._hydrate_results(exact_results)
        semantic_candidates = self._hydrate_results(semantic_candidates)

        # ---- Step 5: Cross-encoder rerank ----
        reranker_cfg = self._scoring.get("reranker", {})
        reranker_diag: Dict[str, Any] = {}

        # Capture pre-rerank order (RRF order before CrossEncoder)
        pre_rerank_ids = [c.get("doc_id", "") for c in semantic_candidates[:top_k]]

        if reranker_cfg.get("enabled", False) and semantic_candidates:
            model_name = reranker_cfg.get(
                "model", "cross-encoder/ms-marco-MiniLM-L-6-v2"
            )
            rerank_top_n = reranker_cfg.get("top_n", 20)

            try:
                reranker = CrossEncoderReranker.get_instance(model_name)
                semantic_candidates = reranker.rerank(
                    query=query,
                    candidates=semantic_candidates,
                    top_n=rerank_top_n,
                )
                reranker_diag["reranker_applied"] = True
            except Exception as exc:
                logger.warning(
                    "Cross-encoder rerank failed, falling back to RRF: %s", exc
                )
                # Fallback: keep RRF order
                semantic_candidates.sort(
                    key=lambda x: x.get("score", 0.0), reverse=True
                )
                reranker_diag["reranker_applied"] = False
                reranker_diag["reranker_error"] = str(exc)
        else:
            # Reranker disabled — sort by pure RRF score
            semantic_candidates.sort(
                key=lambda x: x.get("score", 0.0), reverse=True
            )
            reranker_diag["reranker_applied"] = False

        # Capture post-rerank order
        post_rerank_ids = [c.get("doc_id", "") for c in semantic_candidates[:top_k]]

        reranker_diag["reranker_pre_order"] = pre_rerank_ids
        reranker_diag["reranker_post_order"] = post_rerank_ids

        # ---- Step 6: Metadata bonus ----
        for item in semantic_candidates:
            item["score"] += self._metadata_bonus(
                metadata=item.get("metadata", {}),
                preferred_service=preferred_service,
                preferred_domain=preferred_domain,
            )

        # ---- Step 7: Combine and truncate ----
        final = exact_results + semantic_candidates
        return final[:top_k], reranker_diag

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

    def _resolve_maturity_exact(self, route: RouteDecision) -> List[Dict[str, Any]]:
        if not route.exact_capability_id:
            return []

        corpus_name = CORPUS_MATURITY_CAPABILITIES
        lexical_index = self.lexical_indexes.get(corpus_name)

        if lexical_index is None:
            return []

        results = lexical_index.query(
            query_text=route.exact_capability_id,
            top_k=1,
            exact_capability_id=route.exact_capability_id,
            filters=route.filters,
        )

        return results or []
    
    
    def _hydrate_result_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return item

        doc_id = str(item.get("doc_id", "")).strip()
        if not doc_id:
            return item

        full_doc = self._get_doc_store().get(doc_id)
        if not isinstance(full_doc, dict):
            return item

        current_meta = item.get("metadata", {}) or {}
        rich_meta = self._extract_rich_metadata(full_doc)

        item["metadata"] = {
            **rich_meta,
            **current_meta,
        }
        return item
    
    def _hydrate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self._hydrate_result_item(item) for item in results]
