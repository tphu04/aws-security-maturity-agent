# Bao cao Evaluation — Report Agent

**Ngay chot**: 2026-04-06
**Model**: llama3.2:latest (3.2B, Q4_K_M)
**Kien truc**: Template-first, LLM-enriched, RAG-augmented (Jinja2 HTML5 + 7 LLM sections + N per-finding calls + RAG knowledge injection)
**Metrics**: 100% deterministic (0 LLM judge calls)
**Ket qua**: 8/10 release criteria PASS. Structure 100%, Correctness 100%, Faithfulness 0.719, Coverage 100%
**RAG Ablation**: Specific terms +143% (7→17), RAG grounding +700% (1→8), Latency -18%

---

## 1. Tong quan

### 1.1 Muc tieu

Danh gia chat luong output cua Report Agent — node cuoi cung trong pipeline PDCA. Nhiem vu: nhan data day du tu cac agent truoc → viet noi dung (LLM) → render ra file (HTML/MD/PDF).

Report Agent **KHONG** tinh toan so lieu, **KHONG** truy cap file scan, **KHONG** gom metadata. Toan bo data den tu `build_report_data()` trong orchestrator.

**Dac thu so voi Risk/Planning Agent**: Output khong phai JSON hay structured data, ma la **HTML5 document day du** (cover page, TOC, 7 muc, charts, CSS) voi narrative text do LLM viet xen ke giua data template-rendered. Dieu nay doi hoi evaluation framework khac biet: tach thanh **2 tang** — template (deterministic) va LLM narrative (co variance).

### 1.2 Cau hinh duoc chon

| Thong so | Gia tri |
|----------|---------|
| Model | llama3.2:latest (3.2B params, Q4_K_M quantization) |
| RAG | **Co** — `RAGClient.build_context(consumer="report")` inject knowledge vao 9/18 LLM prompts |
| RAG data | key_findings (risk_summary), control_themes (capability), recommended_practices |
| LLM calls per report | 7 top-level + N per-finding (N = success + failed + manual findings) |
| Temperature | 0.3 (semi-deterministic, cho narrative da dang) |
| Output format | HTML5 + CSS (Jinja2 template rendering) |
| Post-processing | `_clean()`: xoa placeholder, ngoi thu nhat, title trung, None |
| Inference | Ollama local, RTX 3060 Laptop 6GB |

### 1.3 Kien truc Template-first, LLM-enriched

Khac biet co ban voi Risk Agent (LLM sinh toan bo output) va Planning Agent (LLM chi goi khi low-confidence):
Report Agent **ket hop 2 tang**:
- **Tang 1 — Template (deterministic)**: Jinja2 render data truc tiep vao HTML — so lieu, bang, chart, cover page, TOC. Khong co LLM involvement → 100% chinh xac.
- **Tang 2 — LLM narrative**: 7 sections do LLM viet (executive summary, system overview, assessment goals, pass/fail overview, post-analysis, recommendations) + detail cho tung finding.

```
report_data dict (tu build_report_data + rag_context)
    |
    v
ReportAgent.run(data)
    |
    ├── [1] _validate_input()          → kiem tra 9 required keys
    ├── [2] _split_by_status()         → tach raw_findings thanh pass/fail
    │       _make_charts()             → severity bar + pass/fail pie
    │       _calc_score()              → security score 0-100
    ├── [3] _build_rag_knowledge()     → format RAG bundle → text block cho LLM
    │       _write_llm_sections(rag)   → 7 LLM calls (RAG-enriched, conditional bypass)
    ├── [4] _enrich_*(rag_map)         → deep copy + LLM detail + RAG risk
    └── [5] _render()                  → Jinja2 template → HTML + MD + PDF
```

**Conditional bypass** (fix BUG-04): Khi `pre.pass == 0` hoac `pre.fail == 0`, su dung hardcoded text thay vi goi LLM — tranh hallucination khi "khong co gi de viet". Mo rong: khi all-pass (fail=0, fixed=0, failed=0), bypass ca executive_summary, post_analysis, recommendations.

---

## 2. Benchmark Dataset

### 2.1 Thong so

| Thong so | Gia tri |
|----------|---------|
| Tong so test cases | 19 |
| File | `benchmark_llm_gen/benchmark_report_cases.json` |
| AWS services | S3 (primary), IAM, EC2 (multi-service cases) |
| Nhom A (scenario logic) | 9 cases |
| Nhom B (edge cases / bug regression) | 10 cases |

### 2.2 Phan bo

**Theo scenario:**

