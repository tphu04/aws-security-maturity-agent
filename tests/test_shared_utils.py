"""
Unit Tests cho agents/shared/utils.py
======================================
Tham chiếu: Integration_Implementation_Plan.md — SLICE-RS-1
Tối thiểu 3 test cases mỗi function (extract_check_id, parse_llm_json, sanitize_check_id).
"""

import pytest
from agents.shared.utils import extract_check_id, parse_llm_json, sanitize_check_id


# ============================================================
# extract_check_id
# ============================================================


class TestExtractCheckId:
    """Test extract_check_id — priority chain: event_code > check_id > regex fallback."""

    def test_priority1_event_code(self):
        """event_code (Normalizer output) có ưu tiên cao nhất."""
        finding = {
            "event_code": "s3_bucket_public_access",
            "check_id": "other_check",
            "finding_id": "prowler-aws-iam_something-123",
        }
        assert extract_check_id(finding) == "s3_bucket_public_access"

    def test_priority2_check_id(self):
        """Fallback sang check_id khi event_code rỗng."""
        finding = {"event_code": "", "check_id": "iam_user_mfa_enabled"}
        assert extract_check_id(finding) == "iam_user_mfa_enabled"

    def test_priority2_check_id_case_variants(self):
        """Support nhiều case variants: CheckID, checkId."""
        assert extract_check_id({"CheckID": "ec2_instance_public"}) == "ec2_instance_public"
        assert extract_check_id({"checkId": "rds_encryption"}) == "rds_encryption"

    def test_priority3_regex_prowler_format(self):
        """Regex fallback từ finding_id theo format prowler-aws-{check_id}-{digits}."""
        finding = {
            "finding_id": "prowler-aws-s3_account_level_public_access_blocks-065209282642-ap-southeast-1"
        }
        assert extract_check_id(finding) == "s3_account_level_public_access_blocks"

    def test_priority3_regex_underscore_fallback(self):
        """Regex fallback cho finding_id không theo format prowler chuẩn."""
        finding = {"finding_id": "some-custom-s3_bucket_versioning"}
        assert extract_check_id(finding) == "s3_bucket_versioning"

    def test_empty_finding(self):
        """Return None cho finding rỗng."""
        assert extract_check_id({}) is None

    def test_invalid_input(self):
        """Return None cho input không phải dict."""
        assert extract_check_id(None) is None
        assert extract_check_id("not a dict") is None
        assert extract_check_id(42) is None

    def test_whitespace_event_code(self):
        """event_code chỉ có whitespace => skip, dùng fallback."""
        finding = {"event_code": "   ", "check_id": "vpc_flow_logs"}
        assert extract_check_id(finding) == "vpc_flow_logs"


# ============================================================
# parse_llm_json
# ============================================================


class TestParseLlmJson:
    """Test parse_llm_json — robust JSON extraction từ LLM output."""

    def test_clean_json(self):
        """Parse clean JSON string."""
        text = '{"target_service": "s3", "is_group_scan": true}'
        result = parse_llm_json(text)
        assert result["target_service"] == "s3"
        assert result["is_group_scan"] is True

    def test_json_in_markdown_block(self):
        """Parse JSON từ ```json ... ``` block."""
        text = 'Here is the result:\n```json\n{"severity": "High", "score": 8}\n```\nDone.'
        result = parse_llm_json(text)
        assert result["severity"] == "High"
        assert result["score"] == 8

    def test_json_with_surrounding_text(self):
        """Parse JSON khi LLM thêm text xung quanh."""
        text = 'Sure! Here is the analysis:\n{"selected_ids": ["s3_check1", "s3_check2"]}\nHope this helps!'
        result = parse_llm_json(text)
        assert result["selected_ids"] == ["s3_check1", "s3_check2"]

    def test_json_with_control_characters(self):
        """Parse JSON chứa control characters (LLM sometimes outputs these)."""
        text = '{"key": "value\x00with\x1Fcontrol"}'
        result = parse_llm_json(text)
        assert result.get("key") is not None

    def test_empty_input(self):
        """Return {} cho input rỗng."""
        assert parse_llm_json("") == {}
        assert parse_llm_json(None) == {}

    def test_invalid_json(self):
        """Return {} cho text không chứa JSON hợp lệ."""
        assert parse_llm_json("This is not JSON at all") == {}
        assert parse_llm_json("{ broken json: }}}") == {}

    def test_nested_json(self):
        """Parse nested JSON structures."""
        text = '{"outer": {"inner": [1, 2, 3]}, "flag": false}'
        result = parse_llm_json(text)
        assert result["outer"]["inner"] == [1, 2, 3]
        assert result["flag"] is False


# ============================================================
# sanitize_check_id
# ============================================================


class TestSanitizeCheckId:
    """Test sanitize_check_id — remove prefix/suffix rác."""

    def test_remove_check_prefix(self):
        """Remove prefix 'check:'."""
        assert sanitize_check_id("check:s3_bucket_public_access") == "s3_bucket_public_access"

    def test_remove_capability_prefix(self):
        """Remove prefix 'capability:'."""
        assert sanitize_check_id("capability:block_public_access") == "block_public_access"

    def test_remove_overview_suffix(self):
        """Remove suffix '_overview'."""
        assert sanitize_check_id("s3_bucket_encryption_overview") == "s3_bucket_encryption"

    def test_remove_risk_suffix(self):
        """Remove suffix '_risk'."""
        assert sanitize_check_id("iam_user_mfa_risk") == "iam_user_mfa"

    def test_remove_recommendation_suffix(self):
        """Remove suffix '_recommendation'."""
        assert sanitize_check_id("ec2_instance_public_recommendation") == "ec2_instance_public"

    def test_remove_remediation_suffix(self):
        """Remove suffix '_remediation'."""
        assert sanitize_check_id("rds_encryption_remediation") == "rds_encryption"

    def test_remove_prefix_and_suffix(self):
        """Remove both prefix and suffix."""
        assert sanitize_check_id("check:s3_bucket_access_overview") == "s3_bucket_access"

    def test_clean_id_unchanged(self):
        """ID không có prefix/suffix thì giữ nguyên."""
        assert sanitize_check_id("s3_bucket_public_access") == "s3_bucket_public_access"

    def test_empty_input(self):
        """Return empty string cho input rỗng."""
        assert sanitize_check_id("") == ""
        assert sanitize_check_id(None) == ""

    def test_whitespace_handling(self):
        """Strip whitespace."""
        assert sanitize_check_id("  check:s3_test  ") == "s3_test"
