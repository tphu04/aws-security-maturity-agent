"""
Phase 1 smoke tests — verifies that ReportAgent no longer hard-codes S3.

Runs the report agent end-to-end (with a mock LLM that echoes the prompt)
on three scenarios and inspects the prompt text and rendered HTML:

* S3-only findings   → prompts must still call it "Amazon S3" / "bucket".
* IAM-only findings  → prompts must NOT say "Amazon S3" or "bucket"; they
                       should use the AWS IAM terminology instead.
* Multi-service mix  → prompts must fall back to the generic "AWS
                       Infrastructure" / "resource" terminology.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ------------------------------------------------------------------
# Echo LLM that records every prompt and returns it verbatim.
# ------------------------------------------------------------------
class _Response:
    def __init__(self, content):
        self.content = content


class EchoLLM:
    """Returns the prompt so assertions can inspect what was sent."""

    def __init__(self):
        self.prompts = []

    def invoke(self, prompt):
        text = prompt if isinstance(prompt, str) else getattr(
            prompt, "content", str(prompt)
        )
        self.prompts.append(text)
        return _Response(
            "Noi dung mau cho kiem thu. Khong chua tu khoa dac biet."
        )


def _make_data(findings_spec, service_for_resource_field=None, services=None):
    """Build a minimal report_data dict for ReportAgent.run()."""
    raw_pre = []
    findings_table = []
    for idx, (service, resource) in enumerate(findings_spec, 1):
        check_id = f"{service}_check_{idx}"
        raw_pre.append({
            "finding_uid": f"uid-{idx}",
            "finding_id": f"f-{idx}",
            "event_code": check_id,
            "check_id": check_id,
            "service": service,
            "resource_id": resource,
            "severity": "High",
            "status": "FAIL",
            "description": f"Finding {idx} on {service}",
        })
        findings_table.append({
            "stt": idx,
            "finding": f"Finding {idx} on {service}",
            "service": service,
            "resource": resource,
            "severity": "High",
            "before": "FAIL",
            "after": "FAIL",
            "change": "Still Failing (ManualRequired)",
        })

    return {
        "pre": {
            "total": len(raw_pre),
            "pass": 0,
            "fail": len(raw_pre),
            "severity": {"critical": 0, "high": len(raw_pre), "medium": 0, "low": 0},
        },
        "post": {
            "initial_pass": 0,
            "initial_fail": len(raw_pre),
            "final_pass": 0,
            "final_fail": len(raw_pre),
            "fixed": 0,
            "failed": 0,
            "manual": len(raw_pre),
        },
        "environment": {
            "account_id": "123456789012",
            "region": "us-east-1",
            "buckets": [],
        },
        "scope": {
            "services": services or sorted({s for s, _ in findings_spec}),
            "date": "2026-04-19",
            "user_request": "Smoke test",
        },
        "findings_table": findings_table,
        "success_findings": [],
        "failed_findings": [],
        "manual_findings": [],
        "raw_pre_findings": raw_pre,
    }


def _run_report(tmp_path, data):
    from pdca.agents.report_agent import ReportAgent
    llm = EchoLLM()
    agent = ReportAgent(
        output_path=os.path.join(str(tmp_path), "final_report.md"),
        llm_config={"llm": llm},
    )
    # Skip matplotlib charts — irrelevant for prompt content assertions.
    agent._make_charts = lambda pre, out: {
        "severity": "charts/sev.png", "pass_fail": "charts/pf.png",
    }
    result = agent.run(data)
    with open(result["html"], encoding="utf-8") as f:
        html = f.read()
    return llm.prompts, html


# ------------------------------------------------------------------
# Scenario A — S3 only: legacy behaviour preserved (regression guard).
# ------------------------------------------------------------------
def test_s3_only_preserves_s3_terminology(tmp_path):
    data = _make_data([
        ("s3", "prod-data-lake"),
        ("s3", "logs-backup"),
    ])
    prompts, html = _run_report(tmp_path, data)

    joined = "\n".join(prompts)
    assert "Amazon S3" in joined, "S3 scope should use 'Amazon S3' label"
    assert "bucket" in joined.lower()
    # system overview cover-page label should reflect Amazon S3.
    assert "Amazon S3" in html


# ------------------------------------------------------------------
# Scenario F — IAM only: no S3 / bucket leakage allowed.
# ------------------------------------------------------------------
def test_iam_only_drops_s3_and_bucket_terms(tmp_path):
    data = _make_data([
        ("iam", "arn:aws:iam::123456789012:user/alice"),
        ("iam", "arn:aws:iam::123456789012:role/admin"),
    ])
    prompts, html = _run_report(tmp_path, data)

    exec_and_overview = "\n".join(prompts[:2])  # exec_summary + system_overview
    # The two parameterised prompts are the only ones that referenced S3/bucket
    # before Phase 1. They must now advertise IAM instead.
    assert "Amazon S3" not in exec_and_overview, (
        "IAM-only scope must not be introduced as Amazon S3"
    )
    assert "bucket" not in exec_and_overview.lower(), (
        f"'bucket' leaked into IAM-only prompt: {exec_and_overview[:500]}"
    )
    assert "AWS IAM" in exec_and_overview

    # Cover-page table now shows 'Dịch vụ chính' with correct label.
    assert "AWS IAM" in html


# ------------------------------------------------------------------
# Scenario G — multi-service mix with no dominant service.
# ------------------------------------------------------------------
def test_multi_service_uses_generic_terms(tmp_path):
    data = _make_data([
        ("s3", "b-1"), ("s3", "b-2"),
        ("iam", "arn:aws:iam::123456789012:user/alice"),
        ("iam", "arn:aws:iam::123456789012:role/admin"),
        ("ec2", "i-0abc1"), ("ec2", "i-0abc2"),
    ], services=["s3", "iam", "ec2"])
    prompts, html = _run_report(tmp_path, data)

    exec_and_overview = "\n".join(prompts[:2])
    assert "AWS Infrastructure" in exec_and_overview, (
        "Multi-service scope should advertise the generic fallback"
    )
    assert "resources" in exec_and_overview.lower()
    # The generic fallback must keep "Amazon S3" / "bucket" out of the
    # top-of-report framing — S3 may still appear elsewhere because it is
    # present in findings_table, but not as the service being reported on.
    assert "báo cáo đánh giá bảo mật Amazon S3" not in exec_and_overview.lower() \
        and "báo cáo đánh giá bảo mật amazon s3" not in exec_and_overview.lower()

    # Template shows the generic fallback label.
    assert "AWS Infrastructure" in html


# ------------------------------------------------------------------
# _build_system_data — scope-aware resource counting.
# ------------------------------------------------------------------
def test_build_system_data_counts_iam_distinct_resources(tmp_path):
    from pdca.agents.report_agent import ReportAgent
    from pdca.agents.report_module.scope_detector import detect_scope

    llm = EchoLLM()
    agent = ReportAgent(
        output_path=os.path.join(str(tmp_path), "final_report.md"),
        llm_config={"llm": llm},
    )

    env = {"account_id": "123456789012", "region": "us-east-1"}
    scope = {"services": ["iam"], "date": "2026-04-19", "user_request": ""}
    findings = [
        {"service": "iam",
         "resource": "arn:aws:iam::123456789012:user/alice"},
        {"service": "iam",
         "resource": "arn:aws:iam::123456789012:user/bob"},
        # Account-id leak from *_account_level_* check must be dropped.
        {"service": "iam", "resource": "123456789012"},
    ]
    scope_info = detect_scope(findings, env=env, services_hint=["iam"])
    sysdata = agent._build_system_data(env, scope, scope_info, findings=findings)

    assert sysdata["primary_service"] == "iam"
    assert sysdata["service_display"] == "AWS IAM"
    assert sysdata["total_resources"] == 2  # account-id filtered out
    assert sysdata["resource_count_source"] == "findings"
    assert "total_buckets" not in sysdata


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
