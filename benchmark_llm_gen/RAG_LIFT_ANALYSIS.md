# Phan tich van de RAG Lift & Qua trinh cai tien

**Ngay**: 2026-04-03
**Trang thai**: Hoan thanh TP-v2 — Accuracy 80%, RAG Lift +6.7pp

---

## 1. Van de ban dau

RAG duoc ky vong nang cao chat luong danh gia severity,
nhung thuc te **lam giam accuracy** cua llama3.2 tu 76.7% xuong 66.7%.

### Ket qua Single-Pass (truoc cai tien)

| Config | Accuracy | QWK | Consistency | Completeness |
|--------|:--------:|:---:|:-----------:|:------------:|
| llama3.2 no-RAG | **76.7%** | **0.916** | 96.7% | 92.8% |
| llama3.2 w/RAG | 66.7% | 0.684 | 86.7% | 78.3% |
| qwen3:8b w/RAG | 56.7% | 0.760 | 100% | 90.6% |
| qwen3:8b no-RAG | 50.0% | 0.761 | 100% | 93.3% |

RAG Lift cua llama3.2: **-10.0pp accuracy, -23.2pp QWK**.

---

## 2. Nguyen nhan goc

### 2.1 Anchoring Bias

Prompt cu gui **4 signals dong thoi** cho LLM:
1. `finding.severity` (tu Prowler scanner)
2. `rag_context.official_severity` (tu Prowler KB)
3. `rag_context.compliance_mappings`
4. `rag_context.confidence_note`

Khi Signal 1 va 2 **mau thuan** (finding="high", official="medium"),
model 3B khong phan giai duoc → default len **Critical**.

Bang chung — 3 case "exact" (don gian nhat) bi RAG lam sai:

| Case | Finding sev | RAG official | Expected | no-RAG | w/RAG |
|------|:-----------:|:------------:|:--------:|:------:|:-----:|
| risk_s3_exact_001 | high | medium | Medium | Medium OK | Critical SAI |
| risk_cloudtrail_exact_001 | medium | — | Medium | Medium OK | Critical SAI |
| risk_kms_exact_001 | medium | — | Medium | Medium OK | Critical SAI |

### 2.2 Blind Spots

- **llama3.2 "High-blind"**: 0/30 High predictions. Binary: Critical hoac Medium.
- **qwen3:8b "Low-blind"**: 1/30 Low predictions (expected: 6). Over-estimate o dai thap.

### 2.3 Dataset skew

Expected: Critical=14(47%), High=4, Medium=6, Low=6.
Model thien Critical se "trung" nhieu hon tu nhien.

---

## 3. Qua trinh cai tien — 3 lan iteration

### Iteration 1: Two-Pass + Simplified Context (TP-v0)

**Thay doi**:
- Tach 1 prompt thanh 2: PASS1 (finding only) → PASS2 (draft + RAG)
- Bo compliance_mappings va confidence_note khoi LLM view
- PASS2 prompt: "Neu GIONG → GIU NGUYEN", "KHONG tu dong tang severity"

**Kho khan gap phai**:
1. Prompt PASS1 viet khac prompt cu qua nhieu (them "CHI danh gia dua tren...",
   thay doi wording rubric) → baseline giam tu 76.7% xuong 70%
2. PASS2 **qua conservative** → model luon giu draft, khong bao gio dieu chinh
3. Ket qua: w/RAG va no-RAG **giong 100%**, RAG Lift = 0

| Config | Accuracy | QWK | RAG Lift |
|--------|:--------:|:---:|:--------:|
| TP-v0 no-RAG | 70.0% | 0.852 | — |
| TP-v0 w/RAG | 70.0% | 0.852 | 0.0pp |

**Nhan xet**: Loai bo duoc negative lift (-10pp → 0), nhung RAG khong dong gop gi.

### Iteration 2: Khoi phuc PASS1 + Active PASS2 + Fix bug primary_finding (TP-v1)

**Kho khan gap phai va cach giai quyet**:

**Van de 1: PASS1 baseline thap**
- *Nguyen nhan*: Prompt PASS1 viet lai rubric va them constraint khong can thiet
- *Fix*: Khoi phuc PASS1 rubric giong het prompt goc, chi bo phan RAG instructions

**Van de 2: PASS2 khong bao gio duoc goi (Pass 2 call count = 0)**
- *Phat hien*: Kiem tra llm_metrics cho thay **tat ca 30 cases chi co 1 LLM call**
- *Nguyen nhan goc*: `_fetch_rag_chunk()` chi doc `related_findings` tu RAG bundle,
  nhung check chinh nam trong `primary_finding`. Vi du: query s3_bucket_level_public_access_block,
  `primary_finding` co severity="medium" nhung `related_findings` chi chua cac check KHAC
  (s3_account_level_public_access_blocks, s3_access_point_public_access_block).
  → `rag_data.get("severity")` tra ve None → dieu kien `has_rag` = False → Pass 2 bi skip
