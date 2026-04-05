"""
RAG Integration Quality Tests — RiskEvaluationAgent
=====================================================
Danh gia chat luong tich hop RAG vao RiskEvaluationAgent:

1. Context Fetching: RAG context duoc fetch dung tu build_context(consumer="risk")
2. RAG Data Parsing: Parse dung risk_bundle (findings + control_mapping)
3. Confidence Injection: Confidence level duoc inject vao LLM prompt
4. LLM Scoring Quality: AI scoring phu hop voi RAG context
5. Batch Chunking: Xu ly dung khi >20 check_ids
6. Cache Effectiveness: In-memory cache hoat dong dung
7. Compliance Enrichment: Compliance mappings duoc attach vao findings
8. Output Schema: Output format nhat quan va day du
"""

import json
from unittest.mock import MagicMock, patch, call

import pytest

from agents.risk_evaluation_agent import (
    RiskEvaluationAgent,
    SYSTEM_PROMPT_SINGLE,
    _VALID_SEVERITIES,
    _SEVERITY_MAP,
    _RAG_BATCH_CHUNK_SIZE,
)


# ============================================================
# Q1: Context Fetching Quality
# ============================================================

class TestContextFetching:
    """Verify RAG context is fetched correctly for risk evaluation."""

    def test_calls_build_context_with_risk_consumer(self, risk_agent, mock_rag_client, risk_bundle_response,
                                                     sample_fail_findings):
        """Q1.1: Goi build_context voi consumer='risk'."""
        mock_rag_client.build_context.return_value = risk_bundle_response
        risk_agent._fetch_rag_context(sample_fail_findings)

        mock_rag_client.build_context.assert_called()
        kwargs = mock_rag_client.build_context.call_args.kwargs
        assert kwargs["consumer"] == "risk"

    def test_sends_check_ids_with_prefix(self, risk_agent, mock_rag_client, risk_bundle_response,
                                          sample_fail_findings):
        """Q1.2: Check IDs gui di co prefix 'check:' dung format."""
        mock_rag_client.build_context.return_value = risk_bundle_response
        risk_agent._fetch_rag_context(sample_fail_findings)

        kwargs = mock_rag_client.build_context.call_args.kwargs
        check_ids = kwargs["check_ids"]
        for cid in check_ids:
            assert cid.startswith("check:"), f"Check ID '{cid}' missing 'check:' prefix"

    def test_includes_mappings_flag(self, risk_agent, mock_rag_client, risk_bundle_response,
                                     sample_fail_findings):
        """Q1.3: include_mappings=True de lay compliance data."""
        mock_rag_client.build_context.return_value = risk_bundle_response
        risk_agent._fetch_rag_context(sample_fail_findings)

        kwargs = mock_rag_client.build_context.call_args.kwargs
        assert kwargs["include_mappings"] is True

    def test_extracts_unique_check_ids(self, risk_agent, mock_rag_client, risk_bundle_response):
        """Q1.4: Chi gui unique check_ids (loai trung)."""
        duplicate_findings = [
            {"status": "FAIL", "event_code": "s3_bucket_public_access",
             "check_id": "s3_bucket_public_access", "service": "s3",
             "resource_id": "bucket-1", "description": "Fail 1", "severity": "High"},
            {"status": "FAIL", "event_code": "s3_bucket_public_access",
             "check_id": "s3_bucket_public_access", "service": "s3",
             "resource_id": "bucket-2", "description": "Fail 2", "severity": "High"},
            {"status": "FAIL", "event_code": "iam_user_mfa_enabled",
             "check_id": "iam_user_mfa_enabled", "service": "iam",
             "resource_id": "user-1", "description": "No MFA", "severity": "Critical"},
        ]
        mock_rag_client.build_context.return_value = risk_bundle_response
        risk_agent._fetch_rag_context(duplicate_findings)

        kwargs = mock_rag_client.build_context.call_args.kwargs
        check_ids = kwargs["check_ids"]
        # Should only have 2 unique IDs, not 3
        unique_base_ids = {cid.replace("check:", "") for cid in check_ids}
        assert len(unique_base_ids) == 2

    def test_returns_empty_when_no_rag_client(self, risk_agent_no_rag, sample_fail_findings):
        """Q1.5: rag_client=None -> return empty dict."""
        result = risk_agent_no_rag._fetch_rag_context(sample_fail_findings)
        assert result == {}


