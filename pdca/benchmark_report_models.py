"""
Benchmark: So sánh model cho Report Agent
==========================================
Test 3 model với prompt thực tế từ LLMWriter.
Đo: chất lượng tiếng Việt, tốc độ, VRAM, instruction following.

Usage:
    python benchmark_report_models.py
"""

import json
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = "http://localhost:11434"

MODELS_TO_TEST = [
    "gemma3:4b",
    "qwen2.5:7b-instruct-q4_K_M",
    "deepseek-r1:7b",
    # Baseline (current)
    "llama3.2:latest",
]

# ---------------------------------------------------------------------------
# MOCK DATA (realistic, from actual pipeline output)
# ---------------------------------------------------------------------------

MOCK_PRE_STATS = {
    "total": 18,
    "pass": 7,
    "fail": 11,
    "severity": {"critical": 2, "high": 4, "medium": 3, "low": 2},
}

MOCK_SYSDATA = {
    "account_id": "123456789012",
    "region": "ap-southeast-1",
    "buckets": ["data-lake-prod", "app-logs-backup", "static-assets-cdn"],
}

MOCK_META = {
    "user_request": "Scan S3 security",
    "date": "2025-04-13",
}

MOCK_RAG_KNOWLEDGE = """
Key Findings:
- [CRITICAL] S3 Bucket Public Access: Bucket 'data-lake-prod' cho phep truy cap cong khai, co the lo du lieu nhay cam.
- [HIGH] Missing Encryption: 3 buckets thieu server-side encryption (SSE), du lieu luu tru khong duoc ma hoa.
- [HIGH] Missing Access Logging: Thieu access logging tren 4 buckets, khong the audit truy cap.

Control Themes:
- Data Protection: Ma hoa du lieu (encryption at rest & in transit)
- Access Control: Quan ly quyen truy cap (bucket policies, ACLs)

Recommended Practices:
- Enable S3 Block Public Access at account level
- Enable default SSE-S3 or SSE-KMS encryption
- Enable S3 server access logging for audit trail
"""

MOCK_FINDING_SUCCESS = {
    "action": "Enable S3 Bucket Server-Side Encryption",
    "resource": "arn:aws:s3:::app-logs-backup",
    "before": {"status": "FAIL", "severity": "High", "config": "ServerSideEncryption: None"},
    "after": {"status": "PASS", "config": "ServerSideEncryption: AES256 (SSE-S3)"},
    "tool_description": "Enables AES-256 server-side encryption (SSE-S3) on S3 bucket using PutBucketEncryption API.",
    "tool_code": """def remediate(session, bucket_name):
    s3 = session.client('s3')
    s3.put_bucket_encryption(
        Bucket=bucket_name,
        ServerSideEncryptionConfiguration={
            'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]
        }
    )
    return {'status': 'success', 'encryption': 'AES256'}""",
    "rag_risk": "Missing encryption exposes data at rest to unauthorized access if storage media is compromised.",
}

MOCK_POST_DATA = {
    "initial_fail": 11,
    "final_fail": 4,
    "fixed": 5,
    "failed": 2,
    "manual": 4,
}

# ---------------------------------------------------------------------------
# OUTPUT CONSTRAINTS (same as LLMWriter)
# ---------------------------------------------------------------------------

OUTPUT_CONSTRAINTS = """

===== RANG BUOC OUTPUT (BAT BUOC) =====
- KHONG vuot qua {word_limit} tu.
- KHONG tao tieu de (da co san trong template).
- KHONG dung ngoi thu nhat (toi, chung toi).
- KHONG dung placeholder [text o day].
- KHONG lap lai cung 1 y nhieu lan.
- Neu data bang 0 hoac rong, neu ro su that va ngung. KHONG suy doan.
- KHONG su dung emoji hay icon.
"""

# ---------------------------------------------------------------------------
# TEST PROMPTS (extracted from LLMWriter methods)
# ---------------------------------------------------------------------------


