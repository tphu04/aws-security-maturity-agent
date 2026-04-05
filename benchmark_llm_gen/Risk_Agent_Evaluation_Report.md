# Bao cao Evaluation — Risk Evaluation Agent

**Ngay chot**: 2026-04-04
**Model**: llama3.2:latest (3.2B, Q4_K_M)
**Ky thuat**: Two-Pass RAG Integration (v3)
**Faithfulness**: Claim-based LLM-as-Judge (theo RAGAS framework)
**Ket qua**: 83.3% accuracy, QWK 0.941, Faithfulness 0.950, 6/6 release criteria PASS

---

## 1. Tong quan

### 1.1 Muc tieu

Danh gia chat luong output cua Risk Evaluation Agent — module chiu trach nhiem
phan loai muc do nghiem trong (severity) cua cac lo hong bao mat AWS duoc phat
hien boi Prowler scanner.

Agent nhan dau vao la finding tu Prowler, ket hop voi RAG context tu Knowledge Base,
va tra ve:
- `ai_severity`: Critical | High | Medium | Low
- `ai_risk_score`: 0-10
- `ai_reasoning`: Giai thich ngan gon

### 1.2 Cau hinh duoc chon

| Thong so | Gia tri |
|----------|---------|
| Model | llama3.2:latest (3.2B params, Q4_K_M quantization) |
| RAG | Enabled (Two-Pass integration) |
| Temperature | 0 (deterministic) |
| Output format | JSON (Ollama format="json") |
| Inference | Ollama local, RTX 3060 Laptop 6GB |

### 1.3 Ky thuat Two-Pass

Thay vi gui finding + RAG context dong thoi (Single-Pass), Two-Pass tach thanh 2 buoc:

```
Pass 1: [Finding ONLY] ──> LLM ──> Draft severity
                                      |
Pass 2: [Draft + RAG official_severity] ──> LLM ──> Final severity
```

**Ly do**: Single-Pass gay anchoring bias — model 3B khong xu ly duoc
xung dot giua `finding.severity` va `rag_context.official_severity`,
mac dinh tang len Critical. Two-Pass cho phep model hinh thanh judgment
rieng truoc khi tham khao RAG.

---

## 2. Benchmark Dataset

### 2.1 Thong so

| Thong so | Gia tri |
|----------|---------|
| Tong so test cases | 30 |
| File | `benchmark_llm_gen/benchmark_gen_cases.json` |
| AWS services | 6 (S3, IAM, EC2, RDS, CloudTrail, KMS) |
| Severity levels | 4 (Critical, High, Medium, Low) |
| Query categories | 4 (exact, paraphrase, semantic_hard, risk) |

### 2.2 Phan bo

**Theo category:**

| Category | So luong | Mo ta |
|----------|:-------:|-------|
| exact | 8 | Finding description gan giong knowledge base |
| paraphrase | 8 | Finding duoc viet lai (paraphrase) |
| semantic_hard | 7 | Finding mo ta khac nhung cung van de |
| risk | 7 | Finding mo ho, can suy luan sau |

**Theo expected severity:**

| Severity | So luong | Ti le |
|----------|:-------:|:-----:|
| Critical | 14 | 47% |
| High | 4 | 13% |
| Medium | 6 | 20% |
| Low | 6 | 20% |

**Theo service:**

| Service | So luong |
|---------|:-------:|
| S3 | 8 |
| IAM | 7 |
| EC2 | 5 |
| RDS | 4 |
| CloudTrail | 3 |
| KMS | 3 |

### 2.3 Cau truc 1 test case

