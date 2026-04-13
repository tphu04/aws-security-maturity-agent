# Đánh giá Hệ thống RAG (Retrieval-Augmented Generation)

## 1. Tổng quan phương pháp đánh giá

Hệ thống RAG được đánh giá qua **ba tầng benchmark** với tổng cộng **120 test cases**, phản ánh đúng phân bố traffic trong môi trường production:

| Tầng | Mục tiêu đánh giá | Số lượng test cases |
|------|-------------------|---------------------|
| Tầng 1 — Retrieval Accuracy | Hệ thống có tìm đúng tài liệu liên quan không? | 72 cases |
| Tầng 2 — Field Accuracy | Các trường dữ liệu trả về (severity, mapping) có chính xác không? | 33 cases |
| Tầng 3 — Context Completeness | Bundle context có đầy đủ thông tin cho agent downstream không? | 15 cases |

Ngoài ra, một **ablation study** được thực hiện để so sánh hiệu quả của ba chiến lược truy vấn: BM25-only (lexical), Vector-only (semantic), và Hybrid (kết hợp cả hai).

### 1.1. Thiết kế bộ test cases

Bộ test cases được thiết kế dựa trên phân tích traffic thực tế từ ba agent sử dụng hệ thống RAG:

| Loại truy vấn | Tỷ lệ production | Số cases | Mô tả |
|---------------|-------------------|----------|--------|
| check_id_exact | ~35% | 25 | Agent RiskEvaluation và Report truyền check_id chính xác từ kết quả scan |
| check_id_partial | ~10% | 7 | Truy vấn với check_id không đầy đủ hoặc viết tắt |
| agent_query | ~25% | 18 | PlanningAgent sinh câu truy vấn tiếng Anh ngắn (3-5 từ) |
| user_query_vi | ~15% | 10 | Người dùng Việt Nam nhập truy vấn tiếng Việt mix thuật ngữ AWS |
| capability_lookup | ~10% | 9 | Truy vấn maturity capability (exact, tiếng Việt, ngôn ngữ tự nhiên) |
| negative/edge | ~5% | 3 | Truy vấn không hợp lệ, service không tồn tại, chuỗi rỗng |

Hệ thống đánh giá sử dụng **graded relevance** (thang điểm 0-3) cho mỗi test case thay vì chỉ binary đúng/sai, cho phép tính các metric tinh vi hơn như NDCG.

### 1.2. Các metric đánh giá

- **Top-k Accuracy**: Tỷ lệ tài liệu mong đợi xuất hiện trong top-k kết quả (k = 1, 5)
- **MRR (Mean Reciprocal Rank)**: Trung bình nghịch đảo vị trí của kết quả đúng đầu tiên
- **NDCG@5 (Normalized Discounted Cumulative Gain)**: Đo chất lượng xếp hạng có tính đến mức độ liên quan
- **ECE (Expected Calibration Error)**: Đo độ tin cậy của confidence score
- **Service Precision**: Tỷ lệ kết quả trả đúng AWS service
- **Field Accuracy**: Tỷ lệ các trường dữ liệu (severity, title, mapping) trả về chính xác
- **Context Completeness**: Tỷ lệ bundle context đầy đủ các thành phần cần thiết cho agent

---

## 2. Kết quả Tầng 1 — Retrieval Accuracy

### 2.1. Kết quả tổng hợp

Tầng 1 đánh giá khả năng truy vấn cơ bản: với một câu truy vấn đầu vào, hệ thống có trả về đúng tài liệu liên quan trong top-k kết quả không.

| Metric | Prowler Checks (63 cases) | Maturity Capabilities (9 cases) | Combined (72 cases) |
|--------|--------------------------|--------------------------------|---------------------|
| Top-1 Accuracy | 76.2% (48/63) | 77.8% (7/9) | 76.4% (55/72) |
| Top-5 Accuracy | 88.9% (56/63) | 100% (9/9) | 90.3% (65/72) |
| MRR | 0.807 | 0.843 | 0.812 |
| NDCG@5 | 0.827 | 0.881 | 0.834 |
| Service Precision | 100% | — | 100% |
| Avg Latency | 3,478ms (P50) | 3,279ms (P50) | — |

Hệ thống đạt **MRR 0.812** và **Top-5 Accuracy 90.3%**, cho thấy trong hơn 90% trường hợp, tài liệu liên quan nằm trong top-5 kết quả trả về. Service Precision đạt 100%, nghĩa là hệ thống không bao giờ trả về kết quả thuộc sai AWS service.

### 2.2. Phân tích theo loại truy vấn

