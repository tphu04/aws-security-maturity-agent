"""
Unit tests for app.evaluation.metrics.

Covers all functions with known inputs/outputs, edge cases,
and the exact NDCG example from RAG_Evaluation_Framework.md (Section 2.3).
"""

from __future__ import annotations

import math
import pytest

from app.evaluation.metrics import (
    aggregate_metrics,
    compute_average_precision,
    compute_confidence_calibration,
    compute_hit_rate,
    compute_latency_percentiles,
    compute_ndcg,
    compute_reciprocal_rank,
    compute_robustness_gap,
)


# ===================================================================
# compute_reciprocal_rank
# ===================================================================

class TestComputeReciprocalRank:
    def test_first_position(self):
        assert compute_reciprocal_rank(["a", "b", "c"], ["a"]) == 1.0

    def test_second_position(self):
        assert compute_reciprocal_rank(["a", "b", "c"], ["b"]) == 0.5

    def test_third_position(self):
        assert compute_reciprocal_rank(["a", "b", "c"], ["c"]) == pytest.approx(1 / 3)

    def test_not_found(self):
        assert compute_reciprocal_rank(["a", "b", "c"], ["x"]) == 0.0

    def test_multiple_relevant_first_match_wins(self):
        assert compute_reciprocal_rank(["a", "b", "c"], ["b", "c"]) == 0.5

    def test_empty_retrieved(self):
        assert compute_reciprocal_rank([], ["a"]) == 0.0

    def test_empty_relevant(self):
        assert compute_reciprocal_rank(["a", "b"], []) == 0.0

    def test_both_empty(self):
        assert compute_reciprocal_rank([], []) == 0.0


# ===================================================================
# compute_ndcg
# ===================================================================

class TestComputeNDCG:
    def test_framework_example(self):
        """Exact example from RAG_Evaluation_Framework.md Section 2.3.

        Top-5: [Relevant, Not, Relevant, Not, Relevant]
        Relevance vector: [1, 0, 1, 0, 1]
        3 relevant docs in corpus.

        DCG  = 1/log2(2) + 0/log2(3) + 1/log2(4) + 0/log2(5) + 1/log2(6)
             = 1.0 + 0 + 0.5 + 0 + 0.387 = 1.887
        IDCG = 1/log2(2) + 1/log2(3) + 1/log2(4) = 1.0 + 0.631 + 0.5 = 2.131
        NDCG = 1.887 / 2.131 = 0.886
        """
        retrieved = ["a", "x", "b", "y", "c"]
        relevant = ["a", "b", "c"]
        # Exact = 0.88544... ≈ 0.885 (doc shows 0.886 due to rounded intermediates)
        assert compute_ndcg(retrieved, relevant, k=5) == pytest.approx(0.886, abs=0.002)

    def test_perfect_ranking(self):
        """All relevant docs at top positions."""
        retrieved = ["a", "b", "c", "x", "y"]
        relevant = ["a", "b", "c"]
        assert compute_ndcg(retrieved, relevant, k=5) == 1.0

    def test_single_relevant_at_top(self):
        retrieved = ["a", "x", "y"]
        relevant = ["a"]
        assert compute_ndcg(retrieved, relevant, k=3) == 1.0

    def test_single_relevant_at_bottom(self):
        retrieved = ["x", "y", "a"]
        relevant = ["a"]
        # DCG = 0 + 0 + 1/log2(4) = 0.5
        # IDCG = 1/log2(2) = 1.0
        # NDCG = 0.5
        assert compute_ndcg(retrieved, relevant, k=3) == 0.5

    def test_no_relevant_found(self):
        assert compute_ndcg(["x", "y", "z"], ["a", "b"], k=3) == 0.0

    def test_empty_retrieved(self):
        assert compute_ndcg([], ["a"], k=5) == 0.0

    def test_empty_relevant(self):
        assert compute_ndcg(["a", "b"], [], k=5) == 0.0

    def test_k_zero(self):
        assert compute_ndcg(["a"], ["a"], k=0) == 0.0

    def test_k_larger_than_retrieved(self):
        """k > len(retrieved) — should compute on available portion."""
        retrieved = ["a", "b"]
        relevant = ["a", "b"]
        # Only 2 items, k=5 but only 2 to evaluate
        # DCG = 1/log2(2) + 1/log2(3) = 1.0 + 0.631 = 1.631
        # IDCG (k=5, 2 relevant) = 1/log2(2) + 1/log2(3) = 1.631
        # NDCG = 1.0
        assert compute_ndcg(retrieved, relevant, k=5) == 1.0


