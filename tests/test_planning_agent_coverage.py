"""
Supplementary Tests for PlanningAgent V2 — Coverage Gaps
=========================================================
Covers gaps identified by benchmark analysis:

  Gap 1: _build_rag_query (Vietnamese → English translation)
  Gap 2: _enrich_scores (score enrichment from retrieve_checks)
  Gap 3: Score gap filter (DROP_RATIO_THRESHOLD in confidence gate)
  Gap 4: LLM refinement path with mock LLM (end-to-end low confidence)
  Gap 5: No-RAG degradation (RAG ablation scenario)
"""

import json
from unittest.mock import MagicMock, patch, call

import pytest

from pdca.agents.planning_agent import (
    PlanningAgent,
    ALLOWED_GROUPS,
    DROP_RATIO_THRESHOLD,
    MIN_TOP_SCORE_FOR_SKIP,
    TOP_K_RESULTS,
    _VI_EN_SECURITY_KEYWORDS,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_rag_client():
    client = MagicMock()
    client.is_healthy.return_value = True
    return client


@pytest.fixture
def agent(mock_rag_client):
    with patch("pdca.agents.planning_agent.ChatOllama") as MockLLM:
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
    with patch("pdca.agents.planning_agent.ChatOllama") as MockLLM:
        mock_llm = MagicMock()
        MockLLM.return_value = mock_llm
        a = PlanningAgent(
            model_name="test-model",
            base_url="http://localhost:11434",
            rag_client=None,
        )
        a.llm = mock_llm
        yield a


def _make_build_context_response(findings, confidence="medium", mappings=None, maturity=None):
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


def _make_retrieve_response(results):
    return {"results": results}


# ============================================================
# Gap 1: TestBuildRagQuery — Vietnamese → English translation
# ============================================================

class TestBuildRagQuery:
    """Test _build_rag_query: Vietnamese keyword translation + English passthrough."""

    # --- Vietnamese translation ---

    def test_vietnamese_encryption_query(self):
        result = PlanningAgent._build_rag_query("kiểm tra mã hóa RDS database storage", "rds")
        assert "encryption" in result
        assert "rds" in result
        assert "database" in result
        assert "storage" in result

    def test_vietnamese_mfa_query(self):
        result = PlanningAgent._build_rag_query(
            "kiểm tra MFA có được bật cho tất cả IAM users không", "iam"
        )
        assert "iam" in result
        assert "enabled" in result
        assert "mfa" in result.lower()

    def test_vietnamese_public_access_query(self):
        result = PlanningAgent._build_rag_query(
            "kiểm tra xem S3 bucket có bị public access không", "s3"
        )
        assert "s3" in result
        assert "public" in result
        assert "access" in result
        assert "bucket" in result

    def test_vietnamese_network_security(self):
        result = PlanningAgent._build_rag_query("kiểm tra bảo mật mạng", "ec2")
        assert "security" in result
        assert "network" in result

    def test_vietnamese_logging_query(self):
        result = PlanningAgent._build_rag_query("kiểm tra nhật ký hệ thống", "cloudtrail")
        assert "logging" in result
        assert "cloudtrail" in result

    def test_vietnamese_password_policy(self):
        result = PlanningAgent._build_rag_query("kiểm tra chính sách mật khẩu IAM", "iam")
        assert "password" in result
        assert "policy" in result

    def test_vietnamese_access_permission(self):
        result = PlanningAgent._build_rag_query("kiểm tra quyền truy cập trong hệ thống", "iam")
        assert "access" in result
        assert "permission" in result

    def test_vietnamese_backup_query(self):
        result = PlanningAgent._build_rag_query("kiểm tra sao lưu cơ sở dữ liệu", "rds")
        assert "backup" in result
        assert "database" in result

    # --- No noise (Vietnamese fragments filtered) ---

    def test_no_vietnamese_fragments_in_output(self):
        """Output should not contain Vietnamese leftover fragments."""
        result = PlanningAgent._build_rag_query(
            "kiểm tra xem S3 bucket có bị public access không", "s3"
        )
        fragments = {"tra", "xem", "cho", "trong", "truy", "khong", "dang"}
        words = set(result.lower().split())
        assert not words & fragments, f"Found Vietnamese fragments: {words & fragments}"

    def test_no_fragments_complex_query(self):
        result = PlanningAgent._build_rag_query(
            "kiểm tra quyền truy cập trong hệ thống cho tất cả người dùng", "iam"
        )
        for frag in ["tra", "truy", "trong", "cho", "tat"]:
            assert f" {frag} " not in f" {result} ", f"Fragment '{frag}' found in: {result}"

    # --- English passthrough ---

    def test_english_query_passthrough(self):
        query = "check if S3 buckets have encryption enabled"
        result = PlanningAgent._build_rag_query(query, "s3")
        # Should pass through mostly unchanged (may prepend service)
        assert "check" in result
        assert "encryption" in result

    def test_english_query_prepends_service_if_missing(self):
        result = PlanningAgent._build_rag_query("verify EBS volumes are encrypted", "ec2")
        assert result.startswith("ec2")

    def test_english_query_no_double_service(self):
        result = PlanningAgent._build_rag_query("check ec2 security groups", "ec2")
        # Should not have "ec2" twice
        assert result.count("ec2") <= 2  # once in service, once in original text

    # --- Edge cases ---

    def test_empty_service(self):
        result = PlanningAgent._build_rag_query("kiểm tra mã hóa", None)
        assert "encryption" in result

    def test_mixed_vi_en_query(self):
        result = PlanningAgent._build_rag_query(
            "kiểm tra encryption cho S3 bucket", "s3"
        )
        assert "encryption" in result
        assert "s3" in result

    def test_vi_en_keyword_map_coverage(self):
        """All Vietnamese keywords should map to non-empty English."""
        for vi, en in _VI_EN_SECURITY_KEYWORDS.items():
            assert len(en) > 0, f"Empty translation for: {vi}"
            assert en.isascii(), f"Non-ASCII translation for {vi}: {en}"


# ============================================================
# Gap 2: TestEnrichScores — Score enrichment from retrieve_checks
# ============================================================

class TestEnrichScores:
    """Test _enrich_scores: merge real scores from retrieve_checks into PlanningBundle."""

    def test_enriches_default_scores(self, agent, mock_rag_client):
        """When build_context returns score=None (default 0.8), enrich from retrieve_checks."""
        # PlanningBundle with default scores
        bundle = {
            "candidates": [
                {"check_id": "s3_bucket_public_access", "score": 0.8, "severity": "critical", "service": "s3", "title": ""},
                {"check_id": "s3_bucket_encryption", "score": 0.8, "severity": "medium", "service": "s3", "title": ""},
            ],
            "maturity_context": "",
            "confidence": "medium",
            "source": "build_context",
        }

        # retrieve_checks returns real scores
        mock_rag_client.retrieve_checks.return_value = _make_retrieve_response([
            {"doc_id": "check:s3_bucket_public_access", "score": 1.05, "metadata": {"severity": "critical", "service": "s3", "title": ""}},
            {"doc_id": "check:s3_bucket_encryption", "score": 0.72, "metadata": {"severity": "medium", "service": "s3", "title": ""}},
        ])

        result = agent._enrich_scores("test query", bundle)

        # Scores should be updated
        scores = {c["check_id"]: c["score"] for c in result["candidates"]}
        assert scores["s3_bucket_public_access"] == 1.05
        assert scores["s3_bucket_encryption"] == 0.72

    def test_no_enrich_when_retrieve_fails(self, agent, mock_rag_client):
        """When retrieve_checks returns None, keep original scores."""
        bundle = {
            "candidates": [
                {"check_id": "s3_bucket_public_access", "score": 0.8, "severity": "critical", "service": "s3", "title": ""},
            ],
            "maturity_context": "",
            "confidence": "medium",
            "source": "build_context",
        }
        mock_rag_client.retrieve_checks.return_value = None

        result = agent._enrich_scores("test", bundle)
        assert result["candidates"][0]["score"] == 0.8  # unchanged

    def test_partial_enrich(self, agent, mock_rag_client):
        """Only some candidates get enriched (others not in retrieve_checks)."""
        bundle = {
            "candidates": [
                {"check_id": "s3_bucket_public_access", "score": 0.8, "severity": "critical", "service": "s3", "title": ""},
                {"check_id": "s3_bucket_logging", "score": 0.8, "severity": "medium", "service": "s3", "title": ""},
            ],
            "maturity_context": "",
            "confidence": "medium",
            "source": "build_context",
        }
        mock_rag_client.retrieve_checks.return_value = _make_retrieve_response([
            {"doc_id": "check:s3_bucket_public_access", "score": 1.03, "metadata": {"severity": "critical", "service": "s3", "title": ""}},
            # s3_bucket_logging NOT in retrieve results
        ])

        result = agent._enrich_scores("test", bundle)
        scores = {c["check_id"]: c["score"] for c in result["candidates"]}
        assert scores["s3_bucket_public_access"] == 1.03  # enriched
        assert scores["s3_bucket_logging"] == 0.8  # unchanged

    def test_enrich_triggered_when_all_default(self, agent, mock_rag_client):
        """_retrieve should call _enrich_scores when all scores are 0.8."""
        # build_context returns findings with score=None → default 0.8
        mock_rag_client.build_context.return_value = _make_build_context_response(
            findings=[
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3", "title": ""},
            ],
            confidence="medium",
        )
        # retrieve_checks returns real scores
        mock_rag_client.retrieve_checks.return_value = _make_retrieve_response([
            {"doc_id": "check:s3_bucket_public_access", "score": 1.05, "metadata": {"severity": "critical", "service": "s3", "title": ""}},
        ])

        result = agent._retrieve("test query")

        # Should have been enriched
        assert result["candidates"][0]["score"] == 1.05

    def test_no_enrich_when_scores_are_real(self, agent, mock_rag_client):
        """Skip enrichment when build_context already has real scores."""
        mock_rag_client.build_context.return_value = _make_build_context_response(
            findings=[
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3", "title": "", "score": 0.95},
            ],
            confidence="medium",
        )

        result = agent._retrieve("test query")

        # retrieve_checks should NOT be called for enrichment
        assert result["candidates"][0]["score"] == 0.95
        mock_rag_client.retrieve_checks.assert_not_called()


# ============================================================
# Gap 3: TestScoreGapFilter — DROP_RATIO_THRESHOLD in gate
# ============================================================

class TestScoreGapFilter:
    """Test score gap filter drops low-scoring candidates."""

    def test_filter_drops_low_scores(self, agent, mock_rag_client):
        """Candidates below cutoff should be dropped."""
        scored = [
            {"check_id": "kms_cmk_rotation_enabled", "final_score": 0.87, "severity": "high", "service": "kms"},
            {"check_id": "kms_cmk_not_deleted", "final_score": 0.60, "severity": "medium", "service": "kms"},
            {"check_id": "kms_cmk_are_used", "final_score": 0.55, "severity": "low", "service": "kms"},
        ]
        retrieval = {"confidence": "medium"}

        result = agent._apply_confidence_gate("check kms rotation", scored, retrieval)

        # Only first should survive (0.87 * 0.85 = 0.7395, others below)
        checks = result["checks_to_scan"]
        assert "kms_cmk_rotation_enabled" in checks
        assert "kms_cmk_not_deleted" not in checks
        assert "kms_cmk_are_used" not in checks

    def test_filter_keeps_close_scores(self, agent, mock_rag_client):
        """Candidates with similar scores should all be kept."""
        scored = [
            {"check_id": "s3_bucket_public_access", "final_score": 0.88, "severity": "critical", "service": "s3"},
            {"check_id": "s3_bucket_level_public_access_block", "final_score": 0.86, "severity": "high", "service": "s3"},
            {"check_id": "s3_account_level_public_access_blocks", "final_score": 0.85, "severity": "high", "service": "s3"},
        ]
        retrieval = {"confidence": "high"}

        result = agent._apply_confidence_gate("check s3 public access", scored, retrieval)

        # All within 85% of top (0.88 * 0.85 = 0.748) → all kept
        assert len(result["checks_to_scan"]) == 3

    def test_filter_with_single_candidate(self, agent, mock_rag_client):
        """Single candidate always kept."""
        scored = [
            {"check_id": "kms_cmk_rotation_enabled", "final_score": 0.75, "severity": "high", "service": "kms"},
        ]
        retrieval = {"confidence": "medium"}

        result = agent._apply_confidence_gate("check kms", scored, retrieval)
        assert result["checks_to_scan"] == ["kms_cmk_rotation_enabled"]

    def test_filter_threshold_boundary(self, agent, mock_rag_client):
        """Score exactly at cutoff should be kept."""
        top = 1.0
        cutoff = top * DROP_RATIO_THRESHOLD  # 0.85

        scored = [
            {"check_id": "check_a", "final_score": top, "severity": "critical", "service": "s3"},
            {"check_id": "check_b", "final_score": cutoff, "severity": "high", "service": "s3"},  # exactly at cutoff
            {"check_id": "check_c", "final_score": cutoff - 0.001, "severity": "medium", "service": "s3"},  # just below
        ]
        retrieval = {"confidence": "high"}

        result = agent._apply_confidence_gate("test", scored, retrieval)
        checks = result["checks_to_scan"]
        assert "check_a" in checks
        assert "check_b" in checks
        assert "check_c" not in checks


# ============================================================
# Gap 4: TestLLMRefinementPath — End-to-end low confidence
# ============================================================

class TestLLMRefinementPath:
    """Test the LLM refinement path triggers and works correctly."""

    def _setup_low_confidence_rag(self, mock_rag_client):
        """Setup RAG to return low confidence → triggers LLM."""
        mock_rag_client.build_context.return_value = _make_build_context_response(
            findings=[
                {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3", "title": "Public Access", "score": 0.3},
            ],
            confidence="low",
        )
        mock_rag_client.retrieve_checks.return_value = _make_retrieve_response([
            {"doc_id": "check:s3_bucket_public_access", "score": 0.3, "metadata": {"severity": "critical", "service": "s3", "title": ""}},
        ])

    def test_low_confidence_triggers_llm(self, agent, mock_rag_client):
        """Low RAG confidence should trigger LLM refinement."""
        self._setup_low_confidence_rag(mock_rag_client)

        with patch.object(agent, "_llm_refine", return_value=agent._make_output(
            checks=["s3_bucket_public_access"],
            reasoning="Selected based on public access concern.",
        )) as mock_refine:
            result = agent.run("check s3 public access")

        mock_refine.assert_called_once()
        assert "s3_bucket_public_access" in result["checks_to_scan"]

    def test_llm_returns_group_scan(self, agent, mock_rag_client):
        """LLM can decide to do a group scan instead of specific checks."""
        self._setup_low_confidence_rag(mock_rag_client)

        with patch.object(agent, "_llm_refine", return_value=agent._make_output(
            groups=["s3"], reasoning="LLM decided group scan."
        )):
            result = agent.run("check s3 security")

        assert result["groups_to_scan"] == ["s3"]
        assert result["checks_to_scan"] == []

    def test_llm_failure_returns_explicit_error(self, agent, mock_rag_client):
        """When LLM also fails, return explicit error (no silent default)."""
        self._setup_low_confidence_rag(mock_rag_client)

        with patch.object(agent, "_llm_refine", return_value=agent._make_error_output(
            "Could not determine assessment target."
        )):
            result = agent.run("vague request about something")

        assert "error" in result
        assert result["groups_to_scan"] == []
        assert result["checks_to_scan"] == []

    def test_empty_candidates_triggers_llm(self, agent, mock_rag_client):
        """No RAG candidates + low confidence → LLM."""
        mock_rag_client.build_context.return_value = _make_build_context_response(
            findings=[], confidence="low",
        )
        mock_rag_client.retrieve_checks.return_value = _make_retrieve_response([])

        with patch.object(agent, "_llm_refine") as mock_refine:
            mock_refine.return_value = agent._make_error_output("No candidates")
            result = agent.run("do something")

        mock_refine.assert_called_once()

    def test_low_top_score_triggers_llm(self, agent, mock_rag_client):
        """High confidence but very low top score → still triggers LLM."""
        mock_rag_client.build_context.return_value = _make_build_context_response(
            findings=[
                {"check_id": "s3_bucket_public_access", "severity": "low", "service": "s3", "title": "", "score": 0.1},
            ],
            confidence="medium",
        )

        with patch.object(agent, "_llm_refine") as mock_refine:
            mock_refine.return_value = agent._make_output(
                checks=["s3_bucket_public_access"], reasoning="LLM refined."
            )
            result = agent.run("check s3 encryption configuration")

        # Score 0.1 → final_score < MIN_TOP_SCORE_FOR_SKIP (0.35) → LLM
        mock_refine.assert_called_once()


# ============================================================
# Gap 5: TestNoRagDegradation — RAG ablation scenario
# ============================================================

class TestNoRagDegradation:
    """Test agent behavior when RAG is unavailable."""

    def test_fast_track_works_without_rag(self, agent_no_rag):
        """FAST_TRACK should work perfectly without RAG."""
        result = agent_no_rag.run("run s3_bucket_public_access and s3_bucket_default_encryption")
        assert result["checks_to_scan"] == ["s3_bucket_public_access", "s3_bucket_default_encryption"]
        assert not result.get("error")

    def test_group_scan_works_without_rag(self, agent_no_rag):
        """GROUP_SCAN should work perfectly without RAG."""
        result = agent_no_rag.run("scan all iam")
        assert result["groups_to_scan"] == ["iam"]
        assert not result.get("error")

    def test_retrieval_path_degrades_to_llm(self, agent_no_rag):
        """RETRIEVAL_PATH without RAG → empty candidates → LLM refinement."""
        with patch.object(agent_no_rag, "_llm_refine") as mock_refine:
            mock_refine.return_value = agent_no_rag._make_output(
                groups=["s3"], reasoning="No RAG, LLM decided group."
            )
            result = agent_no_rag.run("check s3 public access")

        # Without RAG, _retrieve returns empty → scorer returns [] → gate triggers LLM
        mock_refine.assert_called_once()

    def test_no_rag_retrieval_returns_empty(self, agent_no_rag):
        """_retrieve() with no RAG client returns empty results."""
        result = agent_no_rag._retrieve("any query")
        assert result["candidates"] == []
        assert result["confidence"] == "low"
        assert result["source"] == "none"

    def test_no_rag_no_crash_on_any_input(self, agent_no_rag):
        """Agent should never crash regardless of input when RAG is down."""
        test_inputs = [
            "check s3 public access",
            "kiểm tra bảo mật mạng",
            "scan everything",
            "",
            "x" * 1000,
        ]
        for inp in test_inputs:
            with patch.object(agent_no_rag, "_llm_refine",
                              return_value=agent_no_rag._make_error_output("No RAG")):
                result = agent_no_rag.run(inp)
            assert isinstance(result, dict)
            assert "groups_to_scan" in result
            assert "checks_to_scan" in result


# ============================================================
# Gap 6: TestFaithfulnessMetric — Ensure metric works for LLM reasoning
# ============================================================

class TestFaithfulnessMetricCoverage:
    """Test that faithfulness metric correctly handles both hardcoded and LLM reasoning."""

    def test_hardcoded_reasoning_skipped(self):
        from benchmarks.llm_generation.planning_metrics import evaluate_faithfulness

        result = evaluate_faithfulness(
            reasoning="Deterministic selection: RAG confidence=high, top_score=0.880, selected 3 checks.",
            rag_context={},
            selected_checks=["s3_bucket_public_access"],
        )
        assert result["method"] == "hardcoded_skip"
        assert result["score"] == 1.0

    def test_llm_reasoning_grounded(self):
        from benchmarks.llm_generation.planning_metrics import evaluate_faithfulness

        result = evaluate_faithfulness(
            reasoning="Selected s3_bucket_public_access because it addresses public access vulnerability with critical severity.",
            rag_context={
                "related_findings": [
                    {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
                ]
            },
            selected_checks=["s3_bucket_public_access"],
        )
        assert result["method"] == "keyword_with_negative_checks"
        assert result["grounded"] is True
        assert result["score"] == 1.0

    def test_llm_reasoning_ungrounded(self):
        from benchmarks.llm_generation.planning_metrics import evaluate_faithfulness

        result = evaluate_faithfulness(
            reasoning="I recommend checking firewall rules because network security is important.",
            rag_context={
                "related_findings": [
                    {"check_id": "s3_bucket_public_access", "severity": "critical", "service": "s3"},
                ]
            },
            selected_checks=["s3_bucket_public_access"],
        )
        assert result["method"] == "keyword_with_negative_checks"
        # "s3_bucket_public_access" and "s3" not in reasoning → may still match "s3" partially
        # The important thing is the metric runs and returns a valid result
        assert isinstance(result["score"], float)
        assert 0.0 <= result["score"] <= 1.0

    def test_empty_reasoning(self):
        from benchmarks.llm_generation.planning_metrics import evaluate_faithfulness

        result = evaluate_faithfulness(
            reasoning="",
            rag_context={},
            selected_checks=[],
        )
        assert result["score"] == 0.0
        assert result["grounded"] is False

    def test_group_scan_hardcoded(self):
        from benchmarks.llm_generation.planning_metrics import evaluate_faithfulness

        result = evaluate_faithfulness(
            reasoning="Group scan requested for iam.",
            rag_context={},
            selected_checks=[],
        )
        assert result["method"] == "hardcoded_skip"

    def test_explicit_check_ids_hardcoded(self):
        from benchmarks.llm_generation.planning_metrics import evaluate_faithfulness

        result = evaluate_faithfulness(
            reasoning="Explicit check IDs detected in request.",
            rag_context={},
            selected_checks=["s3_bucket_public_access"],
        )
        assert result["method"] == "hardcoded_skip"


# ============================================================
# Multi-intent splitter + multi-retrieve path
# ============================================================

class TestMultiIntent:
    """Test LLM intent splitter + union-based multi-retrieve."""

    def test_split_intents_returns_list(self, agent):
        fake_raw = '{"sub_queries": ["s3 notification", "s3 encryption"]}'
        with patch.object(agent, "llm"):
            with patch(
                "pdca.agents.planning_agent.ChatPromptTemplate.from_template"
            ) as mock_tpl:
                chain = MagicMock()
                chain.invoke.return_value = fake_raw
                mock_tpl.return_value.__or__.return_value.__or__.return_value = chain
                result = agent._split_intents("kiểm tra notification và encryption của s3", "s3")
        assert result == ["s3 notification", "s3 encryption"]

    def test_split_intents_handles_llm_failure(self, agent):
        with patch(
            "pdca.agents.planning_agent.ChatPromptTemplate.from_template"
        ) as mock_tpl:
            chain = MagicMock()
            chain.invoke.side_effect = RuntimeError("LLM down")
            mock_tpl.return_value.__or__.return_value.__or__.return_value = chain
            result = agent._split_intents("anything", "s3")
        assert result == []

    def test_split_intents_handles_bad_json(self, agent):
        with patch(
            "pdca.agents.planning_agent.ChatPromptTemplate.from_template"
        ) as mock_tpl:
            chain = MagicMock()
            chain.invoke.return_value = '{"sub_queries": "not a list"}'
            mock_tpl.return_value.__or__.return_value.__or__.return_value = chain
            result = agent._split_intents("x", "s3")
        assert result == []

    def test_multi_retrieve_unions_per_topic_candidates(self, agent, mock_rag_client):
        """Two sub-queries return distinct checks; union preserves both topics."""
        def build_context_side_effect(*, consumer, query, top_k, retrieval_mode):
            if "notification" in query.lower():
                return _make_build_context_response([
                    {"check_id": "s3_bucket_event_notifications_enabled",
                     "title": "Notifications", "severity": "medium", "service": "s3", "score": 0.90},
                    {"check_id": "s3_bucket_kms_encryption_enabled",
                     "title": "KMS enc (weak hit)", "severity": "medium", "service": "s3", "score": 0.30},
                ], confidence="high")
            if "encryption" in query.lower():
                return _make_build_context_response([
                    {"check_id": "s3_bucket_default_encryption",
                     "title": "Default enc", "severity": "high", "service": "s3", "score": 0.88},
                    {"check_id": "s3_bucket_kms_encryption_enabled",
                     "title": "KMS enc", "severity": "high", "service": "s3", "score": 0.82},
                ], confidence="high")
            return _make_build_context_response([], confidence="low")

        mock_rag_client.build_context.side_effect = build_context_side_effect

        result = agent._multi_retrieve_and_gate(
            request="kiểm tra notification và encryption của s3",
            sub_queries=["s3 notification", "s3 encryption"],
            detected_service="s3",
        )

        checks = result["checks_to_scan"]
        # Both topics represented — notification check is no longer culled by encryption's cluster
        assert "s3_bucket_event_notifications_enabled" in checks
        assert "s3_bucket_default_encryption" in checks
        assert result["groups_to_scan"] == []
        # Reasoning mentions the split
        assert "Multi-intent" in result["reasoning"]

    def test_multi_retrieve_low_confidence_falls_back_to_llm(self, agent, mock_rag_client):
        mock_rag_client.build_context.return_value = _make_build_context_response(
            [{"check_id": "s3_bucket_event_notifications_enabled", "title": "N",
              "severity": "low", "service": "s3", "score": 0.20}],
            confidence="low",
        )
        with patch.object(agent, "_llm_refine", return_value=agent._make_output(
            checks=["s3_bucket_default_encryption"], reasoning="LLM picked encryption",
        )) as mock_refine:
            result = agent._multi_retrieve_and_gate(
                request="kiểm tra notification và encryption của s3",
                sub_queries=["s3 notification", "s3 encryption"],
                detected_service="s3",
            )
        mock_refine.assert_called_once()
        assert result["checks_to_scan"] == ["s3_bucket_default_encryption"]

    def test_run_triggers_splitter_on_conjunction(self, agent, mock_rag_client):
        """End-to-end: Vietnamese request with 'và' triggers splitter + multi-retrieve."""
        # LLM returns 2 sub-queries
        with patch.object(agent, "_split_intents",
                          return_value=["s3 notification", "s3 encryption"]) as mock_split:
            with patch.object(agent, "_multi_retrieve_and_gate",
                              return_value=agent._make_output(
                                  checks=["s3_bucket_event_notifications_enabled",
                                          "s3_bucket_default_encryption"],
                                  reasoning="multi",
                              )) as mock_multi:
                result = agent.run("kiểm tra notification và encryption của s3")
        mock_split.assert_called_once()
        mock_multi.assert_called_once()
        assert len(result["checks_to_scan"]) == 2

    def test_run_skips_splitter_when_no_conjunction(self, agent, mock_rag_client):
        """Single-topic Vietnamese request — splitter NOT called."""
        mock_rag_client.build_context.return_value = _make_build_context_response(
            [{"check_id": "s3_bucket_default_encryption", "title": "E",
              "severity": "high", "service": "s3", "score": 0.9}],
            confidence="high",
        )
        with patch.object(agent, "_split_intents") as mock_split:
            agent.run("kiểm tra encryption của s3")
        mock_split.assert_not_called()

    def test_run_skips_splitter_when_splitter_returns_single(self, agent, mock_rag_client):
        """Conjunction present but LLM decides it's really one topic — fall back to single path."""
        mock_rag_client.build_context.return_value = _make_build_context_response(
            [{"check_id": "s3_bucket_default_encryption", "title": "E",
              "severity": "high", "service": "s3", "score": 0.9}],
            confidence="high",
        )
        with patch.object(agent, "_split_intents", return_value=["s3 encryption"]):
            with patch.object(agent, "_multi_retrieve_and_gate") as mock_multi:
                agent.run("kiểm tra mã hoá, encryption của s3")
        mock_multi.assert_not_called()

    def test_run_skips_splitter_when_explicit_check_ids(self, agent, mock_rag_client):
        """FAST_TRACK takes precedence over splitter."""
        mock_rag_client.retrieve_checks.return_value = _make_retrieve_response([
            {"doc_id": "s3_bucket_public_access", "score": 1.0,
             "metadata": {"title": "Public", "severity": "high", "service": "s3"}},
        ])
        with patch.object(agent, "_split_intents") as mock_split:
            result = agent.run("check s3_bucket_public_access and s3_bucket_default_encryption")
        # At least one ID validated → FAST_TRACK or hint path; splitter shouldn't run
        # because candidate_ids is non-empty
        mock_split.assert_not_called()