| Scenario | Nhom | So luong | Dac diem | Bug regression |
|----------|:----:|:-------:|----------|:--------------:|
| standard | A | 3 | Co ca PASS + FAIL, co remediation | — |
| all_pass | A | 2 | `pre.fail == 0` → bypass fail_overview | — |
| all_fail | A | 2 | `pre.pass == 0` → bypass pass_overview | — |
| minimal | A | 2 | 1-2 findings, it metadata | — |
| missing_fields | B | 2 | `action=None`, `description=None`, `resource=None` | BUG-02 |
| mixed_case_status | B | 2 | `change` = "FIXED", "fixed", "Failed" lan lon | BUG-03 |
| multi_service | B | 2 | `scope.services = ["s3", "iam", "ec2"]` | BUG-05 |
| high_volume | B | 1 | 50 findings, 15 trong findings_table | — |
| zero_severity | B | 1 | Tat ca severity = 0 | — |
| complex_remediation | B | 2 | Ca 3 loai: success + failed + manual, nested data | — |

### 2.3 Cau truc 1 test case

Test case su dung `report_data` dict — cung cau truc voi output cua `build_report_data()`:

```json
{
  "case_id": "report_standard_001",
  "group": "A_scenario",
  "scenario": "standard",
  "input": {
    "pre": { "total": 10, "pass": 7, "fail": 3,
             "severity": {"critical": 1, "high": 1, "medium": 1, "low": 0} },
    "post": { "initial_pass": 7, "initial_fail": 3,
              "final_pass": 9, "final_fail": 1,
              "fixed": 2, "failed": 0, "manual": 1 },
    "findings_table": [
      {"stt": 1, "finding": "s3_bucket_public_access", "service": "s3",
       "resource": "arn:aws:s3:::my-bucket", "severity": "critical",
       "before": "FAIL", "after": "PASS", "change": "Fixed"}
    ],
    "success_findings": [
      {"finding_id": "f001", "action": "Block public access",
       "resource": "my-bucket", "description": "S3 bucket public access blocked"}
    ],
    "failed_findings": [],
    "manual_findings": [
      {"finding_id": "f002", "description": "Enable S3 versioning",
       "resource": "my-bucket", "severity": "high",
       "manual_reason": "Requires business approval"}
    ],
    "raw_pre_findings": [...],
    "environment": { "account_id": "123456789012", "region": "ap-southeast-1",
                     "buckets": ["my-bucket"] },
    "scope": { "services": ["s3"], "date": "2026-04-05",
               "user_request": "Kiem tra bao mat S3 bucket" }
  },
  "expected": {
    "expected_finding_ids": ["s3_bucket_public_access", "s3_bucket_versioning",
                             "s3_bucket_encryption"],
    "expected_stats": { "total": 10, "fail": 3, "fixed": 2, "manual": 1 },
    "bypass_sections": []
  }
}
```

---

## 3. Metrics Evaluation

### 3.1 Tong quan 4 truc danh gia

| Truc | Do gi | Cach tinh | Chi phi |
|------|-------|-----------|---------|
| **Structure** | Output co su dung duoc khong | Gate check: HTML valid, sections, template leak, None display | 0 |
| **Correctness** | Template-rendered data co dung khong | stats, findings table, score, status colors | 0 |
| **Faithfulness** | LLM narrative co bia so lieu khong | Numerical claims vs `report_data` | 0 |
| **Completeness** | Report co du findings, bypass dung khong | Findings coverage + bypass logic | 0 |

**Dac thu Report Agent**: Tat ca 10 core metrics deu **deterministic** (0 LLM judge calls). Ly do: output gom 2 tang ro rang — template (kiem tra bang parsing) va LLM narrative (kiem tra so lieu bang regex extraction). Khac voi Risk Agent can LLM-as-Judge cho faithfulness.

### 3.2 Structure — Gate Check

**Vai tro**: Gate check — fail bat ky hard constraint nao → output khong su dung duoc, cac metric khac khong can tinh.

*Hard constraints (fail 1 = fail output):*

| Sub-metric | Cach tinh |
|---|---|
| `html_valid` | `<!DOCTYPE html>` + `<html lang="vi">` + `charset="utf-8"` |
| `section_presence_rate` | 7 sections bat buoc co mat trong HTML (Jinja2 headings) |
| `no_template_leak` | Khong co `{{ }}`, `{% %}`, placeholder `[...]` ngoai code blocks |
| `no_none_display` | Khong co Python "None" hien thi trong text (BUG-02) |

*Soft constraints (warning, khong block):*

| Sub-metric | Cach tinh |
|---|---|
| `cover_page_complete` | Account ID (12 so), Region, Date, Report ID (RPT-XXXXXXXX-XXXX), Score |
| `chart_presence` | severity_bar.png + pass_fail_pie.png ton tai |

### 3.3 Correctness — Deterministic Data Accuracy

Chi do **template-rendered layer** (Jinja2 output). Phan nay deterministic — khong phu thuoc LLM.

