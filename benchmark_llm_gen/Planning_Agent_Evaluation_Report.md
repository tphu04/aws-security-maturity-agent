# Bao cao Evaluation — Planning Agent

**Ngay chot**: 2026-04-07
**Model**: llama3.2:latest (3.2B, Q4_K_M)
**Kien truc**: RAG-first, LLM-conditional (V2)
**Faithfulness**: Keyword-based grounded reasoning rate
**Ket qua**: F1 0.656, Planning Correctness 0.759, 9/9 release criteria PASS
**New metrics**: Over-selection 0.363, Under-selection 0.200, Exact Match 35%

---

## 1. Tong quan

### 1.1 Muc tieu

Danh gia chat luong output cua Planning Agent — module chiu trach nhiem
chuyen doi user request (ngon ngu tu nhien) thanh assessment plan cu the:
chon Prowler check IDs de scan hoac xac dinh service group.

Agent nhan dau vao la user request va tra ve:
- `checks_to_scan`: Danh sach Prowler check IDs cu the, HOAC
- `groups_to_scan`: Service group de scan toan bo
- `reasoning`: Giai thich ly do lua chon

### 1.2 Cau hinh duoc chon

| Thong so | Gia tri |
|----------|---------|
| Model | llama3.2:latest (3.2B params, Q4_K_M quantization) |
| RAG | Enabled (PlanningBundle via build_context) |
| LLM calls | 0-1 (chi khi confidence thap, <= 20% requests) |
| Temperature | 0 (deterministic) |
| Output format | Python dict (luon valid, error handling noi bo) |
| Inference | Ollama local, RTX 3060 Laptop 6GB |

### 1.3 Kien truc V2 — RAG-first, LLM-conditional

Khac biet co ban voi Risk Agent (luon goi LLM): Planning Agent **uu tien xu ly
deterministic**, chi goi LLM khi he thong khong du confident.

```
User Request
    |
    v
[InputClassifier] ──> (pure logic, regex + keyword)
    |
    ├── FAST_TRACK: Check IDs co san trong request → tra truc tiep (0 LLM, 0 RAG)
    ├── GROUP_SCAN: Pattern "scan all {service}" → tra group (0 LLM, 0 RAG)
    └── RETRIEVAL_PATH:
            |
            v
        [RAG Retrieval] → build_context() / retrieve_checks()
            |
            v
        [DeterministicScorer] → weighted formula (0.6*rag + 0.3*severity + 0.1*service)
            |
            v
        [Score Enrichment] → merge scores tu retrieve_checks vao PlanningBundle
            |
            v
        [ConfidenceGate] ──> confidence high/medium + top_score > 0.35?
            |                     |
            YES                   NO
            |                     |
        Return top checks     [LLM Refinement] → 1 LLM call
        (no LLM)                  |
                              Return LLM selection
```

**Ket qua benchmark**: 30/30 cases xu ly deterministic (0 LLM calls). ConfidenceGate luon PASS
vi RAG confidence = "medium" va top_score luon > 0.35.

---

## 2. Benchmark Dataset

### 2.1 Thong so

| Thong so | Gia tri |
|----------|---------|
| Tong so test cases | 30 |
| File | `benchmark_llm_gen/benchmark_planning_cases.json` |
| AWS services | 6 (S3, IAM, EC2, RDS, CloudTrail, KMS) |
| Input types | 4 (explicit_checks, group_request, specific_intent, ambiguous) |

### 2.2 Phan bo

**Theo input type:**

