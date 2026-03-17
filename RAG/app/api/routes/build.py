from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.models import ContextBuildRequest, ResponseEnvelope
from app.services.context_service import ContextService

router = APIRouter(prefix="/v1/build", tags=["build"])


def _get_context_service(request: Request) -> ContextService:
    service = getattr(request.app.state, "context_service", None)
    if service is None:
        raise HTTPException(
            status_code=503, detail="context service is not initialized"
        )
    return service


@router.post("/context", response_model=ResponseEnvelope)
def build_context(
    request_body: ContextBuildRequest, request: Request
) -> ResponseEnvelope:
    try:
        service = _get_context_service(request)
        return service.build(request_body)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"unexpected error in build_context: {exc}"
        ) from exc
