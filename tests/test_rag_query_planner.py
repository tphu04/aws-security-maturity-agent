"""Unit tests for RAGQueryPlanner — Phase 3 MVP."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pdca.agents.report_module.rag_query_planner import RAGQueryPlanner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_FINDINGS = [
    {"event_code": "s3_bucket_level_public_access_block", "severity": "HIGH", "status": "FAIL"},
    {"event_code": "s3_account_level_public_access_blocks", "severity": "CRITICAL", "status": "FAIL"},
    {"event_code": "s3_bucket_level_public_access_block", "severity": "HIGH"},  # duplicate
    {"event_code": "iam_root_mfa_enabled", "severity": "HIGH", "status": "FAIL"},
    {"event_code": "", "severity": "LOW"},  # empty check_id — must be skipped
]


# ---------------------------------------------------------------------------
# plan()
# ---------------------------------------------------------------------------

class TestPlan:
    def _planner(self):
        return RAGQueryPlanner(MagicMock())

    def test_dedup_check_ids_order_preserving(self):
        p = self._planner()
        req = p.plan(SAMPLE_FINDINGS, ["s3", "iam"])
        ids = req["check_ids"]
        assert ids == [
            "s3_bucket_level_public_access_block",
            "s3_account_level_public_access_blocks",
            "iam_root_mfa_enabled",
        ]

    def test_empty_check_id_skipped(self):
        p = self._planner()
        req = p.plan(SAMPLE_FINDINGS, [])
        assert "" not in req["check_ids"]

    def test_severity_map_built(self):
        p = self._planner()
        req = p.plan(SAMPLE_FINDINGS, [])
        smap = req["severity_map"]
        assert smap["s3_bucket_level_public_access_block"] == "HIGH"
        assert smap["iam_root_mfa_enabled"] == "HIGH"

    def test_domains_deduped(self):
        p = self._planner()
        req = p.plan([], ["s3", "S3", "iam", "s3"])
        assert req["domains"] == ["s3", "iam"]

    def test_empty_domains_fallback_to_general(self):
        p = self._planner()
        req = p.plan([], [])
        assert req["domains"] == ["general"]

    def test_request_includes_flags(self):
        p = self._planner()
        req = p.plan(SAMPLE_FINDINGS, ["s3"])
        assert req["include_q2"] is True
        assert req["include_q3"] is True


# ---------------------------------------------------------------------------
# execute()
# ---------------------------------------------------------------------------

class TestExecute:
    def test_returns_normalized_bundle_on_success(self):
        mock_client = MagicMock()
        mock_client.build_report_context.return_value = {
            "check_findings": [{"check_id": "s3_bucket_level_public_access_block", "title": "Block Public"}],
            "control_themes": [],
            "capability_details": [],
            "recommended_practices": [],
            "primary_topics": ["s3"],
            "capability_themes": [{"domain": "s3", "narrative": "S3 security overview"}],
            "remediations": [{"check_id": "s3_bucket_level_public_access_block", "steps": []}],
            "confidence": "high",
        }
        p = RAGQueryPlanner(mock_client)
        req = p.plan(SAMPLE_FINDINGS, ["s3"])
        bundle = p.execute(req)

        assert bundle["key_findings"][0]["check_id"] == "s3_bucket_level_public_access_block"
        assert len(bundle["capability_themes"]) == 1
        assert bundle["capability_themes"][0]["domain"] == "s3"
        assert len(bundle["remediations"]) == 1
        assert bundle["confidence"] == "high"

    def test_returns_empty_on_client_failure(self):
        mock_client = MagicMock()
        mock_client.build_report_context.return_value = None
        p = RAGQueryPlanner(mock_client)
        req = p.plan(SAMPLE_FINDINGS, ["s3"])
        bundle = p.execute(req)
        assert bundle == {}

    def test_q1_fields_preserved_in_normalized_bundle(self):
        mock_client = MagicMock()
        mock_client.build_report_context.return_value = {
            "check_findings": [{"check_id": "iam_root_mfa_enabled", "title": "Root MFA"}],
            "control_themes": [{"capability_id": "root_account_protection", "capability_name": "Root Protection"}],
            "capability_details": [],
            "recommended_practices": ["Enable MFA for root"],
            "primary_topics": ["iam"],
            "capability_themes": [],
            "remediations": [],
            "confidence": "medium",
        }
        p = RAGQueryPlanner(mock_client)
        bundle = p.execute(p.plan([], ["iam"]))
        assert bundle["recommended_practices"] == ["Enable MFA for root"]
        assert bundle["control_themes"][0]["capability_id"] == "root_account_protection"


# ---------------------------------------------------------------------------
# execute_legacy()
# ---------------------------------------------------------------------------

class TestExecuteLegacy:
    def test_legacy_returns_q1_bundle(self):
        mock_client = MagicMock()
        mock_client.build_context.return_value = {
            "payload": {
                "report_bundle": {
                    "key_findings": [{"check_id": "s3_test", "title": "Test"}],
                    "control_themes": [],
                    "recommended_practices": ["Do X"],
                    "capability_details": [],
                    "primary_topics": [],
                    "confidence": "high",
                }
            }
        }
        p = RAGQueryPlanner(mock_client)
        bundle = p.execute_legacy(["s3_test"])
        assert bundle["key_findings"][0]["check_id"] == "s3_test"
        assert "capability_themes" not in bundle
        assert "remediations" not in bundle

    def test_legacy_empty_check_ids_returns_empty(self):
        mock_client = MagicMock()
        p = RAGQueryPlanner(mock_client)
        bundle = p.execute_legacy([])
        assert bundle == {}
        mock_client.build_context.assert_not_called()

    def test_legacy_returns_empty_on_none_result(self):
        mock_client = MagicMock()
        mock_client.build_context.return_value = None
        p = RAGQueryPlanner(mock_client)
        bundle = p.execute_legacy(["s3_test"])
        assert bundle == {}
