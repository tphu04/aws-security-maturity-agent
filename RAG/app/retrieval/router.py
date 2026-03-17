from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from app.ingestion.normalizers import normalize_service
from app.ingestion.normalizers import _normalize_for_index as normalize_text_like_index
from app.ingestion.normalizers import _normalize_identifier as normalize_identifier


QueryType = Literal[
    "check_search",
    "maturity_search",
    "mapping_resolution",
    "context_build",
]


KNOWN_SERVICES = {
    "s3",
    "iam",
    "ec2",
    "cloudtrail",
    "kms",
    "rds",
    "eks",
    "lambda",
    "vpc",
    "guardduty",
    "config",
    "acm",
    "secretsmanager",
    "organizations",
    "elb",
    "elbv2",
    "efs",
    "dynamodb",
    "glue",
    "emr",
    "mq",
    "cognito",
    "cloudfront",
    "storagegateway",
    "ecr",
    "workspaces",
    "bedrock",
    "networkfirewall",
    "accessanalyzer",
}


MATURITY_HINT_TERMS = {
    "maturity",
    "capability",
    "practice",
    "best practice",
    "control objective",
    "security outcome",
    "governance",
    "foundational",
    "advanced",
    "domain",
}


CHECK_HINT_TERMS = {
    "check",
    "finding",
    "prowler",
    "security check",
    "misconfiguration",
    "remediation",
    "risk",
}


def normalize_query(query: str) -> str:
    text = normalize_text_like_index(query or "")
    return text.lower()


def _identifier_parts(value: str) -> List[str]:
    normalized = normalize_identifier(value or "")
    if not normalized:
        return []
    return [p for p in normalized.split("_") if p]


def looks_like_check_id(value: str) -> bool:
    """
    Strict check_id heuristic.

    A valid check_id should:
    - normalize cleanly
    - contain at least 3 underscore-separated parts
    - begin with a known AWS service token

    This prevents natural-language strings like:
    'anyone_can_enumerate_objects_in_the_bucket'
    from being treated as exact check IDs.
    """
    normalized = normalize_identifier(value or "")
    if not normalized:
        return False

    parts = _identifier_parts(normalized)
    if len(parts) < 3:
        return False

    if parts[0] not in KNOWN_SERVICES:
        return False

    return len(normalized) >= 12


def looks_like_capability_id(value: str) -> bool:
    """
    Conservative maturity capability alias heuristic.

    Examples:
    - block_public_access
    - audit_api_calls
    - data_backups
    - encryption_at_rest
    - network_segmentation
    """
    raw = (value or "").strip()
    if not raw:
        return False

    if " " in raw:
        return False

    if looks_like_check_id(raw):
        return False

    normalized = normalize_identifier(raw)
    if not normalized:
        return False

    parts = _identifier_parts(normalized)
    if len(parts) < 2 or len(parts) > 8:
        return False

    return len(normalized) >= 8


def extract_service(query: str) -> Optional[str]:
    normalized = normalize_query(query)
    tokens = set(normalized.replace("-", "_").split())

    for service in KNOWN_SERVICES:
        if service in tokens:
            return service

    normalized_identifier = normalize_identifier(normalized)
    for service in KNOWN_SERVICES:
        if (
            normalized_identifier.startswith(f"{service}_")
            or f" {service} " in f" {normalized} "
        ):
            return service

    return None


@dataclass
class RouteDecision:
    query_type: QueryType
    normalized_query: str
    doc_types: List[str] = field(default_factory=list)
    filters: Dict[str, Any] = field(default_factory=dict)
    service: Optional[str] = None
    domain: Optional[str] = None
    provider: str = "aws"
    requires_exact_lookup: bool = False
    exact_check_id: Optional[str] = None
    exact_capability_id: Optional[str] = None


