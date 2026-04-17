"""
Phase X — Task X.2: End-to-End Testing for all 3 report modes
==============================================================
Generates actual HTML reports and validates content/structure.
"""
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdca.agents.report_agent import ReportAgent
from pdca.agents.report_module.maturity_engine import MaturityEngine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPINGS = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_mappings.json")
CAPS = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_capabilities.json")


class MockLLMResponse:
    def __init__(self, c):
        self.content = c

class MockLLM:
    def invoke(self, p):
        return MockLLMResponse("Mock analysis response for testing.")


def _engine():
    return MaturityEngine(MAPPINGS, CAPS)


def _base_data():
    engine = _engine()
    all_checks = list(engine._check_to_mappings.keys())
    return {
        "pre": {"total": 20, "pass": 8, "fail": 12,
                "severity": {"critical": 2, "high": 4, "medium": 3, "low": 3}},
        "post": {"initial_pass": 8, "initial_fail": 12, "final_pass": 16,
                 "final_fail": 4, "fixed": 8, "failed": 1, "manual": 3},
        "environment": {"account_id": "123456789012", "region": "ap-southeast-1", "buckets": ["b1"]},
        "scope": {"services": ["s3"], "date": "2026-04-15", "user_request": "test"},
        "findings_table": [
            {"stt": 1, "check_id": "s3_enc", "finding": "Encryption", "service": "s3",
             "resource": "b1", "severity": "HIGH", "before": "FAIL", "after": "PASS", "change": "Fixed"},
            {"stt": 2, "check_id": "s3_mfa", "finding": "MFA Delete", "service": "s3",
             "resource": "b2", "severity": "CRITICAL", "before": "FAIL", "after": "FAIL",
             "change": "Still Failing (ManualRequired)"},
        ],
        "success_findings": [], "failed_findings": [], "manual_findings": [],
        "raw_pre_findings": [
            {"event_code": c, "status": "PASS" if i < 8 else "FAIL", "severity": "HIGH",
             "finding_uid": f"u{i}", "service": "s3", "resource_id": f"r{i}",
             "description": f"Check {c}"}
            for i, c in enumerate(all_checks[:20])
        ],
    }


def _run_agent(tmpdir, data):
    agent = ReportAgent(
        output_path=os.path.join(tmpdir, "report.md"),
        llm_config={"llm": MockLLM()},
    )
    return agent.run(data)


class TestFullMode:
    def test_full_mode_report(self):
        d = tempfile.mkdtemp()
        try:
            engine = _engine()
            all_checks = list(engine._check_to_mappings.keys())
            all_services = sorted(set(c.split("_")[0].lower() for c in all_checks))
            data = _base_data()
            m_pre = engine.assess(
                [{"event_code": c, "status": "PASS"} for c in all_checks[:300]]
                + [{"event_code": c, "status": "FAIL"} for c in all_checks[300:]],
                scanned_services=all_services,
            )
            m_post = engine.assess([{"event_code": c, "status": "PASS"} for c in all_checks],
                                   scanned_services=all_services)
            data["maturity_assessment"] = m_pre
            data["maturity_post"] = m_post
            data["maturity_delta"] = engine.compute_delta(m_pre, m_post)

            result = _run_agent(d, data)
            html = open(result["html"], encoding="utf-8").read()

            assert "MỨC ĐỘ TRƯỞNG THÀNH" in html
            assert "stage-badge" in html
            assert "Mức độ Trưởng thành Bảo mật" in html
            assert "maturity_radar.png" in html
            assert "stage_progress.png" in html
            assert "domain-card" in html
            assert "capability-table" in html
            assert "Lộ trình Cải thiện" in html
            assert "Tác động lên Mức độ Trưởng thành" in html
            assert "maturity_delta.png" in html
            assert "metric-card" in html
            assert "Khuyến nghị Chiến lược" in html
            assert "Kế hoạch Hành động" in html

            # Chart files exist
            assert os.path.exists(os.path.join(d, "charts", "maturity_radar.png"))
            assert os.path.exists(os.path.join(d, "charts", "stage_progress.png"))
            assert os.path.exists(os.path.join(d, "charts", "maturity_delta.png"))
        finally:
            shutil.rmtree(d)


