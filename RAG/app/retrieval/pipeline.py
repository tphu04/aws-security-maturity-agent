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
                query=route.normalized_query,
                preferred_service=route.service,
                preferred_domain=route.domain,
            )
        merged_results = self._hydrate_results(merged_results)

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

    @staticmethod
    def _rrf(rank: int, k: int = 60) -> float:
        return 1.0 / (k + rank)

    @staticmethod
    def _has_exact_match(item: Dict[str, Any]) -> bool:
        matched_by = set(item.get("matched_by", []) or [])
        return bool(
            {"exact_check_id", "exact_capability_id", "exact_mapping"} & matched_by
        )

    @staticmethod
    def _metadata_bonus(
        metadata: Dict[str, Any],
        preferred_service: Optional[str],
        preferred_domain: Optional[str],
    ) -> float:
        bonus = 0.0

        if preferred_service:
            actual_service = str(metadata.get("service", "") or "").strip().lower()
            if (
                actual_service
                and actual_service == str(preferred_service).strip().lower()
            ):
                bonus += 0.03

        if preferred_domain:
            actual_domain = str(metadata.get("domain", "") or "").strip().lower()
            if actual_domain and actual_domain == str(preferred_domain).strip().lower():
                bonus += 0.02

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

            # prowler_check
            "title": doc.get("title"),
            "severity": doc.get("severity"),
            "description": doc.get("description"),
            "risk": doc.get("risk"),
            "remediation": doc.get("remediation"),
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

    _CONTROL_INTENT_MARKERS: Dict[str, List[str]] = {
        "public_access": [
            "public access",
            "publicly accessible",
            "public exposure",
            "public read",
            "public write",
            "anonymous access",
            "unauthenticated access",
            "internet exposed",
            "block public access",
        ],
        "encryption_at_rest": [
            "encryption at rest",
            "default encryption",
            "server side encryption",
            "kms",
            "sse",
            "stored data",
            "storage encryption",
        ],
        "encryption_in_transit": [
            "encryption in transit",
            "secure transport",
            "https",
            "tls",
            "ssl",
            "secure protocol",
        ],
        "logging_monitoring": [
            "logging",
            "cloudtrail",
            "audit",
            "monitoring",
            "detection",
        ],
        "identity_access": [
            "identity",
            "iam",
            "least privilege",
            "mfa",
            "password",
            "credential",
            "role",
            "permission",
        ],
    }

    _PRODUCT_ENTITY_GATES: Dict[str, List[str]] = {
        "bedrock": ["bedrock", "genai", "gen_ai", "generative", "llm", "prompt"],
        "generative": ["bedrock", "genai", "gen_ai", "generative", "llm", "prompt"],
        "genai": ["bedrock", "genai", "gen_ai", "generative", "llm", "prompt"],
        "prompt": ["bedrock", "genai", "generative", "llm", "prompt", "inference"],
        "sagemaker": ["sagemaker", "ml", "model", "training", "endpoint"],
        "waf": ["waf", "web acl", "webacl", "sql injection", "xss", "rate limit"],
        "macie": ["macie", "pii", "sensitive data", "classification"],
    }

    def _infer_control_intents(self, text: str) -> set[str]:
        normalized = (text or "").lower()
        intents: set[str] = set()
        for intent, markers in self._CONTROL_INTENT_MARKERS.items():
            if any(marker in normalized for marker in markers):
                intents.add(intent)
        return intents

    def _doc_signal_text(self, metadata: Dict[str, Any]) -> str:
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

    def _intent_bonus(self, query: str, metadata: Dict[str, Any]) -> float:
        query_intents = self._infer_control_intents(query)
        doc_intents = self._infer_control_intents(self._doc_signal_text(metadata))

        if not query_intents or not doc_intents:
            return 0.0
        if query_intents & doc_intents:
            return 0.18
        return -0.18

    def _check_id_intent_boost(self, query: str, metadata: Dict[str, Any]) -> float:
        check_id = str(metadata.get("check_id") or "").lower()
        if not check_id:
            return 0.0

        query_intents = self._infer_control_intents(query)
        boost = 0.0

        if "public_access" in query_intents:
            if "public_access" in check_id or "public_access_block" in check_id:
                boost += 0.30
            if "public" in check_id and ("acl" in check_id or "policy" in check_id):
                boost += 0.12

        if "encryption_at_rest" in query_intents:
            if "default_encryption" in check_id or "kms_encryption" in check_id:
                boost += 0.22

        if "encryption_in_transit" in query_intents:
            if "secure_transport" in check_id or "https" in check_id:
                boost += 0.22

        return boost

    def _product_penalty(self, query: str, metadata: Dict[str, Any]) -> float:
        query_text = (query or "").lower()
        doc_text = self._doc_signal_text(metadata)
        for entity_token, required_signals in self._PRODUCT_ENTITY_GATES.items():
            if entity_token in doc_text and not any(
                signal in query_text for signal in required_signals
            ):
                return -0.20
        return 0.0

    def _merge_results(
        self,
        lexical_results: List[Dict[str, Any]],
        vector_results: List[Dict[str, Any]],
        top_k: int,
        query: str,
        preferred_service: Optional[str] = None,
        preferred_domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
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

        all_doc_ids = list(
            dict.fromkeys(list(lexical_rank_map.keys()) + list(vector_rank_map.keys()))
        )

        for doc_id in all_doc_ids:
            lexical_item = next(
                (x for x in lexical_results if x.get("doc_id") == doc_id), None
            )
            vector_item = next(
                (x for x in vector_results if x.get("doc_id") == doc_id), None
            )

            metadata = {}
            matched_by = set()

            if lexical_item:
                metadata = lexical_item.get("metadata", {}) or {}
                matched_by.update(lexical_item.get("matched_by", []) or [])

            if vector_item:
                if not metadata:
                    metadata = vector_item.get("metadata", {}) or {}
                matched_by.update(vector_item.get("matched_by", []) or [])

            score = 0.0

            if doc_id in lexical_rank_map:
                score += self._rrf(lexical_rank_map[doc_id])

            if doc_id in vector_rank_map:
                score += self._rrf(vector_rank_map[doc_id])

            if lexical_item and self._has_exact_match(lexical_item):
                score += 1.0

            if vector_item and self._has_exact_match(vector_item):
                score += 1.0

            score += self._metadata_bonus(
                metadata=metadata,
                preferred_service=preferred_service,
                preferred_domain=preferred_domain,
            )
            score += self._intent_bonus(query=query, metadata=metadata)
            score += self._check_id_intent_boost(query=query, metadata=metadata)
            score += self._product_penalty(query=query, metadata=metadata)

            merged[doc_id] = {
                "doc_id": doc_id,
                "score": score,
                "metadata": metadata,
                "matched_by": sorted(matched_by),
                "_lexical_rank": lexical_rank_map.get(doc_id),
                "_vector_rank": vector_rank_map.get(doc_id),
                "_raw_lexical_score": float(
                    (lexical_item or {}).get("score", 0.0) or 0.0
                ),
                "_raw_vector_score": float(
                    (vector_item or {}).get("score", 0.0) or 0.0
                ),
            }

        ranked = sorted(
            merged.values(),
            key=lambda item: (
                float(item.get("score", 0.0)),
                1 if self._has_exact_match(item) else 0,
                1 if item.get("_vector_rank") is not None else 0,
                1 if item.get("_lexical_rank") is not None else 0,
            ),
            reverse=True,
        )

        for item in ranked:
            item.pop("_lexical_rank", None)
            item.pop("_vector_rank", None)

        return ranked[:top_k]

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
