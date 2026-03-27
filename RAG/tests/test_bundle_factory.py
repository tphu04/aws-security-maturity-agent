"""Unit tests for BundleFactory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.models import (
    Confidence,
    SelectedCapabilityContext,
    SelectedCheckContext,
    SelectedMappingContext,
)
from app.context.bundle_factory import BundleFactory


def _make_check(check_id: str, service: str = "s3") -> SelectedCheckContext:
    return SelectedCheckContext(
        check_id=check_id,
        doc_id=f"doc_{check_id}",
        service=service,
        title=f"Title of {check_id}",
        short_text=f"Description of {check_id}",
        score=0.9,
        confidence=Confidence.high,
        metadata={
            "check_id": check_id,
            "service": service,
            "severity": "high",
            "description": f"Desc {check_id}",
            "risk": f"Risk {check_id}",
            "remediation": f"Fix {check_id}",
        },
    )


def _make_mapping(check_id: str, capability_id: str) -> SelectedMappingContext:
    return SelectedMappingContext(
        check_id=check_id,
        capability_id=capability_id,
        capability_name=f"Cap {capability_id}",
        mapping_confidence=Confidence.high,
        mapping_type="direct",
        review_status="approved",
        rationale=f"Mapping {check_id} to {capability_id}",
        metadata={},
    )


def _make_capability(capability_id: str) -> SelectedCapabilityContext:
    return SelectedCapabilityContext(
        capability_id=capability_id,
        doc_id=f"doc_{capability_id}",
        capability_name=f"Cap {capability_id}",
        domain="security",
        short_text=f"Summary of {capability_id}",
        score=0.8,
        confidence=Confidence.high,
        metadata={
            "capability_id": capability_id,
            "summary": f"Summary of {capability_id}",
            "recommended_practices": ["Practice 1", "Practice 2"],
        },
    )


def test_risk_bundle_structure():
    """Risk bundle should have primary_finding, related_findings, control_mapping, maturity_context."""
    factory = BundleFactory()
    bundle = factory.build_risk_bundle(
        requested_checks=[_make_check("s3_bucket_public_access_block")],
        related_checks=[_make_check("s3_bucket_versioning")],
        selected_mappings=[_make_mapping("s3_bucket_public_access_block", "block_public_access")],
        selected_capabilities=[_make_capability("block_public_access")],
    )
    assert bundle["primary_finding"] is not None
    assert bundle["primary_finding"]["check_id"] == "s3_bucket_public_access_block"
    assert len(bundle["related_findings"]) == 1
    assert len(bundle["control_mapping"]) == 1
    assert len(bundle["maturity_context"]) == 1


def test_risk_bundle_no_requested():
    """Risk bundle with no requested checks should have None primary_finding."""
    factory = BundleFactory()
    bundle = factory.build_risk_bundle(
        requested_checks=[],
        related_checks=[_make_check("s3_bucket_versioning")],
        selected_mappings=[],
        selected_capabilities=[],
    )
    assert bundle["primary_finding"] is None
    assert len(bundle["related_findings"]) == 1


def test_planning_bundle_structure():
    """Planning bundle should have related_findings, control_mapping_ids, maturity_capability_ids."""
    factory = BundleFactory()
    bundle = factory.build_planning_bundle(
        requested_checks=[_make_check("s3_bucket_public_access_block")],
        related_checks=[_make_check("s3_bucket_versioning")],
        selected_mappings=[_make_mapping("s3_bucket_public_access_block", "block_public_access")],
        selected_capabilities=[_make_capability("block_public_access")],
    )
    assert len(bundle["related_findings"]) == 2
    assert "block_public_access" in bundle["control_mapping_ids"]
    assert "block_public_access" in bundle["maturity_capability_ids"]


def test_report_bundle_structure():
    """Report bundle should have primary_topics, key_findings, control_themes, recommended_practices."""
    factory = BundleFactory()
    bundle = factory.build_report_bundle(
        requested_checks=[_make_check("s3_bucket_public_access_block")],
        related_checks=[],
        selected_mappings=[],
        selected_capabilities=[_make_capability("block_public_access")],
    )
    assert "s3" in bundle["primary_topics"]
    assert len(bundle["key_findings"]) == 1
    assert len(bundle["control_themes"]) == 1
    assert len(bundle["recommended_practices"]) >= 1


def test_evaluate_confidence_risk_no_finding():
    """Risk bundle with no primary finding should return low confidence."""
    factory = BundleFactory()
    result = factory.evaluate_bundle_confidence(
        consumer="risk",
        query="test",
        risk_bundle={"primary_finding": None, "control_mapping": [], "maturity_context": []},
        report_bundle=None,
        planning_bundle=None,
        retrieval_confidence=Confidence.high,
    )
    assert result == "low"


def test_evaluate_confidence_planning_no_findings():
    """Planning bundle with no related findings should return low confidence."""
    factory = BundleFactory()
    result = factory.evaluate_bundle_confidence(
        consumer="planning",
        query="test",
        risk_bundle=None,
        report_bundle=None,
        planning_bundle={"related_findings": []},
        retrieval_confidence=Confidence.high,
    )
    assert result == "low"


def test_build_dispatches_correctly():
    """build() should dispatch to the right builder based on consumer."""
    factory = BundleFactory()
    checks = [_make_check("s3_bucket_public_access_block")]
    mappings = [_make_mapping("s3_bucket_public_access_block", "block_public_access")]
    caps = [_make_capability("block_public_access")]

    risk = factory.build("risk", checks, [], mappings, caps)
    assert "primary_finding" in risk

    planning = factory.build("planning", checks, [], mappings, caps)
    assert "related_findings" in planning
    assert "control_mapping_ids" in planning

    report = factory.build("report", checks, [], mappings, caps)
    assert "key_findings" in report
    assert "primary_topics" in report


if __name__ == "__main__":
    test_risk_bundle_structure()
    test_risk_bundle_no_requested()
    test_planning_bundle_structure()
    test_report_bundle_structure()
    test_evaluate_confidence_risk_no_finding()
    test_evaluate_confidence_planning_no_findings()
    test_build_dispatches_correctly()
    print("All BundleFactory tests passed!")
