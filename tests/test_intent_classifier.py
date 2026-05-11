"""Unit tests cho IntentClassifier — rule-based fast path.

LLM path requires Ollama running; we only test the deterministic rule layer
here. Integration coverage for the LLM path lives in
`tests/test_chatbot_api_smoke.py` (skipped when Ollama unavailable).
"""

from __future__ import annotations

import pytest

from pdca.agents.intent_classifier import (
    ChatContext,
    IntentClassifier,
    _detect_finding_ref,
    _detect_service,
    _rule_classify,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestDetectors:
    def test_detect_service_simple(self):
        assert _detect_service("scan s3 buckets") == "s3"
        assert _detect_service("Quét IAM giúp tôi") == "iam"
        assert _detect_service("hello world") is None

    def test_detect_service_word_boundary(self):
        # "iams" should NOT match "iam"
        assert _detect_service("check iams") is None

    def test_detect_finding_ref_prowler_id(self):
        assert _detect_finding_ref("Fix s3_bucket_encryption please") == "s3_bucket_encryption"

    def test_detect_finding_ref_short_codes(self):
        assert _detect_finding_ref("approve T-12") == "T-12"
        assert _detect_finding_ref("verify F-003 again") == "F-003"

    def test_detect_finding_ref_none(self):
        assert _detect_finding_ref("what is encryption?") is None


# ---------------------------------------------------------------------------
# Rule classifier
# ---------------------------------------------------------------------------


class TestRuleClassify:
    @pytest.mark.parametrize("prompt", [
        "Scan S3 buckets",
        "scan iam",
        "Quét EC2 trong account",
        "audit RDS now",
    ])
    def test_scan_verb_plus_service(self, prompt):
        r = _rule_classify(prompt)
        assert r is not None
        assert r.intent == "scan"
        assert r.confidence >= 0.9
        assert r.target_service in {"s3", "iam", "ec2", "rds"}

    @pytest.mark.parametrize("prompt", [
        "What is S3 public access?",
        "Why does this fail?",
        "Tại sao check fail vậy?",
        "Giải thích encryption at rest",
        "How do I enable MFA?",
    ])
    def test_pure_question_is_qa(self, prompt):
        r = _rule_classify(prompt)
        assert r is not None
        assert r.intent == "qa"
        assert r.confidence >= 0.9

    @pytest.mark.parametrize("prompt", [
        "S3 thế nào?",          # service alone + ?, no QA marker matches
        "Tôi muốn xem thêm",     # neither service nor verbs
        "Anything new?",
    ])
    def test_ambiguous_yields_no_rule_match(self, prompt):
        # Rule layer returns None → LLM layer would take over.
        assert _rule_classify(prompt) is None


# ---------------------------------------------------------------------------
# Classifier.classify — rule path only (does not call LLM)
# ---------------------------------------------------------------------------


def _classifier_no_llm() -> IntentClassifier:
    """Build a classifier — its ChatOllama will only be touched on LLM path,
    which we avoid in these tests by using prompts that hit the rule layer."""
    return IntentClassifier(model_name="gemma3:4b", base_url="http://localhost:11434")


class TestClassifyRulePath:
    def test_scan_intent(self):
        c = _classifier_no_llm()
        r = c.classify("scan s3")
        assert r.intent == "scan"
        assert r.target_service == "s3"
        assert r.source == "rule"

    def test_qa_intent(self):
        c = _classifier_no_llm()
        r = c.classify("What is S3 public access?")
        assert r.intent == "qa"
        assert r.source == "rule"

    def test_empty_prompt(self):
        c = _classifier_no_llm()
        r = c.classify("")
        assert r.intent == "qa"
        assert r.source == "fallback"

    def test_context_history_truncation(self):
        # Just exercise the format path — should not raise even with many turns.
        c = _classifier_no_llm()
        ctx = ChatContext(
            run_id="R-1", current_service="s3", findings_count=5,
            last_turns=[{"role": "user", "content": "x" * 500}] * 10,
        )
        r = c.classify("scan iam", context=ctx)
        assert r.intent == "scan"  # still rule-matched
