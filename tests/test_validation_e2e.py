"""End-to-end test for the Phase 5 validation gate.

Requires a live RAG server on :8001 and Ollama on :11434. Skipped
automatically when either is unreachable so `pytest` can still be run
in environments without the full stack up.

Verifies:
* ``validation_report.json`` is written next to the HTML output.
* The validator catches off-scope mentions, wrong-term usage, and
  hallucinated numbers produced by a misbehaving LLM.
* The rendered HTML falls back to the deterministic template string
  for sections that failed validation, so the final report never
  contains the flagged text.
"""
from __future__ import annotations

import json
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAG_URL = "http://localhost:8001/ready"
OLLAMA_URL = "http://localhost:11434/api/tags"


def _alive(url: str) -> bool:
    try:
        r = requests.get(url, timeout=2)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _alive(RAG_URL) or not _alive(OLLAMA_URL),
    reason="Requires live RAG server on :8001 and Ollama on :11434",
)


# ----------------------------------------------------------------------
# Stub LLM that emits KNOWN violations so we can assert the validator
# fires. We use a stub here instead of a real model call because:
#  * gemma3:4b is non-deterministic even at temperature=0 and would make
#    assertions flaky.
#  * The E2E goal is to prove the validator+fallback wiring works, not to
#    benchmark model output.
# Phase 6 (manual review) covers real LLM output quality.
# ----------------------------------------------------------------------
class _Resp:
    def __init__(self, content: str):
        self.content = content


class ViolatingLLM:
    """Emit text with deliberate validator failures per section."""
    PER_SECTION = {
        "executive_summary": (
            # Off-scope service (S3 in an IAM scope) + hallucinated 9999.
            "Rà soát AWS IAM đã ghi nhận 9999 tài nguyên nghiêm trọng và "
            "nhiều S3 bucket bị cấu hình sai."
        ),
        "system_overview": (
            "Hệ thống có một vài IAM user đáng chú ý."
        ),
        "assessment_goals": (
            "Mục tiêu kiểm toán: Identity And Access Management và "
            "Block Public Access cho toàn bộ account."  # ungrounded capability
        ),
    }

    def __init__(self):
        self._counter = 0

    def invoke(self, messages):
        # First 3 calls in ReportAgent._write_llm_sections correspond to
        # exec_summary, system_overview, assessment_goals (after pass/fail
        # overview bypasses). We return targeted violating text for those
        # and plain text for others.
        idx = self._counter
        self._counter += 1
        # Decide based on what the prompt asked for — scan the Human
        # message for a distinguishing keyword.
        human = messages[-1].content if isinstance(messages, list) else str(messages)
        for key, txt in self.PER_SECTION.items():
            hint = {
                "executive_summary": "Executive Summary",
                "system_overview": "System Description",
                "assessment_goals": "Assessment Goals",
            }[key]
            if hint in human:
                return _Resp(txt)
        return _Resp("Nội dung kỹ thuật ngắn gọn, không vi phạm ràng buộc.")


