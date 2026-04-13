# RAG Evaluation

## Dataset

Dataset gồm 60 test cases viết tay, lưu trong [benchmark_cases.json](RAG/data/benchmarks/benchmark_cases.json): 41 cases cho check_search (tìm trong 577 Prowler security checks) và 19 cases cho maturity_search (tìm trong 78 maturity capabilities), phủ 6 AWS services: S3, IAM, EC2, RDS, CloudTrail, KMS.

Mỗi test case gồm: `query` là câu truy vấn, `expected_doc_id` là ground truth chính, `all_relevant_doc_ids` là tất cả documents liên quan kèm `relevance_grades` (1–3, 3 là liên quan nhất), và `forbidden_capability_ids` là documents tuyệt đối không được trả về. Ví dụ một case:

```json
{
  "case_id": "s3_exact_1",
  "category": "exact",
  "service": "s3",
  "query": "s3_bucket_level_public_access_block",
  "expected_doc_id": "check:s3_bucket_level_public_access_block",
  "all_relevant_doc_ids": [
    "check:s3_bucket_level_public_access_block",
    "check:s3_account_level_public_access_blocks",
    "check:s3_access_point_public_access_block"
  ],
  "relevance_grades": {
    "check:s3_bucket_level_public_access_block": 3,
    "check:s3_account_level_public_access_blocks": 2,
    "check:s3_access_point_public_access_block": 2
  },
  "forbidden_capability_ids": ["generative_ai_data_protection_with_amazon_bedrock"]
}
```

Các cases chia theo 4 mức độ khó tăng dần:

- **exact** (25 cases) — query chính là tên check/capability, ví dụ `"s3_bucket_level_public_access_block"`. Đây là cách agents thực tế gọi RAG nhiều nhất.
- **paraphrase** (15 cases) — diễn đạt lại bằng ngôn ngữ tự nhiên, ví dụ `"check if S3 bucket blocks public access"`.
- **risk** (6 cases) — mô tả kịch bản rủi ro, ví dụ `"s3 bucket encryption not enabled risk"`.
- **semantic_hard** (14 cases) — trừu tượng, không có keyword trùng với document, ví dụ `"protect most privileged credentials"` kỳ vọng trả về `iam_avoid_root_usage` nhưng hai câu không có từ chung nào.

Mục đích chia 4 mức: đánh giá hệ thống bắt đầu "vỡ" ở đâu khi query khó dần.

---

## Metrics

Toàn bộ implementation nằm trong [metrics.py](RAG/app/evaluation/metrics.py).

**Hit Rate @k** — trong top-k kết quả có chứa đúng document không? Trả về 1 hoặc 0. Ví dụ kết quả trả về [A, B, C, D, E], expected là C thì Hit@3 = 1, Hit@1 = 0. Đây là metric "trần" — nếu document không lọt vào top-k thì reranker hay agent cũng không cứu được.

**MRR (Mean Reciprocal Rank)** — document đúng nằm ở vị trí nào? RR = 1/rank của relevant document đầu tiên: vị trí 1 → RR=1.0, vị trí 2 → 0.5, vị trí 3 → 0.33, không tìm thấy → 0. MRR là trung bình RR trên tất cả queries.

**NDCG@5 (Normalized Discounted Cumulative Gain)** — chất lượng ranking so với ranking lý tưởng. DCG = tổng(rel[i] / log2(i+2)), chia cho IDCG của perfect ranking. Vị trí thấp bị phạt nặng theo hàm log — document đúng ở vị trí 5 đóng góp ít hơn nhiều so với vị trí 1.

**MAP@5 (Mean Average Precision)** — precision trung bình tại mỗi vị trí có relevant document. AP = (1/R) × tổng(Precision@i × rel(i)). Đánh giá hệ thống trả về relevant documents sớm và đầy đủ cỡ nào.

**ECE (Expected Calibration Error)** — confidence mà RAG gán có khớp với độ chính xác thực tế không? Chia 3 bin: High (kỳ vọng accuracy ≥ 80%), Medium (50–80%), Low (< 50%). ECE = trung bình có trọng số của |actual_accuracy − midpoint|. ECE càng thấp càng tốt. Quan trọng vì agents dựa vào confidence để quyết định — RAG nói "high" mà sai nhiều thì agent bị đánh lừa. Chi tiết tính confidence trong [confidence.py](RAG/app/retrieval/confidence.py).