```json
{
  "case_id": "risk_s3_exact_001",
  "category": "exact",
  "service": "s3",
  "input": {
    "finding": {
      "status": "FAIL",
      "event_code": "s3_bucket_level_public_access_block",
      "service": "s3",
      "resource_id": "arn:aws:s3:::my-public-bucket",
      "region": "us-east-1",
      "description": "S3 Bucket Level Public Access Block is not configured...",
      "severity": "high"
    }
  },
  "rag_context_snapshot": {
    "confidence": "medium",
    "official_severity": "medium",
    "check_title": "Check S3 Bucket Level Public Access Block.",
    "compliance_mappings": ["block_public_access"]
  },
  "expected": {
    "ai_severity": "Medium",
    "required_evidence": ["public access hoac truy cap cong khai", "CIS hoac compliance"]
  }
}
```

---

## 3. Prompts

### 3.1 SYSTEM_PROMPT_PASS1 (Pass 1 — Finding only)

```
Ban la Chuyen gia An ninh mang AWS (Senior AWS Security Analyst).
Nhiem vu: Danh gia rui ro dua tren thong tin lo hong bao mat.

HUONG DAN CHAM DIEM (SCORING RUBRIC):
1. CRITICAL (Score 9-10): Public Access vao du lieu nhay cam, chiem quyen Admin, mat du lieu.
2. HIGH (Score 7-8): Cau hinh sai nghiem trong, thieu ma hoa, dich vu phoi bay ra internet.
3. MEDIUM (Score 4-6): Thieu Logging/Monitoring, thieu MFA, vi pham Compliance khong nguy hiem tuc thi.
4. LOW (Score 1-3): Loi thong tin, thieu Tagging.

YEU CAU OUTPUT JSON:
{
    "ai_severity": "Critical" | "High" | "Medium" | "Low",
    "ai_risk_score": <int 0-10>,
    "ai_reasoning": "<Giai thich ngan gon 1-2 cau>"
}
```

**Input cho Pass 1** (khong co RAG):
```json
{
  "check_id": "s3_bucket_level_public_access_block",
  "service": "s3",
  "resource_id": "arn:aws:s3:::my-public-bucket",
  "region": "us-east-1",
  "description": "S3 Bucket Level Public Access Block is not configured...",
  "original_severity": "high",
  "remediation_text": "..."
}
```

### 3.2 SYSTEM_PROMPT_PASS2 (Pass 2 — RAG adjustment)

```
Ban la Chuyen gia An ninh mang AWS (Senior AWS Security Analyst).

Ban vua danh gia so bo mot lo hong voi ket qua "draft_severity", "draft_score", "draft_reasoning".
Bay gio hay doi chieu voi thong tin chinh thuc tu Prowler Knowledge Base:
- "rag_official_severity": Muc severity chinh thuc tu AWS/Prowler.
- "rag_check_title": Ten chinh thuc cua security check.

QUY TAC DIEU CHINH:
1. Neu draft_severity TRUNG voi rag_official_severity -> giu nguyen.
2. Neu draft_severity CAO HON rag_official_severity -> ha xuong theo rag neu mo ta
   lo hong khong cho thay muc nguy hiem vuot muc official.
3. Neu draft_severity THAP HON rag_official_severity -> tang len theo rag neu mo ta
   lo hong phu hop voi muc official.
4. Luon uu tien bang chung tu mo ta lo hong hon la chi dua vao nhan severity.

YEU CAU OUTPUT JSON:
{
    "ai_severity": "Critical" | "High" | "Medium" | "Low",
    "ai_risk_score": <int 0-10>,
    "ai_reasoning": "<Dua tren draft_reasoning, giu lai mo ta lo hong va bang chung ky thuat.
                      Them ghi chu neu co dieu chinh severity so voi draft.>"
}
```

**Input cho Pass 2** (co draft + RAG):
```json
{
  "check_id": "s3_bucket_level_public_access_block",
  "description": "S3 Bucket Level Public Access Block is not configured...",
  "draft_severity": "High",
  "draft_score": 8,
  "draft_reasoning": "S3 Bucket khong duoc cau hinh Public Access Block...",
  "rag_official_severity": "medium",
  "rag_check_title": "Check S3 Bucket Level Public Access Block."
}
```

### 3.3 Logic dieu kien

