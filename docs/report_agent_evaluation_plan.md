# Report Agent Generation Evaluation — Framework v3 Plan

**Version:** 3.0 (Final — chốt để implement)
**Scope:** Evaluation framework cho Report Agent **sau overhaul** (theo `REPORT_AGENT_IMPROVEMENT_PLAN.md`)
**Mục đích:** Đo lường đúng, kể được story cho LVTN — mỗi metric = 1 insight
**Timeline:** 2 ngày implement

---

## 0. Bối cảnh

Report Agent đã rebuild với 5 năng lực mới:

1. **Scope Generalization** — `scope_detector.py` phát hiện service từ findings, tránh S3-bias
2. **Data Pipeline Hardening** — `remediation_recommendation` preserve qua normalization
3. **Bundle Factory Rebuild** — `ReportBundle.capability_details` populated
4. **View-based RAG** — `rag_formatter.py` slice context theo section
5. **Output Validation Layer** — `ReportValidator` gate với 4 checks: `off_scope`, `hallucinated_number`, `wrong_term`, `ungrounded`

Framework evaluation cũ (`benchmark_report.py`, `report_metrics.py`) thiết kế cho agent **trước** overhaul — không đo được các năng lực mới. Cần v3.

---

## 1. Nguyên tắc thiết kế

1. **Correctness > Coverage** — ít metric nhưng mỗi cái kể 1 story, không 28 metric overlap
2. **Deterministic first, LLM-judge second** — core là deterministic (reproducible, cost=0), LLM-judge bổ sung chiều chất lượng
3. **Grouping theo capability, không theo service** — mỗi nhóm case test 1 năng lực cụ thể của agent
4. **Ablation first-class** — no_rag vs with_rag_v2 để chứng minh RAG contribution
5. **Thesis-ready** — mỗi nhóm case map sang 1 subsection LVTN

---

## 2. Kiến trúc 5 trục

```
SCOPE FIDELITY    "Output nhắc đúng service/resource trong scan scope?"   ★ gate mới
     ↓
STRUCTURE         "HTML parse được, đủ section, không template leak?"       gate cũ
     ↓
FAITHFULNESS      "Số liệu + capability truy nguồn về input/RAG?"
     ↓
CORRECTNESS       "Template data (stats/score/table) khớp input?
                   Ranking severity đúng thứ tự?"
     ↓
QUALITY           "Khuyến nghị executable?"                                 LLM-judge
```

Scope Fidelity đặt trên cùng vì nếu output nhắc sai service (fixture F nhắc "S3" khi scan IAM) thì mọi metric khác vô nghĩa — không phải sai số, mà sai chủ thể.

---

## 3. Core metrics — 9 metrics

| # | Trục | Metric | Loại | Threshold | Thesis story |
|---|------|--------|------|-----------|--------------|
| 1 | Structure | `structure_pass_rate` (html_valid ∧ sections ∧ no_leak ∧ no_none) | Determ | ≥ 1.00 HARD | Output không broken |
| 2 | Scope ★ | `off_scope_mention_rate` | Determ | ≤ 0.02 HARD | De-S3-bias headline (v1 0.28 → v2 0) |
| 3 | Scope | `scope_accuracy` | Determ | ≥ 1.00 HARD | Dynamic scope detection đúng 100% |
| 4 | Faithfulness | `numerical_faithfulness` | Determ | ≥ 0.90 HARD | Validator gate fix 71.9% → ≥ 90% |
| 5 | Faithfulness | `capability_grounding_rate` | Determ | ≥ 0.85 SOFT | RAG evidence consume, không bịa |
| 6 | Faithfulness | `claim_support_rate` | **LLM-Judge** | ≥ 0.85 SOFT | RAGAS-style faithfulness |
| 7 | Correctness | `template_data_accuracy` (stats+table+score+badge gộp 1) | Determ | ≥ 1.00 HARD | Hybrid template+LLM đảm bảo số cứng |
| 8 | Correctness | `ndcg_at_5_severity` | Determ | ≥ 0.85 SOFT | Ưu tiên Critical/High đúng thứ tự |
| 9 | Quality | `actionability_likert` (1–5) | **LLM-Judge** | ≥ 3.5 SOFT | Khuyến nghị executable |

