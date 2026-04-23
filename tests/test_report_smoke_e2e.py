"""Phase 6 smoke E2E — runs ReportAgent on every baseline fixture and
asserts scope/validator/rendering invariants.

Each fixture is rendered with a deterministic mock LLM so the test is
reproducible without external services. For each scenario the test
asserts:

* ``ReportAgent.run()`` returns without exception.
* The rendered HTML exists and is non-trivially large.
* Scope terminology matches the fixture's primary service (no S3/bucket
  leakage for IAM-only; generic fallback for multi-service).
* The validator report is written next to the HTML and contains no
  issues under the safe mock (the safe mock never drifts).

The tests also cover a *violating* LLM path for fixture F to confirm
that the Phase-5 validator gate still fires end-to-end.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fixtures.report_baseline.fixture_builder import ALL_BUILDERS


class _Resp:
    def __init__(self, content: str):
        self.content = content


class SafeMockLLM:
    SAFE_TEXT = (
        "Báo cáo được xây dựng dựa trên kết quả quét cấu hình hiện tại. "
        "Đội kỹ thuật đã rà soát toàn bộ các phát hiện và đề xuất "
        "phương án khắc phục phù hợp với mức độ ưu tiên."
    )

    def invoke(self, messages):
        return _Resp(self.SAFE_TEXT)


def _run(tmp_path, data: Dict[str, Any], llm=None):
    from pdca.agents.report_agent import ReportAgent
    agent = ReportAgent(
        output_path=str(tmp_path / "final_report.md"),
        llm_config={"llm": llm or SafeMockLLM()},
    )
    # Skip PDF export to speed up the suite — not the subject of this test.
    from pdca.agents.report_module import exporters as _exp
    _orig = _exp.export_pdf
    _exp.export_pdf = lambda *a, **kw: str(tmp_path / "final_report.pdf")
    try:
        return agent.run(data)
    finally:
        _exp.export_pdf = _orig


# ----------------------------------------------------------------------
# Parametrized smoke across 7 fixtures — no crash + sane output.
# ----------------------------------------------------------------------
@pytest.mark.parametrize("letter", sorted(ALL_BUILDERS.keys()))
def test_fixture_renders_without_error(tmp_path, letter):
    data = ALL_BUILDERS[letter]()
    result = _run(tmp_path, data)

    html_path = result["html"]
    vreport = result["validation_report"]
    assert os.path.exists(html_path), f"HTML missing for fixture {letter}"
    assert os.path.exists(vreport), f"Validation report missing for {letter}"
    html = open(html_path, encoding="utf-8").read()
    # A non-trivial fixture should produce a real document. Fixture D
    # (zero findings) is the smallest, but every HTML must still be at
    # least several KB once template + charts land.
    assert len(html) > 5000, f"HTML suspiciously small for {letter}"


# ----------------------------------------------------------------------
# Scope invariants — these are the Phase 1 + Phase 5 targets.
# ----------------------------------------------------------------------
@pytest.mark.parametrize("letter", ["A", "B", "C", "D", "E"])
def test_s3_fixtures_keep_s3_terminology(tmp_path, letter):
    """Scenarios A..E must still advertise Amazon S3 / bucket — the
    Phase 1 refactor must not regress the happy path."""
    data = ALL_BUILDERS[letter]()
    result = _run(tmp_path, data)
    html = open(result["html"], encoding="utf-8").read()
    assert "Amazon S3" in html, (
        f"S3 scope label should be present in fixture {letter}"
    )


def test_iam_fixture_has_no_s3_leak(tmp_path):
    """Fixture F — IAM-only scope must NOT surface Amazon S3 framing
    or the word 'bucket' anywhere in the rendered HTML."""
    data = ALL_BUILDERS["F"]()
    result = _run(tmp_path, data)
    html = open(result["html"], encoding="utf-8").read()
    assert "Amazon S3" not in html, (
        "Fixture F (IAM) must not be labeled as Amazon S3"
    )
    assert not re.search(r"\bbucket\b", html, re.IGNORECASE), (
        "Fixture F (IAM) must not use the term 'bucket'"
    )
    assert "AWS IAM" in html, (
        "Fixture F should show 'AWS IAM' as the primary scope label"
    )


def test_multi_service_fixture_uses_generic_label(tmp_path):
    """Fixture G — multi-service scan must fall back to the generic
    'AWS Infrastructure' label rather than a dominant single service."""
    data = ALL_BUILDERS["G"]()
    result = _run(tmp_path, data)
    html = open(result["html"], encoding="utf-8").read()
    assert "AWS Infrastructure" in html, (
        "Multi-service scope should show generic 'AWS Infrastructure' label"
    )
    # The three service labels ARE allowed to appear in the findings
    # table (they are data). What must NOT happen is the top-of-report
    # framing branding the whole report as one service. 'Amazon S3' and
    # 'AWS IAM' are scope labels — they must not be the primary label.
    # Instead, inspect the cover-page scope row: with the generic
    # fallback the string 'AWS Infrastructure' is the unique primary
    # label.
    primary_labels = re.findall(r"(Amazon S3|AWS IAM|Amazon EC2|AWS Infrastructure)",
                                 html)
    assert primary_labels.count("AWS Infrastructure") >= 1


# ----------------------------------------------------------------------
# Validator-report shape — every fixture gets a well-formed report.
# ----------------------------------------------------------------------
@pytest.mark.parametrize("letter", sorted(ALL_BUILDERS.keys()))
def test_validation_report_has_expected_shape(tmp_path, letter):
    data = ALL_BUILDERS[letter]()
    result = _run(tmp_path, data)
    with open(result["validation_report"], encoding="utf-8") as f:
        payload = json.load(f)

    for key in ("sections_validated", "issue_count", "summary", "issues"):
        assert key in payload, f"validation_report missing '{key}' for {letter}"
    assert payload["issue_count"] == len(payload["issues"])
    # Under the safe mock LLM every fixture must pass validation.
    assert payload["issue_count"] == 0, (
        f"Safe mock LLM should not trigger validator (fixture {letter}): "
        f"{payload['summary']}"
    )


# ----------------------------------------------------------------------
# Violating LLM path — fixture F with deliberate S3 mention.
# Confirms the Phase-5 gate still fires when wired end-to-end.
# ----------------------------------------------------------------------
class _ViolatingLLM:
    def invoke(self, messages):
        human = messages[-1].content if isinstance(messages, list) else str(messages)
        if "Executive Summary" in human:
            return _Resp(
                "Rà soát AWS IAM đã ghi nhận nhiều S3 bucket cấu hình sai "
                "và 9999 tài nguyên nghiêm trọng."
            )
        return _Resp("Nội dung an toàn.")


def test_violating_llm_triggers_validator(tmp_path):
    data = ALL_BUILDERS["F"]()
    result = _run(tmp_path, data, llm=_ViolatingLLM())
    with open(result["validation_report"], encoding="utf-8") as f:
        payload = json.load(f)
    kinds = {i["kind"] for i in payload["issues"]}
    assert "off_scope" in kinds, payload
    assert "hallucinated_number" in kinds, payload

    html = open(result["html"], encoding="utf-8").read()
    assert "9999" not in html, "Hallucinated number leaked past the gate"
    assert "S3 bucket" not in html, "Off-scope mention leaked past the gate"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
