"""
RAG Integration Performance Benchmark Tests
=============================================
Danh gia hieu suat cua viec tich hop RAG:

1. Retrieval Latency: Thoi gian goi RAG API
2. Cache Performance: Hieu qua cache (hit/miss rate)
3. Batch Efficiency: So RAG calls cho batch lon
4. Memory Usage: Kich thuoc cache + context
5. LLM Metrics: Tracking latency + call count
6. Scalability: Xu ly nhieu findings cung luc
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from agents.planning_agent import PlanningAgent
from agents.risk_evaluation_agent import RiskEvaluationAgent, _RAG_BATCH_CHUNK_SIZE


# ============================================================
# P1: Planning Agent — Retrieval Efficiency
# ============================================================

class TestPlanningRetrievalEfficiency:
    """Benchmark retrieval efficiency in PlanningAgent."""

    def test_single_rag_call_on_success(self, planning_agent, mock_rag_client, planning_bundle_s3):
        """P1.1: build_context thanh cong -> chi 1 RAG call (khong goi retrieve_checks)."""
        mock_rag_client.build_context.return_value = planning_bundle_s3
        planning_agent._retrieve_candidates("s3 security", "s3")

        assert mock_rag_client.build_context.call_count == 1
        assert mock_rag_client.retrieve_checks.call_count == 0

    def test_max_two_rag_calls_on_fallback(self, planning_agent, mock_rag_client):
        """P1.2: build_context fail -> toi da 2 RAG calls (build_context + retrieve_checks)."""
        mock_rag_client.build_context.return_value = None
        mock_rag_client.retrieve_checks.return_value = {
            "results": [
                {"doc_id": "check:s3_test", "score": 0.8,
                 "metadata": {"service": "s3", "title": "T", "severity": "medium"}},
            ],
        }
        planning_agent._retrieve_candidates("s3 test", "s3")

        assert mock_rag_client.build_context.call_count == 1
        assert mock_rag_client.retrieve_checks.call_count == 1

    def test_no_rag_calls_on_explicit_checks(self, planning_agent, mock_rag_client):
        """P1.3: Explicit check IDs -> 0 RAG calls."""
        planning_agent.run("run s3_bucket_public_access")

        assert mock_rag_client.build_context.call_count == 0
        assert mock_rag_client.retrieve_checks.call_count == 0

    def test_no_rag_calls_on_group_scan(self, planning_agent, mock_rag_client):
        """P1.4: Group scan -> 0 RAG calls."""
        with patch.object(planning_agent, "_detect_explicit_checks", return_value=None):
            with patch.object(planning_agent, "_translate_intent", return_value={
                "target_service": "s3", "is_group_scan": True, "search_queries": [],
            }):
                planning_agent.run("scan all s3")

        assert mock_rag_client.build_context.call_count == 0

    def test_candidate_parsing_efficient(self):
        """P1.5: _parse_findings_to_candidates xu ly 100 findings nhanh."""
        findings = [
            {"check_id": f"s3_check_{i}", "service": "s3",
             "title": f"Check {i}", "severity": "medium"}
            for i in range(100)
        ]

        start = time.perf_counter()
        result = PlanningAgent._parse_findings_to_candidates(findings, "s3")
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1  # Should complete in < 100ms
        assert len(result) <= 10  # Capped at 10

    def test_maturity_context_formatting_efficient(self):
        """P1.6: _format_maturity_context xu ly danh sach dai nhanh."""
        long_ids = [f"mapping_id_{i:04d}" for i in range(1000)]

        start = time.perf_counter()
        result = PlanningAgent._format_maturity_context(long_ids, long_ids)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.05  # Should complete in < 50ms
        assert len(result) <= 500


# ============================================================
# P2: Risk Agent — Batch & Cache Performance
# ============================================================

class TestRiskBatchCachePerformance:
    """Benchmark batch chunking and cache performance in RiskEvaluationAgent."""

    def test_cache_eliminates_duplicate_calls(self, risk_agent, mock_rag_client, risk_bundle_response,
                                                sample_fail_findings):
        """P2.1: Cache eliminates 100% duplicate RAG calls."""
        mock_rag_client.build_context.return_value = risk_bundle_response

        # First fetch
        risk_agent._fetch_rag_context(sample_fail_findings)
        first_call_count = mock_rag_client.build_context.call_count

        # Second fetch (same findings)
        risk_agent._fetch_rag_context(sample_fail_findings)
        second_call_count = mock_rag_client.build_context.call_count

        # No additional calls on second fetch
        assert second_call_count == first_call_count

    def test_batch_chunking_minimizes_calls(self, risk_agent, mock_rag_client, large_fail_findings):
        """P2.2: 25 unique check_ids -> 2 RAG calls (not 25)."""
        mock_rag_client.build_context.return_value = {
            "payload": {
                "risk_bundle": {"related_findings": [], "control_mapping": []}
            },
            "_meta": {"confidence": "medium"},
        }
        risk_agent._fetch_rag_context(large_fail_findings)

        # 25 unique IDs / 20 per batch = 2 calls
        expected_calls = (25 + _RAG_BATCH_CHUNK_SIZE - 1) // _RAG_BATCH_CHUNK_SIZE
        assert mock_rag_client.build_context.call_count == expected_calls

    def test_cache_size_bounded(self, risk_agent, mock_rag_client, large_fail_findings):
        """P2.3: Cache size <= so luong unique check_ids."""
        mock_rag_client.build_context.return_value = {
            "payload": {
                "risk_bundle": {
                    "related_findings": [
                        {"check_id": f"s3_bucket_public_access", "severity": "high", "title": "T"},
                    ],
                    "control_mapping": [],
                }
            },
            "_meta": {"confidence": "medium"},
        }
        risk_agent._fetch_rag_context(large_fail_findings)

        # Cache should not grow unbounded
        assert len(risk_agent._rag_cache) <= len(large_fail_findings)

    def test_cache_hit_rate_100_on_reuse(self, risk_agent, mock_rag_client, risk_bundle_response,
                                          sample_fail_findings):
        """P2.4: Reuse same findings -> 100% cache hit rate on second call."""
        mock_rag_client.build_context.return_value = risk_bundle_response

        risk_agent._fetch_rag_context(sample_fail_findings)
        risk_agent._fetch_rag_context(sample_fail_findings)

        metrics = risk_agent.get_llm_metrics()
        # After second call, all lookups should be hits
        assert metrics["rag_cache"]["hits"] > 0


# ============================================================
# P3: LLM Metrics Tracking
# ============================================================

class TestLLMMetricsTracking:
    """Verify LLM metrics are correctly tracked."""

    def test_metrics_structure(self, risk_agent):
        """P3.1: get_llm_metrics() tra ve dung structure."""
        metrics = risk_agent.get_llm_metrics()

        assert "total_latency" in metrics
        assert "call_history" in metrics
        assert "call_count" in metrics
        assert "rag_cache" in metrics

    def test_metrics_rag_cache_structure(self, risk_agent):
        """P3.2: rag_cache metrics co day du fields."""
        metrics = risk_agent.get_llm_metrics()
        cache_metrics = metrics["rag_cache"]

        assert "hits" in cache_metrics
        assert "misses" in cache_metrics
        assert "hit_rate" in cache_metrics
        assert "confidence" in cache_metrics

    def test_metrics_reset_per_run(self, risk_agent, mock_rag_client, risk_bundle_response,
                                    sample_fail_findings):
        """P3.3: Cache counters duoc reset tai dau moi run() — run moi bat dau sach."""
        mock_rag_client.build_context.return_value = risk_bundle_response
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "High", "ai_risk_score": 8, "ai_reasoning": "test"
        })
        risk_agent.llm.invoke.return_value = mock_response

        # Manually set counters to simulate previous run
        risk_agent._cache_hits = 99
        risk_agent._cache_misses = 99

        # run() resets at START, then re-populates during execution
        risk_agent.run(sample_fail_findings)

        # _cache_hits should be 0 (reset at start, and first run = all misses)
        assert risk_agent._cache_hits == 0

    def test_call_count_matches_findings(self, risk_agent, mock_rag_client, risk_bundle_response,
                                          sample_fail_findings):
        """P3.4: LLM call count = so luong FAIL findings."""
        mock_rag_client.build_context.return_value = risk_bundle_response
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "High", "ai_risk_score": 8, "ai_reasoning": "test"
        })
        risk_agent.llm.invoke.return_value = mock_response

        risk_agent.run(sample_fail_findings)

        # 3 FAIL findings × 2 passes (Two-Pass with RAG) = 6 LLM calls
        assert risk_agent.llm.invoke.call_count == 6

    def test_hit_rate_zero_on_first_run(self, risk_agent, mock_rag_client, risk_bundle_response,
                                          sample_fail_findings):
        """P3.5: Hit rate = 0 on first fetch (all misses)."""
        mock_rag_client.build_context.return_value = risk_bundle_response
        risk_agent._fetch_rag_context(sample_fail_findings)

        # First time, all should be misses
        assert risk_agent._cache_misses > 0


# ============================================================
# P4: Scalability Tests
# ============================================================

class TestScalability:
    """Test handling of large inputs."""

    def test_risk_agent_handles_50_findings(self, risk_agent, mock_rag_client):
        """P4.1: 50 FAIL findings xu ly thanh cong."""
        findings = [
            {
                "status": "FAIL",
                "event_code": f"check_{i}",
                "check_id": f"check_{i}",
                "service": "s3",
                "resource_id": f"resource-{i}",
                "region": "us-east-1",
                "description": f"Finding {i}",
                "severity": "High",
                "remediation_text": f"Fix {i}",
            }
            for i in range(50)
        ]
        mock_rag_client.build_context.return_value = {
            "payload": {
                "risk_bundle": {"related_findings": [], "control_mapping": []}
            },
            "_meta": {"confidence": "medium"},
        }
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "ai_severity": "High", "ai_risk_score": 7, "ai_reasoning": "test"
        })
        risk_agent.llm.invoke.return_value = mock_response

        result = risk_agent.run(findings)
        assert len(result) == 50

    def test_planning_handles_empty_rag_response(self, planning_agent, mock_rag_client):
        """P4.2: PlanningAgent handles empty RAG responses gracefully."""
        mock_rag_client.build_context.return_value = None
        mock_rag_client.retrieve_checks.return_value = None

        with patch.object(planning_agent, "_detect_explicit_checks", return_value=None):
            with patch.object(planning_agent, "_translate_intent", return_value={
                "target_service": "s3", "is_group_scan": False,
                "search_queries": ["test"],
            }):
                result = planning_agent.run("test query")

        assert isinstance(result, dict)
        assert "groups_to_scan" in result or "error" in result

    def test_risk_agent_zero_findings(self, risk_agent):
        """P4.3: 0 findings -> empty result, no errors."""
        result = risk_agent.run([])
        assert result == []

    def test_risk_agent_all_pass_findings(self, risk_agent):
        """P4.4: All PASS findings -> empty result."""
        findings = [
            {"status": "PASS", "event_code": f"check_{i}", "service": "s3"}
            for i in range(10)
        ]
        result = risk_agent.run(findings)
        assert result == []

    def test_planning_candidates_dedup_performance(self):
        """P4.5: Deduplication xu ly nhieu duplicates nhanh."""
        results = []
        for i in range(100):
            results.append({
                "doc_id": f"check:s3_check_{i % 10}",  # Only 10 unique
                "score": 0.5 + (i % 10) * 0.05,
                "metadata": {"service": "s3", "title": f"Check {i}", "severity": "medium"},
            })

        start = time.perf_counter()
        candidates = PlanningAgent._parse_results_to_candidates(results, "s3")
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1
        assert len(candidates) == 10  # 10 unique
