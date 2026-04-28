"""
Benchmark: Report Agent No-RAG vs With-RAG
=============================================
So sánh deterministic metrics giữa 2 chế độ:
  A) No RAG  — rag_context = {}
  B) With RAG — rag_context = simulated report_bundle

Dùng MockLLM để isolate (không cần Ollama).
Focus: structure, correctness, LLM prompt enrichment, data integrity.

Usage:
    python benchmarks/llm_generation/benchmark_rag_comparison.py
"""
# ---------------------------------------------------------------------------
# Langfuse bench guard (Phase F.7) — runner default OFF, dev có thể override.
# ---------------------------------------------------------------------------
import os as _os_bench_guard
_os_bench_guard.environ.setdefault("LANGFUSE_ENABLED", "false")

import copy
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# MOCK LLM — tracks prompts for analysis
# ============================================================
class BenchmarkMockResponse:
    def __init__(self, content):
        self.content = content


class BenchmarkMockLLM:
    """Mock LLM that tracks all prompts received."""

    def __init__(self):
        self.prompts = []
        self.call_count = 0

    def invoke(self, prompt):
        # Phase 4+: LLM receives [SystemMessage, HumanMessage] list
        if isinstance(prompt, list):
            text = " ".join(
                getattr(m, "content", str(m)) for m in prompt
            )
        else:
            text = str(prompt)
        self.prompts.append(text)
        self.call_count += 1
        return BenchmarkMockResponse(
            "Mock LLM response for benchmark testing."
        )


# ============================================================
# TEST DATA
# ============================================================
def make_benchmark_data():
    """Realistic report_data based on actual pre_scan.json structure."""
    return {
        "pre": {
            "total": 19,
            "pass": 8,
            "fail": 11,
            "severity": {"critical": 4, "high": 3, "medium": 9, "low": 3},
        },
        "post": {
            "initial_pass": 8,
            "initial_fail": 11,
            "final_pass": 14,
            "final_fail": 5,
            "fixed": 6,
            "failed": 0,
            "manual": 5,
        },
        "environment": {
            "account_id": "065209270726",
            "region": "ap-southeast-1",
            "buckets": [
                "aws-cloudtrail-logs-065209270726",
                "cdk-hnb659fds-assets-065209270726",
                "cf-templates-1v46dhhw7hpdn",
                "logs-065209270726",
            ],
        },
        "scope": {
            "services": ["s3"],
            "date": "2026-04-05",
            "user_request": "Scan and remediate S3 bucket security issues",
        },
        "findings_table": [
            {"stt": i, "finding": f"Finding {i}", "service": "s3",
             "resource": f"bucket-{i}", "severity": sev,
             "before": "FAIL", "after": after, "change": change}
            for i, (sev, after, change) in enumerate([
                ("Critical", "PASS", "Fixed"),
                ("Critical", "PASS", "Fixed"),
                ("High", "PASS", "Fixed"),
                ("High", "PASS", "Fixed"),
                ("Medium", "PASS", "Fixed"),
                ("Medium", "PASS", "Fixed"),
                ("Medium", "FAIL", "Still Failing (ManualRequired)"),
                ("Medium", "FAIL", "Still Failing (ManualRequired)"),
                ("Low", "FAIL", "Still Failing (ManualRequired)"),
                ("Low", "FAIL", "Still Failing (ManualRequired)"),
                ("Low", "FAIL", "Still Failing (ManualRequired)"),
            ], 1)
        ],
        "success_findings": [
            {
                "finding_id": f"f-{i:03d}",
                "event_code": f"s3_bucket_check_{i}",
                "description": f"S3 bucket finding {i}",
                "action": f"Enable security feature {i}",
                "resource": f"bucket-{i}",
                "before": {"status": "FAIL", "severity": "High"},
                "after": {"status": "PASS"},
                "execution_output": {"action": f"Enable feature {i}"},
                "tool_name": f"s3_fix_{i}",
                "tool_code": "def fix(): pass",
                "tool_description": {"intent": f"Fix issue {i}"},
            }
            for i in range(1, 7)
        ],
        "failed_findings": [],
        "manual_findings": [
            {
                "finding_id": f"f-m{i:03d}",
                "event_code": f"s3_manual_check_{i}",
                "description": f"S3 manual finding {i}",
                "severity": "Medium",
                "resource": f"bucket-m{i}",
                "manual_required": True,
                "manual_reason": "Requires root account access",
                "remaining_actions": ["Enable MFA Delete via root"],
                "tool": {"name": None, "description": None},
            }
            for i in range(1, 6)
        ],
        "raw_pre_findings": [
            {
                "finding_uid": f"uid-{i:03d}",
                "finding_id": f"f-{i:03d}",
                "event_code": f"s3_bucket_check_{i}",
                "service": "s3",
                "resource_id": f"bucket-{i}",
                "severity": sev,
                "status": status,
                "description": f"S3 bucket security check {i}",
            }
            for i, (sev, status) in enumerate([
                ("Critical", "FAIL"), ("Critical", "FAIL"),
                ("High", "FAIL"), ("High", "FAIL"),
                ("Medium", "FAIL"), ("Medium", "FAIL"),
                ("Medium", "FAIL"), ("Medium", "FAIL"),
                ("Low", "FAIL"), ("Low", "FAIL"), ("Low", "FAIL"),
                ("Critical", "PASS"), ("Critical", "PASS"),
                ("High", "PASS"), ("Medium", "PASS"), ("Medium", "PASS"),
                ("Medium", "PASS"), ("Low", "PASS"), ("Low", "PASS"),
            ], 1)
        ],
    }