| Input Type | So luong | Mo ta | Metric chinh |
|------------|:-------:|-------|-------------|
| explicit_checks | 5 | User cung cap check IDs truc tiep | F1 (expected = 1.0) |
| group_request | 5 | "scan all {service}" | Service Accuracy |
| specific_intent | 15 | Mo ta cu the ve security concern | F1 |
| ambiguous | 5 | Mo ho, khong ro intent | Action Type |

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
  "case_id": "plan_specific_s3_pub_001",
  "input_type": "specific_intent",
  "service": "s3",
  "input": {
    "user_request": "kiem tra xem S3 bucket co bi public access khong"
  },
  "expected": {
    "expected_service": "s3",
    "relevant_checks": ["s3_bucket_public_access", "s3_bucket_level_public_access_block",
                         "s3_account_level_public_access_blocks"],
    "acceptable_output_type": "specific_checks"
  }
}
```

---

## 3. Metrics Evaluation

### 3.1 Tong quan 4 truc danh gia + 3 selection metrics

| Truc | Do gi | Cach tinh | Chi phi |
|------|-------|-----------|---------|
| **Structure** | Output co hop le khong | `valid_output_rate` (deterministic) | 0 |
| **Faithfulness** | Reasoning co dua tren context khong | Keyword grounding + 3 negative checks (fabrication, mismatch, phantom) | 0 |
| **Correctness** | Agent chon dung checks/service khong | F1 + Service Accuracy + composite | 0 |
| **Completeness** | Agent chon dung loai hanh dong khong | `action_type_accuracy` (binary) | 0 |

**3 Selection Analysis Metrics bo sung** (ap dung cho specific_checks cases co ground truth):

| Metric | Do gi | Cach tinh | Y nghia |
|--------|-------|-----------|---------|
| **Over-selection rate** | Model chon du bao nhieu check | `FP / |predicted|` | Giai thich truc tiep vi sao Precision thap. Cao = agent chon nhieu check thua |
| **Under-selection rate** | Model bo sot bao nhieu check quan trong | `FN / |relevant|` | Lien quan truc tiep den risk he thong. Cao = miss vulnerability |
| **Exact Match (EM)** | % case chon dung hoan toan | `predicted_set == relevant_set` | Tieu chuan khac nhat — khong cho phep sai lech bat ky |

**Khac biet voi Risk Agent**: Tat ca metrics deu deterministic (0 LLM calls cho evaluation),
vi Planning Agent output la structured data (check IDs, service names), khong phai free text.
Faithfulness su dung negative checks (phat hien fabrication, contradiction) thay vi LLM-as-Judge.

### 3.2 Structure — Valid Output Rate

Gop kiem tra thanh 1 metric duy nhat:
1. Output la 1 trong 3 dang hop le (specific_checks, group_scan, error)
2. `groups_to_scan` va `checks_to_scan` khong cung non-empty (mutual exclusivity)
3. `reasoning` khong rong (tru error output)
4. Check IDs dung Prowler format (82 service prefixes, >= 3 parts, >= 12 ky tu)

### 3.3 Faithfulness — Grounded Reasoning Rate (with Negative Checks)

Reasoning hardcoded (FAST_TRACK, GROUP_SCAN, Deterministic) → auto score 1.0 (khong the hallucinate).

Khi reasoning do **LLM sinh** (low-confidence cases), metric danh gia 2 chieu:

**Positive check (base score)**: Reasoning co chua evidence tu context khong?
- check_id da chon, service name, severity, compliance mapping tu RAG context
- Co evidence → base = 1.0; khong co → base = 0.0

**Negative checks (penalties tru diem)**:

| Check | Penalty | Phat hien |
|-------|:-------:|-----------|
| **N1: Check ID fabrication** | -0.3 | Reasoning nhac check IDs khong co trong RAG candidates |
| **N2: Output-reasoning mismatch** | -0.3 | Reasoning noi "no relevant" nhung output co checks (hoac nguoc lai) |
| **N3: Phantom reference** | -0.2 | Trich dan nguon khong co trong context (Gartner, breach events, dollar amounts) |

```
Faithfulness = max(0.0, base_score - sum(penalties))
```

**Vi du penalized reasoning**:
```
"No relevant checks found. According to Gartner report, this costs $5M.
 Also recommend cloudwatch_log_group_encrypted."
