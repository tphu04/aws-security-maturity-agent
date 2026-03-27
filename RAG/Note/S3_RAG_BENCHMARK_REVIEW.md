# S3 RAG Benchmark Review

## Mục tiêu

Tài liệu này đánh giá benchmark hiện tại trong [rag_benchmark_results.json](C:/Users/trung/Desktop/DoAn/RAG/tests/rag_benchmark_results.json) dưới góc nhìn readiness cho agent, đồng thời đề xuất khung benchmark mới chỉ tập trung trên S3 để đo đúng các rủi ro quan trọng trước khi đưa RAG vào `planning`, `risk`, `report`.

Khung benchmark mới được thêm tại:
- [benchmark_s3_agent_readiness.py](C:/Users/trung/Desktop/DoAn/RAG/tests/benchmark_s3_agent_readiness.py)
- [benchmark_s3_cases.json](C:/Users/trung/Desktop/DoAn/RAG/tests/benchmark_s3_cases.json)

## Tóm tắt điều hành

Benchmark hiện tại cho thấy RAG service đã có nền tảng tốt:
- API trả dữ liệu ổn định.
- Payload theo từng consumer đã được tách đúng shape.
- Technical retrieval cho các tình huống S3 public access có dấu hiệu tốt.

Tuy nhiên benchmark hiện tại chưa đủ để kết luận "agent-safe":
- Số lượng scenario còn ít.
- Chưa đo đúng/sai theo nhãn kỳ vọng.
- Chưa có metric chặn lỗi semantic nguy hiểm.
- Đã xuất hiện false-positive mapping nghiêm trọng với S3 encryption.
- Có case report trả bundle rỗng nhưng benchmark vẫn chỉ ghi là request thành công.

Kết luận thực dụng:
- Dùng được để debug retrieval API.
- Chưa đủ làm tiêu chuẩn release cho agent.

## Những gì benchmark hiện tại làm tốt

### 1. Có coverage cho 3 consumer

Benchmark hiện tại đã chạm vào cả `planning`, `risk`, `report`, đây là điểm mạnh vì context bundle không nên được đánh giá như một endpoint retrieval thuần.

### 2. Có tín hiệu chất lượng nội bộ

Kết quả benchmark hiện tại không chỉ ghi `status=success` mà còn mang theo:
- `confidence`
- `review_req`
- `bundle_stats`
- `prompt_ready_context`

Điều này rất hữu ích để team không bị đánh lừa bởi việc "API có trả JSON".

### 3. Bắt đầu phản ánh được rủi ro semantic

Trong nhiều scenario, payload tự gắn các cảnh báo như:
- `exact_lookup_miss`
- `exact_lookup_mismatch`
- `ambiguous_top_results`
- `low_score_top1`

Đây là dấu hiệu tốt về mặt thiết kế vì hệ thống đã có cơ chế tự cảnh báo khi độ chắc chắn không cao.

## Những nhược điểm chính của benchmark hiện tại

### 1. Success ở API không đồng nghĩa success ở retrieval

Trong benchmark hiện tại, các scenario đều trả `status=success`, nhưng đây mới chỉ là thành công ở lớp giao tiếp API. Nó chưa chứng minh:
- top result có đúng intent không
- mapping có đúng domain không
- bundle có usable cho agent không

### 2. Không có ground truth rõ ràng

Benchmark hiện tại thiếu các nhãn đánh giá như:
- expected top-1 check id
- expected capability id
- forbidden capability ids
- expected primary finding cho risk
- expected minimum completeness cho report bundle

Không có ground truth thì benchmark chủ yếu là "snapshot response", chưa phải benchmark chất lượng.

### 3. Thiếu metric fail-closed cho agent

Các chỉ số quan trọng với agent hiện chưa được đo trực tiếp:
- `required_check_hit_rate`
- `primary_check_exact_rate`
- `forbidden_capability_rate`
- `empty_bundle_rate`
- `report_completeness_rate`

