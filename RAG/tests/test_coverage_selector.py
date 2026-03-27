"""Unit tests for CoverageSelector."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.models import Confidence, SelectedCheckContext
from app.context.coverage_selector import CoverageSelector


def _make_check(check_id: str, service: str = "s3", score: float = 0.5,
                title: str = "", short_text: str = "") -> SelectedCheckContext:
    return SelectedCheckContext(
        check_id=check_id,
        doc_id=f"doc_{check_id}",
        service=service,
        title=title or check_id.replace("_", " "),
        short_text=short_text or f"Description of {check_id}",
        score=score,
        confidence=Confidence.high,
        metadata={"check_id": check_id, "service": service},
    )


def test_empty_candidates():
    """Empty candidate list returns empty selection."""
    selector = CoverageSelector()
    result = selector.planning_coverage_select([], "some query")
    assert result == []


def test_single_intent_selection():
    """With a single intent query, should select relevant candidates."""
    selector = CoverageSelector()
    candidates = [
        _make_check("s3_bucket_public_access_block", "s3", 0.9,
                     title="S3 Public Access Block"),
        _make_check("s3_bucket_versioning", "s3", 0.7,
                     title="S3 Bucket Versioning"),
        _make_check("ec2_instance_public_ip", "ec2", 0.6,
                     title="EC2 Public IP"),
    ]
    result = selector.planning_coverage_select(candidates, "check public access")
    assert len(result) >= 1
    check_ids = {c.check_id for c in result}
    assert "s3_bucket_public_access_block" in check_ids


def test_multi_intent_diversification():
    """With multi-intent query, should diversify across intents."""
    selector = CoverageSelector()
    candidates = [
        _make_check("s3_bucket_public_access_block", "s3", 0.9,
                     title="S3 Public Access Block", short_text="public access"),
        _make_check("s3_bucket_default_encryption", "s3", 0.8,
                     title="S3 Default Encryption", short_text="encrypt default kms"),
        _make_check("cloudtrail_is_enabled", "cloudtrail", 0.7,
                     title="CloudTrail Enabled", short_text="audit log cloudtrail"),
        _make_check("s3_bucket_versioning", "s3", 0.6,
                     title="S3 Bucket Versioning"),
    ]
    result = selector.planning_coverage_select(
        candidates, "check public access and encryption and logging"
    )
    check_ids = {c.check_id for c in result}
    # Should cover all three intents
    assert "s3_bucket_public_access_block" in check_ids
    assert "s3_bucket_default_encryption" in check_ids
    assert "cloudtrail_is_enabled" in check_ids


def test_target_check_count_planning():
    """Planning consumer should get wide candidate pool (15)."""
    selector = CoverageSelector()
    count = selector.target_check_count("planning", Confidence.high, False, [])
    assert count == 15


def test_target_check_count_risk():
    """Risk consumer should get 3 checks."""
    selector = CoverageSelector()
    count = selector.target_check_count("risk", Confidence.high, False, [])
    assert count == 3


def test_target_capability_count_expand():
    """Low confidence risk consumer should expand to 3 capabilities."""
    selector = CoverageSelector()
    count = selector.target_capability_count("risk", Confidence.low, False, [])
    assert count == 3


def test_target_capability_count_normal():
    """High confidence risk consumer should get 2 capabilities."""
    selector = CoverageSelector()
    count = selector.target_capability_count("risk", Confidence.high, False, [])
    assert count == 2


if __name__ == "__main__":
    test_empty_candidates()
    test_single_intent_selection()
    test_multi_intent_diversification()
    test_target_check_count_planning()
    test_target_check_count_risk()
    test_target_capability_count_expand()
    test_target_capability_count_normal()
    print("All CoverageSelector tests passed!")
