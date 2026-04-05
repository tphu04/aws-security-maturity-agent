# Generation Benchmark Dashboard — Model × RAG Comparison

**Generated**: 2026-04-03T07:33:41.128051+00:00  
**Cases**: 30 per run | **Categories**: 4 (exact, paraphrase, semantic_hard, risk) | **Services**: 6  
**Models**: llama3.2:latest, qwen3:8b | **Ablation**: w/RAG vs no-RAG

## 1. Overall Metrics

| Metric | llama3.2 w/RAG | llama3.2 no-RAG | qwen3:8b w/RAG | qwen3:8b no-RAG |
|--------|:-:|:-:|:-:|:-:|
| JSON Parse Rate | 100.0% | 100.0% | 100.0% | 100.0% |
| Schema Compliance | 100.0% | 100.0% | 100.0% | 100.0% |
| Internal Consistency | 86.7% | 96.7% | 100.0% | 100.0% |
| Faithfulness Mean | 0.9333 | 0.9667 | 0.9667 | 0.9833 |
| Severity Accuracy | 66.7% | 76.7% | 56.7% | 50.0% |
| Severity QWK | 0.6838 | 0.9159 | 0.7595 | 0.7609 |
| Evidence Completeness | 78.3% | 92.8% | 90.6% | 93.3% |

## 2. RAG Lift Analysis

RAG Lift = metric(w/RAG) − metric(no-RAG). Positive = RAG helps.

| Metric | llama3.2 RAG Lift | qwen3:8b RAG Lift |
|--------|:-:|:-:|
| Severity Accuracy | -10.0% ↓ | +6.7% ↑ |
| Severity QWK | -23.2% ↓ | -0.1% → |
| Faithfulness | -3.3% ↓ | -1.7% ↓ |
| Evidence Completeness | -14.4% ↓ | -2.8% ↓ |
| Internal Consistency | -10.0% ↓ | +0.0% → |

> **Key finding**: llama3.2 shows **negative RAG lift** on accuracy (−10.0pp) — RAG context
> causes severity overestimation. qwen3:8b shows **positive RAG lift** (+6.7pp),
> demonstrating better utilization of RAG-provided severity guidance.

## 3. Release Criteria

| Criterion | Threshold | llama3.2 w/RAG | llama3.2 no-RAG | qwen3:8b w/RAG | qwen3:8b no-RAG |
|-----------|:-:|:-:|:-:|:-:|:-:|
| json_parse_rate_min | 1.00 | 1.0000 PASS | 1.0000 PASS | 1.0000 PASS | 1.0000 PASS |
| schema_compliance_rate_min | 0.95 | 1.0000 PASS | 1.0000 PASS | 1.0000 PASS | 1.0000 PASS |
| faithfulness_mean_min | 0.80 | 0.9333 PASS | 0.9667 PASS | 0.9667 PASS | 0.9833 PASS |
| severity_accuracy_min | 0.50 | 0.6667 PASS | 0.7667 PASS | 0.5667 PASS | 0.5000 PASS |
| severity_qwk_min | 0.45 | 0.6838 PASS | 0.9159 PASS | 0.7595 PASS | 0.7609 PASS |
| evidence_completeness_mean_min | 0.45 | 0.7833 PASS | 0.9278 PASS | 0.9056 PASS | 0.9333 PASS |
| **Verdict** | — | **PASS** | **PASS** | **PASS** | **PASS** |

## 4. Accuracy by Category

| Category | n | llama3.2 w/RAG | llama3.2 no-RAG | qwen3:8b w/RAG | qwen3:8b no-RAG |
|----------|:-:|:-:|:-:|:-:|:-:|
| exact | 8 | 62.5% | 100.0% | 50.0% | 50.0% |
| paraphrase | 8 | 37.5% | 37.5% | 75.0% | 75.0% |
| semantic_hard | 7 | 85.7% | 85.7% | 57.1% | 42.9% |
| risk | 7 | 85.7% | 85.7% | 42.9% | 28.6% |

### Faithfulness by Category

| Category | llama3.2 w/RAG | llama3.2 no-RAG | qwen3:8b w/RAG | qwen3:8b no-RAG |
|----------|:-:|:-:|:-:|:-:|
| exact | 0.94 | 1.00 | 0.94 | 1.00 |
| paraphrase | 0.94 | 1.00 | 1.00 | 1.00 |
| semantic_hard | 0.93 | 1.00 | 1.00 | 1.00 |
| risk | 0.93 | 0.86 | 0.93 | 0.93 |

### Completeness by Category

| Category | llama3.2 w/RAG | llama3.2 no-RAG | qwen3:8b w/RAG | qwen3:8b no-RAG |
|----------|:-:|:-:|:-:|:-:|
| exact | 50.0% | 79.2% | 83.3% | 93.8% |
| paraphrase | 93.8% | 100.0% | 93.8% | 93.8% |
| semantic_hard | 78.6% | 100.0% | 92.9% | 92.9% |
| risk | 92.9% | 92.9% | 92.9% | 92.9% |

## 5. Accuracy by Service

| Service | n | llama3.2 w/RAG | llama3.2 no-RAG | qwen3:8b w/RAG | qwen3:8b no-RAG |
|---------|:-:|:-:|:-:|:-:|:-:|
| s3 | 8 | 75.0% | 87.5% | 50.0% | 37.5% |
| iam | 8 | 62.5% | 62.5% | 37.5% | 50.0% |
| ec2 | 5 | 80.0% | 80.0% | 60.0% | 40.0% |
| rds | 4 | 50.0% | 50.0% | 100.0% | 100.0% |
| cloudtrail | 3 | 66.7% | 100.0% | 33.3% | 33.3% |
| kms | 2 | 50.0% | 100.0% | 100.0% | 50.0% |

