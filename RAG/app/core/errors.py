from typing import Any, Dict, List, Optional

from .models import ErrorItem, MetaInfo, ResponseEnvelope


def make_error_item(
    code: str, message: str, details: Optional[Any] = None
) -> ErrorItem:
    return ErrorItem(code=code, message=message, details=details)


def make_response(
    request_id: str,
    status: str,
    data: Dict[str, Any],
    meta: MetaInfo,
    errors: Optional[List[ErrorItem]] = None,
) -> ResponseEnvelope:
    return ResponseEnvelope(
        request_id=request_id,
        status=status,
        data=data,
        meta=meta,
        errors=errors or [],
    )


def error_meta(
    index_version: str, confidence: str = "low", review_recommended: bool = True
) -> MetaInfo:
    return MetaInfo(
        index_version=index_version,
        confidence=confidence,
        review_recommended=review_recommended,
    )


# Common error codes
VALIDATION_ERROR = "validation_error"
NOT_FOUND = "not_found"
INDEX_UNAVAILABLE = "index_unavailable"
TIMEOUT = "timeout"
INTERNAL_ERROR = "internal_error"
UNSUPPORTED_REQUEST = "unsupported_request"
CHECK_ID_NOT_FOUND = "check_id_not_found"
MAPPING_MISSING = "mapping_missing"
SERVICE_AMBIGUOUS = "service_ambiguous"
LOW_CONFIDENCE = "low_confidence_candidates"