# ===================================================================
# compute_average_precision
# ===================================================================

class TestComputeAveragePrecision:
    def test_all_relevant_at_top(self):
        """System A from Framework doc: [R, R, R, -, -] → AP = 1.0."""
        retrieved = ["a", "b", "c", "x", "y"]
        relevant = ["a", "b", "c"]
        assert compute_average_precision(retrieved, relevant, k=5) == 1.0

    def test_relevant_scattered(self):
        """System B from Framework doc: [R, -, -, R, R] → AP ≈ 0.756."""
        retrieved = ["a", "x", "y", "b", "c"]
        relevant = ["a", "b", "c"]
        # P@1 = 1/1 = 1.0, P@4 = 2/4 = 0.5, P@5 = 3/5 = 0.6
        # AP = (1.0 + 0.5 + 0.6) / 3 = 0.7
        result = compute_average_precision(retrieved, relevant, k=5)
        assert result == pytest.approx(0.7, abs=0.001)

    def test_single_relevant_at_first(self):
        assert compute_average_precision(["a", "x", "y"], ["a"], k=3) == 1.0

    def test_single_relevant_at_third(self):
        # P@3 = 1/3
        # AP = (1/3) / min(1, 3) = 1/3
        result = compute_average_precision(["x", "y", "a"], ["a"], k=3)
        assert result == pytest.approx(1 / 3, abs=0.001)

    def test_no_relevant_found(self):
        assert compute_average_precision(["x", "y", "z"], ["a"], k=3) == 0.0

    def test_empty_retrieved(self):
        assert compute_average_precision([], ["a"], k=5) == 0.0

    def test_empty_relevant(self):
        assert compute_average_precision(["a"], [], k=5) == 0.0

    def test_k_zero(self):
        assert compute_average_precision(["a"], ["a"], k=0) == 0.0

    def test_k_larger_than_retrieved(self):
        retrieved = ["a", "b"]
        relevant = ["a", "b"]
        # P@1=1/1, P@2=2/2 → AP = (1 + 1) / min(2, 5) = 1.0
        assert compute_average_precision(retrieved, relevant, k=5) == 1.0


# ===================================================================
# compute_hit_rate
# ===================================================================

class TestComputeHitRate:
    def test_hit(self):
        assert compute_hit_rate(["a", "b", "c"], ["c"], k=3) == 1.0

    def test_miss(self):
        assert compute_hit_rate(["a", "b", "c"], ["x"], k=3) == 0.0

    def test_hit_within_k(self):
        assert compute_hit_rate(["a", "b", "c", "d"], ["b"], k=2) == 1.0

    def test_miss_beyond_k(self):
        assert compute_hit_rate(["a", "b", "c", "d"], ["d"], k=2) == 0.0

    def test_empty_retrieved(self):
        assert compute_hit_rate([], ["a"], k=5) == 0.0

    def test_empty_relevant(self):
        assert compute_hit_rate(["a"], [], k=5) == 0.0

    def test_k_zero(self):
        assert compute_hit_rate(["a"], ["a"], k=0) == 0.0


# ===================================================================
# aggregate_metrics
# ===================================================================

class TestAggregateMetrics:
    def test_basic_aggregation(self):
        per_query = [
            {"mrr": 1.0, "ndcg@5": 0.88, "hit@5": 1.0},
            {"mrr": 0.5, "ndcg@5": 0.50, "hit@5": 1.0},
            {"mrr": 0.0, "ndcg@5": 0.00, "hit@5": 0.0},
        ]
        result = aggregate_metrics(per_query)
        assert result["mrr"] == 0.5
        assert result["ndcg@5"] == pytest.approx(0.46, abs=0.01)
        assert result["hit@5"] == pytest.approx(0.6667, abs=0.001)

    def test_single_query(self):
        per_query = [{"mrr": 0.75, "ndcg@5": 0.9}]
        result = aggregate_metrics(per_query)
        assert result["mrr"] == 0.75
        assert result["ndcg@5"] == 0.9

    def test_empty_input(self):
        assert aggregate_metrics([]) == {}


