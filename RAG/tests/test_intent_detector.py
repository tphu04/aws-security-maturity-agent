"""Unit tests for IntentDetector."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.context.intent_detector import IntentDetector


def test_detect_empty_query():
    """Empty or None query returns no intents."""
    detector = IntentDetector()
    assert detector.detect_query_intents(None) == []
    assert detector.detect_query_intents("") == []


def test_detect_single_intent():
    """A query mentioning encryption keywords should detect encryption intent."""
    detector = IntentDetector()
    intents = detector.detect_query_intents("check if S3 bucket has kms encryption")
    assert "encryption" in intents


def test_detect_multiple_intents():
    """A query covering multiple topics should detect multiple intents."""
    detector = IntentDetector()
    intents = detector.detect_query_intents(
        "check public access and encryption and iam permissions"
    )
    assert "public_access" in intents
    assert "encryption" in intents
    assert "iam" in intents
    assert len(intents) >= 3


def test_detect_no_matching_intent():
    """A generic query should return empty list if no keywords match."""
    detector = IntentDetector()
    intents = detector.detect_query_intents("general cloud overview")
    assert intents == []


def test_infer_control_families_empty():
    """Empty text returns no families."""
    detector = IntentDetector()
    assert detector.infer_control_families("") == set()
    assert detector.infer_control_families(None) == set()


def test_infer_control_families_encryption():
    """Text mentioning 'encryption at rest' should map to encryption_at_rest family."""
    detector = IntentDetector()
    families = detector.infer_control_families("Ensure encryption at rest is enabled")
    assert "encryption_at_rest" in families


def test_infer_control_families_multiple():
    """Text mentioning multiple control areas should return multiple families."""
    detector = IntentDetector()
    families = detector.infer_control_families(
        "Enable encryption at rest and configure public access blocking and set up cloudtrail logging"
    )
    assert "encryption_at_rest" in families
    assert "public_access" in families
    assert "logging_monitoring" in families


if __name__ == "__main__":
    test_detect_empty_query()
    test_detect_single_intent()
    test_detect_multiple_intents()
    test_detect_no_matching_intent()
    test_infer_control_families_empty()
    test_infer_control_families_encryption()
    test_infer_control_families_multiple()
    print("All IntentDetector tests passed!")
