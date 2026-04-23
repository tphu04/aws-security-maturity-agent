"""
Scope detection for the report agent.

Phase 1 — Scope Generalization (De-S3-bias).

Given a set of findings (and optional hints from the assessment plan and
AWS environment), this module returns a normalized ``scope`` dict that the
report agent, LLM writer and template can use to stay service-agnostic.

The scope dict exposes both a **specific** view (when one service clearly
dominates) and a **generic** view (when multiple services are in play). It
never assumes S3 — that assumption was the root cause the wider plan
targets.

Public surface
--------------
* ``SERVICE_DISPLAY`` — canonical display name per service id.
* ``RESOURCE_TERMS``  — (singular, plural) resource term per service id.
* ``GENERIC_FALLBACK`` — terms used when no service dominates.
* ``detect_scope(findings, env=None, services_hint=None)`` — main entry.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# Canonical display name for each AWS service id (lowercase keys).
SERVICE_DISPLAY: Dict[str, str] = {
    "s3": "Amazon S3",
    "iam": "AWS IAM",
    "ec2": "Amazon EC2",
    "rds": "Amazon RDS",
    "lambda": "AWS Lambda",
    "cloudtrail": "AWS CloudTrail",
    "cloudfront": "Amazon CloudFront",
    "kms": "AWS KMS",
    "sns": "Amazon SNS",
    "sqs": "Amazon SQS",
    "ecs": "Amazon ECS",
    "eks": "Amazon EKS",
    "vpc": "Amazon VPC",
    "route53": "Amazon Route 53",
    "apigateway": "Amazon API Gateway",
    "dynamodb": "Amazon DynamoDB",
    "elasticache": "Amazon ElastiCache",
    "elb": "Elastic Load Balancing",
    "elbv2": "Elastic Load Balancing v2",
    "guardduty": "Amazon GuardDuty",
    "config": "AWS Config",
    "securityhub": "AWS Security Hub",
    "secretsmanager": "AWS Secrets Manager",
    "ssm": "AWS Systems Manager",
}


# (singular, plural) resource term for each service id.
RESOURCE_TERMS: Dict[str, Tuple[str, str]] = {
    "s3": ("bucket", "buckets"),
    "iam": ("IAM entity", "IAM entities"),
    "ec2": ("instance", "instances"),
    "rds": ("database instance", "database instances"),
    "lambda": ("function", "functions"),
    "cloudtrail": ("trail", "trails"),
    "cloudfront": ("distribution", "distributions"),
    "kms": ("key", "keys"),
    "sns": ("topic", "topics"),
    "sqs": ("queue", "queues"),
    "ecs": ("cluster", "clusters"),
    "eks": ("cluster", "clusters"),
    "vpc": ("VPC", "VPCs"),
    "route53": ("hosted zone", "hosted zones"),
    "apigateway": ("API", "APIs"),
    "dynamodb": ("table", "tables"),
    "elasticache": ("cluster", "clusters"),
    "elb": ("load balancer", "load balancers"),
    "elbv2": ("load balancer", "load balancers"),
    "guardduty": ("detector", "detectors"),
    "config": ("configuration recorder", "configuration recorders"),
    "securityhub": ("Security Hub finding source", "Security Hub finding sources"),
    "secretsmanager": ("secret", "secrets"),
    "ssm": ("parameter", "parameters"),
}


GENERIC_FALLBACK: Dict[str, str] = {
    "display": "AWS Infrastructure",
    "term_singular": "resource",
    "term_plural": "resources",
}


# Findings belonging to one service dominate the scope when they account
# for more than this fraction of all service-tagged findings.
_DOMINANT_THRESHOLD = 0.7


def _infer_service_from_check_id(check_id: Optional[str]) -> Optional[str]:
    """Prowler check_ids are prefixed with the service id (e.g. ``s3_bucket_...``)."""
    if not check_id:
        return None
    token = str(check_id).split("_", 1)[0].strip().lower()
    return token or None


def _collect_services(
    findings: Optional[Iterable[Dict[str, Any]]],
) -> "Counter[str]":
    """Count findings per service id, inferring from check_id when needed."""
    counter: Counter[str] = Counter()
    for finding in findings or []:
        svc = finding.get("service") or _infer_service_from_check_id(
            finding.get("check_id") or finding.get("event_code")
        )
        if svc:
            counter[svc.lower()] += 1
    return counter


def _display_for(service: str) -> str:
    """Resolve a display name, falling back to a generic ``AWS XYZ`` label."""
    if service in SERVICE_DISPLAY:
        return SERVICE_DISPLAY[service]
    return f"AWS {service.upper()}"


def _terms_for(service: str) -> Tuple[str, str]:
    return RESOURCE_TERMS.get(
        service,
        (GENERIC_FALLBACK["term_singular"], GENERIC_FALLBACK["term_plural"]),
    )


def _empty_scope() -> Dict[str, Any]:
    return {
        "primary_service": None,
        "service_list": [],
        "is_multi_service": False,
        "service_display": GENERIC_FALLBACK["display"],
        "resource_term": GENERIC_FALLBACK["term_singular"],
        "resource_term_plural": GENERIC_FALLBACK["term_plural"],
        "dominance_ratio": 0.0,
        "source": "empty",
    }


def _normalize_hint(services_hint: Optional[Sequence[str]]) -> List[str]:
    if not services_hint:
        return []
    out: List[str] = []
    for svc in services_hint:
        if not svc:
            continue
        token = str(svc).strip().lower()
        if token and token not in out:
            out.append(token)
    return out


def detect_scope(
    findings: Optional[Iterable[Dict[str, Any]]] = None,
    env: Optional[Dict[str, Any]] = None,
    services_hint: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Detect the report scope (primary service + resource terminology).

    Parameters
    ----------
    findings : iterable of finding dicts, optional
        Used to infer services (``service`` field or ``check_id`` prefix).
    env : dict, optional
        Reserved for future use (e.g. future environment agents may list
        resources per service). Currently unused but kept for forward
        compatibility so callers do not need to be rewritten later.
    services_hint : sequence of str, optional
        Authoritative hint, typically ``assessment_plan.target_services``.
        When provided and non-empty it takes precedence over what is
        inferred from findings.

    Returns
    -------
    dict
        {
          "primary_service":     str | None,   # None when no single service dominates
          "service_list":        List[str],    # all service ids in scope, lower-cased
          "is_multi_service":    bool,
          "service_display":     str,          # "Amazon S3" or generic fallback
          "resource_term":       str,          # "bucket" / "resource"
          "resource_term_plural":str,          # "buckets" / "resources"
          "dominance_ratio":     float,        # share of the primary service
          "source":              str,          # "hint" | "findings" | "empty"
        }
    """
    _ = env  # reserved; accepted for forward compatibility

    hint_services = _normalize_hint(services_hint)
    counter = _collect_services(findings)

    # Build the effective service set. Hint wins when it's non-empty,
    # but counts still come from findings so multi-service heuristics
    # reflect real data.
    if hint_services:
        service_list = list(hint_services)
        # If the hint declares a single service, treat it as fully dominant
        # regardless of finding counts (assessment plan is authoritative
        # about scope, even if findings leak other service prefixes).
        if len(service_list) == 1:
            primary = service_list[0]
            term_s, term_p = _terms_for(primary)
            return {
                "primary_service": primary,
                "service_list": service_list,
                "is_multi_service": False,
                "service_display": _display_for(primary),
                "resource_term": term_s,
                "resource_term_plural": term_p,
                "dominance_ratio": 1.0,
                "source": "hint",
            }
        # Multi-service hint: decide whether finding counts crown a dominant one.
        source = "hint"
        total_found = sum(counter.values())
        counts_in_hint = {s: counter.get(s, 0) for s in service_list}
        found_total = sum(counts_in_hint.values()) or total_found
    else:
        if not counter:
            return _empty_scope()
        service_list = sorted(counter.keys(), key=lambda s: -counter[s])
        source = "findings"
        counts_in_hint = dict(counter)
        found_total = sum(counter.values())

    if not service_list:
        return _empty_scope()

    # Determine dominance using the inferred counts.
    if found_total > 0 and any(counts_in_hint.values()):
        primary_candidate = max(
            counts_in_hint.items(), key=lambda kv: kv[1]
        )[0]
        dominance = counts_in_hint[primary_candidate] / found_total
    else:
        primary_candidate = service_list[0]
        dominance = 0.0

    is_multi = len(service_list) > 1
    dominant = dominance > _DOMINANT_THRESHOLD

    if is_multi and not dominant:
        return {
            "primary_service": None,
            "service_list": service_list,
            "is_multi_service": True,
            "service_display": GENERIC_FALLBACK["display"],
            "resource_term": GENERIC_FALLBACK["term_singular"],
            "resource_term_plural": GENERIC_FALLBACK["term_plural"],
            "dominance_ratio": round(dominance, 4),
            "source": source,
        }

    primary = primary_candidate
    term_s, term_p = _terms_for(primary)
    return {
        "primary_service": primary,
        "service_list": service_list,
        "is_multi_service": is_multi,
        "service_display": _display_for(primary),
        "resource_term": term_s,
        "resource_term_plural": term_p,
        "dominance_ratio": round(dominance if is_multi else 1.0, 4),
        "source": source,
    }