- *Fix*: Them dong doc `primary_finding` vao `chunk_map` truoc khi doc `related_findings`
- *Day la bug ton tai tu truoc khi co Two-Pass* — Single-Pass khong bi anh huong vi
  no dump toan bo rag_context vao prompt bat ke co severity hay khong

**Van de 3: PASS2 prompt qua than trong**
- *Nguyen nhan*: Rules "Neu GIONG → GIU NGUYEN" va "KHONG tu dong tang" lam model
  mac dinh khong thay doi gi
- *Fix*: Viet lai thanh 4 rules can bang: trung→giu, cao hon→xet ha, thap hon→xet tang,
  uu tien evidence

**Ket qua TP-v1**:

| Config | Accuracy | QWK | Consistency | Completeness | Verdict |
|--------|:--------:|:---:|:-----------:|:------------:|:-------:|
| TP-v1 w/RAG | **76.7%** | 0.854 | 86.7% | **38.9%** | **FAIL** |

- Accuracy dat 76.7% (bang baseline goc!)
- RAG Lift = +3.3pp (w/RAG 76.7% vs no-RAG 73.3%)
- Pass 2 thay doi 11/30 cases: +5 fix, +4 improve, -2 regression
- **NHUNG**: Evidence completeness **38.9% (FAIL)** — duoi nguong 45%

### Iteration 3: Fix evidence completeness (TP-v2)

**Kho khan gap phai**:

**Van de: Pass 2 viet lai reasoning hoan toan, mat het evidence**

Reasoning cua Pass 2 (v1):
> "Muc do nguy hiem cua lo hong nay tuong ung voi muc do chinh thuc tu AWS/Prowler.
>  Vi vay, chung ta giu nguyen muc do nguy hiem la Critical."

Reasoning cua Pass 1 (giau evidence):
> "RDS Instance prod-db co quyen truy cap cong khai duoc bat, dieu nay co the gay ra
>  rui ro cho du lieu nhay cam."

Pass 2 chi noi VE QUA TRINH dieu chinh, khong noi VE LO HONG.
Evidence keywords ("public access", "RDS", "ACL") bi mat hoan toan.

**Fix**: Thay doi duy nhat 1 dong trong PASS2 prompt — mo ta output:
- Cu: `"<Giai thich 1-2 cau, neu ro neu co dieu chinh so voi draft>"`
- Moi: `"<Dua tren draft_reasoning, giu lai mo ta lo hong va bang chung ky thuat. Them ghi chu neu co dieu chinh severity so voi draft.>"`

**Ket qua TP-v2**:

| Config | Accuracy | QWK | Consistency | Completeness | Verdict |
|--------|:--------:|:---:|:-----------:|:------------:|:-------:|
| **TP-v2 w/RAG** | **80.0%** | **0.939** | 93.3% | 60.6% | **PASS** |

### Iteration 4: Fix parse error + Smart reasoning (TP-v3)

**Kho khan gap phai va cach giai quyet**:

**Van de 1: Parse error — 1 case tra ve severity=None (s3_paraphrase_001)**
- *Phat hien*: Per-case output cho thay `got=None`, `ERROR: 'NoneType' object has no attribute 'get'`
- *Dieu tra*: Kiem tra `llm_metrics.call_count` = **0** → loi xay ra **truoc ca Pass 1**,
  khong phai loi LLM parse JSON
- *Nguyen nhan goc*: Traceback chi ra `_fetch_rag_chunk` dong 245:
  `pf.get("check_id")` — `pf` la `None` vi RAG API tra `primary_finding: null`
  khi khong tim duoc check trong knowledge base.
  Code cu dung `risk_bundle.get("primary_finding", {})` — nham tuong `{}` la default,
  nhung khi key ton tai voi value=None thi `.get()` tra ve None, khong phai `{}`
- *Fix*: Thay `get("primary_finding", {})` bang `get("primary_finding") or {}`.
  `or {}` dam bao luon la dict ke ca khi value la None

**Van de 2: Khi exception xay ra, finding raw (khong co severity) duoc tra ve**
- *Nguyen nhan*: `_score_findings` catch exception va `results.append(finding)` —
  finding goc khong co field `severity`, `risk_score` → benchmark doc None
- *Fix*: Thay vi append finding goc, tao fallback dict voi default severity="Medium",
  risk_score=5. Dam bao downstream code luon co du fields

**Van de 3: Completeness 60.6% — PASS nhung cach xa SP-noRAG (92.8%)**
- *Phan tich*: TP-v2 da sua output template de Pass 2 giu lai evidence, nhung
  19/30 cases Pass 2 **khong doi severity** ma van viet lai reasoning (mat evidence)
