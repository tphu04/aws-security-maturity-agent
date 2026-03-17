from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Request

from app.core.config import settings

router = APIRouter(tags=["health"])


def _safe_readiness(request: Request) -> Dict[str, Any]:
    pipeline = getattr(request.app.state, "retrieval_pipeline", None)
    if pipeline is None:
        return {
            "lexical_ready": False,
            "vector_ready": False,
            "mapping_ready": False,
            "minimal_ready": False,
            "hybrid_ready": False,
        }

    try:
        readiness = pipeline.readiness()
    except Exception:
        readiness = {
            "lexical_ready": False,
            "vector_ready": False,
            "mapping_ready": False,
            "minimal_ready": False,
            "hybrid_ready": False,
        }

    mapping_service = getattr(request.app.state, "mapping_service", None)
    if mapping_service is not None:
        try:
            mappings_path = getattr(mapping_service, "_mappings_path", None)
            readiness["mapping_ready"] = bool(
                mappings_path and Path(mappings_path).exists()
            )
        except Exception:
            readiness["mapping_ready"] = False
    else:
        readiness["mapping_ready"] = False

    return readiness


@router.get("/health")
def health(request: Request) -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.service_version,
        "app_initialized": bool(getattr(request.app.state, "app_initialized", False)),
    }


@router.get("/ready")
def ready(request: Request) -> Dict[str, Any]:
    readiness = _safe_readiness(request)
    overall = bool(readiness.get("minimal_ready", False))
    return {
        "status": "ready" if overall else "not_ready",
        "service": settings.service_name,
        "version": settings.service_version,
        "readiness": readiness,
    }


@router.get("/build-info")
def build_info(request: Request) -> Dict[str, Any]:
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "build_info": getattr(request.app.state, "build_info", {}) or {},
        "readiness": _safe_readiness(request),
    }
