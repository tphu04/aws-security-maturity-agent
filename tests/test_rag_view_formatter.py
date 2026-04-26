"""Unit tests for ``RAGViewFormatter`` (Phase 4.1).

The formatter is pure: given a ``rag_context`` dict it returns strings
for specific LLM prompts. These tests lock in the contract documented in
``rag_formatter.py`` — severity ordering, bracket format, empty-input
handling, and per-view field selection.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdca.agents.report_module.rag_formatter import RAGViewFormatter


def _ctx():
    """A realistic rag_context with all known keys populated."""
    return {
        "primary_topics": ["s3", "iam"],
        "key_findings": [
            {
                "check_id": "s3_bucket_public_access",
                "title": "S3 bucket publicly accessible",
                "severity": "critical",
                "risk_summary": "Public S3 buckets expose data to the internet.",
                "remediation": "Enable Block Public Access at bucket level.",
            },
            {
                "check_id": "iam_user_mfa_enabled",
                "title": "IAM user without MFA",
                "severity": "high",
                "risk_summary": "Root-like access without a second factor.",
                "remediation": "Require MFA for every IAM user.",
            },
            {
                "check_id": "s3_bucket_versioning",
                "title": "Bucket versioning disabled",
                "severity": "medium",
                "risk_summary": "Accidental deletion cannot be recovered.",
                "remediation": "Turn on versioning.",
            },
            {
                "check_id": "s3_bucket_logging",
                "title": "Access logging disabled",
                "severity": "low",
                "risk_summary": "Audit trail missing.",
                "remediation": "Enable S3 server access logging.",
            },
        ],
        "control_themes": [
            {
                "capability_id": "data-protection",
                "capability_name": "Data protection at rest",
                "summary_short": "Enforce encryption and lifecycle controls.",
            },
            {
                "capability_id": "identity-access",
                "capability_name": "Identity and access management",
                "summary_short": "Least-privilege IAM with MFA.",
            },
        ],
        "recommended_practices": [
            "Enable S3 Block Public Access at account level.",
            "Apply bucket policies that deny unencrypted uploads.",
            "Require MFA on every IAM principal.",
        ],
        "capability_details": [
            {
                "capability_id": "data-protection",
                "capability_name": "Data protection at rest",
                "summary": "Protect data stored in S3 and block exposure.",
                "risk_explanation": (
                    "Unencrypted or public buckets leak data; without "
                    "versioning, ransomware-driven deletes are unrecoverable."
                ),
                "recommendation": (
                    "Enable default encryption, block public access "
                    "account-wide, and turn on versioning for critical data."
                ),
                "guidance_questions": [
                    "Is Block Public Access enforced at account level?",
                    "Is default encryption mandatory on every bucket?",
                ],
                "url": "https://example/data-protection",
            },
            {
                "capability_id": "identity-access",
                "capability_name": "Identity and access management",
                "summary": "Control who can act on AWS resources.",
                "risk_explanation": "Weak IAM exposes resources to lateral movement.",
                "recommendation": "Enforce MFA and short-lived credentials.",
                "guidance_questions": [],
            },
        ],
        "confidence": "high",
    }


# ----------------------------------------------------------------------
# Empty-input handling
# ----------------------------------------------------------------------
class TestEmpty:
    @pytest.mark.parametrize("ctx", [None, {}])
    def test_all_views_empty_when_no_context(self, ctx):
        f = RAGViewFormatter(ctx)
        assert f.has_data is False
        assert f.for_executive() == ""
        assert f.for_fail_analysis() == ""
        assert f.for_pass_analysis() == ""
        assert f.for_recommendations() == ""
        assert f.for_per_finding("any") == {
            "risk": "", "recommendation": "", "title": ""
        }


# ----------------------------------------------------------------------
# Executive view: top critical/high + short themes
# ----------------------------------------------------------------------
class TestExecutive:
    def test_includes_only_critical_and_high(self):
        out = RAGViewFormatter(_ctx()).for_executive()
        # critical + high should be listed
        assert "S3 bucket publicly accessible" in out
        assert "IAM user without MFA" in out
        # medium + low should NOT appear in the executive summary view
        assert "Bucket versioning disabled" not in out
        assert "Access logging disabled" not in out

    def test_uses_parens_not_brackets_for_severity(self):
        out = RAGViewFormatter(_ctx()).for_executive()
        # No [CRITICAL] / [HIGH] — these get stripped by _PLACEHOLDER.
        assert "[CRITICAL]" not in out
        assert "[HIGH]" not in out
        assert "(CRITICAL)" in out
        assert "(HIGH)" in out

    def test_limits_findings_and_themes(self):
        ctx = _ctx()
        # Flood with criticals to confirm max_findings cap.
        ctx["key_findings"] = [
            {"check_id": f"c{i}", "title": f"T{i}", "severity": "critical",
             "risk_summary": "r"} for i in range(10)
        ]
        out = RAGViewFormatter(ctx).for_executive(max_findings=3)
        # Only 3 findings rendered.
        assert out.count("(CRITICAL)") == 3


# ----------------------------------------------------------------------
# Fail-analysis view: full findings + capability risk explanation
# ----------------------------------------------------------------------
class TestFailAnalysis:
    def test_sorted_critical_first(self):
        out = RAGViewFormatter(_ctx()).for_fail_analysis()
        crit = out.find("(CRITICAL)")
        high = out.find("(HIGH)")
        med = out.find("(MEDIUM)")
        assert 0 <= crit < high < med, out

    def test_includes_capability_risk_block(self):
        out = RAGViewFormatter(_ctx()).for_fail_analysis()
        assert "NĂNG LỰC KIỂM SOÁT CÓ RỦI RO" in out
        assert "Data protection at rest" in out
        # Risk explanation text is present (not just capability name).
        assert "ransomware" in out.lower() or "leak" in out.lower()


# ----------------------------------------------------------------------
# Pass-analysis view: themes only, no findings
# ----------------------------------------------------------------------
class TestPassAnalysis:
    def test_shows_themes_without_findings(self):
        out = RAGViewFormatter(_ctx()).for_pass_analysis()
        assert "Data protection at rest" in out
        assert "Identity and access management" in out
        # Finding titles must not leak into the pass view.
        assert "publicly accessible" not in out
        assert "without MFA" not in out

    def test_empty_when_no_themes(self):
        ctx = _ctx()
        ctx["control_themes"] = []
        assert RAGViewFormatter(ctx).for_pass_analysis() == ""


# ----------------------------------------------------------------------
# Recommendations view: practices + capability.recommendation
# ----------------------------------------------------------------------
class TestRecommendations:
    def test_includes_practices_and_capability_recs(self):
        out = RAGViewFormatter(_ctx()).for_recommendations()
        assert "Block Public Access" in out
        assert "Require MFA" in out or "MFA" in out
        # Capability-level recommendation surfaces.
        assert "Enable default encryption" in out

    def test_no_rationale_or_cli_leak(self):
        """Recommended practices must not contain stringified dicts /
        raw CLI code blocks. This catches regressions where a fallback
        slips ``{'CLI': ...}`` or raw shell text into the view.
        """
        out = RAGViewFormatter(_ctx()).for_recommendations()
        assert "'CLI':" not in out
        assert "Shared concepts:" not in out


# ----------------------------------------------------------------------
# Per-finding view: selector by check_id
# ----------------------------------------------------------------------
class TestPerFinding:
    def test_returns_matching_finding(self):
        out = RAGViewFormatter(_ctx()).for_per_finding(
            "s3_bucket_public_access"
        )
        assert "public" in out["risk"].lower()
        assert "Block Public Access" in out["recommendation"]
        assert "publicly accessible" in out["title"]

    def test_returns_empty_for_unknown_check(self):
        out = RAGViewFormatter(_ctx()).for_per_finding("missing_check_id")
        assert out == {"risk": "", "recommendation": "", "title": ""}

    def test_returns_empty_for_none_check(self):
        out = RAGViewFormatter(_ctx()).for_per_finding("")
        assert out == {"risk": "", "recommendation": "", "title": ""}


# ----------------------------------------------------------------------
# Multi-query mode: Q2 capability_themes in for_pass_analysis
# ----------------------------------------------------------------------

def _ctx_with_q2():
    ctx = _ctx()
    ctx["capability_themes"] = [
        {
            "domain": "s3",
            "narrative": "S3 data protection requires block public access and encryption.",
            "common_pitfalls": ["Missing bucket-level public access block", "No default encryption"],
            "baselines": ["CIS AWS 2.1.5", "Well-Architected Security Pillar"],
        },
        {
            "domain": "iam",
            "narrative": "IAM least privilege must be enforced across all users and roles.",
            "common_pitfalls": ["Root account usage"],
            "baselines": ["CIS IAM 1.4"],
        },
    ]
    return ctx


class TestForPassAnalysisQ2:
    def test_q2_narrative_appears_when_present(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_pass_analysis()
        assert "S3 data protection" in out
        assert "IAM least privilege" in out

    def test_q2_domain_label_appears(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_pass_analysis()
        assert "[S3]" in out or "s3" in out.lower()

    def test_q2_pitfalls_appended(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_pass_analysis()
        assert "public access block" in out.lower() or "lưu ý" in out

    def test_legacy_control_themes_still_present(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_pass_analysis()
        # Q1 control_themes should still appear
        assert "CHỦ ĐỀ KIỂM SOÁT" in out or "Block Public Access" in out

    def test_empty_q2_falls_back_to_q1_only(self):
        ctx = _ctx()
        ctx["capability_themes"] = []
        out = RAGViewFormatter(ctx).for_pass_analysis()
        assert "CHỦ ĐỀ KIỂM SOÁT" in out


# ----------------------------------------------------------------------
# Multi-query mode: Q3 remediations in for_recommendations
# ----------------------------------------------------------------------

def _ctx_with_q3():
    ctx = _ctx()
    ctx["remediations"] = [
        {
            "check_id": "s3_bucket_level_public_access_block",
            "steps": [
                {"order": 1, "type": "cli", "snippet": "aws s3api put-public-access-block --bucket BUCKET --public-access-block-configuration BlockPublicAcls=true"},
                {"order": 2, "type": "iac", "snippet": "Resource: AWS::S3::BucketPublicAccessBlock"},
            ],
            "effort": "low",
        }
    ]
    ctx["capability_themes"] = [
        {
            "domain": "s3",
            "narrative": "Block public access at account level.",
            "baselines": ["CIS AWS 2.1.5", "Well-Architected"],
            "common_pitfalls": [],
        }
    ]
    return ctx


class TestForRecommendationsQ3:
    def test_q3_cli_snippet_appears(self):
        out = RAGViewFormatter(_ctx_with_q3()).for_recommendations()
        assert "aws s3api" in out

    def test_q3_step_type_labeled(self):
        out = RAGViewFormatter(_ctx_with_q3()).for_recommendations()
        assert "[CLI]" in out

    def test_q3_effort_referenced(self):
        out = RAGViewFormatter(_ctx_with_q3()).for_recommendations()
        assert "low" in out or "effort" in out

    def test_q2_baselines_appear(self):
        out = RAGViewFormatter(_ctx_with_q3()).for_recommendations()
        assert "CIS AWS 2.1.5" in out

    def test_q1_practices_still_present(self):
        out = RAGViewFormatter(_ctx_with_q3()).for_recommendations()
        assert "THỰC HÀNH KHUYẾN NGHỊ" in out

    def test_no_cli_dict_blob_leaks(self):
        out = RAGViewFormatter(_ctx_with_q3()).for_recommendations()
        assert "'CLI':" not in out

    def test_empty_q3_falls_back_to_q1_only(self):
        ctx = _ctx()
        ctx["remediations"] = []
        out = RAGViewFormatter(ctx).for_recommendations()
        assert "THỰC HÀNH KHUYẾN NGHỊ" in out


# ----------------------------------------------------------------------
# T2-A: for_fail_analysis() — Q3 remediation steps + Q2 domain pitfalls
# ----------------------------------------------------------------------

def _ctx_with_fail_q3q2():
    """rag_context with key_findings, remediations (Q3), capability_themes (Q2)."""
    ctx = _ctx()
    ctx["remediations"] = [
        {
            "check_id": "s3_bucket_public_access",
            "steps": [
                {
                    "order": 1,
                    "type": "cli",
                    "snippet": "aws s3api put-public-access-block --bucket BUCKET --public-access-block-configuration BlockPublicAcls=true",
                },
                {"order": 2, "type": "iac", "snippet": "Resource: AWS::S3::BucketPublicAccessBlock"},
            ],
            "effort": "low",
        },
        {
            "check_id": "iam_user_mfa_enabled",
            "steps": [
                {"order": 1, "type": "console", "snippet": "IAM → Users → select user → Security credentials → Assign MFA device"},
            ],
            "effort": "low",
        },
    ]
    ctx["capability_themes"] = [
        {
            "domain": "s3",
            "narrative": "S3 data protection requires block public access.",
            "common_pitfalls": ["Missing bucket-level public access block", "No default encryption"],
            "baselines": ["CIS AWS 2.1.5"],
        },
        {
            "domain": "iam",
            "narrative": "IAM least privilege must be enforced.",
            "common_pitfalls": ["Root account usage without MFA"],
            "baselines": ["CIS IAM 1.4"],
        },
    ]
    return ctx


class TestForFailAnalysisQ3Q2:
    def test_q3_cli_snippet_appears(self):
        out = RAGViewFormatter(_ctx_with_fail_q3q2()).for_fail_analysis()
        assert "aws s3api put-public-access-block" in out

    def test_q3_step_type_labeled(self):
        out = RAGViewFormatter(_ctx_with_fail_q3q2()).for_fail_analysis()
        assert "[CLI]" in out

    def test_q3_section_heading(self):
        out = RAGViewFormatter(_ctx_with_fail_q3q2()).for_fail_analysis()
        assert "BƯỚC KHẮC PHỤC TRỌNG TÂM" in out

    def test_q3_matched_by_check_id(self):
        out = RAGViewFormatter(_ctx_with_fail_q3q2()).for_fail_analysis()
        assert "s3_bucket_public_access" in out

    def test_q2_pitfalls_for_failing_domain(self):
        out = RAGViewFormatter(_ctx_with_fail_q3q2()).for_fail_analysis()
        assert "Missing bucket-level public access block" in out or "public access" in out.lower()

    def test_q2_domain_label(self):
        out = RAGViewFormatter(_ctx_with_fail_q3q2()).for_fail_analysis()
        assert "[S3]" in out or "[IAM]" in out

    def test_q2_section_heading(self):
        out = RAGViewFormatter(_ctx_with_fail_q3q2()).for_fail_analysis()
        assert "SAI LẦM PHỔ BIẾN" in out

    def test_q1_findings_still_present(self):
        out = RAGViewFormatter(_ctx_with_fail_q3q2()).for_fail_analysis()
        assert "RỦI RO CHI TIẾT" in out
        assert "S3 bucket publicly accessible" in out

    def test_legacy_no_q3_no_q2_blocks(self):
        """Legacy mode: remediations=[] → no Q3/Q2 blocks, Q1 still present."""
        ctx = _ctx()
        ctx["remediations"] = []
        ctx["capability_themes"] = []
        out = RAGViewFormatter(ctx).for_fail_analysis()
        assert "BƯỚC KHẮC PHỤC TRỌNG TÂM" not in out
        assert "SAI LẦM PHỔ BIẾN" not in out
        assert "RỦI RO CHI TIẾT" in out

    def test_q3_domain_not_in_findings_skipped(self):
        """Q2 pitfall for 'ec2' domain should NOT appear when no EC2 findings."""
        ctx = _ctx_with_fail_q3q2()
        ctx["capability_themes"].append({
            "domain": "ec2",
            "common_pitfalls": ["IMDSv1 still enabled"],
            "narrative": "EC2 metadata service risks.",
            "baselines": [],
        })
        out = RAGViewFormatter(ctx).for_fail_analysis()
        assert "IMDSv1" not in out


# ----------------------------------------------------------------------
# T1-B: for_executive() — Q2 domain narratives
# ----------------------------------------------------------------------

class TestForExecutiveQ2:
    def test_q2_domain_narrative_appears(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_executive()
        assert "S3 data protection" in out

    def test_q2_domain_label(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_executive()
        assert "[S3]" in out or "[IAM]" in out

    def test_q2_section_heading(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_executive()
        assert "BỐI CẢNH BẢO MẬT THEO DOMAIN" in out

    def test_q2_max_domains_respected(self):
        ctx = _ctx_with_q2()
        ctx["capability_themes"].append(
            {"domain": "ec2", "narrative": "EC2 metadata risks.", "common_pitfalls": [], "baselines": []}
        )
        out = RAGViewFormatter(ctx).for_executive(max_domains=2)
        # Only 2 domains should appear — [S3] and [IAM], not [EC2]
        assert out.count("[EC2]") == 0

    def test_q2_pitfalls_not_in_exec(self):
        """Pitfalls are too technical — exec view should not include them."""
        out = RAGViewFormatter(_ctx_with_q2()).for_executive()
        assert "Missing bucket-level public access block" not in out

    def test_q1_findings_still_present(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_executive()
        assert "RỦI RO NGHIÊM TRỌNG" in out

    def test_q1_control_themes_still_present(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_executive()
        assert "CHỦ ĐỀ KIỂM SOÁT" in out

    def test_legacy_no_q2_block(self):
        """Legacy mode: capability_themes=[] → no Q2 block in exec view."""
        ctx = _ctx()
        ctx["capability_themes"] = []
        out = RAGViewFormatter(ctx).for_executive()
        assert "BỐI CẢNH BẢO MẬT THEO DOMAIN" not in out
        assert "RỦI RO NGHIÊM TRỌNG" in out


# ----------------------------------------------------------------------
# T2-B: for_system_overview() — Q2 domain narratives + baselines
# ----------------------------------------------------------------------

class TestForSystemOverview:
    def test_domain_narrative_appears(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_system_overview()
        assert "S3 data protection" in out

    def test_domain_label_present(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_system_overview()
        assert "[S3]" in out or "[IAM]" in out

    def test_section_heading(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_system_overview()
        assert "PHẠM VI BẢO MẬT THEO DOMAIN" in out

    def test_baselines_appear(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_system_overview()
        assert "CIS AWS 2.1.5" in out or "Well-Architected" in out

    def test_baselines_section_heading(self):
        out = RAGViewFormatter(_ctx_with_q2()).for_system_overview()
        assert "TIÊU CHUẨN ĐÁNH GIÁ" in out

    def test_max_domains_respected(self):
        ctx = _ctx_with_q2()
        ctx["capability_themes"].append(
            {"domain": "ec2", "narrative": "EC2 instance risks.", "baselines": ["CIS EC2 3.1"], "common_pitfalls": []}
        )
        out = RAGViewFormatter(ctx).for_system_overview(max_domains=2)
        assert "[EC2]" not in out

    def test_pitfalls_not_in_system_overview(self):
        """Pitfalls are fail-specific — system overview should not include them."""
        out = RAGViewFormatter(_ctx_with_q2()).for_system_overview()
        assert "Missing bucket-level public access block" not in out

    def test_baselines_deduplicated(self):
        ctx = _ctx_with_q2()
        # Add duplicate baseline across two domains
        ctx["capability_themes"][0]["baselines"] = ["CIS AWS 2.1.5", "Well-Architected"]
        ctx["capability_themes"][1]["baselines"] = ["CIS AWS 2.1.5", "CIS IAM 1.4"]
        out = RAGViewFormatter(ctx).for_system_overview()
        assert out.count("CIS AWS 2.1.5") == 1

    def test_legacy_no_capability_themes_returns_empty(self):
        """Legacy mode: no capability_themes → returns '' (no crash)."""
        ctx = _ctx()
        ctx["capability_themes"] = []
        out = RAGViewFormatter(ctx).for_system_overview()
        assert out == ""

    def test_empty_context_returns_empty(self):
        out = RAGViewFormatter({}).for_system_overview()
        assert out == ""
