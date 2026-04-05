# RAG Benchmark Dashboard

**Date**: 2026-04-02T10:47:15.500035+00:00  
**Tag**: phase6-final  
**Total cases**: 60 (checks: 41, maturity: 19)

## Release Status: PASS (13/13 criteria)

| Criterion | Threshold | Actual | Status |
|-----------|-----------|--------|--------|
| checks_top1_accuracy_min | 0.6 | 0.6341 | PASS |
| checks_top5_accuracy_min | 0.8 | 0.8049 | PASS |
| maturity_top1_accuracy_min | 0.6 | 0.8947 | PASS |
| maturity_top5_accuracy_min | 0.8 | 0.9474 | PASS |
| forbidden_capability_rate_max | 0.0 | 0.0 | PASS |
| empty_bundle_rate_max | 0.0 | 0.0 | PASS |
| service_precision_min | 0.85 | 0.902 | PASS |
| average_latency_ms_max | 5000 | 3997.34 | PASS |
| combined_mrr_min | 0.7 | 0.7728 | PASS |
| combined_ndcg5_min | 0.75 | 0.7924 | PASS |
| latency_p90_ms_max | 6000 | 4671.75 | PASS |
| robustness_gap_pp_max | 90 | 87.5 | PASS |
| confidence_ece_max | 0.2 | 0.1866 | PASS |

## Retrieval Quality

| Metric | Checks | Maturity | Combined |
|--------|--------|----------|----------|
| Hit Rate @1 | 26/41 (63.4%) | 17/19 (89.5%) | 43/60 (71.7%) |
| Hit Rate @5 | 33/41 (80.5%) | 18/19 (94.7%) | 51/60 (85.0%) |
| MRR | 0.7114 | 0.9053 | 0.7728 |
| NDCG@5 | 0.7355 | 0.9151 | 0.7924 |
| MAP@5 | 0.7114 | 0.9053 | 0.7728 |

## Robustness by Category

### Checks Retrieval

| Category | Total | Top-1 | Top-5 | MRR | NDCG@5 | Avg Latency |
|----------|-------|-------|-------|-----|--------|-------------|
| exact | 18 | 18 (100.0%) | 18 | 1.0000 | 1.0000 | 3736ms |
| paraphrase | 9 | 5 (55.6%) | 9 | 0.7593 | 0.8214 | 4193ms |
| risk | 6 | 2 (33.3%) | 4 | 0.4722 | 0.5218 | 3947ms |
| semantic_hard | 8 | 1 (12.5%) | 2 | 0.1875 | 0.2039 | 4403ms |

**Robustness Gap**: 87.5 pp (best: exact 1.00, worst: semantic_hard 0.12)

### Maturity Retrieval

| Category | Total | Top-1 | Top-5 | MRR | NDCG@5 | Avg Latency |
|----------|-------|-------|-------|-----|--------|-------------|
| exact | 7 | 7 (100.0%) | 7 | 1.0000 | 1.0000 | 2040ms |
| paraphrase | 6 | 6 (100.0%) | 6 | 1.0000 | 1.0000 | 5472ms |
| semantic_hard | 6 | 4 (66.7%) | 5 | 0.7000 | 0.7312 | 5243ms |

## Reranker Impact

| Suite | Metric | Before | After | Lift | Improved | Degraded | Unchanged |
|-------|--------|--------|-------|------|----------|----------|-----------|
| Checks | MRR | 0.2549 | 0.2724 | 0.0175 | 4 | 3 | 34 |
| Checks | NDCG@5 | 0.2888 | 0.2965 | 0.0076 | | | |
| Maturity | MRR | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 12 |

## Confidence Calibration

**Combined ECE**: 0.1133  
**Overall Calibrated**: No

### Combined

| Level | Count | Actual Accuracy | Expected | Calibrated |
|-------|-------|-----------------|----------|------------|
| high | 48 | 79.2% | >= 80% | No |
| medium | 1 | 100.0% | 50%-80% | No |
| low | 11 | 36.4% | < 50% | Yes |

### Per Route Type

| Route | ECE | High (count/acc) | Medium (count/acc) | Low (count/acc) | Calibrated |
|-------|-----|-------------------|--------------------|-----------------| -----------|
| check_search | 0.1866 | 36 / 72% | 0 / - | 5 / 0% | No |
| maturity_search | 0.2132 | 12 / 100% | 1 / 100% | 6 / 67% | No |

## Performance

| Metric | Checks | Maturity | Combined |
|--------|--------|----------|----------|
| Mean | 3997ms | 4135ms | 4041ms |
| P50 | 3946ms | 4565ms | 4029ms |
| P90 | 4672ms | 6594ms | 5724ms |
| P99 | 5912ms | 6926ms | 6926ms |

## Safety Metrics

| Metric | Value |
|--------|-------|
| Forbidden Capability Rate | 0.0% |
| Service Precision | 90.2% |

## By Service (Checks)

| Service | Total | Top-1 | Top-5 | Svc Correct |
|---------|-------|-------|-------|-------------|
| cloudtrail | 5 | 2 | 3 | 3/5 |
| ec2 | 9 | 4 | 7 | 8/9 |
| iam | 9 | 5 | 7 | 9/9 |
| kms | 3 | 3 | 3 | 3/3 |
| rds | 5 | 4 | 4 | 4/5 |
| s3 | 10 | 8 | 9 | 10/10 |

---
*Generated from `benchmark_latest.json` on 2026-04-02T10:47:15.500035+00:00*