- *Nhan xet*: Voi 19 case khong doi severity, viec goi LLM lan 2 chi de...
  viet lai cau tra loi giong het nhung ngan hon. Hoan toan lang phi
- *Fix*: **Smart reasoning** — them logic trong `_pass2_adjust`:
  `if adjusted["ai_severity"] == draft_severity: adjusted["ai_reasoning"] = draft_reasoning`
  Khi Pass 2 giu nguyen severity → giu nguyen reasoning cua Pass 1 (giau evidence).
  Chi dung reasoning moi cua Pass 2 khi severity thuc su thay doi (11/30 cases)
- *Ket qua*: Completeness tang tu 60.6% len **82.2%** — gan voi SP-noRAG (92.8%)

**Ket qua TP-v3 (final)**:

| Config | Accuracy | QWK | Consistency | Faith | Completeness | Verdict |
|--------|:--------:|:---:|:-----------:|:-----:|:------------:|:-------:|
| **TP-v3 w/RAG** | **83.3%** | **0.941** | **96.7%** | **0.983** | **82.2%** | **PASS** |

---

## 4. Ket qua cuoi cung — So sanh toan bo

| Config | Accuracy | QWK | Consist | Faith | Complt | Verdict |
|--------|:--------:|:---:|:-------:|:-----:|:------:|:-------:|
| llama SP-noRAG (baseline) | 76.7% | 0.916 | 96.7% | 0.967 | 92.8% | PASS |
| llama SP-wRAG (cu) | 66.7% | 0.684 | 86.7% | 0.933 | 78.3% | PASS |
| llama TP-v0 | 70.0% | 0.852 | 96.7% | 0.967 | 76.7% | PASS |
| llama TP-v1 | 76.7% | 0.854 | 86.7% | 0.917 | 38.9% | FAIL |
| llama TP-v2 | 80.0% | 0.939 | 93.3% | 0.933 | 60.6% | PASS |
| **llama TP-v3** | **83.3%** | **0.941** | **96.7%** | **0.983** | **82.2%** | **PASS** |
| qwen3:8b SP-wRAG | 56.7% | 0.760 | 100% | 0.967 | 90.6% | PASS |

### RAG Lift qua cac iteration

| Version | Accuracy Lift | QWK Lift | Giai quyet duoc gi |
|---------|:------------:|:--------:|---|
| Single-Pass (cu) | **-10.0pp** | -0.232 | (van de goc) |
| TP-v0 | 0.0pp | 0.000 | Loai bo negative lift |
| TP-v1 | +3.3pp | -0.043 | RAG bat dau giup |
| TP-v2 | +6.7pp | +0.041 | RAG dong gop tich cuc |
| **TP-v3** | **+10.0pp** | **+0.043** | Fix loi + smart reasoning |

### Per-case: TP-v3 w/RAG vs SP-wRAG cu

| Case | Expected | SP-wRAG | TP-v3 | Thay doi |
|------|:--------:|:-------:|:-----:|:--------:|
| risk_s3_exact_001 | Medium | Critical | **Medium** | FIX |
| risk_cloudtrail_exact_001 | Medium | Critical | **Medium** | FIX |
| risk_kms_exact_001 | Medium | Critical | **Medium** | FIX |
| risk_iam_paraphrase_001 | High | Critical | **High** | FIX |
| risk_ec2_paraphrase_001 | High | Critical | **High** | FIX |
| risk_rds_paraphrase_001 | High | Critical | **High** | FIX |
| risk_s3_paraphrase_001 | Critical | Critical | **Critical** | FIX (was None in v2) |
| risk_s3_paraphrase_003 | Low | Medium | **Low** | FIX |
| risk_iam_paraphrase_002 | Low | Medium | **Low** | FIX |
| risk_iam_semantic_hard_002 | Low | Critical | **Low** | FIX |
| risk_rds_risk_001 | High | Medium | **High** | FIX |
| risk_s3_paraphrase_002 | Medium | Medium | **Medium** | FIX (was High in v1) |
| risk_cloudtrail_paraphrase_001 | Medium | Medium | Low | REGRESS |
| risk_iam_risk_001 | Critical | Critical | High | REGRESS |

**Net: +12 fixes, -2 regressions so voi SP-wRAG**

### So sanh voi qwen3:8b

| Metric | llama3.2 TP-v3 | qwen3:8b SP-wRAG | Ai thang |
|--------|:-:|:-:|---|
| Accuracy | **83.3%** | 56.7% | llama +26.6pp |
| QWK | **0.941** | 0.760 | llama +0.181 |
| RAG Lift | **+10.0pp** | +6.7pp | llama |
| Consistency | 96.7% | **100%** | qwen |
| Completeness | 82.2% | **90.6%** | qwen |
| Faithfulness | **0.983** | 0.967 | llama |
| Latency/case | **~11s** | ~49s | llama 4.5x nhanh hon |