**5 HARD + 4 SOFT.** HARD fail → release fail. SOFT là hướng tối ưu.

---

## 4. Dataset — 24 cases, 5 nhóm theo capability

### 4.1 Grouping

| Nhóm | Cases | Capability đánh giá | Primary metric |
|------|-------|---------------------|----------------|
| **C1 Scope Detection** | 5 | Phát hiện scope từ findings, dynamic terminology | `scope_accuracy`, `off_scope_mention_rate` |
| **C2 Hallucination Stress** | 5 | Chống LLM bịa số/capability khi data sparse | `numerical_faithfulness`, `capability_grounding`, `claim_support` |
| **C3 Prioritization/Ranking** | 4 | Ưu tiên Critical/High đúng thứ tự narrative | `ndcg_at_5_severity` |
| **C4 Structural Robustness** | 5 | Template+LLM hybrid không vỡ trên edge input | `structure_pass_rate`, `template_data_accuracy` |
| **C5 RAG Grounding** | 5 | Narrative bám RAG evidence thay vì bịa | `capability_grounding_rate`, `claim_support_rate`, `actionability_likert` |
| **TOTAL** | **24** | | |

### 4.2 Cases detail

**C1 — Scope Detection (5):**
- `c1_single_s3_dominant` — 8 findings S3 → expect primary=s3
- `c1_single_iam_dominant` ★ — 8 findings IAM → expect primary=iam (bias test)
- `c1_single_ec2_dominant` — 8 findings EC2 → expect primary=ec2
- `c1_two_service_balanced` — S3+IAM 50/50 → expect is_multi, "AWS resources"
- `c1_four_service_wide` — S3+IAM+EC2+RDS → expect is_multi, generic

**C2 — Hallucination Stress (5):**
- `c2_minimal_1_finding` — 1 finding duy nhất (LLM hay bịa để "lấp đầy")
- `c2_all_pass_zero_fail` — 0 fail (LLM hay bịa fake findings)
- `c2_sparse_rag_low_confidence` — RAG bundle thin (LLM hay phịa capability)
- `c2_numbers_trap` — Pre/post stats gần giống nhau (test numerical confusion)
- `c2_capability_absent_in_rag` — Capability không có trong RAG (test ungrounded check)

**C3 — Prioritization (4):**
- `c3_multi_severity_balanced` — Critical+High+Medium+Low mỗi 2-3 cái
- `c3_one_critical_dominant` — 1 Critical + nhiều Low (Critical phải xuất hiện đầu)
- `c3_inverted_description_trap` — Low mô tả dài, Critical mô tả ngắn (trap)
- `c3_findings_100plus_top5` — 100+ findings, top-5 phải đúng thứ tự severity

**C4 — Structural Robustness (5):**
- `c4_missing_optional_fields` — Không có remediation/recommendation
- `c4_mixed_case_status` — FAIL/fail/Fail lẫn lộn
- `c4_unicode_escape_chars` — Vietnamese diacritics + JSON escape
- `c4_empty_env_empty_findings` — Zero baseline
- `c4_post_remediation_delta` — Pre+post full flow

**C5 — RAG Grounding (5):**
- `c5_rich_rag_full_capdetails` — Full capability_details với rich field
- `c5_sparse_rag_low_conf` — Bundle confidence=low, capability_details rỗng
- `c5_conflicting_rag` — Capabilities không match findings
- `c5_rag_noise_injection` — Inject 3 capability không liên quan (adversarial)
- `c5_rag_empty_fallback` — Bundle hoàn toàn rỗng (test fallback)

### 4.3 Port baselines A–G

7 fixtures hiện có trong `tests/fixtures/report_baseline/input/` → reuse (không sinh lại):