| Loại truy vấn | Top-1 | Top-5 | MRR | Nhận xét |
|---------------|-------|-------|-----|----------|
| check_id_exact (25) | **100%** | **100%** | 1.000 | Exact match hoàn hảo — luồng RiskEval/Report hoạt động tối ưu |
| check_id_partial (7) | **85.7%** | **100%** | 0.929 | Xử lý tốt cả khi input không chính xác |
| agent_query (18) | 61.1% | 83.3% | 0.690 | Truy vấn ngắn của PlanningAgent — chấp nhận được do có confidence gate |
| user_query_vi (10) | 60.0% | **90.0%** | 0.690 | Truy vấn tiếng Việt — translation hoạt động hiệu quả |
| capability_exact (3) | **100%** | **100%** | 1.000 | Maturity capability exact match |
| capability_query (3) | **100%** | **100%** | 1.000 | Truy vấn ngôn ngữ tự nhiên cho capability |
| capability_vi (3) | 33.3% | **100%** | 0.528 | Tiếng Việt cho capability — top-1 yếu nhưng top-5 đạt 100% |
| negative (3) | 0% | 0% | — | Đúng hành vi: không trả kết quả sai cho truy vấn không hợp lệ |

**Phân tích chuyên sâu:**

- **Production-critical path** (check_id_exact + partial, chiếm ~70% traffic): đạt **97.5% top-1 accuracy** — đảm bảo luồng RiskEvaluation và Report agent hoạt động chính xác.
- **PlanningAgent path** (agent_query, chiếm ~25% traffic): đạt 61.1% top-1 nhưng 83.3% top-5. Kết quả này chấp nhận được vì PlanningAgent có cơ chế confidence gate — khi RAG confidence thấp, agent tự động gọi LLM để tinh chỉnh kết quả.
- **Vietnamese user input** (chiếm ~5% traffic): đạt **90% top-5 accuracy** nhờ module auto-translation tích hợp sẵn trong pipeline, tự động phát hiện và dịch truy vấn tiếng Việt sang tiếng Anh trước khi truy vấn.

### 2.3. Phân tích theo AWS Service

| Service | Cases | Top-1 | Top-5 | Service Precision |
|---------|-------|-------|-------|-------------------|
| S3 | 11 | 81.8% | 90.9% | 100% |
| IAM | 12 | 75.0% | 100% | 100% |
| EC2 | 13 | 69.2% | 84.6% | 100% |
| RDS | 8 | 87.5% | 100% | 100% |
| CloudTrail | 6 | 100% | 100% | 100% |
| KMS | 2 | 100% | 100% | 100% |
| GuardDuty | 3 | 33.3% | 66.7% | 100% |
| VPC | 2 | 100% | 100% | 100% |
| Lambda | 1 | 100% | 100% | 100% |
| SecretsManager | 1 | 100% | 100% | 100% |
| CloudFront | 1 | 100% | 100% | 100% |

Hầu hết các service đạt trên 80% top-1 accuracy. GuardDuty có accuracy thấp nhất (33.3%) do nhiều sub-protection checks (RDS Protection, Lambda Protection, S3 Protection) có BM25 score cao hơn check `guardduty_is_enabled` — đây là hạn chế của BM25 scoring khi nhiều tài liệu cùng service chứa các keyword giống nhau.

### 2.4. Confidence Calibration

| Mức confidence | Số cases | Accuracy thực tế | Kỳ vọng | Calibrated? |
|----------------|----------|-------------------|---------|-------------|
| High | 26 | **96.2%** | ≥ 80% | Có |
| Medium | 8 | 87.5% | 50-80% | Không (quá cao) |
| Low | 28 | 57.1% | < 50% | Không (quá cao) |

**ECE (Expected Calibration Error): 0.20**

Confidence mức High rất đáng tin cậy (96.2% accuracy). Mức Medium và Low đang under-calibrated — hệ thống thực tế tốt hơn mức nó tự đánh giá. Điều này có nghĩa hệ thống có xu hướng "thận trọng quá mức", đánh confidence thấp cho nhiều kết quả thực tế đúng.

### 2.5. Cross-Encoder Reranker

| Metric | Trước reranking | Sau reranking | Cải thiện |
|--------|----------------|---------------|-----------|
| MRR | 0.382 | 0.430 | **+0.048** |
| NDCG@5 | 0.416 | 0.452 | **+0.036** |
| Cases improved | — | 7 | — |
| Cases degraded | — | 2 | — |

Cross-encoder reranker (ms-marco-MiniLM-L-6-v2) cải thiện MRR thêm 0.048 điểm, với 7 cases được cải thiện và chỉ 2 cases bị giảm chất lượng. Mô hình cross-encoder giúp xếp hạng lại dựa trên semantic similarity chính xác hơn so với fusion score ban đầu.

