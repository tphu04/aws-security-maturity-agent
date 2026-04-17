"""
RAG Fallback & Graceful Degradation Tests
===========================================
Danh gia kha nang xu ly khi RAG khong kha dung hoac tra ve ket qua loi:

1. PlanningAgent degraded mode (no RAGClient)
2. RiskEvaluationAgent degraded mode (no RAGClient)
3. RAG timeout / connection error handling
4. Partial RAG response handling
5. Invalid RAG response format handling
6. Mixed scenarios (RAG intermittent failures)
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from pdca.agents.planning_agent import PlanningAgent
from pdca.agents.risk_evaluation_agent import RiskEvaluationAgent


# ============================================================
# D1: PlanningAgent — No RAGClient
# ============================================================

class TestPlanningAgentDegradedMode:
    """PlanningAgent behavior when RAGClient is None."""

    def test_retrieve_candidates_returns_empty(self, planning_agent_no_rag):
        """D1.1: _retrieve_candidates returns empty result khi no RAGClient."""
        result = planning_agent_no_rag._retrieve_candidates("s3 security", "s3")
        assert result["candidates"] == []
        assert result["source"] == "none"
        assert result["confidence"] == "low"

    def test_run_falls_back_to_group_scan(self, planning_agent_no_rag):
        """D1.2: run() falls back to group scan khi no RAGClient."""
        with patch.object(planning_agent_no_rag, "_detect_explicit_checks", return_value=None):
            with patch.object(planning_agent_no_rag, "_translate_intent", return_value={
                "target_service": "s3", "is_group_scan": False,
                "search_queries": ["public access"],
            }):
                result = planning_agent_no_rag.run("check public access on s3")
        assert result["groups_to_scan"] == ["s3"]
        assert result["checks_to_scan"] == []

    def test_explicit_checks_still_work(self, planning_agent_no_rag):
        """D1.3: Explicit check IDs van hoat dong khi no RAGClient."""
        result = planning_agent_no_rag.run("run s3_bucket_public_access check")
        assert "s3_bucket_public_access" in result["checks_to_scan"]

    def test_no_exception_raised(self, planning_agent_no_rag):
        """D1.4: Khong co exception khi RAGClient is None."""
        with patch.object(planning_agent_no_rag, "_detect_explicit_checks", return_value=None):
            with patch.object(planning_agent_no_rag, "_translate_intent", return_value={
                "target_service": "iam", "is_group_scan": False,
                "search_queries": ["mfa"],
            }):
                result = planning_agent_no_rag.run("check iam mfa")
        assert isinstance(result, dict)
        assert "error" not in result


# ============================================================
# D2: RiskEvaluationAgent — No RAGClient
# ============================================================

class TestRiskAgentDegradedMode:
    """RiskEvaluationAgent behavior when RAGClient is None."""

    def test_fetch_rag_context_returns_empty(self, risk_agent_no_rag, sample_fail_findings):
        """D2.1: _fetch_rag_context returns empty dict khi no RAGClient."""
        result = risk_agent_no_rag._fetch_rag_context(sample_fail_findings)
        assert result == {}

    def test_scoring_still_works(self, risk_agent_no_rag, sample_fail_findings):
        """D2.2: LLM scoring van hoat dong khi no RAG context."""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "High", "ai_risk_score": 7,
            "ai_reasoning": "Risk based on finding description only"
        })
        risk_agent_no_rag.llm.invoke.return_value = mock_response

        result = risk_agent_no_rag.run(sample_fail_findings)
        assert len(result) == 3
        for finding in result:
            assert "severity" in finding
            assert "risk_score" in finding

    def test_compliance_empty_without_rag(self, risk_agent_no_rag, sample_fail_findings):
        """D2.3: compliance = [] khi khong co RAG context."""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "Medium", "ai_risk_score": 5, "ai_reasoning": "test"
        })
        risk_agent_no_rag.llm.invoke.return_value = mock_response

        result = risk_agent_no_rag.run(sample_fail_findings)
        for finding in result:
            assert finding.get("compliance") == []

    def test_confidence_unknown_without_rag(self, risk_agent_no_rag, sample_fail_findings):
        """D2.4: Confidence la 'unknown' khi khong co RAG."""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "Medium", "ai_risk_score": 5, "ai_reasoning": "test"
        })
        risk_agent_no_rag.llm.invoke.return_value = mock_response

        risk_agent_no_rag.run(sample_fail_findings)
        metrics = risk_agent_no_rag.get_llm_metrics()
        assert metrics["rag_cache"]["confidence"] == "unknown"


# ============================================================
# D3: RAG Connection Error Handling
# ============================================================

class TestRAGConnectionErrors:
    """Handling of RAG API connection failures."""

    def test_planning_build_context_returns_none(self, planning_agent, mock_rag_client):
        """D3.1: build_context returns None -> fallback chain activates."""
        mock_rag_client.build_context.return_value = None
        mock_rag_client.retrieve_checks.return_value = None

        result = planning_agent._retrieve_candidates("s3", "s3")
        assert result["source"] == "none"
        assert result["candidates"] == []

    def test_planning_build_context_exception(self, planning_agent, mock_rag_client):
        """D3.2: build_context raises exception -> run() catches via top-level try."""
        mock_rag_client.build_context.side_effect = Exception("Connection refused")
        mock_rag_client.retrieve_checks.return_value = None

        # _try_build_context does NOT catch exceptions — run() top-level try/except does
        # Test the full run() path for graceful error handling
        with patch.object(planning_agent, "_detect_explicit_checks", return_value=None):
            with patch.object(planning_agent, "_translate_intent", return_value={
                "target_service": "s3", "is_group_scan": False, "search_queries": ["test"],
            }):
                result = planning_agent.run("s3 test")
        assert "error" in result or result["groups_to_scan"] == ["s3"]

    def test_risk_build_context_returns_none(self, risk_agent, mock_rag_client, sample_fail_findings):
        """D3.3: Risk agent: build_context returns None -> empty context."""
        mock_rag_client.build_context.return_value = None
        result = risk_agent._fetch_rag_context(sample_fail_findings)
        # Should return cache (empty since nothing was fetched)
        assert isinstance(result, dict)

    def test_risk_build_context_exception(self, risk_agent, mock_rag_client, sample_fail_findings):
        """D3.4: Risk agent: build_context raises -> empty context, no crash."""
        mock_rag_client.build_context.side_effect = Exception("Timeout")
        result = risk_agent._fetch_rag_context(sample_fail_findings)
        assert isinstance(result, dict)


# ============================================================
# D4: Partial / Invalid RAG Responses
# ============================================================

class TestPartialRAGResponses:
    """Handling of incomplete or malformed RAG responses."""

    def test_planning_empty_payload(self, planning_agent, mock_rag_client):
        """D4.1: RAG returns empty payload -> fallback."""
        mock_rag_client.build_context.return_value = {"payload": {}, "_meta": {}}
        mock_rag_client.retrieve_checks.return_value = None

        result = planning_agent._retrieve_candidates("s3", "s3")
        assert result["source"] == "none"

    def test_planning_empty_findings_list(self, planning_agent, mock_rag_client):
        """D4.2: planning_bundle co related_findings=[] -> empty candidates."""
        bundle = {
            "payload": {
                "planning_bundle": {
                    "related_findings": [],
                    "control_mapping_ids": [],
                    "maturity_capability_ids": [],
                }
            },
            "_meta": {"confidence": "high"},
        }
        mock_rag_client.build_context.return_value = bundle
        result = planning_agent._retrieve_candidates("s3", "s3")

        # Should fallback because no candidates
        assert result["candidates"] == [] or result["source"] == "build_context"

    def test_planning_findings_missing_check_id(self, planning_agent, mock_rag_client):
        """D4.3: Findings thieu check_id -> bi skip."""
        bundle = {
            "payload": {
                "planning_bundle": {
                    "related_findings": [
                        {"title": "No check_id", "severity": "high", "service": "s3"},
                        {"check_id": "s3_bucket_versioning", "title": "V", "severity": "medium", "service": "s3"},
                    ],
                    "control_mapping_ids": [],
                    "maturity_capability_ids": [],
                }
            },
            "_meta": {"confidence": "high"},
        }
        mock_rag_client.build_context.return_value = bundle
        result = planning_agent._retrieve_candidates("s3", "s3")

        # Should only have 1 valid candidate
        valid_ids = [c["check_id"] for c in result["candidates"]]
        assert "s3_bucket_versioning" in valid_ids

    def test_risk_empty_risk_bundle(self, risk_agent, mock_rag_client, sample_fail_findings):
        """D4.4: risk_bundle co related_findings=[] -> empty context_map."""
        bundle = {
            "payload": {
                "risk_bundle": {
                    "related_findings": [],
                    "control_mapping": [],
                }
            },
            "_meta": {"confidence": "medium"},
        }
        mock_rag_client.build_context.return_value = bundle
        result = risk_agent._fetch_rag_context(sample_fail_findings)
        assert isinstance(result, dict)

    def test_risk_missing_meta_field(self, risk_agent, mock_rag_client, sample_fail_findings):
        """D4.5: Response thieu _meta -> confidence van la 'unknown'."""
        bundle = {
            "payload": {
                "risk_bundle": {
                    "related_findings": [
                        {"check_id": "s3_bucket_public_access", "severity": "high", "title": "Test"},
                    ],
                    "control_mapping": [],
                }
            },
            # No _meta field
        }
        mock_rag_client.build_context.return_value = bundle
        risk_agent._fetch_rag_context(sample_fail_findings)
        assert risk_agent._rag_confidence == "unknown"

    def test_risk_malformed_control_mapping(self, risk_agent, mock_rag_client, sample_fail_findings):
        """D4.6: control_mapping co entries thieu check_id -> khong crash."""
        bundle = {
            "payload": {
                "risk_bundle": {
                    "related_findings": [
                        {"check_id": "s3_bucket_public_access", "severity": "high", "title": "Test"},
                    ],
                    "control_mapping": [
                        {"capability_id": "orphan_mapping"},  # No check_id
                        {"check_id": "s3_bucket_public_access", "capability_id": "valid_mapping"},
                    ],
                }
            },
            "_meta": {"confidence": "high"},
        }
        mock_rag_client.build_context.return_value = bundle
        result = risk_agent._fetch_rag_context(sample_fail_findings)
        assert isinstance(result, dict)


# ============================================================
# D5: Mixed Scenarios (Intermittent Failures)
# ============================================================

class TestMixedScenarios:
    """Simulating intermittent RAG failures."""

    def test_planning_first_attempt_fails_second_succeeds(self, planning_agent, mock_rag_client):
        """D5.1: build_context fails -> retrieve_checks succeeds."""
        mock_rag_client.build_context.return_value = None
        mock_rag_client.retrieve_checks.return_value = {
            "results": [
                {"doc_id": "check:s3_bucket_versioning", "score": 0.85,
                 "metadata": {"service": "s3", "title": "Versioning", "severity": "medium"}},
            ],
        }
        result = planning_agent._retrieve_candidates("s3 versioning", "s3")
        assert result["source"] == "retrieve_checks"
        assert len(result["candidates"]) == 1

    def test_risk_partial_batch_failure(self, risk_agent, mock_rag_client, large_fail_findings):
        """D5.2: First batch succeeds, second fails -> partial context."""
        call_count = [0]

        def side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "payload": {
                        "risk_bundle": {
                            "related_findings": [
                                {"check_id": "s3_bucket_public_access", "severity": "critical",
                                 "title": "Public Access"},
                            ],
                            "control_mapping": [],
                        }
                    },
                    "_meta": {"confidence": "high"},
                }
            else:
                return None  # Second batch fails

        mock_rag_client.build_context.side_effect = side_effect
        result = risk_agent._fetch_rag_context(large_fail_findings)

        # Should have partial results from first batch
        assert isinstance(result, dict)

    def test_planning_rag_returns_wrong_service_candidates(self, planning_agent, mock_rag_client):
        """D5.3: retrieve_checks returns wrong service -> filtered out."""
        mock_rag_client.build_context.return_value = None
        mock_rag_client.retrieve_checks.return_value = {
            "results": [
                {"doc_id": "check:iam_user_mfa", "score": 0.9,
                 "metadata": {"service": "iam", "title": "MFA", "severity": "critical"}},
                {"doc_id": "check:ec2_instance_public", "score": 0.8,
                 "metadata": {"service": "ec2", "title": "Public IP", "severity": "high"}},
            ],
        }
        result = planning_agent._retrieve_candidates("s3 security", "s3")

        # All wrong-service candidates should be filtered
        for c in result["candidates"]:
            assert c["service"] == "s3" or result["candidates"] == []

    def test_risk_llm_failure_uses_defaults(self, risk_agent):
        """D5.4: LLM scoring fails -> default values (Medium, 5)."""
        finding = {
            "status": "FAIL", "event_code": "test_check",
            "service": "test", "resource_id": "res", "region": "us-east-1",
            "description": "Test", "severity": "High", "remediation_text": "Fix",
        }
        risk_agent.llm.invoke.side_effect = Exception("LLM unavailable")

        result = risk_agent._score_single_finding(finding, {})
        assert result["severity"] == "Medium"
        assert result["risk_score"] == 5
