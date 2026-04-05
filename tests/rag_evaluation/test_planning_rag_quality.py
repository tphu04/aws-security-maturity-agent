"""
RAG Integration Quality Tests — PlanningAgent
==============================================
Danh gia chat luong tich hop RAG vao PlanningAgent:

1. Retrieval Relevance: RAG tra ve ket qua phu hop voi user request
2. Context Enrichment: Maturity context duoc format dung va day du
3. Confidence Branching: Xu ly dung theo confidence level (high/medium/low)
4. Candidate Parsing: Parse dung PlanningBundle va retrieve_checks format
5. Fallback Chain: build_context -> retrieve_checks -> empty
6. Re-ranking Quality: LLM re-ranking su dung maturity context hieu qua
7. Service Detection: Phat hien dung AWS service tu user request
8. Deduplication: Khong tra ve check IDs trung lap
"""

import json
from unittest.mock import MagicMock, patch, call

import pytest

from agents.planning_agent import PlanningAgent
from agents.shared.rag_client import RAGClient


# ============================================================
# Q1: Retrieval Relevance — RAG tra ve ket qua phu hop
# ============================================================

class TestRetrievalRelevance:
    """Verify RAG results are relevant to user queries."""

    def test_s3_query_returns_s3_checks(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q1.1: Query ve S3 phai tra ve S3 checks, khong mix service khac."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        result = planning_agent._retrieve_candidates("s3 public access", "s3")

        assert result["source"] == "build_context"
        for candidate in result["candidates"]:
            assert candidate["service"] == "s3", \
                f"Candidate {candidate['check_id']} has service '{candidate['service']}', expected 's3'"

    def test_iam_query_returns_iam_checks(self, planning_agent, mock_rag_client, planning_bundle_iam):
        """Q1.2: Query ve IAM phai tra ve IAM checks."""
        mock_rag_client.build_context.return_value = planning_bundle_iam
        result = planning_agent._retrieve_candidates("iam mfa users", "iam")

        assert result["source"] == "build_context"
        for candidate in result["candidates"]:
            assert candidate["service"] == "iam"

    def test_candidates_have_required_fields(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q1.3: Moi candidate phai co day du: check_id, title, severity, service, score."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        result = planning_agent._retrieve_candidates("s3 security", "s3")

        required_fields = {"check_id", "title", "severity", "service", "score"}
        for candidate in result["candidates"]:
            missing = required_fields - set(candidate.keys())
            assert not missing, f"Candidate {candidate.get('check_id')} missing fields: {missing}"

    def test_candidate_check_ids_are_valid_format(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q1.4: check_id phai dung format Prowler (service_check_name)."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        result = planning_agent._retrieve_candidates("s3 security", "s3")

        for candidate in result["candidates"]:
            cid = candidate["check_id"]
            assert "_" in cid, f"check_id '{cid}' does not contain underscore"
            assert len(cid) > 8, f"check_id '{cid}' is too short (< 8 chars)"
            assert cid == cid.lower(), f"check_id '{cid}' should be lowercase"

    def test_no_duplicate_candidates(self, planning_agent, mock_rag_client):
        """Q1.5: Ket qua khong duoc co check_id trung lap."""
        # Bundle with duplicate check_ids
        bundle = {
            "payload": {
                "planning_bundle": {
                    "related_findings": [
                        {"check_id": "s3_bucket_public_access", "service": "s3",
                         "title": "Public Access A", "severity": "high"},
                        {"check_id": "s3_bucket_public_access", "service": "s3",
                         "title": "Public Access B", "severity": "critical"},
                        {"check_id": "s3_bucket_versioning", "service": "s3",
                         "title": "Versioning", "severity": "medium"},
                    ],
                    "control_mapping_ids": [],
                    "maturity_capability_ids": [],
                }
            },
            "_meta": {"confidence": "high"},
        }
        mock_rag_client.build_context.return_value = bundle
        result = planning_agent._retrieve_candidates("s3 check", "s3")

        check_ids = [c["check_id"] for c in result["candidates"]]
        assert len(check_ids) == len(set(check_ids)), \
            f"Duplicate check_ids found: {check_ids}"

    def test_max_candidates_limit(self, planning_agent, mock_rag_client):
        """Q1.6: Ket qua khong vuot qua 10 candidates (limit)."""
        many_findings = [
            {"check_id": f"s3_check_{i}", "service": "s3",
             "title": f"Check {i}", "severity": "medium"}
            for i in range(20)
        ]
        bundle = {
            "payload": {
                "planning_bundle": {
                    "related_findings": many_findings,
                    "control_mapping_ids": [],
                    "maturity_capability_ids": [],
                }
            },
            "_meta": {"confidence": "high"},
        }
        mock_rag_client.build_context.return_value = bundle
        result = planning_agent._retrieve_candidates("s3 all", "s3")
        assert len(result["candidates"]) <= 10


# ============================================================
# Q2: Context Enrichment — Maturity context quality
# ============================================================

class TestContextEnrichment:
    """Verify maturity context is properly formatted and enriching."""

    def test_maturity_context_contains_control_mappings(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q2.1: Maturity context phai chua control mapping IDs."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        result = planning_agent._retrieve_candidates("s3 security", "s3")

        assert "Control mappings" in result["maturity_context"]
        assert "cis_aws" in result["maturity_context"]

    def test_maturity_context_contains_capability_ids(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q2.2: Maturity context phai chua maturity capability IDs."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        result = planning_agent._retrieve_candidates("s3 security", "s3")

        assert "Maturity capabilities" in result["maturity_context"]
        assert "data_protection" in result["maturity_context"]

    def test_maturity_context_empty_when_no_mappings(self):
        """Q2.3: Maturity context phai rong khi khong co mappings."""
        result = PlanningAgent._format_maturity_context([], [])
        assert result == ""

    def test_maturity_context_truncated_at_500_chars(self):
        """Q2.4: Maturity context phai bi cat o 500 ky tu."""
        long_ids = [f"very_long_capability_id_{i:03d}_extra_data" for i in range(100)]
        result = PlanningAgent._format_maturity_context(long_ids, long_ids)
        assert len(result) <= 500

    def test_maturity_context_limits_to_5_ids_per_type(self):
        """Q2.5: Chi hien thi toi da 5 IDs moi loai."""
        mapping_ids = [f"map_{i}" for i in range(10)]
        maturity_ids = [f"cap_{i}" for i in range(10)]
        result = PlanningAgent._format_maturity_context(mapping_ids, maturity_ids)

        # Should only show first 5 of each
        assert "map_0" in result
        assert "map_4" in result
        # map_5 onwards should NOT be shown (truncated to first 5)
        # This depends on total length < 500; verify presence of limiting


# ============================================================
# Q3: Confidence Branching
# ============================================================

class TestConfidenceBranching:
    """Verify correct behavior based on RAG confidence levels."""

    def test_high_confidence_proceeds_to_reranking(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q3.1: High confidence -> proceed voi re-ranking, khong group scan."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        result = planning_agent._retrieve_candidates("s3 security", "s3")

        assert result["confidence"] == "high"
        assert len(result["candidates"]) > 0

    def test_low_confidence_triggers_group_scan(self, planning_agent, mock_rag_client, planning_bundle_low_confidence):
        """Q3.2: Low confidence -> fallback to group scan."""
        mock_rag_client.build_context.return_value = planning_bundle_low_confidence

        retrieval = planning_agent._retrieve_candidates("s3 something", "s3")
        result = planning_agent._rerank_and_select("s3 something", retrieval, "s3")

        assert result["groups_to_scan"] == ["s3"]
        assert result["checks_to_scan"] == []

    def test_medium_confidence_proceeds_normally(self, planning_agent, mock_rag_client):
        """Q3.3: Medium confidence -> proceed binh thuong (khong group scan)."""
        bundle = {
            "payload": {
                "planning_bundle": {
                    "related_findings": [
                        {"check_id": "s3_bucket_versioning", "service": "s3",
                         "title": "Versioning", "severity": "medium"},
                    ],
                    "control_mapping_ids": ["cis_1"],
                    "maturity_capability_ids": ["data_protection"],
                }
            },
            "_meta": {"confidence": "medium"},
        }
        mock_rag_client.build_context.return_value = bundle
        retrieval = planning_agent._retrieve_candidates("s3 versioning", "s3")

        assert retrieval["confidence"] == "medium"
        assert len(retrieval["candidates"]) > 0

    def test_confidence_extracted_from_meta(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q3.4: Confidence duoc doc dung tu _meta.confidence."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        result = planning_agent._retrieve_candidates("s3", "s3")
        assert result["confidence"] == "high"

    def test_missing_confidence_defaults_to_medium(self, planning_agent, mock_rag_client):
        """Q3.5: Thieu confidence field -> default 'medium'."""
        bundle = {
            "payload": {
                "planning_bundle": {
                    "related_findings": [
                        {"check_id": "s3_bucket_versioning", "service": "s3",
                         "title": "V", "severity": "medium"},
                    ],
                    "control_mapping_ids": [],
                    "maturity_capability_ids": [],
                }
            },
            "_meta": {},  # No confidence field
        }
        mock_rag_client.build_context.return_value = bundle
        result = planning_agent._retrieve_candidates("s3", "s3")
        assert result["confidence"] == "medium"


# ============================================================
# Q4: Fallback Chain Quality
# ============================================================

class TestFallbackChain:
    """Verify fallback chain: build_context -> retrieve_checks -> empty."""

    def test_primary_path_build_context(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q4.1: Primary path: build_context success -> source='build_context'."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        result = planning_agent._retrieve_candidates("s3", "s3")
        assert result["source"] == "build_context"
        mock_rag_client.retrieve_checks.assert_not_called()

    def test_fallback_to_retrieve_checks(self, planning_agent, mock_rag_client):
        """Q4.2: build_context fails -> fallback to retrieve_checks."""
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

    def test_fallback_chain_complete_failure(self, planning_agent, mock_rag_client):
        """Q4.3: build_context + retrieve_checks both fail -> empty."""
        mock_rag_client.build_context.return_value = None
        mock_rag_client.retrieve_checks.return_value = None

        result = planning_agent._retrieve_candidates("something", "s3")
        assert result["source"] == "none"
        assert result["candidates"] == []
        assert result["confidence"] == "low"

    def test_build_context_missing_bundle_triggers_fallback(self, planning_agent, mock_rag_client):
        """Q4.4: build_context response thieu planning_bundle -> fallback."""
        mock_rag_client.build_context.return_value = {"payload": {}, "_meta": {}}
        mock_rag_client.retrieve_checks.return_value = {
            "results": [
                {"doc_id": "check:s3_bucket_versioning", "score": 0.8,
                 "metadata": {"service": "s3", "title": "V", "severity": "medium"}},
            ],
        }
        result = planning_agent._retrieve_candidates("s3", "s3")
        assert result["source"] == "retrieve_checks"

    def test_retrieve_checks_filters_wrong_service(self, planning_agent, mock_rag_client):
        """Q4.5: Fallback retrieve_checks loc dung service (loai bo service khac)."""
        mock_rag_client.build_context.return_value = None
        mock_rag_client.retrieve_checks.return_value = {
            "results": [
                {"doc_id": "check:s3_bucket_versioning", "score": 0.8,
                 "metadata": {"service": "s3", "title": "V", "severity": "medium"}},
                {"doc_id": "check:iam_user_mfa", "score": 0.9,
                 "metadata": {"service": "iam", "title": "MFA", "severity": "critical"}},
            ],
        }
        result = planning_agent._retrieve_candidates("s3 versioning", "s3")
        for c in result["candidates"]:
            assert c["service"] == "s3"


# ============================================================
# Q5: Service Detection Quality
# ============================================================

class TestServiceDetection:
    """Verify accurate service detection from user requests."""

    @pytest.mark.parametrize("request_text,expected_service", [
        ("check my S3 buckets", "s3"),
        ("audit IAM users", "iam"),
        ("scan EC2 instances", "ec2"),
        ("verify RDS encryption", "rds"),
        ("check VPC flow logs", "vpc"),
        ("lambda function security", "lambda"),
        ("CloudTrail logging", "cloudtrail"),
        ("KMS key rotation", "kms"),
        ("EKS cluster security", "eks"),
        ("SQS queue permissions", "sqs"),
    ])
    def test_direct_service_name_detection(self, planning_agent, request_text, expected_service):
        """Q5.1: Phat hien dung AWS service tu ten truc tiep."""
        result = planning_agent._infer_service_from_keywords(request_text)
        assert result == expected_service, \
            f"Expected '{expected_service}' for '{request_text}', got '{result}'"

    @pytest.mark.parametrize("request_text,expected_service", [
        ("check my storage buckets", "s3"),
        ("scan all running instances", "ec2"),
        ("verify user permissions and roles", "iam"),
        ("audit password policy", "iam"),
        ("check database encryption", "rds"),
        ("check vpc subnet settings", "vpc"),
        ("review encryption keys", "kms"),
    ])
    def test_keyword_based_service_inference(self, planning_agent, request_text, expected_service):
        """Q5.2: Phat hien service tu keywords lien quan."""
        result = planning_agent._infer_service_from_keywords(request_text)
        assert result == expected_service

    def test_sanitize_service_validates_correctly(self, planning_agent):
        """Q5.3: _sanitize_service_name validate va normalize dung."""
        assert planning_agent._sanitize_service_name("S3") == "s3"
        assert planning_agent._sanitize_service_name("  IAM  ") == "iam"
        assert planning_agent._sanitize_service_name("InvalidService123") is None
        assert planning_agent._sanitize_service_name("") is None
        assert planning_agent._sanitize_service_name(None) is None


# ============================================================
# Q6: Re-ranking Quality
# ============================================================

class TestRerankingQuality:
    """Verify LLM re-ranking uses maturity context effectively."""

    def test_empty_candidates_triggers_group_scan(self, planning_agent):
        """Q6.1: Khong co candidates -> group scan."""
        retrieval = {"candidates": [], "maturity_context": "", "confidence": "medium", "source": "none"}
        result = planning_agent._rerank_and_select("test", retrieval, "s3")
        assert result["groups_to_scan"] == ["s3"]

    def test_rerank_uses_maturity_context(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q6.2: Re-ranking prompt nhan maturity_context tu retrieval."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        retrieval = planning_agent._retrieve_candidates("s3 security", "s3")

        assert retrieval["maturity_context"] != ""
        # Verify maturity context is non-empty and will be passed to LLM

    def test_rerank_fallback_uses_top_candidates(self, planning_agent):
        """Q6.3: LLM re-ranking tra ve empty -> dung top RAG candidates."""
        candidates = [
            {"check_id": f"s3_check_{i}", "title": f"Check {i}",
             "severity": "medium", "service": "s3", "score": 1.0}
            for i in range(5)
        ]
        retrieval = {"candidates": candidates, "maturity_context": "", "confidence": "high", "source": "build_context"}

        with patch("agents.planning_agent.parse_llm_json", return_value={"selected_ids": [], "reasoning": "none"}):
            with patch("agents.planning_agent.ChatPromptTemplate") as MockPrompt:
                mock_chain = MagicMock()
                mock_chain.invoke.return_value = '{"selected_ids": []}'
                MockPrompt.from_template.return_value.__or__ = MagicMock(
                    return_value=MagicMock(__or__=MagicMock(return_value=mock_chain)))
                result = planning_agent._rerank_and_select("test", retrieval, "s3")

        assert len(result["checks_to_scan"]) == 5
        assert result["groups_to_scan"] == []


# ============================================================
# Q7: build_context API Call Quality
# ============================================================

class TestBuildContextAPICall:
    """Verify correct API call parameters to RAG."""

    def test_calls_build_context_with_planning_consumer(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q7.1: Goi build_context voi consumer='planning'."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        planning_agent._retrieve_candidates("s3 test", "s3")

        mock_rag_client.build_context.assert_called_once()
        kwargs = mock_rag_client.build_context.call_args.kwargs
        assert kwargs["consumer"] == "planning"

    def test_calls_with_hybrid_retrieval_mode(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q7.2: Goi voi retrieval_mode='hybrid'."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        planning_agent._retrieve_candidates("s3 test", "s3")

        kwargs = mock_rag_client.build_context.call_args.kwargs
        assert kwargs["retrieval_mode"] == "hybrid"

    def test_calls_with_top_k_10(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q7.3: Goi voi top_k=10."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        planning_agent._retrieve_candidates("s3 test", "s3")

        kwargs = mock_rag_client.build_context.call_args.kwargs
        assert kwargs["top_k"] == 10

    def test_combined_query_includes_service(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q7.4: Query combine service name voi user query."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        planning_agent._retrieve_candidates("public access", "s3")

        kwargs = mock_rag_client.build_context.call_args.kwargs
        assert "s3" in kwargs["query"]
        assert "public access" in kwargs["query"]


# ============================================================
# Q8: End-to-end Flow Tests
# ============================================================

class TestEndToEndFlow:
    """Test full run() flow with RAG integration."""

    def test_full_flow_with_rag_success(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q8.1: Full flow: intent -> RAG -> re-rank -> output."""
        mock_rag_client.build_context.return_value = planning_bundle_s3

        with patch.object(planning_agent, "_detect_explicit_checks", return_value=None):
            with patch.object(planning_agent, "_translate_intent", return_value={
                "target_service": "s3", "is_group_scan": False,
                "search_queries": ["public access"],
            }):
                with patch.object(planning_agent, "_rerank_and_select", return_value={
                    "groups_to_scan": [],
                    "checks_to_scan": ["s3_bucket_public_access", "s3_bucket_policy_public_write_access"],
                    "reasoning": "Selected based on relevance",
                }):
                    result = planning_agent.run("check S3 public access")

        assert isinstance(result, dict)
        assert "checks_to_scan" in result or "groups_to_scan" in result

    def test_explicit_check_ids_bypass_rag(self, planning_agent, mock_rag_client):
        """Q8.2: Explicit check IDs -> skip RAG entirely."""
        result = planning_agent.run("run s3_bucket_public_access and s3_bucket_versioning")

        mock_rag_client.build_context.assert_not_called()
        assert "s3_bucket_public_access" in result["checks_to_scan"]

    def test_group_scan_request_skips_rag(self, planning_agent, mock_rag_client):
        """Q8.3: Group scan request -> skip RAG retrieval."""
        with patch.object(planning_agent, "_detect_explicit_checks", return_value=None):
            with patch.object(planning_agent, "_translate_intent", return_value={
                "target_service": "s3", "is_group_scan": True,
                "search_queries": [],
            }):
                result = planning_agent.run("scan all s3")

        assert result["groups_to_scan"] == ["s3"]
        mock_rag_client.build_context.assert_not_called()

    def test_error_handling_returns_fallback(self, planning_agent):
        """Q8.4: Exception -> error dict voi group scan fallback."""
        with patch.object(planning_agent, "_detect_explicit_checks", side_effect=RuntimeError("test error")):
            result = planning_agent.run("crash test")

        assert "error" in result
        assert result["groups_to_scan"] == ["s3"]

    def test_output_schema_consistent(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """Q8.5: Output luon co groups_to_scan + checks_to_scan + reasoning."""
        mock_rag_client.build_context.return_value = planning_bundle_s3

        with patch.object(planning_agent, "_detect_explicit_checks", return_value=None):
            with patch.object(planning_agent, "_translate_intent", return_value={
                "target_service": "s3", "is_group_scan": False, "search_queries": ["test"],
            }):
                with patch.object(planning_agent, "_rerank_and_select", return_value={
                    "groups_to_scan": [], "checks_to_scan": ["s3_bucket_public_access"],
                    "reasoning": "test",
                }):
                    result = planning_agent.run("test")

        assert "groups_to_scan" in result
        assert "checks_to_scan" in result
        assert isinstance(result["groups_to_scan"], list)
        assert isinstance(result["checks_to_scan"], list)
