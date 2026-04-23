"""Unit tests for ReportValidator (Phase 5).

Pure-logic tests: no LLM, no RAG server, no network. The validator is
given a synthetic ``evidence`` dict and asserts on what it flags.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdca.agents.report_module.validators import (
    ReportValidator,
    ValidationIssue,
    ValidationResult,
    build_evidence,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _scope(primary="s3", services=("s3",), multi=False):
    from pdca.agents.report_module.scope_detector import (
        RESOURCE_TERMS, SERVICE_DISPLAY,
    )
    term_s, term_p = RESOURCE_TERMS.get(primary, ("resource", "resources"))
    display = (
        SERVICE_DISPLAY.get(primary, f"AWS {primary.upper()}")
        if primary else "AWS Infrastructure"
    )
    return {
        "primary_service": primary,
        "service_list": list(services),
        "is_multi_service": multi,
        "service_display": display,
        "resource_term": term_s,
        "resource_term_plural": term_p,
    }


def _evidence(
    numbers=None,
    services=("s3",),
    capabilities=None,
    account_id="123456789012",
):
    return {
        "allowed_numbers": set(numbers or []),
        "allowed_services": set(services),
        "allowed_capabilities": set(capabilities or []),
        "account_id": account_id,
    }


# ----------------------------------------------------------------------
# Empty / trivial inputs
# ----------------------------------------------------------------------
class TestEmpty:
    def test_empty_text_is_ok(self):
        v = ReportValidator(_scope(), _evidence())
        assert v.validate("", "exec").ok is True
        assert v.validate("   \n  ", "exec").ok is True

    def test_no_evidence_degrades_gracefully(self):
        # No allowed_services / allowed_capabilities → those checks skip.
        v = ReportValidator(scope=_scope(primary=None, services=()),
                            evidence={})
        # Hallucinated number check also skipped (no allowed set).
        result = v.validate("Random text mentioning IAM and S3 with 999 issues.",
                            "exec")
        assert result.ok is True


# ----------------------------------------------------------------------
# Off-scope service
# ----------------------------------------------------------------------
class TestOffScope:
    def test_flags_service_outside_scope(self):
        """IAM-only scope → S3 mention is off_scope."""
        v = ReportValidator(
            scope=_scope(primary="iam", services=("iam",)),
            evidence=_evidence(services=("iam",)),
        )
        text = "Rà soát IAM user và chính sách S3 bucket của account."
        result = v.validate(text, "exec_summary")
        assert result.ok is False
        kinds = {i.kind for i in result.issues}
        assert "off_scope" in kinds
        off_scope = [i for i in result.issues if i.kind == "off_scope"]
        assert any(i.evidence == "s3" for i in off_scope)

    def test_allows_in_scope_services(self):
        v = ReportValidator(
            scope=_scope(primary="s3", services=("s3",)),
            evidence=_evidence(services=("s3",)),
        )
        result = v.validate("Amazon S3 configuration looks good.", "exec")
        assert not any(i.kind == "off_scope" for i in result.issues)

    def test_multi_service_allows_listed(self):
        v = ReportValidator(
            scope=_scope(primary=None, services=("s3", "iam"), multi=True),
            evidence=_evidence(services=("s3", "iam")),
        )
        text = "S3 buckets và AWS IAM users đều cần kiểm tra."
        result = v.validate(text, "exec")
        off = [i for i in result.issues if i.kind == "off_scope"]
        assert off == [], f"Expected none off-scope, got: {off}"

    def test_iam_not_false_positive_inside_unrelated_word(self):
        """The substring 'iam' must not trigger off_scope when it's part
        of a random Vietnamese word. Only uppercase IAM / aws iam / iam <noun>
        patterns should fire.
        """
        v = ReportValidator(
            scope=_scope(primary="s3", services=("s3",)),
            evidence=_evidence(services=("s3",)),
        )
        # "chia sẻ" etc. — no explicit IAM mention.
        result = v.validate(
            "Đội ngũ đã kiểm tra Amazon S3 và không có vấn đề nghiêm trọng.",
            "exec",
        )
        assert not any(i.kind == "off_scope" for i in result.issues)


# ----------------------------------------------------------------------
# Hallucinated numbers
# ----------------------------------------------------------------------
class TestHallucinatedNumbers:
    def test_flags_number_not_in_allowed_set(self):
        v = ReportValidator(
            scope=_scope(),
            evidence=_evidence(numbers={19, 11, 8}),
        )
        text = "Hệ thống có 42 findings cần xử lý."  # 42 is fabricated
        result = v.validate(text, "exec")
        halluc = [i for i in result.issues if i.kind == "hallucinated_number"]
        assert any(i.evidence == "42" for i in halluc)

    def test_allows_numbers_from_allowed_set(self):
        v = ReportValidator(
            scope=_scope(),
            evidence=_evidence(numbers={19, 11, 8}),
        )
        text = "Có 19 findings, trong đó 11 FAIL và 8 PASS."
        result = v.validate(text, "exec")
        assert not any(i.kind == "hallucinated_number" for i in result.issues)

    def test_ignores_small_numbers(self):
        """Numbers below 5 are treated as quantifiers — too noisy to gate."""
        v = ReportValidator(
            scope=_scope(),
            evidence=_evidence(numbers={10}),
        )
        # "3" is below the threshold; shouldn't flag.
        result = v.validate("Phát hiện 3 vùng yếu kém.", "exec")
        assert not any(i.kind == "hallucinated_number" for i in result.issues)

    def test_percent_tolerance(self):
        v = ReportValidator(
            scope=_scope(),
            evidence=_evidence(numbers={73.7}),
        )
        # 73.7% rendered as 73% / 74%
        result = v.validate("Tỉ lệ đạt chuẩn khoảng 74%.", "exec")
        halluc = [i for i in result.issues if i.kind == "hallucinated_number"]
        assert halluc == [], halluc

    def test_account_id_not_flagged(self):
        """Account id is always present in the prose and is not a data claim."""
        v = ReportValidator(
            scope=_scope(),
            evidence=_evidence(numbers={19}, account_id="123456789012"),
        )
        result = v.validate(
            "Tài khoản 123456789012 đã hoàn tất rà soát.", "exec"
        )
        assert not any(i.kind == "hallucinated_number" for i in result.issues)


# ----------------------------------------------------------------------
# Wrong resource terminology
# ----------------------------------------------------------------------
class TestWrongTerm:
    def test_flags_bucket_in_iam_scope(self):
        v = ReportValidator(
            scope=_scope(primary="iam", services=("iam",)),
            evidence=_evidence(services=("iam",)),
        )
        result = v.validate(
            "Rà soát các bucket cấu hình trái phép.",  # wrong term for IAM
            "fail_overview",
        )
        wrong = [i for i in result.issues if i.kind == "wrong_term"]
        assert any(i.evidence == "bucket" for i in wrong)

    def test_allows_bucket_in_s3_scope(self):
        v = ReportValidator(
            scope=_scope(primary="s3", services=("s3",)),
            evidence=_evidence(services=("s3",)),
        )
        result = v.validate(
            "S3 bucket configuration needs review.", "fail_overview"
        )
        assert not any(i.kind == "wrong_term" for i in result.issues)

    def test_skip_when_no_primary_service(self):
        """Multi-service / unknown scope → no per-service term gating."""
        v = ReportValidator(
            scope=_scope(primary=None, services=("s3", "iam"), multi=True),
            evidence=_evidence(services=("s3", "iam")),
        )
        # 'bucket' appears, but no single primary service → don't flag.
        result = v.validate("Rà soát bucket và IAM role.", "exec")
        assert not any(i.kind == "wrong_term" for i in result.issues)


# ----------------------------------------------------------------------
# Ungrounded capability names
# ----------------------------------------------------------------------
class TestUngrounded:
    def test_flags_capability_not_in_evidence(self):
        v = ReportValidator(
            scope=_scope(),
            evidence=_evidence(capabilities={"Data Protection At Rest"}),
        )
        text = (
            "Khuyến nghị áp dụng Block Public Access cho toàn bộ account "
            "và kích hoạt Data Protection At Rest."
        )
        result = v.validate(text, "recommendations")
        ungrounded = [i for i in result.issues if i.kind == "ungrounded"]
        # "Block Public Access" is not in evidence → flagged.
        assert any("Block Public Access" in i.evidence for i in ungrounded)
        # "Data Protection At Rest" is in evidence → NOT flagged.
        assert not any("Data Protection" in i.evidence for i in ungrounded)

    def test_allows_capability_from_evidence(self):
        v = ReportValidator(
            scope=_scope(),
            evidence=_evidence(capabilities={
                "Block Public Access",
                "Data Protection At Rest",
            }),
        )
        text = (
            "Triển khai Block Public Access và duy trì Data Protection At Rest."
        )
        result = v.validate(text, "recommendations")
        assert not any(i.kind == "ungrounded" for i in result.issues), \
            [i.evidence for i in result.issues if i.kind == "ungrounded"]

    def test_ignores_proper_nouns_without_security_keywords(self):
        """The heuristic should skip ordinary Title-Case phrases that
        don't contain any security-domain keyword.
        """
        v = ReportValidator(
            scope=_scope(),
            evidence=_evidence(capabilities={"Block Public Access"}),
        )
        # No "Control", "Protection", "Encryption" etc. → don't flag.
        result = v.validate(
            "Dự án Golden Gate đã hoàn tất trong quý này.",
            "exec",
        )
        assert not any(i.kind == "ungrounded" for i in result.issues)

    def test_skip_when_no_evidence(self):
        v = ReportValidator(
            scope=_scope(),
            evidence=_evidence(capabilities=()),
        )
        result = v.validate(
            "Khuyến nghị áp dụng Block Public Access.", "reco",
        )
        assert not any(i.kind == "ungrounded" for i in result.issues)


# ----------------------------------------------------------------------
# build_evidence() helper
# ----------------------------------------------------------------------
class TestBuildEvidence:
    def test_collects_all_fields(self):
        ev = build_evidence(
            findings=[{"service": "s3", "status": "FAIL"}],
            pre={"total": 19, "pass": 8, "fail": 11,
                 "severity": {"critical": 2, "high": 3}},
            post={"fixed": 6, "failed": 0, "manual": 5},
            scope={"primary_service": "s3", "service_list": ["s3"]},
            env={"account_id": "123456789012", "buckets": ["a", "b", "c"]},
            rag_context={
                "control_themes": [
                    {"capability_name": "Data Protection At Rest"},
                ],
                "capability_details": [
                    {"capability_name": "Block Public Access"},
                ],
            },
        )
        assert "s3" in ev["allowed_services"]
        assert 19.0 in ev["allowed_numbers"]
        assert 3.0 in ev["allowed_numbers"]  # resource count from buckets
        assert ev["account_id"] == "123456789012"
        caps = {c.lower() for c in ev["allowed_capabilities"]}
        assert "data protection at rest" in caps
        assert "block public access" in caps

    def test_falls_back_to_findings_services_when_no_scope(self):
        ev = build_evidence(
            findings=[{"service": "s3"}, {"service": "iam"}],
            scope=None,
        )
        assert ev["allowed_services"] >= {"s3", "iam"}


# ----------------------------------------------------------------------
# Performance — Phase 5 AC: ≤ 50 ms per section
# ----------------------------------------------------------------------
class TestPerformance:
    def test_validator_under_50ms_for_realistic_section(self):
        v = ReportValidator(
            scope=_scope(primary="s3", services=("s3",)),
            evidence=_evidence(
                numbers={19, 11, 8, 2, 3, 4},
                services=("s3",),
                capabilities={
                    "Block Public Access", "Data Protection At Rest",
                    "Encryption In Transit", "Logging And Monitoring",
                },
            ),
        )
        # Roughly the length of an exec summary (~800 words).
        text = (
            "Rà soát Amazon S3 đã hoàn tất trên tài khoản 123456789012. "
            "Tổng cộng 19 findings, bao gồm 11 FAIL và 8 PASS. "
            "Block Public Access được duy trì cho 3 buckets. "
        ) * 50
        start = time.perf_counter()
        for _ in range(10):
            v.validate(text, "exec_summary")
        elapsed_ms = (time.perf_counter() - start) * 1000 / 10
        assert elapsed_ms < 50, f"Validator averaged {elapsed_ms:.1f} ms"


# ----------------------------------------------------------------------
# Summary / result bag
# ----------------------------------------------------------------------
class TestResultBag:
    def test_result_summary_groups_by_kind(self):
        v = ReportValidator(
            scope=_scope(primary="iam", services=("iam",)),
            evidence=_evidence(
                numbers={10},
                services=("iam",),
                capabilities={"Identity Management"},
            ),
        )
        # Text has: off_scope (S3), hallucinated (42), wrong_term (bucket),
        # ungrounded (Block Public Access).
        text = (
            "Có 42 S3 buckets cần áp dụng Block Public Access."
        )
        result = v.validate(text, "mixed")
        assert result.ok is False
        summary = result.summary()
        # At least the three kinds should appear; exact counts depend on
        # regex ordering but each kind must have ≥ 1.
        assert summary.get("off_scope", 0) >= 1
        assert summary.get("hallucinated_number", 0) >= 1
        assert summary.get("wrong_term", 0) >= 1