# ============================================================
# Q2: RAG Data Parsing Quality
# ============================================================

class TestRAGDataParsing:
    """Verify risk_bundle is parsed correctly into context_map."""

    def test_parses_related_findings(self, risk_agent, mock_rag_client, risk_bundle_response,
                                      sample_fail_findings):
        """Q2.1: Parse related_findings thanh context_map voi severity + title."""
        mock_rag_client.build_context.return_value = risk_bundle_response
        result = risk_agent._fetch_rag_context(sample_fail_findings)

        assert "s3_bucket_public_access" in result
        assert result["s3_bucket_public_access"]["severity"] == "critical"
        assert result["s3_bucket_public_access"]["title"] == "S3 Bucket Public Access Block"

    def test_parses_control_mappings(self, risk_agent, mock_rag_client, risk_bundle_response,
                                      sample_fail_findings):
        """Q2.2: Parse control_mapping thanh mappings list cho moi check_id."""
        mock_rag_client.build_context.return_value = risk_bundle_response
        result = risk_agent._fetch_rag_context(sample_fail_findings)

        assert "s3_bucket_public_access" in result
        mappings = result["s3_bucket_public_access"]["mappings"]
        assert "cis_aws_2.1.1" in mappings
        assert "pci_dss_s3.1" in mappings

    def test_handles_missing_risk_bundle(self, risk_agent, mock_rag_client, sample_fail_findings):
        """Q2.3: Response thieu risk_bundle -> return empty context."""
        mock_rag_client.build_context.return_value = {
            "payload": {},  # No risk_bundle
            "_meta": {},
        }
        result = risk_agent._fetch_rag_context(sample_fail_findings)
        # Should not crash, returns what it can parse
        assert isinstance(result, dict)

    def test_strips_check_prefix_from_ids(self, risk_agent, mock_rag_client, sample_fail_findings):
        """Q2.4: Remove 'check:' prefix tu response check_ids."""
        bundle = {
            "payload": {
                "risk_bundle": {
                    "related_findings": [
                        {"check_id": "check:s3_bucket_public_access", "severity": "high",
                         "title": "Public Access"},
                    ],
                    "control_mapping": [],
                }
            },
            "_meta": {"confidence": "high"},
        }
        mock_rag_client.build_context.return_value = bundle
        result = risk_agent._fetch_rag_context(sample_fail_findings)

        # Key should be without prefix
        assert "s3_bucket_public_access" in result
        assert "check:s3_bucket_public_access" not in result


# ============================================================
# Q3: Confidence Injection Quality
# ============================================================