def is_valid_resource(resource: Optional[str], service: Optional[str],
                      account_id: Optional[str] = None) -> bool:
    """Service-aware replacement for the old ``_looks_like_bucket`` helper.

    The old heuristic rejected account-ID-like strings so S3 *_account_level_*
    checks would not inflate the bucket count. We preserve that guard and
    extend it with sensible rules for other services. Anything that passes
    the guard and has at least 3 characters is accepted — stricter rules
    would wrongly drop obscure ARN shapes.
    """
    if resource is None:
        return False
    r = str(resource).strip()
    if len(r) < 3:
        return False

    acct = str(account_id).strip() if account_id else ""
    if acct and r == acct:
        return False
    # Pure digit strings are almost always an account id leaking through.
    if r.isdigit():
        return False

    svc = (service or "").lower()
    if svc == "s3":
        # Bucket names never start with "arn:" and are never bare numbers.
        return not r.startswith("arn:")
    if svc == "iam":
        return r.startswith("arn:aws:iam") or "/" in r or r.isidentifier()
    if svc == "ec2":
        return (
            r.startswith("i-")
            or r.startswith("arn:aws:ec2")
            or r.startswith("sg-")
            or r.startswith("vol-")
        )
    # Default: accept any non-empty, non-numeric string. Callers can tighten
    # the rule later by extending this function.
    return True