| Sub-metric | Cach tinh |
|---|---|
| `stats_accuracy` | pre.total, pre.fail, post.fixed... khop voi `report_data`? HTML parsing |
| `findings_table_accuracy` | Bang section 4 co dung so dong? Severity badges dung CSS class? |
| `score_accuracy` | Security Score tren cover page = `_calc_score(pre, post)`? |
| `status_color_accuracy` | Fixed → `.status-fixed`, Manual → `.status-manual`, Failed → `.status-error`? |

**Phan biet voi Faithfulness**: Correctness kiem tra phan **template render** (`{{ pre.total }}`). Faithfulness kiem tra phan **LLM viet** (narrative text). Template sai = bug code. LLM sai = hallucination.

### 3.4 Faithfulness — Numerical Claims in Narrative

Core metric (deterministic, chi phi = 0). Trich xuat so lieu tu LLM narrative sections, so khop voi `report_data`.

**Phuong phap**:
1. Build "known numbers" set tu `report_data` (pre.total, pre.fail, post.fixed, severity counts, _calc_score, len(findings)...)
2. Them "infrastructure numbers" (100, 256, 2026 — xuat hien hop le trong report)
3. Extract 7 LLM sections tu HTML bang regex
4. Extract tat ca so tu LLM text
5. Kiem tra moi so co nam trong known set khong

```
Numerical Faithfulness = (So claims so lieu dung) / (Tong claims so lieu trong narrative)
```

**Tai sao chi numerical cho core?** Sai so lieu nghiem trong hon sai dien dat trong bao cao bao mat. "5 Critical findings" khi thuc te co 3 → quyet dinh sai. LLM paraphrase sai y → chi anh huong readability.

### 3.5 Completeness — Findings Coverage + Bypass Logic

| Sub-metric | Cach tinh |
|---|---|
| `findings_coverage` | event_codes tu `findings_table` xuat hien trong HTML? Coverage = found / total. Khi `findings_table` rong (all-pass) → vacuously 1.0 |
| `conditional_bypass_correctness` | Khi `pre.pass == 0`: pass_overview = hardcoded text. Khi `pre.fail == 0`: tuong tu. Kiem tra bypass logic dung |

---

## 4. Release Criteria

| # | Criterion | Nguong | Truc | Mo ta |
|---|-----------|:------:|:----:|-------|
| 1 | `html_valid` | 1.00 | Structure | HTML5 hop le |
| 2 | `section_presence_rate` | 1.00 | Structure | 7/7 sections co mat |
| 3 | `no_template_leak` | 1.00 | Structure | Khong lo Jinja2 syntax |
| 4 | `no_none_display` | 1.00 | Structure | Khong hien "None" |
| 5 | `stats_accuracy` | 1.00 | Correctness | So lieu template dung |
| 6 | `findings_table_accuracy` | 1.00 | Correctness | Bang findings dung |
| 7 | `score_accuracy` | 1.00 | Correctness | Security Score dung |
| 8 | `numerical_faithfulness` | 0.90 | Faithfulness | LLM khong bia so lieu |
| 9 | `findings_coverage` | 0.90 | Completeness | Khong bo sot findings |
| 10 | `conditional_bypass_correctness` | 1.00 | Completeness | Bypass logic dung |

**Verdict**: PASS khi tat ca 10 criteria deu dat.

File cau hinh: `benchmark_llm_gen/release_criteria_report.json`

---

## 5. Ket qua cuoi cung

### 5.1 Metrics tong hop (llama3.2, 19 cases)

| Metric | Gia tri | Nguong | Margin | Verdict |
|--------|:-------:|:------:|:------:|:-------:|
| HTML Valid | **100%** | 100% | +0pp | PASS |
| Section Presence | **100%** | 100% | +0pp | PASS |
| No Template Leak | **100%** | 100% | +0pp | PASS |
| No None Display | **94.74%** | 100% | -5.26pp | FAIL |
| Stats Accuracy | **100%** | 100% | +0pp | PASS |
| Findings Table Accuracy | **100%** | 100% | +0pp | PASS |
| Score Accuracy | **100%** | 100% | +0pp | PASS |
| Numerical Faithfulness | **0.719** | 0.90 | -0.181 | FAIL |
| Findings Coverage | **100%** | 90% | +10pp | PASS |
| Bypass Correctness | **100%** | 100% | +0pp | PASS |
| **Overall Verdict** | | | | **FAIL (8/10)** |

### 5.2 Ket qua theo scenario

| Scenario | n | Gate | Stats | Faith | Coverage |
|----------|:-:|:----:|:-----:|:-----:|:--------:|
| standard | 3 | 100% | 100% | **0.765** | 100% |
| all_pass | 2 | 100% | 100% | 0.675 | 100% |
| all_fail | 2 | 100% | 100% | **0.775** | 100% |
| minimal | 2 | 100% | 100% | 0.208 | 100% |
| missing_fields | 2 | 50% | 100% | 0.792 | 100% |
| mixed_case_status | 2 | 100% | 100% | 0.782 | 100% |
| multi_service | 2 | 100% | 100% | **0.962** | 100% |
| high_volume | 1 | 100% | 100% | 0.667 | 100% |
| zero_severity | 1 | 100% | 100% | 0.667 | 100% |
| complex_remediation | 2 | 100% | 100% | **0.824** | 100% |