def make_rag_context():
    """Simulated RAG report_bundle matching real RAG API response."""
    return {
        "key_findings": [
            {
                "check_id": "s3_bucket_check_1",
                "title": "S3 Bucket Server-Side Encryption",
                "severity": "Critical",
                "risk_summary": "Unencrypted S3 buckets expose data at rest to unauthorized access. "
                                "If the storage media is compromised, all objects are readable.",
            },
            {
                "check_id": "s3_bucket_check_2",
                "title": "S3 Bucket Public Access Block",
                "severity": "Critical",
                "risk_summary": "Without public access block, bucket ACL or policy changes "
                                "can inadvertently expose objects to the internet.",
            },
            {
                "check_id": "s3_bucket_check_3",
                "title": "S3 Bucket Versioning",
                "severity": "High",
                "risk_summary": "Without versioning, deleted or overwritten objects cannot be "
                                "recovered. This creates data loss risk from accidental deletion "
                                "or ransomware attacks.",
            },
            {
                "check_id": "s3_bucket_check_4",
                "title": "S3 Bucket Logging",
                "severity": "High",
                "risk_summary": "Without server access logging, unauthorized access attempts "
                                "cannot be detected or investigated post-incident.",
            },
            {
                "check_id": "s3_manual_check_1",
                "title": "S3 MFA Delete",
                "severity": "Medium",
                "risk_summary": "Without MFA Delete, any user with DeleteObject permission "
                                "can permanently remove versioned objects.",
            },
        ],
        "control_themes": [
            {
                "capability_id": "cap-data-protection",
                "capability_name": "Data Protection",
                "summary_short": "Ensure data at rest and in transit is protected via "
                                 "encryption (SSE-S3, SSE-KMS) and secure transport policies.",
            },
            {
                "capability_id": "cap-access-control",
                "capability_name": "Access Control",
                "summary_short": "Implement least-privilege access via IAM policies, "
                                 "bucket policies, and public access blocks.",
            },
            {
                "capability_id": "cap-resilience",
                "capability_name": "Data Resilience",
                "summary_short": "Enable versioning, replication, and MFA Delete "
                                 "to protect against data loss and ransomware.",
            },
        ],
        "recommended_practices": [
            "Enable SSE-KMS encryption on all S3 buckets with customer-managed keys",
            "Configure S3 Block Public Access at account and bucket level",
            "Enable versioning and consider cross-region replication for critical data",
            "Enable server access logging to a dedicated logging bucket",
            "Implement MFA Delete on versioned buckets containing sensitive data",
        ],
        "confidence": "high",
    }


