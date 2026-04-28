"""Case generator for Report Agent Evaluation v3.

Produces ``benchmark_report_cases_v3.json`` — 24 cases grouped by
capability (C1..C5). 7 cases port the existing baselines A..G from
``tests/fixtures/report_baseline/input/``; 17 are synthesized here.

Each case schema:
    {
      "case_id":   str,
      "group":     "C1_scope_detection" | ... | "C5_rag_grounding",
      "input":     { "report_data": {...}, "rag_snapshot": {...} },
      "expected":  {
          "scope":                {...},
          "forbidden_terms":      [str, ...],
          "required_capabilities":[str, ...],
          "allowed_numbers_snapshot":[int, ...],
          "severity_ranking_gt":  [finding_uid, ...]   # C3 only
      }
    }

Run as a script: ``python -m benchmarks.llm_generation.fixtures.case_generator``.
"""
# ---------------------------------------------------------------------------
# Langfuse bench guard (Phase F.7) — runner default OFF, dev có thể override.
# ---------------------------------------------------------------------------
import os as _os_bench_guard
_os_bench_guard.environ.setdefault("LANGFUSE_ENABLED", "false")

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE_DIR = REPO_ROOT / "tests" / "fixtures" / "report_baseline" / "input"
OUT_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "llm_generation"
    / "benchmark_report_cases_v3.json"
)


# --------------------------------------------------------------------------
# Severity ordering (for NDCG ground truth + ranking cases)
# --------------------------------------------------------------------------

_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def _sev_score(sev: str) -> int:
    return _SEV_RANK.get((sev or "").strip().lower(), 0)


# --------------------------------------------------------------------------
# Building blocks for synthetic fixtures
# --------------------------------------------------------------------------

_SERVICE_CHECK_BANK: Dict[str, List[Dict[str, Any]]] = {
    "s3": [
        {
            "check_id": "s3_bucket_public_access",
            "description": "S3 bucket has public read access",
            "severity": "Critical",
            "resource": "arn:aws:s3:::public-data",
        },
        {
            "check_id": "s3_bucket_versioning",
            "description": "S3 bucket versioning is disabled",
            "severity": "High",
            "resource": "arn:aws:s3:::logs-prod",
        },
        {
            "check_id": "s3_bucket_encryption",
            "description": "S3 bucket default encryption is off",
            "severity": "High",
            "resource": "arn:aws:s3:::media-assets",
        },
        {
            "check_id": "s3_bucket_logging",
            "description": "S3 bucket access logging is not enabled",
            "severity": "Medium",
            "resource": "arn:aws:s3:::reports-archive",
        },
    ],
    "iam": [
        {
            "check_id": "iam_root_mfa_enabled",
            "description": "Root account MFA is disabled",
            "severity": "Critical",
            "resource": "123456789012",
        },
        {
            "check_id": "iam_user_mfa_enabled",
            "description": "IAM user does not have MFA enabled",
            "severity": "High",
            "resource": "arn:aws:iam::123456789012:user/alice",
        },
        {
            "check_id": "iam_password_policy_strong",
            "description": "Password policy does not meet strength requirements",
            "severity": "Medium",
            "resource": "123456789012",
        },
        {
            "check_id": "iam_access_key_rotation",
            "description": "IAM access key has not been rotated in 90 days",
            "severity": "Medium",
            "resource": "arn:aws:iam::123456789012:user/svc-ci",
        },
    ],
    "ec2": [
        {
            "check_id": "ec2_sg_open_ssh",
            "description": "Security group allows SSH (22) from 0.0.0.0/0",
            "severity": "Critical",
            "resource": "sg-0abc1234",
        },
        {
            "check_id": "ec2_ebs_encryption",
            "description": "EBS volume is not encrypted",
            "severity": "High",
            "resource": "vol-0def5678",
        },
        {
            "check_id": "ec2_instance_public_ip",
            "description": "EC2 instance has a public IPv4 address",
            "severity": "Medium",
            "resource": "i-0123456789abcdef0",
        },
        {
            "check_id": "ec2_imdsv2_enforced",
            "description": "IMDSv2 is not enforced on EC2 instance",
            "severity": "Medium",
            "resource": "i-0fedcba987654321",
        },
    ],
    "rds": [
        {
            "check_id": "rds_instance_public",
            "description": "RDS instance is publicly accessible",
            "severity": "Critical",
            "resource": "arn:aws:rds:us-east-1:123456789012:db:prod-db",
        },
        {
            "check_id": "rds_storage_encryption",
            "description": "RDS storage encryption is not enabled",
            "severity": "High",
            "resource": "arn:aws:rds:us-east-1:123456789012:db:stg-db",
        },
    ],
}


_CAPABILITY_BANK: Dict[str, Dict[str, Any]] = {
    "s3": {
        "capability_id": "data-storage",
        "capability_name": "Data Storage Protection",
        "summary": "Protect data at rest in object storage.",
        "risk_explanation": "Misconfigured buckets expose sensitive data.",
        "recommendation": "Enforce encryption, block public access, enable versioning and logging.",
    },
    "iam": {
        "capability_id": "identity-mgmt",
        "capability_name": "Identity And Access Management",
        "summary": "Identity And Access Management controls for IAM.",
        "risk_explanation": "Weak IAM exposes the account to takeover.",
        "recommendation": "Enforce MFA, strong password policy, and rotate keys regularly.",
    },
    "ec2": {
        "capability_id": "compute-hardening",
        "capability_name": "Compute Workload Hardening",
        "summary": "Harden EC2 instances and security groups.",
        "risk_explanation": "Open ports and unencrypted volumes expose workloads.",
        "recommendation": "Restrict security groups, encrypt EBS, enforce IMDSv2.",
    },
    "rds": {
        "capability_id": "database-protection",
        "capability_name": "Database Protection",
        "summary": "Baseline controls for managed relational databases.",
        "risk_explanation": "Public databases or unencrypted storage leaks data.",
        "recommendation": "Disable public accessibility, enable encryption at rest.",
    },
}


