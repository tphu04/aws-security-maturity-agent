from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


Status = Literal["success", "partial", "error"]
ContextConsumer = Literal["planning", "risk", "report"]

class BaseDoc(BaseModel):
    doc_id: str
    doc_type: str
    source_name: str
    source_type: str
    source_uri: str
    version: str
    created_at: str
    updated_at: str
    language: str
    tags: List[str]
    index_version: str
    retrieval_text: Optional[str] = None


class MaturityCapabilityDoc(BaseDoc):
    provider: str = "aws"
    domain: str
    capability_id: str
    capability_name: str
    stage: Optional[str] = None
    summary: str
    risk_explanation: Optional[str] = None
    guidance: Optional[str] = None
    how_to_check: Optional[str] = None
    recommended_practices: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)


class ProwlerCheckDoc(BaseDoc):
    check_id: str
    provider: str = "aws"
    service: str
    title: str
    severity: str
    description: str
    risk: str
    remediation: str
    resource_type: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    synonyms: List[str] = Field(default_factory=list)


class MaturityMappingDoc(BaseDoc):
    check_id: str
    provider: str = "aws"
    service: str
    domain: str
    capability_id: str
    capability_name: str
    mapping_confidence: Confidence
    mapping_reason: str
    review_status: str
    reviewed_by: Optional[str] = None
    mapping_type: Optional[str] = None
    assessment_weight_hint: Optional[float] = None
    report_note: Optional[str] = None