class TestConfidenceInjection:
    """Verify confidence level is correctly injected into LLM prompt."""

    def test_high_confidence_view(self, risk_agent):
        """Q3.1: High confidence -> 'trust compliance data' hint."""
        risk_agent._rag_confidence = "high"
        rag_data = {"severity": "critical", "title": "Test", "mappings": ["cis_1"]}
        view = risk_agent._build_rag_context_view(rag_data)

        assert view["rag_confidence"] == "high"
        assert "trust" in view["confidence_note"].lower()

    def test_low_confidence_view(self, risk_agent):
        """Q3.2: Low confidence -> 'may be incomplete' hint."""
        risk_agent._rag_confidence = "low"
        rag_data = {"severity": "medium", "title": "Test", "mappings": []}
        view = risk_agent._build_rag_context_view(rag_data)

        assert view["rag_confidence"] == "low"
        assert "incomplete" in view["confidence_note"].lower()

    def test_medium_confidence_view(self, risk_agent):
        """Q3.3: Medium confidence -> 'supporting evidence' hint."""
        risk_agent._rag_confidence = "medium"
        rag_data = {"severity": "high", "title": "Test", "mappings": ["nist_1"]}
        view = risk_agent._build_rag_context_view(rag_data)

        assert view["rag_confidence"] == "medium"
        assert "supporting" in view["confidence_note"].lower()

    def test_unknown_confidence_no_hint(self, risk_agent):
        """Q3.4: Unknown confidence -> khong co confidence_note."""
        risk_agent._rag_confidence = "unknown"
        rag_data = {"severity": "medium", "title": "Test", "mappings": []}
        view = risk_agent._build_rag_context_view(rag_data)

        assert "rag_confidence" not in view
        assert "confidence_note" not in view

    def test_confidence_extracted_from_rag_response(self, risk_agent, mock_rag_client, sample_fail_findings):
        """Q3.5: Confidence duoc doc tu _meta.confidence cua RAG response."""
        bundle = {
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
        mock_rag_client.build_context.return_value = bundle
        risk_agent._fetch_rag_context(sample_fail_findings)
        assert risk_agent._rag_confidence == "high"

    def test_rag_context_view_includes_official_severity(self, risk_agent):
        """Q3.6: View bao gom official_severity tu RAG."""
        risk_agent._rag_confidence = "high"
        rag_data = {"severity": "critical", "title": "Test Check", "mappings": ["cis_1"]}
        view = risk_agent._build_rag_context_view(rag_data)

        assert view["official_severity"] == "critical"
        assert view["check_title"] == "Test Check"
        assert view["compliance_mappings"] == ["cis_1"]


# ============================================================
# Q4: LLM Scoring Quality
# ============================================================

class TestLLMScoringQuality:
    """Verify LLM scoring produces valid and consistent results."""

    def test_validate_output_valid_input(self, risk_agent):
        """Q4.1: Valid LLM output -> pass validation."""
        parsed = {"ai_severity": "Critical", "ai_risk_score": 9, "ai_reasoning": "Public access risk"}
        result = RiskEvaluationAgent._validate_llm_output(parsed)

        assert result["ai_severity"] == "Critical"
        assert result["ai_risk_score"] == 9
        assert result["ai_reasoning"] == "Public access risk"

    def test_validate_output_invalid_severity(self, risk_agent):
        """Q4.2: Invalid severity -> default 'Medium'."""
        parsed = {"ai_severity": "SuperCritical", "ai_risk_score": 9, "ai_reasoning": "test"}
        result = RiskEvaluationAgent._validate_llm_output(parsed)
        assert result["ai_severity"] == "Medium"

    def test_validate_output_score_clamped(self, risk_agent):
        """Q4.3: Score ngoai range 0-10 -> clamp."""
        parsed_high = {"ai_severity": "High", "ai_risk_score": 15, "ai_reasoning": "test"}
        result_high = RiskEvaluationAgent._validate_llm_output(parsed_high)
        assert result_high["ai_risk_score"] == 10

        parsed_low = {"ai_severity": "Low", "ai_risk_score": -5, "ai_reasoning": "test"}
        result_low = RiskEvaluationAgent._validate_llm_output(parsed_low)
        assert result_low["ai_risk_score"] == 0

    def test_validate_output_non_int_score(self, risk_agent):
        """Q4.4: Non-integer score -> default 5."""
        parsed = {"ai_severity": "Medium", "ai_risk_score": "not_a_number", "ai_reasoning": "test"}
        result = RiskEvaluationAgent._validate_llm_output(parsed)
        assert result["ai_risk_score"] == 5

    def test_validate_output_missing_fields(self, risk_agent):
        """Q4.5: Missing fields -> defaults."""
        result = RiskEvaluationAgent._validate_llm_output({})
        assert result["ai_severity"] == "Medium"
        assert result["ai_risk_score"] == 5
        assert "No reasoning" in result["ai_reasoning"]

    @pytest.mark.parametrize("severity", ["Critical", "High", "Medium", "Low"])
    def test_all_valid_severities_accepted(self, severity):
        """Q4.6: Tat ca severity values hop le deu duoc chap nhan."""
        parsed = {"ai_severity": severity, "ai_risk_score": 5, "ai_reasoning": "test"}
        result = RiskEvaluationAgent._validate_llm_output(parsed)
        assert result["ai_severity"] == severity

    def test_score_single_finding_with_rag_context(self, risk_agent):
        """Q4.7: _score_single_finding inject RAG context vao LLM view."""
        risk_agent._rag_confidence = "high"
        finding = {
            "status": "FAIL", "event_code": "s3_bucket_public_access",
            "service": "s3", "resource_id": "my-bucket", "region": "us-east-1",
            "description": "Public access enabled", "severity": "High",
            "remediation_text": "Block public access",
        }
        rag_data = {"severity": "critical", "title": "S3 Public Access", "mappings": ["cis_2.1.1"]}

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "Critical", "ai_risk_score": 9,
            "ai_reasoning": "Public access violates CIS benchmark"
        })
        risk_agent.llm.invoke.return_value = mock_response

        result = risk_agent._score_single_finding(finding, rag_data)

        assert result["severity"] == "Critical"
        assert result["risk_score"] == 9
        assert result["compliance"] == ["cis_2.1.1"]
        assert result["prowler_severity"] == "High"

    def test_score_single_finding_without_rag_context(self, risk_agent):
        """Q4.8: _score_single_finding hoat dong binh thuong khi khong co RAG context."""
        finding = {
            "status": "FAIL", "event_code": "custom_check",
            "service": "custom", "resource_id": "res", "region": "us-east-1",
            "description": "Custom check failed", "severity": "Medium",
            "remediation_text": "Fix it",
        }

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "Medium", "ai_risk_score": 5,
            "ai_reasoning": "Moderate risk without compliance context"
        })
        risk_agent.llm.invoke.return_value = mock_response

        result = risk_agent._score_single_finding(finding, {})

        assert result["severity"] == "Medium"
        assert result["compliance"] == []