### 5.3 Ket qua theo group

| Group | n | Gate | Stats | Faith | Coverage |
|-------|:-:|:----:|:-----:|:-----:|:--------:|
| A_scenario | 9 | **100%** | 100% | 0.624 | 100% |
| B_edge_case | 10 | 90% | 100% | **0.805** | 100% |

**Nhan xet**: Edge cases (B) co faithfulness cao hon scenario (A). Ly do: edge cases thuong co data cu the, ro rang hon → LLM it bia dat. Scenario group co all_pass va minimal voi data rong/it → LLM hay hallucinate so lieu.

### 5.4 Per-case results

| Case ID | Scenario | Gate | Score | Stats | Faith | Bug |
|---------|----------|:----:|:-----:|:-----:|:-----:|:---:|
| report_standard_001 | standard | PASS | 86 | 1.00 | 0.714 | |
| report_standard_002 | standard | PASS | 74 | 1.00 | 0.889 | |
| report_standard_003 | standard | PASS | 77 | 1.00 | 0.692 | |
| report_all_pass_001 | all_pass | PASS | 90 | 1.00 | 0.750 | |
| report_all_pass_002 | all_pass | PASS | 90 | 1.00 | 0.600 | |
| report_all_fail_001 | all_fail | PASS | 62 | 1.00 | 0.750 | |
| report_all_fail_002 | all_fail | PASS | 42 | 1.00 | 0.800 | |
| report_minimal_001 | minimal | PASS | 70 | 1.00 | **0.000** | |
| report_minimal_002 | minimal | PASS | 97 | 1.00 | 0.417 | |
| report_missing_fields_001 | missing_fields | PASS | 60 | 1.00 | 0.727 | BUG-02 |
| report_missing_fields_002 | missing_fields | **FAIL** | 50 | 1.00 | 0.857 | BUG-02 |
| report_mixed_case_001 | mixed_case_status | PASS | 66 | 1.00 | 0.800 | BUG-03 |
| report_mixed_case_002 | mixed_case_status | PASS | 62 | 1.00 | 0.765 | BUG-03 |
| report_multi_service_001 | multi_service | PASS | 83 | 1.00 | **1.000** | BUG-05 |
| report_multi_service_002 | multi_service | PASS | 96 | 1.00 | 0.923 | BUG-05 |
| report_high_volume_001 | high_volume | PASS | 87 | 1.00 | 0.667 | |
| report_zero_severity_001 | zero_severity | PASS | 90 | 1.00 | 0.667 | |
| report_complex_remediation_001 | complex_remediation | PASS | 64 | 1.00 | 0.765 | |
| report_complex_remediation_002 | complex_remediation | PASS | 60 | 1.00 | 0.882 | |

---

## 6. Phan tich loi

### 6.1 Gate FAIL: `no_none_display` (1/19 cases)

**Case fail**: `report_missing_fields_002` — input co `action=null`, `description=null`, `resource=null`, `severity=null`, `manual_reason=null` dong thoi.

**Nguyen nhan**: LLM nhan None values tu Python va viet "None" trong narrative text. Template `| default()` fix duoc phan Jinja2 render, nhung LLM text van chua "None".

**Fix da ap dung**:
- Template: Them `| default('N/A')` tai 8 vi tri (section 5.1, 5.2, 5.3, 6.2)
- Report Agent: `_enrich_success/failed()` truyen `action or "N/A"`, `resource or "N/A"` thay vi None
- LLM Writer: `_clean()` them regex `None` → `N/A`

**Ket qua**: Giam tu 8 occurrences xuong 4, nhung van fail (LLM van sinh "None" o context kho match). Day la **LLM variance** — moi run LLM sinh text khac nhau, mot so run co the PASS.

### 6.2 Numerical Faithfulness thap (0.719)

**Cases co faithfulness thap nhat**:

| Case | Faith | Verified | Total | Van de |
|------|:-----:|:--------:|:-----:|--------|
| report_minimal_001 | **0.000** | 0 | 6 | LLM bia 6 so lieu khi chi co 1 finding |
| report_minimal_002 | **0.417** | 5 | 12 | LLM sinh nhieu so lieu khong can thiet |
| report_all_pass_002 | **0.600** | 3 | 5 | LLM them so lieu khi data rong |
| report_high_volume_001 | **0.667** | 20 | 30 | Nhieu so lieu trong narrative dai |
| report_zero_severity_001 | **0.667** | 2 | 3 | LLM bia so khi tat ca severity = 0 |

