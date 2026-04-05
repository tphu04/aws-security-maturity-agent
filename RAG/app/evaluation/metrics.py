"""
Centralized retrieval evaluation metrics.

Provides pure-function implementations of IR metrics used by the
RAG benchmark pipeline.  Every function operates on a single query
unless stated otherwise; use ``aggregate_metrics`` to combine
per-query results across a benchmark run.

Dependencies: only ``math``, ``statistics`` (stdlib) — no third-party
libraries.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional


# -----------------------------------------------------------------------
# Per-query metrics
# -----------------------------------------------------------------------

def compute_reciprocal_rank(
    retrieved_ids: List[str],
    relevant_ids: List[str],
) -> float:
    """Return 1/rank of the first relevant hit, or 0.0 if none found.

    >>> compute_reciprocal_rank(["a", "b", "c"], ["b"])
    0.5
    >>> compute_reciprocal_rank(["a", "b", "c"], ["x"])
    0.0
    """
    if not retrieved_ids or not relevant_ids:
        return 0.0

    relevant_set = set(relevant_ids)
    for idx, doc_id in enumerate(retrieved_ids):
        if doc_id in relevant_set:
            return 1.0 / (idx + 1)
    return 0.0


def compute_ndcg(
    retrieved_ids: List[str],
    relevant_ids: List[str],
    k: int,
) -> float:
    """Compute NDCG@k with binary relevance.

    Steps:
      1. Build a binary relevance vector over the top-k retrieved docs.
      2. DCG  = sum( rel[i] / log2(i + 2) )   (i is 0-based)
      3. IDCG = DCG of the ideal ranking (all relevant docs first).
      4. Return DCG / IDCG, or 0.0 when IDCG is 0.

    The ``i + 2`` denominator follows the standard convention where
    position 1 has discount log2(2) = 1.0.

    >>> compute_ndcg(["a", "x", "b", "y", "c"], ["a", "b", "c"], k=5)
    0.886
    """
    if not retrieved_ids or not relevant_ids or k <= 0:
        return 0.0

    relevant_set = set(relevant_ids)
    top_k = retrieved_ids[:k]

    # Binary relevance vector
    rel = [1.0 if doc_id in relevant_set else 0.0 for doc_id in top_k]

    # DCG
    dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rel))

    # IDCG — ideal ranking: sort relevance descending
    ideal_rel = sorted(rel, reverse=True)
    # But ideal should consider all relevant docs that *could* appear in top-k
    num_relevant_in_k = min(len(relevant_ids), k)
    ideal_rel = [1.0] * num_relevant_in_k + [0.0] * (k - num_relevant_in_k)
    ideal_rel = ideal_rel[:k]
    idcg = sum(r / math.log2(i + 2) for i, r in enumerate(ideal_rel))

    if idcg == 0.0:
        return 0.0

    return round(dcg / idcg, 3)


def compute_average_precision(
    retrieved_ids: List[str],
    relevant_ids: List[str],
    k: int,
) -> float:
    """Compute Average Precision @k for a single query.

    AP = (1 / min(R, k)) * sum( Precision@i * rel(i) )

    where R is the total number of relevant documents.

    >>> compute_average_precision(["a", "b", "c", "d", "e"], ["a", "c", "e"], k=5)
    0.756
    """
    if not retrieved_ids or not relevant_ids or k <= 0:
        return 0.0

    relevant_set = set(relevant_ids)
    top_k = retrieved_ids[:k]

    num_relevant_found = 0
    sum_precision = 0.0

    for i, doc_id in enumerate(top_k):
        if doc_id in relevant_set:
            num_relevant_found += 1
            sum_precision += num_relevant_found / (i + 1)

    if num_relevant_found == 0:
        return 0.0

    denominator = min(len(relevant_ids), k)
    return round(sum_precision / denominator, 3)


def compute_hit_rate(
    retrieved_ids: List[str],
    relevant_ids: List[str],
    k: int,
) -> float:
    """Return 1.0 if any relevant doc appears in top-k, else 0.0.

    >>> compute_hit_rate(["a", "b", "c"], ["c"], k=3)
    1.0
    >>> compute_hit_rate(["a", "b", "c"], ["x"], k=3)
    0.0
    """
    if not retrieved_ids or not relevant_ids or k <= 0:
        return 0.0

    relevant_set = set(relevant_ids)
    return 1.0 if any(doc in relevant_set for doc in retrieved_ids[:k]) else 0.0


# -----------------------------------------------------------------------
# Aggregation
# -----------------------------------------------------------------------

def aggregate_metrics(per_query_metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute mean values across all per-query metric dicts.

    Expected input shape (one dict per query)::

        {"mrr": 1.0, "ndcg@5": 0.88, "map@5": 0.75,
         "hit@1": 1.0, "hit@3": 1.0, "hit@5": 1.0}

    Returns a dict with the same keys, each holding the mean value.
    """
    if not per_query_metrics:
        return {}

    # Collect all numeric keys present in the first entry
    keys = [
        k for k, v in per_query_metrics[0].items()
        if isinstance(v, (int, float))
    ]

    result: Dict[str, Any] = {}
    for key in keys:
        values = [m[key] for m in per_query_metrics if key in m]
        if values:
            result[key] = round(statistics.mean(values), 4)

    return result