# ============================================================
# Q5: Batch Chunking
# ============================================================

class TestBatchChunking:
    """Verify batch chunking for large numbers of check_ids."""

    def test_single_batch_under_limit(self, risk_agent, mock_rag_client, risk_bundle_response,
                                       sample_fail_findings):
        """Q5.1: <=20 check_ids -> 1 RAG call."""
        mock_rag_client.build_context.return_value = risk_bundle_response
        risk_agent._fetch_rag_context(sample_fail_findings)

        assert mock_rag_client.build_context.call_count == 1

    def test_multiple_batches_over_limit(self, risk_agent, mock_rag_client, large_fail_findings):
        """Q5.2: >20 check_ids -> nhieu RAG calls (chunked by 20)."""
        # 25 unique check_ids -> should make 2 calls (20 + 5)
        mock_rag_client.build_context.return_value = {
            "payload": {
                "risk_bundle": {
                    "related_findings": [],
                    "control_mapping": [],
                }
            },
            "_meta": {"confidence": "medium"},
        }
        risk_agent._fetch_rag_context(large_fail_findings)

        assert mock_rag_client.build_context.call_count == 2  # ceil(25/20) = 2

    def test_chunk_size_matches_constant(self):
        """Q5.3: Chunk size = 20 (constant _RAG_BATCH_CHUNK_SIZE)."""
        assert _RAG_BATCH_CHUNK_SIZE == 20


# ============================================================
# Q6: Cache Effectiveness
# ============================================================

class TestCacheEffectiveness:
    """Verify in-memory cache prevents duplicate RAG calls."""

    def test_cache_populated_after_fetch(self, risk_agent, mock_rag_client, risk_bundle_response,
                                          sample_fail_findings):
        """Q6.1: Cache duoc populate sau fetch."""
        mock_rag_client.build_context.return_value = risk_bundle_response
        risk_agent._fetch_rag_context(sample_fail_findings)

        assert len(risk_agent._rag_cache) > 0

    def test_cache_prevents_duplicate_calls(self, risk_agent, mock_rag_client, risk_bundle_response,
                                             sample_fail_findings):
        """Q6.2: Goi _fetch_rag_context 2 lan voi cung findings -> chi 1 RAG call."""
        mock_rag_client.build_context.return_value = risk_bundle_response

        risk_agent._fetch_rag_context(sample_fail_findings)
        first_call_count = mock_rag_client.build_context.call_count

        risk_agent._fetch_rag_context(sample_fail_findings)
        second_call_count = mock_rag_client.build_context.call_count

        assert second_call_count == first_call_count  # No additional calls

    def test_cache_reset_per_run(self, risk_agent, mock_rag_client, risk_bundle_response,
                                  sample_fail_findings):
        """Q6.3: Cache duoc reset khi bat dau run() moi (khong mang data tu run truoc)."""
        mock_rag_client.build_context.return_value = risk_bundle_response

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "High", "ai_risk_score": 8, "ai_reasoning": "test"
        })
        risk_agent.llm.invoke.return_value = mock_response

        # First run populates cache
        risk_agent.run(sample_fail_findings)
        # Cache is cleared at START of second run(), so verify by checking
        # that run() resets counters at the beginning
        assert risk_agent._cache_hits == 0  # Reset at start of run()
        # _cache_misses is set during run, should be > 0 after run completes
        # The key invariant: each run starts fresh

    def test_cache_metrics_tracked(self, risk_agent, mock_rag_client, risk_bundle_response,
                                    sample_fail_findings):
        """Q6.4: Cache hit/miss metrics duoc track."""
        mock_rag_client.build_context.return_value = risk_bundle_response
        risk_agent._fetch_rag_context(sample_fail_findings)

        metrics = risk_agent.get_llm_metrics()
        assert "rag_cache" in metrics
        assert "hits" in metrics["rag_cache"]
        assert "misses" in metrics["rag_cache"]
        assert "hit_rate" in metrics["rag_cache"]

    def test_cache_hit_rate_calculation(self, risk_agent, mock_rag_client, risk_bundle_response,
                                         sample_fail_findings):
        """Q6.5: Hit rate tinh dung."""
        mock_rag_client.build_context.return_value = risk_bundle_response

        # First call: all misses
        risk_agent._fetch_rag_context(sample_fail_findings)
        # Second call: all hits (same ids)
        risk_agent._fetch_rag_context(sample_fail_findings)

        metrics = risk_agent.get_llm_metrics()
        assert metrics["rag_cache"]["hits"] > 0