**Pattern chung**: LLM 3B (llama3.2) co xu huong:
1. **Hallucinate numbers khi data it/rong** — `minimal` va `all_pass` faith thap nhat
2. **Viet so lieu "hop ly nhung sai"** — vi du: noi "4 loi" khi thuc te co 3, noi "5 checks" khi co 2
3. **Khong tuan thu constraint** "Neu data bang 0, neu ro su that. KHONG suy doan" — du da co trong `_OUTPUT_CONSTRAINTS`

**Cases co faithfulness cao nhat**:

| Case | Faith | Nhan xet |
|------|:-----:|----------|
| report_multi_service_001 | **1.000** | Data ro rang (3 services, 3 findings), LLM viet chinh xac |
| report_multi_service_002 | **0.923** | Tuong tu, data structured tot |
| report_standard_002 | **0.889** | Data du lon (6 findings) de LLM bam vao |
| report_complex_remediation_002 | **0.882** | Data chi tiet, LLM co nhieu context |

**Ket luan**: Faithfulness ti le thuan voi **luong data co san**. Khi data nhieu va cu the, LLM viet chinh xac. Khi data it/rong, LLM bia dat.

### 6.3 Bug regression results

| Bug | Test cases | Ket qua | Nhan xet |
|-----|-----------|---------|----------|
| BUG-02 (None display) | missing_fields_001, 002 | 1 PASS, 1 FAIL | Template fix OK, nhung LLM van co the sinh "None" |
| BUG-03 (case-sensitive status) | mixed_case_001, 002 | 2 PASS | `row.change\|lower` hoat dong dung voi moi case |
| BUG-05 (raw list scope) | multi_service_001, 002 | 2 PASS | `scope.services \| join(', ') \| upper` render dung "S3, IAM, EC2" |

---

## 7. Cai tien da ap dung (trong qua trinh benchmark)

### 7.1 Metric fix: findings_table_accuracy

**Van de**: Regex `Bảng chi tiết phát hiện.*?<tbody>` match sai table (section 6.1 thay vi section 4).

**Giai phap**: Regex cu the hon: `Bảng chi tiết phát hiện</h1>\s*<table class="styled-table">.*?<tbody>`.

**Ket qua**: findings_table_accuracy 0% → 100%.

### 7.2 Metric fix: findings_coverage

**Van de**: Coverage tinh ca `finding_id` (internal ID, khong render) va `raw_pre_findings` event_codes (PASS findings, khong co trong findings_table). All-pass cases co 0% coverage (0 findings in table).

**Giai phap**: Chi tinh `findings_table.finding` (rendered trong HTML). Khi `findings_table` rong → vacuously 1.0.

**Ket qua**: findings_coverage 89.47% → 100%.

### 7.3 Faithfulness noise filter

**Van de**: Narrative chua "AES-256" → 256, "2026-04-05" → 2026, "x/100" → 100 bi tinh la "unknown numbers".

**Giai phap**: Them `_INFRASTRUCTURE_NUMBERS = {100, 256, 2024, 2025, 2026, 2027}` vao known set.

### 7.4 Template `| default()` fallback (P0 fix)

**Van de**: 8 vi tri trong template.py render None truc tiep khi fields null.

**Giai phap**: Them `| default('N/A')` hoac `| default('Remediation Action')` tai:
- Section 5.1: `f.resource`
- Section 5.2: `f.resource`
- Section 5.3: `f.description`, `f.resource`, `f.severity`
- Section 6.2: 3 lists (success, manual, failed) — `f.description`, `f.resource`

### 7.5 Conditional bypass mo rong (P1 fix)

**Van de**: All-pass cases (fail=0, fixed=0) van goi LLM cho executive_summary, post_analysis, recommendations → LLM hallucinate khi "khong co gi de viet".

**Giai phap**: Khi `pre.fail == 0 AND post.fixed == 0 AND post.failed == 0`, su dung hardcoded text voi so lieu cu the tu `report_data` (account_id, region, services, total, pass count).

**Ket qua**: all_pass faithfulness tang tu 0.56 → 0.675. Latency giam tu ~17s → ~7s (skip 3 LLM calls).

### 7.6 LLM Writer `_clean()` None handling

**Van de**: LLM nhan Python None values (qua enrichment params) va viet "None" trong text.

**Giai phap**: Regex `(?<=["\s])None(?=["\s,.\)])` → `N/A` trong `_clean()`.

---

## 8. Kien truc ky thuat

### 8.1 Pipeline evaluation

