"""
Phase 2: Integration Tests for Orchestrator ↔ MaturityEngine
=============================================================
Tests data flow from build_report_data() through MaturityEngine
and into report_data for ReportAgent consumption.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdca.orchestrator import build_report_data, _extract_post_findings
from pdca.agents.report_module.maturity_engine import MaturityEngine

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPINGS_PATH = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_mappings.json")
CAPABILITIES_PATH = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_capabilities.json")


# ---------------------------------------------------------------------------
# Test data factory
# ---------------------------------------------------------------------------

def _make_analysis(pre_findings, findings_table):
    """Build minimal analysis dict for testing."""
    pass_count = sum(1 for f in pre_findings if f.get("status") == "PASS")
    fail_count = sum(1 for f in pre_findings if f.get("status") == "FAIL")
    fixed = sum(1 for r in findings_table if r.get("change") == "Fixed")
    return {
        "pre_stats": {
            "total": len(pre_findings),
            "pass": pass_count,
            "fail": fail_count,
            "severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        },
        "post_stats": {
            "pass": sum(1 for r in findings_table if r.get("after") == "PASS"),
            "fail": sum(1 for r in findings_table if r.get("after") == "FAIL"),
        },
        "remediation_stats": {"fixed": fixed, "failed": 0, "manual": 0},
        "findings_table": findings_table,
        "success_findings": [],
        "failed_findings": [],
        "manual_findings": [],
        "raw_pre_findings": pre_findings,
    }


def _make_full_analysis():
    """Analysis with real check_ids that exist in maturity_mappings."""
    pre = [
        {"event_code": "s3_account_level_public_access_blocks", "status": "FAIL", "severity": "HIGH",
         "resource_id": "account", "service": "s3", "finding_uid": "u1"},
        {"event_code": "s3_bucket_level_public_access_block", "status": "FAIL", "severity": "HIGH",
         "resource_id": "bucket-1", "service": "s3", "finding_uid": "u2"},
        {"event_code": "s3_bucket_default_encryption", "status": "PASS", "severity": "MEDIUM",
         "resource_id": "bucket-1", "service": "s3", "finding_uid": "u3"},
    ]
    table = [
        {"stt": 1, "check_id": "s3_account_level_public_access_blocks", "finding": "S3 Public Access Blocks",
         "service": "s3", "resource": "account", "severity": "HIGH",
         "before": "FAIL", "after": "PASS", "change": "Fixed"},
        {"stt": 2, "check_id": "s3_bucket_level_public_access_block", "finding": "S3 Bucket Public Access",
         "service": "s3", "resource": "bucket-1", "severity": "HIGH",
         "before": "FAIL", "after": "PASS", "change": "Fixed"},
        {"stt": 3, "check_id": "s3_bucket_default_encryption", "finding": "S3 Default Encryption",
         "service": "s3", "resource": "bucket-1", "severity": "MEDIUM",
         "before": "PASS", "after": "PASS", "change": "Unchanged"},
    ]
    return _make_analysis(pre, table)


# ============================================================
# Task 2.1 Tests: _extract_post_findings + raw_post_findings
# ============================================================

class TestExtractPostFindings:
    def test_structure(self):
        analysis = _make_full_analysis()
        result = _extract_post_findings(analysis)
        assert len(result) == 3
        for entry in result:
            assert "event_code" in entry
            assert "status" in entry
            assert entry["event_code"] != ""
            assert entry["status"] in ("PASS", "FAIL", "UNKNOWN")

    def test_empty_table(self):
        analysis = {"findings_table": []}
        result = _extract_post_findings(analysis)
        assert result == []

    def test_missing_table(self):
        result = _extract_post_findings({})
        assert result == []

    def test_status_reflects_after(self):
        analysis = _make_full_analysis()
        result = _extract_post_findings(analysis)
        # First 2 were Fixed (FAIL→PASS), third was Unchanged (PASS→PASS)
        assert result[0]["status"] == "PASS"
        assert result[1]["status"] == "PASS"
        assert result[2]["status"] == "PASS"

    def test_change_field_preserved(self):
        analysis = _make_full_analysis()
        result = _extract_post_findings(analysis)
        assert result[0]["change"] == "Fixed"
        assert result[2]["change"] == "Unchanged"


class TestBuildReportDataPostFindings:
    def test_has_raw_post_findings(self):
        analysis = _make_full_analysis()
        data = build_report_data(analysis, {}, {}, "test")
        assert "raw_post_findings" in data
        assert len(data["raw_post_findings"]) == 3

    def test_backward_compatible(self):
        analysis = _make_full_analysis()
        data = build_report_data(analysis, {}, {}, "test")
        # All original fields still present
        for key in ("pre", "post", "findings_table", "success_findings",
                     "failed_findings", "manual_findings", "raw_pre_findings",
                     "environment", "scope"):
            assert key in data, f"Missing key: {key}"

    def test_post_findings_event_code_matches_pre(self):
        analysis = _make_full_analysis()
        data = build_report_data(analysis, {}, {}, "test")
        pre_codes = {f["event_code"] for f in data["raw_pre_findings"]}
        post_codes = {f["event_code"] for f in data["raw_post_findings"]}
        assert pre_codes == post_codes


# ============================================================
# Task 2.2 Tests: MaturityEngine integration in pipeline
# ============================================================

class TestMaturityIntegration:
    def _run_maturity_pipeline(self, analysis):
        """Simulate what report_node does with maturity."""
        data = build_report_data(analysis, {}, {}, "test")

        engine = MaturityEngine(MAPPINGS_PATH, CAPABILITIES_PATH)

        maturity_pre = engine.assess(data.get("raw_pre_findings", []))
        data["maturity_assessment"] = maturity_pre

        raw_post = data.get("raw_post_findings")
        if raw_post:
            maturity_post = engine.assess(raw_post)
            data["maturity_post"] = maturity_post
            data["maturity_delta"] = engine.compute_delta(maturity_pre, maturity_post)
        else:
            data["maturity_post"] = None
            data["maturity_delta"] = None

        return data

    def test_report_data_contains_maturity_keys(self):
        data = self._run_maturity_pipeline(_make_full_analysis())
        assert "maturity_assessment" in data
        assert "maturity_post" in data
        assert "maturity_delta" in data

    def test_maturity_assessment_structure(self):
        data = self._run_maturity_pipeline(_make_full_analysis())
        m = data["maturity_assessment"]
        assert m is not None
        assert "overall_score" in m
        assert "overall_stage" in m
        assert "domains" in m
        assert "coverage" in m

    def test_maturity_engine_called_twice(self):
        data = self._run_maturity_pipeline(_make_full_analysis())
        # Both pre and post should be assessed
        assert data["maturity_assessment"] is not None
        assert data["maturity_post"] is not None
        # Pre had FAILs, post had all PASS → post score >= pre score
        assert data["maturity_post"]["overall_score"] >= data["maturity_assessment"]["overall_score"]

    def test_maturity_delta_computed(self):
        data = self._run_maturity_pipeline(_make_full_analysis())
        delta = data["maturity_delta"]
        assert delta is not None
        assert "overall" in delta
        assert "summary" in delta
        # Score should improve (FAILs fixed)
        assert delta["overall"]["score_delta"] >= 0

    def test_no_post_data_delta_none(self):
        """When findings_table is empty, raw_post_findings is empty → delta still computed but meaningless."""
        analysis = _make_analysis(
            [{"event_code": "s3_account_level_public_access_blocks", "status": "PASS"}],
            []  # no findings_table
        )
        data = self._run_maturity_pipeline(analysis)
        # raw_post_findings is [] (empty but truthy-ish... actually [] is falsy)
        # So maturity_post and delta should be None
        assert data["maturity_post"] is None
        assert data["maturity_delta"] is None

    def test_maturity_fallback_on_error(self):
        """If MaturityEngine fails, report_data should still be usable."""
        analysis = _make_full_analysis()
        data = build_report_data(analysis, {}, {}, "test")

        # Simulate engine failure
        try:
            engine = MaturityEngine("/nonexistent.json", "/also_nonexistent.json")
            raise AssertionError("Should have raised")
        except FileNotFoundError:
            data["maturity_assessment"] = None
            data["maturity_post"] = None
            data["maturity_delta"] = None

        # Report data still complete for non-maturity sections
        assert data["maturity_assessment"] is None
        assert "pre" in data
        assert "post" in data
        assert "findings_table" in data


# ============================================================
# Edge cases
# ============================================================

class TestEdgeCases:
    def test_no_matching_mappings(self):
        """Findings with unknown check_ids → empty maturity assessment."""
        analysis = _make_analysis(
            [{"event_code": "unknown_check_xyz", "status": "PASS"}],
            [{"stt": 1, "check_id": "unknown_check_xyz", "finding": "test",
              "service": "test", "resource": "r1", "severity": "LOW",
              "before": "PASS", "after": "PASS", "change": "Unchanged"}],
        )
        data = build_report_data(analysis, {}, {}, "test")
        engine = MaturityEngine(MAPPINGS_PATH, CAPABILITIES_PATH)
        result = engine.assess(data["raw_pre_findings"])
        assert result["overall_score"] == 0.0
        assert result["coverage"]["assessed"] == 0

    def test_all_findings_pass(self):
        """All PASS findings → high maturity score."""
        engine = MaturityEngine(MAPPINGS_PATH, CAPABILITIES_PATH)
        all_checks = list(engine._check_to_mappings.keys())[:20]
        pre = [{"event_code": c, "status": "PASS"} for c in all_checks]
        table = [
            {"stt": i, "check_id": c, "finding": c, "service": "s3",
             "resource": "r", "severity": "LOW",
             "before": "PASS", "after": "PASS", "change": "Unchanged"}
            for i, c in enumerate(all_checks, 1)
        ]
        analysis = _make_analysis(pre, table)
        data = build_report_data(analysis, {}, {}, "test")

        result = engine.assess(data["raw_pre_findings"])
        assert result["overall_score"] > 80.0


# ============================================================
# Runner
# ============================================================

def _run_tests():
    import traceback

    test_classes = [
        TestExtractPostFindings,
        TestBuildReportDataPostFindings,
        TestMaturityIntegration,
        TestEdgeCases,
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