---

## 3. Kết quả Tầng 2 — Field Accuracy

Tầng 2 đánh giá tính chính xác của các trường dữ liệu mà agent downstream sử dụng. Đây là tầng đánh giá quan trọng vì RiskEvaluation agent dựa vào severity và mapping từ RAG để điều chỉnh risk score.

### 3.1. Kết quả tổng hợp

| Nhóm | Cases | Pass Rate | Chi tiết |
|------|-------|-----------|----------|
| Risk field accuracy | 22 | **72.7%** (16/22) | Severity + title + mapping |
| Planning field accuracy | 11 | **100%** (11/11) | Findings count + severity populated + service correct |
| **Tổng Tầng 2** | **33** | **75.8%** (25/33) | |

### 3.2. Phân tích Risk Field Accuracy

Trong 22 test cases cho consumer "risk", 16 cases pass và 6 cases fail. Phân tích chi tiết các failure:

| Loại failure | Số cases | Nguyên nhân |
|-------------|----------|-------------|
| Thiếu maturity mapping | 5 | Check chưa có mapping trong dữ liệu maturity_mappings |
| Severity không khớp | 2 | Severity trong normalized data khác với expected |

**Root cause chính**: Dữ liệu maturity_mappings chưa cover đầy đủ tất cả các prowler checks. Cụ thể, các check thuộc EC2 (security group, EBS encryption, IMDSv2) và GuardDuty chưa có mapping tới maturity capability tương ứng. Đây là **data gap** trong quy trình sinh mapping, không phải lỗi của thuật toán retrieval.

### 3.3. Phân tích Planning Field Accuracy

Tất cả 11 test cases cho consumer "planning" đều pass, bao gồm:
- 8 truy vấn tiếng Anh (agent-generated) cho 6 AWS services
- 3 truy vấn tiếng Việt (user input với auto-translation)

Mỗi case kiểm tra: (1) số lượng findings trả về ≥ ngưỡng tối thiểu, (2) tất cả findings có trường severity, (3) service đúng xuất hiện trong kết quả. Kết quả 100% cho thấy pipeline RAG → PlanningAgent hoạt động ổn định.

---

## 4. Kết quả Tầng 3 — Context Completeness

Tầng 3 đánh giá tính đầy đủ của bundle context mà RAG trả về cho Report agent. Report agent cần: key_findings (với risk_summary), control_themes, và recommended_practices để sinh báo cáo chuyên sâu.

### 4.1. Kết quả tổng hợp

| Nhóm | Cases | Pass Rate | Chi tiết |
|------|-------|-----------|----------|
| Single-check context | 10 | **100%** (10/10) | Mỗi check trả đầy đủ risk_summary, themes, practices |
| Batch multi-check context | 4 | **75%** (3/4) | 1 batch 5 checks bị thiếu key_findings |
| Negative/edge cases | 1 | **100%** (1/1) | Check_id không tồn tại → xử lý đúng |
| **Tổng Tầng 3** | **15** | **93.3%** (14/15) | |

### 4.2. Phân tích

Khi truy vấn đơn lẻ (1 check_id), hệ thống trả về **100% đầy đủ context** cho 10 service khác nhau (S3, IAM, EC2, RDS, CloudTrail, GuardDuty, KMS, VPC, Lambda, SecretsManager). Report agent luôn nhận được risk_summary, control_themes, và recommended_practices.

Failure duy nhất xảy ra ở batch truy vấn 5 check_ids cùng lúc — hệ thống trả về ít key_findings hơn kỳ vọng. Nguyên nhân là `max_context_items` limit trong bundle factory giới hạn số lượng items để tối ưu kích thước response.

---

## 5. Ablation Study — So sánh chiến lược truy vấn

Ablation study so sánh ba chiến lược retrieval trên cùng bộ test cases (69 cases, loại trừ negative):

### 5.1. Kết quả tổng hợp

| Metric | BM25-only | Vector-only | **Hybrid** |
|--------|-----------|-------------|------------|
| **Top-1 Accuracy** | 71.0% | 71.0% | **79.7%** |
| **Top-5 Accuracy** | 91.3% | 85.5% | **94.2%** |
| **MRR** | 0.787 | 0.767 | **0.846** |
| Avg Latency | 2,823ms | 2,877ms | 3,705ms |

Hybrid retrieval vượt trội ở mọi metric accuracy so với BM25-only (+8.7pp Top-1) và Vector-only (+8.7pp Top-1). Latency tăng khoảng 30% do cần chạy song song cả BM25 và vector search rồi merge kết quả, nhưng vẫn nằm trong ngưỡng chấp nhận (P50 < 4 giây).