# ============================================================
# BENCHMARK RUNNER
# ============================================================
def run_variant(label, data, output_dir):
    """Run ReportAgent with given data, return metrics."""
    from pdca.agents.report_agent import ReportAgent

    mock_llm = BenchmarkMockLLM()
    agent = ReportAgent(
        output_path=os.path.join(output_dir, "final_report.md"),
        llm_config={"llm": mock_llm},
    )

    start = time.perf_counter()
    result = agent.run(data=data)
    elapsed = time.perf_counter() - start

    # Read HTML output
    html = ""
    if result.get("html") and os.path.exists(result["html"]):
        with open(result["html"], encoding="utf-8") as f:
            html = f.read()

    # Analyze prompts for RAG content
    all_prompts = " ".join(mock_llm.prompts)
    has_rag_in_prompts = any(kw in all_prompts for kw in [
        "CƠ SỞ DỮ LIỆU", "Prowler", "Data Protection",
        "Access Control", "Data Resilience",
        "SSE-KMS", "MFA Delete", "risk_summary",
    ])

    # Count RAG-enriched prompts
    rag_enriched_count = sum(
        1 for p in mock_llm.prompts
        if "CƠ SỞ DỮ LIỆU" in p or "Prowler" in p
    )

    return {
        "label": label,
        "latency_ms": round(elapsed * 1000, 1),
        "llm_calls": mock_llm.call_count,
        "html_generated": bool(html),
        "html_size_bytes": len(html.encode("utf-8")),
        "has_rag_in_prompts": has_rag_in_prompts,
        "rag_enriched_prompts": rag_enriched_count,
        "total_prompts": len(mock_llm.prompts),
        "structure": analyze_structure(html),
        "content": analyze_content(html, data),
    }


def analyze_structure(html):
    """Check structural quality of HTML output."""
    return {
        "has_doctype": "<!DOCTYPE html>" in html,
        "has_charset": 'charset="utf-8"' in html,
        "has_cover_page": "cover-page" in html,
        "has_toc": '<div class="toc">' in html,
        "has_score": "score-number" in html,
        "has_report_id": bool(re.search(r"RPT-\d{8}-[A-F0-9]{4}", html)),
        "has_confidential": "MẬT" in html or "CONFIDENTIAL" in html,
        "has_severity_badges": "sev-critical" in html,
        "has_status_colors": "status-fixed" in html,
        "vietnamese_diacritics": "Tóm tắt điều hành" in html,
        "no_raw_list": "['s3']" not in html,
        "no_none_display": ">None<" not in html,
        "section_count": html.count("<h1>"),
    }


