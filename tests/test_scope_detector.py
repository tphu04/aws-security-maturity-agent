"""
Unit tests for scope_detector (Phase 1 — De-S3-bias).

Covers:
- S3-only findings → Amazon S3 + bucket terminology
- IAM-only findings → AWS IAM + IAM-entity terminology
- EC2-only findings → Amazon EC2 + instance terminology
- Multi-service with dominant one (>70%) → dominant wins
- Multi-service evenly spread → generic AWS Infrastructure fallback
- Empty findings → empty scope
- Services hint from assessment plan takes precedence
- Single-service hint forces dominance even when finding prefixes disagree
- Unknown service → falls back to "AWS {SERVICE}" + generic terms
- Service inferred from check_id when 'service' field missing
- is_valid_resource() drops account-id / numeric strings
"""
import os
import sys

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdca.agents.report_module.scope_detector import (
    GENERIC_FALLBACK,
    RESOURCE_TERMS,
    SERVICE_DISPLAY,
    detect_scope,
    is_valid_resource,
)


def _make_finding(service=None, check_id=None):
    f = {}
    if service is not None:
        f["service"] = service
    if check_id is not None:
        f["check_id"] = check_id
    return f


# ------------------------------------------------------------------
# detect_scope — single-service cases
# ------------------------------------------------------------------
def test_s3_only_findings_report_amazon_s3_and_bucket_terms():
    findings = [_make_finding(service="s3") for _ in range(5)]
    scope = detect_scope(findings)

    assert scope["primary_service"] == "s3"
    assert scope["service_display"] == "Amazon S3"
    assert scope["resource_term"] == "bucket"
    assert scope["resource_term_plural"] == "buckets"
    assert scope["is_multi_service"] is False
    assert scope["service_list"] == ["s3"]
    assert scope["source"] == "findings"


def test_iam_only_findings_report_aws_iam():
    findings = [_make_finding(service="iam") for _ in range(3)]
    scope = detect_scope(findings)

    assert scope["primary_service"] == "iam"
    assert scope["service_display"] == "AWS IAM"
    assert scope["resource_term"] == RESOURCE_TERMS["iam"][0]
    assert scope["resource_term_plural"] == RESOURCE_TERMS["iam"][1]
    assert scope["is_multi_service"] is False


def test_ec2_only_findings_report_amazon_ec2_instance():
    findings = [_make_finding(service="ec2") for _ in range(4)]
    scope = detect_scope(findings)

    assert scope["primary_service"] == "ec2"
    assert scope["service_display"] == "Amazon EC2"
    assert scope["resource_term"] == "instance"
    assert scope["resource_term_plural"] == "instances"


# ------------------------------------------------------------------
# detect_scope — multi-service cases
# ------------------------------------------------------------------
def test_multi_service_with_dominant_service_wins():
    # 8 s3 + 1 iam + 1 ec2 → s3 dominates (80% > 70% threshold)
    findings = (
        [_make_finding(service="s3")] * 8
        + [_make_finding(service="iam")]
        + [_make_finding(service="ec2")]
    )
    scope = detect_scope(findings)

    assert scope["primary_service"] == "s3"
    assert scope["service_display"] == "Amazon S3"
    assert scope["is_multi_service"] is True
    assert set(scope["service_list"]) == {"s3", "iam", "ec2"}
    assert scope["dominance_ratio"] > 0.7


def test_multi_service_evenly_spread_uses_generic_fallback():
    # 3 s3 + 3 iam + 3 ec2 — no single service dominates.
    findings = (
        [_make_finding(service="s3")] * 3
        + [_make_finding(service="iam")] * 3
        + [_make_finding(service="ec2")] * 3
    )
    scope = detect_scope(findings)

    assert scope["primary_service"] is None
    assert scope["is_multi_service"] is True
    assert scope["service_display"] == GENERIC_FALLBACK["display"]
    assert scope["resource_term"] == GENERIC_FALLBACK["term_singular"]
    assert scope["resource_term_plural"] == GENERIC_FALLBACK["term_plural"]
    assert set(scope["service_list"]) == {"s3", "iam", "ec2"}


# ------------------------------------------------------------------
# detect_scope — edge cases
# ------------------------------------------------------------------
def test_empty_findings_returns_empty_scope():
    scope = detect_scope([])

    assert scope["primary_service"] is None
    assert scope["is_multi_service"] is False
    assert scope["service_list"] == []
    assert scope["service_display"] == GENERIC_FALLBACK["display"]
    assert scope["source"] == "empty"