| Baseline | → Case ID | Nhóm |
|----------|-----------|------|
| A (S3 all-pass) | `c2_all_pass_zero_fail` | C2 |
| B (S3 all-fail) | `c3_multi_severity_balanced` | C3 |
| C (S3 mixed) | `c1_single_s3_dominant` | C1 |
| D (S3 zero-findings) | `c4_empty_env_empty_findings` | C4 |
| E (S3 multi-bucket) | `c3_findings_100plus_top5` (với mở rộng) | C3 |
| F (IAM-only) ★ | `c1_single_iam_dominant` | C1 |
| G (multi-service) | `c1_two_service_balanced` | C1 |

→ Sinh mới **17 cases** (C1:2, C2:4, C3:3, C4:4, C5:5).

### 4.4 Schema mỗi case

```json
{
  "case_id": "c1_single_iam_dominant",
  "group": "C1_scope_detection",
  "input": {
    "report_data": { "pre": {...}, "post": {...}, "findings": [...], "env": {...} },
    "rag_snapshot": { "primary_topics": [...], "capability_details": [...], ... }
  },
  "expected": {
    "scope": { "primary_service": "iam", "service_list": ["iam"], "is_multi_service": false, "resource_term_plural": "roles and policies" },
    "forbidden_terms": ["s3", "bucket", "amazon s3"],
    "required_capabilities": ["Identity And Access Management"],
    "allowed_numbers_snapshot": [8, 5, 3, 12345678],
    "severity_ranking_gt": ["iam_check_critical_1", "iam_check_high_1", ...]
  }
}
```

---

## 5. Ablation study — 2 conditions

```
no_rag          Empty ReportBundle (primary_topics=[], capability_details=[], recommended_practices=[])
with_rag_v2     Full bundle (Phase 3 rebuild — capability_details + remediation_recommendation)
```

→ **48 report generations** (24 × 2). Cùng findings, cùng scope, chỉ khác RAG bundle.

### Expected contrast (để LVTN predict + verify)

| Metric | no_rag | with_rag_v2 | Δ expected | Insight |
|--------|--------|-------------|------------|---------|
| `scope_accuracy` | 1.00 | 1.00 | 0 | Scope từ findings, không cần RAG |
| `structure_pass_rate` | 1.00 | 1.00 | 0 | Template-driven |
| `off_scope_mention_rate` | 0.00 | 0.00 | 0 | Validator chặn cả 2 |
| `numerical_faithfulness` | 0.78 | 0.92 | +0.14 | RAG cung cấp context số |
| `ndcg_at_5_severity` | 0.85 | 0.87 | +0.02 | Nhỏ — ranking từ finding |
| `capability_grounding_rate` | 0.00 | 0.88 | **+0.88** ★ | RAG-only capability |
| `claim_support_rate` | 0.55 | 0.85 | **+0.30** ★ | RAG ground claims |
| `actionability_likert` | 2.8 | 4.0 | **+1.2** ★ | RAG cung cấp remediation text |
| `template_data_accuracy` | 1.00 | 1.00 | 0 | Deterministic |

Story LVTN: RAG có giá trị **chọn lọc** ở 3 metric quan trọng, không universal — framework discriminative, đo đúng chỗ.

---

## 6. LLM-Judge setup

### 6.1 Provider

**Primary: Gemini Flash Latest** (Google AI Studio free tier)
- API key: https://aistudio.google.com/apikey (free, không cần thẻ)
- **Credentials đã setup trong [.env](.env)** (gitignored):
  ```
  GOOGLE_API_KEY=<redacted — xem .env>
  GEMINI_MODEL=gemini-flash-latest
  GEMINI_ENDPOINT=https://generativelanguage.googleapis.com/v1beta/models
  ```