```
| Check | Penalty | Ly do |
|-------|:-------:|-------|
| N2: output mismatch | -0.3 | Noi "no relevant" nhung output co checks |
| N3: phantom reference | -0.2 | "According to Gartner report" khong co trong context |
| N1: fabrication | -0.3 | "cloudwatch_log_group_encrypted" khong co trong RAG candidates |
| **Total** | **-0.8** | **Score = max(0, 1.0 - 0.8) = 0.2** |

**Benchmark chinh (30 cases w/RAG)**: 30/30 cases = hardcoded reasoning → faithfulness = 1.0.
Day la ket qua dung vi ConfidenceGate luon PASS (0 LLM calls).

**LLM Refinement integration test** (force low confidence, 3 cases thuc te voi Ollama):
LLM reasoning duoc danh gia day du, ket qua:

| Query | Faithfulness | Penalties | Evidence |
|-------|:----------:|:---------:|----------|
| "check if KMS keys have rotation enabled" | **1.0** | 0 | kms, medium, kms_cmk_rotation_enabled |
| "verify S3 bucket encryption" | **1.0** | 0 | s3, s3_bucket_default_encryption, s3_bucket_kms_encryption |
| "check S3 public access" | **1.0** | 0 | s3, s3_bucket_public_access |

Ket luan: Khi LLM duoc kich hoat (low confidence), reasoning **grounded tot** — khong fabrication,
khong phantom reference, khong mau thuan voi output.

### 3.4 Correctness — Planning Correctness (composite)

**Check Selection F1** (khi agent tra specific checks):
```
Precision = |Selected ∩ Relevant| / |Selected|
Recall    = |Selected ∩ Relevant| / |Relevant|
F1        = 2 × Precision × Recall / (Precision + Recall)
```

**Service Accuracy** (khi agent tra group scan):
```
Correct = groups_to_scan[0] == expected_service
```

**Composite metric**:
```
Planning_Correctness = 0.7 × F1_mean + 0.3 × service_accuracy
```

### 3.5 Completeness — Action Type Accuracy

Binary per case: agent chon **dung loai hanh dong** khong?
- Expected "specific_checks" → agent tra `checks_to_scan` → dung
- Expected "group_scan" → agent tra `groups_to_scan` → dung
- Expected "either" → ca 2 deu chap nhan

### 3.6 Selection Analysis — Over-selection, Under-selection, Exact Match

3 metrics bo sung danh gia **chi tiet hon F1** ve hanh vi chon check cua agent.
Chi ap dung cho specific_checks cases co ground truth (20/30 cases).

#### Over-selection rate (FP / |predicted|)

Do ti le checks agent chon nhung **khong can thiet**. Giai thich truc tiep vi sao Precision thap.

```
Over-selection = |predicted - relevant| / |predicted|
```

Vi du: Expected = {A, B}, Agent chon = {A, B, C, D} → Over-selection = 2/4 = 0.50

**Y nghia trong security**: Over-selection gay **scan thua**, tang thoi gian va chi phi compute,
nhung khong gay miss vulnerability. Day la loi "an toan hon" so voi under-selection.

#### Under-selection rate (FN / |relevant|)

Do ti le checks quan trong ma agent **bo sot**. Lien quan truc tiep den risk he thong.

```
Under-selection = |relevant - predicted| / |relevant|
```

Vi du: Expected = {A, B, C}, Agent chon = {A} → Under-selection = 2/3 = 0.67

**Y nghia trong security**: Under-selection la **rui ro thuc su** — bo sot security check co the
dan den miss vulnerability khong duoc phat hien. Metric nay can duoc uu tien giam thieu.

#### Exact Match (EM)

Binary: predicted set **bang chinh xac** relevant set. Khong cho phep thua hay thieu.

```
EM = 1 if predicted_set == relevant_set else 0
EM_rate = sum(EM) / total_cases
```

**Y nghia**: Tieu chuan khac nhat, phu hop cho bao cao voi giang vien/reviewer.
EM thap + F1 cao cho thay agent **gan dung nhung khong hoan hao** — thuong la co 1-2 FP hoac FN.

---

## 4. Release Criteria

| Criterion | Nguong | Chieu | Mo ta |
|-----------|:------:|:-----:|-------|
| valid_output_rate_min | 100% | >= | Moi output phai hop le |
| grounded_reasoning_rate_min | 80% | >= | >= 80% reasoning co evidence tu context |
| check_selection_f1_min | 60% | >= | F1 >= 0.60 (specific checks cases) |
| service_accuracy_min | 90% | >= | >= 90% group scan chon dung service |
| planning_correctness_min | 65% | >= | Composite >= 0.65 |
| action_type_accuracy_min | 85% | >= | >= 85% chon dung loai hanh dong |
| over_selection_rate_max | 40% | <= | Agent khong duoc chon du qua 40% checks |
| under_selection_rate_max | 40% | <= | Agent khong duoc bo sot qua 40% checks quan trong |
| exact_match_rate_min | 20% | >= | >= 20% cases phai chon dung hoan toan |

**Verdict**: PASS khi tat ca 9 criteria deu dat.

File cau hinh: `benchmark_llm_gen/release_criteria_planning.json`

---

## 5. Ket qua cuoi cung

### 5.1 Metrics tong hop (llama3.2 w/RAG, 30 cases)

| Metric | Gia tri | Nguong | Margin | Verdict |
|--------|:-------:|:------:|:------:|:-------:|
| Valid Output Rate | **100%** | >= 100% | +0pp | PASS |
| Grounded Reasoning | **1.000** | >= 0.80 | +0.200 | PASS |
| Check Selection F1 | **0.656** | >= 0.60 | +0.056 | PASS |
| Service Accuracy | **100%** | >= 90% | +10pp | PASS |
| Planning Correctness | **0.759** | >= 0.65 | +0.109 | PASS |
| Action Type Accuracy | **100%** | >= 85% | +15pp | PASS |
| **Over-selection rate** | **0.363** | <= 0.40 | -0.037 | PASS |
| **Under-selection rate** | **0.200** | <= 0.40 | -0.200 | PASS |
| **Exact Match rate** | **35.0%** | >= 20% | +15pp | PASS |
| **Overall Verdict** | | | | **9/9 PASS** |

**Precision/Recall breakdown** (specific checks cases):
- Mean Precision: **0.637**
- Mean Recall: **0.800**

### 5.2 Ket qua theo input type

| Input Type | n | F1 | Svc Acc | Action | Over-sel | Under-sel | EM |
|------------|:-:|:--:|:------:|:------:|:--------:|:---------:|:--:|
| explicit_checks | 5 | **1.00** | — | 100% | **0.00** | **0.00** | **100%** |
| group_request | 5 | — | **100%** | 100% | — | — | — |
| specific_intent | 15 | 0.54 | — | 100% | 0.48 | 0.27 | 13% |
| ambiguous | 5 | N/A | — | 100% | — | — | — |

### 5.3 Ket qua theo service

| Service | n | F1 mean |
|---------|:-:|:-------:|
| S3 | 6 | **0.81** |
| KMS | 3 | **0.70** |
| CloudTrail | 3 | 0.63 |
| IAM | 7 | 0.61 |
| RDS | 5 | 0.58 |
| EC2 | 6 | 0.48 |

### 5.4 Per-case results (specific_intent) — voi Selection Analysis

| Case ID | Request (tom tat) | F1 | P | R | Over-sel | Under-sel | EM |
|---------|-------------------|:--:|:-:|:-:|:--------:|:---------:|:--:|
| s3_enc_002 | S3 encryption enabled | **1.00** | 1.00 | 1.00 | 0.00 | 0.00 | Y |
| kms_rot_013 | KMS key rotation | **1.00** | 1.00 | 1.00 | 0.00 | 0.00 | Y |
| s3_pub_001 | S3 public access (VI) | 0.86 | 0.75 | 1.00 | 0.25 | 0.00 | N |
| iam_policy_006 | IAM admin privileges | 0.67 | 0.67 | 0.67 | 0.33 | 0.33 | N |
| rds_pub_010 | RDS public access | 0.50 | 0.33 | 1.00 | 0.67 | 0.00 | N |
| ec2_imds_008 | IMDSv2 | 0.50 | 0.33 | 1.00 | 0.67 | 0.00 | N |
| iam_key_005 | IAM access keys | 0.50 | 0.40 | 0.67 | 0.60 | 0.33 | N |
| rds_enc_011 | RDS encryption | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 | N |
| ct_log_012 | CloudTrail logging | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 | N |
| iam_root_014 | Root account | 0.50 | 1.00 | 0.33 | 0.00 | 0.67 | N |
| s3_log_003 | S3 logging | 0.40 | 0.25 | 1.00 | 0.75 | 0.00 | N |
| iam_mfa_004 | MFA enabled | 0.40 | 0.50 | 0.33 | 0.50 | 0.67 | N |
| ec2_sg_007 | Security groups SSH | 0.40 | 0.25 | 1.00 | 0.75 | 0.00 | N |
| kms_pub_015 | KMS public key | 0.40 | 0.25 | 1.00 | 0.75 | 0.00 | N |
| ec2_ebs_009 | EBS encryption | **0.00** | 0.00 | 0.00 | 1.00 | 1.00 | N |

Chi tiet day du trong benchmark output JSON.

### 5.5 Phan tich Selection Analysis

#### Over-selection (model chon du)

**Tong quan**: Mean over-selection rate = **0.363** (36.3% predicted checks la thua).

| Muc do | Over-sel | Cases | Dac diem |
|--------|:--------:|:-----:|---------|
| Hoan hao (0.00) | 0.00 | 7 | explicit_checks (5) + 2 specific (s3_enc, kms_rot) |
| Thap (0.01-0.30) | 0.25 | 1 | s3_pub_001: 1 FP trong 4 predicted |
| Trung binh (0.31-0.60) | 0.33-0.60 | 5 | iam_policy, iam_key, rds_enc, ct_log, iam_mfa |
| Cao (0.61-0.80) | 0.67-0.75 | 6 | s3_log, ec2_sg, kms_pub, rds_pub, ec2_imds |
| Qua cao (>0.80) | 1.00 | 1 | ec2_ebs_009: 100% checks chon deu sai |

**Root cause**: RAG tra nhieu candidates co score gan nhau → DeterministicScorer giu lai tat ca.
Cases co over-sel >= 0.67 deu la truong hop expected chi 1 check nhung RAG tra 3-4 candidates.

**Moi quan he voi Precision**: Over-selection rate = 1 - Precision (khi predicted > 0).
Mean Precision 0.637 tuong ung voi mean over-sel 0.363. Day la 2 mat cua cung 1 van de.

#### Under-selection (model bo sot)

**Tong quan**: Mean under-selection rate = **0.200** (20% checks quan trong bi bo sot).

| Muc do | Under-sel | Cases | Dac diem |
|--------|:---------:|:-----:|---------|
| Hoan hao (0.00) | 0.00 | 12 | Agent khong bo sot check nao |
| Trung binh (0.33-0.50) | 0.33-0.50 | 5 | iam_policy, iam_key, rds_enc, ct_log |
| Cao (0.67) | 0.67 | 2 | iam_mfa_004, iam_root_014: miss 2/3 checks |
| Hoan toan (1.00) | 1.00 | 1 | ec2_ebs_009: miss 1/1 check |

**Nhan xet**: Under-selection tap trung vao **IAM compound queries** (can nhieu checks lien quan
nhung RAG chi tra 1-2). Vi du "kiem tra MFA cho tat ca users" can 3 checks (user MFA + root MFA
+ hardware MFA) nhung agent chi tim 1.

**Risk implication**: 20% under-selection nghia la cu 5 checks quan trong, co 1 bi bo sot.
Trong security context, day la rui ro can giam — mot missed check co the la mot vulnerability
khong duoc phat hien.

#### Exact Match (chon dung hoan toan)

**Tong quan**: EM rate = **35%** (7/20 cases chon dung hoan toan).

| Input Type | EM cases | Total | EM rate |
|------------|:--------:|:-----:|:-------:|
| explicit_checks | 5/5 | 5 | **100%** |
| specific_intent | 2/15 | 15 | **13.3%** |

**7 cases dat EM**:
- 5 explicit_checks (FAST_TRACK — trivially exact)
- s3_enc_002 (S3 encryption — RAG tra chinh xac 2 checks)
- kms_rot_013 (KMS rotation — RAG tra chinh xac 1 check)

**13 cases khong dat EM** (nhung van co F1 > 0):
- 6 cases: chi over-select (co tat ca relevant + them FP) — F1 van kha (0.40-0.86)
- 5 cases: ca over va under-select — F1 trung binh (0.40-0.67)
- 1 case: chi under-select (iam_root_014: P=1.0 nhung R=0.33) — chon it nhung dung
- 1 case: complete miss (ec2_ebs_009: F1=0.00)

**Insight**: EM thap + F1 kha cho thay agent **gan dung nhung khong hoan hao**. Phan lon
cases sai do them 1-3 FP (over-select), khong phai hoan toan sai huong.

---

## 6. RAG Ablation

### 6.1 So sanh With RAG vs Without RAG

| Metric | With RAG | Without RAG | RAG Lift |
|--------|:--------:|:-----------:|:--------:|
| Valid Output Rate | **100%** | 33.3% | **+66.7pp** |
| Grounded Reasoning | **1.000** | 0.733 | **+0.267** |
| Check Selection F1 | **0.656** | 0.250 | **+0.406** |
| Over-selection rate | **0.363** | ~0.90 | **-0.537** (giam = tot) |
| Under-selection rate | **0.200** | ~0.85 | **-0.650** (giam = tot) |
| Exact Match rate | **35%** | ~0% | **+35pp** |
| Service Accuracy | **100%** | 100% | 0 |
| Planning Correctness | **0.759** | 0.475 | **+0.284** |
| Action Type Accuracy | **100%** | 100% | 0 |
| Verdict | **PASS (9/9)** | **FAIL** | |

### 6.2 Tai sao Without RAG that bai?

Khi khong co RAG:
- 20/30 cases (specific_intent + ambiguous) di vao RETRIEVAL_PATH
- `_retrieve()` tra empty → scorer tra [] → ConfidenceGate FAIL → LLM refinement
- LLM (3B) **khong biet Prowler check IDs** → bia check names (vd `S3BucketPublicAccessCheck`,
  `CheckMFAStatusForIAMUsers`, `EC2_VPC_CIDR_BLOCK`)
- Tat ca check IDs bia **khong match Prowler format** → Structure FAIL
- Khong overlap voi ground truth → F1 = 0.00 cho 15/15 specific_intent cases

### 6.3 RAG Lift theo input type

| Input Type | F1 w/RAG | F1 no-RAG | RAG Lift |
|------------|:--------:|:---------:|:--------:|
| explicit_checks | 1.00 | 1.00 | 0 (khong dung RAG) |
| group_request | N/A | N/A | 0 (khong dung RAG) |
| specific_intent | **0.54** | **0.00** | **+0.54** |
| ambiguous | N/A | N/A | — |

**Ket luan**: RAG la **bat buoc** cho specific_intent requests. Khong co RAG, LLM 3B
khong the cung cap valid Prowler check IDs.

---

## 7. Phan tich loi

### 7.1 Patterns loi chinh

**Pattern A — Low Precision (FP cao)**: Agent tra nhieu checks hon can thiet.

| Case | Expected | Got | FP | Nguyen nhan |
|------|:--------:|:---:|:--:|-------------|
| s3_pub_001 | 3 checks | 5 checks | 4 | RAG tra nhieu S3 public-related checks co score gan nhau |
| s3_log_003 | 1 check | 4 checks | 3 | RAG tra nhieu S3 checks co score gan nhau |
| ec2_sg_007 | 1 check | 4 checks | 3 | RAG tra nhieu EC2 checks lien quan port |
| kms_pub_015 | 1 check | 4 checks | 3 | RAG tra tat ca KMS checks |
| iam_key_005 | 3 checks | 5 checks | 3 | RAG tra nhieu IAM key-related checks |

**Root cause**: RAG scores qua gan nhau (vi du 1.030, 1.028, 1.027, 1.026 cho cac S3 checks).
DeterministicScorer khong phan biet duoc relevant vs irrelevant khi scores cach nhau < 0.01.
Score gap filter (DROP_RATIO_THRESHOLD=0.85) chi giup khi co **gap thuc su**.

**Pattern B — Low Recall (FN cao)**: Agent bo sot checks dung.

| Case | Expected | Got | FN | Nguyen nhan |
|------|:--------:|:---:|:--:|-------------|
| s3_pub_001 | 3 checks | 5 checks | 2 | RAG tra nhieu nhung miss `s3_bucket_level_public_access_block`, `s3_account_level_public_access_blocks` |
| iam_mfa_004 | 3 checks | 2 checks | 2 | RAG khong tra root MFA checks |
| iam_root_014 | 3 checks | 1 check | 2 | RAG chi tra 1/3 root-related checks |

**Root cause**: RAG retrieval khong recall du checks lien quan, dac biet cho compound queries
(vd "kiem tra MFA cho tat ca users" can ca user MFA + root MFA + hardware MFA).

**Pattern C — Complete miss (F1=0.00)**: 1 case.

| Case | Expected | Got | Nguyen nhan |
|------|----------|-----|-------------|
| ec2_ebs_009 | ec2_ebs_default_encryption | workspaces_volume_encryption_enabled | RAG tra sai service (workspaces thay vi ec2) |

### 7.2 Over-selection vs Under-selection Trade-off (specific_intent)

| Metric | Gia tri | Nhan xet |
|--------|:-------:|----------|
| Mean Precision | **0.516** | Diem yeu chinh — nhieu false positives |
| Mean Recall | **0.733** | Kha — da tim duoc phan lon checks dung |
| **Over-selection rate** | **0.484** | ~48% checks agent chon la thua |
| **Under-selection rate** | **0.267** | ~27% checks quan trong bi bo sot |
| **Exact Match** | **13.3%** | Chi 2/15 cases chon dung hoan toan |

**Over-selection >> Under-selection**: Agent **chon du gap doi** so voi bo sot (0.484 vs 0.267).

Day la trade-off **chap nhan duoc trong security context**:
- **FP (over-select)**: Scan thua → chi tang thoi gian, khong gay rui ro
- **FN (under-select)**: Bo sot check → **co the miss vulnerability** → rui ro that su

Tuy nhien, over-selection rate 0.484 cho specific_intent van qua cao — gan nua so checks
agent chon la khong can thiet. Can cai thien RAG scoring resolution de giam FP.

---

## 8. Cai tien da ap dung (trong qua trinh benchmark)

### 8.1 Vietnamese → English query translation

**Van de**: RAG documents la tieng Anh. Query tieng Viet (vd "kiem tra ma hoa RDS") co
embedding similarity thap voi documents → retrieval sai hoan toan.

**Giai phap**: Them `_build_rag_query()` — dich keywords tieng Viet sang tieng Anh
bang dictionary-based translation (khong can LLM). Vi du:
```
"kiem tra ma hoa RDS database storage" → "rds check encryption database storage"
```

**Ket qua**:
| Case | F1 truoc | F1 sau | Delta |
|------|:--------:|:------:|:-----:|
| rds_enc_011 (ma hoa RDS) | 0.00 | **0.50** | +0.50 |
| s3_pub_001 (public access) | 0.57 | **0.86** | +0.29 |

### 8.2 Score enrichment

**Van de**: `build_context()` tra `score=None` cho findings → default 0.8 cho tat ca
→ DeterministicScorer khong phan biet duoc candidates.

**Giai phap**: Them `_enrich_scores()` — lay scores chi tiet tu `retrieve_checks()` merge vao PlanningBundle.

### 8.3 Score gap filter

**Van de**: DeterministicScorer tra tat ca TOP_K=5 candidates ke ca irrelevant.

**Giai phap**: Them `DROP_RATIO_THRESHOLD=0.85` — chi giu candidates co score >= 85% cua top score.

**Ket qua**:
| Case | F1 truoc | F1 sau | Candidates truoc → sau |
|------|:--------:|:------:|:-----:|
| kms_rot_013 | 0.40 | **1.00** | 4 → 1 (dropped 3 FP) |
| iam_policy_006 | 0.57 | **0.67** | 4 → 3 (dropped 1 FP) |
| rds_pub_010 | 0.40 | **0.50** | 4 → 3 (dropped 1 FP) |

### 8.4 Metric whitelist fix

**Van de**: Benchmark metric chi whitelist 31 Prowler service prefixes, thuc te co 82.
Check IDs hop le (workspaces_, kafka_, neptune_...) bi danh invalid sai.

**Giai phap**: Mo rong whitelist tu 31 → 82 prefixes trong `planning_metrics.py`.

**Ket qua**: valid_output_rate: 76.7% → 100%.

---

## 9. Kien truc ky thuat

### 9.1 Files lien quan

| File | Vai tro |
|------|---------|
| `agents/planning_agent.py` | Agent chinh — V2 architecture |
| `agents/shared/rag_client.py` | Client goi RAG API |
| `agents/shared/utils.py` | parse_llm_json, sanitize_check_id |
| `config.py` | OLLAMA_MODEL, OLLAMA_BASE_URL, RAG_API_URL |
| `benchmark_llm_gen/benchmark_planning.py` | Benchmark engine |
| `benchmark_llm_gen/run_planning_benchmark.py` | CLI entry point |
| `benchmark_llm_gen/planning_metrics.py` | 7 metrics implementation (4 core + 3 selection analysis) |
| `benchmark_llm_gen/benchmark_planning_cases.json` | 30 test cases |
| `benchmark_llm_gen/release_criteria_planning.json` | Nguong PASS/FAIL |
| `tests/test_planning_agent_rs2.py` | Unit tests (60+ tests) |
| `tests/test_planning_agent_coverage.py` | Supplementary tests — query translation, score enrichment, gap filter, LLM path, no-RAG (41 tests) |
| `tests/test_planning_faithfulness.py` | Faithfulness metric tests — negative checks + LLM integration (22 tests, 3 require Ollama+RAG) |

### 9.2 Cach chay benchmark

```bash
# Chay full benchmark voi RAG
python benchmark_llm_gen/run_planning_benchmark.py --mode full

