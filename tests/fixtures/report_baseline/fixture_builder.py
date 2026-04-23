"""Deterministic fixture builders for the 7 Phase-6 baseline scenarios.

Keeping the builders in Python (instead of hand-rolled JSON) lets the
tests assert structural invariants and lets the capture script reproduce
the inputs from source. Each ``build_<letter>()`` returns the ``data``
dict consumed by :meth:`ReportAgent.run`.

Scenarios:
    A  S3-only, all findings PASS                      (edge: bypass LLM)
    B  S3-only, all findings FAIL                      (stress)
    C  S3-only, mixed pass/fail                        (canonical)
    D  S3 zero findings                                (edge)
    E  S3 multi-bucket, high density                   (stress)
    F  IAM-only, mixed                                 (de-S3 check)
    G  Multi-service S3 + IAM + EC2, no dominant svc   (generic fallback)
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

ACCOUNT = "123456789012"
REGION = "us-east-1"
SCAN_DATE = "2026-04-20"


# ---------------------------------------------------------------------
# Low-level builders
# ---------------------------------------------------------------------
def _finding(idx: int, service: str, check_id: str, resource: str,
             severity: str, status: str, description: str) -> Dict[str, Any]:
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


def _severity_counter(raw: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in raw:
        sev = (f.get("severity") or "").lower()
        if sev in counts:
            counts[sev] += 1
    return counts


def _table_row(idx: int, f: Dict[str, Any], change: str) -> Dict[str, Any]:
    return {
        "stt": idx,
        "finding": f["description"],
        "service": f["service"],
        "resource": f["resource_id"],
        "severity": f["severity"],
        "before": f["status"],
        "after": "PASS" if change == "Fixed" else f["status"],
        "change": change,
    }


def _rag_context(capability_name: str, capability_id: str,
                  service: str) -> Dict[str, Any]:
    """Minimal but well-formed RAG context so the validator populates
    its ``allowed_capabilities`` set. Without this, the ungrounded-
    capability check degrades gracefully but we want to exercise it."""
    return {
        "primary_topics": [capability_name],
        "control_themes": [{
            "capability_id": capability_id,
            "capability_name": capability_name,
            "summary_short": f"{capability_name} controls for {service.upper()}.",
        }],
        "capability_details": [{
            "capability_id": capability_id,
            "capability_name": capability_name,
            "summary": f"{capability_name} enforces baseline guardrails.",
            "risk_explanation": "Misconfiguration exposes data or access.",
            "recommendation": "Apply the documented remediation.",
            "guidance_questions": [],
        }],
        "recommended_practices": [
            f"Apply the {capability_name} baseline on every resource.",
            "Log and monitor configuration drift.",
        ],
        "key_findings": [],
        "confidence": "medium",
    }


def _pre_post(raw: List[Dict[str, Any]],
              fixed_check_ids: Optional[Iterable[str]] = None,
              manual_check_ids: Optional[Iterable[str]] = None
              ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    fixed_ids = set(fixed_check_ids or ())
    manual_ids = set(manual_check_ids or ())
    passes = [f for f in raw if f["status"] == "PASS"]
    fails = [f for f in raw if f["status"] == "FAIL"]
    fixed_count = sum(1 for f in fails if f["check_id"] in fixed_ids)
    manual_count = sum(1 for f in fails if f["check_id"] in manual_ids)
    failed_count = max(0, len(fails) - fixed_count - manual_count)
    initial_pass = len(passes)
    initial_fail = len(fails)
    final_pass = initial_pass + fixed_count
    final_fail = initial_fail - fixed_count
    pre = {
        "total": len(raw),
        "pass": initial_pass,
        "fail": initial_fail,
        "severity": _severity_counter(fails),
    }
    post = {
        "initial_pass": initial_pass,
        "initial_fail": initial_fail,
        "final_pass": final_pass,
        "final_fail": final_fail,
        "fixed": fixed_count,
        "failed": failed_count,
        "manual": manual_count,
    }
    return pre, post


def _assemble(raw: List[Dict[str, Any]], services: List[str],
              user_request: str,
              fixed_check_ids: Optional[Iterable[str]] = None,
              manual_check_ids: Optional[Iterable[str]] = None,
              environment_extra: Optional[Dict[str, Any]] = None,
              rag_context: Optional[Dict[str, Any]] = None
              ) -> Dict[str, Any]:
    fixed_ids = set(fixed_check_ids or ())
    manual_ids = set(manual_check_ids or ())
    pre, post = _pre_post(raw, fixed_ids, manual_ids)
    findings_table = []
    for idx, f in enumerate(raw, 1):
        if f["status"] == "PASS":
            change = "Unchanged"
        elif f["check_id"] in fixed_ids:
            change = "Fixed"
        elif f["check_id"] in manual_ids:
            change = "Still Failing (ManualRequired)"
        else:
            change = "Still Failing"
        findings_table.append(_table_row(idx, f, change))
    env = {"account_id": ACCOUNT, "region": REGION, "buckets": []}
    if environment_extra:
        env.update(environment_extra)
    data: Dict[str, Any] = {
        "pre": pre,
        "post": post,
        "environment": env,
        "scope": {
            "services": services,
            "date": SCAN_DATE,
            "user_request": user_request,
        },
        "findings_table": findings_table,
        "success_findings": [],
        "failed_findings": [],
        "manual_findings": [],
        "raw_pre_findings": raw,
    }
    if rag_context is not None:
        data["rag_context"] = rag_context
    return data


# ---------------------------------------------------------------------
# Scenario builders
# ---------------------------------------------------------------------
def build_A() -> Dict[str, Any]:
    """S3-only, all PASS — exercises bypass path in _write_llm_sections."""
    buckets = ["prod-data-lake", "logs-archive", "public-assets",
               "analytics-warehouse", "ml-models", "ops-backup"]
    raw = [
        _finding(i + 1, "s3", "s3_bucket_default_encryption", b,
                 "Low", "PASS",
                 f"Bucket {b} has default encryption enabled")
        for i, b in enumerate(buckets)
    ]
    data = _assemble(
        raw, services=["s3"],
        user_request="Verify that every S3 bucket has baseline encryption.",
        environment_extra={"buckets": buckets},
        rag_context=_rag_context("Data Protection", "data-protection", "s3"),
    )
    return data


def build_B() -> Dict[str, Any]:
    """S3-only, all FAIL — stress the fail-overview + recommendation paths."""
    entries = [
        ("prod-data-lake", "s3_bucket_public_access", "Critical",
         "Bucket prod-data-lake has public ACL grants"),
        ("logs-archive", "s3_bucket_default_encryption", "High",
         "Bucket logs-archive missing default encryption"),
        ("backup-prod", "s3_bucket_object_versioning", "High",
         "Bucket backup-prod has versioning disabled"),
        ("public-assets", "s3_bucket_secure_transport", "Medium",
         "Bucket public-assets allows plain HTTP access"),
        ("analytics-warehouse", "s3_bucket_policy_public_write", "Critical",
         "Bucket analytics-warehouse policy allows public write"),
        ("ops-backup", "s3_bucket_logging_enabled", "Low",
         "Bucket ops-backup has server access logging disabled"),
    ]
    raw = [
        _finding(i + 1, "s3", check_id, bucket, sev, "FAIL", desc)
        for i, (bucket, check_id, sev, desc) in enumerate(entries)
    ]
    fixed = {"s3_bucket_default_encryption", "s3_bucket_object_versioning",
             "s3_bucket_secure_transport"}
    manual = {"s3_bucket_policy_public_write"}
    data = _assemble(
        raw, services=["s3"],
        user_request="Remediate every critical and high S3 misconfiguration.",
        fixed_check_ids=fixed, manual_check_ids=manual,
        environment_extra={"buckets": sorted({e[0] for e in entries})},
        rag_context=_rag_context("Data Protection", "data-protection", "s3"),
    )
    return data


def build_C() -> Dict[str, Any]:
    """S3-only, mixed pass/fail — canonical scenario."""
    entries = [
        ("prod-data-lake", "s3_bucket_default_encryption", "High", "FAIL",
         "Bucket prod-data-lake missing default encryption"),
        ("prod-data-lake", "s3_bucket_object_versioning", "Medium", "PASS",
         "Bucket prod-data-lake has versioning enabled"),
        ("logs-archive", "s3_bucket_public_access", "Critical", "FAIL",
         "Bucket logs-archive allows public read"),
        ("logs-archive", "s3_bucket_secure_transport", "Medium", "PASS",
         "Bucket logs-archive enforces TLS"),
        ("public-assets", "s3_bucket_logging_enabled", "Low", "FAIL",
         "Bucket public-assets has access logging off"),
        ("public-assets", "s3_bucket_default_encryption", "High", "PASS",
         "Bucket public-assets has default encryption"),
    ]
    raw = [
        _finding(i + 1, "s3", check_id, bucket, sev, status, desc)
        for i, (bucket, check_id, sev, status, desc) in enumerate(entries)
    ]
    fixed = {"s3_bucket_default_encryption", "s3_bucket_logging_enabled"}
    manual = {"s3_bucket_public_access"}
    data = _assemble(
        raw, services=["s3"],
        user_request="Audit S3 encryption, versioning and public exposure.",
        fixed_check_ids=fixed, manual_check_ids=manual,
        environment_extra={"buckets": ["prod-data-lake", "logs-archive",
                                        "public-assets"]},
        rag_context=_rag_context("Data Protection", "data-protection", "s3"),
    )
    return data


def build_D() -> Dict[str, Any]:
    """S3 zero findings — pathological empty scan."""
    raw: List[Dict[str, Any]] = []
    data = _assemble(
        raw, services=["s3"],
        user_request="Scan S3 posture for the empty account.",
        environment_extra={"buckets": []},
        rag_context=_rag_context("Data Protection", "data-protection", "s3"),
    )
    # Zero-finding scenario — report agent handles this via early bypass.
    return data


def build_E() -> Dict[str, Any]:
    """S3 multi-bucket intensive — 12 findings across 4 buckets."""
    buckets = ["prod-data-lake", "logs-archive", "public-assets", "ops-backup"]
    check_matrix = [
        ("s3_bucket_default_encryption", "High"),
        ("s3_bucket_object_versioning", "Medium"),
        ("s3_bucket_secure_transport", "Medium"),
    ]
    raw: List[Dict[str, Any]] = []
    idx = 0
    for bucket in buckets:
        for check_id, sev in check_matrix:
            idx += 1
            status = "FAIL" if (idx % 3) else "PASS"
            raw.append(_finding(
                idx, "s3", check_id, bucket, sev, status,
                f"{check_id} for bucket {bucket}",
            ))
    fixed = {"s3_bucket_default_encryption"}
    manual = {"s3_bucket_secure_transport"}
    data = _assemble(
        raw, services=["s3"],
        user_request="Intensive sweep of every S3 bucket across the account.",
        fixed_check_ids=fixed, manual_check_ids=manual,
        environment_extra={"buckets": buckets},
        rag_context=_rag_context("Data Protection", "data-protection", "s3"),
    )
    return data


def build_F() -> Dict[str, Any]:
    """IAM-only, mixed — tests de-S3 generalization."""
    entries = [
        ("arn:aws:iam::123456789012:user/alice",
         "iam_user_mfa_enabled", "High", "FAIL",
         "IAM user alice does not have MFA enabled"),
        ("arn:aws:iam::123456789012:user/bob",
         "iam_user_mfa_enabled", "High", "FAIL",
         "IAM user bob does not have MFA enabled"),
        ("arn:aws:iam::123456789012:user/carol",
         "iam_user_mfa_enabled", "Low", "PASS",
         "IAM user carol has MFA enabled"),
        ("123456789012",
         "iam_root_mfa_enabled", "Critical", "FAIL",
         "Root account MFA is disabled"),
        ("123456789012",
         "iam_password_policy_strong", "Medium", "FAIL",
         "Password policy does not meet strength requirements"),
        ("123456789012",
         "iam_password_policy_min_length", "Low", "PASS",
         "Password policy meets minimum length"),
    ]
    raw = [
        _finding(i + 1, "iam", check_id, resource, sev, status, desc)
        for i, (resource, check_id, sev, status, desc) in enumerate(entries)
    ]
    fixed = {"iam_user_mfa_enabled", "iam_password_policy_strong"}
    manual = {"iam_root_mfa_enabled"}
    data = _assemble(
        raw, services=["iam"],
        user_request="Review IAM MFA, password policy and root protection.",
        fixed_check_ids=fixed, manual_check_ids=manual,
        rag_context=_rag_context("Identity And Access Management",
                                  "identity-mgmt", "iam"),
    )
    return data


def build_G() -> Dict[str, Any]:
    """Multi-service (S3 + IAM + EC2) — tests generic-fallback terminology."""
    entries = [
        ("s3", "prod-data-lake", "s3_bucket_default_encryption",
         "High", "FAIL",
         "Bucket prod-data-lake missing default encryption"),
        ("s3", "prod-data-lake", "s3_bucket_object_versioning",
         "Medium", "PASS",
         "Bucket prod-data-lake has versioning enabled"),
        ("s3", "logs-archive", "s3_bucket_secure_transport",
         "Medium", "FAIL",
         "Bucket logs-archive allows HTTP access"),
        ("iam", "arn:aws:iam::123456789012:user/alice",
         "iam_user_mfa_enabled", "High", "FAIL",
         "IAM user alice does not have MFA enabled"),
        ("iam", "arn:aws:iam::123456789012:role/admin",
         "iam_role_inline_policy", "Medium", "FAIL",
         "IAM role admin has inline policy attached"),
        ("iam", "arn:aws:iam::123456789012:user/carol",
         "iam_user_mfa_enabled", "Low", "PASS",
         "IAM user carol has MFA enabled"),
        ("ec2", "i-0abc1", "ec2_instance_imdsv2_required",
         "High", "FAIL",
         "EC2 instance i-0abc1 still allows IMDSv1"),
        ("ec2", "i-0abc2", "ec2_instance_public_ip",
         "Medium", "FAIL",
         "EC2 instance i-0abc2 has a public IP"),
        ("ec2", "i-0abc3", "ec2_instance_imdsv2_required",
         "Low", "PASS",
         "EC2 instance i-0abc3 enforces IMDSv2"),
    ]
    raw = [
        _finding(i + 1, svc, check_id, res, sev, status, desc)
        for i, (svc, res, check_id, sev, status, desc) in enumerate(entries)
    ]
    fixed = {"s3_bucket_default_encryption", "iam_user_mfa_enabled",
             "ec2_instance_imdsv2_required"}
    manual = {"ec2_instance_public_ip"}
    data = _assemble(
        raw, services=["s3", "iam", "ec2"],
        user_request="Multi-service baseline review: S3, IAM, EC2.",
        fixed_check_ids=fixed, manual_check_ids=manual,
        environment_extra={"buckets": ["prod-data-lake", "logs-archive"]},
        rag_context=_rag_context("Baseline Security",
                                  "baseline-security", "multi"),
    )
    return data


ALL_BUILDERS = {
    "A": build_A,
    "B": build_B,
    "C": build_C,
    "D": build_D,
    "E": build_E,
    "F": build_F,
    "G": build_G,
}


def build_all() -> Dict[str, Dict[str, Any]]:
    return {letter: builder() for letter, builder in ALL_BUILDERS.items()}