- Quota: 500 RPD — đủ cho 5 full ablation/ngày
- Test key: `curl "$GEMINI_ENDPOINT/$GEMINI_MODEL:generateContent" -H "X-goog-api-key: $GOOGLE_API_KEY" -H 'Content-Type: application/json' -X POST -d '{"contents":[{"parts":[{"text":"ping"}]}]}'`

**Fallback chain:** `gemini → openrouter (existing key) → ollama (local)`

**Security note:** API key lưu trong [.env](.env) (đã có trong [.gitignore](.gitignore)). Code load qua `os.getenv("GOOGLE_API_KEY")`, **không bao giờ hardcode key vào source hay docs commit vào git**.

### 6.2 2 judges

**J1 — FaithfulnessJudge** (RAGAS-style)
- Input: full narrative + RAG context + findings
- Method: Claim decomposition → NLI verdict
- Output JSON: `{ claims: [{text, verdict}], overall_score }`
- Score = supported_claims / total_claims

**J2 — ActionabilityJudge** (G-Eval Likert)
- Input: recommendations section + RAG `recommended_practices`
- Method: 1–5 Likert với Chain-of-Thought
- Output JSON: `{ likert: int, reasoning: str }`
- Rubric: 5=có step cụ thể/command, 1=vague platitude

### 6.3 Sampling

- **2 samples per judge per report** (Gemini variance thấp, 2 đủ)
- `temperature=0.3`, `seed` pinned
- Mean của 2 samples

### 6.4 Total calls

```
24 cases × 2 conditions × 2 judges × 2 samples = 192 LLM calls
```

### 6.5 Caching & reproducibility

- Cache response theo `hash(prompt + model + seed)` → re-run free
- Pin model version: `gemini-2.5-flash-preview-05-20`
- Log `{model, temp, seed, prompt_hash}` vào `judge_results.json`

---

## 7. Chi phí & runtime

```
Bước                              Số lượng      Runtime
──────────────────────────────────────────────────────────
Report generation (Ollama local)  48 × ~30s     ~24 phút
Deterministic metrics             48 × ~2s      ~2 phút
LLM judge (Gemini)                192 × ~3s     ~10 phút
──────────────────────────────────────────────────────────
TOTAL full ablation run                         ~36 phút

Cost:                                           $0 (hoàn toàn free tier)
```

Sau khi cache ấm, re-run deterministic only: **~26 phút** (skip LLM calls).

---

## 8. File inventory

### 8.1 Files NEW (cần viết)

| File | Mục đích | LOC estimate |
|------|----------|--------------|
| `benchmarks/llm_generation/benchmark_report_cases_v3.json` | 24 cases | ~1500 lines JSON |
| `benchmarks/llm_generation/report_metrics_v3.py` | 7 deterministic metrics | ~400 |
| `benchmarks/llm_generation/ranking_metrics.py` | NDCG@5 + helpers | ~100 |
| `benchmarks/llm_generation/report_judges.py` | 2 LLM judges + provider abstraction | ~350 |
| `benchmarks/llm_generation/ablation_runner.py` | no_rag / with_rag_v2 orchestrator | ~200 |
| `benchmarks/llm_generation/run_report_benchmark_v3.py` | Main entry, CLI | ~250 |
| `benchmarks/llm_generation/release_criteria_report_v3.json` | 9 thresholds | ~30 |
| `benchmarks/llm_generation/fixtures/case_generator.py` | Sinh 17 cases mới từ template | ~300 |

### 8.2 Files REUSE (import, không sửa)

- `pdca/agents/report_module/validators.py` → `ReportValidator`, `build_evidence`
- `pdca/agents/report_module/scope_detector.py` → `detect_scope`
- `pdca/agents/report_agent.py` → inference entry
- `benchmarks/llm_generation/benchmark_report.py` → inference pipeline wrapper

### 8.3 Files KEEP (deprecated, giữ cho comparison)

- `benchmarks/llm_generation/benchmark_report_cases.json` (v1)
- `benchmarks/llm_generation/report_metrics.py` (v1)
- `benchmarks/llm_generation/release_criteria_report.json` (v1)