# ===================================================================
# compute_latency_percentiles
# ===================================================================

class TestComputeLatencyPercentiles:
    def test_basic(self):
        latencies = [100.0, 200.0, 300.0, 400.0, 500.0]
        result = compute_latency_percentiles(latencies)
        assert result["p50_ms"] == 300.0
        assert result["mean_ms"] == 300.0

    def test_single_value(self):
        result = compute_latency_percentiles([150.0])
        assert result["p50_ms"] == 150.0
        assert result["p90_ms"] == 150.0
        assert result["p99_ms"] == 150.0
        assert result["mean_ms"] == 150.0

    def test_empty(self):
        assert compute_latency_percentiles([]) == {}

    def test_percentiles_ordering(self):
        latencies = list(range(1, 101))  # 1..100
        result = compute_latency_percentiles([float(x) for x in latencies])
        assert result["p50_ms"] <= result["p90_ms"] <= result["p99_ms"]


# ===================================================================
# compute_robustness_gap
# ===================================================================

class TestComputeRobustnessGap:
    def test_framework_example(self):
        """Example from the implementation plan."""
        cats = {
            "exact": {"top1_rate": 1.0},
            "paraphrase": {"top1_rate": 0.667},
            "risk": {"top1_rate": 0.167},
            "semantic_hard": {"top1_rate": 0.25},
        }
        result = compute_robustness_gap(cats)
        assert result["gap_pp"] == 83.3
        assert result["best_category"] == "exact"
        assert result["best_value"] == 1.0
        assert result["worst_category"] == "risk"
        assert result["worst_value"] == 0.167

    def test_no_gap(self):
        cats = {
            "a": {"top1_rate": 0.8},
            "b": {"top1_rate": 0.8},
        }
        result = compute_robustness_gap(cats)
        assert result["gap_pp"] == 0.0

    def test_empty_categories(self):
        result = compute_robustness_gap({})
        assert result["gap_pp"] == 0.0
        assert result["best_category"] is None

    def test_custom_metric_key(self):
        cats = {
            "a": {"hit_rate_5": 0.9},
            "b": {"hit_rate_5": 0.5},
        }
        result = compute_robustness_gap(cats, metric_key="hit_rate_5")
        assert result["gap_pp"] == 40.0

    def test_missing_metric_key_in_some_categories(self):
        cats = {
            "a": {"top1_rate": 0.9},
            "b": {},  # missing key
        }
        result = compute_robustness_gap(cats)
        # Only "a" has the key, so gap = 0
        assert result["gap_pp"] == 0.0
        assert result["best_category"] == "a"
        assert result["worst_category"] == "a"

    def test_all_categories_missing_metric_key(self):
        cats = {
            "a": {"other_metric": 0.9},
            "b": {"other_metric": 0.5},
        }
        result = compute_robustness_gap(cats)
        assert result["gap_pp"] == 0.0
        assert result["best_category"] is None
        assert result["worst_category"] is None


# ===================================================================
# compute_confidence_calibration
# ===================================================================