**Robustness Gap** — chênh lệch Top-1 accuracy giữa category tốt nhất và yếu nhất (percentage points). Gap lớn nghĩa là hệ thống không ổn định.

---

## Benchmark Flow

Script chạy benchmark: [run_benchmark.py](RAG/scripts/run_benchmark.py) gọi xuống [benchmark_retrieval.py](RAG/data/benchmarks/benchmark_retrieval.py).

Quy trình: load 60 test cases → khởi động RAG server → gửi từng query đến API (top_k=5, debug=True) → nhận top-5 results → so sánh với ground truth → tính per-query metrics (RR, NDCG@5, AP@5, hit@1/3/5) → aggregate theo category và service → kiểm tra 13 release criteria. Tất cả 13 cái phải PASS mới được deploy. Criteria nằm trong [release_criteria.json](RAG/data/benchmarks/release_criteria.json):

```json
{
  "checks_top1_accuracy_min": 0.60,
  "checks_top5_accuracy_min": 0.80,
  "maturity_top1_accuracy_min": 0.60,
  "maturity_top5_accuracy_min": 0.80,
  "combined_mrr_min": 0.70,
  "combined_ndcg5_min": 0.75,
  "forbidden_capability_rate_max": 0.0,
  "empty_bundle_rate_max": 0.0,
  "service_precision_min": 0.85,
  "average_latency_ms_max": 5000,
  "latency_p90_ms_max": 6000,
  "robustness_gap_pp_max": 90,
  "confidence_ece_max": 0.20
}
```

---

## Kết quả

Kết quả đầy đủ trong [benchmark_latest.json](RAG/data/benchmarks/benchmark_outputs/benchmark_latest.json), báo cáo chi tiết ở [RAG_Evaluation_Report.md](RAG/Note/RAG_Evaluation_Report.md).

### Release Criteria: PASS 13/13

```
criterion                       threshold    actual     passed
─────────────────────────────────────────────────────────────
checks_top1_accuracy_min        ≥ 0.60       0.6341     ✓
checks_top5_accuracy_min        ≥ 0.80       0.8049     ✓
maturity_top1_accuracy_min      ≥ 0.60       0.8947     ✓
maturity_top5_accuracy_min      ≥ 0.80       0.9474     ✓
combined_mrr_min                ≥ 0.70       0.7736     ✓
combined_ndcg5_min              ≥ 0.75       0.7931     ✓
forbidden_capability_rate_max   ≤ 0.00       0.0000     ✓
empty_bundle_rate_max           ≤ 0.00       0.0000     ✓
service_precision_min           ≥ 0.85       0.9020     ✓
average_latency_ms_max          ≤ 5000       3384.91    ✓
latency_p90_ms_max              ≤ 6000       3865.40    ✓
robustness_gap_pp_max           ≤ 90         87.50      ✓
confidence_ece_max              ≤ 0.20       0.0825     ✓
```

### Tổng quan

```
                 Total   Top-1         Top-5         MRR      NDCG@5   MAP@5
Combined          60     43 (71.7%)    51 (85.0%)    0.7736   0.7931   0.7736
Checks            41     26 (63.4%)    33 (80.5%)    0.7114   0.7355   0.7114
Maturity          19     17 (89.5%)    18 (94.7%)    0.9081   0.9170   0.9081
```

### Theo category — Checks endpoint

```
Category        Cases   Top-1          Top-3          Top-5          MRR      NDCG@5
exact            18     18 (100.0%)    18 (100.0%)    18 (100.0%)    1.0000   1.0000
paraphrase        9      5 ( 55.6%)     9 (100.0%)     9 (100.0%)    0.7593   0.8214
risk              6      2 ( 33.3%)     4 ( 66.7%)     4 ( 66.7%)    0.4722   0.5218
semantic_hard     8      1 ( 12.5%)     2 ( 25.0%)     2 ( 25.0%)    0.1875   0.2039
```

### Theo category — Maturity endpoint

```
Category        Cases   Top-1          Top-5          MRR      NDCG@5
exact             7      7 (100.0%)     7 (100.0%)    1.0000   1.0000
paraphrase        6      6 (100.0%)     6 (100.0%)    1.0000   1.0000
semantic_hard     6      4 ( 66.7%)     5 ( 83.3%)    0.7083   0.7390
```