### 8.4 Output artifacts

- `benchmarks/llm_generation/benchmark_outputs/report_v3_ablation_<timestamp>.json`
- `benchmarks/llm_generation/benchmark_outputs/report_v3_latest.json`
- `benchmarks/llm_generation/benchmark_outputs/judge_cache/` (response cache)
- `benchmarks/llm_generation/Report_Agent_Evaluation_Report_v3.md` (writeup LVTN)

---

## 9. Implementation plan — 2 ngày

### Day 1 — Deterministic core

**Morning (4h):**
1. `fixtures/case_generator.py` — template cho 17 cases mới
2. Sinh `benchmark_report_cases_v3.json` (24 cases)
3. Port 7 baselines từ `tests/fixtures/report_baseline/input/`
4. Validate schema, spot-check 3 cases

**Afternoon (4h):**
1. `ranking_metrics.py` — NDCG@5, severity rank extraction từ HTML
2. `report_metrics_v3.py` — 7 deterministic metrics (import validator)
3. `run_report_benchmark_v3.py` — CLI, mode=deterministic-only
4. Chạy deterministic pass → verify metrics sensible
5. `release_criteria_report_v3.json`

**Gate Day 1:** Chạy được `python run_report_benchmark_v3.py --mode deterministic` trên 24 cases, ra 7 metrics.

### Day 2 — LLM-Judge + Ablation

**Morning (4h):**
1. `report_judges.py` — provider abstraction (Gemini/Groq/Ollama)
2. `FaithfulnessJudge` + `ActionabilityJudge` với CoT prompting
3. Judge response caching (hash-based)
4. Spot-test 3 cases → verify JSON parse + score reasonable

**Afternoon (4h):**
1. `ablation_runner.py` — no_rag vs with_rag_v2 wrapper
2. Chạy full 48-run ablation
3. Aggregate results → `report_v3_latest.json`
4. Generate comparison tables → `Report_Agent_Evaluation_Report_v3.md`

**Gate Day 2:** Full 192-call LLM judge pass, ablation table có Δ theo dự đoán.

---

## 10. Deliverables cho LVTN

### 10.1 Tables (cho chương Results)

**Table 1 — Main results** (headline):
```
Metric                        Target   v2 Actual   PASS?
structure_pass_rate          ≥ 1.00    TBD        TBD
off_scope_mention_rate       ≤ 0.02    TBD        TBD
scope_accuracy               ≥ 1.00    TBD        TBD
numerical_faithfulness       ≥ 0.90    TBD        TBD
capability_grounding_rate    ≥ 0.85    TBD        TBD
claim_support_rate           ≥ 0.85    TBD        TBD
template_data_accuracy       ≥ 1.00    TBD        TBD
ndcg_at_5_severity           ≥ 0.85    TBD        TBD
actionability_likert         ≥ 3.5     TBD        TBD
```

**Table 2 — Capability group breakdown:**
```
Group                    N    Scope    Faithful    Ranking    Quality
C1 Scope Detection       5    TBD      TBD         —          —
C2 Hallucination         5    —        TBD         —          TBD
C3 Prioritization        4    —        —           TBD        —
C4 Structural            5    TBD      —           —          —
C5 RAG Grounding         5    —        TBD         —          TBD
```

**Table 3 — Ablation:**
```
Metric                        no_rag   with_rag_v2   Δ        Insight
capability_grounding_rate     TBD      TBD           TBD      RAG-only ★
claim_support_rate            TBD      TBD           TBD      RAG ground ★
actionability_likert          TBD      TBD           TBD      RAG remediation ★
numerical_faithfulness        TBD      TBD           TBD      Context numbers
scope_accuracy                TBD      TBD           0        Độc lập RAG
structure_pass_rate           TBD      TBD           0        Độc lập RAG
```

### 10.2 Charts

- **Radar 5 trục** — so sánh v1 baseline vs v2 (normalized 0-1)
- **Bar chart Ablation** — 9 metrics × {no_rag, with_rag_v2} (highlight Δ)

