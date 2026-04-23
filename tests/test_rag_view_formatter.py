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