Maturity tốt hơn checks nhiều vì corpus nhỏ hơn (78 vs 577 docs), BM25 ít bị nhiễu.

### Theo service — Checks endpoint

```
Service       Cases   Top-1        Top-5        Service Correct
S3             10      8 (80%)      9 (90%)     10/10 (100%)
IAM             9      5 (56%)      7 (78%)      9/9  (100%)
EC2             9      4 (44%)      7 (78%)      8/9  ( 89%)
RDS             5      4 (80%)      4 (80%)      4/5  ( 80%)
CloudTrail      5      2 (40%)      3 (60%)      3/5  ( 60%)
KMS             3      3 (100%)     3 (100%)     3/3  (100%)
```

CloudTrail yếu nhất vì các query như "cloudtrail logs in s3 bucket" bị BM25 kéo sang S3 checks — keyword "s3 bucket" mạnh hơn "cloudtrail".

### Confidence Calibration

```
ECE = 0.0825 (target ≤ 0.20) — PASS

Level      Cases   Actual Accuracy   Expected Range   Calibrated?
high        33      93.9%            ≥ 80%            Yes
medium      16      50.0%            50–80%           Yes
low         11      36.4%            < 50%            Yes

Overall calibrated: True
```

Agents có thể tin tưởng confidence level: RAG nói "high" thì đúng ~94%, nói "low" thì chỉ đúng ~36%.

### Latency

```
Mean:    3406.64 ms
P50:     3252.11 ms
P90:     3865.40 ms  (target ≤ 6000ms)
P99:     9053.77 ms  (cold start query đầu tiên)
```

### Reranker Lift (Checks)

```
              Before     After      Lift
MRR           0.2549     0.2724     +0.0175
NDCG@5        0.2888     0.2965     +0.0076

Cases improved:   4/41
Cases degraded:   3/41
Cases unchanged: 34/41
```

Cross-encoder (ms-marco) có lift dương nhưng nhỏ. Model train trên web search, không tối ưu cho AWS security domain.

### Robustness

```
Gap: 87.5pp (target ≤ 90pp) — PASS
Best:  exact        = 100.0%
Worst: semantic_hard =  12.5%
```

### Failure Analysis — 8 cases không hit Top-5 (checks)

```
case_id                    category        query (rút gọn)                              expected_doc_id                          root cause
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
s3_risk_2                  risk            "s3 bucket encryption not enabled risk"       s3_bucket_default_encryption              RRF dilution
iam_semantic_hard_1        semantic_hard   "protect most privileged credentials"         iam_avoid_root_usage                      Recall failure
iam_semantic_hard_2        semantic_hard   "enforce strong password requirements"        iam_password_policy_minimum_length_14      Reranker mis-ranking
ec2_semantic_hard_1        semantic_hard   "prevent credential theft via metadata"       ec2_launch_template_imdsv2_required        Recall failure
ec2_semantic_hard_2        semantic_hard   "close dangerous admin ports"                 ec2_sg_allow_ingress_all_ports              Vector miss
rds_semantic_hard_1        semantic_hard   "databases isolated from internet"            rds_instance_no_public_access               Recall failure
cloudtrail_risk_1          risk            "cloudtrail logs in public s3 bucket"         cloudtrail_logs_s3_bucket_not_public        Cross-service confusion
cloudtrail_semantic_hard_1 semantic_hard   "track api activity across cloud"             cloudtrail_multi_region_enabled             Recall failure
```

Root cause phân loại:

```
Recall failure          4 cases   Document không chứa semantic concepts tương ứng query
Reranker mis-ranking    2 cases   Cross-encoder cho score sai
Cross-service confusion 1 case    BM25 match sang service khác vì keyword mạnh hơn
RRF dilution            1 case    Document bị đẩy xuống khi merge 2 sources
```

4/8 failures là do nội dung document thiếu concept — đây là vấn đề data, không phải algorithm. Ví dụ "credential theft via metadata" kỳ vọng "imdsv2 required" — đúng ý nghĩa nhưng không có từ chung nào. Không model nào bridge được gap này mà không enrichment nội dung document.
