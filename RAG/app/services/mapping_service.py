from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import (
    CORPUS_MATURITY_MAPPINGS,
    MANIFEST_PATH,
    NORMALIZED_PATHS,
)
from app.core.errors import make_error_item
from app.core.utils import mapping_sort_key
from app.core.models import ErrorItem, MetaInfo, ResolveMappingRequest, ResponseEnvelope
from app.ingestion.normalizers import normalize_service
from app.ingestion.normalizers import _normalize_identifier as normalize_identifier


class MappingService:
    """
    Exact lookup service for curated maturity mappings.

    Storage-aware behavior:
    - loads from normalized artifact for corpus 'maturity_mappings'
    - supports multiple mappings per check_id
    - ranks candidates deterministically
    - returns manifest index_version when available
    """

    def __init__(self, mappings_path: Optional[Path] = None) -> None:
        self._mappings_path = Path(
            mappings_path or NORMALIZED_PATHS[CORPUS_MATURITY_MAPPINGS]
        )
        self._mapping_index: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self._manifest: Optional[Dict[str, Any]] = None

    def resolve(self, request: ResolveMappingRequest) -> ResponseEnvelope:
        request_id = str(uuid.uuid4())

        normalized_check_id = normalize_identifier(request.check_id)
        normalized_service = (
            normalize_service(request.service) if request.service else None
        )
        normalized_domain = self._normalize_optional_field(
            getattr(request, "domain", None)
        )

        diagnostics: Dict[str, Any] = {
            "service": "mapping_resolution",
            "check_id": normalized_check_id,
            "service_filter": normalized_service,
            "domain_filter": normalized_domain,
            "mappings_path": str(self._mappings_path),
        }

        if not normalized_check_id:
            return ResponseEnvelope(
                request_id=request_id,
                status="error",
                data={"mapping": None, "candidates": []},
                meta=MetaInfo(
                    index_version=self._index_version(),
                    confidence="low",
                    review_recommended=True,
                    diagnostics=diagnostics,
                ),
                errors=[
                    ErrorItem(
                        code="INVALID_REQUEST",
                        message="check_id is required for mapping resolution",
                        details=None,
                    )
                ],
            )

        try:
            mapping_index = self._get_mapping_index()
        except Exception as exc:
            diagnostics["exception_type"] = type(exc).__name__
            return ResponseEnvelope(
                request_id=request_id,
                status="error",
                data={"mapping": None, "candidates": []},
                meta=MetaInfo(
                    index_version=self._index_version(),
                    confidence="low",
                    review_recommended=True,
                    diagnostics=diagnostics,
                ),
                errors=[
                    ErrorItem(
                        code="MAPPING_LOAD_FAILED",
                        message="failed to load mapping index",
                        details=str(exc),
                    )
                ],
            )

        candidates = mapping_index.get(normalized_check_id, [])
        diagnostics["candidate_count_before_filter"] = len(candidates)

        if not candidates:
            return ResponseEnvelope(
                request_id=request_id,
                status="partial",
                data={"mapping": None, "candidates": []},
                meta=MetaInfo(
                    index_version=self._index_version(),
                    confidence="low",
                    review_recommended=True,
                    diagnostics=diagnostics,
                ),
                errors=[
                    make_error_item(
                        "MAPPING_MISSING",
                        f"no mapping found for check_id '{normalized_check_id}'",
                    )
                ],
            )

        filtered = self._filter_candidates(
            candidates=candidates,
            service=normalized_service,
            domain=normalized_domain,
        )
        diagnostics["candidate_count_after_filter"] = len(filtered)

        if not filtered:
            diagnostics["available_services"] = sorted(
                {
                    str(item.get("service", "")).strip().lower()
                    for item in candidates
                    if str(item.get("service", "")).strip()
                }
            )
            diagnostics["available_domains"] = sorted(
                {
                    str(item.get("domain", "")).strip().lower()
                    for item in candidates
                    if str(item.get("domain", "")).strip()
                }
            )

            return ResponseEnvelope(
                request_id=request_id,
                status="partial",
                data={"mapping": None, "candidates": []},
                meta=MetaInfo(
                    index_version=self._index_version(),
                    confidence="low",
                    review_recommended=True,
                    diagnostics=diagnostics,
                ),
                errors=[
                    make_error_item(
                        "MAPPING_FILTER_MISMATCH",
                        f"mapping exists for check_id '{normalized_check_id}' but no candidate matches the requested filters",
                    )
                ],
            )

        ranked = sorted(filtered, key=mapping_sort_key, reverse=True)
        best = ranked[0]

        mapping_confidence = (
            str(best.get("mapping_confidence", "medium")).strip().lower()
        )
        if mapping_confidence not in {"high", "medium", "low"}:
            mapping_confidence = "low"

        review_recommended = mapping_confidence == "low" or str(
            best.get("review_status", "unreviewed")
        ).strip().lower() in {"review_required", "unreviewed"}

        diagnostics["selected_doc_id"] = best.get("doc_id")
        diagnostics["selected_capability_id"] = best.get("capability_id")
        diagnostics["selected_review_status"] = best.get("review_status")
        diagnostics["selected_mapping_type"] = best.get("mapping_type")
        diagnostics["candidate_doc_ids"] = [
            item.get("doc_id") for item in ranked[:5] if item.get("doc_id")
        ]

        return ResponseEnvelope(
            request_id=request_id,
            status="success",
            data={
                "mapping": best,
                "candidates": ranked[:5],
            },
            meta=MetaInfo(
                index_version=self._index_version(),
                confidence=mapping_confidence,
                review_recommended=review_recommended,
                diagnostics=diagnostics,
            ),
            errors=[],
        )

    def _get_mapping_index(self) -> Dict[str, List[Dict[str, Any]]]:
        if self._mapping_index is not None:
            return self._mapping_index

        if not self._mappings_path.exists():
            self._mapping_index = {}
            return self._mapping_index

        with self._mappings_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        index: Dict[str, List[Dict[str, Any]]] = {}
        for item in payload:
            check_id = normalize_identifier(item.get("check_id"))
            if not check_id:
                continue
            index.setdefault(check_id, []).append(item)

        self._mapping_index = index
        return self._mapping_index

    def _filter_candidates(
        self,
        candidates: List[Dict[str, Any]],
        service: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filtered = list(candidates)

        if service:
            service_filtered = [
                item
                for item in filtered
                if not str(item.get("service", "")).strip()
                or str(item.get("service", "")).strip().lower() == service
            ]
            if service_filtered:
                filtered = service_filtered
            else:
                return []

        if domain:
            domain_filtered = [
                item
                for item in filtered
                if str(item.get("domain", "")).strip().lower() == domain
            ]
            if domain_filtered:
                filtered = domain_filtered
            else:
                return []

        return filtered


    @staticmethod
    def filter_for_agent_context(
        candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Filter mappings for agent context: prefer approved/reviewed, exclude draft
        if better alternatives exist."""
        if not candidates:
            return []

        trusted = [
            item for item in candidates
            if str(item.get("review_status", "")).strip().lower()
            in {"approved", "reviewed", "auto_high"}
        ]

        # If we have trusted mappings, use only those
        if trusted:
            return trusted

        # Fallback: return all but mark as needing review
        return candidates

    @staticmethod
    def _normalize_optional_field(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().lower()
        return text or None

    def _index_version(self) -> str:
        manifest = self._get_manifest()
        return str(manifest.get("index_version", "unknown"))

    def _get_manifest(self) -> Dict[str, Any]:
        if self._manifest is not None:
            return self._manifest

        path = Path(MANIFEST_PATH)
        if not path.exists():
            self._manifest = {}
            return self._manifest

        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            self._manifest = payload if isinstance(payload, dict) else {}
        except Exception:
            self._manifest = {}

        return self._manifest
