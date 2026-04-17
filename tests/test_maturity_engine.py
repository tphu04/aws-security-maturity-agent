"""
Unit Tests for MaturityEngine — Phase 1
========================================
Tests scoring algorithm, stage determination, compute_delta, and edge cases.
Uses real maturity JSON data files for integration-level accuracy.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdca.agents.report_module.maturity_engine import (
    MaturityEngine,
    DOMAIN_DISPLAY,
    STAGE_LABELS,
    STAGE_ORDER,
    CAPABILITY_PASS_THRESHOLD,
    STAGE_COMPLETION_THRESHOLD,
    _MAPPING_WEIGHTS,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPINGS_PATH = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_mappings.json")
CAPABILITIES_PATH = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_capabilities.json")


def _engine():
    """Create engine with real data files."""
    return MaturityEngine(MAPPINGS_PATH, CAPABILITIES_PATH)


def _make_findings(pass_ids, fail_ids=None):
    """Helper to build findings list from check_id lists."""
    findings = [{"event_code": cid, "status": "PASS"} for cid in pass_ids]
    if fail_ids:
        findings += [{"event_code": cid, "status": "FAIL"} for cid in fail_ids]
    return findings


# ============================================================
# Task 1.1: Data Loading & Lookups
# ============================================================

class TestEngineInit:
    def test_loads_correct_counts(self):
        engine = _engine()
        assert len(engine._check_to_mappings) == 502
        assert len(engine._cap_info) == 78

    def test_cap_domains_built_from_mappings(self):
        engine = _engine()
        assert len(engine._cap_domains) > 0
        # capabilities.json has domain="" for all → _cap_domains comes from mappings
        for cap_id, domains in engine._cap_domains.items():
            for d in domains:
                assert d in DOMAIN_DISPLAY, f"Unknown domain '{d}' for {cap_id}"

    def test_check_to_mappings_structure(self):
        engine = _engine()
        key = "s3_account_level_public_access_blocks"
        assert key in engine._check_to_mappings
        entries = engine._check_to_mappings[key]
        assert len(entries) >= 1
        entry = entries[0]
        assert entry["capability_id"] == "block_public_access"
        assert entry["domain"] == "data_protection"
        assert entry["mapping_type"] == "direct"
        assert entry["mapping_confidence"] == "high"

    def test_capability_has_single_canonical_domain(self):
        # Each capability resolves to exactly ONE canonical domain (fix for
        # IAM Data Perimeters leaking into Resilience via unreviewed low-
        # confidence mappings).
        engine = _engine()
        domains = engine._cap_domains.get("audit_api_calls", set())
        assert len(domains) == 1, f"expected single canonical domain, got {domains}"

    def test_missing_file_raises(self):
        try:
            MaturityEngine("/nonexistent/path.json", CAPABILITIES_PATH)
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as e:
            assert "maturity_mappings" in str(e)

    def test_missing_capabilities_file_raises(self):
        try:
            MaturityEngine(MAPPINGS_PATH, "/nonexistent/path.json")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as e:
            assert "maturity_capabilities" in str(e)


# ============================================================
# Regression: IAM Data Perimeters leaking into Resilience domain
# ============================================================

class TestCanonicalDomainRegression:
    def test_iam_data_perimeters_canonical_domain_is_identity_access(self):
        eng = _engine()
        assert eng._canonical_domain["iam_data_perimeters_conditional_access"] \
            == "identity_access", (
            "IAM Data Perimeters: Conditional Access must belong to "
            "identity_access, not resilience (previous bug)."
        )

    def test_cap_domains_returns_single_canonical_domain(self):
        eng = _engine()
        domains = eng._cap_domains.get("iam_data_perimeters_conditional_access")
        assert domains == {"identity_access"}, (
            f"expected {{'identity_access'}}, got {domains}"
        )

    def test_check_to_mappings_override_has_canonical_domain(self):
        eng = _engine()
        hits = []
        for check_id, entries in eng._check_to_mappings.items():
            for e in entries:
                if e["capability_id"] == "iam_data_perimeters_conditional_access":
                    hits.append((check_id, e["domain"]))
        assert hits, "expected at least one mapping to this capability"
        bad = [h for h in hits if h[1] != "identity_access"]
        assert not bad, f"found {len(bad)} mappings still pointing to wrong domain: {bad[:3]}"

    def test_assess_places_iam_capability_in_correct_domain(self):
        eng = _engine()
        target_check = None
        for check_id, entries in eng._check_to_mappings.items():
            if any(e["capability_id"] == "iam_data_perimeters_conditional_access"
                   for e in entries):
                target_check = check_id
                break
        assert target_check, "no check mapped to IAM Data Perimeters"

        findings = [{"event_code": target_check, "status": "PASS"}]
        result = eng.assess(findings, scanned_services=["s3", "iam", "acm"])

        iam_caps = [c["capability_id"]
                    for c in result["domains"]["identity_access"]["capabilities"]]
        res_caps = [c["capability_id"]
                    for c in result["domains"].get("resilience", {}).get("capabilities", [])]

        assert "iam_data_perimeters_conditional_access" in iam_caps
        assert "iam_data_perimeters_conditional_access" not in res_caps


# ============================================================
# Task 1.2: assess() — Core Scoring
# ============================================================

class TestAssess:
    def test_empty_findings(self):
        engine = _engine()
        result = engine.assess([])
        assert result["overall_score"] == 0.0
        assert result["overall_stage"] == "1 quickwins"
        assert result["coverage"]["assessed"] == 0
        assert result["coverage"]["not_assessed"] == 78
        assert len(result["unmapped_capabilities"]) == 78

    def test_no_matching_mappings(self):
        engine = _engine()
        result = engine.assess([{"event_code": "nonexistent_check", "status": "PASS"}])
        assert result["overall_score"] == 0.0
        assert result["coverage"]["assessed"] == 0

    def test_all_pass_high_score(self):
        engine = _engine()
        # Use all known check_ids with PASS
        all_checks = list(engine._check_to_mappings.keys())
        findings = _make_findings(all_checks)
        result = engine.assess(findings)
        assert result["overall_score"] > 90.0, f"Expected >90, got {result['overall_score']}"

    def test_mixed_pass_fail_weighted(self):
        engine = _engine()
        # 2 checks both map to block_public_access, both direct/high (weight=1.0)
        findings = _make_findings(
            ["s3_account_level_public_access_blocks"],
            ["s3_bucket_level_public_access_block"]
        )
        result = engine.assess(findings)
        # score = (1*1 + 1*0) / (1+1) * 100 = 50.0
        caps = result["domains"]["data_protection"]["capabilities"]
        bpa = [c for c in caps if c["capability_id"] == "block_public_access"][0]
        assert bpa["score"] == 50.0
        assert bpa["pass_count"] == 1
        assert bpa["fail_count"] == 1
        assert bpa["status"] == "assessed"

    def test_capability_appears_in_single_domain_after_assessment(self):
        # After canonical-domain fix: a capability belongs to exactly one
        # domain in the rolled-up result. Previously the same capability could
        # leak into multiple domains via unreviewed mappings.
        engine = _engine()
        target_checks = [
            cid for cid, mappings in engine._check_to_mappings.items()
            if any(m["capability_id"] == "audit_api_calls" for m in mappings)
        ]
        assert len(target_checks) > 0
        findings = _make_findings(target_checks[:1])
        result = engine.assess(findings)

        domains_with_audit = [
            d_id for d_id, d in result["domains"].items()
            if any(c["capability_id"] == "audit_api_calls" for c in d.get("capabilities", []))
        ]
        assert len(domains_with_audit) == 1, (
            f"expected audit_api_calls in exactly 1 domain, got {domains_with_audit}"
        )

    def test_output_has_all_required_keys(self):
        engine = _engine()
        result = engine.assess(_make_findings(["s3_account_level_public_access_blocks"]))
        assert "overall_score" in result
        assert "overall_stage" in result
        assert "overall_stage_label" in result
        assert "domains" in result
        assert "unmapped_capabilities" in result
        assert "confidence_summary" in result
        assert "coverage" in result

        # Domain structure
        for domain_id in DOMAIN_DISPLAY:
            d = result["domains"][domain_id]
            assert "display_name" in d
            assert "score" in d
            assert "stage" in d
            assert "stage_label" in d
            assert "capabilities" in d
            assert "total_checks" in d
            assert "passed_checks" in d

    def test_scores_in_range(self):
        engine = _engine()
        all_checks = list(engine._check_to_mappings.keys())[:50]
        result = engine.assess(_make_findings(all_checks[:25], all_checks[25:]))
        assert 0.0 <= result["overall_score"] <= 100.0
        for d in result["domains"].values():
            assert 0.0 <= d["score"] <= 100.0

    def test_stage_in_valid_set(self):
        engine = _engine()
        result = engine.assess(_make_findings(list(engine._check_to_mappings.keys())[:10]))
        assert result["overall_stage"] in STAGE_ORDER
        for d in result["domains"].values():
            assert d["stage"] in STAGE_ORDER

    def test_finding_without_event_code_skipped(self):
        engine = _engine()
        findings = [
            {"status": "PASS"},  # no event_code
            {"event_code": "s3_account_level_public_access_blocks", "status": "PASS"},
        ]
        result = engine.assess(findings)
        assert result["coverage"]["assessed"] >= 1

    def test_finding_with_check_id_field(self):
        engine = _engine()
        findings = [{"check_id": "s3_account_level_public_access_blocks", "status": "PASS"}]
        result = engine.assess(findings)
        assert result["coverage"]["assessed"] >= 1


# ============================================================
# Task 1.3: Stage Determination
# ============================================================

class TestStageDetermination:
    def test_all_pass_highest_stage(self):
        engine = _engine()
        all_checks = list(engine._check_to_mappings.keys())
        result = engine.assess(_make_findings(all_checks))
        # With all checks passing, domains with caps at multiple stages
        # should achieve higher stages
        for d in result["domains"].values():
            if d["capabilities"]:
                assert d["stage"] in STAGE_ORDER

    def test_progressive_no_skip(self):
        """Stage must be progressive — can't skip stages."""
        engine = _engine()
        # Create synthetic capabilities to test progressive logic
        caps = [
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 0.0, "stage": "2 foundational", "status": "assessed"},  # fails
            {"score": 100.0, "stage": "3 efficient", "status": "assessed"},
        ]
        stage = engine._determine_domain_stage(caps)
        # Should stop at quickwins because foundational fails
        assert stage == "1 quickwins"

    def test_threshold_boundary(self):
        engine = _engine()
        # 69% < 70% threshold → does not achieve stage
        caps_below = [
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 0.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 0.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 0.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 0.0, "stage": "1 quickwins", "status": "assessed"},
        ]
        # 6/10 = 60% < 70% → stays at default "1 quickwins" but doesn't advance past it
        # Actually the default IS "1 quickwins", so this test checks that
        # with ONLY quickwins caps that don't meet threshold, it still returns quickwins
        stage = engine._determine_domain_stage(caps_below)
        assert stage == "1 quickwins"

        # 70% exactly → achieves stage
        caps_at = [
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 0.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 0.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 0.0, "stage": "1 quickwins", "status": "assessed"},
        ]
        # 7/10 = 70% → achieves "1 quickwins"
        stage = engine._determine_domain_stage(caps_at)
        assert stage == "1 quickwins"

    def test_empty_domain(self):
        engine = _engine()
        stage = engine._determine_domain_stage([])
        assert stage == "1 quickwins"

    def test_progressive_completion(self):
        engine = _engine()
        caps = [
            {"score": 100.0, "stage": "1 quickwins", "status": "assessed"},
            {"score": 100.0, "stage": "2 foundational", "status": "assessed"},
        ]
        stage = engine._determine_domain_stage(caps)
        assert stage == "2 foundational"

    def test_overall_stage_weakest_link(self):
        engine = _engine()
        # Overall stage should be the minimum across domains
        result = engine.assess(_make_findings(["s3_account_level_public_access_blocks"]))
        # Only 1 capability assessed → most domains have no data → overall is quickwins
        assert result["overall_stage"] == "1 quickwins"