- Neu **khong co RAG client** → chi chay Pass 1 (single-pass)
- Neu **RAG data khong co severity** → chi chay Pass 1
- Neu **Pass 2 parse fail** → fallback giu ket qua Pass 1
- Neu **Pass 2 severity = Pass 1 severity** → giu reasoning cua Pass 1 (smart reasoning)

---

## 4. Metrics Evaluation

### 4.1 Tong quan 4 truc danh gia

| Truc | Do gi | Cach tinh | Chi phi |
|------|-------|-----------|---------|
| **Structure** | Output co dung format | Deterministic rules | 0 (khong can LLM) |
| **Faithfulness** | Output co dua tren context khong | Claim-based + LLM-as-Judge | Co (1 LLM call/claim) |
| **Correctness** | Severity co dung khong | Accuracy + QWK (sklearn) | 0 |
| **Completeness** | Reasoning co du evidence khong | Keyword matching | 0 |

### 4.2 Structure (Structured Output Compliance)

- `json_parseable`: Output parse duoc JSON
- `schema_valid`: Co du 3 fields (severity, risk_score, reasoning)
- `severity_valid`: severity thuoc {Critical, High, Medium, Low}
- `score_valid`: risk_score la int 0-10
- `severity_score_consistent`: severity khop voi score range
  - Critical: 9-10, High: 7-8, Medium: 4-6, Low: 1-3

**Aggregate**: json_parse_rate, schema_compliance_rate, internal_consistency_rate

### 4.3 Faithfulness (Claim-based, LLM-as-Judge)

Theo framework RAGAS (Es et al. 2023), faithfulness do:
**"Bao nhieu phan tram noi dung trong reasoning co the xac minh duoc tu context?"**

#### Phuong phap: Claim Decomposition + Verification

**Buoc 1 — Claim Decomposition**: Tach reasoning thanh cac claims (cau don, >= 10 ky tu).

Vi du reasoning:
```
"S3 Bucket co public access la rui ro Critical vi du lieu nhay cam co the bi truy cap trai phep.
 Theo CIS Benchmark 1.3, day la vi pham muc do cao."
```
Phan tach thanh 2 claims:
1. "S3 Bucket co public access la rui ro Critical vi du lieu nhay cam co the bi truy cap trai phep"
2. "Theo CIS Benchmark 1.3, day la vi pham muc do cao"

**Buoc 2 — Build context**: Gop finding description + RAG snapshot thanh context string:
```
S3 Bucket Level Public Access Block is not configured for bucket my-public-bucket.
Check: s3_bucket_level_public_access_block. Prowler severity: high.
Official severity: medium. Check title: Check S3 Bucket Level Public Access Block.
Compliance: block_public_access.
```

**Buoc 3 — Verification (LLM-as-Judge)**: Voi moi claim, hoi LLM judge:
```
You are a fact-checker for AWS security findings.

CONTEXT (ground truth):
{context}

CLAIM to verify:
"{claim}"

Rules:
- "supported": claim restates, paraphrases, or logically follows from CONTEXT.
  Translation between Vietnamese and English counts as paraphrase.
- "not_supported": claim introduces specific facts NOT in CONTEXT
  (dates, dollar amounts, report names, breach events, statistics).

Answer ONLY: {"verdict": "supported"} or {"verdict": "not_supported"}
```

**Buoc 4 — Scoring**:
```
Faithfulness = (So claim Supported) / (Tong so claims)
```

#### Vi du danh gia

**Output faithful (score = 1.0):**
```
"S3 Bucket khong cau hinh Public Access Block, cho phep truy cap cong khai."
```
| Claim | Verdict | Ly do |
|-------|---------|-------|
| "S3 Bucket khong cau hinh Public Access Block, cho phep truy cap cong khai" | Supported | Paraphrase cua finding description |

