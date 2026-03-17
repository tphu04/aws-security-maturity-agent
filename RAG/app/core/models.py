from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


Status = Literal["success", "partial", "error"]
retrieval_mode: Literal["lexical", "vector", "hybrid"] = "hybrid"

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
    
    
BuildContextRequest = ContextBuildRequest