def build_test_prompts():
    """Build 3 representative prompts covering different report sections."""

    # Test 1: Executive Summary (hardest — long context, needs synthesis)
    exec_summary_prompt = f"""
Ban la Senior Cloud Security Consultant.
Nhiem vu cua ban la viet **Executive Summary** cho bao cao danh gia bao mat Amazon S3 gui len C-Level (CTO/CISO).

===== DU LIEU DAU VAO =====
- Boi canh he thong: {json.dumps(MOCK_SYSDATA, ensure_ascii=False)}
- Ket qua quet (Pre-remediation): {json.dumps(MOCK_PRE_STATS, ensure_ascii=False)}
- Meta & User Notes: {json.dumps(MOCK_META, ensure_ascii=False)}

===== KIEN THUC CHUYEN MON TU CO SO DU LIEU =====
{MOCK_RAG_KNOWLEDGE}

Hay SU DUNG kien thuc tren de viet chinh xac hon — KHONG bia them.

===== YEU CAU CAU TRUC =====
1. **Boi canh & Muc tieu (1 doan van ngan):**
   - Xac nhan hoan tat danh gia bao mat tren tai khoan/region nao.
2. **Tom tat Hien trang An ninh (Bullet Points):**
   - Neu so luong findings va so loi (FAIL findings) mot cach chinh xac.
   - Nhan manh cac nhom rui ro chinh.
3. **Ket luan & Dinh huong (1 doan van ngan):**
   - Danh gia muc do truong thanh bao mat.
   - De xuat dinh huong chien luoc.

===== GIONG VAN =====
- Chuyen nghiep, khach quan, mang tinh tu van chien luoc.
""" + OUTPUT_CONSTRAINTS.format(word_limit=400)

    # Test 2: Remediation Detail (technical writing + code analysis)
    f = MOCK_FINDING_SUCCESS
    remediation_prompt = f"""
Ban la Chuyen gia Ky thuat Bao mat (Technical Security Writer).

Nhiem vu: Viet bao cao chi tiet cho mot hanh dong khac phuc tu dong (Auto-remediation)
da duoc thuc hien thanh cong.

===== DU LIEU DAU VAO =====
Hanh dong: {f["action"]}
Tai nguyen: {f["resource"]}
Mo ta rui ro chinh thuc: {f["rag_risk"]}

Trang thai truoc (Before): {json.dumps(f["before"], ensure_ascii=False)}
Trang thai sau (After): {json.dumps(f["after"], ensure_ascii=False)}

Mo ta ky thuat cua cong cu: {f["tool_description"]}

Source code cua cong cu:
{f["tool_code"]}

===== YEU CAU NOI DUNG =====
Viet mot ban tuong trinh ky thuat ro rang, chia lam 3 phan:

1. **Phan tich Van de & Rui ro:**
   - Giai thich tai sao tai nguyen khong dat chuan.
   - Neu rui ro an ninh thuc te.

2. **Chi tiet Ky thuat Thuc thi:**
   - Phan tich hanh vi ky thuat cua remediation dua tren source code.
   - KHONG trich dan lai source code.

3. **Xac nhan Ket qua:**
   - Tom tat trang thai After.
   - Mo ta loi ich bao mat.

Van phong: Chuyen nghiep, khach quan, dam chat ky thuat.
""" + OUTPUT_CONSTRAINTS.format(word_limit=350)

    # Test 3: Post-Remediation Recommendations (strategic writing)
    recommendations_prompt = f"""
Viet noi dung **Khuyen nghi chien luoc** cho bao cao bao mat.
Noi dung huong toi cap quan ly, dua hoan toan tren du lieu sau remediation.

===== DU LIEU SU DUNG =====
{json.dumps(MOCK_POST_DATA, indent=2, ensure_ascii=False)}

===== THUC HANH KHUYEN NGHI TU CO SO DU LIEU =====
- Enable S3 Block Public Access at account level
- Enable default SSE-S3 or SSE-KMS encryption
- Enable S3 server access logging for audit trail

Uu tien cac khuyen nghi tren khi dua ra de xuat chien luoc.

===== QUY TAC BAT BUOC =====
1. KHONG dung ngoi thu nhat.
2. KHONG dua ra khuyen nghi cho van de khong ton tai trong du lieu.
3. Khong dung ngon ngu sao rong hoac chung chung.

===== YEU CAU DO DAI =====
- Moi khuyen nghi gom:
  * Tieu de ngan
  * **2-3 cau giai thich cu the**

===== DINH HUONG NOI DUNG =====
- Uu tien xu ly cac Manual Findings con ton dong.
- Neu khong co Failed, chi de cap duy tri automation hien co.
- De xuat co che giam sat va ra soat dinh ky.

Van phong: Management-level, thuc te, gan voi du lieu.
""" + OUTPUT_CONSTRAINTS.format(word_limit=300)

    return {
        "exec_summary": {
            "name": "Executive Summary",
            "prompt": exec_summary_prompt,
            "word_limit": 400,
        },
        "remediation_detail": {
            "name": "Remediation Detail",
            "prompt": remediation_prompt,
            "word_limit": 350,
        },
        "recommendations": {
            "name": "Recommendations",
            "prompt": recommendations_prompt,
            "word_limit": 300,
        },
    }


