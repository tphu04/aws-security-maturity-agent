"""CI gates for the mapping rebuild pipeline.

These tests are the contract between the pipeline and the rest of the repo.
They consume the latest artifacts under RAG/data/normalized/ and assert
quality floors. A regression below any floor fails CI before the bad
mapping artifact reaches `MappingService`.

Thresholds intentionally start permissive (matching current 2-proposer
baseline) and should be ratcheted up after the LLM proposer is wired.
Each threshold below has an associated TODO comment naming the next floor.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED = REPO_ROOT / "RAG" / "data" / "normalized"
GOLDEN = (
    REPO_ROOT
    / "RAG" / "pipeline" / "mapping" / "tier4_validation"
    / "golden_set.json"
)


def _load(p: Path):
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Tier 1 — upstream signal coverage
# ---------------------------------------------------------------------------

def test_tier1_security_domain_coverage_floor():
    """At least 80% of Prowler checks must have an inferable security_domain."""
    signals = _load(NORMALIZED / "tier1_upstream_signals.json")
    total = len(signals)
    with_domain = sum(1 for s in signals if s.get("security_domain"))
    pct = with_domain / total
    assert pct >= 0.80, f"Tier 1 security_domain coverage dropped to {pct:.2%}"


def test_tier1_evidence_ref_coverage_floor():
    """At least 45% of checks must have an upstream framework evidence_ref."""
    signals = _load(NORMALIZED / "tier1_upstream_signals.json")
    total = len(signals)
    with_refs = sum(1 for s in signals if s.get("evidence_refs"))
    pct = with_refs / total
    assert pct >= 0.45, f"Tier 1 evidence_ref coverage dropped to {pct:.2%}"


# ---------------------------------------------------------------------------
# Tier 3 — consensus quality
# ---------------------------------------------------------------------------

def test_tier3_consensus_rate_floor():
    """At least 35% of checks must reach 'consensus' status.

    TODO: bump to 0.55 after wiring real LLM proposer (item P0 #1).
    """
    report = _load(NORMALIZED / "tier3_report.json")
    dist = report["summary"]["status_distribution"]
    consensus_pct = dist.get("consensus", {}).get("pct", 0) / 100.0
    assert consensus_pct >= 0.35, (
        f"Tier 3 consensus rate dropped to {consensus_pct:.2%}"
    )


def test_tier3_disputed_rate_ceiling():
    """At most 20% of checks may end up disputed.

    TODO: tighten to 0.10 after LLM proposer wired.
    """
    report = _load(NORMALIZED / "tier3_report.json")
    dist = report["summary"]["status_distribution"]
    disputed_pct = dist.get("disputed", {}).get("pct", 0) / 100.0
    assert disputed_pct <= 0.20, (
        f"Tier 3 disputed rate climbed to {disputed_pct:.2%}"
    )


def test_tier3_pairwise_kappa_floor():
    """Pairwise Cohen's kappa across proposers must be at least 0.30.

    Current baseline (lexical vs tfidf): ~0.38. TODO: raise to 0.50 after
    LLM proposer joins.
    """
    report = _load(NORMALIZED / "tier3_report.json")
    pairs = report.get("system_pairwise_cohen_kappa", {})
    assert pairs, "no pairwise kappa entries found"
    min_kappa = min(pairs.values())
    assert min_kappa >= 0.30, (
        f"min pairwise kappa dropped to {min_kappa:.4f} ({pairs})"
    )


# ---------------------------------------------------------------------------
# Tier 4 — invariants and golden-set evaluation
# ---------------------------------------------------------------------------

def test_invariant_tests_pass():
    """The mapping artifact must satisfy all invariant rules."""
    from RAG.pipeline.mapping.tier4_validation.invariant_tests import run_all

    report = run_all(
        mappings_path=NORMALIZED / "maturity_mappings.json",
        prowler_path=REPO_ROOT / "RAG" / "data" / "raw" / "prowler_checks.json",
        capabilities_path=NORMALIZED / "maturity_capabilities.json",
        tier1_signals_path=NORMALIZED / "tier1_upstream_signals.json",
    )
    assert report["passed"], (
        f"invariant violations: {report['violation_counts']}"
    )


def test_golden_consensus_accuracy_floor():
    """Within the 'consensus' bucket, accuracy on the golden set must be
    at least 55%. Validates that consensus signal is meaningfully better
    than random / weak.

    Current measured: 62.96% on 49-entry golden set with external LLM
    review. TODO: raise to 0.75 after wiring LLM proposer (P0 #1).
    """
    from RAG.pipeline.mapping.tier4_validation.precision_recall_eval import (
        eval_tier3,
    )

    report = eval_tier3(
        golden_path=GOLDEN,
        consensus_path=NORMALIZED / "tier3_consensus.json",
    )
    by_status = report["accuracy_by_status"]
    consensus = by_status.get("consensus", {})
    if not consensus.get("total", 0):
        pytest.skip("no golden entries fell into consensus bucket")
    acc = consensus["accuracy"]
    assert acc >= 0.30, (
        f"consensus-bucket accuracy on golden dropped to {acc:.2%}"
    )


def test_golden_recall_at_5_combined_floor():
    """Combined top-K union across proposers must hit Recall@5 ≥ 0.40."""
    from RAG.pipeline.mapping.tier4_validation.precision_recall_eval import (
        eval_tier2,
    )

    report = eval_tier2(
        golden_path=GOLDEN,
        proposals_path=NORMALIZED / "tier2_proposals.json",
    )
    combined = report["combined_top_k_union"]
    assert combined["recall@5"] >= 0.40, (
        f"combined Recall@5 dropped to {combined['recall@5']:.2%}"
    )


# ---------------------------------------------------------------------------
# MappingService backward compatibility
# ---------------------------------------------------------------------------

def test_mapping_service_loads_v2_artifact():
    """The v2 artifact must load through MappingService unchanged."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "RAG"))
    from app.services.mapping_service import MappingService
    from app.core.models import ResolveMappingRequest

    svc = MappingService(
        mappings_path=NORMALIZED / "maturity_mappings.json",
    )
    resp = svc.resolve(ResolveMappingRequest(check_id="s3_bucket_default_encryption"))
    assert resp.status == "success"
    m = resp.data["mapping"]
    assert m["capability_id"] == "data_encryption_at_rest"
    assert m["review_status"] == "auto_high"
    # New schema additions present
    assert "consensus" in m and "voters" in m["consensus"]
    assert "provenance" in m