_DISPLAY = {
    "s3": "Amazon S3",
    "iam": "AWS IAM",
    "ec2": "Amazon EC2",
    "rds": "Amazon RDS",
}
_RESOURCE_PLURAL = {
    "s3": "buckets",
    "iam": "IAM entities",
    "ec2": "instances",
    "rds": "database instances",
}

# Which ancillary service terms should NEVER appear when scope is another service.
_OFF_SCOPE_TERMS = {
    "s3": ["iam", "ec2", "rds", "role", "instance"],
    "iam": ["s3", "bucket", "amazon s3", "ec2", "rds"],
    "ec2": ["s3", "bucket", "iam role", "rds"],
    "rds": ["s3", "bucket", "iam role", "ec2"],
}


# --------------------------------------------------------------------------
# Helpers to build findings / stats / raw rows
# --------------------------------------------------------------------------

def _make_finding_row(
    stt: int,
    service: str,
    check_id: str,
    description: str,
    severity: str,
    resource: str,
    status_before: str = "FAIL",
    status_after: str = "PASS",
) -> Dict[str, Any]:
    change = "Fixed" if status_before == "FAIL" and status_after == "PASS" else (
        "Still Failing" if status_after == "FAIL" else "Unchanged"
    )
    return {
        "stt": stt,
        "finding": description,
        "service": service,
        "resource": resource,
        "severity": severity,
        "before": status_before,
        "after": status_after,
        "change": change,
    }


def _make_raw_finding(
    idx: int,
    service: str,
    check_id: str,
    description: str,
    severity: str,
    resource: str,
    status: str = "FAIL",
) -> Dict[str, Any]:
    return {
        "finding_uid": f"uid-{service}-{idx}",
        "finding_id": f"f-{service}-{idx}",
        "event_code": check_id,
        "check_id": check_id,
        "service": service,
        "resource_id": resource,
        "resource": resource,
        "severity": severity,
        "status": status,
        "description": description,
    }


