from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.models import (
    CapabilityQueryRequest,
    CapabilityTheme,
    ContextBuildRequest,
    ContextBuildResponse,
    RemediationGuide,
    RemediationQueryRequest,
    ReportContextBundle,
    ReportContextRequest,
    ResponseEnvelope,
    RetrieveChecksRequest,
    RetrieveMaturityRequest,
)
from app.services.check_service import CheckService
from app.services.context_service import ContextService
from app.services.maturity_service import MaturityService
from app.services.report_context_service import ReportContextService


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


def get_report_context_service(request: Request) -> ReportContextService:
    service = getattr(request.app.state, "report_context_service", None)
    if service is None:
        raise RuntimeError("report_context_service is not initialized on app.state")
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


# ============================================================
# Multi-query RAG endpoints (Phase 2 MVP)
# ============================================================


@router.post("/retrieve/capability", response_model=list[CapabilityTheme])
async def retrieve_capability(
    payload: CapabilityQueryRequest,
    service: ReportContextService = Depends(get_report_context_service),
) -> list[CapabilityTheme]:
    from app.core.models import ReportContextRequest
    req = ReportContextRequest(
        check_ids=[],
        domains=[payload.domain],
        include_q2=True,
        include_q3=False,
        top_k_capability=payload.top_k,
    )
    bundle = await service.build(req)
    return bundle.capability_themes


@router.post("/retrieve/remediation", response_model=list[RemediationGuide])
async def retrieve_remediation(
    payload: RemediationQueryRequest,
    service: ReportContextService = Depends(get_report_context_service),
) -> list[RemediationGuide]:
    from app.core.models import ReportContextRequest
    req = ReportContextRequest(
        check_ids=[payload.check_id],
        domains=[],
        severity_map={payload.check_id: payload.severity} if payload.severity else {},
        include_q2=False,
        include_q3=True,
        top_k_remediation=payload.top_k,
    )
    bundle = await service.build(req)
    return bundle.remediations


@router.post("/retrieve/report_context", response_model=ReportContextBundle)
async def retrieve_report_context(
    payload: ReportContextRequest,
    service: ReportContextService = Depends(get_report_context_service),
) -> ReportContextBundle:
    return await service.build(payload)