```
benchmark_report_cases.json (19 cases)
    |
    v
[load_cases] → validate 9 required input fields
    |
    v
[run_inference] → ReportAgent.run(data=case["input"])
    |                  ├── Charts (matplotlib)
    |                  ├── LLM sections (7 + N per-finding)
    |                  └── Jinja2 render → HTML + MD + PDF
    |
    v
[save_inference] → HTML files + inference JSON
    |
    v
[run_evaluation] → 4 truc metrics (100% deterministic)
    |   ├── evaluate_structure(html)    → gate check
    |   ├── evaluate_correctness(html, report_data) → template accuracy
    |   ├── evaluate_faithfulness(html, report_data) → numerical claims
    |   └── evaluate_completeness(html, report_data) → coverage + bypass
    |
    v
[aggregate_results] → summary + breakdowns + release criteria
    |
    v
[save_report] → JSON + print console summary
```

### 8.2 Files lien quan

| File | Vai tro |
|------|---------|
| `agents/report_agent.py` | Agent chinh — pipeline 5 buoc (425 dong) |
| `agents/report_module/llm_writer.py` | LLM calls + _clean() + fallback (542 dong) |
| `agents/report_module/template.py` | Full HTML5 template + CSS (361 dong) |
| `agents/report_module/exporters.py` | write_file, export_pdf (101 dong) |
| `agents/report_module/chart_util.py` | matplotlib charts (77 dong) |
| `benchmark_llm_gen/benchmark_report.py` | Benchmark engine — 5 buoc |
| `benchmark_llm_gen/run_report_benchmark.py` | CLI entry point |
| `benchmark_llm_gen/report_metrics.py` | 4 metrics implementation |
| `benchmark_llm_gen/benchmark_report_cases.json` | 19 test cases |
| `benchmark_llm_gen/release_criteria_report.json` | 10 nguong PASS/FAIL |

### 8.3 Cach chay benchmark

```bash
# Chay full benchmark (inference + evaluate)
python benchmark_llm_gen/run_report_benchmark.py --mode full

# Chi chay inference, luu output
python benchmark_llm_gen/run_report_benchmark.py --mode inference-only

# Chi evaluate tu inference co san (re-evaluate voi metrics moi)
python benchmark_llm_gen/run_report_benchmark.py --mode evaluate-only \
  --inference-dir benchmark_llm_gen/inference_outputs/report_run_YYYYMMDD_HHMMSS

# Custom test cases
python benchmark_llm_gen/run_report_benchmark.py --mode full \
  --cases benchmark_llm_gen/benchmark_report_cases_mini.json

# Debug mode
python benchmark_llm_gen/run_report_benchmark.py --mode full -v
```

Yeu cau:
- Ollama running (`ollama serve`) voi model llama3.2:latest
- Python packages: jinja2, matplotlib, pyyaml, langchain-ollama

### 8.4 Latency

| Scenario | n | Mean | Min | Max | Ghi chu |
|----------|:-:|:----:|:---:|:---:|---------|
| standard | 3 | 27.4s | 24.4s | 31.1s | 7 LLM + 2-3 per-finding |
| all_pass | 2 | 7.5s | 7.5s | 7.6s | Bypass 3 LLM sections |
| all_fail | 2 | 26.2s | 23.4s | 29.0s | 3-4 per-finding |
| minimal | 2 | 27.0s | 23.7s | 30.3s | 1 per-finding nhung LLM cham |
| missing_fields | 2 | 25.2s | 24.3s | 26.1s | |
| mixed_case | 2 | 27.1s | 25.8s | 28.3s | |
| multi_service | 2 | 27.2s | 24.6s | 29.8s | |
| high_volume | 1 | **69.8s** | — | — | 15 per-finding calls |
| complex_remediation | 2 | 31.6s | 29.4s | 33.7s | 4 per-finding + nested data |

**Trung binh toan benchmark**: 26.9s/case. Bottleneck la so luong LLM calls (ti le voi so findings).

---

## 9. Han che

1. **19 cases** khong du de tinh statistical significance. Faithfulness co variance cao giua cac run (LLM non-deterministic o temperature 0.3). Day la directional evaluation.

2. **Numerical faithfulness** chi kiem tra so lieu, khong kiem tra **noi dung dien dat**. LLM co the viet "he thong an toan" khi thuc te co Critical findings — faithfulness van = 1.0 neu khong co so sai. Can `narrative_faithfulness` (LLM-as-Judge, extension layer) de catch.

3. **No None display** phu thuoc LLM behavior. Du da fix template + `_clean()` + param fallback, LLM 3B van co the sinh "None" o context bat ngo. Chi giai quyet triet de bang model lon hon hoac them nhieu `_clean()` rules.

4. **All deterministic metrics** khong do **chat luong van ban** (coherence, actionability, professional tone). Can G-Eval (extension layer) de danh gia.

5. **Single model**: Chi test llama3.2. Model khac (qwen3:8b, phi4-mini) co the cho ket qua khac — can multi-model comparison.

6. **RAG Ablation da thuc hien**: Xem Section 11 — benchmark No-RAG vs With-RAG (real LLM, deterministic metrics). Ket qua: specific terms +143%, RAG grounding +700%, latency -18%, 0 regression.

