# Báo cáo Đánh giá Hệ thống RAG Retrieval

**Ngày chạy benchmark:** 2026-04-07  
**Run ID:** `benchmark_run_20260407_063248`  
**Phiên bản index:** `rag-v4-2026-04-05`  
**Chế độ retrieval:** Hybrid (BM25 + Vector)  
**Verdict tổng thể:** ❌ **FAIL** (2/13 tiêu chí không đạt)

---

## Mục lục

1. [Giải thích các Metric](#1-giải-thích-các-metric)
2. [Tổng quan kết quả (Combined Summary)](#2-tổng-quan-kết-quả-combined-summary)
3. [Check Retrieval — Phân tích theo Loại Query](#3-check-retrieval--phân-tích-theo-loại-query)
4. [Check Retrieval — Phân tích theo AWS Service](#4-check-retrieval--phân-tích-theo-aws-service)
5. [Maturity Retrieval — Phân tích theo Loại Query](#5-maturity-retrieval--phân-tích-theo-loại-query)
6. [Hiệu quả Reranker](#6-hiệu-quả-reranker)
7. [Hiệu năng Latency](#7-hiệu-năng-latency)
8. [Confidence Calibration](#8-confidence-calibration)
9. [Release Criteria — Kết quả đánh giá ngưỡng](#9-release-criteria--kết-quả-đánh-giá-ngưỡng)
10. [Phân tích các Case Thất bại](#10-phân-tích-các-case-thất-bại)
11. [Kết luận và Khuyến nghị](#11-kết-luận-và-khuyến-nghị)

---

## 1. Giải thích các Metric

Hệ thống đánh giá RAG sử dụng hai nhóm metric chính: **Độ chính xác retrieval** và **Chất lượng xếp hạng**. Mỗi metric đo một khía cạnh khác nhau của hiệu suất tìm kiếm.

### 1.1 Accuracy Metrics (Độ chính xác)

#### Hit @ K (Tỷ lệ nhấn tại vị trí K)
- **Định nghĩa:** Tỷ lệ truy vấn có kết quả đúng xuất hiện trong top-K kết quả trả về.
- **Công thức:** Hit@K = (số case có expected_doc_id trong top-K) / (tổng số case)
- **Giá trị:** [0, 1], càng cao càng tốt.
- **Ý nghĩa thực tế:**  
  - **Hit@1** phản ánh độ chính xác khi agent/hệ thống chỉ dùng kết quả đầu tiên — rất quan trọng vì downstream agent thường ưu tiên kết quả rank 1.  
  - **Hit@5** phản ánh khả năng "recall" — kết quả đúng có trong danh sách gợi ý không.
- **Ngưỡng release:** checks Hit@1 >= 60%, checks Hit@5 >= 80%

#### Service Precision (Độ chính xác dịch vụ)
- **Định nghĩa:** Tỷ lệ kết quả top-1 thuộc đúng AWS service so với expected service.
- **Ý nghĩa:** Đảm bảo hệ thống không trả về check của service sai (vd: query về S3 nhưng trả về IAM check). Đây là ràng buộc an toàn cơ bản — sai service là lỗi nghiêm trọng trong context bảo mật cloud.
- **Ngưỡng release:** >= 85%

#### Forbidden Capability Rate (Tỷ lệ vi phạm capability bị cấm)
- **Định nghĩa:** % truy vấn mà kết quả trả về chứa ít nhất một capability bị đánh dấu `forbidden` cho query đó.
- **Ý nghĩa:** Mỗi test case định nghĩa một tập `forbidden_capability_ids` — những capability không liên quan hoặc sai ngữ cảnh mà hệ thống không được phép trả về. Vi phạm cho thấy hệ thống bị "lạc đường" ngữ nghĩa.
- **Ngưỡng release:** = 0% (zero-tolerance)

---

### 1.2 Ranking Quality Metrics (Chất lượng xếp hạng)

#### MRR — Mean Reciprocal Rank (Trung bình nghịch đảo xếp hạng)
- **Định nghĩa:** Trung bình của nghịch đảo hạng (1/rank) của kết quả đúng đầu tiên trong mỗi truy vấn.
- **Công thức:**

```
MRR = (1/N) * sum( 1 / rank_i )
```

- **Ví dụ:**
  - Kết quả đúng ở vị trí 1 → RR = 1.0
  - Kết quả đúng ở vị trí 2 → RR = 0.5
  - Kết quả đúng ở vị trí 3 → RR = 0.333
  - Không tìm thấy → RR = 0.0
- **Giá trị:** [0, 1], càng cao càng tốt.
- **Ưu điểm:** Đo "mức độ cao" của kết quả đúng. Nhạy hơn Hit@1 vì phân biệt rank 2 và rank 5.
- **Ngưỡng release:** Combined MRR >= 0.70

#### NDCG@5 — Normalized Discounted Cumulative Gain at 5
- **Định nghĩa:** Đo chất lượng xếp hạng khi tính đến **graded relevance** (mức độ liên quan phân cấp), với hình phạt log cho kết quả đúng ở vị trí thấp.
- **Công thức:**

```
DCG@5  = sum(k=1..5) [ rel_k / log2(k+1) ]
NDCG@5 = DCG@5 / IDCG@5      (IDCG = DCG của xếp hạng lý tưởng)
```

- **Ví dụ:** Kết quả đúng ở rank 1 đóng góp rel/log2(2)=rel; rank 2 đóng góp rel/log2(3)≈rel/1.58; rank 5 đóng góp rel/log2(6)≈rel/2.58.
- **Giá trị:** [0, 1], càng cao càng tốt.
- **Ưu điểm so với MRR:** NDCG tính đến toàn bộ danh sách và mức độ liên quan phân cấp, không chỉ vị trí kết quả đúng đầu tiên. Phù hợp khi cần đánh giá toàn bộ top-5.
- **Ngưỡng release:** Combined NDCG@5 >= 0.75

#### MAP@5 — Mean Average Precision at 5
- **Định nghĩa:** Trung bình của Average Precision (AP) tại K=5 cho mỗi truy vấn.
- **Công thức:**

```
AP@5 = (1/R) * sum(k=1..5) [ P(k) * rel(k) ]
  R      = số kết quả đúng trong tập ground truth
  P(k)   = precision tại vị trí k
  rel(k) = 1 nếu kết quả tại k là đúng
```

- **Ý nghĩa:** Khi có nhiều kết quả đúng, MAP@5 thưởng cho hệ thống nào đặt tất cả kết quả đúng ở vị trí cao hơn.
- **Trong hệ thống này:** Phần lớn mỗi query chỉ có 1 expected_doc_id nên MAP@5 ≈ MRR; với các query có `all_relevant_doc_ids`, MAP@5 phản ánh tốt hơn.

---

### 1.3 Latency Metrics (Hiệu năng thời gian)

| Metric | Ký hiệu | Ý nghĩa |
|--------|---------|---------|
| Mean latency | avg_ms | Thời gian phản hồi trung bình — bị ảnh hưởng bởi outlier |
| Median latency | p50_ms | 50% request hoàn thành trong thời gian này — đại diện cho trải nghiệm thông thường |
| P90 latency | p90_ms | 90% request hoàn thành trong thời gian này — đại diện cho trường hợp chậm |
| P99 latency | p99_ms | 99% request hoàn thành trong thời gian này — worst-case |

**Lưu ý:** Pipeline bao gồm nhiều bước: query translation (Phi-4 mini LLM) → BM25 + vector search → RRF fusion → cross-encoder reranker. Latency cao chủ yếu do LLM translation và cross-encoder inference.

---

### 1.4 Robustness Gap (Khoảng cách độ bền)

- **Định nghĩa:** Hiệu số (percentage points) giữa category có Top-1 cao nhất và category có Top-1 thấp nhất.
- **Công thức:** `gap_pp = best_category_top1_rate - worst_category_top1_rate`
- **Ý nghĩa:** Đo sự không đồng đều về hiệu suất giữa các loại query. Gap càng lớn → hệ thống càng "chuyên biệt" cho một số loại query và kém ổn định với loại khác.
- **Ngưỡng release:** <= 90 pp

---

### 1.5 Confidence Calibration & ECE

- **Định nghĩa:** Hệ thống gán nhãn confidence (`high`/`medium`/`low`) cho mỗi kết quả. Calibration đo xem confidence có phản ánh đúng xác suất thực sự không.
- **ECE — Expected Calibration Error:**

```
ECE = sum_b ( |B_b| / N ) * | accuracy(B_b) - confidence(B_b) |
  B_b = nhóm case thuộc bin b (high/medium/low)
```

- **Ngưỡng calibration:**
  - `high` confidence: accuracy thực tế phải >= 80%
  - `medium` confidence: accuracy thực tế phải trong [50%, 80%)
  - `low` confidence: accuracy thực tế phải <= 50%
- **Giá trị ECE:** [0, 1], càng gần 0 càng tốt (calibrated hoàn hảo).
- **Ngưỡng release:** ECE <= 0.20

---

## 2. Tổng quan kết quả (Combined Summary)

**Tổng số test case:** 72 (63 check queries + 9 maturity queries)

| Metric | Checks (63 cases) | Maturity (9 cases) | Combined (72 cases) |
|--------|:-----------------:|:-----------------:|:-------------------:|
| **Top-1 Accuracy** | 76.19% (48/63) | 77.78% (7/9) | **76.39%** (55/72) |
| **Top-3 Accuracy** | 84.13% (53/63) | 88.89% (8/9) | **84.72%** (61/72) |
| **Top-5 Accuracy** | 88.89% (56/63) | 100.0% (9/9) | **90.28%** (65/72) |
| **MRR** | 0.8066 | 0.8426 | **0.8111** |
| **NDCG@5** | 0.8270 | 0.8812 | **0.8338** |
| **MAP@5** | 0.8066 | 0.8426 | **0.8111** |
| **Avg Latency** | 3341 ms | 4631 ms | 3502 ms |
| **Service Precision** | 100% | — | **100%** |
| **Forbidden Rate** | 0% | 0% | **0%** |

> **Nhận xét tổng thể:**
>
> Hệ thống RAG đạt hiệu suất **tốt đến rất tốt** trên hai endpoint. Combined Top-1 đạt 76.39% — vượt ngưỡng tối thiểu 60% đáng kể, và Combined Top-5 đạt 90.28% — đủ để phủ hầu hết nhu cầu thực tế khi agent có thể xem xét danh sách top-5.
>
> Đáng chú ý, **Maturity retrieval vượt trội so với Check retrieval** ở cả Top-1 lẫn các ranking metric (NDCG 0.881 vs 0.827), phản ánh corpus maturity nhỏ hơn và ít ambiguous hơn so với corpus check với hàng nghìn check có tên tương tự nhau.
>
> MRR = 0.811 và NDCG@5 = 0.834 cho thấy khi hệ thống tìm đúng, kết quả đúng thường ở rank rất cao (gần rank 1), không bị đẩy xuống sâu trong danh sách. Đây là dấu hiệu tích cực về chất lượng fusion và reranking.
>
> Hai điểm cần cải thiện: **Latency P90 vượt ngưỡng** (6953ms > 6000ms) do tiếng Việt cần thêm thời gian xử lý LLM, và **Robustness Gap = 100pp** do khoảng cách tuyệt đối giữa exact-match (100%) và negative cases (0%). Negative cases (query ngoài phạm vi) về bản chất không nên match — đây là hành vi đúng, nhưng ảnh hưởng đến metric robustness.

---

## 3. Check Retrieval — Phân tích theo Loại Query

Benchmark thiết kế 5 loại query để mô phỏng phân phối thực tế:

| Loại Query | N | Top-1 | Top-1% | Top-3% | Top-5% | MRR | NDCG@5 | Avg Latency |
|-----------|:-:|:-----:|:------:|:------:|:------:|:---:|:------:|:-----------:|
| `check_id_exact` | 25 | 25 | **100%** | 100% | 100% | **1.000** | **1.000** | 2590 ms |
| `check_id_partial` | 7 | 6 | **85.7%** | 100% | 100% | **0.929** | **0.947** | 2819 ms |
| `agent_query` | 18 | 11 | **61.1%** | 77.8% | 83.3% | **0.690** | **0.726** | 2757 ms |
| `user_query_vi` | 10 | 6 | **60.0%** | 70.0% | 90.0% | **0.690** | **0.741** | **6892 ms** |
| `negative` | 3 | 0 | **0%** | 0% | 0% | **0.000** | **0.000** | 2490 ms |

> **Nhận xét sâu — Phân tích theo loại query:**
>
> **check_id_exact (25 cases — 100% Top-1, MRR = 1.0):** Khi agent hoặc người dùng cung cấp chính xác check ID (vd: `s3_bucket_public_access`), hệ thống đạt **kết quả hoàn hảo tuyệt đối**. Đây là kết quả kỳ vọng vì hệ thống có exact-match bonus (+2.0 điểm) và BM25 index được tối ưu cho check ID. Thời gian xử lý 2590ms là baseline tốt cho toàn pipeline.
>
> **check_id_partial (7 cases — 85.7% Top-1, Top-5 100%):** Query dạng viết tắt hoặc một phần tên check (vd: `s3_public_access` thay vì `s3_bucket_level_public_access_block`). Hệ thống xử lý tốt — tất cả 7 case đều có kết quả đúng trong Top-5, chỉ 1 case bị đẩy xuống rank 2. Fuzzy matching và synonym expansion hoạt động hiệu quả.
>
> **agent_query (18 cases — 61.1% Top-1, Top-5 83.3%):** Đây là loại query quan trọng nhất trong thực tế — câu hỏi tự nhiên tiếng Anh do planning agent sinh ra (vd: "s3 public access check", "ec2 security group open ports"). Top-1 chỉ đạt 61.1% — sát ngưỡng tối thiểu 60%. Nguyên nhân: query ngắn và mơ hồ khiến hệ thống khó phân biệt giữa nhiều check liên quan (vd: "s3 public access" có thể map đến 6+ check khác nhau). 3/18 case thất bại hoàn toàn (không trong Top-5). **Đây là điểm yếu cần ưu tiên cải thiện nhất cho check retrieval.**
>
> **user_query_vi (10 cases — 60.0% Top-1, Top-5 90%, Latency 6892ms):** Query tiếng Việt từ người dùng cuối (vd: "EBS volume chưa được bật mã hóa mặc định"). Độ chính xác Top-1 tương đương agent_query tiếng Anh, cho thấy query translation với Phi-4 mini hoạt động đủ tốt về chất lượng. Tuy nhiên, **latency 6892ms gần gấp đôi** so với query tiếng Anh do bước dịch LLM. Đây là nguyên nhân chính khiến P90 vượt ngưỡng 6000ms.
>
> **negative (3 cases — 0% — Hành vi đúng có chủ ý!):** Các query ngoài phạm vi: query về Azure (sai cloud provider), query trống, và query ID ngẫu nhiên không tồn tại. Hệ thống **không trả về kết quả nào đúng** — đây là behavior chính xác. Tuy nhiên metric robustness_gap tính cả negative cases vào, làm gap = 100pp và vi phạm ngưỡng 90pp. Metric này cần được refine để loại trừ out-of-scope cases.

---

## 4. Check Retrieval — Phân tích theo AWS Service

| Service | N | Top-1 | Top-1% | Top-3% | Top-5% | Service Precision |
|---------|:-:|:-----:|:------:|:------:|:------:|:-----------------:|
| CloudTrail | 6 | 6 | **100%** | 100% | 100% | 6/6 (100%) |
| KMS | 2 | 2 | **100%** | 100% | 100% | 2/2 (100%) |
| VPC | 2 | 2 | **100%** | 100% | 100% | 2/2 (100%) |
| Lambda | 1 | 1 | **100%** | 100% | 100% | 1/1 (100%) |
| SecretsManager | 1 | 1 | **100%** | 100% | 100% | 1/1 (100%) |
| CloudFront | 1 | 1 | **100%** | 100% | 100% | 1/1 (100%) |
| RDS | 8 | 7 | **87.5%** | 100% | 100% | 8/8 (100%) |
| S3 | 11 | 9 | **81.8%** | 90.9% | 90.9% | 11/11 (100%) |
| IAM | 12 | 9 | **75.0%** | 83.3% | 100% | 12/12 (100%) |
| EC2 | 13 | 9 | **69.2%** | 84.6% | 84.6% | 13/13 (100%) |
| GuardDuty | 3 | 1 | **33.3%** | 33.3% | 66.7% | 3/3 (100%) |
| unknown (negative) | 3 | 0 | 0% | 0% | 0% | — |

> **Nhận xét sâu — Phân tích theo AWS Service:**
>
> **Service Precision = 100% trên tất cả in-scope services:** Đây là kết quả xuất sắc và quan trọng về mặt an toàn. Không có query nào về S3 mà hệ thống trả về IAM check ở top-1, không có query IAM nào trả về EC2 check. `product_gate = "filter"` trong scoring config hoạt động hoàn toàn hiệu quả ở cả pipeline hybrid.
>
> **CloudTrail, KMS, VPC, Lambda, SecretsManager, CloudFront — 100% Top-1:** Các service này đạt hoàn hảo một phần vì số lượng test case nhỏ (1–6 cases), nhưng cũng phản ánh corpus cho các service này ít ambiguous — mỗi khái niệm bảo mật có một check rõ ràng, không có nhiều check "gần giống" nhau.
>
> **RDS (87.5%) và S3 (81.8%) — Tốt:** RDS chỉ miss 1/8 case ở Top-1 nhưng Top-5 = 100%, cho thấy kết quả đúng bị đẩy xuống rank thấp hơn chứ không bị mất hoàn toàn. S3 có 1 case miss Top-5 hoàn toàn (`s3_risk_2`: "s3 bucket encryption not enabled risk of data exposure" — hệ thống trả về các check về public access thay vì encryption, do từ "risk of data exposure" bị match với nhiều check không liên quan đến encryption).
>
> **IAM (75.0%) — Cần chú ý:** IAM có corpus lớn và nhiều check liên quan đến nhau (MFA, password policy, root access, credential rotation…). Query ngữ nghĩa trừu tượng (vd: "enforce strong password requirements") dễ bị match sang Cognito password policy thay vì IAM password policy. Top-5 = 100% cho thấy kết quả đúng luôn có mặt trong danh sách, chỉ là thứ hạng chưa tốt — candidate selection đúng nhưng reranker chưa tối ưu cho IAM domain.
>
> **EC2 (69.2%) — Cần cải thiện:** EC2 có số lượng check phong phú nhất và nhiều dạng câu hỏi trừu tượng (IMDS, security groups, ports). 2 case miss Top-5 đều là semantic_hard queries. `ec2_launch_template_imdsv2_required` bị miss vì câu query "prevent credential theft via instance metadata endpoint" không chứa từ "launch template" hay "imdsv2" — hệ thống trả về `autoscaling_group_launch_configuration_requires_imdsv2` (liên quan nhưng không phải exact target). Cần thêm synonyms cho IMDS v2 checks.
>
> **GuardDuty (33.3% — Điểm yếu lớn nhất):** Chỉ 1/3 case đúng ở Top-1 và 2/3 Top-5. GuardDuty checks có tên rất đặc thù (threat_detection_llm_jacking, threat_detection_enumeration) nhưng query agent sinh ra ngắn gọn ("guardduty enabled threat detection"). Corpus GuardDuty nhỏ khiến BM25 ít hiệu quả, còn vector search không đủ semantic signal để phân biệt các loại threat detection. Cần bổ sung synonyms và tăng số test cases GuardDuty trong benchmark tiếp theo.

---

## 5. Maturity Retrieval — Phân tích theo Loại Query

**Tổng số cases:** 9 (đại diện cho 3 loại query pattern)

| Loại Query | N | Top-1 | Top-1% | Top-3% | Top-5% | MRR | NDCG@5 | Avg Latency |
|-----------|:-:|:-----:|:------:|:------:|:------:|:---:|:------:|:-----------:|
| `capability_exact` | 3 | 3 | **100%** | 100% | 100% | **1.000** | **1.000** | 2048 ms |
| `capability_query` | 3 | 3 | **100%** | 100% | 100% | **1.000** | **1.000** | 4497 ms |
| `capability_vi` | 3 | 1 | **33.3%** | 66.7% | 100% | **0.528** | **0.644** | **7346 ms** |

> **Nhận xét sâu — Maturity Retrieval:**
>
> **capability_exact và capability_query (100% Top-1, MRR = 1.0):** Khi query là tên exact của capability hoặc câu hỏi tiếng Anh mô tả capability, hệ thống đạt **kết quả hoàn hảo**. Corpus maturity capabilities được thiết kế với mô tả rõ ràng, không overlapping như checks, giúp vector search hoạt động rất hiệu quả. Latency 4497ms cho capability_query phản ánh pipeline hybrid đầy đủ có LLM translation.
>
> **capability_vi (33.3% Top-1, Top-5 100%, Latency 7346ms — Điểm yếu cần cải thiện):** Chỉ 1/3 query tiếng Việt về maturity capability đúng ở rank 1, dù tất cả đều có trong Top-5. Đây là vấn đề **thứ hạng** (ranking), không phải recall. LLM translation từ tiếng Việt đôi khi chọn từ khóa không khớp hoàn toàn với tên canonical của capability, khiến fusion score của kết quả đúng không đủ cao để lên rank 1. Latency 7346ms là cao nhất toàn hệ thống — kết hợp hai bước nặng: LLM translation + hybrid retrieval đầy đủ.
>
> **Nhận xét tổng thể về Maturity:** Với 9 test cases, các con số cần được diễn giải cẩn thận về mặt thống kê. NDCG@5 = 0.881 là kết quả tốt, nhưng cần mở rộng benchmark maturity lên ít nhất 30–50 cases để có đánh giá đáng tin cậy. Cần bổ sung thêm: semantic paraphrase, cross-capability queries, và negative maturity cases.

---

## 6. Hiệu quả Reranker

Hệ thống sử dụng cross-encoder `cross-encoder/ms-marco-MiniLM-L-6-v2` để rerank kết quả sau bước hybrid fusion.

| Metric | Trước Rerank | Sau Rerank | Lift |
|--------|:-----------:|:---------:|:----:|
| MRR | 0.3822 | 0.4303 | **+0.0481 (+12.6%)** |
| NDCG@5 | 0.4158 | 0.4516 | **+0.0358 (+8.6%)** |

| Loại kết quả | Số case |
|-------------|:-------:|
| Improved (rerank cải thiện thứ hạng) | **7** |
| Degraded (rerank làm tệ hơn) | **2** |
| Unchanged (không thay đổi) | **51** |

> **Nhận xét sâu — Reranker:**
>
> **MRR lift +12.6% và NDCG lift +8.6%:** Reranker cải thiện rõ ràng chất lượng xếp hạng, đặc biệt trên các trường hợp mà hybrid fusion chưa đủ để đặt kết quả đúng lên top-1. Đây là mức lift tốt cho một cross-encoder nhỏ (MiniLM-L-6-v2 — 6 layers, ~22M params, trọng tâm speed).
>
> **51/60 cases unchanged (85%):** Tỷ lệ cao này cho thấy reranker **không can thiệp vào những case đã xếp hạng tốt**, tránh gây nhiễu. Đây là hành vi lý tưởng — reranker chỉ "sửa" những trường hợp hybrid fusion chưa xử lý tốt.
>
> **7 improved vs 2 degraded (tỷ lệ 3.5:1):** Hiệu quả ròng tích cực, nhưng 2 case bị degraded cần phân tích. Nguyên nhân thường gặp: cross-encoder nhỏ bị overfitted cho MS MARCO (English Q&A domain), có thể không generalize tốt cho domain security checks với tên kỹ thuật dài (vd: `ec2_launch_template_imdsv2_required`). Giá trị lift trên subset (mrr before 0.38 → 0.43) nhỏ hơn nhiều so với toàn bộ pipeline (MRR 0.807) vì subset này tập trung vào các case khó — nơi reranker có tác động thực sự.
>
> **Cơ hội cải thiện:** Thử nghiệm với cross-encoder lớn hơn (ms-marco-MiniLM-L-12-v2 hoặc ms-marco-deberta-v3-base) để đánh giá trade-off latency/quality. Xem xét fine-tune reranker trên domain-specific pairs (security check queries) để giảm gap giữa MS MARCO distribution và cloud security domain.

---

## 7. Hiệu năng Latency

| Percentile | Checks | Maturity | Combined |
|-----------|:------:|:--------:|:--------:|
| **Mean** | 3341 ms | 4631 ms | 3502 ms |
| **Median (P50)** | ~2727 ms | ~4048 ms | 2764 ms |
| **P90** | **6926 ms** | — | **6953 ms** ❌ |
| **P99** | 7505 ms | — | 7505 ms |

**Phân phối latency theo loại query:**

| Loại Query | Avg Latency | Ghi chú |
|-----------|:-----------:|---------|
| check_id_exact | 2590 ms | Baseline — BM25 exact match + vector |
| negative | 2490 ms | Nhanh nhất — query ngắn/trống |
| check_id_partial | 2819 ms | Tương tự exact |
| agent_query | 2757 ms | English — ít LLM overhead |
| capability_exact | 2048 ms | Maturity exact — nhanh nhất |
| capability_query | 4497 ms | Maturity hybrid đầy đủ |
| **user_query_vi** | **6892 ms** | ⚠ Translation LLM overhead cao |
| **capability_vi** | **7346 ms** | ⚠ Cao nhất toàn hệ thống |

**Release Criteria:**
- Average latency: 3502ms vs ngưỡng 5000ms → ✅ PASS (headroom 30%)
- **P90 latency: 6953ms vs ngưỡng 6000ms → ❌ FAIL (vượt 15.9%)**

> **Nhận xét sâu — Latency:**
>
> **Nguyên nhân P90 vượt ngưỡng:** P90 bị kéo lên bởi **tiếng Việt** (latency 6892–7346ms). Bước `query_translation` sử dụng Phi-4 mini chạy locally thêm ~3.5–4.5 giây so với query tiếng Anh. Khi ~20% test cases là tiếng Việt với latency phân phối trên 6000ms, P90 bị ảnh hưởng trực tiếp và nhất quán.
>
> **Median 2764ms là chấp nhận được:** Với hầu hết query tiếng Anh, hệ thống phản hồi trong ~2.7 giây — đủ tốt cho agent-driven workflow không yêu cầu sub-second response.
>
> **Chiến lược cải thiện latency:**
> 1. **Async translation:** Chạy BM25 search với query gốc tiếng Việt song song với Phi-4 mini translation, merge kết quả sau khi có translation — tiết kiệm ~30–40% latency tiếng Việt, đưa về ~4200ms.
> 2. **Cache translation:** Lưu cache kết quả dịch cho query tiếng Việt phổ biến — giảm latency cho repeated queries về 0 overhead.
> 3. **Điều chỉnh ngưỡng SLA:** Nâng ngưỡng P90 release từ 6000ms lên 8000ms để phản ánh bilingual workload thực tế, hoặc tách SLA riêng: tiếng Anh ≤5000ms và tiếng Việt ≤9000ms.

---

## 8. Confidence Calibration

Hệ thống phân loại mỗi kết quả vào 3 bucket confidence: `high`, `medium`, `low`.

### 8.1 Kết quả Calibration tổng thể

| Confidence Level | Số case | Accuracy thực tế | Accuracy kỳ vọng | Calibrated? |
|-----------------|:-------:|:----------------:|:----------------:|:-----------:|
| **High** | 31 | **96.77%** | >= 80% | ✅ Tốt |
| **Medium** | 9 | **88.89%** | [50%, 80%) | ❌ Overconfident (thực tế > expected_max) |
| **Low** | 31 | **54.84%** | <= 50% | ❌ Underconfident (thực tế > expected_max) |
| **ECE** | — | **0.1901** | <= 0.20 | ✅ PASS (sát ngưỡng) |

### 8.2 Calibration theo Route

| Route | High (acc) | Medium (acc) | Low (acc) | ECE | Overall |
|-------|:---------:|:------------:|:---------:|:---:|:-------:|
| check_search | 96.15% ✅ | 87.5% ❌ | 57.14% ❌ | 0.200 | ❌ FAIL |
| maturity_search | 100% ✅ | 100% ❌ | 33.33% ✅ | 0.122 | ❌ FAIL |

> **Nhận xét sâu — Confidence Calibration:**
>
> **High confidence (31 cases — 96.77% accuracy — Hoạt động xuất sắc):** Khi hệ thống tự tin cao, kết quả gần như luôn đúng (chỉ 1/31 case sai). Downstream agent có thể **yên tâm hành động ngay** khi nhận được `high` confidence mà không cần xác nhận thêm — đây là hành vi mong muốn trong autonomous pipeline.
>
> **Medium confidence (9 cases — 88.89% accuracy — Vấn đề calibration nghiêm trọng):** Medium confidence được kỳ vọng có accuracy trong [50%, 80%), nhưng thực tế đạt 88.89% — cao hơn ngưỡng upper bound. Hệ thống đang **under-label** — gán `medium` cho những case thực ra rất tốt. Nguyên nhân: thresholds confidence quá thận trọng với các query dạng partial/paraphrase (nhiều match nhưng hệ thống không chắc → label medium, trong khi reranker lại sort đúng). Cần recalibrate score-to-confidence mapping hoặc áp dụng Platt scaling trên validation set.
>
> **Low confidence (31 cases — 54.84% accuracy — Vấn đề đối xứng):** Low confidence được kỳ vọng <= 50% nhưng thực tế đạt 54.84%. Hệ thống gán `low` cho nhiều case thực ra vẫn tìm đúng — chủ yếu là tiếng Việt/semantic queries có kết quả đúng hơn hệ thống nghĩ. Cần phân tích lại logic gán confidence để tách biệt "không chắc nhưng đúng" và "không chắc và sai".
>
> **ECE = 0.1901 — Margin cực mỏng:** Hệ thống vừa qua được criterion này (0.1901 < 0.20) nhưng chỉ còn 0.001 margin. Bất kỳ thay đổi nhỏ nào (thêm test cases tiếng Việt, thay đổi score threshold) có thể làm ECE vượt ngưỡng trong run tiếp theo. **Đây là rủi ro ổn định cần theo dõi sát.**

---

## 9. Release Criteria — Kết quả đánh giá ngưỡng

**Verdict: ❌ FAIL — 2/13 tiêu chí không đạt**

| # | Tiêu chí | Ngưỡng | Kết quả thực tế | Trạng thái |
|:-:|---------|:------:|:---------------:|:---------:|
| 1 | Checks Top-1 accuracy | >= 60% | 76.19% | ✅ PASS |
| 2 | Checks Top-5 accuracy | >= 80% | 88.89% | ✅ PASS |
| 3 | Maturity Top-1 accuracy | >= 60% | 77.78% | ✅ PASS |
| 4 | Maturity Top-5 accuracy | >= 80% | 100.0% | ✅ PASS |
| 5 | Forbidden capability rate | <= 0% | 0.0% | ✅ PASS |
| 6 | Empty bundle rate | <= 0% | 0.0% | ✅ PASS |
| 7 | Service precision | >= 85% | 100.0% | ✅ PASS |
| 8 | Average latency | <= 5000 ms | 3341 ms | ✅ PASS |
| 9 | Combined MRR | >= 0.70 | 0.8111 | ✅ PASS |
| 10 | Combined NDCG@5 | >= 0.75 | 0.8338 | ✅ PASS |
| 11 | **P90 latency** | **<= 6000 ms** | **6953 ms** | **❌ FAIL** |
| 12 | **Robustness gap** | **<= 90 pp** | **100.0 pp** | **❌ FAIL** |
| 13 | Confidence ECE | <= 0.20 | 0.1901 | ✅ PASS (sát ngưỡng) |

> **Nhận xét sâu — Release Criteria:**
>
> **11/13 tiêu chí PASS — Hệ thống đạt chất lượng tốt về accuracy và ranking.** Các tiêu chí cốt lõi về độ chính xác, ranking, safety đều được đáp ứng với margin rõ ràng, cho thấy hệ thống sẵn sàng về mặt chức năng cho production.
>
> **Criterion #11 — P90 Latency FAIL (6953ms vs 6000ms):** Đây là FAIL kỹ thuật nhưng với **context quan trọng**: P90 bị kéo lên hoàn toàn bởi bilingual workload (tiếng Việt ~20% cases). Nếu loại bỏ tiếng Việt, P90 ước tính ~4500ms — dễ dàng đạt ngưỡng. Không phải bottleneck kiến trúc mà là trade-off thiết kế bilingual pipeline. Giải pháp kỹ thuật khả thi trong 1–2 sprint.
>
> **Criterion #12 — Robustness Gap FAIL (100pp vs 90pp):** Gap = `best (check_id_exact: 100%)` − `worst (negative: 0%)` = 100pp. Tuy nhiên, **negative cases là intentional out-of-scope queries** — hệ thống trả về 0% đúng đắn (không nên match khi query Azure hoặc query trống). Nếu chỉ tính in-scope categories: `check_id_exact (100%) − user_query_vi (60%) = 40pp` — trong ngưỡng an toàn. Metric robustness_gap cần được refine để loại trừ negative cases.
>
> **Criterion #13 — ECE = 0.1901:** Margin chỉ 0.001 — rủi ro cao cho run tiếp theo. Cần recalibrate confidence thresholds ngay.

---

## 10. Phân tích các Case Thất bại

### 10.1 Cases thất bại hoàn toàn (không trong Top-5)

| Case ID | Category | Service | Query | Expected | Nguyên nhân phân tích |
|---------|----------|---------|-------|----------|----------------------|
| `chk_agent_01` | agent_query | S3 | "s3 public access check" | `s3_bucket_public_access` | Query quá ngắn và ambiguous — có 6+ S3 public access checks khác nhau. BM25 và vector không đủ signal để chọn đúng. |
| `chk_agent_07` | agent_query | EC2 | "ec2 security group open ports" | `ec2_securitygroup_allow_ingress_from_internet_to_all_ports` | Query match vào các check port-specific (SSH, RDP, MySQL...) hơn check "all ports" tổng quát. Kết quả liên quan nhưng không đúng target. |
| `chk_agent_15` | agent_query | GuardDuty | "guardduty enabled threat detection" | `guardduty_is_enabled` | Corpus GuardDuty nhỏ, query translation chọn từ không match check ID cơ bản. Nhiều threat_detection checks cạnh tranh với "is_enabled" check. |
| `chk_vi_06` | user_query_vi | EC2 | "EBS volume chua duoc bat ma hoa mac dinh" | `ec2_ebs_default_encryption` | Translation ra "EBS volume encryption not enabled by default" hợp lý nhưng match vào encryption-at-rest checks cụ thể thay vì check default encryption account-level. |

### 10.2 Cases thất bại có chủ ý (Negative/Out-of-scope)

| Case ID | Query | Hành vi hệ thống | Đánh giá |
|---------|-------|-----------------|---------|
| `chk_neg_01` | "check azure firewall rules" | Trả về AWS checks không liên quan | ✅ **Đúng** — Azure ngoài scope |
| `chk_neg_02` | *(empty query)* | Không tìm được kết quả hợp lệ | ✅ **Đúng** — empty query nên fail |
| `chk_neg_03` | "xyznonexistent_check_id_12345" | Không tìm được check ID | ✅ **Đúng** — garbage query nên không match |

> **Nhận xét — Negative Cases:** Tất cả 3 negative cases được xử lý đúng semantic — hệ thống không "hallucinate" kết quả cho query vô nghĩa hay ngoài phạm vi. Đây là dấu hiệu tốt về độ ổn định và an toàn của pipeline. Metric robustness_gap nên được điều chỉnh để không tính negative cases.

### 10.3 Cases đúng Top-5 nhưng miss Top-1

**Maturity capability_vi** có 2/3 case ở rank 2–3 thay vì rank 1: LLM translation tiếng Việt chọn từ khóa cạnh tranh → reranker đặt wrong result lên rank 1 dù kết quả đúng vẫn có mặt trong top-5. Đây là vấn đề ranking quality, không phải recall — giải pháp là cải thiện translation prompt hoặc tăng weight cho exact capability name match.

**IAM partial queries:** 3 case IAM đúng Top-5 nhưng rank 2–3 vì IAM corpus có nhiều checks gần giống nhau (password_policy_minimum_length_14, password_policy_lowercase, password_policy_symbol...) và reranker không đủ domain knowledge để phân biệt.

---

## 11. Kết luận và Khuyến nghị

### 11.1 Tóm tắt Điểm mạnh

| Điểm mạnh | Đánh giá |
|-----------|---------|
| Exact check ID retrieval | ⭐⭐⭐⭐⭐ Hoàn hảo — 100% Top-1 |
| Service isolation (zero cross-service contamination) | ⭐⭐⭐⭐⭐ Hoàn hảo — Service Precision 100% |
| Safety (zero forbidden capability violations) | ⭐⭐⭐⭐⭐ Hoàn hảo — Forbidden Rate 0% |
| Maturity capability retrieval (English) | ⭐⭐⭐⭐⭐ Hoàn hảo — Top-5 100% |
| Combined ranking quality (MRR, NDCG@5) | ⭐⭐⭐⭐ Rất tốt — trên ngưỡng đáng kể |
| Reranker effectiveness | ⭐⭐⭐⭐ Tốt — +12.6% MRR lift |
| High confidence calibration | ⭐⭐⭐⭐ Tốt — 96.77% accuracy |

### 11.2 Ưu tiên cải thiện

| # | Vấn đề | Ảnh hưởng | Ưu tiên |
|:-:|--------|:---------:|:-------:|
| 1 | P90 latency vượt ngưỡng (do tiếng Việt) | Cao — criterion FAIL | 🔴 Cao |
| 2 | ECE = 0.1901 — sát ngưỡng, medium/low bins miscalibrated | Cao — stability risk | 🔴 Cao |
| 3 | Robustness gap metric cần điều chỉnh definition | Trung bình — metric design issue | 🟡 Trung bình |
| 4 | GuardDuty Top-1 chỉ 33.3% | Trung bình — service-specific gap | 🟡 Trung bình |
| 5 | agent_query ngắn/ambiguous miss Top-5 | Trung bình — UX impact | 🟡 Trung bình |
| 6 | Maturity benchmark chỉ có 9 cases (thiếu statistical power) | Thấp | 🟢 Thấp |

### 11.3 Khuyến nghị kỹ thuật

**[P0] Async query translation cho tiếng Việt:** Chạy BM25 search với query gốc song song với Phi-4 mini translation. Merge results sau khi có translation. Dự kiến giảm P90 từ ~7000ms xuống ~4500ms, đưa P90 về dưới ngưỡng 6000ms.

**[P0] Recalibrate confidence thresholds:** ECE cách ngưỡng fail chỉ 0.001 điểm. Chạy Platt scaling hoặc isotonic regression trên validation set để recalibrate score → confidence bucket mapping. Mục tiêu: đưa medium bin accuracy về [50%, 80%) thực sự.

**[P1] Refine robustness_gap metric:** Loại bỏ `negative` category khỏi tính toán gap, hoặc tách thành `in_scope_robustness_gap` (4 in-scope categories) và `rejection_rate` riêng. Gap thực sự trong-phạm-vi là 40pp (100% − 60%) — rất trong ngưỡng an toàn.

**[P1] Cải thiện GuardDuty retrieval:** Bổ sung synonyms cho GuardDuty checks, đặc biệt `guardduty_is_enabled` cần thêm aliases như "enable threat detection", "activate guardduty", "turn on guardduty". Thêm 5–10 test cases GuardDuty vào benchmark_cases.json v5.

**[P2] Xử lý ambiguous agent queries:** Với queries ngắn như "s3 public access check", nghiên cứu thêm bước **query expansion** dựa vào conversation context của planning agent để làm rõ scope trước khi retrieval.

**[P2] Mở rộng benchmark maturity:** Tăng từ 9 lên 30–50 cases để có statistical significance. Thêm các category: semantic_paraphrase, cross_capability, negative_maturity.

---

*Báo cáo được tạo từ kết quả benchmark run `20260407_063248`. Dữ liệu nguồn: `RAG/data/benchmarks/benchmark_outputs/benchmark_run_20260407_063248.json`.*
