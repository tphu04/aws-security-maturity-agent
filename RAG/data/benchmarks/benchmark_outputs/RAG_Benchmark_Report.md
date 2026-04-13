# RAG System - Benchmark Evaluation Report

**Ngày chạy:** 2026-04-07  
**Tag:** final-report  
**Tổng test cases:** 72 retrieval + 48 context = 120 cases  
**Server:** localhost:8000 (CPU-only)

---

## 1. Retrieval Quality (Tier 1)

Đánh giá khả năng truy xuất đúng tài liệu từ 72 benchmark cases (63 check + 9 maturity), dùng 13 release criteria.

### 1.1. Tổng hợp Retrieval Metrics

| Metric | Checks (63 cases) | Maturity (9 cases) | Combined (72 cases) |
|--------|-------------------|---------------------|----------------------|
| **Top-1 Accuracy** | 76.2% | 77.8% | 76.4% |
| **Top-5 Accuracy** | 88.9% | 100.0% | 90.3% |
| **MRR** | 0.8066 | 0.8426 | 0.8111 |
| **NDCG@5** | 0.8270 | 0.8812 | 0.8338 |
| **MAP@5** | 0.8066 | 0.8426 | 0.8111 |

### 1.2. Release Criteria

| Criterion | Threshold | Actual | Result |
|-----------|-----------|--------|--------|
| Checks Top-1 Accuracy | >= 60% | 76.2% | PASS |
| Checks Top-5 Accuracy | >= 80% | 88.9% | PASS |
| Maturity Top-1 Accuracy | >= 60% | 77.8% | PASS |
| Maturity Top-5 Accuracy | >= 80% | 100.0% | PASS |
| Combined MRR | >= 0.70 | 0.8111 | PASS |
| Combined NDCG@5 | >= 0.75 | 0.8338 | PASS |
| Service Precision | >= 85% | 100.0% | PASS |
| Forbidden Capability Rate | = 0% | 0.0% | PASS |
| Average Latency | <= 5000ms | 3753ms | PASS |
| Latency P90 | <= 6000ms | 6998ms | FAIL |
| Robustness Gap | <= 90pp | 100.0pp | FAIL |
| Confidence ECE | <= 0.20 | 0.20 | PASS |

**Verdict: 11/13 PASS, 2 FAIL** (latency P90 vượt ngưỡng do CPU-only; robustness gap do negative cases luôn 0%).

### 1.3. Retrieval Accuracy theo Query Category

| Category | Cases | Top-1 | Top-5 | MRR |
|----------|-------|-------|-------|-----|
| check_id_exact | 25 | 100.0% | 100.0% | 1.0000 |
| check_id_partial | 7 | 85.7% | 100.0% | 0.9286 |
| agent_query | 18 | 61.1% | 83.3% | 0.6898 |
| user_query_vi | 10 | 60.0% | 90.0% | 0.6900 |
| negative | 3 | 0.0% | 0.0% | 0.0000 |
| capability_exact | 3 | 100.0% | 100.0% | 1.0000 |
| capability_query | 3 | 100.0% | 100.0% | 1.0000 |
| capability_vi | 3 | 33.3% | 100.0% | 0.5278 |

### 1.4. Reranker Lift

| Metric | Before Reranker | After Reranker | Lift |
|--------|-----------------|----------------|------|
| MRR (checks) | 0.3822 | 0.4303 | +0.0481 |
| NDCG (checks) | 0.4158 | 0.4516 | +0.0358 |
| Cases improved / degraded | — | — | 7 / 2 |

---

## 2. Ablation Study: BM25 vs Vector vs Hybrid

So sánh 3 retrieval mode trên cùng 69 cases (loại 3 negative).

### 2.1. Overall Comparison

| Metric | BM25-only | Vector-only | Hybrid |
|--------|-----------|-------------|--------|
| **Top-1 Accuracy** | 71.0% | 71.0% | **79.7%** |
| **Top-5 Accuracy** | 91.3% | 85.5% | **94.2%** |
| **MRR** | 0.7865 | 0.7674 | **0.8464** |
| **Avg Latency** | 2812ms | 2869ms | 3573ms |

### 2.2. Ablation theo Query Category

| Category | BM25 Top-1 | Vector Top-1 | Hybrid Top-1 | Best Mode |
|----------|-----------|-------------|-------------|-----------|
| check_id_exact (25) | 100.0% | 84.0% | 100.0% | BM25 = Hybrid |
| check_id_partial (7) | 57.1% | 71.4% | **85.7%** | Hybrid |
| agent_query (18) | 55.6% | **66.7%** | 61.1% | Vector |
| user_query_vi (10) | 30.0% | 40.0% | **60.0%** | Hybrid |
| capability_exact (3) | 100.0% | 100.0% | 100.0% | Tie |
| capability_query (3) | 66.7% | 66.7% | **100.0%** | Hybrid |
| capability_vi (3) | 66.7% | 66.7% | 33.3% | BM25 = Vector |

---

## 3. Context Quality (Tier 2 + Tier 3)

Đánh giá chất lượng context bundle được build cho 3 downstream agents, 48 test cases.

### 3.1. Pass Rate theo Consumer Agent

| Consumer | Tier | Cases | Passed | Pass Rate |
|----------|------|-------|--------|-----------|
| Risk Evaluation | Tier 2 | 22 | 14 | 63.6% |
| Planning Agent | Tier 2 | 11 | 11 | 100.0% |
| Report Agent | Tier 3 | 15 | 14 | 93.3% |
| **Combined** | **2+3** | **48** | **39** | **81.3%** |

### 3.2. Field Accuracy chi tiết (Tier 2)

| Field | Risk Agent | Planning Agent |
|-------|------------|----------------|
| bundle_exists | 22/22 (100%) | 11/11 (100%) |
| severity_correct | 19/22 (86.4%) | — |
| title_contains | 22/22 (100%) | — |
| has_mapping | 21/22 (95.5%) | — |
| mapping_capability_match | 14/22 (63.6%) | — |
| findings_count | — | 11/11 (100%) |
| findings_have_severity | — | 11/11 (100%) |
| service_present | — | 11/11 (100%) |

### 3.3. Context Completeness (Tier 3 - Report Agent)

| Field | Passed / Tested | Rate |
|-------|-----------------|------|
| bundle_exists | 15/15 | 100% |
| key_findings_count | 14/15 | 93.3% |
| has_risk_summary | 15/15 | 100% |
| control_themes_count | 7/7 | 100% |
| practices_count | 3/3 | 100% |
| has_topics | 5/5 | 100% |

---

## 4. Tổng kết

| Dimension | Metric | Score |
|-----------|--------|-------|
| Retrieval Accuracy | Combined Top-1 / Top-5 | 76.4% / 90.3% |
| Retrieval Quality | MRR / NDCG@5 | 0.811 / 0.834 |
| Hybrid Advantage | MRR gain vs best single-mode | +0.060 (vs BM25) |
| Context - Risk Agent | Field accuracy pass rate | 63.6% |
| Context - Planning Agent | Field accuracy pass rate | 100.0% |
| Context - Report Agent | Completeness pass rate | 93.3% |
| Safety | Forbidden capability rate | 0.0% |
| Safety | Service precision | 100.0% |
| Latency | Average / P90 | 3753ms / 6998ms |
| Release Criteria | Pass rate | 11/13 (84.6%) |
