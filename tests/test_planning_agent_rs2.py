"""
Unit Tests cho PlanningAgent V2 — RAG-first, LLM-conditional
=============================================================
Covers:
  - InputClassifier: check ID extraction, service detection, path classification
  - DeterministicScorer: weighted formula, severity, service match, ordering
  - ConfidenceGate: high/medium skip LLM, low triggers LLM
  - LLM Refinement: select checks, fallback to group, explicit error
  - Output Contract: both aliases, error output
  - End-to-End: all paths integrated
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from agents.planning_agent import (
    PlanningAgent,
    ALLOWED_GROUPS,
    SEVERITY_WEIGHTS,
    SCORE_WEIGHT_RAG,
    SCORE_WEIGHT_SEVERITY,
    SCORE_WEIGHT_SERVICE,
    TOP_K_RESULTS,
    LLM_REFINEMENT_PROMPT,
    VALID_SERVICES,
)
from agents.shared.rag_client import RAGClient


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_rag_client():
    """Create a mocked RAGClient (no real HTTP calls)."""
    client = MagicMock(spec=RAGClient)
    client.is_healthy.return_value = True
    return client


@pytest.fixture
def agent(mock_rag_client):
    """Create PlanningAgent with mocked LLM and RAGClient."""
    with patch("agents.planning_agent.ChatOllama") as MockLLM:
        mock_llm = MagicMock()
        MockLLM.return_value = mock_llm
        a = PlanningAgent(
            model_name="test-model",
            base_url="http://localhost:11434",
            rag_client=mock_rag_client,
        )
        a.llm = mock_llm
        yield a


@pytest.fixture
def agent_no_rag():
    """Create PlanningAgent without RAGClient (degraded mode)."""
    with patch("agents.planning_agent.ChatOllama") as MockLLM:
        mock_llm = MagicMock()
        MockLLM.return_value = mock_llm
        a = PlanningAgent(
            model_name="test-model",
            base_url="http://localhost:11434",
            rag_client=None,
        )
        a.llm = mock_llm
        yield a


def _make_rag_build_context_response(findings, confidence="high", mappings=None, maturity=None):
    """Helper to build a mock build_context response."""
    return {
        "payload": {
            "planning_bundle": {
                "related_findings": findings,
                "control_mapping_ids": mappings or [],
                "maturity_capability_ids": maturity or [],
            }
        },
        "_meta": {"confidence": confidence},
    }


def _make_rag_retrieve_response(results):
    """Helper to build a mock retrieve_checks response."""
    return {"results": results}


# ============================================================
# TestInputClassifier
# ============================================================

class TestInputClassifier:
    """Test _classify_input, _extract_check_ids, _detect_service."""

    def test_extract_check_ids_valid(self, agent):
        ids = agent._extract_check_ids("scan s3_bucket_public_access and s3_bucket_versioning_enabled")
        assert "s3_bucket_public_access" in ids
        assert "s3_bucket_versioning_enabled" in ids

    def test_extract_check_ids_rejects_short(self, agent):
        ids = agent._extract_check_ids("check s3_test")
        assert ids == []

    def test_extract_check_ids_rejects_no_service_prefix(self, agent):
        ids = agent._extract_check_ids("check foobar_something_else_long_enough")
        assert ids == []

    def test_extract_check_ids_rejects_natural_language(self, agent):
        ids = agent._extract_check_ids("anyone_can_enumerate_objects_in_the_bucket")
        assert ids == []

    def test_detect_service_direct(self, agent):
        assert agent._detect_service("check my s3 buckets") == "s3"

    def test_detect_service_keyword(self, agent):
        assert agent._detect_service("check my buckets") == "s3"

    def test_detect_service_iam_keyword(self, agent):
        assert agent._detect_service("check user permissions") == "iam"

    def test_detect_service_none(self, agent):
        assert agent._detect_service("do something random") is None

    def test_classify_fast_track(self, agent):
        result = agent._classify_input("scan s3_bucket_public_access_block")
        assert result["path"] == "FAST_TRACK"
        assert len(result["check_ids"]) >= 1

    def test_classify_group_scan(self, agent):
        result = agent._classify_input("scan all iam checks")
        assert result["path"] == "GROUP_SCAN"
        assert result["service"] == "iam"

    def test_classify_group_scan_requires_service(self, agent):
        result = agent._classify_input("scan all checks")
        assert result["path"] == "RETRIEVAL_PATH"

    def test_classify_group_scan_requires_allowed_group(self, agent):
        result = agent._classify_input("scan all sagemaker checks")
        assert result["path"] == "RETRIEVAL_PATH"

    def test_classify_retrieval_default(self, agent):
        result = agent._classify_input("check public buckets")
        assert result["path"] == "RETRIEVAL_PATH"
        assert result["service"] == "s3"


# ============================================================
# TestDeterministicScorer
# ============================================================

class TestDeterministicScorer:
    """Test _score_candidates pure function."""

    def test_scoring_formula(self, agent):
        retrieval = {"candidates": [
            {"check_id": "s3_test_check_one", "severity": "critical", "service": "s3", "score": 0.9},
        ]}
        scored = agent._score_candidates(retrieval, "s3")
        expected = round(
            SCORE_WEIGHT_RAG * 0.9 + SCORE_WEIGHT_SEVERITY * 1.0 + SCORE_WEIGHT_SERVICE * 1.0,
            4,
        )
        assert scored[0]["final_score"] == expected

    def test_severity_boost(self, agent):
        retrieval = {"candidates": [
            {"check_id": "s3_check_low_one", "severity": "low", "service": "s3", "score": 0.9},
            {"check_id": "s3_check_critical_one", "severity": "critical", "service": "s3", "score": 0.9},
        ]}
        scored = agent._score_candidates(retrieval, "s3")
        assert scored[0]["check_id"] == "s3_check_critical_one"

    def test_service_match_bonus(self, agent):
        retrieval = {"candidates": [
            {"check_id": "ec2_check_test_one", "severity": "high", "service": "ec2", "score": 0.8},
            {"check_id": "s3_check_test_one", "severity": "high", "service": "s3", "score": 0.8},
        ]}
        scored = agent._score_candidates(retrieval, "s3")
        assert scored[0]["check_id"] == "s3_check_test_one"

    def test_returns_top_k(self, agent):
        retrieval = {"candidates": [
            {"check_id": f"s3_check_number_{i:02d}", "severity": "medium", "service": "s3", "score": 0.5}
            for i in range(10)
        ]}
        scored = agent._score_candidates(retrieval, "s3")
        assert len(scored) == TOP_K_RESULTS

    def test_empty_candidates(self, agent):
        scored = agent._score_candidates({"candidates": []}, "s3")
        assert scored == []

    def test_no_service_detected(self, agent):
        retrieval = {"candidates": [
            {"check_id": "s3_check_test_one", "severity": "high", "service": "s3", "score": 0.8},
        ]}
        scored = agent._score_candidates(retrieval, None)
        expected = round(SCORE_WEIGHT_RAG * 0.8 + SCORE_WEIGHT_SEVERITY * 0.8 + SCORE_WEIGHT_SERVICE * 0.0, 4)
        assert scored[0]["final_score"] == expected


# ============================================================
# TestConfidenceGate
# ============================================================

class TestConfidenceGate:
    """Test _apply_confidence_gate decision logic."""

    def test_high_confidence_skips_llm(self, agent):
        retrieval = {"confidence": "high", "candidates": [], "maturity_context": ""}
        scored = [{"check_id": "s3_bucket_public_access", "final_score": 0.8}]
        result = agent._apply_confidence_gate("check s3", scored, retrieval)
        assert "s3_bucket_public_access" in result["checks_to_scan"]
        assert not result.get("error")
        # LLM should NOT have been called
        agent.llm.invoke.assert_not_called()

    def test_medium_confidence_skips_llm(self, agent):
        retrieval = {"confidence": "medium", "candidates": [], "maturity_context": ""}
        scored = [{"check_id": "iam_user_mfa_enabled", "final_score": 0.5}]
        result = agent._apply_confidence_gate("check iam", scored, retrieval)
        assert "iam_user_mfa_enabled" in result["checks_to_scan"]

    def test_low_confidence_calls_llm(self, agent, mock_rag_client):
        retrieval = {"confidence": "low", "candidates": [], "maturity_context": "", "source": "none"}
        scored = [{"check_id": "s3_test_check_one", "final_score": 0.2}]

        # Mock LLM chain
        with patch.object(agent, "_llm_refine", return_value=agent._make_output(
            checks=["s3_test_check_one"], reasoning="LLM refined"
        )) as mock_refine:
            result = agent._apply_confidence_gate("check something", scored, retrieval)
            mock_refine.assert_called_once()

    def test_high_confidence_low_score_calls_llm(self, agent):
        retrieval = {"confidence": "high", "candidates": [], "maturity_context": ""}
        scored = [{"check_id": "s3_test_check_one", "final_score": 0.1}]

        with patch.object(agent, "_llm_refine", return_value=agent._make_output(
            checks=["s3_test_check_one"], reasoning="refined"
        )) as mock_refine:
            agent._apply_confidence_gate("something", scored, retrieval)
            mock_refine.assert_called_once()

    def test_empty_candidates_calls_llm(self, agent):
        retrieval = {"confidence": "high", "candidates": [], "maturity_context": ""}

        with patch.object(agent, "_llm_refine", return_value=agent._make_error_output("no data")) as mock_refine:
            agent._apply_confidence_gate("something", [], retrieval)
            mock_refine.assert_called_once()


# ============================================================
# TestLLMRefinement
# ============================================================

class TestLLMRefinement:
    """Test _llm_refine conditional LLM call."""

    def _setup_llm_response(self, agent, response_dict):
        """Configure mock LLM to return a specific JSON response."""
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = json.dumps(response_dict)
        agent.llm.__or__ = MagicMock(return_value=mock_chain)

    def test_selects_checks(self, agent):
        with patch("agents.planning_agent.ChatPromptTemplate") as MockPrompt:
            mock_chain = MagicMock()
            mock_chain.invoke.return_value = json.dumps({
                "selected_ids": ["s3_bucket_public_access"],
                "target_group": "",
                "reasoning": "Selected S3 check",
            })
            MockPrompt.from_template.return_value.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )
            result = agent._llm_refine(
                "check s3", [{"check_id": "s3_bucket_public_access", "final_score": 0.3}],
                {"maturity_context": ""},
            )
            assert "s3_bucket_public_access" in result["checks_to_scan"]

    def test_falls_back_to_group(self, agent):
        with patch("agents.planning_agent.ChatPromptTemplate") as MockPrompt:
            mock_chain = MagicMock()
            mock_chain.invoke.return_value = json.dumps({
                "selected_ids": [],
                "target_group": "iam",
                "reasoning": "Scan all IAM",
            })
            MockPrompt.from_template.return_value.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )
            result = agent._llm_refine("check iam", [], {"maturity_context": ""})
            assert result["groups_to_scan"] == ["iam"]

    def test_explicit_error_on_total_failure(self, agent):
        with patch("agents.planning_agent.ChatPromptTemplate") as MockPrompt:
            mock_chain = MagicMock()
            mock_chain.invoke.return_value = json.dumps({
                "selected_ids": [],
                "target_group": "",
                "reasoning": "Cannot determine intent",
            })
            MockPrompt.from_template.return_value.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )
            result = agent._llm_refine("do something", [], {"maturity_context": ""})
            assert result.get("error")
            assert result["groups_to_scan"] == []
            assert result["checks_to_scan"] == []

    def test_llm_exception_returns_error(self, agent):
        with patch("agents.planning_agent.ChatPromptTemplate") as MockPrompt:
            MockPrompt.from_template.return_value.__or__ = MagicMock(
                side_effect=Exception("Ollama timeout")
            )
            result = agent._llm_refine("check s3", [], {"maturity_context": ""})
            assert result.get("error")
            assert "s3" not in result["groups_to_scan"]


# ============================================================
# TestOutputContract
# ============================================================

class TestOutputContract:
    """Test output format matches downstream consumer expectations."""

    def test_make_output_has_both_aliases(self, agent):
        result = agent._make_output(groups=["s3"], reasoning="test")
        assert result["groups_to_scan"] == ["s3"]
        assert result["target_services"] == ["s3"]
        assert result["checks_to_scan"] == []
        assert result["reasoning"] == "test"

    def test_make_output_checks(self, agent):
        result = agent._make_output(checks=["s3_bucket_public_access"], reasoning="test")
        assert result["groups_to_scan"] == []
        assert result["target_services"] == []
        assert result["checks_to_scan"] == ["s3_bucket_public_access"]

    def test_make_error_output_no_s3_default(self, agent):
        result = agent._make_error_output("something failed")
        assert result["groups_to_scan"] == []
        assert result["target_services"] == []
        assert result["checks_to_scan"] == []
        assert result["error"] == "something failed"

    def test_output_has_all_required_keys(self, agent):
        result = agent._make_output(groups=["iam"], checks=["iam_user_mfa_enabled"])
        required = {"groups_to_scan", "target_services", "checks_to_scan", "reasoning"}
        assert required.issubset(set(result.keys()))


# ============================================================
# TestRAGIntegration
# ============================================================

class TestRAGIntegration:
    """Test _retrieve and RAG fallback chain."""

    def test_build_context_success(self, agent, mock_rag_client):
        mock_rag_client.build_context.return_value = _make_rag_build_context_response(
            findings=[
                {"check_id": "s3_bucket_public_access", "title": "Public Access", "severity": "high", "service": "s3"},
                {"check_id": "s3_bucket_versioning_enabled", "title": "Versioning", "severity": "medium", "service": "s3"},
            ],
            confidence="high",
        )
        result = agent._retrieve("check s3 buckets")
        assert result["source"] == "build_context"
        assert result["confidence"] == "high"
        assert len(result["candidates"]) == 2

    def test_fallback_to_retrieve_checks(self, agent, mock_rag_client):
        mock_rag_client.build_context.return_value = None
        mock_rag_client.retrieve_checks.return_value = _make_rag_retrieve_response([
            {"doc_id": "check:s3_bucket_public_access", "score": 0.75, "metadata": {"title": "Public", "severity": "high", "service": "s3"}},
        ])
        result = agent._retrieve("check s3")
        assert result["source"] == "retrieve_checks"
        assert len(result["candidates"]) == 1

    def test_both_fail_returns_empty(self, agent, mock_rag_client):
        mock_rag_client.build_context.return_value = None
        mock_rag_client.retrieve_checks.return_value = None
        result = agent._retrieve("check something")
        assert result["source"] == "none"
        assert result["candidates"] == []
        assert result["confidence"] == "low"

    def test_no_rag_client_returns_empty(self, agent_no_rag):
        result = agent_no_rag._retrieve("check s3")
        assert result["candidates"] == []
        assert result["source"] == "none"

    def test_deduplicates_candidates(self, agent, mock_rag_client):
        mock_rag_client.build_context.return_value = _make_rag_build_context_response(
            findings=[
                {"check_id": "s3_bucket_public_access", "title": "Public", "severity": "high", "service": "s3"},
                {"check_id": "s3_bucket_public_access", "title": "Public Dup", "severity": "high", "service": "s3"},
            ],
            confidence="high",
        )
        result = agent._retrieve("check s3")
        assert len(result["candidates"]) == 1


# ============================================================
# TestEndToEnd
# ============================================================

class TestEndToEnd:
    """Test full run() pipeline integration."""

    def test_fast_track_skips_everything(self, agent, mock_rag_client):
        result = agent.run("scan s3_bucket_public_access_block")
        assert "s3_bucket_public_access_block" in result["checks_to_scan"]
        assert result["groups_to_scan"] == []
        mock_rag_client.build_context.assert_not_called()

    def test_group_scan_skips_everything(self, agent, mock_rag_client):
        result = agent.run("scan all iam checks")
        assert result["groups_to_scan"] == ["iam"]
        assert result["target_services"] == ["iam"]
        assert result["checks_to_scan"] == []
        mock_rag_client.build_context.assert_not_called()

    def test_retrieval_high_confidence_no_llm(self, agent, mock_rag_client):
        mock_rag_client.build_context.return_value = _make_rag_build_context_response(
            findings=[
                {"check_id": "s3_bucket_public_access", "title": "Public Access", "severity": "critical", "service": "s3"},
                {"check_id": "s3_bucket_versioning_enabled", "title": "Versioning", "severity": "high", "service": "s3"},
            ],
            confidence="high",
        )
        result = agent.run("check public s3 buckets")
        assert len(result["checks_to_scan"]) > 0
        assert not result.get("error")
        # LLM should not have been called
        agent.llm.invoke.assert_not_called()

    def test_empty_request_returns_error(self, agent):
        result = agent.run("")
        assert result.get("error")
        assert result["groups_to_scan"] == []

    def test_none_request_returns_error(self, agent):
        result = agent.run(None)
        assert result.get("error")

    def test_total_failure_no_s3_default(self, agent, mock_rag_client):
        mock_rag_client.build_context.return_value = None
        mock_rag_client.retrieve_checks.return_value = None

        with patch.object(agent, "_llm_refine", return_value=agent._make_error_output("Cannot determine")):
            result = agent.run("do something vague")
            assert result.get("error")
            assert "s3" not in result["groups_to_scan"]
            assert result["checks_to_scan"] == []


# ============================================================
# TestConstants
# ============================================================

class TestConstants:
    """Test module-level constants are properly configured."""

    def test_valid_services_at_least_20(self):
        assert len(VALID_SERVICES) >= 20

    def test_allowed_groups_subset_of_valid(self):
        assert ALLOWED_GROUPS.issubset(set(VALID_SERVICES))

    def test_severity_weights_complete(self):
        for sev in ("critical", "high", "medium", "low"):
            assert sev in SEVERITY_WEIGHTS

    def test_scoring_weights_sum_to_1(self):
        total = SCORE_WEIGHT_RAG + SCORE_WEIGHT_SEVERITY + SCORE_WEIGHT_SERVICE
        assert abs(total - 1.0) < 0.001

    def test_refinement_prompt_exists(self):
        assert "selected_ids" in LLM_REFINEMENT_PROMPT
        assert "target_group" in LLM_REFINEMENT_PROMPT
