from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.models import (
    ContextBuildRequest,
    ContextBuildResponse,
    ResponseEnvelope,
    RetrieveChecksRequest,
    RetrieveMaturityRequest,
)
from app.services.check_service import CheckService
from app.services.context_service import ContextService
from app.services.maturity_service import MaturityService


router = APIRouter(prefix="/v1", tags=["rag"])


# ============================================================
# Dependency helpers
# ============================================================


def get_check_service(request: Request) -> CheckService:
    service = getattr(request.app.state, "check_service", None)
    if service is None:
        raise RuntimeError("check_service is not initialized on app.state")
    return service


def get_maturity_service(request: Request) -> MaturityService:
    service = getattr(request.app.state, "maturity_service", None)
    if service is None:
        raise RuntimeError("maturity_service is not initialized on app.state")
    return service


def get_context_service(request: Request) -> ContextService:
    service = getattr(request.app.state, "context_service", None)
    if service is None:
        raise RuntimeError("context_service is not initialized on app.state")
    return service


# ============================================================
# Retrieval endpoints
# ============================================================


@router.post("/retrieve/checks", response_model=ResponseEnvelope)
def retrieve_checks(
    payload: RetrieveChecksRequest,
    service: CheckService = Depends(get_check_service),
) -> ResponseEnvelope:
    return service.search(payload)


@router.post("/retrieve/maturity", response_model=ResponseEnvelope)
def retrieve_maturity(
    payload: RetrieveMaturityRequest,
    service: MaturityService = Depends(get_maturity_service),
) -> ResponseEnvelope:
    return service.search(payload)


# ============================================================
# Context Construction endpoint
# ============================================================


@router.post("/context/build", response_model=ContextBuildResponse)
def build_context(
    payload: ContextBuildRequest,
    service: ContextService = Depends(get_context_service),
) -> ContextBuildResponse:
    return service.build(payload)