class MetaInfo(BaseModel):
    index_version: str
    confidence: Confidence
    review_recommended: bool
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class ErrorItem(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ResponseEnvelope(BaseModel):
    request_id: str
    status: Status
    data: Dict[str, Any]
    meta: MetaInfo
    errors: List[ErrorItem] = Field(default_factory=list)


class RetrieveChecksRequest(BaseModel):
    query: Optional[str] = None
    check_id: Optional[str] = None
    provider: Optional[str] = "aws"
    service: Optional[str] = None
    top_k: int = 5
    debug: bool = False
    retrieval_mode: Literal["lexical", "vector", "hybrid"] = "hybrid"

    @model_validator(mode="after")
    def validate_input(self):
        if not self.query and not self.check_id:
            raise ValueError("either query or check_id must be provided")
        return self


class RetrieveMaturityRequest(BaseModel):
    query: Optional[str] = None
    domain: Optional[str] = None
    capability_id: Optional[str] = None
    top_k: int = 5
    debug: bool = False
    retrieval_mode: Literal["lexical", "vector", "hybrid"] = "hybrid"

    @model_validator(mode="after")
    def validate_input(self):
        if not self.query and not self.capability_id:
            raise ValueError("either query or capability_id must be provided")
        return self


class ResolveMappingRequest(BaseModel):
    check_id: str
    provider: Optional[str] = "aws"
    service: Optional[str] = None


class FindingInput(BaseModel):
    check_id: str
    service: str
    status: str
    severity: Optional[str] = None
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None


class ContextBuildRequest(BaseModel):
    finding: FindingInput
    include_check_context: bool = True
    include_maturity_context: bool = True
    include_mapping_context: bool = True
    top_k: int = 3
   
   
# ============================================================
# Context Construction models
# ============================================================

class ContextBundleStats(BaseModel):
    check_count: int = 0
    mapping_count: int = 0
    capability_count: int = 0


class ContextEvidenceItem(BaseModel):
    doc_id: str
    source_type: str
    doc_type: str
    title: Optional[str] = None
    short_text: str
    why_selected: str
    score: Optional[float] = None
    confidence: Optional[Confidence] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SelectedCheckContext(BaseModel):
    check_id: str
    doc_id: str
    service: Optional[str] = None
    title: Optional[str] = None
    short_text: str
    matched_by: List[str] = Field(default_factory=list)
    score: Optional[float] = None
    confidence: Optional[Confidence] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SelectedMappingContext(BaseModel):
    check_id: str
    capability_id: str
    capability_name: Optional[str] = None
    mapping_confidence: Optional[Confidence] = None
    mapping_type: Optional[str] = None
    review_status: Optional[str] = None
    rationale: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SelectedCapabilityContext(BaseModel):
    capability_id: str
    doc_id: str
    capability_name: Optional[str] = None
    domain: Optional[str] = None
    short_text: str
    score: Optional[float] = None
    confidence: Optional[Confidence] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PromptReadyContext(BaseModel):
    header: str
    evidence_block: str
    guidance_block: str

# --- Bundle Schema Contracts ---

class BundleMapping(BaseModel):
    check_id: str
    capability_id: str
    capability_name: Optional[str] = "Unknown capability"
    mapping_confidence: Optional[Confidence] = None
    mapping_type: Optional[str] = None
    review_status: Optional[str] = None
    rationale_short: Optional[str] = None

class PlanningFinding(BaseModel):
    check_id: str
    service: Optional[str] = "unknown"
    title: Optional[str] = "Unknown Check"
    severity: Optional[str] = None

class PlanningBundle(BaseModel):
    related_findings: List[PlanningFinding] = Field(default_factory=list)
    control_mapping_ids: List[str] = Field(default_factory=list)
    maturity_capability_ids: List[str] = Field(default_factory=list)

class RiskFinding(BaseModel):
    check_id: str
    service: Optional[str] = None
    title: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    risk: Optional[str] = None
    remediation: Optional[str] = None

class RiskMapping(BaseModel):
    check_id: str
    capability_id: str
    mapping_confidence: str

class RiskCapability(BaseModel):
    capability_id: str
    capability_name: Optional[str] = "Unknown capability"
    short_text: str

class BundleCapability(BaseModel):
    capability_id: str
    capability_name: Optional[str] = "Unknown capability"
    stage: Optional[str] = None
    summary_short: Optional[str] = None
    risk_explanation_short: Optional[str] = None
    guidance_short: Optional[str] = None
    recommended_practices_short: List[str] = Field(default_factory=list)

class RiskBundle(BaseModel):
    primary_finding: Optional[RiskFinding] = None
    related_findings: List[RiskFinding] = Field(default_factory=list)
    control_mapping: List[RiskMapping] = Field(default_factory=list)
    maturity_context: List[RiskCapability] = Field(default_factory=list)

class ReportFinding(BaseModel):
    check_id: str
    title: str
    severity: Optional[str] = None
    risk_summary: Optional[str] = None

class ReportCapability(BaseModel):
    capability_id: str
    capability_name: Optional[str] = "Unknown capability"
    summary_short: str

class ReportBundle(BaseModel):
    primary_topics: List[str] = Field(default_factory=list)
    key_findings: List[ReportFinding] = Field(default_factory=list)
    control_themes: List[ReportCapability] = Field(default_factory=list)
    recommended_practices: List[str] = Field(default_factory=list)


class ContextPayload(BaseModel):
    planning_bundle: Optional[PlanningBundle] = None
    risk_bundle: Optional[RiskBundle] = None
    report_bundle: Optional[ReportBundle] = None

class ContextDiagnostics(BaseModel):
    bundle_stats: ContextBundleStats = Field(default_factory=ContextBundleStats)
    selected_checks: List[SelectedCheckContext] = Field(default_factory=list)
    selected_mappings: List[SelectedMappingContext] = Field(default_factory=list)
    selected_capabilities: List[SelectedCapabilityContext] = Field(default_factory=list)
    evidence_summary: List[ContextEvidenceItem] = Field(default_factory=list)
    adjusted_confidence: Optional[str] = None

class ContextBuildData(BaseModel):
    consumer: ContextConsumer
    query: Optional[str] = None
    payload: ContextPayload
    diagnostics: ContextDiagnostics


class ContextBuildRequest(BaseModel):
    query: Optional[str] = None
    consumer: ContextConsumer
    provider: str = "aws"
    service: Optional[str] = None
    domain: Optional[str] = None
    check_ids: List[str] = Field(default_factory=list)
    findings: List[FindingInput] = Field(default_factory=list)
    top_k: int = 5
    retrieval_mode: Literal["lexical", "vector", "hybrid"] = "hybrid"
    include_mappings: bool = True
    include_maturity: bool = True
    max_context_items: int = 8
    max_chars_per_item: int = 600
    debug: bool = False

    @model_validator(mode="after")
    def validate_input(self):
        has_query = bool(self.query and self.query.strip())
        has_check_ids = len(self.check_ids) > 0
        has_findings = len(self.findings) > 0

        if not (has_query or has_check_ids or has_findings):
            raise ValueError("at least one of query, check_ids, or findings must be provided")

        if self.top_k < 1:
            raise ValueError("top_k must be >= 1")

        if self.max_context_items < 1:
            raise ValueError("max_context_items must be >= 1")

        if self.max_chars_per_item < 100:
            raise ValueError("max_chars_per_item must be >= 100")

        return self


class ContextBuildResponse(BaseModel):
    request_id: str
    status: Status
    data: ContextBuildData
    meta: MetaInfo
    errors: List[ErrorItem] = Field(default_factory=list) 
    
BuildContextRequest = ContextBuildRequest