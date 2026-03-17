from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from app.core.errors import make_error_item
from app.core.models import ErrorItem, MetaInfo, ResponseEnvelope, RetrieveChecksRequest
from app.indexing.lexical_index import BM25Index
from app.indexing.vector_index import VectorIndex
from app.retrieval.pipeline import RetrievalPipeline
from app.retrieval.router import normalize_query


class CheckService:
    """
    Service wrapper for check retrieval.

    Behavior:
    - prefers request.check_id when present
    - falls back to request.query
    - uses RetrievalPipeline with explicit_type="check_search"
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
            # Backward compatibility:
            # - if caller still passes a legacy lexical_index, keep working
            # - otherwise load from new multi-corpus storage
            if lexical_index is not None:
                self._pipeline = RetrievalPipeline(
                    lexical_index=lexical_index,
                    vector_index=vector_index,
                )
            else:
                self._pipeline = RetrievalPipeline.from_storage(
                    vector_index=vector_index,
                )

    def search(self, request: RetrieveChecksRequest) -> ResponseEnvelope:
        request_id = str(uuid.uuid4())

        query = (request.check_id or request.query or "").strip()
        if not query:
            return ResponseEnvelope(
                request_id=request_id,
                status="error",
                data={"results": []},
                meta=MetaInfo(
                    index_version=self._index_version(),
                    confidence="low",
                    review_recommended=True,
                    diagnostics={"service": "check_search"},
                ),
                errors=[
                    ErrorItem(
                        code="INVALID_REQUEST",
                        message="either query or check_id must be provided",
                        details=None,
                    )
                ],
            )

        try:
            pipeline_output = self._pipeline.retrieve(
                query=query,
                explicit_type="check_search",
                provider=getattr(request, "provider", "aws") or "aws",
                service=request.service,
                top_k=request.top_k or 5,
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
                        "service": "check_search",
                        "exception_type": type(exc).__name__,
                    },
                ),
                errors=[
                    ErrorItem(
                        code="RETRIEVAL_FAILED",
                        message="check retrieval failed",
                        details=str(exc),
                    )
                ],
            )

        results = pipeline_output.get("results", []) or []
        meta = pipeline_output.get("meta", {}) or {}

        verification = meta.get("verification", {}) or {}
        readiness = meta.get("readiness", {}) or {}
        degraded = bool(meta.get("degraded", False))
        confidence = meta.get("confidence", "low")
        pipeline_diagnostics = meta.get("diagnostics", {}) or {}
        routing = meta.get("routing", {}) or {}

        warnings = verification.get("warnings", []) or []
        status = "success" if results else "partial"
        review_recommended = (confidence == "low") or bool(warnings)

        diagnostics: Dict[str, Any] = {
            "service": "check_search",
            "normalized_query": pipeline_output.get("query", normalize_query(query)),
            "query_type": pipeline_output.get("query_type", "check_search"),
            "filters": pipeline_output.get("filters", {}),
            "verification": verification,
            "readiness": readiness,
            "degraded": degraded,
            "routing": routing,
        }
        diagnostics.update(pipeline_diagnostics)

        errors: list[ErrorItem] = []
        if not results:
            errors.append(make_error_item("NO_RESULTS", "no check results found"))
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

    def _index_version(self) -> str:
        try:
            readiness_meta = getattr(self._pipeline, "_manifest", {}) or {}
            return str(readiness_meta.get("index_version", "unknown"))
        except Exception:
            return "unknown"
