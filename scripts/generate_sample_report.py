"""
Generate sample reports for visual inspection.
Uses REAL LLM (Ollama) + real maturity data + synthetic findings.

Usage:
    python scripts/generate_sample_report.py              # all 3 modes
    python scripts/generate_sample_report.py full          # full mode only
    python scripts/generate_sample_report.py partial       # partial mode only
    python scripts/generate_sample_report.py focused       # focused mode only

Output: data/samples/<mode>/final_report.html
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdca.agents.report_agent import ReportAgent
from pdca.agents.report_module.maturity_engine import MaturityEngine

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPINGS = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_mappings.json")
CAPS = os.path.join(PROJECT_ROOT, "RAG", "data", "normalized", "maturity_capabilities.json")
OUTPUT_BASE = os.path.join(PROJECT_ROOT, "data", "samples")


def build_synthetic_findings(engine, n_pass=10, n_fail=8):
    """Build realistic synthetic findings from real check_ids."""
    all_checks = list(engine._check_to_mappings.keys())
    findings = []
    for i, cid in enumerate(all_checks[:n_pass + n_fail]):
        findings.append({
            "event_code": cid,
            "status": "PASS" if i < n_pass else "FAIL",
            "severity": ["CRITICAL", "HIGH", "MEDIUM", "LOW"][i % 4],
            "finding_uid": f"uid-{i:03d}",
            "finding_id": f"f-{i:03d}",
            "service": engine._check_to_mappings[cid][0].get("domain", "s3").split("_")[0],
            "resource_id": f"arn:aws:s3:::bucket-{i:02d}",
            "description": f"Check: {cid.replace('_', ' ').title()}",
        })
    return findings


def build_findings_table(pre_findings, fixed_count=6):
    """Build findings_table simulating remediation."""
    table = []
    for i, f in enumerate(pre_findings):
        if f["status"] == "FAIL":
            if i < fixed_count + len([x for x in pre_findings if x["status"] == "PASS"]):
                after, change = "PASS", "Fixed"
            elif i % 3 == 0:
                after, change = "FAIL", "Still Failing (ManualRequired)"
            else:
                after, change = "FAIL", "Still Failing (RemediationFailed)"
        else:
            after, change = "PASS", "Unchanged"

        table.append({
            "stt": i + 1,
            "check_id": f["event_code"],
            "finding": f["description"],
            "service": f.get("service", "s3"),
            "resource": f["resource_id"],
            "severity": f["severity"],
            "before": f["status"],
            "after": after,
            "change": change,
        })
    return table


def build_report_data(engine, mode="full"):
    """Build complete report_data for a given mode."""
    all_checks = list(engine._check_to_mappings.keys())

    if mode == "full":
        n_pass, n_fail = 250, 252  # covers most checks -> full mode
    elif mode == "partial":
        n_pass, n_fail = 12, 8    # ~20 checks -> partial mode
    else:
        n_pass, n_fail = 2, 1     # very few -> focused mode

    pre_findings = build_synthetic_findings(engine, n_pass, n_fail)
    table = build_findings_table(pre_findings)

    pass_count = sum(1 for f in pre_findings if f["status"] == "PASS")
    fail_count = len(pre_findings) - pass_count
    fixed = sum(1 for r in table if r["change"] == "Fixed")
    manual = sum(1 for r in table if "ManualRequired" in r["change"])
    failed_fix = sum(1 for r in table if "RemediationFailed" in r["change"])
    final_pass = sum(1 for r in table if r["after"] == "PASS")
    final_fail = sum(1 for r in table if r["after"] == "FAIL")

    sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in pre_findings:
        s = f["severity"].lower()
        if s in sev:
            sev[s] += 1

    # Build post findings from table
    raw_post = [
        {"event_code": r["check_id"], "status": r["after"], "severity": r["severity"],
         "service": r["service"], "resource_id": r["resource"], "change": r["change"]}
        for r in table
    ]

    data = {
        "pre": {"total": len(pre_findings), "pass": pass_count, "fail": fail_count, "severity": sev},
        "post": {
            "initial_pass": pass_count, "initial_fail": fail_count,
            "final_pass": final_pass, "final_fail": final_fail,
            "fixed": fixed, "failed": failed_fix, "manual": manual,
        },
        "environment": {
            "account_id": "123456789012",
            "region": "ap-southeast-1",
            "buckets": [f"bucket-{i:02d}" for i in range(5)],
        },
        "scope": {
            "services": ["s3", "iam", "cloudtrail"],
            "date": "2026-04-15",
            "user_request": "Comprehensive AWS security maturity assessment",
        },
        "findings_table": table,
        "success_findings": [],
        "failed_findings": [],
        "manual_findings": [],
        "raw_pre_findings": pre_findings,
        "raw_post_findings": raw_post,
    }

    # Maturity assessment
    maturity_pre = engine.assess(pre_findings)
    data["maturity_assessment"] = maturity_pre

    if mode in ("full", "partial") and fail_count > 0:
        maturity_post = engine.assess(raw_post)
        data["maturity_post"] = maturity_post
        data["maturity_delta"] = engine.compute_delta(maturity_pre, maturity_post)
    else:
        data["maturity_post"] = None
        data["maturity_delta"] = None

    return data


def generate_report(mode, use_mock_llm=False):
    """Generate a report for the given mode."""
    engine = MaturityEngine(MAPPINGS, CAPS)
    data = build_report_data(engine, mode)

    out_dir = os.path.join(OUTPUT_BASE, mode)
    os.makedirs(out_dir, exist_ok=True)

    if use_mock_llm:
        class MockResp:
            def __init__(self, c):
                self.content = c
        class MockLLM:
            def invoke(self, p):
                return MockResp("Mock LLM response for visual testing.")
        agent = ReportAgent(
            output_path=os.path.join(out_dir, "final_report.md"),
            llm_config={"llm": MockLLM()},
        )
    else:
        from pdca.config import OLLAMA_MODEL, OLLAMA_BASE_URL
        agent = ReportAgent(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            output_path=os.path.join(out_dir, "final_report.md"),
        )

    print(f"\n{'='*60}")
    print(f"Generating {mode.upper()} mode report...")
    print(f"  Maturity score: {data['maturity_assessment']['overall_score']:.1f}")
    print(f"  Coverage: {data['maturity_assessment']['coverage']['assessed']} assessed")
    print(f"  Findings: {data['pre']['total']} (PASS={data['pre']['pass']}, FAIL={data['pre']['fail']})")
    if data.get("maturity_delta"):
        d = data["maturity_delta"]["overall"]
        print(f"  Delta: {d['pre_score']:.1f} -> {d['post_score']:.1f} ({d['score_delta']:+.1f})")
    print(f"{'='*60}")

    start = time.time()
    result = agent.run(data)
    elapsed = time.time() - start

    print(f"\nDone in {elapsed:.1f}s")
    print(f"  HTML: {result['html']}")
    print(f"  PDF:  {result.get('pdf', 'N/A')}")

    metrics = agent.get_llm_metrics()
    print(f"  LLM calls: {metrics['call_count']}, total latency: {metrics['total_latency']:.1f}s")

    return result


if __name__ == "__main__":
    modes = sys.argv[1:] if len(sys.argv) > 1 else ["full", "partial", "focused"]

    # Check for --mock flag
    use_mock = "--mock" in modes
    modes = [m for m in modes if m != "--mock"]

    for mode in modes:
        if mode not in ("full", "partial", "focused"):
            print(f"Unknown mode: {mode}. Use: full, partial, focused")
            continue
        try:
            generate_report(mode, use_mock_llm=use_mock)
        except Exception as e:
            print(f"\nERROR generating {mode} report: {e}")
            import traceback
            traceback.print_exc()