# -----------------------------------------------------------------------
# Latency
# -----------------------------------------------------------------------

def compute_latency_percentiles(latencies: List[float]) -> Dict[str, float]:
    """Return p50, p90, p99, and mean from a list of latency values (ms).

    >>> result = compute_latency_percentiles([100, 200, 300, 400, 500])
    >>> result["p50_ms"]
    300.0
    """
    if not latencies:
        return {}

    s = sorted(latencies)
    n = len(s)

    return {
        "p50_ms": round(s[n // 2], 2),
        "p90_ms": round(s[min(int(n * 0.9), n - 1)], 2),
        "p99_ms": round(s[min(int(n * 0.99), n - 1)], 2),
        "mean_ms": round(statistics.mean(s), 2),
    }


# -----------------------------------------------------------------------
# Robustness
# -----------------------------------------------------------------------

def compute_robustness_gap(
    by_category: Dict[str, Dict[str, Any]],
    metric_key: str = "top1_rate",
) -> Dict[str, Any]:
    """Measure the performance gap between best and worst query categories.

    *by_category* maps category names to dicts that contain at least
    ``metric_key``.  The gap is expressed in percentage-points.

    >>> cats = {
    ...     "exact": {"top1_rate": 1.0},
    ...     "paraphrase": {"top1_rate": 0.667},
    ...     "risk": {"top1_rate": 0.167},
    ...     "semantic_hard": {"top1_rate": 0.25},
    ... }
    >>> result = compute_robustness_gap(cats)
    >>> result["gap_pp"]
    83.3
    """
    if not by_category:
        return {"gap_pp": 0.0, "best_category": None, "best_value": 0.0,
                "worst_category": None, "worst_value": 0.0}

    entries = []
    for cat_name, cat_data in by_category.items():
        value = cat_data.get(metric_key)
        if value is not None:
            entries.append((cat_name, float(value)))

    if not entries:
        return {"gap_pp": 0.0, "best_category": None, "best_value": 0.0,
                "worst_category": None, "worst_value": 0.0}

    best_cat, best_val = max(entries, key=lambda x: x[1])
    worst_cat, worst_val = min(entries, key=lambda x: x[1])

    gap_pp = round((best_val - worst_val) * 100, 1)

    return {
        "gap_pp": gap_pp,
        "best_category": best_cat,
        "best_value": round(best_val, 4),
        "worst_category": worst_cat,
        "worst_value": round(worst_val, 4),
    }


# -----------------------------------------------------------------------
# Confidence calibration
# -----------------------------------------------------------------------

# Bin definitions: each maps a confidence label to:
#   expected_min / expected_max — thresholds for the "calibrated?" check
#   midpoint — used in ECE computation
_CALIBRATION_BINS: Dict[str, Dict[str, float]] = {
    "high": {"expected_min": 0.80, "midpoint": 0.90},
    "medium": {"expected_min": 0.50, "expected_max": 0.80, "midpoint": 0.65},
    "low": {"expected_max": 0.50, "midpoint": 0.25},
}


def compute_confidence_calibration(
    cases: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Analyse confidence calibration across High / Medium / Low bins.

    Each element in *cases* must have:

    - ``confidence`` — ``"high"`` | ``"medium"`` | ``"low"`` (str)
    - ``hit_top1``  — ``True`` / ``False`` (bool)

    Returns a dict with per-bin stats, ECE, and an overall verdict::

        {
            "high":   {"count": 5,  "actual_accuracy": 0.80, ...},
            "medium": {"count": 40, "actual_accuracy": 0.65, ...},
            "low":    {"count": 15, "actual_accuracy": 0.20, ...},
            "ece": 0.08,
            "overall_calibrated": True,
            "total_cases": 60,
        }

    **ECE** (Expected Calibration Error)::

        ECE = Σ_bin ( |actual_accuracy - midpoint| × count ) / total

    A lower ECE indicates better calibration.

    >>> cases = [{"confidence": "high", "hit_top1": True}] * 4 + \\
    ...         [{"confidence": "high", "hit_top1": False}] * 1
    >>> result = compute_confidence_calibration(cases)
    >>> result["high"]["actual_accuracy"]
    0.8
    """
    if not cases:
        return {
            "high": {"count": 0, "actual_accuracy": None,
                     "expected_min": 0.80, "calibrated": None},
            "medium": {"count": 0, "actual_accuracy": None,
                       "expected_min": 0.50, "calibrated": None},
            "low": {"count": 0, "actual_accuracy": None,
                    "expected_max": 0.50, "calibrated": None},
            "ece": 0.0,
            "overall_calibrated": None,
            "total_cases": 0,
        }

    # Group by confidence level
    bins: Dict[str, List[bool]] = {"high": [], "medium": [], "low": []}
    for c in cases:
        level = str(c.get("confidence", "")).lower()
        if level in bins:
            bins[level].append(bool(c.get("hit_top1", False)))

    total = sum(len(v) for v in bins.values())
    ece_numerator = 0.0
    per_bin: Dict[str, Dict[str, Any]] = {}

    for level, hits in bins.items():
        spec = _CALIBRATION_BINS[level]
        count = len(hits)

        if count == 0:
            per_bin[level] = {
                "count": 0,
                "actual_accuracy": None,
                "calibrated": None,
            }
            # Carry over relevant expected threshold
            if "expected_min" in spec:
                per_bin[level]["expected_min"] = spec["expected_min"]
            if "expected_max" in spec:
                per_bin[level]["expected_max"] = spec["expected_max"]
            continue

        accuracy = round(sum(hits) / count, 4)

        # Calibrated?
        if level == "high":
            calibrated = accuracy >= spec["expected_min"]
        elif level == "medium":
            calibrated = spec["expected_min"] <= accuracy <= spec["expected_max"]
        else:  # low
            calibrated = accuracy <= spec["expected_max"]

        entry: Dict[str, Any] = {
            "count": count,
            "actual_accuracy": accuracy,
            "calibrated": calibrated,
        }
        if "expected_min" in spec:
            entry["expected_min"] = spec["expected_min"]
        if "expected_max" in spec:
            entry["expected_max"] = spec["expected_max"]
        per_bin[level] = entry

        # ECE contribution
        ece_numerator += abs(accuracy - spec["midpoint"]) * count

    ece = round(ece_numerator / total, 4) if total else 0.0

    # Overall: all populated bins must be calibrated
    populated = [v for v in per_bin.values() if v["count"] > 0]
    overall = (
        all(v["calibrated"] for v in populated)
        if populated
        else None
    )

    return {
        **per_bin,
        "ece": ece,
        "overall_calibrated": overall,
        "total_cases": total,
    }