**Output co hallucination (score = 0.5):**
```
"Lo hong nay da gay ra vu data breach nam 2023 khien mat 5 trieu USD.
 Theo Gartner, day la van de pho bien."
```
| Claim | Verdict | Ly do |
|-------|---------|-------|
| "Data breach nam 2023 khien mat 5 trieu USD" | Not Supported | Ngay, so tien khong co trong context |
| "Theo Gartner, day la van de pho bien" | Supported | Judge danh gia la nhan dinh chung hop ly (*) |

(*) LLM 3B judge con han che: khong phan biet duoc trích dan nguon bia (Gartner) vs nhan dinh chung.

#### Tai sao dung LLM-as-Judge thay vi rule-based?

| | Rule-based (phien ban cu) | Claim-based LLM-as-Judge (hien tai) |
|---|---|---|
| Phuong phap | Detect contradiction patterns + hallucination regex | Claim decomposition + LLM verification |
| Do gi | "Co dau hieu mau thuan ro rang khong?" | "Tung claim co xac minh duoc tu context khong?" |
| Bo sot | Subtle hallucination: claim hop ly nhung khong co trong context | LLM 3B co the miss trích dan nguon bia |
| Ket qua | 0.983 (qua lac quan) | **0.950** (thuc te hon) |
| Chi phi | 0 | ~3 phut them cho 30 cases (1 LLM call/claim) |
| Theo framework | Phien ban rut gon | **Dung tinh than RAGAS** |

#### Fallback

Khi Ollama khong available (vd CI/CD environment), tu dong fallback ve rule-based heuristic.

### 4.4 Correctness (Severity Accuracy)

**Severity Accuracy**: % so case predicted severity = expected severity

**Quadratic Weighted Kappa (QWK)**:
- Do muc dong thuan co trong so cho severity ordinal (Low < Medium < High < Critical)
- Phat case sai xa (vd Critical→Low) nang hon case sai gan (Critical→High)
- QWK = 1.0: hoan hao, 0.8+: tot, 0.6-0.8: kha

### 4.5 Completeness (Evidence Coverage)

Moi test case co `required_evidence` — danh sach keywords can co trong reasoning.
- Ho tro alternatives: "encryption hoac ma hoa" → match neu co 1 trong 2
- Normalized: lowercase + bo dau tieng Viet truoc matching

**Scoring**: evidence_found / total_required. Aggregate: mean

---

## 5. Release Criteria

### 5.1 Nguong

| Criterion | Nguong | Mo ta |
|-----------|:------:|-------|
| json_parse_rate_min | 100% | Moi output phai parse duoc JSON |
| schema_compliance_rate_min | 95% | >= 95% output co du 3 fields |
| faithfulness_mean_min | 80% | Trung binh faithfulness >= 0.80 |
| severity_accuracy_min | 50% | >= 50% severity dung |
| severity_qwk_min | 0.45 | QWK >= 0.45 (moderate agreement) |
| evidence_completeness_mean_min | 45% | Trung binh evidence coverage >= 45% |

**Verdict**: PASS khi tat ca 6 criteria deu dat. FAIL neu bat ky 1 cai nao khong dat.

### 5.2 File cau hinh

`benchmark_llm_gen/release_criteria_gen.json`

---

## 6. Ket qua cuoi cung

### 6.1 Metrics tong hop (llama3.2 Two-Pass v3 w/RAG, 30 cases)

| Metric | Gia tri | Nguong | Margin | Verdict |
|--------|:-------:|:------:|:------:|:-------:|
| JSON Parse Rate | **100%** | 100% | +0pp | PASS |
| Schema Compliance | **100%** | 95% | +5pp | PASS |
| Internal Consistency | **96.7%** | — | — | — |
| Faithfulness Mean (claim-based) | **0.950** | 0.80 | +0.150 | PASS |
| Severity Accuracy | **83.3%** | 50% | +33.3pp | PASS |
| Severity QWK | **0.941** | 0.45 | +0.491 | PASS |
| Evidence Completeness | **82.2%** | 45% | +37.2pp | PASS |
| **Overall Verdict** | | | | **PASS** |