def _compute_pre(raw: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(raw)
    fail = sum(1 for f in raw if f["status"] == "FAIL")
    pre = {
        "total": total,
        "pass": total - fail,
        "fail": fail,
        "severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
    }
    for f in raw:
        if f["status"] != "FAIL":
            continue
        sev = f["severity"].lower()
        if sev in pre["severity"]:
            pre["severity"][sev] += 1
    return pre


def _compute_post(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    initial_fail = sum(1 for r in rows if r["before"] == "FAIL")
    fixed = sum(
        1 for r in rows
        if r["before"] == "FAIL" and r["after"] == "PASS"
    )
    still_failing = initial_fail - fixed
    return {
        "initial_pass": len(rows) - initial_fail,
        "initial_fail": initial_fail,
        "final_pass": len(rows) - still_failing,
        "final_fail": still_failing,
        "fixed": fixed,
        "failed": 0,
        "manual": 0,
    }


def _make_rag(
    service_ids: List[str],
    confidence: str = "medium",
    capability_details_override: Optional[List[Dict[str, Any]]] = None,
    noise_capabilities: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    primary_topics = [_CAPABILITY_BANK[s]["capability_name"] for s in service_ids]
    control_themes = [
        {
            "capability_id": _CAPABILITY_BANK[s]["capability_id"],
            "capability_name": _CAPABILITY_BANK[s]["capability_name"],
            "summary_short": _CAPABILITY_BANK[s]["summary"],
        }
        for s in service_ids
    ]
    if capability_details_override is not None:
        cap_details = capability_details_override
    else:
        cap_details = [
            {
                **_CAPABILITY_BANK[s],
                "guidance_questions": [],
            }
            for s in service_ids
        ]
    if noise_capabilities:
        cap_details = cap_details + noise_capabilities
    return {
        "primary_topics": primary_topics,
        "control_themes": control_themes,
        "capability_details": cap_details,
        "recommended_practices": [
            f"Apply the {_CAPABILITY_BANK[s]['capability_name']} baseline on every resource."
            for s in service_ids
        ] + ["Log and monitor configuration drift."],
        "key_findings": [],
        "confidence": confidence,
    }


def _make_empty_rag() -> Dict[str, Any]:
    return {
        "primary_topics": [],
        "control_themes": [],
        "capability_details": [],
        "recommended_practices": [],
        "key_findings": [],
        "confidence": "low",
    }


def _build_report_data(
    raw: List[Dict[str, Any]],
    services: List[str],
    user_request: str,
    buckets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for i, r in enumerate(raw, start=1):
        # Mark first FAIL of each severity as still-failing so the post
        # stats aren't trivially all-fixed.
        after = "PASS"
        if r["status"] == "FAIL" and r["severity"] == "Critical" and i % 3 == 1:
            after = "FAIL"
        rows.append(_make_finding_row(
            stt=i,
            service=r["service"],
            check_id=r["check_id"],
            description=r["description"],
            severity=r["severity"],
            resource=r["resource"],
            status_before=r["status"],
            status_after=after if r["status"] == "FAIL" else "PASS",
        ))
    pre = _compute_pre(raw)
    post = _compute_post(rows)
    return {
        "pre": pre,
        "post": post,
        "environment": {
            "account_id": "123456789012",
            "region": "us-east-1",
            "buckets": buckets or [],
        },
        "scope": {
            "services": services,
            "date": "2026-04-20",
            "user_request": user_request,
        },
        "findings_table": rows,
        "success_findings": [],
        "failed_findings": [],
        "manual_findings": [],
        "raw_pre_findings": raw,
    }


def _expected_scope_for(
    services: List[str],
    is_multi: bool = False,
) -> Dict[str, Any]:
    if is_multi:
        return {
            "primary_service": None,
            "service_list": sorted(services),
            "is_multi_service": True,
            "service_display": "AWS Infrastructure",
            "resource_term_plural": "resources",
        }
    s = services[0]
    return {
        "primary_service": s,
        "service_list": [s],
        "is_multi_service": False,
        "service_display": _DISPLAY[s],
        "resource_term_plural": _RESOURCE_PLURAL[s],
    }


def _allowed_numbers(report_data: Dict[str, Any]) -> List[int]:
    pre, post = report_data["pre"], report_data["post"]
    nums = {
        pre["total"], pre["pass"], pre["fail"],
        post["initial_pass"], post["initial_fail"],
        post["final_pass"], post["final_fail"],
        post["fixed"], post["failed"], post["manual"],
        int(report_data["environment"]["account_id"]),
        *(v for v in pre["severity"].values()),
    }
    nums.discard(0)
    return sorted(nums)


# --------------------------------------------------------------------------
# Port baseline A..G
# --------------------------------------------------------------------------

_BASELINE_MAP: Dict[str, Dict[str, Any]] = {
    "A": {
        "case_id": "c2_all_pass_zero_fail",
        "group": "C2_hallucination_stress",
        "services": ["s3"],
        "is_multi": False,
    },
    "B": {
        "case_id": "c3_multi_severity_balanced",
        "group": "C3_prioritization",
        "services": ["s3"],
        "is_multi": False,
        "needs_ranking_gt": True,
    },
    "C": {
        "case_id": "c1_single_s3_dominant",
        "group": "C1_scope_detection",
        "services": ["s3"],
        "is_multi": False,
    },
    "D": {
        "case_id": "c4_empty_env_empty_findings",
        "group": "C4_structural_robustness",
        "services": ["s3"],  # baseline declared s3 scope, kept
        "is_multi": False,
    },
    "E": {
        "case_id": "c3_findings_100plus_top5",
        "group": "C3_prioritization",
        "services": ["s3"],
        "is_multi": False,
        "needs_ranking_gt": True,
        "expand_to": 100,
    },
    "F": {
        "case_id": "c1_single_iam_dominant",
        "group": "C1_scope_detection",
        "services": ["iam"],
        "is_multi": False,
    },
    "G": {
        "case_id": "c1_two_service_balanced",
        "group": "C1_scope_detection",
        "services": None,  # filled from the file
        "is_multi": True,
    },
}


def _load_baseline(letter: str) -> Dict[str, Any]:
    path = BASELINE_DIR / f"{letter}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _ranking_gt(raw: List[Dict[str, Any]]) -> List[str]:
    """Severity-desc order → finding_uid list. Ties broken by original order."""
    indexed = list(enumerate(raw))
    indexed.sort(key=lambda kv: (-_sev_score(kv[1]["severity"]), kv[0]))
    return [r["finding_uid"] for _, r in indexed[:5]]


def _expand_findings(raw: List[Dict[str, Any]], target: int) -> List[Dict[str, Any]]:
    """Duplicate rows with unique uids until we reach ``target`` findings."""
    if len(raw) >= target:
        return raw
    out = list(raw)
    template = raw or [_make_raw_finding(
        0, "s3", "s3_bucket_encryption", "S3 bucket default encryption is off",
        "Medium", "arn:aws:s3:::extra",
    )]
    i = 0
    while len(out) < target:
        base = deepcopy(template[i % len(template)])
        idx = len(out) + 1
        base["finding_uid"] = f"uid-expand-{idx}"
        base["finding_id"] = f"f-expand-{idx}"
        out.append(base)
        i += 1
    return out


def port_baseline(letter: str) -> Dict[str, Any]:
    meta = _BASELINE_MAP[letter]
    data = _load_baseline(letter)
    raw = data.get("raw_pre_findings", []) or []
    if meta.get("expand_to"):
        raw = _expand_findings(raw, meta["expand_to"])
        data = dict(data)
        data["raw_pre_findings"] = raw
        # Rebuild findings_table / pre / post consistent with expanded raw.
        rows = [
            _make_finding_row(
                stt=i + 1,
                service=r["service"],
                check_id=r["check_id"],
                description=r["description"],
                severity=r["severity"],
                resource=r["resource"],
                status_before=r["status"],
                status_after="PASS" if r["status"] == "FAIL" else "PASS",
            )
            for i, r in enumerate(raw)
        ]
        data["findings_table"] = rows
        data["pre"] = _compute_pre(raw)
        data["post"] = _compute_post(rows)

    services = meta["services"]
    if services is None:
        services = sorted({
            (r.get("service") or "").lower()
            for r in raw if r.get("service")
        })
        services = [s for s in services if s]

    rag = data.get("rag_context") or _make_empty_rag()

    expected: Dict[str, Any] = {
        "scope": _expected_scope_for(services, is_multi=meta["is_multi"]),
        "forbidden_terms": [] if meta["is_multi"] else _OFF_SCOPE_TERMS.get(services[0], []),
        "required_capabilities": [_CAPABILITY_BANK[s]["capability_name"] for s in services if s in _CAPABILITY_BANK],
        "allowed_numbers_snapshot": _allowed_numbers(data),
    }
    if meta.get("needs_ranking_gt"):
        expected["severity_ranking_gt"] = _ranking_gt(raw)

    return {
        "case_id": meta["case_id"],
        "group": meta["group"],
        "source": f"baseline_{letter}",
        "input": {
            "report_data": {k: v for k, v in data.items() if k != "rag_context"},
            "rag_snapshot": rag,
        },
        "expected": expected,
    }


# --------------------------------------------------------------------------
# Synthesize new cases (17)
# --------------------------------------------------------------------------

def _make_case_from_checks(
    case_id: str,
    group: str,
    services: List[str],
    check_specs: List[tuple],
    user_request: str,
    rag_override: Optional[Dict[str, Any]] = None,
    is_multi: bool = False,
    needs_ranking_gt: bool = False,
    forbidden_terms: Optional[List[str]] = None,
    required_capabilities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """``check_specs`` = list of (service, check_index, status) tuples."""
    raw: List[Dict[str, Any]] = []
    for i, (svc, bank_idx, status) in enumerate(check_specs, start=1):
        bank = _SERVICE_CHECK_BANK[svc][bank_idx]
        # Create a unique resource per iteration for realism.
        resource = bank["resource"]
        if svc == "s3":
            resource = f"arn:aws:s3:::{bank['check_id']}-{i}"
        raw.append(_make_raw_finding(
            idx=i,
            service=svc,
            check_id=bank["check_id"],
            description=bank["description"],
            severity=bank["severity"],
            resource=resource,
            status=status,
        ))

    report_data = _build_report_data(raw, services=services, user_request=user_request)
    rag = rag_override if rag_override is not None else _make_rag(
        [s for s in services if s in _CAPABILITY_BANK]
    )

    primary = services[0] if not is_multi else None
    expected: Dict[str, Any] = {
        "scope": _expected_scope_for(services, is_multi=is_multi),
        "forbidden_terms": forbidden_terms if forbidden_terms is not None else (
            [] if is_multi else _OFF_SCOPE_TERMS.get(primary, [])
        ),
        "required_capabilities": required_capabilities if required_capabilities is not None else [
            _CAPABILITY_BANK[s]["capability_name"] for s in services if s in _CAPABILITY_BANK
        ],
        "allowed_numbers_snapshot": _allowed_numbers(report_data),
    }
    if needs_ranking_gt:
        expected["severity_ranking_gt"] = _ranking_gt(raw)

    return {
        "case_id": case_id,
        "group": group,
        "source": "synthetic",
        "input": {"report_data": report_data, "rag_snapshot": rag},
        "expected": expected,
    }


def _c1_single_ec2_dominant() -> Dict[str, Any]:
    specs = [
        ("ec2", 0, "FAIL"),
        ("ec2", 1, "FAIL"),
        ("ec2", 2, "FAIL"),
        ("ec2", 3, "FAIL"),
        ("ec2", 0, "FAIL"),
        ("ec2", 1, "FAIL"),
        ("ec2", 2, "FAIL"),
        ("ec2", 3, "PASS"),
    ]
    return _make_case_from_checks(
        "c1_single_ec2_dominant", "C1_scope_detection",
        services=["ec2"], check_specs=specs,
        user_request="Harden EC2 workloads and security groups.",
    )


def _c1_four_service_wide() -> Dict[str, Any]:
    specs = [
        ("s3", 0, "FAIL"), ("s3", 1, "FAIL"),
        ("iam", 0, "FAIL"), ("iam", 1, "FAIL"),
        ("ec2", 0, "FAIL"), ("ec2", 1, "FAIL"),
        ("rds", 0, "FAIL"), ("rds", 1, "FAIL"),
    ]
    return _make_case_from_checks(
        "c1_four_service_wide", "C1_scope_detection",
        services=["s3", "iam", "ec2", "rds"], check_specs=specs,
        user_request="Wide baseline sweep across the AWS estate.",
        is_multi=True,
    )


def _c2_minimal_1_finding() -> Dict[str, Any]:
    specs = [("iam", 0, "FAIL")]
    return _make_case_from_checks(
        "c2_minimal_1_finding", "C2_hallucination_stress",
        services=["iam"], check_specs=specs,
        user_request="Root MFA spot-check.",
    )


def _c2_sparse_rag_low_confidence() -> Dict[str, Any]:
    specs = [
        ("s3", 0, "FAIL"),
        ("s3", 1, "FAIL"),
        ("s3", 2, "FAIL"),
    ]
    # RAG is thin: confidence=low, capability_details empty, practices generic.
    thin_rag = {
        "primary_topics": ["Data Storage Protection"],
        "control_themes": [],
        "capability_details": [],
        "recommended_practices": ["Follow baseline guardrails."],
        "key_findings": [],
        "confidence": "low",
    }
    return _make_case_from_checks(
        "c2_sparse_rag_low_confidence", "C2_hallucination_stress",
        services=["s3"], check_specs=specs,
        user_request="S3 review with limited RAG context.",
        rag_override=thin_rag,
        required_capabilities=[],  # Sparse RAG → we don't require capability mention.
    )


def _c2_numbers_trap() -> Dict[str, Any]:
    specs = [
        ("ec2", 0, "FAIL"), ("ec2", 1, "FAIL"),
        ("ec2", 2, "FAIL"), ("ec2", 3, "FAIL"),
        ("ec2", 0, "PASS"), ("ec2", 1, "PASS"),
        ("ec2", 2, "PASS"),
    ]
    return _make_case_from_checks(
        "c2_numbers_trap", "C2_hallucination_stress",
        services=["ec2"], check_specs=specs,
        user_request="EC2 hardening — pre/post stats are close.",
    )


def _c2_capability_absent_in_rag() -> Dict[str, Any]:
    specs = [
        ("rds", 0, "FAIL"),
        ("rds", 1, "FAIL"),
    ]
    # RAG discusses a capability that does not match the service in scope.
    misplaced_rag = _make_rag(["s3"])
    return _make_case_from_checks(
        "c2_capability_absent_in_rag", "C2_hallucination_stress",
        services=["rds"], check_specs=specs,
        user_request="RDS review with mismatched RAG context.",
        rag_override=misplaced_rag,
        required_capabilities=[],
    )


def _c3_one_critical_dominant() -> Dict[str, Any]:
    specs = [
        ("iam", 0, "FAIL"),  # Critical
        ("iam", 2, "PASS"),  # Medium
        ("iam", 3, "PASS"),  # Medium
        ("iam", 1, "PASS"),  # High
        ("iam", 2, "PASS"),  # Medium
        ("iam", 3, "PASS"),  # Medium
    ]
    return _make_case_from_checks(
        "c3_one_critical_dominant", "C3_prioritization",
        services=["iam"], check_specs=specs,
        user_request="IAM review — 1 Critical must lead narrative.",
        needs_ranking_gt=True,
    )


def _c3_inverted_description_trap() -> Dict[str, Any]:
    # Critical has short description, Low has long verbose one.
    raw = [
        _make_raw_finding(
            1, "ec2", "ec2_sg_open_ssh",
            "Open SSH.",  # terse
            "Critical", "sg-0abc1234",
        ),
        _make_raw_finding(
            2, "ec2", "ec2_instance_public_ip",
            "EC2 instance has a public IPv4 address attached via ENI which "
            "increases attack surface and may allow direct lateral movement "
            "from the internet given mis-scoped security groups.",
            "Low", "i-0123456789abcdef0",
        ),
        _make_raw_finding(
            3, "ec2", "ec2_ebs_encryption",
            "EBS unencrypted.",
            "High", "vol-0def5678",
        ),
        _make_raw_finding(
            4, "ec2", "ec2_imdsv2_enforced",
            "IMDSv2 not enforced (legacy instance launched before the hardening "
            "baseline was rolled out, currently owned by an archived team).",
            "Medium", "i-0fedcba987654321",
        ),
    ]
    report_data = _build_report_data(
        raw, services=["ec2"],
        user_request="EC2 review — do not be misled by description length.",
    )
    rag = _make_rag(["ec2"])
    return {
        "case_id": "c3_inverted_description_trap",
        "group": "C3_prioritization",
        "source": "synthetic",
        "input": {"report_data": report_data, "rag_snapshot": rag},
        "expected": {
            "scope": _expected_scope_for(["ec2"]),
            "forbidden_terms": _OFF_SCOPE_TERMS["ec2"],
            "required_capabilities": [_CAPABILITY_BANK["ec2"]["capability_name"]],
            "allowed_numbers_snapshot": _allowed_numbers(report_data),
            "severity_ranking_gt": _ranking_gt(raw),
        },
    }


def _c4_missing_optional_fields() -> Dict[str, Any]:
    specs = [
        ("s3", 0, "FAIL"),
        ("s3", 1, "FAIL"),
        ("s3", 2, "PASS"),
    ]
    case = _make_case_from_checks(
        "c4_missing_optional_fields", "C4_structural_robustness",
        services=["s3"], check_specs=specs,
        user_request="S3 review with sparse RAG fields.",
    )
    # Strip recommendation / risk_explanation from each capability_detail.
    cap_details = case["input"]["rag_snapshot"]["capability_details"]
    for cd in cap_details:
        cd.pop("recommendation", None)
        cd.pop("risk_explanation", None)
    return case


def _c4_mixed_case_status() -> Dict[str, Any]:
    raw = [
        _make_raw_finding(
            1, "s3", "s3_bucket_public_access",
            "S3 bucket has public read access", "Critical",
            "arn:aws:s3:::public-a", status="FAIL",
        ),
        _make_raw_finding(
            2, "s3", "s3_bucket_versioning",
            "S3 bucket versioning is disabled", "High",
            "arn:aws:s3:::logs-a", status="fail",  # lowercase
        ),
        _make_raw_finding(
            3, "s3", "s3_bucket_encryption",
            "S3 bucket default encryption is off", "Medium",
            "arn:aws:s3:::media-a", status="Fail",  # mixed
        ),
        _make_raw_finding(
            4, "s3", "s3_bucket_logging",
            "S3 bucket access logging is not enabled", "Low",
            "arn:aws:s3:::reports-a", status="pass",
        ),
    ]
    report_data = _build_report_data(
        raw, services=["s3"],
        user_request="S3 review with inconsistent status casing.",
    )
    rag = _make_rag(["s3"])
    return {
        "case_id": "c4_mixed_case_status",
        "group": "C4_structural_robustness",
        "source": "synthetic",
        "input": {"report_data": report_data, "rag_snapshot": rag},
        "expected": {
            "scope": _expected_scope_for(["s3"]),
            "forbidden_terms": _OFF_SCOPE_TERMS["s3"],
            "required_capabilities": [_CAPABILITY_BANK["s3"]["capability_name"]],
            "allowed_numbers_snapshot": _allowed_numbers(report_data),
        },
    }


def _c4_unicode_escape_chars() -> Dict[str, Any]:
    raw = [
        _make_raw_finding(
            1, "iam", "iam_user_mfa_enabled",
            "Người dùng IAM \"nguyễn.alice\" chưa bật MFA — cần xử lý.",
            "High", "arn:aws:iam::123456789012:user/nguyen.alice",
            status="FAIL",
        ),
        _make_raw_finding(
            2, "iam", "iam_password_policy_strong",
            "Chính sách mật khẩu \"yếu\" (<12 ký tự): rủi ro đăng nhập trái phép.",
            "Medium", "123456789012", status="FAIL",
        ),
    ]
    report_data = _build_report_data(
        raw, services=["iam"],
        user_request="IAM review — Vietnamese diacritics and quote escapes.",
    )
    rag = _make_rag(["iam"])
    return {
        "case_id": "c4_unicode_escape_chars",
        "group": "C4_structural_robustness",
        "source": "synthetic",
        "input": {"report_data": report_data, "rag_snapshot": rag},
        "expected": {
            "scope": _expected_scope_for(["iam"]),
            "forbidden_terms": _OFF_SCOPE_TERMS["iam"],
            "required_capabilities": [_CAPABILITY_BANK["iam"]["capability_name"]],
            "allowed_numbers_snapshot": _allowed_numbers(report_data),
        },
    }


def _c4_post_remediation_delta() -> Dict[str, Any]:
    specs = [
        ("ec2", 0, "FAIL"), ("ec2", 1, "FAIL"),
        ("ec2", 2, "FAIL"), ("ec2", 3, "FAIL"),
        ("ec2", 0, "PASS"),
    ]
    return _make_case_from_checks(
        "c4_post_remediation_delta", "C4_structural_robustness",
        services=["ec2"], check_specs=specs,
        user_request="EC2 pre+post baseline with remediation delta.",
    )


def _c5_rich_rag_full_capdetails() -> Dict[str, Any]:
    specs = [
        ("s3", 0, "FAIL"),
        ("s3", 1, "FAIL"),
        ("s3", 2, "PASS"),
    ]
    # Richer capability_details: add guidance_questions.
    cap = {
        **_CAPABILITY_BANK["s3"],
        "guidance_questions": [
            "Is server-side encryption (SSE-KMS) enabled on every bucket?",
            "Is the Block Public Access setting enforced at the account level?",
        ],
    }
    rich_rag = {
        "primary_topics": ["Data Storage Protection"],
        "control_themes": [
            {
                "capability_id": cap["capability_id"],
                "capability_name": cap["capability_name"],
                "summary_short": cap["summary"],
            }
        ],
        "capability_details": [cap],
        "recommended_practices": [
            "Enable SSE-KMS on every S3 bucket.",
            "Enforce the Block Public Access setting at the account level.",
            "Enable S3 access logging and retain for 90 days.",
        ],
        "key_findings": [],
        "confidence": "high",
    }
    return _make_case_from_checks(
        "c5_rich_rag_full_capdetails", "C5_rag_grounding",
        services=["s3"], check_specs=specs,
        user_request="S3 review with rich RAG context.",
        rag_override=rich_rag,
    )


def _c5_sparse_rag_low_conf() -> Dict[str, Any]:
    specs = [
        ("iam", 0, "FAIL"),
        ("iam", 1, "FAIL"),
    ]
    thin_rag = _make_empty_rag()
    return _make_case_from_checks(
        "c5_sparse_rag_low_conf", "C5_rag_grounding",
        services=["iam"], check_specs=specs,
        user_request="IAM review with empty RAG bundle.",
        rag_override=thin_rag,
        required_capabilities=[],
    )


def _c5_conflicting_rag() -> Dict[str, Any]:
    specs = [
        ("iam", 0, "FAIL"),
        ("iam", 1, "FAIL"),
        ("iam", 2, "FAIL"),
    ]
    # RAG claims data storage and database capabilities — does not match IAM.
    bad_rag = _make_rag(["s3", "rds"])
    return _make_case_from_checks(
        "c5_conflicting_rag", "C5_rag_grounding",
        services=["iam"], check_specs=specs,
        user_request="IAM review — RAG context is mismatched.",
        rag_override=bad_rag,
        required_capabilities=[],
    )


def _c5_rag_noise_injection() -> Dict[str, Any]:
    specs = [
        ("s3", 0, "FAIL"),
        ("s3", 1, "FAIL"),
        ("s3", 2, "FAIL"),
    ]
    noise = [
        {
            "capability_id": "noise-lambda",
            "capability_name": "Serverless Function Governance",
            "summary": "Off-topic capability for adversarial injection.",
            "risk_explanation": "Not relevant to this scope.",
            "recommendation": "N/A.",
            "guidance_questions": [],
        },
        {
            "capability_id": "noise-route53",
            "capability_name": "DNS Zone Hardening",
            "summary": "Off-topic capability for adversarial injection.",
            "risk_explanation": "Not relevant to this scope.",
            "recommendation": "N/A.",
            "guidance_questions": [],
        },
        {
            "capability_id": "noise-appsync",
            "capability_name": "GraphQL Gateway Policies",
            "summary": "Off-topic capability for adversarial injection.",
            "risk_explanation": "Not relevant to this scope.",
            "recommendation": "N/A.",
            "guidance_questions": [],
        },
    ]
    rag = _make_rag(["s3"], noise_capabilities=noise)
    return _make_case_from_checks(
        "c5_rag_noise_injection", "C5_rag_grounding",
        services=["s3"], check_specs=specs,
        user_request="S3 review — RAG contains off-topic noise capabilities.",
        rag_override=rag,
        forbidden_terms=_OFF_SCOPE_TERMS["s3"] + [
            "serverless function", "dns zone", "graphql",
        ],
    )


def _c5_rag_empty_fallback() -> Dict[str, Any]:
    specs = [
        ("ec2", 0, "FAIL"),
        ("ec2", 1, "FAIL"),
    ]
    return _make_case_from_checks(
        "c5_rag_empty_fallback", "C5_rag_grounding",
        services=["ec2"], check_specs=specs,
        user_request="EC2 review — fully empty RAG bundle.",
        rag_override=_make_empty_rag(),
        required_capabilities=[],
    )


# --------------------------------------------------------------------------
# Round 2 — 6 additional cases (total 30, parity with Planning/Risk agents)
# --------------------------------------------------------------------------

def _c2_large_pre_all_pass() -> Dict[str, Any]:
    """10 findings, every one PASS. Stress "fill narrative" at larger scale
    than c2_all_pass_zero_fail (6 findings). Tests hallucination pressure
    when nothing to remediate and input is uniformly positive."""
    specs = [
        ("s3", i % 4, "PASS") for i in range(10)
    ]
    return _make_case_from_checks(
        "c2_large_pre_all_pass", "C2_hallucination_stress",
        services=["s3"], check_specs=specs,
        user_request="S3 review — large clean environment (10 PASS, 0 FAIL).",
    )


def _c2_contradictory_rag() -> Dict[str, Any]:
    """RAG claims the capability is already well-enforced, findings show
    violations. Tests whether the agent echoes the RAG evidence (wrong)
    or stays grounded in the actual scan data (right)."""
    specs = [
        ("iam", 0, "FAIL"),  # Root MFA disabled — Critical
        ("iam", 1, "FAIL"),  # User MFA disabled — High
        ("iam", 2, "FAIL"),  # Weak password policy — Medium
    ]
    misleading_rag = {
        "primary_topics": ["Identity And Access Management"],
        "control_themes": [
            {
                "capability_id": "identity-mgmt",
                "capability_name": "Identity And Access Management",
                "summary_short": (
                    "Identity controls are fully enforced across the account "
                    "with MFA active on all principals."
                ),
            }
        ],
        "capability_details": [
            {
                "capability_id": "identity-mgmt",
                "capability_name": "Identity And Access Management",
                "summary": (
                    "MFA is enforced on all IAM users and the root account. "
                    "Password policy meets industry strength requirements."
                ),
                "risk_explanation": "Residual risk is minimal given current enforcement.",
                "recommendation": "Maintain current posture and monitor for drift.",
                "guidance_questions": [],
            }
        ],
        "recommended_practices": [
            "Continue enforcing MFA on all principals.",
            "Review IAM posture quarterly.",
        ],
        "key_findings": [],
        "confidence": "high",
    }
    return _make_case_from_checks(
        "c2_contradictory_rag", "C2_hallucination_stress",
        services=["iam"], check_specs=specs,
        user_request="IAM review — findings contradict RAG posture claim.",
        rag_override=misleading_rag,
    )


def _c3_all_critical_same_sev() -> Dict[str, Any]:
    """6 findings, all Critical. Tests NDCG tie-breaking when ground-truth
    severity has no gradient — relevance is uniform so ranking order
    within the tier must fall back to input order cleanly."""
    raw = [
        _make_raw_finding(
            i + 1, "s3", "s3_bucket_public_access",
            f"S3 bucket {i+1} has public read access exposing sensitive data",
            "Critical",
            f"arn:aws:s3:::critical-bucket-{i+1}",
            status="FAIL",
        )
        for i in range(6)
    ]
    report_data = _build_report_data(
        raw, services=["s3"],
        user_request="S3 review — multiple concurrent Critical findings.",
    )
    rag = _make_rag(["s3"])
    return {
        "case_id": "c3_all_critical_same_sev",
        "group": "C3_prioritization",
        "source": "synthetic",
        "input": {"report_data": report_data, "rag_snapshot": rag},
        "expected": {
            "scope": _expected_scope_for(["s3"]),
            "forbidden_terms": _OFF_SCOPE_TERMS["s3"],
            "required_capabilities": [_CAPABILITY_BANK["s3"]["capability_name"]],
            "allowed_numbers_snapshot": _allowed_numbers(report_data),
            "severity_ranking_gt": _ranking_gt(raw),
        },
    }


def _c3_reversed_order_input() -> Dict[str, Any]:
    """Findings input in ascending severity (Low → Medium → High → Critical).
    Tests whether narrative re-orders by severity (correct) or preserves
    the misleading input order."""
    raw = [
        _make_raw_finding(
            1, "ec2", "ec2_instance_public_ip",
            "EC2 instance has a public IPv4 address",
            "Low", "i-0a11", status="PASS",
        ),
        _make_raw_finding(
            2, "ec2", "ec2_imdsv2_enforced",
            "IMDSv2 is not enforced on EC2 instance",
            "Medium", "i-0b22", status="FAIL",
        ),
        _make_raw_finding(
            3, "ec2", "ec2_ebs_encryption",
            "EBS volume is not encrypted",
            "High", "vol-0c33", status="FAIL",
        ),
        _make_raw_finding(
            4, "ec2", "ec2_sg_open_ssh",
            "Security group allows SSH from 0.0.0.0/0",
            "Critical", "sg-0d44", status="FAIL",
        ),
    ]
    report_data = _build_report_data(
        raw, services=["ec2"],
        user_request="EC2 review — input ordered low-to-high severity.",
    )
    rag = _make_rag(["ec2"])
    return {
        "case_id": "c3_reversed_order_input",
        "group": "C3_prioritization",
        "source": "synthetic",
        "input": {"report_data": report_data, "rag_snapshot": rag},
        "expected": {
            "scope": _expected_scope_for(["ec2"]),
            "forbidden_terms": _OFF_SCOPE_TERMS["ec2"],
            "required_capabilities": [_CAPABILITY_BANK["ec2"]["capability_name"]],
            "allowed_numbers_snapshot": _allowed_numbers(report_data),
            "severity_ranking_gt": _ranking_gt(raw),
        },
    }


def _c5_partial_capability_overlap() -> Dict[str, Any]:
    """Two capabilities in the bundle, each partially overlapping the
    scope (S3). Tests how the agent disambiguates when multiple RAG
    entries are candidate grounds for the same claim."""
    specs = [
        ("s3", 0, "FAIL"),
        ("s3", 2, "FAIL"),
    ]
    overlap_rag = {
        "primary_topics": [
            "Data Storage Protection",
            "Data Protection At Rest",
        ],
        "control_themes": [
            {
                "capability_id": "data-storage",
                "capability_name": "Data Storage Protection",
                "summary_short": "Protect data at rest in object storage.",
            },
            {
                "capability_id": "data-at-rest",
                "capability_name": "Data Protection At Rest",
                "summary_short": "Encryption and key management for stored data.",
            },
        ],
        "capability_details": [
            {
                "capability_id": "data-storage",
                "capability_name": "Data Storage Protection",
                "summary": "Block Public Access and bucket policies on S3.",
                "risk_explanation": "Public buckets leak data.",
                "recommendation": "Enforce Block Public Access at the account level.",
                "guidance_questions": [],
            },
            {
                "capability_id": "data-at-rest",
                "capability_name": "Data Protection At Rest",
                "summary": "SSE-KMS encryption for buckets and volumes.",
                "risk_explanation": "Unencrypted storage exposes data if disks leak.",
                "recommendation": "Enable SSE-KMS and rotate keys quarterly.",
                "guidance_questions": [],
            },
        ],
        "recommended_practices": [
            "Enforce Block Public Access at the account level.",
            "Enable SSE-KMS on every S3 bucket.",
        ],
        "key_findings": [],
        "confidence": "high",
    }
    return _make_case_from_checks(
        "c5_partial_capability_overlap", "C5_rag_grounding",
        services=["s3"], check_specs=specs,
        user_request="S3 review — two overlapping RAG capabilities.",
        rag_override=overlap_rag,
        required_capabilities=[
            "Data Storage Protection",
            "Data Protection At Rest",
        ],
    )


def _c5_rag_rich_guidance() -> Dict[str, Any]:
    """RAG bundle with populated ``guidance_questions``. Most other cases
    leave this field empty; this one tests whether the agent incorporates
    guidance questions into the narrative (should improve claim grounding
    and actionability)."""
    specs = [
        ("iam", 0, "FAIL"),
        ("iam", 1, "FAIL"),
        ("iam", 2, "FAIL"),
    ]
    guidance_rag = {
        "primary_topics": ["Identity And Access Management"],
        "control_themes": [
            {
                "capability_id": "identity-mgmt",
                "capability_name": "Identity And Access Management",
                "summary_short": "IAM baseline controls.",
            }
        ],
        "capability_details": [
            {
                "capability_id": "identity-mgmt",
                "capability_name": "Identity And Access Management",
                "summary": "IAM controls cover MFA, password policy, and key rotation.",
                "risk_explanation": (
                    "Weak IAM posture enables account takeover and lateral "
                    "movement across the account."
                ),
                "recommendation": (
                    "Enforce MFA on root and all IAM users, apply strong "
                    "password policy, rotate access keys every 90 days."
                ),
                "guidance_questions": [
                    "Is MFA enforced on the root account and all IAM users?",
                    "Does the account password policy require 14+ characters with complexity?",
                    "Are access keys rotated at least every 90 days?",
                    "Are service accounts using IAM roles rather than static keys?",
                ],
            }
        ],
        "recommended_practices": [
            "Enforce MFA on the root account (hardware token preferred).",
            "Apply password policy: 14+ chars, symbol + digit + mixed case.",
            "Rotate IAM access keys every 90 days via an automated job.",
            "Prefer IAM roles over static access keys for service principals.",
        ],
        "key_findings": [],
        "confidence": "high",
    }
    return _make_case_from_checks(
        "c5_rag_rich_guidance", "C5_rag_grounding",
        services=["iam"], check_specs=specs,
        user_request="IAM review — bundle carries rich guidance questions.",
        rag_override=guidance_rag,
    )


# --------------------------------------------------------------------------
# Assemble all cases
# --------------------------------------------------------------------------

def build_all_cases() -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []

    # 7 ported baselines.
    for letter in ["A", "B", "C", "D", "E", "F", "G"]:
        cases.append(port_baseline(letter))

    # 23 synthesized cases (17 round-1 + 6 round-2). Final distribution:
    #   C1: 5  (C, F, G from baselines + 2 synth)
    #   C2: 7  (A baseline + 4 round-1 + 2 round-2)
    #   C3: 6  (B, E baselines + 2 round-1 + 2 round-2)
    #   C4: 5  (D baseline + 4 round-1)
    #   C5: 7  (5 round-1 + 2 round-2)
    cases.extend([
        # C1 (2 synth — 5 total)
        _c1_single_ec2_dominant(),
        _c1_four_service_wide(),
        # C2 round-1 (4 synth)
        _c2_minimal_1_finding(),
        _c2_sparse_rag_low_confidence(),
        _c2_numbers_trap(),
        _c2_capability_absent_in_rag(),
        # C3 round-1 (2 synth)
        _c3_one_critical_dominant(),
        _c3_inverted_description_trap(),
        # C4 (4 synth)
        _c4_missing_optional_fields(),
        _c4_mixed_case_status(),
        _c4_unicode_escape_chars(),
        _c4_post_remediation_delta(),
        # C5 round-1 (5 synth)
        _c5_rich_rag_full_capdetails(),
        _c5_sparse_rag_low_conf(),
        _c5_conflicting_rag(),
        _c5_rag_noise_injection(),
        _c5_rag_empty_fallback(),
        # Round-2 additions (6 cases — reach parity with Planning/Risk at 30)
        _c2_large_pre_all_pass(),
        _c2_contradictory_rag(),
        _c3_all_critical_same_sev(),
        _c3_reversed_order_input(),
        _c5_partial_capability_overlap(),
        _c5_rag_rich_guidance(),
    ])

    return cases


def main() -> None:
    cases = build_all_cases()

    # Sanity: unique case_ids.
    ids = [c["case_id"] for c in cases]
    if len(set(ids)) != len(ids):
        dupes = [i for i in ids if ids.count(i) > 1]
        raise SystemExit(f"Duplicate case_ids: {sorted(set(dupes))}")

    groups: Dict[str, int] = {}
    for c in cases:
        groups[c["group"]] = groups.get(c["group"], 0) + 1

    payload = {
        "schema_version": 3,
        "generated_for": "Report Agent Evaluation v3",
        "total_cases": len(cases),
        "group_counts": groups,
        "cases": cases,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {len(cases)} cases -> {OUT_PATH}")
    for g, n in sorted(groups.items()):
        print(f"  {g}: {n}")


if __name__ == "__main__":
    main()
