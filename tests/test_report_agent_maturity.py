"""
Phase 5: Tests for Report Agent Maturity Integration
=====================================================
Tests mode selection, fix metrics, residual risks,
chart integration, LLM section integration, and run() flow.
"""
import copy
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdca.agents.report_agent import (
    ReportAgent,
    FULL_MIN_DOMAINS, FULL_MIN_COVERAGE_PCT, PARTIAL_MIN_COVERAGE_PCT,
    PARTIAL_MIN_CAPABILITIES,
)
from pdca.agents.report_module.maturity_engine import MaturityEngine

# ---------------------------------------------------------------------------
# Paths & Mock LLM
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPINGS_PATH = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_mappings.json")
CAPABILITIES_PATH = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_capabilities.json")


class MockLLMResponse:
    def __init__(self, content):
        self.content = content


class MockLLM:
    def invoke(self, prompt):
        return MockLLMResponse("Mock LLM output for testing purposes.")


def _engine():
    return MaturityEngine(MAPPINGS_PATH, CAPABILITIES_PATH)


def _agent(tmpdir):
    return ReportAgent(
        output_path=os.path.join(tmpdir, "report.md"),
        llm_config={"llm": MockLLM()},
    )


def _base_data():
    """Minimal valid report_data for ReportAgent."""
    return {
        "pre": {
            "total": 10, "pass": 5, "fail": 5,
            "severity": {"critical": 1, "high": 2, "medium": 1, "low": 1},
        },
        "post": {
            "initial_pass": 5, "initial_fail": 5,
            "final_pass": 8, "final_fail": 2,
            "fixed": 3, "failed": 1, "manual": 1,
        },
        "environment": {"account_id": "123456789012", "region": "ap-southeast-1", "buckets": []},
        "scope": {"services": ["s3"], "date": "2026-04-15", "user_request": "test"},
        "findings_table": [
            {"stt": 1, "check_id": "s3_bucket_encryption", "finding": "Encryption", "service": "s3",
             "resource": "bucket-1", "severity": "HIGH", "before": "FAIL", "after": "PASS", "change": "Fixed"},
            {"stt": 2, "check_id": "s3_mfa_delete", "finding": "MFA Delete", "service": "s3",
             "resource": "bucket-2", "severity": "CRITICAL", "before": "FAIL", "after": "FAIL",
             "change": "Still Failing (ManualRequired)"},
            {"stt": 3, "check_id": "s3_versioning", "finding": "Versioning", "service": "s3",
             "resource": "bucket-3", "severity": "MEDIUM", "before": "FAIL", "after": "FAIL",
             "change": "Still Failing (RemediationFailed)"},
        ],
        "success_findings": [],
        "failed_findings": [],
        "manual_findings": [],
        "raw_pre_findings": [
            {"event_code": "s3_bucket_encryption", "status": "FAIL", "severity": "HIGH"},
            {"event_code": "s3_mfa_delete", "status": "FAIL", "severity": "CRITICAL"},
            {"event_code": "s3_versioning", "status": "FAIL", "severity": "MEDIUM"},
        ],
    }


# ============================================================
# Task 5.1: _determine_report_mode()
# ============================================================