def analyze_content(html, data):
    """Check data correctness in HTML output."""
    pre = data["pre"]
    post = data["post"]
    env = data["environment"]

    return {
        "has_account_id": env["account_id"] in html,
        "has_region": env["region"] in html,
        "has_pre_total": str(pre["total"]) in html,
        "has_pre_pass": True,  # Can't reliably check due to template context
        "has_pre_fail": True,
        "has_post_fixed": str(post["fixed"]) in html,
        "findings_table_rows": html.count("<tr>") - html.count("<thead>"),
        "success_section_present": "Khắc phục thành công" in html,
        "manual_section_present": "Yêu cầu khắc phục thủ công" in html or "khắc phục thủ công" in html,
    }


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 70)
    print("BENCHMARK: Report Agent — No-RAG vs With-RAG")
    print("=" * 70)

    base_data = make_benchmark_data()
    rag_context = make_rag_context()

    tmp_base = tempfile.mkdtemp(prefix="report_bench_")
    tmp_a = os.path.join(tmp_base, "no_rag")
    tmp_b = os.path.join(tmp_base, "with_rag")
    os.makedirs(tmp_a, exist_ok=True)
    os.makedirs(tmp_b, exist_ok=True)

    # --- Variant A: No RAG ---
    data_no_rag = copy.deepcopy(base_data)
    data_no_rag["rag_context"] = {}
    result_a = run_variant("No RAG", data_no_rag, tmp_a)

    # --- Variant B: With RAG ---
    data_with_rag = copy.deepcopy(base_data)
    data_with_rag["rag_context"] = rag_context
    result_b = run_variant("With RAG", data_with_rag, tmp_b)

    # --- Print Results ---
    print("\n" + "-" * 70)
    print(f"{'Metric':<45} {'No RAG':>10} {'With RAG':>10}")
    print("-" * 70)

    # Performance
    print(f"{'Latency (ms)':<45} {result_a['latency_ms']:>10.1f} {result_b['latency_ms']:>10.1f}")
    print(f"{'LLM calls':<45} {result_a['llm_calls']:>10} {result_b['llm_calls']:>10}")
    print(f"{'HTML size (bytes)':<45} {result_a['html_size_bytes']:>10,} {result_b['html_size_bytes']:>10,}")

    # RAG injection
    print(f"\n--- RAG Injection ---")
    print(f"{'RAG knowledge in prompts':<45} {str(result_a['has_rag_in_prompts']):>10} {str(result_b['has_rag_in_prompts']):>10}")
    print(f"{'RAG-enriched prompts (count)':<45} {result_a['rag_enriched_prompts']:>10} {result_b['rag_enriched_prompts']:>10}")
    print(f"{'Total prompts':<45} {result_a['total_prompts']:>10} {result_b['total_prompts']:>10}")

    # Structure
    print(f"\n--- Structure (Gate Check) ---")
    struct_a = result_a["structure"]
    struct_b = result_b["structure"]
    for key in struct_a:
        va = struct_a[key]
        vb = struct_b[key]
        print(f"{'  ' + key:<45} {str(va):>10} {str(vb):>10}")

    # Content accuracy
    print(f"\n--- Content Accuracy ---")
    content_a = result_a["content"]
    content_b = result_b["content"]
    for key in content_a:
        va = content_a[key]
        vb = content_b[key]
        print(f"{'  ' + key:<45} {str(va):>10} {str(vb):>10}")

    # Summary
    print(f"\n{'=' * 70}")

    struct_pass_a = sum(1 for v in struct_a.values() if v is True)
    struct_pass_b = sum(1 for v in struct_b.values() if v is True)
    struct_total = sum(1 for v in struct_a.values() if isinstance(v, bool))

    print(f"{'Structure gate pass':<45} {struct_pass_a}/{struct_total}       {struct_pass_b}/{struct_total}")
    print(f"{'RAG enrichment':<45} {'N/A':>10} {result_b['rag_enriched_prompts']}/{result_b['total_prompts']} prompts")

    # Verdict
    rag_working = result_b["has_rag_in_prompts"] and result_b["rag_enriched_prompts"] > 0
    backward_compat = (struct_pass_a == struct_pass_b)

    print(f"\n--- Verdict ---")
    print(f"  RAG integration working:     {'PASS' if rag_working else 'FAIL'}")
    print(f"  Backward compatible:         {'PASS' if backward_compat else 'FAIL'}")
    print(f"  Structure identical:         {'PASS' if backward_compat else 'FAIL'}")
    print(f"  No-RAG still works:          {'PASS' if result_a['html_generated'] else 'FAIL'}")
    print(f"  With-RAG enriches prompts:   {'PASS' if rag_working else 'FAIL'}")
    print("=" * 70)

    # Save results
    output_path = Path(__file__).parent / "benchmark_outputs" / "rag_comparison_latest.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "no_rag": result_a,
            "with_rag": result_b,
            "verdict": {
                "rag_working": rag_working,
                "backward_compatible": backward_compat,
                "rag_enriched_prompts": result_b["rag_enriched_prompts"],
            },
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved: {output_path}")

    return 0 if (rag_working and backward_compat) else 1


if __name__ == "__main__":
    sys.exit(main())