### 6.2 Faithfulness chi tiet (claim-based)

27/30 cases dat faithfulness = 1.0 (moi claim trong reasoning deu xac minh duoc tu context).
3 cases co faithfulness < 1.0:

| Case | Score | Claims | Van de |
|------|:-----:|:------:|--------|
| risk_s3_exact_001 | 0.50 | 1/2 supported | Pass 2 reasoning chua meta-statement ("Dua tren draft_reasoning...") — prompt template leak |
| risk_cloudtrail_paraphrase_001 | 0.33 | 1/3 supported | Reasoning ghi chu quy trinh dieu chinh ("dieu chinh xuong Low") — meta-reasoning khong nam trong finding context |
| risk_rds_risk_001 | 0.67 | 2/3 supported | Claim so sanh "thap hon muc official" — tham chieu quy trinh Two-Pass, khong phai thong tin lo hong |

**Nhan xet**: Ca 3 cases co faithfulness thap deu do **meta-reasoning** (reasoning noi ve quy trinh dieu chinh
thay vi noi ve lo hong). Day la tac dung phu cua Two-Pass — khi Pass 2 thay doi severity, reasoning co xu huong
giai thich ly do dieu chinh thay vi mo ta lo hong. Khong phai hallucination truyen thong (bia thong tin)
nhung van la grounding issue theo dinh nghia RAGAS.

### 6.3 Accuracy theo category

| Category | n | Accuracy | Faithfulness (claim) | Completeness |
|----------|:-:|:--------:|:--------------------:|:------------:|
| exact | 8 | **87.5%** | 0.94 | 70.8% |
| paraphrase | 8 | **87.5%** | 0.92 | 93.8% |
| semantic_hard | 7 | 71.4% | 1.00 | 78.6% |
| risk | 7 | **85.7%** | 0.95 | 85.7% |

### 6.3 Accuracy theo service

| Service | n | Accuracy |
|---------|:-:|:--------:|
| S3 | 8 | **100%** |
| IAM | 8 | 75.0% |
| EC2 | 5 | 60.0% |
| RDS | 4 | **100%** |
| CloudTrail | 3 | 66.7% |
| KMS | 2 | **100%** |

### 6.4 Phan bo severity predictions

| Severity | Expected | Predicted | Nhan xet |
|----------|:--------:|:---------:|----------|
| Critical | 14 | 10 | Under-predict 4 (bi ha thanh High) |
| High | 4 | 8 | Over-predict 4 (tu Critical bi ha) |
| Medium | 6 | 5 | Gan dung |
| Low | 6 | 7 | Gan dung |

### 6.5 Per-case results

| Case ID | Expected | Predicted | Result |
|---------|:--------:|:---------:|:------:|
| risk_s3_exact_001 | Medium | Medium | OK |
| risk_s3_exact_002 | Medium | Medium | OK |
| risk_iam_exact_001 | Critical | Critical | OK |
| risk_ec2_exact_001 | Critical | High | MISS |
| risk_rds_exact_001 | Critical | Critical | OK |
| risk_cloudtrail_exact_001 | Medium | Medium | OK |
| risk_kms_exact_001 | Medium | Medium | OK |
| risk_iam_exact_002 | Critical | Critical | OK |
| risk_s3_paraphrase_001 | Critical | Critical | OK |
| risk_s3_paraphrase_002 | Medium | Medium | OK |
| risk_iam_paraphrase_001 | High | High | OK |
| risk_ec2_paraphrase_001 | High | High | OK |
| risk_rds_paraphrase_001 | High | High | OK |
| risk_cloudtrail_paraphrase_001 | Medium | Low | MISS |
| risk_s3_paraphrase_003 | Low | Low | OK |
| risk_iam_paraphrase_002 | Low | Low | OK |
| risk_s3_semantic_hard_001 | Critical | Critical | OK |
| risk_iam_semantic_hard_001 | Critical | High | MISS |
| risk_ec2_semantic_hard_001 | Critical | High | MISS |
| risk_rds_semantic_hard_001 | Critical | Critical | OK |
| risk_ec2_semantic_hard_002 | Critical | Critical | OK |
| risk_iam_semantic_hard_002 | Low | Low | OK |
| risk_kms_semantic_hard_001 | Critical | Critical | OK |
| risk_s3_risk_001 | Critical | Critical | OK |
| risk_iam_risk_001 | Critical | High | MISS |
| risk_ec2_risk_001 | Critical | Critical | OK |
| risk_cloudtrail_risk_001 | Low | Low | OK |
| risk_rds_risk_001 | High | High | OK |
| risk_iam_risk_002 | Low | Low | OK |
| risk_s3_risk_002 | Low | Low | OK |