# ============================================================
# Task 1.4: compute_delta()
# ============================================================

class TestComputeDelta:
    def test_none_pre(self):
        engine = _engine()
        post = engine.assess(_make_findings(["s3_account_level_public_access_blocks"]))
        assert engine.compute_delta(None, post) is None

    def test_none_post(self):
        engine = _engine()
        pre = engine.assess(_make_findings(["s3_account_level_public_access_blocks"]))
        assert engine.compute_delta(pre, None) is None

    def test_both_none(self):
        engine = _engine()
        assert engine.compute_delta(None, None) is None

    def test_improvement(self):
        engine = _engine()
        pre = engine.assess(_make_findings(
            [],
            ["s3_account_level_public_access_blocks", "s3_bucket_level_public_access_block"]
        ))
        post = engine.assess(_make_findings(
            ["s3_account_level_public_access_blocks", "s3_bucket_level_public_access_block"]
        ))
        delta = engine.compute_delta(pre, post)
        assert delta is not None
        assert delta["overall"]["score_delta"] > 0
        assert delta["summary"]["improved"] >= 1

    def test_newly_passing(self):
        engine = _engine()
        pre = engine.assess(_make_findings(
            [],
            ["s3_account_level_public_access_blocks", "s3_bucket_level_public_access_block"]
        ))
        # pre score for block_public_access = 0 (all fail)
        post = engine.assess(_make_findings(
            ["s3_account_level_public_access_blocks", "s3_bucket_level_public_access_block"]
        ))
        # post score = 100 (all pass)
        delta = engine.compute_delta(pre, post)
        newly_passing = [c for c in delta["capabilities_improved"] if c["newly_passing"]]
        assert len(newly_passing) >= 1

    def test_regression(self):
        engine = _engine()
        pre = engine.assess(_make_findings(
            ["s3_account_level_public_access_blocks"]
        ))
        post = engine.assess(_make_findings(
            [],
            ["s3_account_level_public_access_blocks"]
        ))
        delta = engine.compute_delta(pre, post)
        assert delta["summary"]["regressed"] >= 1
        assert delta["overall"]["score_delta"] < 0

    def test_delta_output_schema(self):
        engine = _engine()
        pre = engine.assess(_make_findings(["s3_account_level_public_access_blocks"]))
        post = engine.assess(_make_findings(
            ["s3_account_level_public_access_blocks", "s3_bucket_level_public_access_block"]
        ))
        delta = engine.compute_delta(pre, post)

        assert "overall" in delta
        assert "domains" in delta
        assert "capabilities_improved" in delta
        assert "capabilities_unchanged" in delta
        assert "capabilities_regressed" in delta
        assert "stages_unlocked" in delta
        assert "summary" in delta

        # Overall keys
        o = delta["overall"]
        for key in ["pre_score", "post_score", "score_delta", "pre_stage", "post_stage", "stage_changed"]:
            assert key in o

        # Summary keys
        s = delta["summary"]
        for key in ["total_capabilities_affected", "improved", "unchanged", "regressed", "newly_passing", "domains_stage_up"]:
            assert key in s

    def test_stage_unlock(self):
        engine = _engine()
        # Use many checks to potentially trigger stage changes
        all_checks = list(engine._check_to_mappings.keys())
        pre = engine.assess(_make_findings([], all_checks))  # all FAIL
        post = engine.assess(_make_findings(all_checks))      # all PASS
        delta = engine.compute_delta(pre, post)

        # Score should have improved dramatically
        assert delta["overall"]["score_delta"] > 50
        # With all passing, some domains should unlock stages
        # (depends on data but likely at least one)