# ---------------------------------------------------------------------------
# SCORING CRITERIA
# ---------------------------------------------------------------------------

SCORING_CRITERIA = """
=== TIEU CHI CHAM DIEM (1-5 moi muc) ===

1. VIETNAMESE QUALITY (Chat luong tieng Viet)
   5: Tu nhien, chuyen nghiep, nhu nguoi ban ngu viet
   3: Hieu duoc nhung co loi ngu phap/tu vung
   1: Khong doc duoc / lon xon tieng Anh-Viet

2. INSTRUCTION FOLLOWING (Tuan thu chi dan)
   5: Dung cau truc, dung word limit, khong vi pham constraints
   3: Thieu 1-2 phan, hoac vuot word limit
   1: Khong theo format, bo qua constraints

3. CONTENT ACCURACY (Do chinh xac noi dung)
   5: Dung so lieu, khong bia, phan tich logic
   3: Co sai sot nho, nhung y chinh dung
   1: Bia so lieu, sai logic

4. PROFESSIONAL TONE (Van phong chuyen nghiep)
   5: Phu hop bao cao C-level, thuat ngu chinh xac
   3: Chap nhan duoc nhung chua dat chuan
   1: Qua casual hoac khong phu hop

5. CONCISENESS (Suc tich)
   5: Du y, khong thua, khong thieu
   3: Hoi dai dong hoac thieu y
   1: Lap lai nhieu, lan man
"""

# ---------------------------------------------------------------------------
# BENCHMARK RUNNER
# ---------------------------------------------------------------------------


