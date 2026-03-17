from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.models import ResolveMappingRequest, ResponseEnvelope
from app.services.mapping_service import MappingService

router = APIRouter(prefix="/v1/resolve", tags=["resolve"])


def _get_mapping_service(request: Request) -> MappingService:
    service = getattr(request.app.state, "mapping_service", None)
    if service is None:
        raise HTTPException(
            status_code=503, detail="mapping service is not initialized"
        )
    return service


@router.post("/mapping", response_model=ResponseEnvelope)
def resolve_mapping(
    request_body: ResolveMappingRequest, request: Request
) -> ResponseEnvelope:
    try:
        service = _get_mapping_service(request)
        return service.resolve(request_body)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"unexpected error in resolve_mapping: {exc}"
        ) from exc