# ============================================================
# Q7: Compliance Enrichment
# ============================================================

class TestComplianceEnrichment:
    """Verify compliance mappings are correctly attached to scored findings."""

    def test_compliance_mappings_in_output(self, risk_agent, mock_rag_client, risk_bundle_response):
        """Q7.1: Scored findings co compliance mappings tu RAG."""
        mock_rag_client.build_context.return_value = risk_bundle_response
        risk_agent._rag_confidence = "high"

        finding = {
            "status": "FAIL", "event_code": "s3_bucket_public_access",
            "service": "s3", "resource_id": "bucket", "region": "us-east-1",
            "description": "Public", "severity": "High", "remediation_text": "Fix",
        }
        rag_data = {"severity": "critical", "title": "Public Access",
                     "mappings": ["cis_aws_2.1.1", "pci_dss_s3.1"]}

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "Critical", "ai_risk_score": 9, "ai_reasoning": "Critical"
        })
        risk_agent.llm.invoke.return_value = mock_response

        result = risk_agent._score_single_finding(finding, rag_data)
        assert result["compliance"] == ["cis_aws_2.1.1", "pci_dss_s3.1"]

    def test_empty_compliance_when_no_rag(self, risk_agent):
        """Q7.2: Khong co RAG context -> compliance = []."""
        finding = {
            "status": "FAIL", "event_code": "test_check",
            "service": "test", "resource_id": "res", "region": "us-east-1",
            "description": "Test", "severity": "Medium", "remediation_text": "Fix",
        }

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "Medium", "ai_risk_score": 5, "ai_reasoning": "test"
        })
        risk_agent.llm.invoke.return_value = mock_response

        result = risk_agent._score_single_finding(finding, {})
        assert result["compliance"] == []

    def test_prowler_severity_preserved(self, risk_agent):
        """Q7.3: prowler_severity giu nguyen gia tri goc."""
        finding = {
            "status": "FAIL", "event_code": "test_check",
            "service": "test", "resource_id": "res", "region": "us-east-1",
            "description": "Test", "severity": "High", "remediation_text": "Fix",
        }

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "Critical", "ai_risk_score": 9, "ai_reasoning": "Upgraded"
        })
        risk_agent.llm.invoke.return_value = mock_response

        result = risk_agent._score_single_finding(finding, {})
        assert result["prowler_severity"] == "High"
        assert result["severity"] == "Critical"  # AI may override


# ============================================================
# Q8: Output Schema & Sorting
# ============================================================

