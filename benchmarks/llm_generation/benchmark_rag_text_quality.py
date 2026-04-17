"""
Benchmark: Text Quality — No-RAG vs With-RAG (Real LLM)
=========================================================
Chạy ReportAgent thật với Ollama, so sánh chất lượng text output.

Đánh giá deterministic (không cần LLM judge):
1. Hallucination rate: số liệu sai so với data thực
2. Specificity: có dùng term cụ thể hay chung chung
3. RAG grounding: có reference đến kiến thức từ RAG không
4. Placeholder leak: còn [text ở đây] không
5. First person leak: còn "chúng tôi" / "tôi" không
6. Content richness: word count, unique terms

Usage:
    python benchmarks/llm_generation/benchmark_rag_text_quality.py
"""
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
# SAME TEST DATA as benchmark_rag_comparison.py
# ============================================================
def make_benchmark_data():
    return {
        "pre": {
            "total": 19, "pass": 8, "fail": 11,
            "severity": {"critical": 4, "high": 3, "medium": 9, "low": 3},
        },
        "post": {
            "initial_pass": 8, "initial_fail": 11,
            "final_pass": 14, "final_fail": 5,
            "fixed": 6, "failed": 0, "manual": 5,
        },
        "environment": {
            "account_id": "065209270726",
            "region": "ap-southeast-1",
            "buckets": ["aws-cloudtrail-logs-065209270726", "cdk-hnb659fds-assets-065209270726",
                        "cf-templates-1v46dhhw7hpdn", "logs-065209270726"],
        },
        "scope": {
            "services": ["s3"], "date": "2026-04-05",
            "user_request": "Scan and remediate S3 bucket security issues",
        },
        "findings_table": [
            {"stt": i, "finding": f"S3 bucket check {i}", "service": "s3",
             "resource": f"bucket-{i}", "severity": sev,
             "before": "FAIL", "after": after, "change": change}
            for i, (sev, after, change) in enumerate([
                ("Critical", "PASS", "Fixed"), ("Critical", "PASS", "Fixed"),
                ("High", "PASS", "Fixed"), ("High", "PASS", "Fixed"),
                ("Medium", "PASS", "Fixed"), ("Medium", "PASS", "Fixed"),
                ("Medium", "FAIL", "Still Failing (ManualRequired)"),
                ("Medium", "FAIL", "Still Failing (ManualRequired)"),
                ("Low", "FAIL", "Still Failing (ManualRequired)"),
                ("Low", "FAIL", "Still Failing (ManualRequired)"),
                ("Low", "FAIL", "Still Failing (ManualRequired)"),
            ], 1)
        ],
        "success_findings": [
            {"finding_id": f"f-{i:03d}", "event_code": f"s3_bucket_check_{i}",
             "description": f"S3 bucket versioning not enabled on bucket-{i}",
             "action": "Enable S3 bucket versioning",
             "resource": f"bucket-{i}",
             "before": {"status": "FAIL", "severity": "High"},
             "after": {"status": "PASS"},
             "execution_output": {"action": "Enable versioning", "resource": f"bucket-{i}"},
             "tool_name": "s3_enable_versioning",
             "tool_code": "def fix(bucket): boto3.client('s3').put_bucket_versioning(Bucket=bucket, VersioningConfiguration={'Status':'Enabled'})",
             "tool_description": {"intent": "Enable S3 bucket versioning"}}
            for i in range(1, 4)  # 3 success findings
        ],
        "failed_findings": [],
        "manual_findings": [
            {"finding_id": "f-m001", "event_code": "s3_mfa_delete",
             "description": "S3 bucket MFA delete not enabled",
             "severity": "Medium", "resource": "bucket-critical-1",
             "manual_required": True,
             "manual_reason": "Requires root account access for MFA Delete configuration",
             "remaining_actions": ["Sign in as root user", "Enable MFA Delete via CLI"],
             "tool": {"name": None, "description": None}},
        ],
        "raw_pre_findings": [
            {"finding_uid": f"uid-{i:03d}", "finding_id": f"f-{i:03d}",
             "event_code": f"s3_bucket_check_{i}", "service": "s3",
             "resource_id": f"bucket-{i}", "severity": sev, "status": status,
             "description": f"S3 bucket security check {i}"}
            for i, (sev, status) in enumerate([
                ("Critical", "FAIL"), ("Critical", "FAIL"), ("High", "FAIL"),
                ("High", "FAIL"), ("Medium", "FAIL"), ("Medium", "FAIL"),
                ("Medium", "FAIL"), ("Medium", "FAIL"), ("Low", "FAIL"),
                ("Low", "FAIL"), ("Low", "FAIL"),
                ("Critical", "PASS"), ("High", "PASS"), ("Medium", "PASS"),
                ("Medium", "PASS"), ("Medium", "PASS"), ("Low", "PASS"),
                ("Low", "PASS"), ("Low", "PASS"),
            ], 1)
        ],
    }


