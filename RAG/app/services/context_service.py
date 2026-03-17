from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from app.core.errors import make_error_item
from app.core.models import (
    BuildContextRequest,
    FindingInput,
    MetaInfo,
    ResolveMappingRequest,
    ResponseEnvelope,
    RetrieveChecksRequest,
    RetrieveMaturityRequest,
)
from app.indexing.lexical_index import BM25Index
from app.indexing.vector_index import VectorIndex
from app.retrieval.pipeline import RetrievalPipeline
from app.services.check_service import CheckService
from app.services.mapping_service import MappingService
from app.services.maturity_service import MaturityService


class ContextService:
    """
    Builds analysis context with the intended flow:

    1. retrieve check context from finding.check_id
    2. resolve curated mapping from finding.check_id
    3. retrieve maturity context using mapping capability
    """

    def __init__(
        self,
        check_service: Optional[CheckService] = None,
        mapping_service: Optional[MappingService] = None,
        maturity_service: Optional[MaturityService] = None,
        pipeline: Optional[RetrievalPipeline] = None,
        lexical_index: Optional[BM25Index] = None,
        vector_index: Optional[VectorIndex] = None,
    ) -> None:
        if pipeline is None:
            # Prefer new storage-aware pipeline loading.
            if lexical_index is not None:
                pipeline = RetrievalPipeline(
                    lexical_index=lexical_index,
                    vector_index=vector_index,
                )
            else:
                pipeline = RetrievalPipeline.from_storage(
                    vector_index=vector_index,
                )

        self._pipeline = pipeline
        self._check_service = check_service or CheckService(pipeline=pipeline)
        self._mapping_service = mapping_service or MappingService()
        self._maturity_service = maturity_service or MaturityService(pipeline=pipeline)

    def build(self, request: BuildContextRequest) -> ResponseEnvelope:
        request_id = str(uuid.uuid4())

        finding = self._coerce_finding(request.finding)
        if finding is None:
            return ResponseEnvelope(
                request_id=request_id,
                status="error",
                data={
                    "finding": None,
                    "check_context": None,
                    "mapping_context": None,
                    "maturity_context": None,
                },
                meta=MetaInfo(
                    index_version=self._index_version(),
                    confidence="low",
                    review_recommended=True,
                    diagnostics={"service": "context_build"},
                ),
                errors=[make_error_item("INVALID_REQUEST", "invalid finding payload")],
            )

        errors = []
        diagnostics: Dict[str, Any] = {
            "service": "context_build",
            "include_check_context": request.include_check_context,
            "include_mapping_context": request.include_mapping_context,
            "include_maturity_context": request.include_maturity_context,
            "finding_check_id": finding.check_id,
            "finding_service": finding.service,
        }

        check_context = None
        mapping_context = None
        maturity_context = None

        component_confidences: list[str] = []
        component_index_versions: list[str] = []
        review_recommended = False

        # 1) Check context
        if request.include_check_context:
            check_resp = self._check_service.search(
                RetrieveChecksRequest(
                    query=finding.check_id,
                    check_id=finding.check_id,
                    provider="aws",
                    service=finding.service,
                    top_k=1,
                    debug=False,
                )
            )
            diagnostics["check_status"] = check_resp.status
            diagnostics["check_meta"] = check_resp.meta.model_dump()
            component_index_versions.append(str(check_resp.meta.index_version))

            if check_resp.data.get("results"):
                check_context = check_resp.data["results"][0]
                component_confidences.append(str(check_resp.meta.confidence))
            else:
                errors.append(
                    make_error_item("CHECK_CONTEXT_MISSING", "check context not found")
                )

            if check_resp.meta.review_recommended:
                review_recommended = True

        # 2) Mapping context
        if request.include_mapping_context:
            mapping_resp = self._mapping_service.resolve(
                ResolveMappingRequest(
                    check_id=finding.check_id,
                    provider="aws",
                    service=finding.service,
                )
            )
            diagnostics["mapping_status"] = mapping_resp.status
            diagnostics["mapping_meta"] = mapping_resp.meta.model_dump()
            component_index_versions.append(str(mapping_resp.meta.index_version))

            mapping_context = mapping_resp.data.get("mapping")
            if mapping_context:
                component_confidences.append(str(mapping_resp.meta.confidence))
            else:
                errors.append(
                    make_error_item(
                        "MAPPING_CONTEXT_MISSING", "mapping context not found"
                    )
                )

            if mapping_resp.meta.review_recommended:
                review_recommended = True

        # 3) Maturity context must come from mapping
        if request.include_maturity_context:
            capability_query = None
            capability_domain = None

            if mapping_context:
                capability_query = (
                    mapping_context.get("capability_id")
                    or mapping_context.get("capability_name")
                    or None
                )
                capability_domain = mapping_context.get("domain")

            if capability_query:
                maturity_resp = self._maturity_service.search(
                    RetrieveMaturityRequest(
                        query=capability_query,
                        capability_id=(
                            mapping_context.get("capability_id")
                            if mapping_context
                            else None
                        ),
                        domain=capability_domain,
                        top_k=request.top_k or 3,
                        debug=False,
                    )
                )
                diagnostics["maturity_status"] = maturity_resp.status
                diagnostics["maturity_meta"] = maturity_resp.meta.model_dump()
                component_index_versions.append(str(maturity_resp.meta.index_version))

                if maturity_resp.data.get("results"):
                    maturity_context = maturity_resp.data["results"][0]
                    component_confidences.append(str(maturity_resp.meta.confidence))
                else:
                    errors.append(
                        make_error_item(
                            "MATURITY_CONTEXT_MISSING", "maturity context not found"
                        )
                    )

                if maturity_resp.meta.review_recommended:
                    review_recommended = True
            else:
                diagnostics["maturity_status"] = "skipped"
                errors.append(
                    make_error_item(
                        "MATURITY_CONTEXT_SKIPPED",
                        "maturity retrieval skipped because mapping capability was unavailable",
                    )
                )
                review_recommended = True

        status = self._derive_status(
            include_check_context=request.include_check_context,
            include_mapping_context=request.include_mapping_context,
            include_maturity_context=request.include_maturity_context,
            check_context=check_context,
            mapping_context=mapping_context,
            maturity_context=maturity_context,
        )

        confidence = self._aggregate_confidence(component_confidences)
        if status != "success":
            review_recommended = True
        if confidence == "low":
            review_recommended = True

        diagnostics["component_confidences"] = component_confidences
        diagnostics["component_index_versions"] = component_index_versions
        diagnostics["final_status"] = status
        diagnostics["orchestration_ready"] = self._pipeline.is_ready()

        return ResponseEnvelope(
            request_id=request_id,
            status=status,
            data={
                "finding": finding.model_dump(),
                "check_context": check_context,
                "mapping_context": mapping_context,
                "maturity_context": maturity_context,
            },
            meta=MetaInfo(
                index_version=self._resolve_context_index_version(
                    component_index_versions
                ),
                confidence=confidence,
                review_recommended=review_recommended,
                diagnostics=diagnostics,
            ),
            errors=errors,
        )

    def _index_version(self) -> str:
        try:
            manifest = getattr(self._pipeline, "_manifest", {}) or {}
            return str(manifest.get("index_version", "unknown"))
        except Exception:
            return "unknown"

    def _resolve_context_index_version(self, versions: list[str]) -> str:
        cleaned = [str(v).strip() for v in versions if str(v).strip()]
        if cleaned:
            unique = list(dict.fromkeys(cleaned))
            if len(unique) == 1:
                return unique[0]
        return self._index_version()

    @staticmethod
    def _coerce_finding(value: Any) -> Optional[FindingInput]:
        if isinstance(value, FindingInput):
            return value
        if isinstance(value, dict):
            try:
                return FindingInput(**value)
            except Exception:
                return None
        return None

    @staticmethod
    def _derive_status(
        include_check_context: bool,
        include_mapping_context: bool,
        include_maturity_context: bool,
        check_context: Any,
        mapping_context: Any,
        maturity_context: Any,
    ) -> str:
        required = []
        if include_check_context:
            required.append(check_context is not None)
        if include_mapping_context:
            required.append(mapping_context is not None)
        if include_maturity_context:
            required.append(maturity_context is not None)

        if required and all(required):
            return "success"
        if required and any(required):
            return "partial"
        return "error"

    @staticmethod
    def _aggregate_confidence(confidences: list[str]) -> str:
        if not confidences:
            return "low"

        normalized = [str(c).lower() for c in confidences]
        if all(c == "high" for c in normalized):
            return "high"
        if "low" in normalized:
            return "low"
        return "medium"