class TestPartialMode:
    def test_partial_mode_report(self):
        d = tempfile.mkdtemp()
        try:
            engine = _engine()
            all_checks = list(engine._check_to_mappings.keys())
            data = _base_data()
            # Use multi-service scope so 20 checks = ~25% coverage → partial
            data["maturity_assessment"] = engine.assess(
                [{"event_code": c, "status": "PASS"} for c in all_checks[:20]],
                scanned_services=["s3", "iam", "cloudtrail", "ec2", "rds"],
            )
            data["maturity_delta"] = None

            result = _run_agent(d, data)
            html = open(result["html"], encoding="utf-8").read()

            assert "maturity_radar.png" not in html
            assert "stage_progress.png" in html
            assert "Phạm vi Giới hạn" in html
            assert "maturity-banner warning" in html
            assert "Tác động lên Mức độ Trưởng thành" not in html
        finally:
            shutil.rmtree(d)


class TestFocusedMode:
    def test_focused_mode_report(self):
        d = tempfile.mkdtemp()
        try:
            data = _base_data()
            result = _run_agent(d, data)
            html = open(result["html"], encoding="utf-8").read()

            assert "ĐÁNH GIÁ VÀ KHẮC PHỤC" in html
            assert "Mức độ Trưởng thành Bảo mật" not in html
            assert "maturity_radar.png" not in html
            assert "6. Hậu Khắc phục" in html
            assert "7. Khuyến nghị" in html
            assert "metric-card" in html
            assert "Kết quả Xác minh" in html
        finally:
            shutil.rmtree(d)


class TestEdgeCases:
    def test_none_maturity_no_crash(self):
        d = tempfile.mkdtemp()
        try:
            data = _base_data()
            data["maturity_assessment"] = None
            data["maturity_delta"] = None
            result = _run_agent(d, data)
            assert os.path.exists(result["html"])
        finally:
            shutil.rmtree(d)

    def test_all_pass_no_residual(self):
        d = tempfile.mkdtemp()
        try:
            data = _base_data()
            data["pre"] = {"total": 5, "pass": 5, "fail": 0,
                          "severity": {"critical": 0, "high": 0, "medium": 0, "low": 0}}
            data["post"] = {"initial_pass": 5, "initial_fail": 0, "final_pass": 5,
                           "final_fail": 0, "fixed": 0, "failed": 0, "manual": 0}
            data["findings_table"] = []
            result = _run_agent(d, data)
            html = open(result["html"], encoding="utf-8").read()
            assert "khắc phục thành công" in html
        finally:
            shutil.rmtree(d)

    def test_new_issue_in_post_scan(self):
        d = tempfile.mkdtemp()
        try:
            engine = _engine()
            all_checks = list(engine._check_to_mappings.keys())
            all_services = sorted(set(c.split("_")[0].lower() for c in all_checks))
            data = _base_data()
            data["findings_table"].append(
                {"stt": 3, "check_id": "s3_new", "finding": "New Issue", "service": "s3",
                 "resource": "b1", "severity": "HIGH", "before": "PASS", "after": "FAIL",
                 "change": "NewIssue"}
            )
            # Full mode with maturity delta that includes regression
            m_pre = engine.assess([{"event_code": c, "status": "PASS"} for c in all_checks],
                                  scanned_services=all_services)
            m_post = engine.assess(
                [{"event_code": c, "status": "PASS"} for c in all_checks[:400]]
                + [{"event_code": c, "status": "FAIL"} for c in all_checks[400:]],
                scanned_services=all_services,
            )
            data["maturity_assessment"] = m_pre
            data["maturity_delta"] = engine.compute_delta(m_pre, m_post)
            result = _run_agent(d, data)
            html = open(result["html"], encoding="utf-8").read()
            assert "Vấn đề mới" in html
        finally:
            shutil.rmtree(d)


# ============================================================
# Runner
# ============================================================

def _run_tests():
    import traceback

    test_classes = [
        TestFullMode,
        TestPartialMode,
        TestFocusedMode,
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
        for name, tb in errors:
            print(f"\n--- {name} ---")
            print(tb)

    return failed == 0


if __name__ == "__main__":
    success = _run_tests()
    sys.exit(0 if success else 1)
