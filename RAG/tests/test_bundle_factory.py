"""Unit tests for BundleFactory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.models import (
    Confidence,
    ReportBundle,
    SelectedCapabilityContext,
    SelectedCheckContext,
    SelectedMappingContext,
)
from app.context.bundle_factory import (
    BundleFactory,
    _filter_confident_mappings,
    _severity_rank,
    _truncate_at_sentence,
)


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


# ------------------------------------------------------------------
# Phase 3 — Bundle Factory Rebuild: new tests
# ------------------------------------------------------------------

def _check_with(
    check_id: str,
    severity: str,
    recommendation: str = None,
    remediation: str = "{'CLI': 'aws do-stuff'}",
    service: str = "s3",
):
    """Build a check whose rich metadata exposes both the noisy remediation
    code block AND the clean remediation_recommendation — we rely on this to
    assert the bundle picks the clean one."""
    return SelectedCheckContext(
        check_id=check_id,
        doc_id=f"doc_{check_id}",
        service=service,
        title=f"Title {check_id}",
        short_text="",
        score=0.9,
        confidence=Confidence.high,
        metadata={
            "severity": severity,
            "risk": f"Risk for {check_id}. Second sentence.",
            "remediation": remediation,
            "remediation_recommendation": recommendation,
        },
    )


def _cap_with(capability_id: str):
    return SelectedCapabilityContext(
        capability_id=capability_id,
        doc_id=f"doc_{capability_id}",
        capability_name=f"Cap {capability_id}",
        domain="security",
        short_text="",
        score=0.8,
        confidence=Confidence.high,
        metadata={
            "summary": f"Summary of {capability_id}. Long enough to survive truncation.",
            "risk_explanation": f"Attackers exploit {capability_id} when absent.",
            "guidance": "Enable setting X and audit periodically.",
            "how_to_check": "1) Review config\n2) Verify CloudTrail\n- Check IAM policy",
            "recommended_practices": [f"Practice A for {capability_id}"],
            "source_uri": f"https://docs.aws/{capability_id}",
            "domain": "security",
            "stage": "optimized",
        },
    )


def test_report_bundle_validates_against_schema():
    """Bundle output must satisfy the ReportBundle pydantic contract."""
    factory = BundleFactory()
    bundle = factory.build_report_bundle(
        requested_checks=[_check_with("s3_a", "high", "Enable encryption.")],
        related_checks=[],
        selected_mappings=[_make_mapping("s3_a", "cap_a")],
        selected_capabilities=[_cap_with("cap_a")],
    )
    # Raises ValidationError on schema mismatch.
    rb = ReportBundle(**bundle)
    assert rb.capability_details, "capability_details must not be empty"


def test_severity_sorting_orders_critical_first():
    """key_findings must come out critical -> high -> medium -> low."""
    factory = BundleFactory()
    bundle = factory.build_report_bundle(
        requested_checks=[
            _check_with("c_low", "low", "Low rec."),
            _check_with("c_crit", "critical", "Critical rec."),
            _check_with("c_med", "medium", "Medium rec."),
            _check_with("c_high", "high", "High rec."),
        ],
        related_checks=[],
        selected_mappings=[],
        selected_capabilities=[],
    )
    severities = [f["severity"] for f in bundle["key_findings"]]
    assert severities == ["critical", "high", "medium", "low"]
    # Stable: severity is the sort key, ranks match helper.
    assert _severity_rank("critical") < _severity_rank("low")


def test_confidence_filter_drops_low_confidence_mappings():
    """control_themes must not include capabilities linked only via low-conf mappings."""
    factory = BundleFactory()
    bundle = factory.build_report_bundle(
        requested_checks=[_check_with("c1", "high", "Rec for c1.")],
        related_checks=[],
        selected_mappings=[
            SelectedMappingContext(check_id="c1", capability_id="cap_low", mapping_confidence=Confidence.low),
            SelectedMappingContext(check_id="c1", capability_id="cap_high", mapping_confidence=Confidence.high),
        ],
        selected_capabilities=[_cap_with("cap_low"), _cap_with("cap_high")],
    )
    theme_ids = {t["capability_id"] for t in bundle["control_themes"]}
    assert "cap_high" in theme_ids
    assert "cap_low" not in theme_ids, "low-confidence mapping leaked into bundle"

    # Helper-level sanity.
    kept = _filter_confident_mappings(
        [
            SelectedMappingContext(check_id="x", capability_id="c", mapping_confidence=Confidence.low),
            SelectedMappingContext(check_id="x", capability_id="c", mapping_confidence=Confidence.medium),
        ],
        min_level="medium",
    )
    assert len(kept) == 1


def test_sentence_truncation_cuts_at_boundary_not_mid_word():
    """_truncate_at_sentence must prefer punctuation boundaries."""
    text = "First sentence. Second sentence continues further and further until the limit."
    out = _truncate_at_sentence(text, max_chars=20)
    assert out.endswith("...")
    # Should include the period from "First sentence."
    assert "First sentence" in out
    # Must not cut mid-word ("contin...")
    assert "contin" not in out

    # Short input is returned untouched.
    assert _truncate_at_sentence("short", max_chars=50) == "short"
    assert _truncate_at_sentence("", max_chars=50) is None
    assert _truncate_at_sentence(None, max_chars=50) is None


def test_recommended_practices_no_rationale_or_cli_leak():
    """recommended_practices must come from remediation_recommendation
    (human-readable) and capability.recommended_practices — NOT from
    raw remediation blobs or mapping.rationale."""
    factory = BundleFactory()
    bundle = factory.build_report_bundle(
        requested_checks=[
            _check_with(
                "c1",
                "high",
                recommendation="Enable MFA for all IAM users.",
                remediation="{'CLI': 'aws iam update-account-password-policy ...'}",
            ),
        ],
        related_checks=[],
        selected_mappings=[
            SelectedMappingContext(
                check_id="c1",
                capability_id="cap1",
                mapping_confidence=Confidence.high,
                rationale="Shared concepts: something noisy",
            )
        ],
        selected_capabilities=[_cap_with("cap1")],
    )
    practices = bundle["recommended_practices"]
    assert practices, "should surface at least one practice"
    for p in practices:
        assert not p.startswith("{'CLI"), f"CLI dict leaked: {p}"
        assert "Shared concepts" not in p, f"mapping rationale leaked: {p}"
        assert "aws iam update-account" not in p, f"raw CLI leaked: {p}"
    # The clean recommendation made it through.
    assert any("MFA" in p for p in practices)


def test_capability_details_populated_with_rich_fields():
    """capability_details must surface summary/risk/recommendation/guidance
    for >= 80% of the capabilities that pass the confidence gate."""
    factory = BundleFactory()
    bundle = factory.build_report_bundle(
        requested_checks=[_check_with("c1", "high", "Rec c1.")],
        related_checks=[],
        selected_mappings=[_make_mapping("c1", "cap_a"), _make_mapping("c1", "cap_b")],
        selected_capabilities=[_cap_with("cap_a"), _cap_with("cap_b")],
    )
    details = bundle["capability_details"]
    assert len(details) == 2
    rich = sum(
        1
        for d in details
        if d["risk_explanation"]
        and d["recommendation"]
        and d["guidance_questions"]
    )
    assert rich / len(details) >= 0.8
    # Spot-check field surfacing.
    d0 = details[0]
    assert d0["url"] and d0["url"].startswith("https://")
    assert d0["domain"] == "security"
    assert d0["stage"] == "optimized"
    assert isinstance(d0["guidance_questions"], list)
    assert len(d0["guidance_questions"]) >= 2


def test_evaluate_confidence_report_empty_capability_details():
    """Report consumer without capability_details must degrade to low."""
    factory = BundleFactory()
    result = factory.evaluate_bundle_confidence(
        consumer="report",
        query="q",
        risk_bundle=None,
        report_bundle={
            "key_findings": [{"check_id": "c1"}],
            "primary_topics": ["s3"],
            "control_themes": [{"capability_id": "cap"}],
            "recommended_practices": ["p1", "p2", "p3"],
            "capability_details": [],
        },
        planning_bundle=None,
        retrieval_confidence=Confidence.high,
    )
    assert result == "low"


def test_evaluate_confidence_report_fewer_than_three_practices():
    """Report with <3 practices must demote high to medium."""
    factory = BundleFactory()
    result = factory.evaluate_bundle_confidence(
        consumer="report",
        query="q",
        risk_bundle=None,
        report_bundle={
            "key_findings": [{"check_id": "c1"}],
            "primary_topics": ["s3"],
            "control_themes": [{"capability_id": "cap"}],
            "recommended_practices": ["only_one"],
            "capability_details": [{"capability_id": "cap"}],
        },
        planning_bundle=None,
        retrieval_confidence=Confidence.high,
    )
    assert result == "medium"


if __name__ == "__main__":
    test_risk_bundle_structure()
    test_risk_bundle_no_requested()
    test_planning_bundle_structure()
    test_report_bundle_structure()
    test_evaluate_confidence_risk_no_finding()
    test_evaluate_confidence_planning_no_findings()
    test_build_dispatches_correctly()
    test_report_bundle_validates_against_schema()
    test_severity_sorting_orders_critical_first()
    test_confidence_filter_drops_low_confidence_mappings()
    test_sentence_truncation_cuts_at_boundary_not_mid_word()
    test_recommended_practices_no_rationale_or_cli_leak()
    test_capability_details_populated_with_rich_fields()
    test_evaluate_confidence_report_empty_capability_details()
    test_evaluate_confidence_report_fewer_than_three_practices()
    print("All BundleFactory tests passed!")