Đây mới là các metric thực sự quyết định việc agent có nên tin context hay không.

### 4. Chưa khóa lỗi semantic nguy hiểm

Trường hợp đáng chú ý nhất ở S3:
- `s3_bucket_default_encryption` đang map sang `generative_ai_data_protection_with_amazon_bedrock`
- `s3_bucket_kms_encryption` cũng map sang `generative_ai_data_protection_with_amazon_bedrock`
- `s3_bucket_secure_transport_policy` cũng bị kéo về cùng capability Bedrock

Các mapping này hiện nằm ngay trong normalized mapping data:
- [maturity_mappings.json](C:/Users/trung/Desktop/DoAn/RAG/data/normalized/maturity_mappings.json)

Đây là lỗi semantic mức cao vì:
- check kỹ thuật S3 là đúng
- nhưng control/maturity context bị lệch sang domain GenAI/Bedrock
- agent có thể lập luận hoặc viết báo cáo sai theo kiểu "đúng technical fact, sai governance meaning"

### 5. Không xem bundle rỗng là lỗi chất lượng

Ở scenario `Report 1: Generate report for S3 public access`, benchmark hiện tại cho thấy:
- `checks_found = 0`
- `mappings_found = 0`
- `capabilities_found = 0`
- `confidence = low`

Nhưng nếu chỉ nhìn lớp API thì đây vẫn là response thành công. Với agent, đây phải được xem là failure của readiness, không phải success trung lập.

## Phân tích theo consumer trên S3

### Planning

Ưu điểm:
- thường lấy ra được đúng check kỹ thuật cùng service `s3`
- có khả năng trả bundle gọn, hữu ích cho scan planning

Nhược điểm:
- phần maturity/mapping dễ bị drift
- nếu agent dùng luôn capability context để suy luận scan scope, plan có thể đúng nửa đầu và lệch nửa sau

Rủi ro agent:
- scan scope đúng nhưng giải thích lý do sai
- chọn nhầm related controls

### Risk

Ưu điểm:
- với finding cụ thể, hệ thống có xu hướng trả đúng `primary_finding`
- technical evidence của S3 checks khá usable

Nhược điểm:
- control mapping vẫn chưa đủ sạch
- nếu risk agent dùng maturity context để tăng/giảm severity, false-positive mapping sẽ làm sai risk reasoning

Rủi ro agent:
- reasoning nghe hợp lý nhưng dựa trên control context sai

### Report

Ưu điểm:
- khi retrieval tốt, report bundle có thể khá giàu thông tin

Nhược điểm:
- là consumer nhạy nhất với lỗi quality
- bundle rỗng hoặc mapping sai sẽ kéo narrative sai ngay
- report cần cả factual check + control theme + recommended practices, nên dễ vỡ hơn planning/risk

Rủi ro agent:
- báo cáo rỗng
- báo cáo đúng kỹ thuật nhưng control framing sai
- báo cáo trôi sang domain không liên quan

## Khung benchmark S3 mới đo những gì

Khung mới chỉ test trên `S3` và đo trực tiếp readiness cho agent qua endpoint `/v1/context/build`.

### Dataset

Case file: [benchmark_s3_cases.json](C:/Users/trung/Desktop/DoAn/RAG/tests/benchmark_s3_cases.json)

Nhóm scenario:
- `planning`
- `risk`
- `report`

Chủ đề S3:
- public access
- encryption at rest
- encryption in transit

### Metric lớp retrieval

- `required_check_hit_rate`
- `required_check_mrr_avg`
- `service_precision_avg`

Ý nghĩa:
- top kết quả có chạm đúng S3 check mong muốn không
- check có giữ đúng service boundary không

### Metric lớp mapping/maturity

- `required_capability_hit_rate`
- `forbidden_capability_rate`

Ý nghĩa:
- có kéo được capability đúng không
- có bị trôi sang capability cấm không

Trên S3, `generative_ai_data_protection_with_amazon_bedrock` được xem là capability cấm cho các case generic encryption/public access.