class SemanticRouter:
    """
    Phase 1 routing goals:
    - avoid false exact-check routing for NL underscore strings
    - support exact maturity capability aliases
    """

    def route(
        self,
        query: str,
        explicit_type: Optional[str] = None,
        provider: Optional[str] = "aws",
        service: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> RouteDecision:
        normalized_query = normalize_query(query)
        normalized_provider = (provider or "aws").strip().lower()
        normalized_service = (
            normalize_service(service) if service else extract_service(normalized_query)
        )
        normalized_domain = (
            normalize_text_like_index(domain).strip() if domain else None
        )

        exact_check_id = (
            normalize_identifier(query) if looks_like_check_id(query) else None
        )
        exact_capability_id = (
            normalize_identifier(query) if looks_like_capability_id(query) else None
        )

        if explicit_type == "mapping_resolution":
            exact_mapping_check_id = normalize_identifier(query)
            return RouteDecision(
                query_type="mapping_resolution",
                normalized_query=normalized_query,
                doc_types=["maturity_mapping"],
                filters=self._build_filters(
                    provider=normalized_provider,
                    service=normalized_service,
                    domain=None,
                    doc_types=["maturity_mapping"],
                ),
                service=normalized_service,
                domain=None,
                provider=normalized_provider,
                requires_exact_lookup=bool(exact_mapping_check_id),
                exact_check_id=exact_mapping_check_id or None,
                exact_capability_id=None,
            )

        if explicit_type == "maturity_search":
            return RouteDecision(
                query_type="maturity_search",
                normalized_query=normalized_query,
                doc_types=["maturity_capability"],
                filters=self._build_filters(
                    provider=normalized_provider,
                    service=None,
                    domain=normalized_domain,
                    doc_types=["maturity_capability"],
                ),
                service=None,
                domain=normalized_domain,
                provider=normalized_provider,
                requires_exact_lookup=bool(exact_capability_id),
                exact_check_id=None,
                exact_capability_id=exact_capability_id,
            )

        if explicit_type == "context_build":
            return RouteDecision(
                query_type="context_build",
                normalized_query=normalized_query,
                doc_types=["prowler_check"],
                filters=self._build_filters(
                    provider=normalized_provider,
                    service=normalized_service,
                    domain=None,
                    doc_types=["prowler_check"],
                ),
                service=normalized_service,
                domain=None,
                provider=normalized_provider,
                requires_exact_lookup=bool(exact_check_id),
                exact_check_id=exact_check_id,
                exact_capability_id=None,
            )

        if explicit_type == "check_search":
            return RouteDecision(
                query_type="check_search",
                normalized_query=normalized_query,
                doc_types=["prowler_check"],
                filters=self._build_filters(
                    provider=normalized_provider,
                    service=normalized_service,
                    domain=None,
                    doc_types=["prowler_check"],
                ),
                service=normalized_service,
                domain=None,
                provider=normalized_provider,
                requires_exact_lookup=bool(exact_check_id),
                exact_check_id=exact_check_id,
                exact_capability_id=None,
            )

        if exact_check_id:
            return RouteDecision(
                query_type="check_search",
                normalized_query=normalized_query,
                doc_types=["prowler_check"],
                filters=self._build_filters(
                    provider=normalized_provider,
                    service=normalized_service,
                    domain=None,
                    doc_types=["prowler_check"],
                ),
                service=normalized_service,
                domain=None,
                provider=normalized_provider,
                requires_exact_lookup=True,
                exact_check_id=exact_check_id,
                exact_capability_id=None,
            )

        if exact_capability_id:
            return RouteDecision(
                query_type="maturity_search",
                normalized_query=normalized_query,
                doc_types=["maturity_capability"],
                filters=self._build_filters(
                    provider=normalized_provider,
                    service=None,
                    domain=normalized_domain,
                    doc_types=["maturity_capability"],
                ),
                service=None,
                domain=normalized_domain,
                provider=normalized_provider,
                requires_exact_lookup=True,
                exact_check_id=None,
                exact_capability_id=exact_capability_id,
            )

        lower_query = normalized_query.lower()

        if any(term in lower_query for term in MATURITY_HINT_TERMS):
            return RouteDecision(
                query_type="maturity_search",
                normalized_query=normalized_query,
                doc_types=["maturity_capability"],
                filters=self._build_filters(
                    provider=normalized_provider,
                    service=None,
                    domain=normalized_domain,
                    doc_types=["maturity_capability"],
                ),
                service=None,
                domain=normalized_domain,
                provider=normalized_provider,
                requires_exact_lookup=False,
                exact_check_id=None,
                exact_capability_id=None,
            )

        if any(term in lower_query for term in CHECK_HINT_TERMS):
            return RouteDecision(
                query_type="check_search",
                normalized_query=normalized_query,
                doc_types=["prowler_check"],
                filters=self._build_filters(
                    provider=normalized_provider,
                    service=normalized_service,
                    domain=None,
                    doc_types=["prowler_check"],
                ),
                service=normalized_service,
                domain=None,
                provider=normalized_provider,
                requires_exact_lookup=False,
                exact_check_id=None,
                exact_capability_id=None,
            )

        return RouteDecision(
            query_type="check_search",
            normalized_query=normalized_query,
            doc_types=["prowler_check"],
            filters=self._build_filters(
                provider=normalized_provider,
                service=normalized_service,
                domain=None,
                doc_types=["prowler_check"],
            ),
            service=normalized_service,
            domain=None,
            provider=normalized_provider,
            requires_exact_lookup=False,
            exact_check_id=None,
            exact_capability_id=None,
        )

    @staticmethod
    def _build_filters(
        provider: Optional[str],
        service: Optional[str],
        domain: Optional[str],
        doc_types: Optional[List[str]],
    ) -> Dict[str, Any]:
        filters: Dict[str, Any] = {}
        if provider:
            filters["provider"] = provider
        if service:
            filters["service"] = service
        if domain:
            filters["domain"] = domain
        if doc_types and len(doc_types) == 1:
            filters["doc_type"] = doc_types[0]
        return filters