**25/30 dung (83.3%). 5 case sai deu la adjacent error (chenh 1 bac).**

---

## 7. So sanh cac cau hinh

### 7.1 Toan bo configs da test

| Config | Accuracy | QWK | Consistency | Faith | Complete | Verdict |
|--------|:--------:|:---:|:-----------:|:-----:|:--------:|:-------:|
| llama3.2 SP no-RAG | 76.7% | 0.916 | 96.7% | 0.967 | 92.8% | PASS |
| llama3.2 SP w/RAG | 66.7% | 0.684 | 86.7% | 0.933 | 78.3% | PASS |
| llama3.2 TP-v0 w/RAG | 70.0% | 0.852 | 96.7% | 0.967 | 76.7% | PASS |
| llama3.2 TP-v1 w/RAG | 76.7% | 0.854 | 86.7% | 0.917 | 38.9% | FAIL |
| llama3.2 TP-v2 w/RAG | 80.0% | 0.939 | 93.3% | 0.933 | 60.6% | PASS |
| **llama3.2 TP-v3 w/RAG** | **83.3%** | **0.941** | **96.7%** | **0.950** | **82.2%** | **PASS** |
| qwen3:8b SP no-RAG | 50.0% | 0.761 | 100% | 0.983 | 93.3% | PASS |
| qwen3:8b SP w/RAG | 56.7% | 0.760 | 100% | 0.967 | 90.6% | PASS |

SP = Single-Pass, TP = Two-Pass.
Faith cot: v0-v2 dung rule-based heuristic, TP-v3 dung claim-based LLM-as-Judge (nghiem ngat hon → score thap hon).

### 7.2 RAG Lift qua cac iteration

| Version | Accuracy Lift | QWK Lift | Cai tien chinh |
|---------|:------------:|:--------:|----------------|
| Single-Pass | **-10.0pp** | -0.232 | Van de goc: RAG lam giam accuracy |
| TP-v0 | 0.0pp | 0.000 | Loai bo negative lift |
| TP-v1 | +3.3pp | -0.043 | Fix bug primary_finding, RAG bat dau giup |
| TP-v2 | +6.7pp | +0.041 | Fix PASS2 prompt |
| **TP-v3** | **+10.0pp** | **+0.043** | Fix parse error + smart reasoning |

### 7.3 So sanh llama3.2 vs qwen3:8b

| Metric | llama3.2 TP-v3 | qwen3:8b SP-wRAG | Chenh lech |
|--------|:-:|:-:|:-:|
| Accuracy | **83.3%** | 56.7% | +26.6pp |
| QWK | **0.941** | 0.760 | +0.181 |
| RAG Lift | **+10.0pp** | +6.7pp | +3.3pp |
| Faithfulness (claim-based) | **0.950** | 0.967* | -0.017 |
| Completeness | 82.2% | **90.6%** | -8.4pp |
| Consistency | 96.7% | **100%** | -3.3pp |
| Latency/case | **~11s** | ~49s | 4.5x nhanh hon |
| Model size | **3.2B** | 8.2B | 2.6x nho hon |

