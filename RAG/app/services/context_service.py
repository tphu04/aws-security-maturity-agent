from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Sequence

from app.context.context_builder import ContextBuilder
from app.core.errors import make_error_item
from app.core.models import (
    Confidence,
    ContextBuildRequest,
    ContextBuildResponse,
    MetaInfo,
    ResolveMappingRequest,
    RetrieveChecksRequest,
    RetrieveMaturityRequest,
)
from app.indexing.lexical_index import BM25Index
from app.indexing.vector_index import VectorIndex
from app.retrieval.pipeline import RetrievalPipeline
from app.services.check_service import CheckService
from app.services.mapping_service import MappingService
from app.services.maturity_service import MaturityService, normalize_capability_id


class ContextService:
    """
    Context construction orchestration layer.

    Responsibilities:
    - parse ContextBuildRequest
    - retrieve check context
    - resolve curated mappings
    - retrieve maturity context
    - aggregate warnings/confidence
    - call ContextBuilder to produce agent-friendly context packet
    """

    def __init__(
        self,
        check_service: Optional[CheckService] = None,
        mapping_service: Optional[MappingService] = None,
        maturity_service: Optional[MaturityService] = None,
        pipeline: Optional[RetrievalPipeline] = None,
        lexical_index: Optional[BM25Index] = None,
        vector_index: Optional[VectorIndex] = None,
        builder: Optional[ContextBuilder] = None,
    ) -> None:
        if pipeline is None:
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
        self._builder = builder or ContextBuilder()

    # ============================================================
    # Public API
    # ============================================================

    def build(self, request: ContextBuildRequest) -> ContextBuildResponse:
        request_id = str(uuid.uuid4())

        diagnostics: Dict[str, Any] = {
            "service": "context_build",
            "consumer": request.consumer,
            "provider": request.provider,
            "service_filter": request.service,
            "domain_filter": request.domain,
            "top_k": request.top_k,
            "retrieval_mode": request.retrieval_mode,
            "include_mappings": request.include_mappings,
            "include_maturity": request.include_maturity,
            "max_context_items": request.max_context_items,
            "max_chars_per_item": request.max_chars_per_item,
        }

        errors: List[Any] = []
        warnings: List[str] = []
        component_confidences: List[str] = []
        component_index_versions: List[str] = []
        review_recommended = False

        try:
            normalized_check_ids = self._collect_check_ids(request)
            diagnostics["normalized_check_ids"] = normalized_check_ids
            diagnostics["input_findings_count"] = len(request.findings or [])
        except Exception as exc:
            return self._error_response(
                request_id=request_id,
                diagnostics=diagnostics,
                code="INVALID_REQUEST",
                message="failed to normalize context build request",
                details=str(exc),
            )

        check_results: List[Dict[str, Any]] = []
        mapping_results: List[Dict[str, Any]] = []
        maturity_results: List[Dict[str, Any]] = []

        # --------------------------------------------------------
        # 1) Check retrieval
        # --------------------------------------------------------
        try:
            check_outputs = self._retrieve_checks(request, normalized_check_ids)
            check_results = self._merge_result_lists(
                [resp.data.get("results", []) for resp in check_outputs]
            )
            diagnostics["check_request_count"] = len(check_outputs)
            diagnostics["check_result_count"] = len(check_results)

            for resp in check_outputs:
                component_confidences.append(str(resp.meta.confidence))
                component_index_versions.append(str(resp.meta.index_version))
                review_recommended = review_recommended or bool(
                    resp.meta.review_recommended
                )
                warnings.extend(self._extract_warning_messages(resp.errors))

            if not check_results:
                errors.append(
                    make_error_item("CHECK_CONTEXT_MISSING", "check context not found")
                )
        except Exception as exc:
            diagnostics["check_exception_type"] = type(exc).__name__
            errors.append(
                make_error_item(
                    "CHECK_CONTEXT_FAILED", "check context retrieval failed", str(exc)
                )
            )
            review_recommended = True

        # --------------------------------------------------------
        # 2) Mapping resolution
        # --------------------------------------------------------
        selected_check_ids_for_mapping = self._extract_check_ids_from_results(
            check_results
        )
        if request.include_mappings and selected_check_ids_for_mapping:
            try:
                mapping_outputs = self._resolve_mappings(
                    request=request,
                    check_ids=selected_check_ids_for_mapping,
                )
                mapping_results = self._merge_mapping_candidates(mapping_outputs)
                diagnostics["mapping_request_count"] = len(mapping_outputs)
                diagnostics["mapping_result_count"] = len(mapping_results)

                for resp in mapping_outputs:
                    component_confidences.append(str(resp.meta.confidence))
                    component_index_versions.append(str(resp.meta.index_version))
                    review_recommended = review_recommended or bool(
                        resp.meta.review_recommended
                    )
                    warnings.extend(self._extract_warning_messages(resp.errors))

                if not mapping_results:
                    errors.append(
                        make_error_item(
                            "MAPPING_CONTEXT_MISSING", "mapping context not found"
                        )
                    )
            except Exception as exc:
                diagnostics["mapping_exception_type"] = type(exc).__name__
                errors.append(
                    make_error_item(
                        "MAPPING_CONTEXT_FAILED", "mapping resolution failed", str(exc)
                    )
                )
                review_recommended = True
        elif request.include_mappings:
            diagnostics["mapping_skipped"] = True
            diagnostics["mapping_skip_reason"] = "no_selected_check_ids"

        # --------------------------------------------------------
        # 3) Maturity retrieval
        # --------------------------------------------------------
        capability_ids = self._extract_capability_ids_from_mappings(mapping_results)
        diagnostics["requested_capability_ids"] = capability_ids
        if request.include_maturity and capability_ids:
            try:
                maturity_outputs = self._retrieve_maturity(
                    request=request,
                    capability_ids=capability_ids,
                    mapping_results=mapping_results,
                )
                raw_maturity_results = self._merge_result_lists(
                    [resp.data.get("results", []) for resp in maturity_outputs]
                )
                maturity_results = (
                    self._filter_maturity_results_by_requested_capabilities(
                        results=raw_maturity_results,
                        requested_capability_ids=capability_ids,
                    )
                )

                diagnostics["maturity_request_count"] = len(maturity_outputs)
                diagnostics["maturity_result_count"] = len(maturity_results)
                diagnostics["raw_maturity_result_count"] = len(raw_maturity_results)
                diagnostics["resolved_capability_ids"] = (
                    self._extract_capability_ids_from_results(maturity_results)
                )

                for resp in maturity_outputs:
                    component_confidences.append(str(resp.meta.confidence))
                    component_index_versions.append(str(resp.meta.index_version))
                    review_recommended = review_recommended or bool(
                        resp.meta.review_recommended
                    )
                    warnings.extend(self._extract_warning_messages(resp.errors))

                if not maturity_results:
                    errors.append(
                        make_error_item(
                            "MATURITY_CONTEXT_MISSING", "maturity context not found"
                        )
                    )
            except Exception as exc:
                diagnostics["maturity_exception_type"] = type(exc).__name__
                errors.append(
                    make_error_item(
                        "MATURITY_CONTEXT_FAILED", "maturity retrieval failed", str(exc)
                    )
                )
                review_recommended = True
        elif request.include_maturity:
            diagnostics["maturity_skipped"] = True
            diagnostics["maturity_skip_reason"] = "no_capability_ids"

        # --------------------------------------------------------
        # 4) Build bundle + context packet
        # --------------------------------------------------------
        final_confidence = self._aggregate_confidence(component_confidences)
        unique_warnings = self._dedupe_preserve_order(warnings)
        if final_confidence == "low":
            review_recommended = True

        retrieval_bundle: Dict[str, Any] = {
            "query": request.query,
            "consumer": request.consumer,
            "provider": request.provider,
            "service": request.service,
            "domain": request.domain,
            "requested_check_ids": normalized_check_ids,
            "check_results": check_results,
            "mapping_results": mapping_results,
            "maturity_results": maturity_results,
            "confidence": final_confidence,
            "review_recommended": review_recommended,
            "warnings": unique_warnings,
        }

        diagnostics["component_confidences"] = component_confidences
        diagnostics["component_index_versions"] = component_index_versions
        diagnostics["final_warning_count"] = len(unique_warnings)
        diagnostics["orchestration_ready"] = self._pipeline.is_ready()
        diagnostics["bundle_counts"] = {
            "check_results": len(check_results),
            "mapping_results": len(mapping_results),
            "maturity_results": len(maturity_results),
        }

        try:
            context_data = self._builder.build(
                bundle=retrieval_bundle,
                consumer=request.consumer,
                options={
                    "max_context_items": request.max_context_items,
                    "max_chars_per_item": request.max_chars_per_item,
                },
            )
        except Exception as exc:
            diagnostics["builder_exception_type"] = type(exc).__name__
            return self._error_response(
                request_id=request_id,
                diagnostics=diagnostics,
                code="CONTEXT_BUILD_FAILED",
                message="context builder failed",
                details=str(exc),
                index_version=self._resolve_context_index_version(
                    component_index_versions
                ),
            )

        # Apply semantic confidence degrade if builder determined bundle quality is poor
        if context_data.diagnostics.adjusted_confidence:
            final_confidence = context_data.diagnostics.adjusted_confidence
            if final_confidence == "low":
                review_recommended = True

        status = self._derive_status(
            has_checks=bool(check_results),
            include_mappings=request.include_mappings,
            has_mappings=bool(mapping_results),
            include_maturity=request.include_maturity,
            has_maturity=bool(maturity_results),
        )

        if status != "success":
            review_recommended = True

        return ContextBuildResponse(
            request_id=request_id,
            status=status,
            data=context_data,
            meta=MetaInfo(
                index_version=self._resolve_context_index_version(
                    component_index_versions
                ),
                confidence=final_confidence,
                review_recommended=review_recommended,
                diagnostics=diagnostics,
            ),
            errors=errors
            + [make_error_item("RETRIEVAL_WARNING", w) for w in unique_warnings],
        )

    # ============================================================
    # Step 1: checks
    # ============================================================

    def _retrieve_checks(
        self,
        request: ContextBuildRequest,
        normalized_check_ids: Sequence[str],
    ) -> List[Any]:
        responses: List[Any] = []

        # Planning uses a wider candidate pool for coverage-aware selection
        is_planning = request.consumer == "planning"
        effective_top_k = 15 if is_planning else max(1, request.top_k)

        # exact / finding-driven retrieval first
        for check_id in normalized_check_ids:
            responses.append(
                self._check_service.search(
                    RetrieveChecksRequest(
                        query=check_id,
                        check_id=check_id,
                        provider=request.provider,
                        service=request.service,
                        top_k=max(1, request.top_k),
                        debug=request.debug,
                        retrieval_mode=request.retrieval_mode,
                    )
                )
            )

        # query-driven retrieval when query exists
        if request.query and request.query.strip():
            responses.append(
                self._check_service.search(
                    RetrieveChecksRequest(
                        query=request.query.strip(),
                        provider=request.provider,
                        service=request.service,
                        top_k=effective_top_k,
                        debug=request.debug,
                        retrieval_mode=request.retrieval_mode,
                    )
                )
            )

        return responses

    # ============================================================
    # Step 2: mappings
    # ============================================================

    def _resolve_mappings(
        self,
        request: ContextBuildRequest,
        check_ids: Sequence[str],
    ) -> List[Any]:
        responses: List[Any] = []

        for check_id in check_ids:
            responses.append(
                self._mapping_service.resolve(
                    ResolveMappingRequest(
                        check_id=check_id,
                        provider=request.provider,
                        service=request.service,
                    )
                )
            )

        return responses

    # ============================================================
    # Step 3: maturity
    # ============================================================

    def _retrieve_maturity(
        self,
        request: ContextBuildRequest,
        capability_ids: Sequence[str],
        mapping_results: Sequence[Dict[str, Any]],
    ) -> List[Any]:
        responses: List[Any] = []

        domain_by_capability: Dict[str, Optional[str]] = {}
        for item in mapping_results:
            capability_id = normalize_capability_id(item.get("capability_id"))
            if capability_id and capability_id not in domain_by_capability:
                domain_by_capability[capability_id] = self._maybe_str(
                    item.get("domain")
                )

        for capability_id in capability_ids:
            responses.append(
                self._maturity_service.search(
                    RetrieveMaturityRequest(
                        query=capability_id,
                        capability_id=capability_id,
                        provider=request.provider,
                        domain=request.domain,
                        top_k=max(1, request.top_k),
                        debug=request.debug,
                        retrieval_mode=request.retrieval_mode,
                    )
                )
            )

        return responses

    # ============================================================
    # Aggregation helpers
    # ============================================================

    def _collect_check_ids(self, request: ContextBuildRequest) -> List[str]:
        collected: List[str] = []

        for check_id in request.check_ids or []:
            normalized = self._normalize_identifier(check_id)
            if normalized:
                collected.append(normalized)

        for finding in request.findings or []:
            normalized = self._normalize_identifier(getattr(finding, "check_id", None))
            if normalized:
                collected.append(normalized)

        return self._dedupe_preserve_order(collected)

    def _extract_check_ids_from_results(
        self, results: Sequence[Dict[str, Any]]
    ) -> List[str]:
        collected: List[str] = []
        for item in results:
            metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
            check_id = self._maybe_str(metadata.get("check_id"))
            if check_id:
                collected.append(check_id)
        return self._dedupe_preserve_order(collected)

    def _extract_capability_ids_from_mappings(
        self, mappings: Sequence[Dict[str, Any]]
    ) -> List[str]:
        collected: List[str] = []
        for item in mappings:
            capability_id = normalize_capability_id(item.get("capability_id"))
            if capability_id:
                collected.append(capability_id)
        return self._dedupe_preserve_order(collected)

    def _merge_result_lists(
        self, result_lists: Sequence[Sequence[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen_doc_ids: set[str] = set()

        for results in result_lists:
            for item in results or []:
                if not isinstance(item, dict):
                    continue
                doc_id = self._maybe_str(item.get("doc_id"))
                if not doc_id:
                    continue
                if doc_id in seen_doc_ids:
                    continue
                merged.append(item)
                seen_doc_ids.add(doc_id)

        return merged

    def _merge_mapping_candidates(
        self, mapping_outputs: Sequence[Any]
    ) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()

        for resp in mapping_outputs:
            payload_candidates = (
                resp.data.get("candidates", []) if hasattr(resp, "data") else []
            )
            payload_mapping = (
                resp.data.get("mapping") if hasattr(resp, "data") else None
            )

            candidates: List[Dict[str, Any]] = []
            if isinstance(payload_mapping, dict):
                candidates.append(payload_mapping)
            if isinstance(payload_candidates, list):
                candidates.extend(
                    [item for item in payload_candidates if isinstance(item, dict)]
                )

            for item in candidates:
                check_id = self._maybe_str(item.get("check_id"))
                capability_id = self._maybe_str(item.get("capability_id"))
                if not check_id or not capability_id:
                    continue
                pair = (check_id, capability_id)
                if pair in seen_pairs:
                    continue
                merged.append(item)
                seen_pairs.add(pair)

        return merged

    def _extract_warning_messages(self, error_items: Sequence[Any]) -> List[str]:
        warnings: List[str] = []
        for item in error_items or []:
            code = self._maybe_str(getattr(item, "code", None))
            message = self._maybe_str(getattr(item, "message", None))
            if code == "RETRIEVAL_WARNING" and message:
                warnings.append(message)
        return warnings

    # ============================================================
    # Status / confidence / version
    # ============================================================

    def _index_version(self) -> str:
        try:
            manifest = getattr(self._pipeline, "_manifest", {}) or {}
            return str(manifest.get("index_version", "unknown"))
        except Exception:
            return "unknown"

    def _resolve_context_index_version(self, versions: Sequence[str]) -> str:
        cleaned = [str(v).strip() for v in versions if str(v).strip()]
        if cleaned:
            unique = list(dict.fromkeys(cleaned))
            if len(unique) == 1:
                return unique[0]
        return self._index_version()

    @staticmethod
    def _aggregate_confidence(confidences: Sequence[str]) -> str:
        if not confidences:
            return "low"

        normalized = [str(c).lower() for c in confidences]
        if all(c == "high" for c in normalized):
            return "high"
        if "low" in normalized:
            return "low"
        return "medium"

    @staticmethod
    def _derive_status(
        has_checks: bool,
        include_mappings: bool,
        has_mappings: bool,
        include_maturity: bool,
        has_maturity: bool,
    ) -> str:
        required = [has_checks]
        if include_mappings:
            required.append(has_mappings)
        if include_maturity:
            required.append(has_maturity)

        if required and all(required):
            return "success"
        if required and any(required):
            return "partial"
        return "error"

    # ============================================================
    # Generic helpers
    # ============================================================

    def _filter_maturity_results_by_requested_capabilities(
        self,
        results: Sequence[Dict[str, Any]],
        requested_capability_ids: Sequence[str],
    ) -> List[Dict[str, Any]]:
        if not results:
            return []

        requested = {
            normalize_capability_id(item)
            for item in requested_capability_ids
            if normalize_capability_id(item)
        }
        if not requested:
            return list(results)

        exact: List[Dict[str, Any]] = []
        fallback: List[Dict[str, Any]] = []

        for item in results:
            capability_id = self._extract_capability_id_from_result(item)
            if capability_id and capability_id in requested:
                exact.append(item)
            else:
                fallback.append(item)

        return exact if exact else list(results)

    def _extract_capability_ids_from_results(
        self, results: Sequence[Dict[str, Any]]
    ) -> List[str]:
        collected: List[str] = []
        for item in results:
            capability_id = self._extract_capability_id_from_result(item)
            if capability_id:
                collected.append(capability_id)
        return self._dedupe_preserve_order(collected)

    def _extract_capability_id_from_result(self, item: Dict[str, Any]) -> Optional[str]:
        metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
        capability_id = (
            metadata.get("capability_id")
            or item.get("capability_id")
            or metadata.get("id")
            or item.get("id")
        )
        return normalize_capability_id(capability_id)

    def _error_response(
        self,
        request_id: str,
        diagnostics: Dict[str, Any],
        code: str,
        message: str,
        details: Optional[str] = None,
        index_version: Optional[str] = None,
    ) -> ContextBuildResponse:
        return ContextBuildResponse(
            request_id=request_id,
            status="error",
            data=self._builder.build(
                bundle={
                    "query": None,
                    "consumer": diagnostics.get("consumer", "report"),
                    "check_results": [],
                    "mapping_results": [],
                    "maturity_results": [],
                    "confidence": "low",
                    "review_recommended": True,
                    "warnings": [],
                },
                consumer=diagnostics.get("consumer", "report"),
                options={},
            ),
            meta=MetaInfo(
                index_version=index_version or self._index_version(),
                confidence=Confidence.low,
                review_recommended=True,
                diagnostics=diagnostics,
            ),
            errors=[make_error_item(code, message, details)],
        )

    @staticmethod
    def _dedupe_preserve_order(values: Sequence[str]) -> List[str]:
        seen: set[str] = set()
        result: List[str] = []
        for value in values:
            cleaned = str(value).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            result.append(cleaned)
        return result

    @staticmethod
    def _normalize_identifier(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().lower()
        return text or None

    @staticmethod
    def _maybe_str(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