def test_none_findings_returns_empty_scope():
    scope = detect_scope(None)
    assert scope["primary_service"] is None
    assert scope["source"] == "empty"


def test_service_hint_single_service_is_authoritative():
    # Even if findings leak other service prefixes, a single-service
    # assessment plan should win.
    findings = [
        _make_finding(check_id="s3_bucket_public_access"),
        _make_finding(check_id="iam_user_mfa_disabled"),  # leaked
    ]
    scope = detect_scope(findings, services_hint=["s3"])

    assert scope["primary_service"] == "s3"
    assert scope["is_multi_service"] is False
    assert scope["source"] == "hint"
    assert scope["dominance_ratio"] == 1.0


def test_multi_service_hint_respects_finding_dominance():
    # Hint says s3+iam are in scope; findings show 9 s3 + 1 iam → s3 dominates.
    findings = (
        [_make_finding(service="s3")] * 9
        + [_make_finding(service="iam")]
    )
    scope = detect_scope(findings, services_hint=["s3", "iam"])

    assert scope["is_multi_service"] is True
    assert scope["primary_service"] == "s3"
    assert set(scope["service_list"]) == {"s3", "iam"}


def test_unknown_service_falls_back_to_aws_prefix():
    findings = [_make_finding(service="neptune") for _ in range(3)]
    scope = detect_scope(findings)

    assert scope["primary_service"] == "neptune"
    # "neptune" is not in SERVICE_DISPLAY → generic "AWS NEPTUNE" label
    assert scope["service_display"] == "AWS NEPTUNE"
    # Not in RESOURCE_TERMS → generic fallback singular/plural
    assert scope["resource_term"] == GENERIC_FALLBACK["term_singular"]
    assert scope["resource_term_plural"] == GENERIC_FALLBACK["term_plural"]


def test_service_inferred_from_check_id_when_service_field_missing():
    findings = [
        _make_finding(check_id="s3_bucket_public_access"),
        _make_finding(check_id="s3_bucket_versioning"),
    ]
    scope = detect_scope(findings)

    assert scope["primary_service"] == "s3"
    assert scope["service_display"] == "Amazon S3"


def test_findings_without_service_or_check_id_are_ignored():
    findings = [
        {"foo": "bar"},  # no service field, no check_id
        _make_finding(service="s3"),
    ]
    scope = detect_scope(findings)

    # Only the s3 finding contributes.
    assert scope["primary_service"] == "s3"
    assert scope["service_list"] == ["s3"]


def test_service_dictionary_is_case_insensitive():
    findings = [_make_finding(service="S3"), _make_finding(service="s3")]
    scope = detect_scope(findings)
    assert scope["primary_service"] == "s3"


# ------------------------------------------------------------------
# is_valid_resource — drops account id / numeric / too-short strings
# ------------------------------------------------------------------
def test_is_valid_resource_rejects_account_id():
    assert is_valid_resource("123456789012", service="s3",
                             account_id="123456789012") is False


def test_is_valid_resource_rejects_pure_digits():
    # Pure digit string looks like an account id regardless.
    assert is_valid_resource("999888777666", service="s3") is False


def test_is_valid_resource_rejects_short_strings_and_none():
    assert is_valid_resource(None, service="s3") is False
    assert is_valid_resource("", service="s3") is False
    assert is_valid_resource("ab", service="s3") is False


def test_is_valid_resource_accepts_s3_bucket_name():
    assert is_valid_resource("prod-data-lake", service="s3") is True


def test_is_valid_resource_rejects_s3_arn_prefix():
    # Bucket names never start with "arn:" — legitimate S3 resources are bare names.
    assert is_valid_resource("arn:aws:s3:::foo", service="s3") is False


def test_is_valid_resource_accepts_iam_arn():
    assert is_valid_resource(
        "arn:aws:iam::123456789012:user/alice", service="iam"
    ) is True


def test_is_valid_resource_accepts_ec2_instance_id():
    assert is_valid_resource("i-0abcd1234", service="ec2") is True


def test_service_display_dict_has_expected_core_services():
    """Guard against accidental deletion of core service entries."""
    for svc in ("s3", "iam", "ec2", "rds", "lambda", "cloudtrail"):
        assert svc in SERVICE_DISPLAY
        assert svc in RESOURCE_TERMS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