7. **High volume case** (report_high_volume_001) chi co 1 case → khong du de tinh trung binh. Latency 70s co the la bottleneck trong production voi nhieu findings.

---

## 10. Ket luan

Report Agent voi **template-first, LLM-enriched architecture** dat:

**Diem manh (deterministic layer — 100% across the board):**
- **Structure**: HTML5 hop le, 7 sections, khong template leak, cover page day du — 100%
- **Correctness**: Stats, findings table, security score, status colors — **100%** (template rendering flawless)
- **Completeness**: Findings coverage 100%, bypass logic 100%

**Diem yeu (LLM layer — phu thuoc model quality):**
- **Faithfulness**: 0.719 — LLM 3B hallucinate so lieu, dac biet khi data it/rong
- **None display**: 94.74% — LLM van sinh "None" du da fix template + clean

**So sanh voi Risk/Planning Agent:**

| Khia canh | Risk Agent | Planning Agent | Report Agent |
|-----------|:----------:|:--------------:|:------------:|
| Verdict | **PASS (6/6)** | **PASS (6/6)** | FAIL (8/10) |
| LLM dependency | Moi case | 0% (deterministic) | 7 + N per-finding |
| RAG dependency | Bat buoc | Bat buoc | Optional (graceful degradation) |
| RAG impact | Core (scoring) | Core (check discovery) | Enrichment (+143% specific terms) |
| Faithfulness | 0.950 (claim-based) | 1.000 (trivial) | 0.719 (numerical) |
| Correctness | 83.3% (severity) | 75.9% (composite) | **100%** (template) |

**Huong cai thien:**
1. **RAG da tich hop** (Section 11) — specific terms +143%, RAG grounding +700%, latency -18%
2. **Mo rong conditional bypass** cho nhieu LLM sections hon — giam hallucination khi data it
3. **Model lon hon** (qwen3:8b, phi4-mini 3.8B) — kha nang tuan thu constraints tot hon
4. **Them `_clean()` rules** — strict hon voi pattern "None", so lieu ngoai range
5. **Extension layer**: Trien khai `narrative_faithfulness` (LLM-as-Judge) va `correctness_judge_mean` khi core metrics on dinh
6. **RAG + Model upgrade ket hop** — chay lai benchmark voi model lon hon + RAG de do cai thien faithfulness

---

## 11. RAG Ablation Study

### 11.1 Boi canh

Report Agent truoc day **khong dung RAG** — LLM viet narrative chi dua tren so lieu thong ke (pass/fail count, severity count), **khong co kien thuc chuyen mon** ve tung check cu the.

Sau khi tich hop RAG (`RAGClient.build_context(consumer="report")`), LLM nhan them:
- **key_findings**: risk_summary chinh thuc tu Prowler database
- **control_themes**: maturity capabilities (Data Protection, Access Control, Data Resilience)
- **recommended_practices**: best practices cu the (SSE-KMS, Block Public Access, MFA Delete...)

### 11.2 Thiet ke benchmark

| Thong so | Gia tri |
|----------|---------|
| Model | llama3.2:latest (3.2B) |
| Variant A | No RAG — `rag_context = {}` |
| Variant B | With RAG — simulated `report_bundle` (5 key_findings, 3 control_themes, 5 practices) |
| Test data | 19 findings (8 PASS, 11 FAIL), 3 success, 1 manual, 4 buckets |
| Metrics | Deterministic: word count, specific terms, RAG grounding, hallucination, placeholder/first-person |
| LLM | Real Ollama inference (khong mock) |

**Benchmark scripts:**
- `benchmark_llm_gen/benchmark_rag_comparison.py` — MockLLM, do structure/correctness (32/32 tests)
- `benchmark_llm_gen/benchmark_rag_text_quality.py` — Real LLM, do text quality

### 11.3 Ket qua chi tiet

#### Performance

| Metric | No RAG | With RAG | Delta |
|--------|:------:|:--------:|:-----:|
| Total latency | 40.6s | **33.4s** | -18% |
| LLM latency | 39.1s | **32.4s** | -17% |
| LLM calls | 11 | 11 | 0 |

**Nhan xet**: With-RAG **nhanh hon** 18%. RAG context giup LLM focus nhanh hon — co "cau tra loi mau" trong prompt nen generate it token hon truoc khi dat dung noi dung.

#### Content Volume

| Metric | No RAG | With RAG | Delta |
|--------|:------:|:--------:|:-----:|
| Word count | 3,062 | 3,017 | -45 |
| Unique words (>3 chars) | 513 | **552** | **+39** |

**Nhan xet**: With-RAG viet **ngan gon hon** (it 45 tu) nhung **vocabulary phong phu hon** (them 39 tu unique). Day la dau hieu cua content chat luong cao hon — it repetition, nhieu thuat ngu chinh xac.

#### Data Accuracy