class TestComputeConfidenceCalibration:
    def test_empty_input(self):
        result = compute_confidence_calibration([])
        assert result["total_cases"] == 0
        assert result["ece"] == 0.0
        assert result["overall_calibrated"] is None
        assert result["high"]["count"] == 0
        assert result["medium"]["count"] == 0
        assert result["low"]["count"] == 0

    def test_all_high_all_correct(self):
        """Perfect high confidence — all hits."""
        cases = [{"confidence": "high", "hit_top1": True}] * 10
        result = compute_confidence_calibration(cases)
        assert result["high"]["count"] == 10
        assert result["high"]["actual_accuracy"] == 1.0
        assert result["high"]["calibrated"] is True
        assert result["overall_calibrated"] is True

    def test_all_high_below_threshold(self):
        """High confidence but accuracy < 80% → not calibrated."""
        cases = (
            [{"confidence": "high", "hit_top1": True}] * 3
            + [{"confidence": "high", "hit_top1": False}] * 7
        )
        result = compute_confidence_calibration(cases)
        assert result["high"]["count"] == 10
        assert result["high"]["actual_accuracy"] == 0.3
        assert result["high"]["calibrated"] is False
        assert result["overall_calibrated"] is False

    def test_high_exactly_at_threshold(self):
        """High confidence with exactly 80% accuracy → calibrated."""
        cases = (
            [{"confidence": "high", "hit_top1": True}] * 4
            + [{"confidence": "high", "hit_top1": False}] * 1
        )
        result = compute_confidence_calibration(cases)
        assert result["high"]["actual_accuracy"] == 0.8
        assert result["high"]["calibrated"] is True

    def test_medium_calibrated(self):
        """Medium confidence with accuracy in 50-80% → calibrated."""
        cases = (
            [{"confidence": "medium", "hit_top1": True}] * 6
            + [{"confidence": "medium", "hit_top1": False}] * 4
        )
        result = compute_confidence_calibration(cases)
        assert result["medium"]["actual_accuracy"] == 0.6
        assert result["medium"]["calibrated"] is True

    def test_medium_too_high_not_calibrated(self):
        """Medium confidence with accuracy > 80% → not calibrated (too good)."""
        cases = (
            [{"confidence": "medium", "hit_top1": True}] * 9
            + [{"confidence": "medium", "hit_top1": False}] * 1
        )
        result = compute_confidence_calibration(cases)
        assert result["medium"]["actual_accuracy"] == 0.9
        assert result["medium"]["calibrated"] is False

    def test_medium_too_low_not_calibrated(self):
        """Medium confidence with accuracy < 50% → not calibrated."""
        cases = (
            [{"confidence": "medium", "hit_top1": True}] * 2
            + [{"confidence": "medium", "hit_top1": False}] * 8
        )
        result = compute_confidence_calibration(cases)
        assert result["medium"]["actual_accuracy"] == 0.2
        assert result["medium"]["calibrated"] is False

    def test_low_calibrated(self):
        """Low confidence with accuracy < 50% → calibrated."""
        cases = (
            [{"confidence": "low", "hit_top1": True}] * 2
            + [{"confidence": "low", "hit_top1": False}] * 8
        )
        result = compute_confidence_calibration(cases)
        assert result["low"]["actual_accuracy"] == 0.2
        assert result["low"]["calibrated"] is True

    def test_low_too_high_not_calibrated(self):
        """Low confidence with accuracy >= 50% → not calibrated."""
        cases = (
            [{"confidence": "low", "hit_top1": True}] * 6
            + [{"confidence": "low", "hit_top1": False}] * 4
        )
        result = compute_confidence_calibration(cases)
        assert result["low"]["actual_accuracy"] == 0.6
        assert result["low"]["calibrated"] is False

    def test_mixed_bins_all_calibrated(self):
        """All three bins populated and calibrated."""
        cases = (
            # High: 4/5 = 80% ✓
            [{"confidence": "high", "hit_top1": True}] * 4
            + [{"confidence": "high", "hit_top1": False}] * 1
            # Medium: 3/5 = 60% ✓
            + [{"confidence": "medium", "hit_top1": True}] * 3
            + [{"confidence": "medium", "hit_top1": False}] * 2
            # Low: 1/5 = 20% ✓
            + [{"confidence": "low", "hit_top1": True}] * 1
            + [{"confidence": "low", "hit_top1": False}] * 4
        )
        result = compute_confidence_calibration(cases)
        assert result["high"]["calibrated"] is True
        assert result["medium"]["calibrated"] is True
        assert result["low"]["calibrated"] is True
        assert result["overall_calibrated"] is True
        assert result["total_cases"] == 15

    def test_mixed_bins_one_fails(self):
        """One bin fails → overall not calibrated."""
        cases = (
            # High: 4/5 = 80% ✓
            [{"confidence": "high", "hit_top1": True}] * 4
            + [{"confidence": "high", "hit_top1": False}] * 1
            # Medium: 1/5 = 20% ✗ (too low)
            + [{"confidence": "medium", "hit_top1": True}] * 1
            + [{"confidence": "medium", "hit_top1": False}] * 4
        )
        result = compute_confidence_calibration(cases)
        assert result["high"]["calibrated"] is True
        assert result["medium"]["calibrated"] is False
        assert result["overall_calibrated"] is False

    def test_ece_computation(self):
        """Verify ECE formula: Σ(|accuracy - midpoint| × count) / total."""
        cases = (
            # High: 4/5 = 0.80, midpoint 0.90, |0.80-0.90| = 0.10
            [{"confidence": "high", "hit_top1": True}] * 4
            + [{"confidence": "high", "hit_top1": False}] * 1
            # Medium: 3/5 = 0.60, midpoint 0.65, |0.60-0.65| = 0.05
            + [{"confidence": "medium", "hit_top1": True}] * 3
            + [{"confidence": "medium", "hit_top1": False}] * 2
            # Low: 1/5 = 0.20, midpoint 0.25, |0.20-0.25| = 0.05
            + [{"confidence": "low", "hit_top1": True}] * 1
            + [{"confidence": "low", "hit_top1": False}] * 4
        )
        result = compute_confidence_calibration(cases)
        # ECE = (0.10*5 + 0.05*5 + 0.05*5) / 15 = 1.0/15 = 0.0667
        assert result["ece"] == pytest.approx(0.0667, abs=0.001)

    def test_ece_zero_when_perfectly_calibrated(self):
        """ECE = 0 when each bin's accuracy matches its midpoint exactly."""
        # Need accuracy = midpoint: high 0.90, medium 0.65, low 0.25
        # High: 9/10 = 0.90
        cases = (
            [{"confidence": "high", "hit_top1": True}] * 9
            + [{"confidence": "high", "hit_top1": False}] * 1
            # Medium: 13/20 = 0.65
            + [{"confidence": "medium", "hit_top1": True}] * 13
            + [{"confidence": "medium", "hit_top1": False}] * 7
            # Low: 5/20 = 0.25
            + [{"confidence": "low", "hit_top1": True}] * 5
            + [{"confidence": "low", "hit_top1": False}] * 15
        )
        result = compute_confidence_calibration(cases)
        assert result["ece"] == pytest.approx(0.0, abs=0.001)

    def test_only_medium_cases(self):
        """Only medium bin populated, others empty."""
        cases = [{"confidence": "medium", "hit_top1": True}] * 7 + \
                [{"confidence": "medium", "hit_top1": False}] * 3
        result = compute_confidence_calibration(cases)
        assert result["high"]["count"] == 0
        assert result["high"]["actual_accuracy"] is None
        assert result["medium"]["count"] == 10
        assert result["medium"]["actual_accuracy"] == 0.7
        assert result["low"]["count"] == 0
        assert result["total_cases"] == 10
        # Overall: only medium populated, and it's calibrated (70% in 50-80%)
        assert result["overall_calibrated"] is True

    def test_unknown_confidence_levels_ignored(self):
        """Cases with unknown/None confidence are silently ignored."""
        cases = [
            {"confidence": "medium", "hit_top1": True},
            {"confidence": "unknown", "hit_top1": True},
            {"confidence": None, "hit_top1": True},
            {"confidence": "", "hit_top1": True},
        ]
        result = compute_confidence_calibration(cases)
        assert result["total_cases"] == 1  # only "medium"
        assert result["medium"]["count"] == 1

    def test_case_insensitive_confidence(self):
        """Confidence level matching is case-insensitive."""
        cases = [
            {"confidence": "HIGH", "hit_top1": True},
            {"confidence": "High", "hit_top1": True},
            {"confidence": "MEDIUM", "hit_top1": False},
        ]
        result = compute_confidence_calibration(cases)
        assert result["high"]["count"] == 2
        assert result["medium"]["count"] == 1

    def test_expected_thresholds_in_output(self):
        """Verify expected_min/expected_max are present in output."""
        cases = [{"confidence": "high", "hit_top1": True}]
        result = compute_confidence_calibration(cases)
        assert result["high"]["expected_min"] == 0.80
        assert result["medium"].get("expected_min") == 0.50
        assert result["medium"].get("expected_max") == 0.80
        assert result["low"].get("expected_max") == 0.50

    def test_realistic_scenario_zero_high(self):
        """Realistic: 0 high, all medium — insight about strict thresholds."""
        cases = (
            [{"confidence": "medium", "hit_top1": True}] * 35
            + [{"confidence": "medium", "hit_top1": False}] * 15
            + [{"confidence": "low", "hit_top1": True}] * 3
            + [{"confidence": "low", "hit_top1": False}] * 7
        )
        result = compute_confidence_calibration(cases)
        assert result["high"]["count"] == 0
        assert result["high"]["calibrated"] is None
        assert result["medium"]["count"] == 50
        assert result["medium"]["actual_accuracy"] == 0.7
        assert result["low"]["count"] == 10
        assert result["low"]["actual_accuracy"] == 0.3
        assert result["total_cases"] == 60

    def test_per_route_separate_calibration(self):
        """Verify that per-route calibration produces independent results.

        Simulates the Task 5.2 flow: filter cases by route_type, then
        compute_confidence_calibration independently per route.
        """
        # check_search: all medium, high accuracy (70%)
        check_cases = (
            [{"confidence": "medium", "hit_top1": True, "route_type": "check_search"}] * 7
            + [{"confidence": "medium", "hit_top1": False, "route_type": "check_search"}] * 3
        )
        # maturity_search: all medium, low accuracy (30%) — not calibrated
        maturity_cases = (
            [{"confidence": "medium", "hit_top1": True, "route_type": "maturity_search"}] * 3
            + [{"confidence": "medium", "hit_top1": False, "route_type": "maturity_search"}] * 7
        )
        all_cases = check_cases + maturity_cases

        # Per-route calibration
        by_route = {}
        for route in ("check_search", "maturity_search"):
            filtered = [
                {"confidence": c["confidence"], "hit_top1": c["hit_top1"]}
                for c in all_cases if c["route_type"] == route
            ]
            by_route[route] = compute_confidence_calibration(filtered)

        # check_search: 70% medium → calibrated (50-80%)
        assert by_route["check_search"]["medium"]["actual_accuracy"] == 0.7
        assert by_route["check_search"]["medium"]["calibrated"] is True
        assert by_route["check_search"]["overall_calibrated"] is True

        # maturity_search: 30% medium → NOT calibrated (<50%)
        assert by_route["maturity_search"]["medium"]["actual_accuracy"] == 0.3
        assert by_route["maturity_search"]["medium"]["calibrated"] is False
        assert by_route["maturity_search"]["overall_calibrated"] is False

        # This is the key 5.2 insight: one route calibrated, other not
        assert by_route["check_search"]["overall_calibrated"] != \
               by_route["maturity_search"]["overall_calibrated"]


# ===================================================================
# _infer_route_type (Task 5.2 — from benchmark_retrieval)
# ===================================================================

class TestInferRouteType:
    def test_checks_endpoint(self):
        from data.benchmarks.benchmark_retrieval import _infer_route_type
        assert _infer_route_type("http://localhost:8000/v1/retrieve/checks") == "check_search"

    def test_maturity_endpoint(self):
        from data.benchmarks.benchmark_retrieval import _infer_route_type
        assert _infer_route_type("http://localhost:8000/v1/retrieve/maturity") == "maturity_search"

    def test_unknown_endpoint(self):
        from data.benchmarks.benchmark_retrieval import _infer_route_type
        assert _infer_route_type("http://localhost:8000/v1/retrieve/other") == "unknown"

    def test_empty_endpoint(self):
        from data.benchmarks.benchmark_retrieval import _infer_route_type
        assert _infer_route_type("") == "unknown"