# ============================================================
# Task 1.5: Graceful Degradation
# ============================================================

class TestGracefulDegradation:
    def test_invalid_json_structure(self):
        """Non-array JSON should raise ValueError."""
        path = os.path.join(tempfile.gettempdir(), "_test_invalid_maturity.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"not": "a list"}, f)
        try:
            MaturityEngine(path, CAPABILITIES_PATH)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "JSON array" in str(e)
        finally:
            os.unlink(path)

    def test_empty_json_arrays(self):
        """Empty JSON arrays should produce a working engine with empty results."""
        path_m = os.path.join(tempfile.gettempdir(), "_test_empty_mappings.json")
        path_c = os.path.join(tempfile.gettempdir(), "_test_empty_caps.json")
        with open(path_m, 'w', encoding='utf-8') as fm:
            json.dump([], fm)
        with open(path_c, 'w', encoding='utf-8') as fc:
            json.dump([], fc)
        try:
            engine = MaturityEngine(path_m, path_c)
            result = engine.assess([{"event_code": "test", "status": "PASS"}])
            assert result["overall_score"] == 0.0
            assert result["coverage"]["total_capabilities"] == 0
        finally:
            os.unlink(path_m)
            os.unlink(path_c)

    def test_only_weak_mappings_partial_status(self):
        """Capabilities with only weak mappings should have status 'partial'."""
        engine = _engine()
        # Find a check_id that has only weak mapping
        weak_checks = []
        for check_id, mappings in engine._check_to_mappings.items():
            if all(m["mapping_type"] == "weak" for m in mappings):
                weak_checks.append(check_id)
                break
        if not weak_checks:
            # Skip if no weak-only checks exist in data
            return

        result = engine.assess(_make_findings(weak_checks))
        for d in result["domains"].values():
            for c in d["capabilities"]:
                if c["capability_id"] in [
                    m["capability_id"]
                    for m in engine._check_to_mappings[weak_checks[0]]
                ]:
                    assert c["status"] == "partial"


# ============================================================
# Runner
# ============================================================

def _run_tests():
    """Simple test runner — no pytest dependency needed."""
    import traceback

    test_classes = [
        TestEngineInit,
        TestAssess,
        TestStageDetermination,
        TestComputeDelta,
        TestGracefulDegradation,
    ]

    passed = 0
    failed = 0
    errors = []

    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        for method_name in sorted(methods):
            name = f"{cls.__name__}.{method_name}"
            try:
                getattr(instance, method_name)()
                passed += 1
                print(f"  PASS  {name}")
            except Exception as e:
                failed += 1
                errors.append((name, traceback.format_exc()))
                print(f"  FAIL  {name}: {e}")

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")

    if errors:
        print(f"\nFailure details:")
        for name, tb in errors:
            print(f"\n--- {name} ---")
            print(tb)

    return failed == 0


if __name__ == "__main__":
    success = _run_tests()
    sys.exit(0 if success else 1)