## 6. Severity Prediction Distribution

Expected distribution: Critical=14, High=4, Medium=6, Low=6

| Severity | Expected | llama3.2 w/RAG | llama3.2 no-RAG | qwen3:8b w/RAG | qwen3:8b no-RAG |
|----------|:-:|:-:|:-:|:-:|:-:|
| Critical | 14 | 21 | 17 | 11 | 8 |
| High | 4 | 0 | 0 | 11 | 14 |
| Medium | 6 | 6 | 10 | 7 | 7 |
| Low | 6 | 3 | 3 | 1 | 1 |

## 7. Per-Case Severity Predictions

Cases marked with `*` indicate incorrect prediction vs expected.

| Case ID                        | Expected | llama3.2 w/RAG  | llama3.2 no-RAG | qwen3:8b w/RAG  | qwen3:8b no-RAG |
|--------------------------------|:--------:|:-:|:-:|:-:|:-:|
| risk_s3_exact_001              | Medium   | **Critical** ✗ | Medium | **Critical** ✗ | **High** ✗ |
| risk_s3_exact_002              | Medium   | Medium | Medium | **High** ✗ | **High** ✗ |
| risk_iam_exact_001             | Critical | Critical | Critical | Critical | Critical |
| risk_ec2_exact_001             | Critical | Critical | Critical | **High** ✗ | **High** ✗ |
| risk_rds_exact_001             | Critical | Critical | Critical | Critical | Critical |
| risk_cloudtrail_exact_001      | Medium   | **Critical** ✗ | Medium | **High** ✗ | **High** ✗ |
| risk_kms_exact_001             | Medium   | **Critical** ✗ | Medium | Medium | Medium |
| risk_iam_exact_002             | Critical | Critical | Critical | Critical | Critical |
| risk_s3_paraphrase_001         | Critical | Critical | Critical | Critical | Critical |
| risk_s3_paraphrase_002         | Medium   | Medium | Medium | **High** ✗ | **High** ✗ |
| risk_iam_paraphrase_001        | High     | **Critical** ✗ | **Critical** ✗ | High | High |
| risk_ec2_paraphrase_001        | High     | **Critical** ✗ | **Critical** ✗ | High | High |
| risk_rds_paraphrase_001        | High     | **Critical** ✗ | **Critical** ✗ | High | High |
| risk_cloudtrail_paraphrase_001 | Medium   | Medium | Medium | Medium | Medium |
| risk_s3_paraphrase_003         | Low      | **Medium** ✗ | **Medium** ✗ | Low | **Medium** ✗ |
| risk_iam_paraphrase_002        | Low      | **Medium** ✗ | **Medium** ✗ | **Medium** ✗ | Low |
| risk_s3_semantic_hard_001      | Critical | Critical | Critical | Critical | Critical |
| risk_iam_semantic_hard_001     | Critical | Critical | Critical | **High** ✗ | **High** ✗ |
| risk_ec2_semantic_hard_001     | Critical | Critical | Critical | **High** ✗ | **High** ✗ |
| risk_rds_semantic_hard_001     | Critical | Critical | Critical | Critical | Critical |
| risk_ec2_semantic_hard_002     | Critical | Critical | Critical | Critical | Critical |
| risk_iam_semantic_hard_002     | Low      | **Critical** ✗ | **Medium** ✗ | **Medium** ✗ | **Medium** ✗ |
| risk_kms_semantic_hard_001     | Critical | Critical | Critical | Critical | **High** ✗ |
| risk_s3_risk_001               | Critical | Critical | Critical | Critical | Critical |
| risk_iam_risk_001              | Critical | Critical | Critical | **High** ✗ | **High** ✗ |
| risk_ec2_risk_001              | Critical | Critical | Critical | Critical | **High** ✗ |
| risk_cloudtrail_risk_001       | Low      | Low | Low | **Medium** ✗ | **Medium** ✗ |
| risk_rds_risk_001              | High     | **Medium** ✗ | **Medium** ✗ | High | High |
| risk_iam_risk_002              | Low      | Low | Low | **Medium** ✗ | **Medium** ✗ |
| risk_s3_risk_002               | Low      | Low | Low | **Medium** ✗ | **Medium** ✗ |

## 8. Root Cause Analysis: RAG Lift

### llama3.2 — Negative RAG Lift (−10.0pp accuracy)

| Symptom | Detail |
|---------|--------|
| Over-prediction (sev > expected) | w/RAG: 9/30, no-RAG: 6/30 |
| Critical over-use | w/RAG: 21/30, no-RAG: 17/30 |
| Internal consistency | w/RAG: 86.7%, no-RAG: 96.7% |

**Root cause**: llama3.2 (3B params) struggles to integrate RAG severity guidance.
When RAG context supplies `official_severity`, the model over-anchors on worst-case
interpretations, inflating Critical predictions. Without RAG, it relies on its own
calibration which is paradoxically more accurate for this benchmark.

### qwen3:8b — Positive RAG Lift (+6.7pp accuracy)

RAG **fixed** 3 cases: risk_s3_paraphrase_003, risk_kms_semantic_hard_001, risk_ec2_risk_001

RAG **broke** 1 cases: risk_iam_paraphrase_002

qwen3:8b (8B params) has sufficient capacity to correctly interpret RAG severity
hints and adjust predictions accordingly, yielding net positive lift.

---
*Dashboard generated from benchmark run files on 2026-04-03T07:33:41.128051+00:00*  
*Source files: gen_benchmark_run_20260403_103853.json, gen_benchmark_run_20260403_103854.json, gen_benchmark_run_20260403_115443.json, gen_benchmark_run_20260403_122819.json*