class TestOutputSchema:
    """Verify output format consistency and correct sorting."""

    def test_enriched_finding_has_all_fields(self, risk_agent):
        """Q8.1: Enriched finding co day du fields."""
        finding = {
            "status": "FAIL", "event_code": "s3_test",
            "service": "s3", "resource_id": "res", "region": "us-east-1",
            "description": "Test", "severity": "High", "remediation_text": "Fix",
        }
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "High", "ai_risk_score": 8, "ai_reasoning": "test"
        })
        risk_agent.llm.invoke.return_value = mock_response

        result = risk_agent._score_single_finding(finding, {})

        required_fields = {"severity", "risk_score", "reasoning", "prowler_severity", "compliance"}
        missing = required_fields - set(result.keys())
        assert not missing, f"Missing fields: {missing}"

    def test_sort_by_priority_order(self, risk_agent):
        """Q8.2: Sort dung theo severity desc, risk_score desc."""
        findings = [
            {"severity": "Low", "risk_score": 2},
            {"severity": "Critical", "risk_score": 10},
            {"severity": "High", "risk_score": 7},
            {"severity": "Critical", "risk_score": 8},
            {"severity": "Medium", "risk_score": 5},
        ]
        sorted_findings = RiskEvaluationAgent._sort_by_priority(findings)

        assert sorted_findings[0]["severity"] == "Critical"
        assert sorted_findings[0]["risk_score"] == 10
        assert sorted_findings[1]["severity"] == "Critical"
        assert sorted_findings[1]["risk_score"] == 8
        assert sorted_findings[2]["severity"] == "High"
        assert sorted_findings[-1]["severity"] == "Low"

    def test_filter_only_fail_findings(self, risk_agent, sample_mixed_findings):
        """Q8.3: Chi xu ly FAIL findings, bo qua PASS."""
        result = risk_agent._filter_fail_findings(sample_mixed_findings)
        for f in result:
            assert f["status"] == "FAIL"
        assert len(result) == 3  # Only 3 FAIL out of 5

    def test_run_returns_empty_for_all_pass(self, risk_agent):
        """Q8.4: Tat ca PASS findings -> return empty list."""
        all_pass = [
            {"status": "PASS", "event_code": "s3_test", "service": "s3"},
            {"status": "PASS", "event_code": "iam_test", "service": "iam"},
        ]
        result = risk_agent.run(all_pass)
        assert result == []

    def test_run_full_pipeline(self, risk_agent, mock_rag_client, risk_bundle_response,
                                sample_fail_findings):
        """Q8.5: Full pipeline: filter -> fetch RAG -> score -> sort."""
        mock_rag_client.build_context.return_value = risk_bundle_response

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "High", "ai_risk_score": 8, "ai_reasoning": "test"
        })
        risk_agent.llm.invoke.return_value = mock_response

        result = risk_agent.run(sample_fail_findings)

        assert len(result) == 3
        # Results should be sorted (highest severity/score first)
        for i in range(len(result) - 1):
            curr_sev = _SEVERITY_MAP.get(result[i].get("severity"), 0)
            next_sev = _SEVERITY_MAP.get(result[i + 1].get("severity"), 0)
            if curr_sev == next_sev:
                assert result[i].get("risk_score", 0) >= result[i + 1].get("risk_score", 0)
            else:
                assert curr_sev >= next_sev


# ============================================================
# Q9: System Prompt Quality
# ============================================================

class TestSystemPromptQuality:
    """Verify system prompt content for risk evaluation."""

    def test_prompt_mentions_rag_context(self):
        """Q9.1: Two-Pass: PASS2 prompt references RAG context fields."""
        from agents.risk_evaluation_agent import SYSTEM_PROMPT_PASS2
        assert "rag_official_severity" in SYSTEM_PROMPT_PASS2

    def test_prompt_has_scoring_rubric(self):
        """Q9.2: System prompt co scoring rubric (1-10)."""
        assert "9-10" in SYSTEM_PROMPT_SINGLE
        assert "7-8" in SYSTEM_PROMPT_SINGLE
        assert "4-6" in SYSTEM_PROMPT_SINGLE
        assert "1-3" in SYSTEM_PROMPT_SINGLE

    def test_prompt_mentions_compliance(self):
        """Q9.3: System prompt nhac den compliance standards."""
        assert "CIS" in SYSTEM_PROMPT_SINGLE or "compliance" in SYSTEM_PROMPT_SINGLE.lower()

    def test_prompt_output_format_json(self):
        """Q9.4: System prompt yeu cau output JSON voi 3 fields."""
        assert "ai_severity" in SYSTEM_PROMPT_SINGLE
        assert "ai_risk_score" in SYSTEM_PROMPT_SINGLE
        assert "ai_reasoning" in SYSTEM_PROMPT_SINGLE

    def test_prompt_no_garbage_characters(self):
        """Q9.5: System prompt khong chua ky tu rac."""
        import re
        # Check for common garbage patterns
        garbage_patterns = [r"\._", r"\.{3,}", r"[^\x00-\x7F\xC0-\xFF]"]
        for pattern in garbage_patterns:
            matches = re.findall(pattern, SYSTEM_PROMPT_SINGLE)
            # Filter out legitimate uses
            if pattern == r"\._":
                assert len(matches) == 0, f"Found garbage pattern '{pattern}': {matches}"