### 10.3 Chapter structure

```
4.x Report Agent Evaluation
  4.x.1 Framework — 5 trục, 9 metrics (1 bảng)
  4.x.2 Dataset — 24 cases, 5 nhóm theo capability (1 bảng)
  4.x.3 Methodology — LLM-Judge + caching + reproducibility
  4.x.4 Results
    4.x.4.1 Scope Detection                 (C1)
    4.x.4.2 Hallucination Resistance        (C2)
    4.x.4.3 Severity Prioritization         (C3)
    4.x.4.4 Structural Robustness           (C4)
    4.x.4.5 RAG Grounding Quality           (C5)
  4.x.5 Ablation Study — RAG Contribution ★
  4.x.6 Discussion — limitations, threats to validity
```

---

## 11. Success criteria

### 11.1 Framework success (meta-criteria)

- ✅ 9 metrics chạy được, reproducible
- ✅ Ablation có signal (Δ ≠ 0 ở metric mong đợi)
- ✅ LLM-Judge agreement cao giữa 2 samples (σ ≤ 0.1 cho Likert, ≤ 0.05 cho faithfulness)
- ✅ Runtime ≤ 40 phút per full ablation
- ✅ Cost = $0

### 11.2 Agent success (release criteria)

5 HARD metrics ≥ threshold:
- `structure_pass_rate ≥ 1.00`
- `off_scope_mention_rate ≤ 0.02`
- `scope_accuracy ≥ 1.00`
- `numerical_faithfulness ≥ 0.90`
- `template_data_accuracy ≥ 1.00`

4 SOFT metrics: report actual, discussion nếu dưới threshold.

---

## 12. Risks & mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Gemini free tier quota exceed | Low | Med | Fallback chain groq→ollama; cache responses |
| 17 cases sinh synthetic không realistic | Med | Med | Base trên Prowler check catalog thật; spot-check 5 cases |
| NDCG ground truth severity bias | Med | Low | Document methodology; severity-based là proxy, không perfect |
| LLM-Judge variance cao | Low | Med | 2 samples + pinned seed; report σ cạnh mean |
| `ReportValidator` evidence schema thay đổi | Low | High | Pin import path; schema diff check Day 1 morning |
| Inference local Ollama chậm/fail | Med | Med | Report generation tách biệt với eval; retry logic |

---

## 13. Open questions (giải quyết trong implementation)

1. NDCG ground truth — generate tự động từ severity hay hand-label? → **Tự động từ severity rank + document methodology**
2. Adversarial cases (C5 noise injection) — sinh synthetic hay lấy từ real RAG mis-retrieval? → **Synthetic, inject 3 off-topic capabilities**
3. Cases C3 `findings_100plus_top5` — data volume có làm timeout inference không? → **Test Day 1, giảm xuống 50 nếu cần**
4. Cache key cho judge — include full prompt hay hash prefix? → **Full prompt hash (SHA256) để đảm bảo correctness**

---

## 14. Confirmations đã chốt

| # | Decision | Value |
|---|----------|-------|
| 1 | Cases count | **24** |
| 2 | Capability groups | **5 (C1-C5)** |
| 3 | Metrics count | **9** (5 HARD + 4 SOFT) |
| 4 | Trục count | **5** (Scope/Structure/Faithfulness/Correctness/Quality) |
| 5 | Ablation conditions | **2** (no_rag, with_rag_v2) |
| 6 | LLM-Judge count | **2** (Faithfulness, Actionability) |
| 7 | Judge samples | **2** |
| 8 | LLM provider | **Gemini 2.5 Flash** (fallback: Groq, Ollama) |
| 9 | Human calibration | **Skip** |
| 10 | Total runtime target | **≤ 36 phút** |
| 11 | Total cost | **$0** |
| 12 | Implementation timeline | **2 ngày** |

---

**End of Plan v3 — Ready to implement.**
