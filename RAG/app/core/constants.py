"""
Centralized shared constants for the RAG system.

Single source of truth for intent clusters, entity gates, and query hint terms.
Previously these were duplicated across pipeline.py, context_builder.py,
gen_maturity_mapping.py, and router.py with inconsistencies.
"""

from __future__ import annotations

from typing import Dict, List, Set


# ---------------------------------------------------------------------------
# CONTROL_INTENT_CLUSTERS
#
# Merged superset from:
#   - pipeline.py::_CONTROL_INTENT_MARKERS (5 intents)
#   - context_builder.py::_CONTROL_FAMILY_GATES (5 intents)
#   - gen_maturity_mapping.py::CONTROL_INTENT_CLUSTERS (6 intents)
#
# Used for: control family detection in retrieval scoring, entity gating,
#           and maturity mapping generation.
# ---------------------------------------------------------------------------
CONTROL_INTENT_CLUSTERS: Dict[str, List[str]] = {
    "public_access": [
        "public access",
        "publicly accessible",
        "public exposure",
        "public read",
        "public write",
        "anonymous access",
        "unauthenticated access",
        "internet exposed",
        "world readable",
        "world writable",
        "block public access",
    ],
    "encryption_at_rest": [
        "encryption at rest",
        "encrypt everything",
        "default encryption",
        "server side encryption",
        "sse",
        "kms",
        "customer managed key",
        "stored data",
        "storage encryption",
    ],
    "encryption_in_transit": [
        "encryption in transit",
        "secure transport",
        "https",
        "tls",
        "ssl",
        "secure protocol",
        "transport encryption",
    ],
    "identity_access": [
        "least privilege",
        "identity",
        "iam",
        "mfa",
        "password",
        "credential",
        "role",
        "permission",
        "policy",
    ],
    "logging_monitoring": [
        "cloudtrail",
        "logging",
        "audit",
        "audit logs",
        "audit api calls",
        "monitoring",
        "detection",
    ],
    "resilience_backup": [
        "backup",
        "recovery",
        "resilience",
        "business continuity",
        "disaster recovery",
        "rto",
        "rpo",
    ],
}


# ---------------------------------------------------------------------------
# QUERY_INTENT_CLUSTERS
#
# From context_builder.py::_INTENT_CLUSTERS.
# Used for: lightweight query intent detection in ContextBuilder to drive
#           coverage-aware selection (planning consumer).
# These are shorter keyword triggers (vs. the longer phrases in
# CONTROL_INTENT_CLUSTERS which are used for control family matching).
# ---------------------------------------------------------------------------
QUERY_INTENT_CLUSTERS: Dict[str, List[str]] = {
    "encryption": ["encrypt", "kms", "ssl", "tls", "at rest", "in transit", "cmk"],
    "public_access": ["public", "exposed", "open", "unrestricted", "internet"],
    "iam": ["iam", "user", "role", "permission", "policy", "password", "mfa", "credential"],
    "logging": ["log", "cloudtrail", "audit", "trail", "monitoring", "cloudwatch"],
    "network": ["vpc", "sg", "security group", "nacl", "network", "port", "ingress", "egress", "firewall"],
    "backup": ["backup", "snapshot", "recovery", "retention", "rto", "rpo"],
    "access_control": ["access", "control", "restrict", "allow", "deny", "block"],
    "root": ["root", "admin", "superuser"],
    "secrets": ["secret", "key", "token", "api key", "credential", "password"],
}


# ---------------------------------------------------------------------------
# PRODUCT_ENTITY_GATES
#
# Merged superset from:
#   - pipeline.py::_PRODUCT_ENTITY_GATES (7 entities)
#   - context_builder.py::_PRODUCT_ENTITY_GATES (11 entities)
#   - gen_maturity_mapping.py::PRODUCT_ENTITY_GATES (8 entities)
#
# Used for: preventing irrelevant capability mappings from being matched
#           to checks. If a capability name contains a product entity token,
#           the check must contain at least one required signal.
# ---------------------------------------------------------------------------
PRODUCT_ENTITY_GATES: Dict[str, List[str]] = {
    "bedrock": [
        "bedrock", "genai", "gen_ai", "generative", "llm",
        "foundationmodel", "foundation_model", "fm", "prompt",
    ],
    "genai": [
        "bedrock", "genai", "gen_ai", "generative", "llm", "ai", "ml", "prompt",
    ],
    "generative": [
        "bedrock", "genai", "gen_ai", "generative", "llm", "ai", "prompt",
    ],
    "prompt": [
        "bedrock", "genai", "llm", "prompt", "inference",
    ],
    "sagemaker": [
        "sagemaker", "sagemaker_", "_sagemaker", "ml", "model", "training", "endpoint",
    ],
    "guardduty": [
        "guardduty", "guard_duty", "guard duty", "threat", "malware",
    ],
    "macie": [
        "macie", "sensitive", "sensitive data", "pii", "data_classification", "classification",
    ],
    "inspector": [
        "inspector", "vulnerability", "cve", "ecr",
    ],
    "waf": [
        "waf", "web_acl", "web acl", "webacl", "rate_limit", "rate limit",
        "sql_injection", "sql injection", "xss",
    ],
    "shield": [
        "shield", "ddos", "dos",
    ],
    "securityhub": [
        "securityhub", "security_hub", "hub",
    ],
}


# ---------------------------------------------------------------------------
# KNOWN_SERVICES
#
# From router.py. Used for: query routing (check_id detection heuristic).
# ---------------------------------------------------------------------------
KNOWN_SERVICES: Set[str] = {
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


# ---------------------------------------------------------------------------
# Query routing hint terms
#
# From router.py. Used for: corpus routing heuristics.
# ---------------------------------------------------------------------------
MATURITY_HINT_TERMS: Set[str] = {
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

CHECK_HINT_TERMS: Set[str] = {
    "check",
    "finding",
    "prowler",
    "security check",
    "misconfiguration",
    "remediation",
    "risk",
}