class TestDetermineReportMode:
    def test_none_returns_focused(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            assert agent._determine_report_mode(None) == "focused"
        finally:
            shutil.rmtree(d)

    def test_full_mode(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            engine = _engine()
            all_checks = list(engine._check_to_mappings.keys())
            all_services = sorted(set(c.split("_")[0].lower() for c in all_checks))
            maturity = engine.assess([{"event_code": c, "status": "PASS"} for c in all_checks],
                                     scanned_services=all_services)
            mode = agent._determine_report_mode(maturity)
            assert mode == "full", f"Expected full, got {mode}"
        finally:
            shutil.rmtree(d)

    def test_partial_mode(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            engine = _engine()
            all_checks = list(engine._check_to_mappings.keys())
            # 20 checks gives ~7 assessed, 4 domains → partial (not enough for full)
            maturity = engine.assess([{"event_code": c, "status": "PASS"} for c in all_checks[:20]],
                                     scanned_services=["s3", "iam", "cloudtrail", "ec2", "rds"])
            mode = agent._determine_report_mode(maturity)
            cov = maturity["coverage"]
            assessed = cov["assessed"] + cov["partial"]
            assert mode == "partial", f"Expected partial, got {mode} (assessed={assessed})"
        finally:
            shutil.rmtree(d)

    def test_focused_mode_few_caps(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            engine = _engine()
            all_checks = list(engine._check_to_mappings.keys())
            # 5 checks → 1 assessed cap → focused
            maturity = engine.assess([{"event_code": c, "status": "PASS"} for c in all_checks[:5]])
            mode = agent._determine_report_mode(maturity)
            assert mode == "focused", f"Expected focused, got {mode}"
        finally:
            shutil.rmtree(d)

    def test_empty_assessment(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            engine = _engine()
            maturity = engine.assess([])
            assert agent._determine_report_mode(maturity) == "focused"
        finally:
            shutil.rmtree(d)


# ============================================================
# Task 5.2: Fix Metrics & Residual Risks
# ============================================================

class TestFixMetrics:
    def test_basic_metrics(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            data = _base_data()
            metrics = agent._compute_fix_metrics(data)
            assert metrics["total_findings"] == 10
            assert metrics["total_fail_pre"] == 5
            assert metrics["fixed"] == 3
            assert metrics["fix_rate_pct"] == 60.0  # 3/5 * 100
        finally:
            shutil.rmtree(d)

    def test_division_by_zero(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            data = copy.deepcopy(_base_data())
            data["pre"] = {"total": 0, "pass": 0, "fail": 0, "severity": {}}
            data["post"] = {"initial_pass": 0, "initial_fail": 0, "final_pass": 0,
                           "final_fail": 0, "fixed": 0, "failed": 0, "manual": 0}
            metrics = agent._compute_fix_metrics(data)
            assert metrics["fix_rate_pct"] == 0.0
            assert metrics["residual_rate_pct"] == 0.0
            assert metrics["pre_pass_rate_pct"] == 0.0
        finally:
            shutil.rmtree(d)

    def test_all_pass_no_fixes(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            data = copy.deepcopy(_base_data())
            data["pre"] = {"total": 10, "pass": 10, "fail": 0, "severity": {}}
            data["post"] = {"initial_pass": 10, "initial_fail": 0, "final_pass": 10,
                           "final_fail": 0, "fixed": 0, "failed": 0, "manual": 0}
            metrics = agent._compute_fix_metrics(data)
            assert metrics["fix_rate_pct"] == 0.0
            assert metrics["pre_pass_rate_pct"] == 100.0
        finally:
            shutil.rmtree(d)


class TestResidualRisks:
    def test_classification(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            data = _base_data()
            residual = agent._classify_residual_risks(data)
            assert len(residual["auto_fix_failed"]) == 1   # RemediationFailed
            assert len(residual["manual_required"]) == 1    # ManualRequired
            assert residual["total"] == 2
        finally:
            shutil.rmtree(d)

    def test_severity_breakdown(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            data = _base_data()
            residual = agent._classify_residual_risks(data)
            assert residual["severity_breakdown"]["critical"] == 1
            assert residual["severity_breakdown"]["medium"] == 1
        finally:
            shutil.rmtree(d)

    def test_all_fixed_empty(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            data = copy.deepcopy(_base_data())
            # All findings PASS after remediation
            for f in data["findings_table"]:
                f["after"] = "PASS"
                f["change"] = "Fixed"
            residual = agent._classify_residual_risks(data)
            assert residual["total"] == 0
        finally:
            shutil.rmtree(d)

    def test_empty_table(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            data = copy.deepcopy(_base_data())
            data["findings_table"] = []
            residual = agent._classify_residual_risks(data)
            assert residual["total"] == 0
        finally:
            shutil.rmtree(d)


# ============================================================
# Task 5.3: Maturity Charts Integration
# ============================================================

class TestMaturityCharts:
    def test_full_mode_creates_radar_and_stage(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            engine = _engine()
            maturity = engine.assess([
                {"event_code": c, "status": "PASS"}
                for c in list(engine._check_to_mappings.keys())
            ])
            charts = agent._make_maturity_charts(maturity, "full", d)
            assert "radar" in charts
            assert "stage_progress" in charts
            assert os.path.exists(os.path.join(d, charts["radar"]))
            assert os.path.exists(os.path.join(d, charts["stage_progress"]))
        finally:
            shutil.rmtree(d)

    def test_partial_mode_no_radar(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            engine = _engine()
            maturity = engine.assess([
                {"event_code": c, "status": "PASS"}
                for c in list(engine._check_to_mappings.keys())[:20]
            ])
            charts = agent._make_maturity_charts(maturity, "partial", d)
            assert "radar" not in charts
            assert "stage_progress" in charts
        finally:
            shutil.rmtree(d)

    def test_delta_chart_created(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            engine = _engine()
            checks = list(engine._check_to_mappings.keys())[:15]
            pre = engine.assess([{"event_code": c, "status": "FAIL"} for c in checks])
            post = engine.assess([{"event_code": c, "status": "PASS"} for c in checks])
            delta = engine.compute_delta(pre, post)
            charts = agent._make_post_remediation_charts(delta, d)
            assert "maturity_delta" in charts
            assert os.path.exists(os.path.join(d, charts["maturity_delta"]))
        finally:
            shutil.rmtree(d)


# ============================================================
# Task 5.4: LLM Sections Integration
# ============================================================

class TestMaturityLLMSections:
    def test_full_mode_all_sections(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            engine = _engine()
            maturity = engine.assess([
                {"event_code": c, "status": "PASS"}
                for c in list(engine._check_to_mappings.keys())
            ])
            sections = agent._write_maturity_llm_sections(maturity, "full")
            assert "maturity_overview" in sections
            assert "domain_assessments" in sections
            assert "maturity_roadmap" in sections
            assert len(sections["domain_assessments"]) == 5  # all 5 domains
        finally:
            shutil.rmtree(d)

    def test_partial_mode_skips_empty_domains(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            engine = _engine()
            # Only a few checks → some domains have no data
            maturity = engine.assess([
                {"event_code": c, "status": "PASS"}
                for c in list(engine._check_to_mappings.keys())[:20]
            ])
            sections = agent._write_maturity_llm_sections(maturity, "partial")
            assert "domain_assessments" in sections
            # Should have fewer than 5 domain assessments
            assert len(sections["domain_assessments"]) <= 5
        finally:
            shutil.rmtree(d)

    def test_post_remediation_sections(self):
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            fix_metrics = {
                "fix_rate_pct": 80.0, "auto_success_rate_pct": 90.0,
                "pre_pass_rate_pct": 40.0, "post_pass_rate_pct": 80.0,
                "pass_rate_delta": 40.0, "residual_fail": 2, "residual_rate_pct": 10.0,
            }
            residual = {"auto_fix_failed": [], "manual_required": [],
                       "unchanged": [], "severity_breakdown": {}, "total": 0}
            sections = agent._write_post_remediation_llm_sections(
                fix_metrics, residual, None, "focused"
            )
            assert "post_remediation_analysis" in sections
            assert "action_plan" in sections
        finally:
            shutil.rmtree(d)


# ============================================================
# Task 5.5: Full run() Integration
# ============================================================

class TestRunIntegration:
    def test_focused_mode_no_maturity(self):
        """run() without maturity data → focused mode, backward compatible."""
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            data = _base_data()
            result = agent.run(data)
            assert "html" in result
            assert os.path.exists(result["html"])
        finally:
            shutil.rmtree(d)

    def test_full_mode_with_maturity(self):
        """run() with full maturity data → full mode."""
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            engine = _engine()
            all_checks = list(engine._check_to_mappings.keys())
            all_services = sorted(set(c.split("_")[0].lower() for c in all_checks))

            # Build maturity data
            maturity_pre = engine.assess([
                {"event_code": c, "status": "PASS"} for c in all_checks[:300]
            ] + [{"event_code": c, "status": "FAIL"} for c in all_checks[300:]],
                scanned_services=all_services)
            maturity_post = engine.assess([
                {"event_code": c, "status": "PASS"} for c in all_checks
            ], scanned_services=all_services)
            maturity_delta = engine.compute_delta(maturity_pre, maturity_post)

            data = _base_data()
            data["maturity_assessment"] = maturity_pre
            data["maturity_post"] = maturity_post
            data["maturity_delta"] = maturity_delta

            result = agent.run(data)
            assert "html" in result
            assert os.path.exists(result["html"])
            # Check that charts were generated
            assert os.path.exists(os.path.join(d, "charts", "maturity_radar.png"))
            assert os.path.exists(os.path.join(d, "charts", "stage_progress.png"))
            assert os.path.exists(os.path.join(d, "charts", "maturity_delta.png"))
        finally:
            shutil.rmtree(d)

    def test_backward_compatible_no_maturity_keys(self):
        """run() works when maturity keys are completely absent."""
        d = tempfile.mkdtemp()
        try:
            agent = _agent(d)
            data = _base_data()
            # Explicitly no maturity keys
            assert "maturity_assessment" not in data
            result = agent.run(data)
            assert "html" in result
        finally:
            shutil.rmtree(d)


# ============================================================
# Runner
# ============================================================

def _run_tests():
    import traceback

    test_classes = [
        TestDetermineReportMode,
        TestFixMetrics,
        TestResidualRisks,
        TestMaturityCharts,
        TestMaturityLLMSections,
        TestRunIntegration,
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