def make_rag_context():
    return {
        "key_findings": [
            {"check_id": "s3_bucket_check_1", "title": "S3 Bucket Server-Side Encryption",
             "severity": "Critical",
             "risk_summary": "Unencrypted S3 buckets expose data at rest to unauthorized access. "
                             "If the storage media is compromised, all objects are readable in plaintext."},
            {"check_id": "s3_bucket_check_2", "title": "S3 Bucket Public Access Block",
             "severity": "Critical",
             "risk_summary": "Without public access block, bucket ACL or policy changes can inadvertently "
                             "expose objects to the internet, leading to data breach."},
            {"check_id": "s3_bucket_check_3", "title": "S3 Bucket Versioning",
             "severity": "High",
             "risk_summary": "Without versioning, deleted or overwritten objects cannot be recovered. "
                             "This creates data loss risk from accidental deletion or ransomware."},
            {"check_id": "s3_mfa_delete", "title": "S3 MFA Delete",
             "severity": "Medium",
             "risk_summary": "Without MFA Delete, any user with DeleteObject permission can permanently "
                             "remove versioned objects, bypassing versioning protection."},
        ],
        "control_themes": [
            {"capability_id": "cap-dp", "capability_name": "Data Protection",
             "summary_short": "Ensure encryption at rest (SSE-S3/SSE-KMS) and in transit (TLS/SecureTransport)."},
            {"capability_id": "cap-ac", "capability_name": "Access Control",
             "summary_short": "Implement least-privilege via IAM policies, bucket policies, and public access blocks."},
            {"capability_id": "cap-res", "capability_name": "Data Resilience",
             "summary_short": "Enable versioning, cross-region replication, and MFA Delete for data durability."},
        ],
        "recommended_practices": [
            "Enable SSE-KMS encryption on all S3 buckets with customer-managed keys",
            "Configure S3 Block Public Access at account and bucket level",
            "Enable versioning and cross-region replication for critical data",
            "Enable server access logging to a dedicated logging bucket",
            "Implement MFA Delete on versioned buckets containing sensitive data",
        ],
        "confidence": "high",
    }


# ============================================================
# TEXT QUALITY METRICS (deterministic)
# ============================================================

# Terms that indicate specific security knowledge (not generic)
SPECIFIC_SECURITY_TERMS = [
    "SSE-KMS", "SSE-S3", "encryption at rest", "encryption in transit",
    "SecureTransport", "TLS", "public access block", "bucket policy",
    "IAM policy", "least-privilege", "MFA Delete", "versioning",
    "cross-region replication", "data loss", "data breach",
    "ransomware", "compliance", "CIS", "Well-Architected",
    "boto3", "put_bucket_versioning", "KMS key",
    "server access logging", "CloudTrail",
]

# Generic filler terms (no real information)
GENERIC_FILLER = [
    "important", "significant", "various", "appropriate",
    "ensure security", "best practices", "security measures",
    "proper configuration", "adequate protection",
]


