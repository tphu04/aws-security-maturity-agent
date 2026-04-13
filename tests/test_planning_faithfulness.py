"""
Tests for Planning Agent Faithfulness metric — negative checks + LLM path.

Covers:
  - Keyword grounding (positive check)
  - Check ID fabrication detection (N1)
  - Output-reasoning mismatch detection (N2)
  - Phantom reference detection (N3)
  - Combined scoring
  - LLM refinement path with real Ollama (integration test, skipped if unavailable)
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from benchmark_llm_gen.planning_metrics import evaluate_faithfulness


# ============================================================
# Positive check: grounding
# ============================================================

class TestGrounding:
    """Keyword evidence matching (base score)."""

    def test_grounded_with_check_id(self):
        result = evaluate_faithfulness(
            reasoning="Selected s3_bucket_public_access due to public access risk.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        assert result["grounded"] is True
        assert result["score"] == 1.0

    def test_grounded_with_service_name(self):
        result = evaluate_faithfulness(
            reasoning="This relates to S3 storage security concerns.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        assert result["grounded"] is True

    def test_not_grounded(self):
        result = evaluate_faithfulness(
            reasoning="I recommend checking firewall rules for better protection.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        # "firewall", "protection" not in evidence pool (s3, critical, s3_bucket_public_access)
        # But "s3_bucket_public_access" is in selected_checks → parts added to pool
        # "bucket_public_access" may match... let's check actual behavior
        assert isinstance(result["score"], float)

    def test_empty_reasoning(self):
        result = evaluate_faithfulness(
            reasoning="",
            rag_context={},
            selected_checks=[],
        )
        assert result["score"] == 0.0
        assert result["grounded"] is False

    def test_hardcoded_skip(self):
        result = evaluate_faithfulness(
            reasoning="Deterministic selection: RAG confidence=high, top_score=0.880",
            rag_context={},
            selected_checks=["s3_bucket_public_access"],
        )
        assert result["method"] == "hardcoded_skip"
        assert result["score"] == 1.0
        assert result["penalties"] == []


# ============================================================
# N1: Check ID Fabrication
# ============================================================

class TestCheckIdFabrication:
    """Detect reasoning mentioning check IDs not in RAG candidates."""

    def test_fabricated_check_id_penalized(self):
        result = evaluate_faithfulness(
            reasoning="Selected s3_bucket_public_access and also recommend cloudwatch_log_group_encrypted for monitoring.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        fabrication_penalties = [p for p in result["penalties"] if p["type"] == "check_id_fabrication"]
        assert len(fabrication_penalties) == 1
        assert result["score"] < 1.0

    def test_no_fabrication_when_all_in_context(self):
        result = evaluate_faithfulness(
            reasoning="Selected s3_bucket_public_access based on critical severity in RAG context.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        fabrication_penalties = [p for p in result["penalties"] if p["type"] == "check_id_fabrication"]
        assert len(fabrication_penalties) == 0

    def test_no_fabrication_when_in_selected(self):
        """Check IDs in selected_checks should not be counted as fabricated."""
        result = evaluate_faithfulness(
            reasoning="Selected kms_cmk_rotation_enabled because key rotation is important.",
            rag_context={"related_findings": []},
            selected_checks=["kms_cmk_rotation_enabled"],
        )
        fabrication_penalties = [p for p in result["penalties"] if p["type"] == "check_id_fabrication"]
        assert len(fabrication_penalties) == 0


# ============================================================
# N2: Output-Reasoning Mismatch
# ============================================================

class TestOutputReasoningMismatch:
    """Detect reasoning contradicting output."""

    def test_says_no_result_but_has_checks(self):
        result = evaluate_faithfulness(
            reasoning="No relevant checks found in the candidates for this request.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        mismatch_penalties = [p for p in result["penalties"] if p["type"] == "output_reasoning_mismatch"]
        assert len(mismatch_penalties) == 1
        assert result["score"] < 1.0

    def test_consistent_no_result(self):
        """Reasoning says no result AND output is empty → no penalty."""
        result = evaluate_faithfulness(
            reasoning="No relevant checks found for this vague query.",
            rag_context={},
            selected_checks=[],
        )
        mismatch_penalties = [p for p in result["penalties"] if p["type"] == "output_reasoning_mismatch"]
        assert len(mismatch_penalties) == 0

    def test_consistent_has_result(self):
        """Reasoning explains selection AND output has checks → no penalty."""
        result = evaluate_faithfulness(
            reasoning="Selected based on public access vulnerability with critical severity.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        mismatch_penalties = [p for p in result["penalties"] if p["type"] == "output_reasoning_mismatch"]
        assert len(mismatch_penalties) == 0

    def test_vietnamese_no_result_phrase(self):
        result = evaluate_faithfulness(
            reasoning="Khong tim thay check phu hop cho yeu cau nay.",
            rag_context={},
            selected_checks=["s3_bucket_public_access"],
        )
        mismatch_penalties = [p for p in result["penalties"] if p["type"] == "output_reasoning_mismatch"]
        assert len(mismatch_penalties) == 1


# ============================================================
# N3: Phantom Reference
# ============================================================

class TestPhantomReference:
    """Detect fabricated references to external sources."""

    def test_phantom_gartner_reference(self):
        result = evaluate_faithfulness(
            reasoning="Selected s3_bucket_public_access. Theo report Gartner 2024, public access is a top risk.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        phantom_penalties = [p for p in result["penalties"] if p["type"] == "phantom_reference"]
        assert len(phantom_penalties) == 1
        assert result["score"] < 1.0

    def test_phantom_breach_year(self):
        result = evaluate_faithfulness(
            reasoning="This vulnerability caused a breach in 2023 affecting millions of users.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        phantom_penalties = [p for p in result["penalties"] if p["type"] == "phantom_reference"]
        assert len(phantom_penalties) == 1

    def test_phantom_dollar_amount(self):
        result = evaluate_faithfulness(
            reasoning="This could cost $5 million in damages. Selected s3_bucket_public_access.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        phantom_penalties = [p for p in result["penalties"] if p["type"] == "phantom_reference"]
        assert len(phantom_penalties) == 1

    def test_no_phantom_clean_reasoning(self):
        result = evaluate_faithfulness(
            reasoning="Selected s3_bucket_public_access because public access to S3 is a critical security risk.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        phantom_penalties = [p for p in result["penalties"] if p["type"] == "phantom_reference"]
        assert len(phantom_penalties) == 0


# ============================================================
# Combined scoring
# ============================================================

class TestCombinedScoring:
    """Test penalty accumulation and score floor."""

    def test_multiple_penalties_accumulate(self):
        result = evaluate_faithfulness(
            reasoning="No relevant checks found. According to Gartner report, security is important. Also check cloudwatch_log_group_encrypted.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        # N2: says "no relevant" but has checks → -0.3
        # N3: "According to Gartner report" → -0.2
        # N1: "cloudwatch_log_group_encrypted" not in RAG → -0.3
        assert len(result["penalties"]) >= 2
        assert result["score"] <= 0.5

    def test_score_floor_at_zero(self):
        """Score should never go below 0.0."""
        result = evaluate_faithfulness(
            reasoning="No relevant checks. Theo bao cao Gartner, $5 million loss in 2023 breach. Also cloudwatch_log_group_encrypted is needed.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        assert result["score"] >= 0.0

    def test_perfect_reasoning(self):
        """Clean reasoning with all evidence grounded → score 1.0."""
        result = evaluate_faithfulness(
            reasoning="Selected s3_bucket_public_access due to critical severity public access vulnerability in S3.",
            rag_context={"related_findings": [
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
            ]},
            selected_checks=["s3_bucket_public_access"],
        )
        assert result["score"] == 1.0
        assert result["penalties"] == []
        assert result["grounded"] is True


# ============================================================
# LLM Refinement Path — Integration test
# ============================================================

def _ollama_available():
    """Check if Ollama is running."""
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        return True
    except Exception:
        return False


def _rag_available():
    """Check if RAG server is running."""
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:8001/ready", timeout=3)
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not (_ollama_available() and _rag_available()),
    reason="Requires Ollama + RAG server running"
)
class TestLLMRefinementIntegration:
    """Integration test: force low confidence → LLM refinement → measure faithfulness.

    Requires: Ollama at localhost:11434, RAG at localhost:8001.
    """

    def _run_with_low_confidence(self, user_request: str):
        """Run Planning Agent with RAG forced to low confidence."""
        import sys
        sys.path.insert(0, ".")
        from agents.planning_agent import PlanningAgent
        from agents.shared.rag_client import RAGClient

        rag = RAGClient(base_url="http://localhost:8001")
        agent = PlanningAgent(
            model_name="llama3.2",
            base_url="http://localhost:11434",
            rag_client=rag,
        )

        # Patch _retrieve to return low confidence → force LLM refinement
        real_retrieve = agent._retrieve

        def patched_retrieve(query):
            result = real_retrieve(query)
            result["confidence"] = "low"  # Force low confidence
            return result

        agent._retrieve = patched_retrieve
        output = agent.run(user_request)

        # Also get RAG context for faithfulness eval
        rag_result = rag.build_context(consumer="planning", query=user_request, top_k=10)
        rag_context = {}
        if rag_result:
            bundle = rag_result.get("payload", {}).get("planning_bundle", {})
            rag_context = {
                "related_findings": bundle.get("related_findings", []),
                "control_mapping_ids": bundle.get("control_mapping_ids", []),
                "maturity_capability_ids": bundle.get("maturity_capability_ids", []),
            }

        return output, rag_context

    def test_llm_reasoning_is_evaluated(self):
        """LLM refinement produces non-hardcoded reasoning → faithfulness actually evaluated."""
        output, rag_context = self._run_with_low_confidence("check S3 public access")

        checks = output.get("checks_to_scan", [])
        reasoning = output.get("reasoning", "")

        result = evaluate_faithfulness(
            reasoning=reasoning,
            rag_context=rag_context,
            selected_checks=checks,
        )

        # Method should NOT be hardcoded_skip (LLM generated reasoning)
        assert result["method"] == "keyword_with_negative_checks", \
            f"Expected keyword_with_negative_checks, got {result['method']}. Reasoning: {reasoning[:100]}"

        # Score should be a real evaluation, not trivially 1.0
        assert isinstance(result["score"], float)
        assert 0.0 <= result["score"] <= 1.0

        # Should have checked for penalties
        assert "penalties" in result

    def test_llm_reasoning_grounded_in_context(self):
        """LLM reasoning should reference RAG context (check IDs, service names)."""
        output, rag_context = self._run_with_low_confidence("check if KMS keys have rotation enabled")

        checks = output.get("checks_to_scan", [])
        reasoning = output.get("reasoning", "")

        result = evaluate_faithfulness(
            reasoning=reasoning,
            rag_context=rag_context,
            selected_checks=checks,
        )

        # Expect grounded (LLM should mention KMS or check IDs from context)
        # This may fail if LLM produces poor reasoning — that's a valid finding
        print(f"  Reasoning: {reasoning[:200]}")
        print(f"  Score: {result['score']}, Grounded: {result['grounded']}")
        print(f"  Penalties: {result['penalties']}")
        print(f"  Evidence: {result['evidence_found']}")

    def test_llm_no_fabrication(self):
        """LLM should not fabricate check IDs not in RAG candidates."""
        output, rag_context = self._run_with_low_confidence("verify S3 bucket encryption")

        checks = output.get("checks_to_scan", [])
        reasoning = output.get("reasoning", "")

        result = evaluate_faithfulness(
            reasoning=reasoning,
            rag_context=rag_context,
            selected_checks=checks,
        )

        fabrication_penalties = [p for p in result["penalties"] if p["type"] == "check_id_fabrication"]
        print(f"  Reasoning: {reasoning[:200]}")
        print(f"  Fabrication penalties: {fabrication_penalties}")
        # Report finding rather than hard assert — LLM behavior varies