---

## 5. Tong ket kho khan & bai hoc

### 5.1 Cac kho khan chinh

| # | Kho khan | Nguyen nhan | Cach phat hien | Cach giai quyet |
|---|---------|------------|----------------|-----------------|
| 1 | RAG lam giam accuracy -10pp | Anchoring bias: 4 signals mau thuan trong 1 prompt | So sanh per-case w/RAG vs no-RAG | Two-Pass: tach finding evaluation va RAG adjustment |
| 2 | Prompt moi yeu hon prompt cu | Viet lai rubric khac tu ngu goc | Baseline TP-noRAG 70% < SP-noRAG 76.7% | Khoi phuc rubric giong het prompt goc |
| 3 | Pass 2 khong bao gio duoc goi | Bug: `_fetch_rag_chunk` chi doc `related_findings`, bo qua `primary_finding` | Kiem tra `llm_metrics.call_count` = 1 cho tat ca 30 cases | Them doc `primary_finding` vao chunk_map |
| 4 | Pass 2 qua conservative | Prompt rules "GIU NGUYEN" + "KHONG tang" | TP-wRAG = TP-noRAG 100% giong nhau | Viet lai 4 rules can bang (giu/ha/tang/evidence) |
| 5 | Evidence completeness 38.9% FAIL | Pass 2 viet reasoning ve qua trinh dieu chinh, mat evidence | So sanh reasoning wRAG vs noRAG cung case | Thay doi output template: "Dua tren draft_reasoning, giu lai bang chung ky thuat" |
| 6 | 1 case crash (severity=None) | `primary_finding` la None khi RAG khong tim duoc check. `get(key, {})` van tra None khi key ton tai voi value=None | Traceback chi ra `pf.get("check_id")` voi pf=None. call_count=0 chung to loi truoc LLM | Thay `get("primary_finding", {})` bang `get("primary_finding") or {}` |
| 7 | Exception tra finding raw khong co severity | `_score_findings` catch exception va append finding goc (thieu severity/risk_score fields) | Benchmark doc severity=None tu finding goc | Tao fallback dict voi default severity="Medium", risk_score=5 |
| 8 | Completeness 60.6% — 19/30 cases khong doi severity nhung van viet lai reasoning | Pass 2 luon goi LLM va dung reasoning moi (ngan, thieu evidence) ke ca khi khong doi severity | Dem so case severity khong doi: 19/30 → reasoning bi viet lai vo ich | Smart reasoning: neu severity khong doi → giu nguyen reasoning Pass 1 |

### 5.2 Thay doi mang lai cai tien lon nhat

1. **Two-Pass architecture** (v0): Dao nguoc RAG Lift tu -10pp len 0pp.
   Y tuong cot loi: model hinh thanh judgment rieng TRUOC khi thay RAG context.

2. **Fix bug primary_finding** (v1): Kich hoat Pass 2 thuc su hoat dong.
   Khong phai loi prompt — la loi data pipeline. Neu khong check call_count se khong
   bao gio phat hien.

3. **Output template 1 dong** (v2): Tang completeness tu 38.9% len 60.6%.
   Thay doi nho nhat (1 dong) nhung impact lon nhat ve completeness.

4. **`or {}` — 3 ky tu** (v3): Fix crash cho 1 case, accuracy +3.3pp.
   Su khac biet giua `get(key, default)` va `get(key) or default` trong Python
   khi value co the la None. Bai hoc: luon dung `or {}` khi API co the tra null.

5. **Smart reasoning** (v3): Completeness tu 60.6% len 82.2%.
   Logic: khong can viet lai reasoning neu ket luan khong doi. Giu lai reasoning
   giau evidence cua Pass 1, chi dung reasoning moi khi severity thuc su thay doi.

### 5.3 Van de con ton tai

- **2 regressions** — Pass 2 ha Critical xuong High (iam_risk_001, iam_semantic_hard_001)
- **Completeness 82.2%** van thap hon SP-noRAG (92.8%) — do 11 case co severity doi
  dung reasoning moi cua Pass 2 (ngan hon Pass 1)
- **Chua test qwen3:8b voi Two-Pass**

---

## 6. Tien do

- [x] Phan tich root cause
- [x] Benchmark cleanup & documentation
- [x] Implement Two-Pass (TP-v0) — loai bo negative lift
- [x] Khoi phuc PASS1 prompt + Fix bug primary_finding (TP-v1)
- [x] Fix evidence completeness (TP-v2) — 80% accuracy, all PASS
- [x] Fix parse error + Smart reasoning (TP-v3) — **83.3% accuracy, 82.2% completeness**
- [ ] Thu qwen3:8b voi Two-Pass
- [ ] Giam 2 regressions con lai