def analyze_text_quality(html: str, data: dict, has_rag: bool) -> dict:
    """Analyze text quality of generated HTML report."""

    # Extract only LLM-generated text (remove HTML tags + template data)
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    words = text.split()

    # 1. Hallucination: check if numbers in text match data
    pre = data["pre"]
    post = data["post"]
    hallucination_checks = []

    # Check critical numbers that should appear
    expected_numbers = {
        "pre.total": str(pre["total"]),
        "pre.pass": str(pre["pass"]),
        "pre.fail": str(pre["fail"]),
        "post.fixed": str(post["fixed"]),
        "post.manual": str(post["manual"]),
    }
    for label, expected in expected_numbers.items():
        found = expected in text
        hallucination_checks.append({"label": label, "expected": expected, "found": found})

    correct_numbers = sum(1 for c in hallucination_checks if c["found"])
    number_accuracy = correct_numbers / len(hallucination_checks) if hallucination_checks else 1.0

    # 2. Specificity: count specific security terms vs generic filler
    text_lower = text.lower()
    specific_found = [t for t in SPECIFIC_SECURITY_TERMS if t.lower() in text_lower]
    generic_found = [t for t in GENERIC_FILLER if t.lower() in text_lower]
    specificity_ratio = len(specific_found) / max(len(specific_found) + len(generic_found), 1)

    # 3. Placeholder leak
    placeholder_count = len(re.findall(r'\[.*?\]', text))

    # 4. First person leak
    first_person_count = len(re.findall(r'[Cc]hung toi|[Cc]húng tôi|[Tt]ôi\b|[Tt]oi\b', text))

    # 5. Content richness
    unique_words = len(set(w.lower() for w in words if len(w) > 3))

    # 6. RAG grounding (only relevant for with-RAG)
    rag_terms = [
        "Data Protection", "Access Control", "Data Resilience",
        "SSE-KMS", "public access block", "MFA Delete",
        "data breach", "ransomware", "encryption at rest",
    ]
    rag_grounded = [t for t in rag_terms if t.lower() in text_lower]

    return {
        "word_count": len(words),
        "unique_words": unique_words,
        "number_accuracy": round(number_accuracy, 4),
        "hallucination_checks": hallucination_checks,
        "specific_terms_count": len(specific_found),
        "specific_terms": specific_found,
        "generic_filler_count": len(generic_found),
        "specificity_ratio": round(specificity_ratio, 4),
        "placeholder_leaks": placeholder_count,
        "first_person_leaks": first_person_count,
        "rag_grounded_terms": len(rag_grounded),
        "rag_grounded_list": rag_grounded,
    }


# ============================================================
# RUNNER
# ============================================================
def run_variant(label, data, output_dir):
    from pdca.agents.report_agent import ReportAgent
    from pdca.config import OLLAMA_BASE_URL, OLLAMA_MODEL

    agent = ReportAgent(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        output_path=os.path.join(output_dir, "final_report.md"),
    )

    start = time.perf_counter()
    result = agent.run(data=data)
    elapsed = time.perf_counter() - start

    html = ""
    if result.get("html") and os.path.exists(result["html"]):
        with open(result["html"], encoding="utf-8") as f:
            html = f.read()

    llm_metrics = agent.get_llm_metrics()

    return {
        "label": label,
        "html": html,
        "html_path": result.get("html", ""),
        "latency_s": round(elapsed, 1),
        "llm_metrics": llm_metrics,
    }


