from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional

from app.core.errors import make_error_item
from app.core.models import (
    ErrorItem,
    MetaInfo,
    ResponseEnvelope,
    RetrieveMaturityRequest,
)
from app.indexing.lexical_index import BM25Index
from app.indexing.vector_index import VectorIndex
from app.retrieval.pipeline import RetrievalPipeline
from app.retrieval.router import normalize_query


def normalize_capability_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    text = text.replace("-", "_").replace(" ", "_")
    text = re.sub(r"_+", "_", text)
    return text


class MaturityService:
    """
    Service wrapper for maturity capability retrieval.

    Behavior:
    - prefers capability_id if present
    - falls back to query
    - uses RetrievalPipeline with explicit_type="maturity_search"
    - re-ranks results to prefer exact capability_id match
    - defaults to storage-aware pipeline loading when no pipeline is injected
    """

    def __init__(
        self,
        pipeline: Optional[RetrievalPipeline] = None,
        lexical_index: Optional[BM25Index] = None,
        vector_index: Optional[VectorIndex] = None,
    ) -> None:
        if pipeline is not None:
            self._pipeline = pipeline
        else:
            if lexical_index is not None:
                self._pipeline = RetrievalPipeline(
                    lexical_index=lexical_index,
                    vector_index=vector_index,
                )
            else:
                self._pipeline = RetrievalPipeline.from_storage(
                    vector_index=vector_index,
                )

    def search(self, request: RetrieveMaturityRequest) -> ResponseEnvelope:
        request_id = str(uuid.uuid4())

        requested_capability_id = normalize_capability_id(
            getattr(request, "capability_id", None)
        )
        query = (getattr(request, "capability_id", None) or request.query or "").strip()

        if not query:
            return ResponseEnvelope(
                request_id=request_id,
                status="error",
                data={"results": []},
                meta=MetaInfo(
                    index_version=self._index_version(),
                    confidence="low",
                    review_recommended=True,
                    diagnostics={"service": "maturity_search"},
                ),
                errors=[
                    ErrorItem(
                        code="INVALID_REQUEST",
                        message="either query or capability_id must be provided",
                        details=None,
                    )
                ],
            )

        try:
            pipeline_output = self._pipeline.retrieve(
                query=query,
                explicit_type="maturity_search",
                provider=getattr(request, "provider", "aws") or "aws",
                domain=request.domain,
                top_k=max(request.top_k or 5, 5),
                retrieval_mode=request.retrieval_mode,
            )
        except Exception as exc:
            return ResponseEnvelope(
                request_id=request_id,
                status="error",
                data={"results": []},
                meta=MetaInfo(
                    index_version=self._index_version(),
                    confidence="low",
                    review_recommended=True,
                    diagnostics={
                        "service": "maturity_search",
                        "exception_type": type(exc).__name__,
                    },
                ),
                errors=[
                    ErrorItem(
                        code="RETRIEVAL_FAILED",
                        message="maturity retrieval failed",
                        details=str(exc),
                    )
                ],
            )

        raw_results = pipeline_output.get("results", []) or []
        results = self._rerank_results_by_capability_id(
            results=raw_results,
            requested_capability_id=requested_capability_id,
        )

        meta = pipeline_output.get("meta", {}) or {}
        verification = meta.get("verification", {}) or {}
        readiness = meta.get("readiness", {}) or {}
        degraded = bool(meta.get("degraded", False))
        confidence = meta.get("confidence", "low")
        pipeline_diagnostics = meta.get("diagnostics", {}) or {}
        routing = meta.get("routing", {}) or {}

        warnings = verification.get("warnings", []) or []
        status = "success" if results else "partial"

        exact_match_found = self._has_exact_capability_match(
            results=results,
            requested_capability_id=requested_capability_id,
        )

        review_recommended = (
            (confidence == "low")
            or bool(warnings)
            or (requested_capability_id is not None and not exact_match_found)
        )

        diagnostics: Dict[str, Any] = {
            "service": "maturity_search",
            "normalized_query": pipeline_output.get("query", normalize_query(query)),
            "query_type": pipeline_output.get("query_type", "maturity_search"),
            "filters": pipeline_output.get("filters", {}),
            "verification": verification,
            "readiness": readiness,
            "degraded": degraded,
            "routing": routing,
            "requested_capability_id": requested_capability_id,
            "resolved_capability_ids": self._extract_capability_ids(results),
            "exact_capability_match_found": exact_match_found,
        }
        diagnostics.update(pipeline_diagnostics)

        errors: List[ErrorItem] = []
        if not results:
            errors.append(
                make_error_item("NO_RESULTS", "no maturity capability results found")
            )
        elif requested_capability_id and not exact_match_found:
            errors.append(
                make_error_item(
                    "RETRIEVAL_WARNING",
                    "capability_exact_match_miss",
                )
            )

        for warning in warnings:
            errors.append(make_error_item("RETRIEVAL_WARNING", warning))

        return ResponseEnvelope(
            request_id=request_id,
            status=status,
            data={"results": results},
            meta=MetaInfo(
                index_version=str(meta.get("index_version", self._index_version())),
                confidence=confidence,
                review_recommended=review_recommended,
                diagnostics=diagnostics,
            ),
            errors=errors,
        )

    def _rerank_results_by_capability_id(
        self,
        results: List[Dict[str, Any]],
        requested_capability_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        if not results or not requested_capability_id:
            return results

        exact: List[Dict[str, Any]] = []
        non_exact: List[Dict[str, Any]] = []

        for item in results:
            item_capability_id = self._result_capability_id(item)
            if item_capability_id == requested_capability_id:
                exact.append(item)
            else:
                non_exact.append(item)

        return exact + non_exact

    def _has_exact_capability_match(
        self,
        results: List[Dict[str, Any]],
        requested_capability_id: Optional[str],
    ) -> bool:
        if not requested_capability_id:
            return False
        return any(
            self._result_capability_id(item) == requested_capability_id
            for item in results
        )

    def _extract_capability_ids(self, results: List[Dict[str, Any]]) -> List[str]:
        seen = set()
        out: List[str] = []

        for item in results:
            cap_id = self._result_capability_id(item)
            if cap_id and cap_id not in seen:
                seen.add(cap_id)
                out.append(cap_id)

        return out

    def _result_capability_id(self, item: Dict[str, Any]) -> Optional[str]:
        metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
        capability_id = (
            metadata.get("capability_id")
            or item.get("capability_id")
            or metadata.get("id")
            or item.get("id")
        )
        return normalize_capability_id(capability_id)

    def _index_version(self) -> str:
        try:
            manifest = getattr(self._pipeline, "_manifest", {}) or {}
            return str(manifest.get("index_version", "unknown"))
        except Exception:
            return "unknown"