| Metric | No RAG | With RAG |
|--------|:------:|:--------:|
| Number accuracy (5 checks) | **100%** | **100%** |
| Placeholder leaks | 0 | 0 |
| First person leaks | 0 | 0 |

**Nhan xet**: RAG **khong gay regression** tren data accuracy. So lieu van chinh xac 100%, `_clean()` hoat dong tot ca 2 variant.

#### Specificity — Security Knowledge Quality

| Metric | No RAG | With RAG | Delta |
|--------|:------:|:--------:|:-----:|
| Specific security terms | 7 | **17** | **+143%** |
| Generic filler terms | 1 | 1 | 0 |
| Specificity ratio | 88% | **94%** | +6pp |

**Chi tiet specific terms:**

| No RAG (7 terms) | With RAG (17 terms) |
|---|---|
| MFA Delete | **SSE-KMS** |
| versioning | **SSE-S3** |
| compliance | **encryption at rest** |
| CIS | **SecureTransport** |
| Well-Architected | **TLS** |
| boto3 | **public access block** |
| put_bucket_versioning | MFA Delete |
| | versioning |
| | **data loss** |
| | **data breach** |
| | **ransomware** |
| | compliance |
| | CIS |
| | Well-Architected |
| | boto3 |
| | put_bucket_versioning |
| | **server access logging** |

**10 terms moi hoan toan** (in dam) xuat hien chi trong With-RAG — tat ca la thuat ngu bao mat chinh xac tu RAG knowledge base.

#### RAG Grounding

| Metric | No RAG | With RAG | Delta |
|--------|:------:|:--------:|:-----:|
| RAG-grounded terms | 1 | **8** | **+700%** |

**Terms grounded (With RAG):** Access Control, Data Resilience, SSE-KMS, public access block, MFA Delete, data breach, ransomware, encryption at rest

**Nhan xet**: No-RAG chi co 1 term trung voi RAG knowledge (MFA Delete — xuat hien tu nhien trong tool_code). With-RAG co **8 terms** truc tiep tu RAG bundle → LLM da **su dung** kien thuc duoc cung cap thay vi suy doan.

### 11.4 Structure & Correctness (MockLLM benchmark)

Chay rieng voi MockLLM de kiem tra RAG khong pha structure:

| Metric | No RAG | With RAG |
|--------|:------:|:--------:|
| Structure gate | **12/12** | **12/12** |
| Content accuracy | **All PASS** | **All PASS** |
| RAG-enriched prompts | 0/18 | **9/18** |

**9/18 prompts** duoc RAG enrich:
- Executive Summary (key_findings + control_themes + practices)
- PASS Findings Overview (control_themes)
- FAIL Findings Overview (control_themes)
- 3x Per-finding success detail (rag_risk)
- 1x Manual guide (rag_context: title + risk_summary)
- Recommendations (recommended_practices)

### 11.5 Tom tat RAG Ablation

```
                        No RAG          With RAG        Verdict
                        ------          --------        -------
Specific terms          7               17 (+143%)      IMPROVED
RAG grounding           1               8 (+700%)       IMPROVED
Specificity ratio       88%             94% (+6pp)      IMPROVED
Unique vocabulary       513             552 (+39)       IMPROVED
Latency                 40.6s           33.4s (-18%)    IMPROVED
Number accuracy         100%            100%            MAINTAINED
Placeholder leaks       0               0               MAINTAINED
First person leaks      0               0               MAINTAINED
Structure gate          12/12           12/12           MAINTAINED
Content accuracy        All PASS        All PASS        MAINTAINED
```

**Ket luan RAG Ablation:**
- RAG **cai thien ro ret** chat luong text: +143% specific terms, +700% grounding, +6pp specificity
- RAG **khong gay bat ky regression nao**: accuracy 100%, structure 12/12, 0 leaks
- RAG **giam latency 18%**: LLM generate nhanh hon khi co context cu the
- RAG la **optional** — report van hoat dong hoan hao khi RAG down (graceful degradation)

### 11.6 Han che cua benchmark

1. **1 run duy nhat** — LLM non-deterministic, can nhieu run de tinh mean + std
2. **Simulated RAG bundle** — khong goi RAG API that, dung data co dinh. Ket qua thuc te phu thuoc RAG retrieval quality
3. **Chi do specificity** — khong do coherence, readability, hay actionability cua text
4. **Chua do faithfulness delta** — can re-run full 19-case benchmark voi RAG de so sanh faithfulness 0.719 vs with-RAG

### 11.7 Huong tiep theo

1. **Re-run full benchmark (19 cases) voi RAG** de so sanh faithfulness va None display rate
2. **Multi-run** (3-5 runs moi variant) de tinh statistical significance
3. **Model upgrade + RAG**: Test qwen3:8b voi RAG — ky vong faithfulness dat threshold 0.90
4. **Live RAG benchmark**: Goi RAG API that thay vi simulated bundle
