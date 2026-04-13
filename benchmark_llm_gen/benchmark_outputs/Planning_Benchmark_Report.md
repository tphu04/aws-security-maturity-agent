# Planning Agent - Benchmark Evaluation Report

**Ngay chay:** 2026-04-07  
**Version:** V2 (translate-first, topic-based classification)  
**Tong test cases:** 50  
**LLM Backend:** Ollama llama3.2 (localhost:11434)  
**RAG Backend:** localhost:8000 (hybrid retrieval)

---

## 1. Release Criteria

9 release criteria danh gia Planning Agent across 4 dimensions: Structure, Faithfulness, Correctness, Completeness.

| Criterion | Threshold | Truoc fix | Result | Sau fix | Result |
|-----------|-----------|-----------|--------|---------|--------|
| Valid Output Rate | >= 100% | 96.00% | FAIL | 100.00% | PASS |
| Grounded Reasoning Rate | >= 0.80 | 0.92 | PASS | 0.92 | PASS |
| Check Selection F1 | >= 0.60 | 0.775 | PASS | 0.794 | PASS |
| Service Accuracy | >= 90% | 100.0% | PASS | 92.9% | PASS |
| Planning Correctness | >= 0.65 | 0.843 | PASS | 0.834 | PASS |
| Action Type Accuracy | >= 85% | 80.0% | FAIL | 90.0% | PASS |
| Over-selection Rate | <= 0.40 | 0.290 | PASS | 0.275 | PASS |
| Under-selection Rate | <= 0.40 | 0.111 | PASS | 0.087 | PASS |
| Exact Match Rate | >= 20% | 33.3% | PASS | 34.8% | PASS |

**Verdict: 9/9 PASS** (truoc fix: 7/9 PASS)

---

## 2. Overall Metrics

### 2.1. Structure (Output Validity)

| Metric | Score |
|--------|-------|
| **Valid Output Rate** | 100.0% (50/50) |
| Schema Valid | 100.0% |
| Mutual Exclusivity | 100.0% |
| Reasoning Non-empty | 100.0% |
| Check ID Format Valid | 100.0% |

### 2.2. Faithfulness (Grounded Reasoning)

| Metric | Score |
|--------|-------|
| **Grounded Reasoning Rate** | 92.0% (46/50) |
| Hardcoded reasoning (auto 1.0) | 16 cases |
| Keyword-grounded | 30 cases |
| Ungrounded | 4 cases |

4 ungrounded cases: 2 ambiguous (khong co RAG evidence trong reasoning), 1 edge (empty request), 1 specific_intent (group misclass).

### 2.3. Correctness (Check Selection + Service)

| Metric | Score |
|--------|-------|
| **Check Selection F1** | 0.794 |
| Precision | 0.725 |
| Recall | 0.946 |
| **Over-selection Rate** | 0.275 (FP/predicted) |
| **Under-selection Rate** | 0.087 (FN/relevant) |
| **Exact Match Rate** | 34.8% |
| **Service Accuracy** | 92.9% (13/14 group cases) |
| **Planning Correctness** | 0.834 (0.7*F1 + 0.3*SA) |

Cases breakdown: 35 specific_checks, 14 group_scan, 1 error.

### 2.4. Completeness (Action Type)

| Metric | Score |
|--------|-------|
| **Action Type Accuracy** | 90.0% (45/50) |
| Correct specific_checks | 31/35 |
| Correct group_scan | 13/14 |
| Correct error | 1/1 |

---

## 3. Breakdown theo Input Type

| Input Type | Cases | F1 | Service Acc | Action Type | Faithfulness | Over-sel | Under-sel | EM |
|------------|-------|----|-------------|-------------|--------------|----------|-----------|-----|
| explicit_checks | 2 | 1.00 | - | 100% | 1.00 | 0.00 | 0.00 | 100% |
| group_request | 9 | - | 100% | 100% | 1.00 | - | - | - |
| specific_intent | 25 | 0.77 | 100% | 84% | 0.96 | 0.30 | 0.10 | 29% |
| ambiguous | 6 | - | - | 100% | 0.67 | - | - | - |
| multi_service | 4 | - | 0% | 100% | 1.00 | - | - | - |
| edge_case | 4 | - | - | 75% | 0.75 | - | - | - |

### Nhan xet

- **explicit_checks (2):** Perfect — FAST_TRACK path extract check IDs truc tiep.
- **group_request (9):** Perfect — topic-based classification hoat dong cho ca VI lan EN.
- **specific_intent (25):** F1=0.77 voi Recall=0.95 cao — RAG retrieval hieu qua. 4 cases bi misclass thanh group (thieu topic keyword trong enhanced query).
- **ambiguous (6):** Tat ca action type dung. Faithfulness=0.67 vi 2 cases khong co evidence trong reasoning.
- **multi_service (4):** Known limitation — single-query RAG chi cover 1 service. Service accuracy=0% vi agent chon dung service nhung khong match "multi" expected.
- **edge_case (4):** 3/4 dung. `plan_edge_002` (off-topic request) van tra specific_checks thay vi error.

---

## 4. Breakdown theo AWS Service

