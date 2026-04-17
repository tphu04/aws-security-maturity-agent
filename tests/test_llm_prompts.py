"""
Phase 4: Tests for LLM Prompt Methods (Maturity-aware)
=======================================================
Tests write_maturity_overview, write_domain_assessment, write_maturity_roadmap,
write_post_remediation_analysis_v2, write_action_plan.

Uses MockLLM — no real LLM calls needed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdca.agents.report_module.llm_validator import FactValidator
from pdca.agents.report_module.llm_writer import LLMWriter
from pdca.agents.report_module.maturity_engine import MaturityEngine

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPINGS_PATH = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_mappings.json")
CAPABILITIES_PATH = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_capabilities.json")


# ---------------------------------------------------------------------------
# Mock LLMs
# ---------------------------------------------------------------------------

class MockLLMResponse:
    def __init__(self, content):
        self.content = content


class MockLLM:
    """Returns predictable text. Captures prompt for inspection."""
    def __init__(self):
        self.last_prompt = None

    def invoke(self, prompt):
        self.last_prompt = prompt
        return MockLLMResponse(
            "Detailed analysis based on the provided security data. "
            "The assessment shows measurable improvements in security posture."
        )


class FailingLLM:
    def invoke(self, prompt):
        raise ConnectionError("LLM service unavailable")


class ScriptedLLM:
    """MockLLM variant that returns a caller-provided content string."""
    def __init__(self, content: str):
        self._content = content
        self.last_prompt = None

    def invoke(self, prompt: str):
        self.last_prompt = prompt
        return MockLLMResponse(self._content)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _engine():
    return MaturityEngine(MAPPINGS_PATH, CAPABILITIES_PATH)


def _maturity_data():
    engine = _engine()
    checks = list(engine._check_to_mappings.keys())[:20]
    return engine.assess(
        [{"event_code": c, "status": "PASS"} for c in checks[:10]]
        + [{"event_code": c, "status": "FAIL"} for c in checks[10:20]]
    )


def _delta_data():
    engine = _engine()
    checks = list(engine._check_to_mappings.keys())[:15]
    pre = engine.assess([{"event_code": c, "status": "FAIL"} for c in checks])
    post = engine.assess([{"event_code": c, "status": "PASS"} for c in checks])
    return engine.compute_delta(pre, post)


def _fix_metrics():
    return {
        "total_findings": 20, "total_fail_pre": 12,
        "fixed": 8, "failed_fix": 1, "manual": 3,
        "fix_rate_pct": 66.7, "auto_success_rate_pct": 88.9,
        "residual_fail": 4, "residual_rate_pct": 20.0,
        "pre_pass_rate_pct": 40.0, "post_pass_rate_pct": 80.0,
        "pass_rate_delta": 40.0,
    }


def _residual_risks():
    return {
        "auto_fix_failed": [{"check_id": "x", "severity": "HIGH"}],
        "manual_required": [{"check_id": "y", "severity": "CRITICAL"}],
        "unchanged": [],
        "severity_breakdown": {"critical": 1, "high": 1, "medium": 0, "low": 0},
        "total": 2,
    }


# ============================================================
# Task 4.1: write_maturity_overview()
# ============================================================

class TestMaturityOverview:
    def test_returns_string(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        result = writer.write_maturity_overview(_maturity_data())
        assert isinstance(result, str)
        assert len(result) > 10

    def test_prompt_contains_score(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        maturity = _maturity_data()
        writer.write_maturity_overview(maturity)
        assert str(maturity["overall_score"]) in llm.last_prompt

    def test_prompt_contains_stage(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        maturity = _maturity_data()
        writer.write_maturity_overview(maturity)
        assert maturity["overall_stage_label"] in llm.last_prompt

    def test_prompt_has_word_limit(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        writer.write_maturity_overview(_maturity_data())
        assert "350" in llm.last_prompt

    def test_none_data_returns_fallback(self):
        writer = LLMWriter(llm=MockLLM())
        result = writer.write_maturity_overview(None)
        assert "không khả dụng" in result

    def test_llm_failure_returns_fallback(self):
        writer = LLMWriter(llm=FailingLLM())
        result = writer.write_maturity_overview(_maturity_data())
        assert "không khả dụng" in result

    def test_no_first_person_in_prompt(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        writer.write_maturity_overview(_maturity_data())
        assert "ngôi thứ nhất" in llm.last_prompt  # constraint mentioned


# ============================================================
# Task 4.2: write_domain_assessment()
# ============================================================

class TestDomainAssessment:
    def test_returns_string(self):
        writer = LLMWriter(llm=MockLLM())
        maturity = _maturity_data()
        dp = maturity["domains"]["data_protection"]
        result = writer.write_domain_assessment("Data Protection", dp)
        assert isinstance(result, str)
        assert len(result) > 10

    def test_prompt_contains_domain_name(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        maturity = _maturity_data()
        dp = maturity["domains"]["data_protection"]
        writer.write_domain_assessment("Data Protection", dp)
        assert "Data Protection" in llm.last_prompt

    def test_prompt_contains_capabilities(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        maturity = _maturity_data()
        dp = maturity["domains"]["data_protection"]
        writer.write_domain_assessment("Data Protection", dp)
        # Should contain at least one capability name
        has_cap = any(
            c["capability_name"] in llm.last_prompt
            for c in dp.get("capabilities", [])
        )
        assert has_cap or "(Không có)" in llm.last_prompt

    def test_word_limit_250(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        maturity = _maturity_data()
        dp = maturity["domains"]["data_protection"]
        writer.write_domain_assessment("Data Protection", dp)
        assert "250" in llm.last_prompt

    def test_none_data_returns_fallback(self):
        writer = LLMWriter(llm=MockLLM())
        result = writer.write_domain_assessment("Test", None)
        assert "không khả dụng" in result


# ============================================================
# Task 4.3: write_maturity_roadmap()
# ============================================================

class TestMaturityRoadmap:
    def test_returns_string(self):
        writer = LLMWriter(llm=MockLLM())
        result = writer.write_maturity_roadmap(_maturity_data())
        assert isinstance(result, str)
        assert len(result) > 10

    def test_prompt_mentions_unmapped(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        writer.write_maturity_roadmap(_maturity_data())
        assert "chưa đánh giá" in llm.last_prompt

    def test_prompt_has_coverage(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        maturity = _maturity_data()
        writer.write_maturity_roadmap(maturity)
        coverage = maturity["coverage"]
        total = str(coverage["total_capabilities"])
        assert total in llm.last_prompt

    def test_none_returns_fallback(self):
        writer = LLMWriter(llm=MockLLM())
        result = writer.write_maturity_roadmap(None)
        assert "không khả dụng" in result


# ============================================================
# Task 4.4: write_post_remediation_analysis_v2()
# ============================================================

class TestPostRemediationV2:
    def test_full_mode_with_delta(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        result = writer.write_post_remediation_analysis_v2(
            _fix_metrics(), _residual_risks(), _delta_data(), "full"
        )
        assert isinstance(result, str)
        assert len(result) > 10
        # Full mode → word limit 400
        assert "400" in llm.last_prompt

    def test_focused_mode_shorter(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        writer.write_post_remediation_analysis_v2(
            _fix_metrics(), _residual_risks(), None, "focused"
        )
        # Focused mode → word limit 200
        assert "200" in llm.last_prompt

    def test_no_delta_skips_maturity(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        writer.write_post_remediation_analysis_v2(
            _fix_metrics(), _residual_risks(), None, "partial"
        )
        assert "Maturity Delta" not in llm.last_prompt or "bỏ qua" in llm.last_prompt

    def test_prompt_contains_fix_rate(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        metrics = _fix_metrics()
        writer.write_post_remediation_analysis_v2(
            metrics, _residual_risks(), _delta_data(), "full"
        )
        assert "66.7" in llm.last_prompt  # fix_rate_pct

    def test_none_metrics_returns_fallback(self):
        writer = LLMWriter(llm=MockLLM())
        result = writer.write_post_remediation_analysis_v2(None, None, None, "full")
        assert "không khả dụng" in result

    def test_llm_failure_returns_fallback(self):
        writer = LLMWriter(llm=FailingLLM())
        result = writer.write_post_remediation_analysis_v2(
            _fix_metrics(), _residual_risks(), _delta_data(), "full"
        )
        assert "không khả dụng" in result


# ============================================================
# Task 4.5: write_action_plan()
# ============================================================

class TestActionPlan:
    def test_returns_string(self):
        writer = LLMWriter(llm=MockLLM())
        result = writer.write_action_plan(_residual_risks(), _delta_data())
        assert isinstance(result, str)
        assert len(result) > 10

    def test_prompt_contains_timeline(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        writer.write_action_plan(_residual_risks(), _delta_data())
        assert "1 tuần" in llm.last_prompt
        assert "1 tháng" in llm.last_prompt
        assert "quý" in llm.last_prompt.lower()

    def test_prompt_contains_severity(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        writer.write_action_plan(_residual_risks(), _delta_data())
        assert "CRITICAL" in llm.last_prompt

    def test_no_residual_no_crash(self):
        writer = LLMWriter(llm=MockLLM())
        result = writer.write_action_plan({}, None)
        assert isinstance(result, str)

    def test_word_limit_300(self):
        llm = MockLLM()
        writer = LLMWriter(llm=llm)
        writer.write_action_plan(_residual_risks(), _delta_data())
        assert "300" in llm.last_prompt

    def test_llm_failure_returns_fallback(self):
        writer = LLMWriter(llm=FailingLLM())
        result = writer.write_action_plan(_residual_risks(), _delta_data())
        assert "không khả dụng" in result


# ============================================================
# FactValidator — anti-hallucination guard for LLM sections
# ============================================================

class TestFactValidator:
    def test_validator_accepts_allowed_numbers(self):
        v = FactValidator()
        text = "<p>Đã fix 14 findings và còn 5 FAIL.</p>"
        result = v.validate(text, allowed={14.0, 5.0})
        assert result.ok, f"expected ok, offending={result.offending}"

    def test_validator_rejects_hallucinated_number(self):
        v = FactValidator()
        text = "<p>Có 5 vượt qua sau điều chỉnh, 3 thủ công.</p>"
        result = v.validate(text, allowed={0.0, 2.0, 3.0})
        assert not result.ok, "expected rejection"
        assert "5" in result.offending

    def test_validator_ignores_small_ordinals(self):
        v = FactValidator()
        text = "<p>1. Xử lý Manual Findings.<br>2. Duy trì automation.</p>"
        result = v.validate(text, allowed={50.0, 100.0})
        assert result.ok

    def test_validator_handles_percentages(self):
        v = FactValidator()
        text = "<p>Pass rate 73.7% không đổi.</p>"
        result = v.validate(text, allowed={73.7})
        assert result.ok

    def test_validator_rejects_wrong_percent(self):
        v = FactValidator()
        text = "<p>Pass rate 85% (thực tế 73.7%).</p>"
        result = v.validate(text, allowed={73.7})
        assert not result.ok

    def test_recommendations_fallback_on_hallucination(self):
        llm = ScriptedLLM(
            "<p>Có <strong>5 vượt qua sau điều chỉnh</strong>, 14 thành công.</p>"
        )
        writer = LLMWriter(llm=llm)
        data = {
            "post_summary": {"initial_fail": 5, "final_fail": 5},
            "remediation_outcome": {
                "auto_fix_success": 0,
                "auto_fix_failed": 2,
                "manual_required": 3,
            },
            "severity_before": {"critical": 0, "high": 0, "medium": 2, "low": 3},
        }
        out = writer.write_post_remediation_recommendations(data)
        assert (
            "0 được khắc phục tự động" in out
            or "0 ĐÃ FIX" in out
            or "fixed: 0" in out.lower()
            or "2 auto-fix" in out.lower()
            or "2 Auto-fix" in out
        )
        assert "5 vượt qua" not in out

    def test_recommendations_keeps_truthful_llm_output(self):
        llm = ScriptedLLM(
            "<p>Có 3 findings cần xử lý thủ công và 2 auto-fix thất bại.</p>"
        )
        writer = LLMWriter(llm=llm)
        data = {
            "post_summary": {"initial_fail": 5, "final_fail": 5},
            "remediation_outcome": {
                "auto_fix_success": 0,
                "auto_fix_failed": 2,
                "manual_required": 3,
            },
            "severity_before": {"critical": 0, "high": 0, "medium": 2, "low": 3},
        }
        out = writer.write_post_remediation_recommendations(data)
        assert (
            "3 findings" in out
            or "3 manual" in out.lower()
            or "3 thủ công" in out
        )

    def test_exec_summary_prompt_contains_fail_findings(self):
        llm = ScriptedLLM("ok")
        writer = LLMWriter(llm=llm)
        fails = [
            {"description": "Check if S3 bucket MFA Delete is not enabled.",
             "severity": "medium", "resource": "bucket-a"},
            {"description": "Lifecycle configuration missing.",
             "severity": "low", "resource": "bucket-a"},
        ]
        writer.write_exec_summary(
            pre={"total": 19, "pass": 14, "fail": 5,
                 "severity": {"critical": 0, "high": 0, "medium": 2, "low": 3}},
            sysdata={"account_id": "x"},
            meta={},
            fail_findings=fails,
        )
        prompt = llm.last_prompt or ""
        assert "MFA Delete" in prompt
        assert "Lifecycle configuration" in prompt
        assert "DANH SÁCH LỖI CỤ THỂ" in prompt


# ============================================================
# Runner
# ============================================================

def _run_tests():
    import traceback

    test_classes = [
        TestMaturityOverview,
        TestDomainAssessment,
        TestMaturityRoadmap,
        TestPostRemediationV2,
        TestActionPlan,
        TestFactValidator,
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