def main():
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 70)
    print("TEXT QUALITY BENCHMARK: No-RAG vs With-RAG (Real LLM)")
    print("=" * 70)
    print("Model: llama3.2 via Ollama")
    print("This will take a few minutes per variant...")
    print()

    base_data = make_benchmark_data()
    rag_ctx = make_rag_context()

    tmp_base = tempfile.mkdtemp(prefix="text_quality_bench_")

    # --- Variant A: No RAG ---
    print("[1/2] Running No-RAG variant...")
    tmp_a = os.path.join(tmp_base, "no_rag")
    os.makedirs(tmp_a, exist_ok=True)
    data_a = copy.deepcopy(base_data)
    data_a["rag_context"] = {}
    result_a = run_variant("No RAG", data_a, tmp_a)
    print(f"      Done in {result_a['latency_s']}s, "
          f"{result_a['llm_metrics'].get('call_count', 0)} LLM calls")

    # --- Variant B: With RAG ---
    print("[2/2] Running With-RAG variant...")
    tmp_b = os.path.join(tmp_base, "with_rag")
    os.makedirs(tmp_b, exist_ok=True)
    data_b = copy.deepcopy(base_data)
    data_b["rag_context"] = rag_ctx
    result_b = run_variant("With RAG", data_b, tmp_b)
    print(f"      Done in {result_b['latency_s']}s, "
          f"{result_b['llm_metrics'].get('call_count', 0)} LLM calls")

    # --- Analyze ---
    qa = analyze_text_quality(result_a["html"], base_data, has_rag=False)
    qb = analyze_text_quality(result_b["html"], base_data, has_rag=True)

    # --- Print Results ---
    print(f"\n{'=' * 70}")
    print(f"{'Metric':<45} {'No RAG':>10} {'With RAG':>10} {'Delta':>8}")
    print(f"{'=' * 70}")

    print(f"\n--- Performance ---")
    print(f"{'Total latency (s)':<45} {result_a['latency_s']:>10.1f} {result_b['latency_s']:>10.1f}")
    llm_a = result_a['llm_metrics'].get('total_latency', 0)
    llm_b = result_b['llm_metrics'].get('total_latency', 0)
    print(f"{'LLM total latency (s)':<45} {llm_a:>10.1f} {llm_b:>10.1f}")

    print(f"\n--- Content Volume ---")
    print(f"{'Word count':<45} {qa['word_count']:>10,} {qb['word_count']:>10,} {qb['word_count']-qa['word_count']:>+8,}")
    print(f"{'Unique words (len>3)':<45} {qa['unique_words']:>10,} {qb['unique_words']:>10,} {qb['unique_words']-qa['unique_words']:>+8,}")

    print(f"\n--- Data Accuracy ---")
    print(f"{'Number accuracy':<45} {qa['number_accuracy']:>10.0%} {qb['number_accuracy']:>10.0%}")
    print(f"{'Placeholder leaks':<45} {qa['placeholder_leaks']:>10} {qb['placeholder_leaks']:>10}")
    print(f"{'First person leaks':<45} {qa['first_person_leaks']:>10} {qb['first_person_leaks']:>10}")

    print(f"\n--- Specificity (Security Knowledge) ---")
    print(f"{'Specific security terms':<45} {qa['specific_terms_count']:>10} {qb['specific_terms_count']:>10} {qb['specific_terms_count']-qa['specific_terms_count']:>+8}")
    print(f"{'Generic filler terms':<45} {qa['generic_filler_count']:>10} {qb['generic_filler_count']:>10} {qb['generic_filler_count']-qa['generic_filler_count']:>+8}")
    print(f"{'Specificity ratio':<45} {qa['specificity_ratio']:>10.0%} {qb['specificity_ratio']:>10.0%}")

    print(f"\n--- RAG Grounding ---")
    print(f"{'RAG-grounded terms':<45} {qa['rag_grounded_terms']:>10} {qb['rag_grounded_terms']:>10} {qb['rag_grounded_terms']-qa['rag_grounded_terms']:>+8}")

    if qb['rag_grounded_list']:
        print(f"  Terms found (With RAG): {', '.join(qb['rag_grounded_list'])}")
    if qa['rag_grounded_list']:
        print(f"  Terms found (No RAG):   {', '.join(qa['rag_grounded_list'])}")

    if qa['specific_terms']:
        print(f"\n  Specific terms (No RAG):  {', '.join(qa['specific_terms'][:10])}")
    if qb['specific_terms']:
        print(f"  Specific terms (With RAG): {', '.join(qb['specific_terms'][:10])}")

    # --- Verdict ---
    print(f"\n{'=' * 70}")
    print("VERDICT:")
    improved = []
    same = []
    worse = []

    if qb['specific_terms_count'] > qa['specific_terms_count']:
        improved.append(f"Specific terms: {qa['specific_terms_count']} -> {qb['specific_terms_count']}")
    elif qb['specific_terms_count'] == qa['specific_terms_count']:
        same.append("Specific terms")

    if qb['rag_grounded_terms'] > qa['rag_grounded_terms']:
        improved.append(f"RAG grounding: {qa['rag_grounded_terms']} -> {qb['rag_grounded_terms']}")
    elif qb['rag_grounded_terms'] == qa['rag_grounded_terms']:
        same.append("RAG grounding")

    if qb['placeholder_leaks'] <= qa['placeholder_leaks']:
        same.append("No new placeholder leaks")
    else:
        worse.append(f"Placeholder leaks: {qa['placeholder_leaks']} -> {qb['placeholder_leaks']}")

    if qb['first_person_leaks'] <= qa['first_person_leaks']:
        same.append("No new first-person leaks")
    else:
        worse.append(f"First person leaks: {qa['first_person_leaks']} -> {qb['first_person_leaks']}")

    if qb['number_accuracy'] >= qa['number_accuracy']:
        same.append("Number accuracy maintained")
    else:
        worse.append(f"Number accuracy: {qa['number_accuracy']:.0%} -> {qb['number_accuracy']:.0%}")

    if improved:
        print(f"  IMPROVED:")
        for i in improved:
            print(f"    + {i}")
    if same:
        print(f"  MAINTAINED:")
        for s in same:
            print(f"    = {s}")
    if worse:
        print(f"  DEGRADED:")
        for w in worse:
            print(f"    - {w}")

    print(f"{'=' * 70}")

    # Save
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": "llama3.2",
        "no_rag": {"latency_s": result_a["latency_s"], "llm_metrics": result_a["llm_metrics"], "quality": qa},
        "with_rag": {"latency_s": result_b["latency_s"], "llm_metrics": result_b["llm_metrics"], "quality": qb},
    }
    # Remove non-serializable
    out_path = Path(__file__).parent / "benchmark_outputs" / "rag_text_quality_latest.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nDetailed results: {out_path}")
    print(f"HTML outputs: {tmp_base}")


if __name__ == "__main__":
    main()