| Service | Cases | F1 Mean | Nhan xet |
|---------|-------|---------|----------|
| s3 | 6 | 0.964 | Rat tot — RAG co nhieu S3 checks |
| iam | 7 | 0.767 | Kha — over-selection do nhieu checks lien quan |
| ec2 | 6 | 1.000 | Perfect |
| rds | 4 | 0.667 | Trung binh — RAG miss 1 so transport encryption checks |
| kms | 4 | 0.700 | Kha — over-selection voi kms_cmk_are_used |
| vpc | 2 | 1.000 | Perfect |
| lambda | 2 | - | Chi group_scan cases |
| eks | 3 | 1.000 | Perfect |
| cloudtrail | 4 | 1.000 | Perfect |
| guardduty | 1 | 0.500 | Over-select — RAG tra 2 checks, expected chi 1 |
| secretsmanager | 2 | 0.667 | Kha |
| elbv2 | 1 | 0.000 | Fail — RAG khong tim duoc elbv2_ssl_listeners |
| cloudwatch | 2 | 0.667 | Kha |

---

## 5. Classification Path Distribution

Agent su dung 3 paths voi do phuc tap tang dan:

| Path | Cases | Mean Latency | Median | Max | Mo ta |
|------|-------|-------------|--------|-----|-------|
| FAST_TRACK | 2 | 1ms | 1ms | 1ms | Regex extract check IDs, no I/O |
| GROUP_SCAN | 14 | 589ms | 0ms | 8236ms | Topic-based classification |
| RETRIEVAL | 33 | 5909ms | 4874ms | 31252ms | RAG + scoring + optional LLM |
| ERROR | 1 | 0ms | 0ms | 0ms | Empty input validation |

- **Latency trung binh toan bo:** 4065ms
- **LLM calls:** Chi khi ConfidenceGate fail (low confidence) — ~20% cases
- GROUP_SCAN median=0ms vi hau het resolve o classification step (truoc RAG). 1 case co latency cao do RAG goi truoc khi group detect.

---

## 6. Comparison: Truoc va Sau Fix

### 6.1. Thay doi kiến trúc

| Aspect | Truoc | Sau |
|--------|-------|-----|
| Classification order | Classify (raw) -> Translate -> Retrieve | Translate -> Classify (enhanced) -> Retrieve |
| Group detection | Regex tieng Anh (`scan all`, `full scan`) | Topic absence detection (language-independent) |
| LLM output constraint | `sanitize_check_id()` only | Intersect voi candidate pool |
| Metric error handling | `error` type khong duoc handle | `error` type duoc evaluate dung |

### 6.2. Impact

| Metric | Truoc | Sau | Delta |
|--------|-------|-----|-------|
| Valid Output Rate | 96.0% | 100.0% | +4.0pp |
| Action Type Accuracy | 80.0% | 90.0% | +10.0pp |
| Group request action | 11.1% (1/9) | 100% (9/9) | +88.9pp |
| Check Selection F1 | 0.775 | 0.794 | +0.019 |
| Over-selection Rate | 0.290 | 0.275 | -0.015 |
| Under-selection Rate | 0.111 | 0.087 | -0.024 |

---

## 7. Known Limitations & Remaining Issues

### 7.1. Specific Intent misclassified as Group (4 cases)

4 `specific_intent` cases bi classify thanh `group_scan` vi query sau translate khong chua topic keyword:

| Case | Request | Enhanced Query | Missing Topic |
|------|---------|---------------|---------------|
| plan_intent_008 | "security group nao dang mo port SSH" | "ec2 security group" | "security group" tokenize thanh 2 generic words |
| plan_intent_015 | "log files protected from tampering" | "cloudtrail ..." | "tampering" chua co trong topic keywords |
| plan_intent_019 | "Lambda function bi public truy cap" | "lambda function public access" | "function" bi loai vi la service keyword |
| plan_intent_020 | "cum EKS co endpoint mo ra ngoai" | "eks cluster ..." | "cluster" map sang eks, bi loai |

**Root cause:** Multi-word tokenization va service-keyword overlap. Cai thien bang cach enriching `_KEYWORD_SERVICE_MAP` voi concepts moi (khong phai hardcode per-case).

### 7.2. Multi-service limitation

4 `multi_service` cases (known limitation): Agent chi thuc hien 1 RAG query nen chi cover 1 service. Can multi-query pipeline de ho tro.

### 7.3. Off-topic detection

`plan_edge_002` ("xin chao, hom nay thoi tiet dep qua") — RAG van tra results vi query "xin nay" match noise. Can minimum-relevance threshold o retrieval level.

### 7.4. elbv2 coverage gap

`plan_intent_024` (SSL policy check) — F1=0.0. RAG khong tim duoc `elbv2_ssl_listeners`. Co the do index thieu coverage cho elbv2 checks.

---

## 8. Tong ket

| Dimension | Metric | Score |
|-----------|--------|-------|
| Structure | Valid Output Rate | 100.0% |
| Faithfulness | Grounded Reasoning Rate | 92.0% |
| Correctness | F1 / Precision / Recall | 0.794 / 0.725 / 0.946 |
| Correctness | Service Accuracy | 92.9% |
| Correctness | Planning Correctness | 0.834 |
| Completeness | Action Type Accuracy | 90.0% |
| Selection Quality | Over / Under-selection | 0.275 / 0.087 |
| Selection Quality | Exact Match Rate | 34.8% |
| Latency | Mean / Median | 4065ms / 3824ms |
| Release Criteria | Pass rate | **9/9 (100%)** |
