"""
Phase 6: Tests for Adaptive Report Template
=============================================
Tests template rendering for full/partial/focused modes,
CSS classes, conditional sections, and edge cases.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jinja2 import Template
from pdca.agents.report_module.template import REPORT_TEMPLATE, REPORT_CSS
from pdca.agents.report_module.maturity_engine import MaturityEngine

# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPINGS_PATH = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_mappings.json")
CAPABILITIES_PATH = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_capabilities.json")


def _engine():
    return MaturityEngine(MAPPINGS_PATH, CAPABILITIES_PATH)


def _base_ctx():
    """Minimal template context for focused mode."""
    return {
        "env": {"account_id": "123456789012", "region": "ap-southeast-1", "buckets": []},
        "scope": {"services": ["s3"], "date": "2026-04-15", "user_request": "test"},
        "pre": {"total": 10, "pass": 5, "fail": 5,
                "severity": {"critical": 1, "high": 2, "medium": 1, "low": 1}},
        "post": {"initial_pass": 5, "initial_fail": 5,
                 "final_pass": 8, "final_fail": 2,
                 "fixed": 3, "failed": 1, "manual": 1},
        "score": 75, "report_id": "RPT-TEST-001",
        "charts": {"severity": "charts/sev.png", "pass_fail": "charts/pf.png"},
        "maturity_charts": {},
        "table": [
            {"stt": 1, "finding": "Encryption", "service": "s3", "resource": "bucket-1",
             "severity": "HIGH", "before": "FAIL", "after": "PASS", "change": "Fixed"},
            {"stt": 2, "finding": "MFA Delete", "service": "s3", "resource": "bucket-2",
             "severity": "CRITICAL", "before": "FAIL", "after": "FAIL",
             "change": "Still Failing (ManualRequired)"},
        ],
        "success": [], "failed": [], "manual": [],
        "llm": {
            "executive_summary": "Executive summary text.",
            "system_overview": "System overview.",
            "assessment_goals": "Assessment goals.",
            "pass_overview": "Pass overview.", "fail_overview": "Fail overview.",
            "post_analysis": "Post analysis.", "recommendations": "Recommendations.",
        },
        "maturity": None, "maturity_delta": None,
        "report_mode": "focused",
        "fix_metrics": {
            "fix_rate_pct": 60.0, "fixed": 3, "total_fail_pre": 5,
            "failed_fix": 1, "manual": 1,
            "auto_success_rate_pct": 75.0, "residual_fail": 2, "residual_rate_pct": 20.0,
            "pre_pass_rate_pct": 50.0, "post_pass_rate_pct": 80.0, "pass_rate_delta": 30.0,
        },
        "residual_risks": {
            "auto_fix_failed": [{"finding": "F1", "service": "s3", "severity": "HIGH", "resource": "r1"}],
            "manual_required": [{"finding": "F2", "service": "s3", "severity": "CRITICAL", "resource": "r2"}],
            "unchanged": [],
            "severity_breakdown": {"critical": 1, "high": 1, "medium": 0, "low": 0},
            "total": 2,
        },
    }


def _full_ctx():
    """Template context for full maturity mode."""
    ctx = _base_ctx()
    engine = _engine()
    all_checks = list(engine._check_to_mappings.keys())
    all_services = sorted(set(c.split("_")[0].lower() for c in all_checks))
    maturity = engine.assess(
        [{"event_code": c, "status": "PASS"} for c in all_checks[:300]]
        + [{"event_code": c, "status": "FAIL"} for c in all_checks[300:]],
        scanned_services=all_services,
    )
    maturity_post = engine.assess([{"event_code": c, "status": "PASS"} for c in all_checks],
                                  scanned_services=all_services)
    delta = engine.compute_delta(maturity, maturity_post)

    ctx["maturity"] = maturity
    ctx["maturity_delta"] = delta
    ctx["report_mode"] = "full"
    ctx["maturity_charts"] = {
        "radar": "charts/radar.png",
        "stage_progress": "charts/stage.png",
        "maturity_delta": "charts/delta.png",
    }
    ctx["llm"]["maturity_overview"] = "Maturity overview narrative."
    ctx["llm"]["domain_assessments"] = {d: f"Assessment for {d}" for d in maturity["domains"]}
    ctx["llm"]["maturity_roadmap"] = "Roadmap narrative."
    ctx["llm"]["post_remediation_analysis"] = "Post analysis v2."
    ctx["llm"]["action_plan"] = "Action plan narrative."
    return ctx


def _render(ctx):
    return Template(REPORT_TEMPLATE).render(**ctx)


# ============================================================
# Task 6.1: CSS
# ============================================================

class TestCSS:
    def test_css_has_maturity_classes(self):
        assert ".maturity-banner" in REPORT_CSS
        assert ".stage-badge" in REPORT_CSS
        assert ".domain-card" in REPORT_CSS
        assert ".capability-table" in REPORT_CSS
        assert ".metric-card" in REPORT_CSS
        assert ".delta-positive" in REPORT_CSS
        assert ".verification-pass" in REPORT_CSS
        assert ".severity-critical" in REPORT_CSS

    def test_css_no_syntax_errors(self):
        # Basic check: balanced braces
        assert REPORT_CSS.count("{") == REPORT_CSS.count("}")


# ============================================================
# Task 6.2: Cover Page
# ============================================================

class TestCoverPage:
    def test_full_mode_cover(self):
        html = _render(_full_ctx())
        assert "MỨC ĐỘ TRƯỞNG THÀNH" in html
        assert "stage-badge" in html

    def test_partial_mode_cover(self):
        ctx = _full_ctx()
        ctx["report_mode"] = "partial"
        ctx["maturity_charts"] = {"stage_progress": "charts/stage.png", "maturity_delta": "charts/delta.png"}
        html = _render(ctx)
        assert "Đánh giá một phần" in html

    def test_focused_mode_cover(self):
        html = _render(_base_ctx())
        assert "ĐÁNH GIÁ VÀ KHẮC PHỤC" in html
        assert "stage-badge" not in html or "Trưởng thành" not in html[:2000]


# ============================================================
# Task 6.3: Section 5 — Maturity
# ============================================================

class TestMaturitySection:
    def test_full_mode_has_all_sections(self):
        ctx = _full_ctx()
        # Force a stub unmapped capability so the conditional "Năng lực Chưa
        # Được Đánh giá" section renders. Matches production behaviour where
        # real scans usually leave some capabilities unassessed.
        ctx["maturity"]["unmapped_capabilities"] = [
            {"capability_name": "Stub unmapped", "stage": "1 quickwins",
             "guidance": "stub"}
        ]
        html = _render(ctx)
        assert "Mức độ Trưởng thành Bảo mật" in html
        assert "Maturity overview narrative" in html
        assert "radar.png" in html
        assert "stage.png" in html
        assert "Năng lực Chưa Được Đánh giá" in html
        assert "Lộ trình Cải thiện" in html

    def test_unmapped_section_hidden_when_empty(self):
        ctx = _full_ctx()
        ctx["maturity"]["unmapped_capabilities"] = []
        html = _render(ctx)
        assert "Năng lực Chưa Được Đánh giá" not in html, (
            "Section should be hidden when there are no unmapped capabilities"
        )

    def test_full_mode_domain_cards(self):
        html = _render(_full_ctx())
        assert "domain-card" in html
        assert "Data Protection" in html

    def test_partial_mode_no_radar(self):
        ctx = _full_ctx()
        ctx["report_mode"] = "partial"
        ctx["maturity_charts"] = {"stage_progress": "charts/stage.png"}
        html = _render(ctx)
        assert "radar.png" not in html
        assert "stage.png" in html

    def test_partial_mode_warning_banner(self):
        ctx = _full_ctx()
        ctx["report_mode"] = "partial"
        ctx["maturity_charts"] = {"stage_progress": "charts/stage.png"}
        html = _render(ctx)
        assert "Phạm vi Giới hạn" in html
        assert "maturity-banner warning" in html

    def test_focused_mode_no_maturity_section(self):
        html = _render(_base_ctx())
        assert "Đánh giá Mức độ Trưởng thành" not in html

    def test_focused_mode_with_small_mapping(self):
        ctx = _base_ctx()
        engine = _engine()
        checks = list(engine._check_to_mappings.keys())[:3]
        ctx["maturity"] = engine.assess([{"event_code": c, "status": "PASS"} for c in checks])
        html = _render(ctx)
        assert "Ánh xạ Năng lực Bảo mật" in html

    def test_maturity_none_no_crash(self):
        ctx = _base_ctx()
        ctx["maturity"] = None
        html = _render(ctx)
        assert len(html) > 1000


# ============================================================
# Task 6.4: Section 8 — Post-Remediation
# ============================================================

class TestPostRemediation:
    def test_verification_table(self):
        html = _render(_base_ctx())
        assert "Kết quả Xác minh" in html
        assert "verification-pass" in html or "verification-fail" in html

    def test_fix_metrics_cards(self):
        html = _render(_base_ctx())
        assert "metric-card" in html
        assert "60.0%" in html  # fix_rate_pct

    def test_maturity_delta_section_present(self):
        html = _render(_full_ctx())
        assert "Tác động lên Mức độ Trưởng thành" in html
        assert "delta.png" in html

    def test_maturity_delta_hidden_when_none(self):
        ctx = _base_ctx()
        ctx["maturity_delta"] = None
        html = _render(ctx)
        assert "Tác động lên Mức độ Trưởng thành" not in html

    def test_residual_risks_tables(self):
        html = _render(_base_ctx())
        assert "Khắc phục Tự động Thất bại" in html
        assert "Cần Xử lý Thủ công" in html

    def test_all_fixed_success_banner(self):
        ctx = _base_ctx()
        ctx["residual_risks"] = {
            "auto_fix_failed": [], "manual_required": [], "unchanged": [],
            "severity_breakdown": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "total": 0,
        }
        html = _render(ctx)
        assert "Tất cả findings đã được khắc phục thành công" in html

    def test_change_icons_rendered(self):
        html = _render(_base_ctx())
        assert "Đã khắc phục" in html
        assert "Cần xử lý thủ công" in html


# ============================================================
# Task 6.5: Section 9 — Recommendations
# ============================================================

class TestRecommendations:
    def test_full_mode_section_title(self):
        html = _render(_full_ctx())
        assert "Khuyến nghị Chiến lược" in html

    def test_focused_mode_section_title(self):
        html = _render(_base_ctx())
        assert "7. Khuyến nghị" in html

    def test_action_plan_present(self):
        ctx = _full_ctx()
        html = _render(ctx)
        assert "Kế hoạch Hành động" in html
        assert "Action plan narrative" in html

    def test_action_plan_hidden_when_absent(self):
        ctx = _base_ctx()
        assert "action_plan" not in ctx["llm"]
        html = _render(ctx)
        assert "Kế hoạch Hành động" not in html


# ============================================================
# Regression: zero-delta rows must use `delta-zero`, not `delta-negative`
# ============================================================

class TestDeltaStyling:
    def _zero_delta_ctx(self):
        ctx = _full_ctx()
        ctx["maturity_delta"]["overall"]["score_delta"] = 0.0
        ctx["maturity_delta"]["overall"]["post_score"] = \
            ctx["maturity_delta"]["overall"]["pre_score"]
        # Make FAIL count unchanged so the findings row also renders zero delta.
        ctx["post"]["final_fail"] = ctx["pre"]["fail"]
        return ctx

    def test_zero_score_delta_uses_delta_zero_class(self):
        html = _render(self._zero_delta_ctx())
        assert "delta-zero" in html, (
            "zero score_delta must render with class=delta-zero"
        )

    def test_unchanged_fail_count_is_delta_zero(self):
        html = _render(self._zero_delta_ctx())
        assert 'class="delta-zero">0<' in html, (
            "unchanged FAIL count row must use delta-zero styling"
        )

    def test_positive_score_delta_still_positive(self):
        ctx = _full_ctx()
        ctx["maturity_delta"]["overall"]["score_delta"] = 2.5
        html = _render(ctx)
        assert "delta-positive" in html


# ============================================================
# Runner
# ============================================================

def _run_tests():
    import traceback

    test_classes = [
        TestCSS,
        TestCoverPage,
        TestMaturitySection,
        TestPostRemediation,
        TestRecommendations,
        TestDeltaStyling,
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