(*) qwen3:8b faithfulness do bang rule-based (chua chay lai voi claim-based).

---

## 8. Phan tich loi

### 8.1 5 cases sai

| Case | Expected | Got | Lech | Phan tich |
|------|:--------:|:---:|:----:|-----------|
| risk_ec2_exact_001 | Critical | High | -1 | EC2 security group rule, RAG ha severity |
| risk_cloudtrail_paraphrase_001 | Medium | Low | -1 | CloudTrail monitoring, model danh gia qua nhe |
| risk_iam_semantic_hard_001 | Critical | High | -1 | IAM inline policy admin, finding mo ho |
| risk_ec2_semantic_hard_001 | Critical | High | -1 | EC2 SSH 0.0.0.0, model khong nhan dien Critical |
| risk_iam_risk_001 | Critical | High | -1 | IAM cross-account trust, case ambiguous |

**Dac diem chung**:
- 5/5 deu la **adjacent error** (chenh dung 1 bac), khong co case sai xa
- 4/5 la Critical→High (model co xu huong ha Critical thanh High o IAM/EC2)
- 3/5 thuoc category semantic_hard hoac risk (cases kho nhat)

### 8.2 Bias pattern

- **Under-predict Critical**: 10/14 dung (71.4%). 4 case bi ha thanh High
- **High accuracy cao**: 4/4 dung (100%) — khi expected la High, model predict chinh xac
- **Medium/Low tot**: 11/12 dung (91.7%) — chi sai 1 case Medium→Low

---

## 9. Kien truc ky thuat

### 9.1 Pipeline tong the

```
Prowler Scanner
    |
    v
[Normalized Findings] ──> RiskEvaluationAgent.run()
    |                         |
    |                    [1] Filter FAIL findings
    |                    [2] Fetch RAG context (batch, cached)
    |                    [3] For each finding:
    |                         |
    |                    Pass 1: LLM(finding) → draft severity
    |                         |
    |                    Pass 2: LLM(draft + RAG) → final severity
    |                         |    (skip neu khong co RAG data)
    |                         |    (fallback neu parse fail)
    |                         |    (giu reasoning Pass 1 neu severity khong doi)
    |                         |
    |                    [4] Validate output (whitelist 3 fields)
    |                    [5] Sort by priority
    |
    v
[Prioritized Findings with AI severity + reasoning]
```

### 9.2 Files lien quan

| File | Vai tro |
|------|---------|
| `agents/risk_evaluation_agent.py` | Agent chinh — Two-Pass logic, prompts, validation |
| `agents/shared/rag_client.py` | Client goi RAG API |
| `agents/shared/utils.py` | extract_check_id, parse_llm_json |
| `config.py` | OLLAMA_MODEL, OLLAMA_BASE_URL, RAG_API_URL |
| `benchmark_llm_gen/benchmark_generation.py` | Benchmark engine (Load→Inference→Evaluate→Aggregate) |
| `benchmark_llm_gen/run_gen_benchmark.py` | CLI entry point |
| `benchmark_llm_gen/gen_metrics.py` | 4 metrics implementation |
| `benchmark_llm_gen/benchmark_gen_cases.json` | 30 test cases |
| `benchmark_llm_gen/release_criteria_gen.json` | Nguong PASS/FAIL |
| `benchmark_llm_gen/RAG_LIFT_ANALYSIS.md` | Phan tich chi tiet qua trinh cai tien |

### 9.3 Cach chay benchmark

```bash
# Chay full benchmark voi RAG
OLLAMA_MODEL=llama3.2:latest python benchmark_llm_gen/run_gen_benchmark.py --mode full

# Chay khong RAG (ablation test)
OLLAMA_MODEL=llama3.2:latest python benchmark_llm_gen/run_gen_benchmark.py --mode full --no-rag

# Chi evaluate tu inference co san
python benchmark_llm_gen/run_gen_benchmark.py --mode evaluate-only \
  --inference-dir benchmark_llm_gen/inference_outputs/run_20260403_174524

# Tao dashboard so sanh
python benchmark_llm_gen/generate_gen_dashboard.py
```

