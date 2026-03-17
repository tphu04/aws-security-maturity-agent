from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.models import (
    ResponseEnvelope,
    RetrieveChecksRequest,
    RetrieveMaturityRequest,
)
from app.services.check_service import CheckService
from app.services.maturity_service import MaturityService

router = APIRouter(prefix="/v1/retrieve", tags=["retrieve"])


def _get_check_service(request: Request) -> CheckService:
    service = getattr(request.app.state, "check_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="check service is not initialized")
    return service


def _get_maturity_service(request: Request) -> MaturityService:
    service = getattr(request.app.state, "maturity_service", None)
    if service is None:
        raise HTTPException(
            status_code=503, detail="maturity service is not initialized"
        )
    return service


@router.post("/checks", response_model=ResponseEnvelope)
def retrieve_checks(
    request_body: RetrieveChecksRequest, request: Request
) -> ResponseEnvelope:
    try:
        service = _get_check_service(request)
        return service.search(request_body)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"unexpected error in retrieve_checks: {exc}"
        ) from exc


@router.post("/maturity", response_model=ResponseEnvelope)
def retrieve_maturity(
    request_body: RetrieveMaturityRequest, request: Request
) -> ResponseEnvelope:
    try:
        service = _get_maturity_service(request)
        return service.search(request_body)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"unexpected error in retrieve_maturity: {exc}"
        ) from exc
