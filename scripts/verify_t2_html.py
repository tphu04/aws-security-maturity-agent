"""Quick HTML quality check for T1/T2 improvements.

Checks 3 things in each generated HTML:
1. System overview mentions domain security context (Q2 grounding)
2. Fail section has remediation steps (Q3 grounding)
3. Domain assessment has corpus descriptions (T1-A enrichment)
"""
import pathlib
import re
import sys

CHECKS = [
    ("system_overview_q2", r"PHẠM VI BẢO MẬT THEO DOMAIN|domain.*bảo mật|S3.*data protection|IAM.*least privilege", "System overview has Q2 domain context"),
    ("fail_q3_steps",      r"BƯỚC KHẮC PHỤC TRỌNG TÂM|aws s3api|aws iam|aws ec2|\[CLI\]|\[CONSOLE\]|\[IAC\]", "Fail section has Q3 remediation steps"),
    ("fail_q2_pitfalls",   r"SAI LẦM PHỔ BIẾN|\[S3\]|\[IAM\]|\[EC2\]", "Fail section has Q2 domain pitfalls"),
    ("exec_q2_domain",     r"BỐI CẢNH BẢO MẬT THEO DOMAIN", "Executive has Q2 domain narratives"),
]

def check_html(html_path: pathlib.Path) -> dict:
    text = html_path.read_text(encoding="utf-8", errors="replace")
    results = {}
    for key, pattern, label in CHECKS:
        found = bool(re.search(pattern, text, re.IGNORECASE))
        results[key] = (found, label)
    return results

def main():
    inf_dir = pathlib.Path("benchmarks/llm_generation/inference_outputs/report_v3_t2_improvements")
    if not inf_dir.exists():
        print("ERROR: inference dir not found — has the benchmark finished?")
        sys.exit(1)

    html_files = sorted(inf_dir.glob("*.html"))
    if not html_files:
        print("ERROR: no HTML files found")
        sys.exit(1)

    all_pass = True
    for html in html_files:
        print(f"\n{'='*55}")
        print(f"  {html.stem}")
        print(f"{'='*55}")
        results = check_html(html)
        for key, (found, label) in results.items():
            mark = "✓" if found else "✗"
            status = "FOUND" if found else "MISSING"
            print(f"  [{mark}] {label}: {status}")
            if not found:
                all_pass = False

    print(f"\n{'='*55}")
    print("OVERALL:", "ALL CHECKS PASSED" if all_pass else "SOME CHECKS MISSING")
    print("Note: MISSING may mean RAG service returned empty context for this case.")

if __name__ == "__main__":
    main()