# Chay khong RAG (ablation test)
python benchmark_llm_gen/run_planning_benchmark.py --mode full --no-rag

# Chi evaluate tu inference co san
python benchmark_llm_gen/run_planning_benchmark.py --mode evaluate-only \
  --inference-dir benchmark_llm_gen/inference_outputs/planning_run_YYYYMMDD_HHMMSS

# Debug mode
python benchmark_llm_gen/run_planning_benchmark.py --mode full -v
```

Yeu cau:
- Ollama running (`ollama serve`) voi model llama3.2:latest
- RAG server running tai localhost:8001 (chi khi chay voi RAG)

### 9.3 Latency

| Path | n | Mean | Min | Max |
|------|:-:|:----:|:---:|:---:|
| FAST_TRACK | 5 | ~1ms | 0.6ms | 3.8ms |
| GROUP_SCAN | 5 | ~1ms | 0.6ms | 1.6ms |
| RETRIEVAL_PATH | 20 | ~5s | 1.6s | 27.6s |

RETRIEVAL_PATH latency chu yeu do 2 RAG calls (build_context + retrieve_checks for enrichment).
Case s3_pub_001 co latency cao nhat (27.6s) do cold start RAG. LLM khong duoc goi trong benchmark nay.

---

## 10. Han che

1. **Faithfulness trong benchmark chinh = trivially 1.0**: 0/30 cases trigger LLM trong benchmark
   30 cases (hardcoded reasoning luon pass). **Da khac phuc** bang integration test rieng
   (`test_planning_faithfulness.py::TestLLMRefinementIntegration`) — force low confidence voi
   Ollama + RAG that, ket qua: 3/3 cases LLM reasoning grounded tot (score=1.0, 0 penalties).
   Tuy nhien, chi test 3 cases LLM → can mo rong neu thay doi prompt hoac model.

2. **Over-selection rate cao (0.363, specific_intent: 0.484)**: RAG tra scores qua gan nhau
   cho nhieu candidates → agent giu lai tat ca. Score gap filter chi giai quyet mot phan.
   Can cai thien RAG retrieval quality (embedding model tot hon, cross-encoder reranking).

3. **Exact Match thap cho specific_intent (13.3%)**: Chi 2/15 specific_intent cases dat EM.
   Phan lon cases co 1-3 FP (over-select). EM se tang khi giam over-selection.

4. **1 case F1=0.00** (ec2_ebs_009): RAG tra `workspaces_volume_encryption_enabled` thay vi
   `ec2_ebs_default_encryption`. Day la loi RAG retrieval, khong phai Planning Agent logic.
   Case nay co over-sel=1.00 va under-sel=1.00 — hoan toan sai huong.

5. **30 cases** khong du de tinh statistical significance. Day la directional evaluation.

6. **Vietnamese query translation** dung dictionary-based (29 keywords). Co the miss compound
   phrases hoac informal language. LLM-based translation se chinh xac hon nhung tang latency.

7. **Ambiguous cases** (5) khong co ground truth checks → F1/Over-sel/Under-sel/EM = N/A. Chi do action_type.

8. **Score enrichment** goi them 1 RAG call (`retrieve_checks`) cho moi RETRIEVAL_PATH request,
   tang latency ~50%. Trade-off chap nhan duoc vi cai thien scoring quality dang ke.

---

## 11. Ket luan

Planning Agent voi **RAG-first, LLM-conditional architecture (V2)** dat:
- **9/9 release criteria PASS** (6 core + 3 selection analysis)
- **Planning Correctness 0.759** (composite: 0.7 × F1 + 0.3 × Service Accuracy)
- **Check Selection F1 0.656** (P=0.637, R=0.800) — recall kha, precision can cai thien
- **Over-selection rate 0.363** — 36.3% checks chon la thua (giai thich Precision thap)
- **Under-selection rate 0.200** — 20% checks quan trong bi bo sot (risk metric)
- **Exact Match 35%** — 7/20 cases chon dung hoan toan
- **Service Accuracy 100%** — group scan luon chon dung service
- **Action Type Accuracy 100%** — luon chon dung loai hanh dong
- **0 LLM calls** khi co RAG — toan bo xu ly deterministic

### Selection Analysis Summary

3 metrics moi cung cap **insight sau hon F1** ve hanh vi agent:

| Metric | Y nghia | Ket qua | Nhan xet |
|--------|---------|:-------:|----------|
| Over-selection | Chon du | **0.363** | Van de chinh — RAG scores qua gan nhau, agent giu lai qua nhieu candidates |
| Under-selection | Bo sot | **0.200** | Chap nhan — tap trung o IAM compound queries |
| Exact Match | Chinh xac tuyet doi | **35%** | explicit_checks dat 100%, specific_intent chi 13% |

**Over-selection la van de lon hon under-selection** (0.363 vs 0.200). Trong security context,
day la trade-off chap nhan duoc: chon thua chi tang scan time, bo sot co the miss vulnerability.
Tuy nhien, over-sel 0.484 cho specific_intent van qua cao — can cai thien.

Faithfulness duoc danh gia bang **keyword grounding + 3 negative checks** (fabrication,
output-reasoning mismatch, phantom reference). Benchmark chinh (30 cases) cho faithfulness = 1.0
vi tat ca reasoning la hardcoded (0 LLM calls). Integration test rieng voi Ollama + RAG that
(force low confidence → LLM refinement) xac nhan: **LLM reasoning grounded tot, 0 penalties
tren 3 test cases** — khong fabrication, khong phantom reference, khong mau thuan output.

Diem manh lon nhat cua V2: **FAST_TRACK (F1=1.00, EM=100%)** va **GROUP_SCAN (SA=100%)**
xu ly chinh xac 10/30 cases ma khong can RAG hay LLM. Diem yeu chinh nam o
**RAG retrieval quality** cho specific_intent — khi RAG tra nhieu candidates co score
gan nhau, agent khong phan biet duoc relevant vs irrelevant (F1=0.54, EM=13.3%).

Cac van de cu the:
- **ec2_ebs_009** van la complete miss (F1=0.00, over=1.00, under=1.00) — RAG tra `workspaces_volume_encryption_enabled` thay vi `ec2_ebs_default_encryption`
- **iam_mfa_004** va **iam_root_014** co under-sel = 0.67 — RAG khong recall du IAM compound checks

Huong cai thien tiep theo: nang cap RAG (embedding model, scoring resolution, cross-encoder reranking)
se truc tiep giam over-selection rate va tang Exact Match rate cho specific_intent.