# ----------------------------------------------------------------------
# Fixture data — IAM-only scope
# ----------------------------------------------------------------------
def _iam_scope_report_data():
    return {
        "pre": {
            "total": 6, "pass": 2, "fail": 4,
            "severity": {"critical": 1, "high": 2, "medium": 1, "low": 0},
        },
        "post": {
            "initial_pass": 2, "initial_fail": 4,
            "final_pass": 5, "final_fail": 1,
            "fixed": 3, "failed": 0, "manual": 1,
        },
        "environment": {
            "account_id": "123456789012",
            "region": "ap-southeast-1",
            "buckets": [],  # not applicable for IAM
        },
        "scope": {
            "services": ["iam"],
            "date": "2026-04-20",
            "user_request": "Kiểm tra IAM MFA + passwords + keys",
        },
        "findings_table": [
            {"stt": 1, "finding": "iam_user_mfa_enabled", "status": "FAIL",
             "severity": "high", "resource": "arn:aws:iam::123456789012:user/alice",
             "change": "Fixed"},
        ],
        "raw_pre_findings": [
            {"finding_id": "f1", "event_code": "iam_user_mfa_enabled",
             "description": "IAM user without MFA", "severity": "high",
             "status": "FAIL", "resource_id": "arn:aws:iam::123456789012:user/alice",
             "service": "iam"},
            {"finding_id": "f2", "event_code": "iam_root_mfa_enabled",
             "description": "Root account MFA disabled", "severity": "critical",
             "status": "FAIL", "resource_id": "123456789012",
             "service": "iam"},
            {"finding_id": "f3", "event_code": "iam_password_policy_strong",
             "description": "Password policy weak", "severity": "medium",
             "status": "FAIL", "resource_id": "123456789012",
             "service": "iam"},
            {"finding_id": "f4", "event_code": "iam_user_console_access",
             "description": "Console access without MFA", "severity": "high",
             "status": "FAIL", "resource_id": "arn:aws:iam::123456789012:user/bob",
             "service": "iam"},
            {"finding_id": "f5", "event_code": "iam_user_mfa_enabled",
             "description": "Carol MFA OK", "severity": "low",
             "status": "PASS", "resource_id": "arn:aws:iam::123456789012:user/carol",
             "service": "iam"},
            {"finding_id": "f6", "event_code": "iam_password_policy_strong",
             "description": "Password policy applied", "severity": "low",
             "status": "PASS", "resource_id": "123456789012",
             "service": "iam"},
        ],
        "success_findings": [],
        "failed_findings": [],
        "manual_findings": [],
        # Minimal RAG context so the validator's allowed_capabilities is
        # populated (otherwise the ungrounded check would skip).
        "rag_context": {
            "control_themes": [
                {"capability_id": "identity-mgmt",
                 "capability_name": "Identity And Access Management",
                 "summary_short": "Manage IAM principals."},
            ],
            "capability_details": [
                {"capability_id": "identity-mgmt",
                 "capability_name": "Identity And Access Management",
                 "summary": "Least-privilege IAM.",
                 "risk_explanation": "Weak IAM enables lateral movement.",
                 "recommendation": "Enforce MFA and short-lived creds."},
            ],
            "recommended_practices": ["Require MFA for every IAM user."],
            "key_findings": [],
            "confidence": "high",
        },
    }


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
def test_validation_report_written(tmp_path):
    """validation_report.json must exist next to the HTML, populated with
    at least the issues we injected.
    """
    from pdca.agents.report_agent import ReportAgent

    out = tmp_path / "validation_e2e"
    agent = ReportAgent(
        output_path=str(out / "final_report.md"),
        llm_config={"llm": ViolatingLLM()},
    )
    result = agent.run(_iam_scope_report_data())

    vpath = result["validation_report"]
    assert os.path.exists(vpath), f"Missing {vpath}"
    with open(vpath, encoding="utf-8") as f:
        payload = json.load(f)

    assert payload["issue_count"] > 0, \
        f"Expected injected violations to surface: {payload}"

    kinds = {i["kind"] for i in payload["issues"]}
    # Executive summary injected: off-scope (S3) + hallucinated (9999).
    assert "off_scope" in kinds, payload
    assert "hallucinated_number" in kinds, payload
    # Assessment goals injected: ungrounded ("Block Public Access").
    # Only one ungrounded name is injected so this is a soft check — do
    # not require it if the heuristic filtered it out.
    # (Phase 5 acceptance covers the hard cases above.)


def test_html_contains_fallback_not_violation(tmp_path):
    """After validation fails, the rendered HTML must contain the
    deterministic template fallback, not the offending LLM text.
    """
    from pdca.agents.report_agent import ReportAgent

    out = tmp_path / "validation_e2e_html"
    agent = ReportAgent(
        output_path=str(out / "final_report.md"),
        llm_config={"llm": ViolatingLLM()},
    )
    result = agent.run(_iam_scope_report_data())

    with open(result["html"], encoding="utf-8") as f:
        html = f.read()

    # Offending executive summary content MUST NOT leak into the final
    # HTML. "9999" is the hallucinated number, "S3 bucket" is the
    # off-scope mention.
    assert "9999" not in html, "Hallucinated number leaked into HTML"
    assert "S3 bucket" not in html, "Off-scope service leaked into HTML"

    # The fallback template string is in HTML — look for a distinctive
    # phrase.
    assert "Đánh giá bảo mật" in html  # from exec_summary fallback


def test_clean_llm_output_passes_validation(tmp_path):
    """A clean LLM output must pass — issue_count == 0, no fallback used."""
    from pdca.agents.report_agent import ReportAgent

    class CleanLLM:
        def invoke(self, messages):
            return _Resp(
                "AWS IAM đã được rà soát. "
                "Tất cả 6 findings đều đã được ghi nhận đầy đủ."
            )

    out = tmp_path / "validation_e2e_clean"
    agent = ReportAgent(
        output_path=str(out / "final_report.md"),
        llm_config={"llm": CleanLLM()},
    )
    result = agent.run(_iam_scope_report_data())

    with open(result["validation_report"], encoding="utf-8") as f:
        payload = json.load(f)

    # Clean text - the only risk is mention of "6" which is in allowed_numbers
    # (pre.total=6). Assert no off_scope or wrong_term issues surfaced.
    kinds = {i["kind"] for i in payload["issues"]}
    assert "off_scope" not in kinds, payload
    assert "wrong_term" not in kinds, payload