def get_gpu_stats():
    """Get current GPU VRAM usage."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            used, total = result.stdout.strip().split(", ")
            return {"vram_used_mb": int(used), "vram_total_mb": int(total)}
    except Exception:
        pass
    return {"vram_used_mb": -1, "vram_total_mb": -1}


def call_ollama(model: str, prompt: str, temperature: float = 0.5) -> dict:
    """Call Ollama API and measure performance."""
    import urllib.request

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 1024,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    gpu_before = get_gpu_stats()
    start = time.perf_counter()

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e), "duration": 0, "response": ""}

    duration = time.perf_counter() - start
    gpu_after = get_gpu_stats()

    response_text = data.get("response", "")
    eval_count = data.get("eval_count", 0)
    eval_duration_ns = data.get("eval_duration", 1)
    tokens_per_sec = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns > 0 else 0

    return {
        "response": response_text,
        "duration_sec": round(duration, 2),
        "tokens_generated": eval_count,
        "tokens_per_sec": round(tokens_per_sec, 2),
        "vram_used_mb": gpu_after["vram_used_mb"],
        "word_count": len(response_text.split()),
    }


def count_constraint_violations(text: str, word_limit: int) -> dict:
    """Auto-check constraint violations."""
    violations = {}

    # Word limit
    wc = len(text.split())
    if wc > word_limit * 1.2:  # 20% tolerance
        violations["word_limit_exceeded"] = f"{wc}/{word_limit}"

    # First person
    import re
    first_person = re.findall(
        r'[Cc]húng\s+tôi|[Tt]ôi\s', text, re.IGNORECASE
    )
    if first_person:
        violations["first_person_used"] = len(first_person)

    # Emoji
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        "\u2600-\u26FF\u2700-\u27BF\u2B50\u2705\u274C\u2714\u2716]+",
    )
    emojis = emoji_pattern.findall(text)
    if emojis:
        violations["emoji_used"] = len(emojis)

    # Placeholder brackets
    placeholders = re.findall(r'\[.*?\]', text)
    # Filter out legitimate markdown links
    real_placeholders = [p for p in placeholders if not p.startswith('[http')]
    if real_placeholders:
        violations["placeholders"] = len(real_placeholders)

    return violations


def preload_model(model: str):
    """Pre-load model into VRAM to get fair measurements."""
    import urllib.request

    print(f"  Loading {model} into VRAM...", end=" ", flush=True)
    payload = json.dumps({
        "model": model,
        "prompt": "Hello",
        "stream": False,
        "options": {"num_predict": 1},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
        print("OK")
    except Exception as e:
        print(f"WARN: {e}")


def run_benchmark():
    """Main benchmark runner."""
    test_prompts = build_test_prompts()
    results = {}
    output_dir = Path("benchmark_results")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print("  REPORT AGENT MODEL BENCHMARK")
    print(f"  Models: {', '.join(MODELS_TO_TEST)}")
    print(f"  Tests: {', '.join(test_prompts.keys())}")
    print("=" * 70)

    for model in MODELS_TO_TEST:
        print(f"\n{'='*70}")
        print(f"  MODEL: {model}")
        print(f"{'='*70}")

        preload_model(model)
        results[model] = {"tests": {}, "summary": {}}

        total_tokens = 0
        total_time = 0
        total_violations = 0

        for test_key, test_data in test_prompts.items():
            print(f"\n  [{test_key}] {test_data['name']}...")

            result = call_ollama(model, test_data["prompt"])

            if "error" in result:
                print(f"    ERROR: {result['error']}")
                results[model]["tests"][test_key] = {"error": result["error"]}
                continue

            violations = count_constraint_violations(
                result["response"], test_data["word_limit"]
            )

            total_tokens += result["tokens_generated"]
            total_time += result["duration_sec"]
            total_violations += len(violations)

            results[model]["tests"][test_key] = {
                "duration_sec": result["duration_sec"],
                "tokens_generated": result["tokens_generated"],
                "tokens_per_sec": result["tokens_per_sec"],
                "word_count": result["word_count"],
                "word_limit": test_data["word_limit"],
                "vram_used_mb": result["vram_used_mb"],
                "violations": violations,
                "response": result["response"],
            }

            print(f"    Duration:    {result['duration_sec']}s")
            print(f"    Speed:       {result['tokens_per_sec']} tok/s")
            print(f"    Words:       {result['word_count']}/{test_data['word_limit']}")
            print(f"    VRAM:        {result['vram_used_mb']} MB")
            if violations:
                print(f"    Violations:  {violations}")
            else:
                print(f"    Violations:  None")

            # Save individual response for manual review
            resp_file = output_dir / f"{model.replace(':', '_')}_{test_key}.txt"
            resp_file.write_text(result["response"], encoding="utf-8")

        results[model]["summary"] = {
            "total_tokens": total_tokens,
            "total_time_sec": round(total_time, 2),
            "avg_tokens_per_sec": round(total_tokens / total_time, 2) if total_time > 0 else 0,
            "total_violations": total_violations,
        }

    # ------------------------------------------------------------------
    # SUMMARY TABLE
    # ------------------------------------------------------------------
    print("\n\n")
    print("=" * 90)
    print("  SUMMARY")
    print("=" * 90)
    print(f"{'Model':<35} {'Avg tok/s':>10} {'Total time':>12} {'VRAM (MB)':>10} {'Violations':>11}")
    print("-" * 90)

    for model in MODELS_TO_TEST:
        s = results[model]["summary"]
        # Get max VRAM from any test
        max_vram = max(
            (t.get("vram_used_mb", 0) for t in results[model]["tests"].values()
             if isinstance(t, dict) and "vram_used_mb" in t),
            default=0,
        )
        print(
            f"{model:<35} {s['avg_tokens_per_sec']:>10.1f} "
            f"{s['total_time_sec']:>10.1f}s {max_vram:>10} "
            f"{s['total_violations']:>11}"
        )

    # Save full results
    results_file = output_dir / f"benchmark_{timestamp}.json"
    # Strip response text for JSON (too large)
    results_slim = {}
    for model, data in results.items():
        results_slim[model] = {
            "summary": data["summary"],
            "tests": {
                k: {kk: vv for kk, vv in v.items() if kk != "response"}
                for k, v in data["tests"].items()
            },
        }
    results_file.write_text(
        json.dumps(results_slim, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n  Results saved to: {output_dir}/")
    print(f"  - benchmark_{timestamp}.json (metrics)")
    print(f"  - <model>_<test>.txt (responses for manual review)")
    print(f"\n  Next: Read each .txt file and score manually using criteria below.\n")
    print(SCORING_CRITERIA)


if __name__ == "__main__":
    run_benchmark()
