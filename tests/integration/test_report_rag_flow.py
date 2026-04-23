"""Phase 6 integration test — RAG bundle → ReportAgent wiring.

Exercises the contract that joins the RAG bundle factory to the report
agent, without booting a live FastAPI server. The flow verified here:

    BundleFactory.build_report_bundle(...)
        → ``rag_context`` dict that ReportAgent consumes
        → RAGViewFormatter produces per-section views
        → ReportValidator picks up ``allowed_capabilities`` from the
          same bundle and uses them to ground the LLM output.

The goal is to catch silent drift between the bundle schema (owned by
the RAG module) and the downstream report consumers — a class of bug
that unit tests on either side cannot catch in isolation.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "RAG"))

from RAG.app.core.models import (  # noqa: E402
    Confidence,
    ReportBundle,
    SelectedCapabilityContext,
    SelectedCheckContext,
    SelectedMappingContext,
)
from RAG.app.context.bundle_factory import BundleFactory  # noqa: E402
from pdca.agents.report_module.rag_formatter import RAGViewFormatter  # noqa: E402
from pdca.agents.report_module.scope_detector import detect_scope  # noqa: E402
from pdca.agents.report_module.validators import build_evidence, ReportValidator  # noqa: E402


# ---------------------------------------------------------------------
# Realistic bundle fixture — IAM-focused so the cross-module scope wiring
# is the thing under test (same scope used by fixture F in the smoke suite).
# ---------------------------------------------------------------------
def _check(check_id: str, severity: str = "high",
           service: str = "iam") -> SelectedCheckContext:
    return SelectedCheckContext(
        check_id=check_id,
        doc_id=f"doc_{check_id}",
        service=service,
        title=f"Title {check_id}",
        short_text=f"Description {check_id}",
        score=0.9,
        confidence=Confidence.high,
        metadata={
            "check_id": check_id,
            "service": service,
            "severity": severity,
            "description": f"Finding for {check_id}",
            "risk": f"Risk exposure if {check_id} is not enforced.",
            "remediation": "aws iam update-account-password-policy ...",
            "remediation_recommendation":
                f"Configure {check_id.replace('_', ' ')} on every principal.",
        },
    )


def _mapping(check_id: str, capability_id: str,
             confidence: Confidence = Confidence.high) -> SelectedMappingContext:
    return SelectedMappingContext(
        check_id=check_id,
        capability_id=capability_id,
        capability_name=f"Capability {capability_id}",
        mapping_confidence=confidence,
        mapping_type="direct",
        review_status="approved",
        rationale=f"{check_id} maps to {capability_id}",
        metadata={},
    )


def _capability(capability_id: str, name: str) -> SelectedCapabilityContext:
    return SelectedCapabilityContext(
        capability_id=capability_id,
        doc_id=f"doc_{capability_id}",
        capability_name=name,
        domain="identity",
        short_text=f"Summary for {name}",
        score=0.85,
        confidence=Confidence.high,
        metadata={
            "capability_id": capability_id,
            "capability_name": name,
            "summary": f"{name} establishes baseline IAM controls.",
            "risk_explanation":
                "Weak IAM governance enables lateral movement across accounts.",
            "guidance":
                "Enforce MFA on every human and programmatic principal.",
            "recommended_practices": [
                f"Require MFA for every {name} principal.",
                "Rotate credentials on a 90-day cycle.",
            ],
            "how_to_check":
                "Is MFA enabled for every user?\n"
                "Are access keys rotated regularly?",
        },
    )


def _build_bundle():
    factory = BundleFactory()
    checks = [
        _check("iam_user_mfa_enabled"),
        _check("iam_root_mfa_enabled", severity="critical"),
        _check("iam_password_policy_strong", severity="medium"),
    ]
    mappings = [
        _mapping("iam_user_mfa_enabled", "identity-mgmt"),
        _mapping("iam_root_mfa_enabled", "identity-mgmt"),
        _mapping("iam_password_policy_strong", "access-mgmt"),
    ]
    capabilities = [
        _capability("identity-mgmt", "Identity And Access Management"),
        _capability("access-mgmt", "Access Lifecycle Management"),
    ]
    bundle = factory.build_report_bundle(
        requested_checks=checks,
        related_checks=[],
        selected_mappings=mappings,
        selected_capabilities=capabilities,
    )
    return bundle, checks


# ---------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------
def test_bundle_validates_as_report_bundle_schema():
    bundle, _ = _build_bundle()
    # Round-tripping through the pydantic model is the formal contract.
    rb = ReportBundle(**bundle)
    assert rb.key_findings, "key_findings must not be empty"
    assert rb.capability_details, "capability_details must not be empty"
    assert rb.recommended_practices, "recommended_practices must not be empty"


def test_key_findings_sorted_by_severity():
    bundle, _ = _build_bundle()
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    seen = [rank.get((f.get("severity") or "").lower(), 4)
            for f in bundle["key_findings"]]
    assert seen == sorted(seen), (
        f"key_findings must be sorted by severity (critical->low): got {seen}"
    )


def test_recommended_practices_are_clean_text():
    bundle, _ = _build_bundle()
    for practice in bundle["recommended_practices"]:
        # These are the exact leak vectors Phase 3 closed.
        assert "Shared concepts" not in practice
        assert "{'CLI':" not in practice
        assert "aws iam " not in practice.lower()


def test_rag_view_formatter_consumes_bundle():
    """The formatter and the bundle must agree on field names — a
    typo on either side surfaces as an empty view."""
    bundle, _ = _build_bundle()
    # Formatter expects rag_context shape with these keys.
    rag_context = {
        "primary_topics": bundle.get("primary_topics", []),
        "key_findings": bundle.get("key_findings", []),
        "control_themes": bundle.get("control_themes", []),
        "recommended_practices": bundle.get("recommended_practices", []),
        "capability_details": bundle.get("capability_details", []),
        "confidence": "medium",
    }
    scope = detect_scope(
        findings=[{"service": "iam", "check_id": "iam_user_mfa_enabled"}],
        services_hint=["iam"],
    )
    fmt = RAGViewFormatter(rag_context, scope)
    assert fmt.has_data, "Formatter should see data from a non-empty bundle"
    assert fmt.for_executive(), "Executive view must render with real bundle"
    assert fmt.for_fail_analysis(), "Fail analysis view must render"
    assert fmt.for_recommendations(), "Recommendations view must render"


def test_validator_evidence_includes_bundle_capabilities():
    """The validator's allowed_capabilities set must be populated from
    the same ``capability_details`` that the bundle produced — otherwise
    grounded capability mentions get flagged as hallucinated."""
    bundle, _ = _build_bundle()
    rag_context = {
        "capability_details": bundle["capability_details"],
        "control_themes": bundle["control_themes"],
    }
    scope = detect_scope(
        findings=[{"service": "iam"}], services_hint=["iam"],
    )
    evidence = build_evidence(
        findings=[{"service": "iam", "resource_id": "arn:aws:iam::1:user/a"}],
        pre={"total": 1, "pass": 0, "fail": 1,
             "severity": {"critical": 0, "high": 1, "medium": 0, "low": 0}},
        post={"initial_pass": 0, "initial_fail": 1, "final_pass": 0,
              "final_fail": 1, "fixed": 0, "failed": 1, "manual": 0},
        scope=scope,
        env={"account_id": "1", "region": "us-east-1"},
        rag_context=rag_context,
    )
    allowed = {c.lower() for c in evidence.get("allowed_capabilities", set())}
    assert "identity and access management" in allowed, (
        f"Bundle capability must flow into validator evidence: {allowed}"
    )

    validator = ReportValidator(scope=scope, evidence=evidence)
    # A section that mentions a bundle-provided capability must pass.
    text = (
        "Đội bảo mật đã rà soát các điều khiển trong nhóm "
        "Identity And Access Management và lên kế hoạch khắc phục."
    )
    result = validator.validate(text, section="recommendations")
    ungrounded = [i for i in result.issues if i.kind == "ungrounded"]
    assert not ungrounded, (
        f"Capability from the bundle must not be flagged ungrounded: {ungrounded}"
    )


def test_validator_flags_capability_outside_bundle():
    """Inverse direction — a capability name *not* in the bundle must
    be caught by the grounding check. Guards the bundle from being a
    silent no-op."""
    bundle, _ = _build_bundle()
    rag_context = {
        "capability_details": bundle["capability_details"],
        "control_themes": bundle["control_themes"],
    }
    scope = detect_scope(findings=[{"service": "iam"}], services_hint=["iam"])
    evidence = build_evidence(
        findings=[{"service": "iam", "resource_id": "arn:aws:iam::1:user/a"}],
        pre={"total": 1, "pass": 0, "fail": 1,
             "severity": {"critical": 0, "high": 1, "medium": 0, "low": 0}},
        post={"initial_pass": 0, "initial_fail": 1, "final_pass": 0,
              "final_fail": 1, "fixed": 0, "failed": 1, "manual": 0},
        scope=scope,
        env={"account_id": "1", "region": "us-east-1"},
        rag_context=rag_context,
    )
    validator = ReportValidator(scope=scope, evidence=evidence)
    text = (
        "Đội bảo mật đề xuất áp dụng Zero Trust Architecture "
        "và Continuous Access Evaluation cho toàn bộ tài khoản."
    )
    result = validator.validate(text, section="recommendations")
    kinds = {i.kind for i in result.issues}
    assert "ungrounded" in kinds, (
        f"Off-bundle capability must be flagged: {result.issues}"
    )


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