### Metric lớp bundle cho agent

- `empty_bundle_rate`
- `bundle_completeness_rate`
- `primary_check_exact_rate` cho `risk`
- `report_completeness_rate` cho `report`

Ý nghĩa:
- bundle có usable không
- risk có lấy đúng finding chính không
- report có đủ topic, finding, theme, practice không

### Metric vận hành

- `review_recommended_rate`
- `confidence_distribution`
- `average_latency_ms`
- `warning_counts`

## Tiêu chuẩn readiness đề xuất

### Planning

Chỉ nên xem là ready khi:
- `required_check_hit_rate >= 0.95`
- `required_capability_hit_rate >= 0.90`
- `service_precision_avg = 1.0`
- `forbidden_capability_rate = 0`
- `empty_bundle_rate = 0`

### Risk

Chỉ nên xem là ready khi:
- `primary_check_exact_rate = 1.0`
- `required_check_hit_rate >= 0.95`
- `required_capability_hit_rate >= 0.90`
- `forbidden_capability_rate = 0`
- `empty_bundle_rate = 0`

### Report

Chỉ nên xem là ready khi:
- `required_check_hit_rate >= 0.95`
- `required_capability_hit_rate >= 0.90`
- `bundle_completeness_rate >= 0.95`
- `report_completeness_rate >= 0.95`
- `forbidden_capability_rate = 0`
- `empty_bundle_rate = 0`

## Kế hoạch cải thiện chất lượng tốt nhất trước khi đưa cho agent dùng

### P0. Sửa mapping S3 sai domain

Ưu tiên cao nhất là làm sạch curated mappings cho các check S3 sau:
- `s3_bucket_default_encryption`
- `s3_bucket_kms_encryption`
- `s3_bucket_secure_transport_policy`

Mục tiêu:
- encryption at rest -> `data_encryption_at_rest`
- secure transport -> `encryption_in_transit`
- public access -> `block_public_access`

Nếu chưa sửa mapping data ngay, cần chặn ở `ContextBuilder` hoặc `MappingService` bằng entity gate mạnh hơn.

### P1. Thêm fail-closed rule cho agent

- `planning`: nếu có forbidden capability hoặc review flag cao, bỏ maturity context, chỉ giữ check context
- `risk`: chỉ dùng maturity context khi capability hit đúng và không có forbidden capability
- `report`: nếu report bundle không đủ tối thiểu thì không generate narrative đầy đủ

### P2. Tăng độ mạnh của entity gating

Hiện domain alignment chưa đủ để chặn semantic drift.

Cần thêm:
- product/entity gating theo từ khóa cứng
- cấm match `bedrock` nếu query/check không có tín hiệu GenAI
- trọng số phạt mạnh cho capability có product token lạ

### P3. Tách scoring giữa check quality và mapping quality

Hiện một case có thể nhìn "ổn" vì check đúng dù mapping sai.

Cần báo cáo riêng:
- retrieval technical pass/fail
- mapping semantic pass/fail
- bundle usability pass/fail

### P4. Dùng benchmark mới làm release gate

Trước khi agent consume RAG cho S3:
1. Chạy [benchmark_s3_agent_readiness.py](C:/Users/trung/Desktop/DoAn/RAG/tests/benchmark_s3_agent_readiness.py)
2. Kiểm tra `consumer_readiness`
3. Chỉ mở tích hợp cho consumer nào đạt `ready`

## Kết luận

Benchmark hiện tại là một baseline tốt để quan sát response shape, nhưng chưa đủ để bảo đảm quality cho agent.

Để chuẩn bị cho agent dùng thật, việc quan trọng nhất không phải là tăng số scenario chung chung, mà là:
- đo đúng/sai theo ground truth
- chặn forbidden semantic drift
- coi bundle rỗng là failure
- đánh giá readiness theo từng consumer

Khung benchmark S3 mới được thêm vào repo nhằm phục vụ đúng mục tiêu đó.