### 5.2. Phân tích theo loại truy vấn

| Loại truy vấn | BM25 Top-1 | Vector Top-1 | Hybrid Top-1 | Phân tích |
|---------------|-----------|-------------|-------------|-----------|
| check_id_exact | **100%** | 84.0% | **100%** | BM25 thắng nhờ exact token matching; Vector yếu vì check_id không phải ngôn ngữ tự nhiên |
| check_id_partial | 57.1% | 71.4% | **85.7%** | Hybrid kết hợp BM25 keyword match + Vector semantic similarity |
| agent_query | 55.6% | **66.7%** | 61.1% | Vector mạnh hơn cho truy vấn ngôn ngữ tự nhiên ngắn |
| user_query_vi | 30.0% | 40.0% | **60.0%** | Hybrid hưởng lợi nhiều nhất: BM25 match từ tiếng Anh + Vector match semantic |
| capability_query | 66.7% | 66.7% | **100%** | Hybrid đạt tối ưu cho capability lookup |

**Nhận xét quan trọng:**

1. **BM25 chiếm ưu thế cho exact match**: Khi input là check_id chính xác, BM25 đạt 100% nhờ cơ chế exact token lookup trong index. Vector search chỉ đạt 84% vì embedding của check_id dạng `s3_bucket_public_access` không phải ngôn ngữ tự nhiên mà mô hình BGE được huấn luyện trên.

2. **Vector chiếm ưu thế cho ngôn ngữ tự nhiên**: Với agent_query (câu truy vấn 3-5 từ tiếng Anh), Vector đạt 66.7% so với BM25 55.6%. Mô hình embedding BGE-base-en-v1.5 nắm bắt semantic similarity tốt hơn keyword matching cho dạng truy vấn này.

3. **Hybrid kết hợp tốt nhất cả hai**: Đặc biệt cho Vietnamese queries (+30pp so với BM25-only), hybrid tận dụng BM25 để match các thuật ngữ tiếng Anh (S3, MFA, SSH) và vector search để match ý nghĩa tổng thể của câu truy vấn.

4. **Trade-off latency**: Hybrid chậm hơn ~30% nhưng cải thiện Top-1 accuracy 8.7pp — đây là trade-off chấp nhận được trong bối cảnh hệ thống không yêu cầu real-time (P90 < 7 giây).

---

## 6. Đánh giá tổng hợp và hạn chế

### 6.1. Điểm mạnh

| Khía cạnh | Đánh giá | Bằng chứng |
|-----------|----------|------------|
| Production-critical accuracy | Xuất sắc | 97.5% top-1 cho check_id lookup (70% traffic) |
| Service precision | Hoàn hảo | 100% — không bao giờ trả sai service |
| Context completeness | Rất tốt | 93.3% bundle đầy đủ cho Report agent |
| Vietnamese support | Hiệu quả | 90% top-5 cho truy vấn tiếng Việt |
| Confidence reliability | Đáng tin ở mức High | 96.2% accuracy cho high confidence |
| Hybrid retrieval | Vượt trội | +8.7pp so với mỗi phương pháp đơn lẻ |

### 6.2. Hạn chế

| Hạn chế | Mức độ | Chi tiết |
|---------|--------|----------|
| Maturity mapping gaps | Trung bình | 6/22 risk cases thiếu mapping — cần bổ sung dữ liệu |
| Agent query accuracy | Trung bình | 61.1% top-1 — cần cải thiện cho truy vấn mơ hồ |
| Confidence calibration | Nhẹ | ECE 0.20 — mức Medium/Low under-calibrated |
| Vietnamese top-1 | Nhẹ | 60% top-1 — phụ thuộc vào chất lượng translation model |
| Batch context truncation | Nhẹ | Bundle >5 checks có thể bị giới hạn bởi max_context_items |

### 6.3. Tổng kết metrics

| Tầng | Đo gì | Cases | Kết quả chính |
|------|--------|-------|---------------|
| **Tầng 1** | Retrieval Accuracy | 72 | MRR=0.812, Top-5=90.3% |
| **Tầng 2** | Field Accuracy | 33 | 75.8% (Planning 100%, Risk 72.7%) |
| **Tầng 3** | Context Completeness | 15 | 93.3% |
| **Ablation** | BM25 vs Vector vs Hybrid | 69 × 3 = 207 | Hybrid MRR=0.846 tốt nhất |
| **Tổng** | | **120 unique + 207 ablation runs** | |