Yeu cau:
- Ollama running (`ollama serve`) voi model llama3.2:latest
- RAG server running tai localhost:8001 (chi khi chay voi RAG)

---

## 10. Qua trinh cai tien (tom tat)

### 10.1 Van de ban dau

Single-Pass RAG lam **giam** accuracy 10pp (76.7% → 66.7%) do anchoring bias.
Model 3B khong xu ly duoc 4 signals mau thuan trong 1 prompt.

### 10.2 4 iterations

| Iteration | Thay doi chinh | Accuracy | RAG Lift |
|-----------|---------------|:--------:|:--------:|
| v0 | Two-Pass architecture | 70.0% | 0.0pp |
| v1 | Fix bug primary_finding + Active PASS2 | 76.7% | +3.3pp |
| v2 | Fix PASS2 output template | 80.0% | +6.7pp |
| **v3** | **Fallback + Smart reasoning** | **83.3%** | **+10.0pp** |

### 10.3 Kho khan chinh va cach giai quyet

| Kho khan | Cach giai quyet |
|----------|----------------|
| Anchoring bias (4 signals mau thuan) | Two-Pass: tach finding vs RAG |
| Pass 2 khong duoc goi (bug data pipeline) | Fix: doc `primary_finding` thay vi chi `related_findings` |
| Pass 2 qua conservative | Viet lai 4 rules can bang |
| Evidence bi mat khi Pass 2 viet lai reasoning | Smart reasoning: giu reasoning Pass 1 khi severity khong doi |
| Parse error crash (primary_finding=null) | `get() or {}` thay vi `get(, {})` |

Chi tiet day du: `benchmark_llm_gen/RAG_LIFT_ANALYSIS.md`

---

## 11. Han che

1. **Dataset skew**: 47% cases la Critical — accuracy co the bi inflate cho model thien Critical
2. **30 cases** khong du de tinh statistical significance (chi du cho directional evaluation)
3. **Evidence completeness 82.2%** thap hon SP-noRAG (92.8%) — trade-off cua Two-Pass
4. **Under-predict Critical** o IAM/EC2 — Pass 2 ha severity qua muc cho mot so case
5. **Latency x2** do 2 LLM calls (11s vs 6.5s/case) — chap nhan duoc cho batch processing
6. **Chua test tren nhieu model khac** — chi co llama3.2 va qwen3:8b
7. **Faithfulness LLM-as-Judge dung model 3B** — judge model nho co the miss mot so subtle hallucination
   (vd trích dan nguon bia). Framework khuyen nghi dung model lon hon (GPT-4) hoac MiniCheck de chinh xac hon

---

## 12. Ket luan

Risk Evaluation Agent voi **llama3.2 Two-Pass v3** dat:
- **83.3% severity accuracy** (25/30 cases dung)
- **QWK 0.941** (gan hoan hao, moi case sai chi chenh 1 bac)
- **Faithfulness 0.950** (claim-based LLM-as-Judge, dung tinh than RAGAS framework)
- **RAG Lift +10.0pp** (chung minh RAG cai thien chat luong)
- **6/6 release criteria PASS**

Day la cau hinh tot nhat trong tat ca configs da test (vuot SP-noRAG 76.7%,
vuot qwen3:8b 56.7%), dong thoi chung minh RAG thuc su dong gop tich cuc
cho viec danh gia severity.

Faithfulness duoc danh gia bang **claim-based verification** theo framework RAGAS,
thay vi rule-based heuristic ban dau. Ket qua 0.950 (thay vi 0.983 rule-based)
phan anh chinh xac hon chat luong grounding — 3 cases co meta-reasoning
(noi ve quy trinh dieu chinh thay vi mo ta lo hong) duoc phat hien dung.
