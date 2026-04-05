# RAG Evaluation Framework

**Ngày tạo**: 02/04/2026  
**Phiên bản**: 1.0  
**Mục tiêu**: Xây dựng framework đánh giá chuẩn cho hệ thống RAG phục vụ AWS Security Assessment, chọn lọc các metrics core phù hợp với kiến trúc cụ thể của hệ thống.

---

## 1. Bối cảnh và Nguyên tắc

### 1.1 Đặc thù hệ thống

Hệ thống RAG hiện tại **không sinh câu trả lời trực tiếp** (no generation). Thay vào đó, RAG đóng vai trò **cung cấp context** cho các downstream agent (Planning, Risk, Report). Điều này quyết định việc chọn metrics:

- **Retrieval quality là trọng tâm** — context sai = agent sai.
- **Generation metrics (faithfulness, hallucination) không áp dụng trực tiếp** — phần generation nằm ở agent layer, không nằm trong RAG.
- **Context completeness quan trọng hơn answer correctness** — agent cần đủ thông tin, không cần RAG trả lời đúng.

### 1.2 Pipeline cần đánh giá

```
Query → Router → [BM25 ∥ Vector] → RRF Merge → Product Gate → CrossEncoder Rerank → Metadata Bonus → Verifier → ContextBuilder → Agent Bundle
```

Mỗi stage trong pipeline đều có thể đo lường riêng, nhưng framework này tập trung vào **3 điểm đo chính** (evaluation points):

| Điểm đo | Vị trí | Câu hỏi cần trả lời |
|----------|--------|----------------------|
| **Retrieval Quality** | Sau Reranker, trước ContextBuilder | RAG có tìm đúng documents không? |
| **Context Quality** | Sau ContextBuilder, trước Agent | Context bundle có đầy đủ và chính xác không? |
| **System Quality** | End-to-end | Hệ thống có đủ nhanh và ổn định không? |

### 1.3 Nguyên tắc chọn metrics

1. **Ưu tiên chất lượng hơn số lượng** — chọn ít metrics nhưng mỗi metric phải trả lời được một câu hỏi rõ ràng.
2. **Phải đo được** — mỗi metric phải có công thức tính cụ thể và có thể tự động hóa.
3. **Phải actionable** — kết quả metric phải chỉ ra được cần cải thiện ở đâu.
4. **Fit với kiến trúc** — không áp dụng metrics dành cho RAG có generation vào hệ thống context-only.

---

## 2. Retrieval Quality Metrics

Đây là nhóm metrics quan trọng nhất. Đo lường khả năng tìm đúng documents từ knowledge base.

### 2.1 Hit Rate @k (Recall @k)

**Câu hỏi**: *"Trong top-k kết quả, có chứa document đúng không?"*

**Công thức**:

```
Hit Rate @k = (Số queries có ít nhất 1 relevant doc trong top-k) / (Tổng số queries)
```

**Giải thích**: Đây là metric đơn giản nhất nhưng nền tảng nhất. Nó trả lời câu hỏi: *"RAG có tìm được document cần thiết không?"* mà không quan tâm document đó nằm ở vị trí nào trong top-k.

**Ví dụ minh họa**:

| Query | Top-5 Results | Relevant Doc | Hit @5? |
|-------|--------------|--------------|---------|
| "S3 public access" | [A, **B✓**, C, D, E] | B | Yes |
| "KMS key rotation" | [X, Y, Z, W, V] | M | No |

- Nếu 8/10 queries hit → Hit Rate @5 = 80%

**Tại sao cần**: Hit Rate @k cho biết "ceiling" — nếu document đúng không nằm trong top-k thì mọi bước sau (rerank, context build) đều vô nghĩa. Đây là điều kiện cần (necessary condition).

**Giá trị k nên đo**: k = 1, 3, 5. Trong hệ thống hiện tại, ContextBuilder thường lấy top-5 checks để build bundle, nên Hit Rate @5 là ngưỡng quan trọng nhất.

**Hệ thống hiện tại đang đo**: Có (gọi là Top-k Accuracy). Checks Top-1 = 65.85%, Top-5 = 85.37%.

---

### 2.2 Mean Reciprocal Rank (MRR)

**Câu hỏi**: *"Document đúng nằm ở vị trí cao hay thấp trong danh sách kết quả?"*

**Công thức**:

```
MRR = (1/N) × Σ (1 / rank_i)

Trong đó:
- N = tổng số queries
- rank_i = vị trí của relevant document đầu tiên cho query i
- Nếu không tìm thấy relevant doc → 1/rank_i = 0
```

**Giải thích**: MRR đo **vị trí trung bình** của kết quả đúng đầu tiên. Khác với Hit Rate chỉ hỏi "có hay không", MRR hỏi thêm "nằm ở đâu". Document đúng ở vị trí 1 cho điểm 1.0, vị trí 2 cho điểm 0.5, vị trí 3 cho 0.33, vị trí 5 cho 0.2.

**Ví dụ minh họa**:

| Query | Vị trí doc đúng | Reciprocal Rank |
|-------|-----------------|-----------------|
| Q1: "S3 encryption at rest" | 1 | 1/1 = 1.0 |
| Q2: "IAM password policy" | 3 | 1/3 = 0.33 |
| Q3: "EC2 security group" | 2 | 1/2 = 0.5 |
| Q4: "RDS backup encryption" | Không tìm thấy | 0 |

MRR = (1.0 + 0.33 + 0.5 + 0) / 4 = **0.458**

**Tại sao cần**: MRR bổ sung cho Hit Rate. Hai hệ thống có thể cùng Hit Rate @5 = 80%, nhưng hệ thống A có MRR = 0.9 (hầu hết ở vị trí 1) còn hệ thống B có MRR = 0.3 (hầu hết ở vị trí 4-5). Hệ thống A rõ ràng tốt hơn vì agent nhận được document đúng ở vị trí cao nhất → confidence cao hơn.

**Đặc biệt quan trọng với hệ thống hiện tại** vì: Confidence thresholds phụ thuộc nặng vào top-1 score. Nếu MRR thấp (document đúng thường ở vị trí 2-3 thay vì 1), confidence sẽ bị degrade mặc dù retrieval thực ra đã tìm đúng.

---

### 2.3 Normalized Discounted Cumulative Gain (NDCG @k)

**Câu hỏi**: *"Thứ tự xếp hạng tổng thể có tốt không? Các documents quan trọng có được xếp lên trên không?"*

**Công thức**:

```
DCG @k = Σ(i=1 đến k) [rel_i / log2(i + 1)]

NDCG @k = DCG @k / IDCG @k

Trong đó:
- rel_i = relevance score của document tại vị trí i (thường 0 hoặc 1, hoặc graded 0-3)
- IDCG @k = DCG @k của thứ tự sắp xếp lý tưởng (ideal)
- log2(i+1) = discount factor — vị trí càng thấp, đóng góp càng ít
```

**Giải thích**: NDCG là metric **toàn diện nhất** cho ranking quality. Nó không chỉ xét document đúng đầu tiên (như MRR) mà xét **tất cả** documents trong top-k, và **phạt** khi document quan trọng bị xếp thấp.

**Ví dụ minh họa** (binary relevance: relevant=1, not relevant=0):

Query: "S3 public access controls"  
Top-5 results: [Relevant, Not, Relevant, Not, Relevant]  
Relevance vector: [1, 0, 1, 0, 1]

```
DCG @5 = 1/log2(2) + 0/log2(3) + 1/log2(4) + 0/log2(5) + 1/log2(6)
       = 1.0 + 0 + 0.5 + 0 + 0.387
       = 1.887

Ideal order: [1, 1, 1, 0, 0]
IDCG @5 = 1/log2(2) + 1/log2(3) + 1/log2(4) + 0 + 0
        = 1.0 + 0.631 + 0.5
        = 2.131

NDCG @5 = 1.887 / 2.131 = 0.886
```

**Tại sao cần**: NDCG quan trọng khi **một query có thể có nhiều relevant documents**. Trong hệ thống hiện tại, khi agent query "S3 encryption", có thể có 3-4 checks liên quan (encryption at rest, in transit, KMS key management, bucket default encryption). NDCG đo xem các checks này có được xếp cao trong kết quả hay bị lẫn với các checks không liên quan.

**So sánh với MRR**:
- MRR chỉ quan tâm **document đúng đầu tiên** → phù hợp khi mỗi query có đúng 1 answer.
- NDCG quan tâm **toàn bộ ranking** → phù hợp khi mỗi query có nhiều relevant documents (thực tế của security checks).

**Graded Relevance** (nâng cao): Thay vì binary (0/1), có thể dùng graded relevance:
- 3 = Highly relevant (exact match check cho query)
- 2 = Relevant (cùng domain, cùng service, liên quan trực tiếp)
- 1 = Marginally relevant (cùng service nhưng khác domain)
- 0 = Not relevant

Graded relevance giúp phân biệt giữa "tìm được document liên quan nhưng không phải tốt nhất" và "tìm được document hoàn toàn sai".

---

### 2.4 Mean Average Precision (MAP @k)

**Câu hỏi**: *"Trung bình, các relevant documents được tập trung ở đầu danh sách hay bị phân tán?"*

**Công thức**:

```
Precision @k = (Số relevant docs trong top-k) / k

AP (Average Precision) cho 1 query:
AP = (1/R) × Σ(k=1 đến K) [Precision@k × rel(k)]

Trong đó:
- R = tổng số relevant documents cho query đó
- rel(k) = 1 nếu document tại vị trí k là relevant, 0 nếu không
- Chỉ tính Precision@k tại các vị trí có relevant document

MAP = trung bình AP trên tất cả queries
```

**Giải thích**: MAP đo **mật độ tập trung** của relevant documents ở đầu danh sách. Nếu tất cả relevant documents nằm ở vị trí 1, 2, 3 thì AP cao. Nếu chúng nằm rải rác ở vị trí 1, 5, 10 thì AP thấp.

**Ví dụ minh họa**:

Query: "S3 access control" — có 3 relevant docs trong corpus (R=3)

**Hệ thống A**: [R, R, R, -, -] (3 relevant docs ở top-3)
```
AP = (1/3) × [P@1×1 + P@2×1 + P@3×1]
   = (1/3) × [1/1 + 2/2 + 3/3]
   = (1/3) × [1.0 + 1.0 + 1.0] = 1.0
```

**Hệ thống B**: [R, -, -, R, R] (relevant docs ở vị trí 1, 4, 5)
```
AP = (1/3) × [P@1×1 + P@4×1 + P@5×1]
   = (1/3) × [1/1 + 2/4 + 3/5]
   = (1/3) × [1.0 + 0.5 + 0.6] = 0.7
```

**Tại sao cần**: MAP đặc biệt hữu ích khi đánh giá ContextBuilder. ContextBuilder lấy top-k results và build bundle — nếu relevant documents tập trung ở đầu (MAP cao), bundle sẽ chứa ít noise hơn và agent nhận được context chất lượng hơn.

---

### 2.5 Tổng kết Retrieval Metrics — Mỗi metric trả lời câu hỏi gì?

| Metric | Câu hỏi | Khi nào dùng | Giá trị lý tưởng |
|--------|---------|-------------|-------------------|
| **Hit Rate @k** | Có tìm được doc đúng? | Kiểm tra baseline | 1.0 |
| **MRR** | Doc đúng ở vị trí nào? | Đánh giá ranking top-1 | 1.0 |
| **NDCG @k** | Ranking tổng thể tốt không? | Đánh giá khi có nhiều relevant docs | 1.0 |
| **MAP @k** | Relevant docs có tập trung ở đầu? | Đánh giá context quality tiềm năng | 1.0 |

**Recommendation**: Với hệ thống hiện tại, **MRR + NDCG @5** là cặp metrics tối thiểu cần thiết. MRR đánh giá ranking cho single-answer queries (exact lookup), NDCG @5 đánh giá ranking cho multi-answer queries (semantic search). Hit Rate @5 nên giữ lại vì đã có sẵn và dễ hiểu.

---

## 3. Context Quality Metrics

Nhóm metrics này đo lường chất lượng context bundle mà ContextBuilder tạo ra cho agent. Đây là lớp đánh giá đặc thù của hệ thống — các RAG framework phổ thông thường không có vì chúng đo generation quality thay vì context quality.

### 3.1 Context Precision

**Câu hỏi**: *"Trong context bundle gửi cho agent, bao nhiêu phần trăm là thông tin relevant?"*

**Công thức**:

```
Context Precision = (Số relevant items trong bundle) / (Tổng số items trong bundle)
```

**Giải thích**: Context Precision đo **độ sạch** (purity) của context bundle. Bundle lý tưởng chỉ chứa thông tin relevant — không có noise, không có false positives. Trong hệ thống hiện tại, "items" có thể là checks, capabilities, hoặc mappings trong bundle.

**Ví dụ**: Agent query "S3 public access". ContextBuilder trả về bundle chứa:
- 3 checks liên quan đến S3 public access ✓
- 1 check liên quan đến S3 encryption ✗ (noise)
- 2 capabilities relevant ✓

Context Precision (checks) = 3/4 = 75%

**Tại sao cần**: Context có noise sẽ khiến agent bị phân tán, tốn token, và có thể đưa ra đánh giá sai. Đặc biệt quan trọng với hệ thống hiện tại vì agent sử dụng LLM có context window giới hạn — mỗi item noise trong bundle đều chiếm chỗ của thông tin hữu ích.

**Liên hệ với metrics hiện tại**: Forbidden Capability Rate (hiện = 0%) là một dạng đặc biệt của Context Precision — đo false positive nghiêm trọng nhất (cross-service mapping sai). Context Precision mở rộng phạm vi đo sang tất cả items, không chỉ forbidden items.

### 3.2 Context Recall

**Câu hỏi**: *"Trong tất cả thông tin relevant có trong knowledge base, bundle có bao gồm đủ không?"*

**Công thức**:

```
Context Recall = (Số relevant items có trong bundle) / (Tổng số relevant items trong knowledge base)
```

**Giải thích**: Context Recall đo **độ đầy đủ** (completeness) của context bundle. Bundle có thể rất sạch (Precision = 100%) nhưng thiếu thông tin quan trọng (Recall thấp).

**Ví dụ**: Với query "S3 encryption", knowledge base có 4 checks relevant:
1. S3 default encryption ✓ (có trong bundle)
2. S3 bucket encryption in transit ✓
3. S3 KMS key management ✗ (thiếu)
4. S3 object lock encryption ✗ (thiếu)

Context Recall = 2/4 = 50% — agent chỉ nhận được nửa thông tin cần thiết.

**Tại sao cần**: Agent cần **đủ** context để đưa ra đánh giá toàn diện. Nếu Context Recall thấp, agent sẽ bỏ sót các security controls quan trọng — đây là rủi ro nghiêm trọng trong security assessment.

**Thách thức**: Để đo Context Recall, cần có **ground truth** — danh sách tất cả relevant items cho mỗi query. Điều này đòi hỏi expert annotation. Có thể bắt đầu với một tập nhỏ queries đã được annotate đầy đủ.

### 3.3 Context Relevance Score

**Câu hỏi**: *"Trung bình, mỗi item trong bundle relevant đến mức nào với query?"*

**Công thức**:

```
Context Relevance = (1/N) × Σ relevance_score(item_i, query)

Trong đó relevance_score có thể được tính bằng:
- CrossEncoder score (đã có sẵn trong pipeline)
- Cosine similarity giữa query embedding và item embedding
- Human annotation (0-3 scale)
```

**Giải thích**: Khác với Context Precision (binary: relevant/not relevant), Context Relevance Score đo **mức độ** relevant trên thang liên tục. Một check có thể "hơi liên quan" (score 0.3) hoặc "rất liên quan" (score 0.9).

**Tại sao cần**: Đặc biệt hữu ích để phát hiện các trường hợp "technically relevant but practically unhelpful". Ví dụ: check về "S3 lifecycle policy" technically liên quan đến S3 nhưng không hữu ích khi agent hỏi về "S3 public access".

**Lợi thế triển khai**: Hệ thống đã có CrossEncoder cho reranking — có thể tái sử dụng cross-encoder scores làm proxy cho relevance scoring mà không cần infrastructure mới.

---

## 4. Robustness Metrics

Nhóm metrics đo lường **độ bền** của hệ thống trước các biến thể query. Đây là nhóm metrics thường bị bỏ qua nhưng rất quan trọng trong production.

### 4.1 Query Robustness (Cross-Category Consistency)

**Câu hỏi**: *"Hệ thống có hoạt động nhất quán trên các loại query khác nhau không?"*

**Công thức**:

```
Robustness Gap = max(metric_by_category) - min(metric_by_category)

Ví dụ với Top-1 Accuracy:
- Exact: 100%
- Paraphrase: 66.7%
- Risk: 16.7%
- Semantic Hard: 25%

Robustness Gap = 100% - 16.7% = 83.3pp
```

**Giải thích**: Robustness Gap đo **khoảng cách hiệu suất** giữa category tốt nhất và tệ nhất. Gap càng nhỏ, hệ thống càng ổn định. Gap lớn cho thấy hệ thống chỉ hoạt động tốt với một kiểu query cụ thể và sẽ fail khi user query theo cách khác.

**Phân tích hệ thống hiện tại**: Robustness Gap = 83.3pp là **rất lớn**, cho thấy:
- Hệ thống phụ thuộc nặng vào keyword matching (Exact query tốt, Semantic query kém).
- Risk queries (mô tả rủi ro thay vì tên check) gần như không hoạt động ở Top-1.
- Đây là **điểm yếu nghiêm trọng nhất** hiện tại và nên là ưu tiên tối ưu hóa.

**Tại sao cần**: Trong production, user không query theo một pattern cố định. Agent downstream có thể gửi paraphrase, risk description, hoặc semantic query. Hệ thống cần xử lý tốt tất cả các loại.

### 4.2 Service Precision

**Câu hỏi**: *"Kết quả top-1 có đúng service được hỏi không?"*

**Công thức**:

```
Service Precision = (Số queries có top-1 result đúng service) / (Tổng số queries có service constraint)
```

**Giải thích**: Đây là metric **safety-critical** trong security assessment. Nếu agent hỏi về S3 mà RAG trả về IAM check → agent sẽ đánh giá sai dịch vụ → security gap.

**Hệ thống hiện tại**: Service Precision = 87.8%. Product Gate đã được triển khai để filter cross-service results, nhưng vẫn còn 12.2% cases bị sai service.

**Tại sao cần**: Đây là metric không thể trade-off. Trong security assessment, trả về kết quả sai service còn tệ hơn không trả về gì — vì nó tạo ra false sense of security.

### 4.3 Confidence Calibration

**Câu hỏi**: *"Confidence score có phản ánh đúng chất lượng thực tế không?"*

**Cách đo**:

```
1. Nhóm queries theo confidence level (High/Medium/Low)
2. Tính accuracy thực tế cho mỗi nhóm
3. So sánh:

Confidence Level | Expected Accuracy | Actual Accuracy | Calibrated?
High             | >80%              | ?%              | ?
Medium           | 50-80%            | ?%              | ?
Low              | <50%              | ?%              | ?
```

**Giải thích**: Confidence Calibration đo xem **hệ thống có "biết" khi nào nó sai không**. Hệ thống well-calibrated sẽ:
- Gán High confidence → hầu hết kết quả đúng
- Gán Low confidence → hệ thống thực sự không chắc chắn

Hệ thống poorly-calibrated sẽ gán High confidence cho cả kết quả đúng lẫn sai → agent không thể tin vào confidence signal.

**Tại sao cần**: Downstream agents dùng confidence để quyết định có cần human review không. Nếu confidence không calibrated:
- High confidence + wrong result → agent tin kết quả sai → security risk
- Low confidence + correct result → agent request human review không cần thiết → inefficiency

**Phân tích hiện tại**: S3 Agent Readiness cho thấy 0% High, 100% Medium — confidence thresholds có thể quá strict, cần calibration.

---

## 5. System Performance Metrics

### 5.1 Latency

**Câu hỏi**: *"Hệ thống có đủ nhanh cho production use không?"*

**Các percentile cần đo**:

| Metric | Giải thích | Target hiện tại |
|--------|-----------|-----------------|
| **P50 (Median)** | 50% requests nhanh hơn giá trị này | ≤ 1,500ms |
| **P90** | 90% requests nhanh hơn | ≤ 2,500ms |
| **P99** | 99% requests nhanh hơn (worst case) | ≤ 5,000ms |
| **Mean** | Trung bình (bị ảnh hưởng bởi outliers) | ≤ 2,000ms |

**Giải thích**: P50 cho biết trải nghiệm "typical", P90 cho biết trải nghiệm "bad day", P99 cho biết worst case. Chỉ đo Mean là không đủ vì Mean bị kéo bởi outliers — 99% requests có thể nhanh nhưng 1% cực chậm sẽ kéo mean lên.

**Tại sao cần**: RAG là bước giữa trong pipeline agent. Latency RAG cộng dồn với latency LLM inference. Nếu RAG mất 3s + LLM mất 5s → total 8s → user experience kém.

**Breakdown quan trọng**: Nên đo latency từng stage:

```
BM25 search:        ~Xms
Vector search:      ~Xms  
(song song, lấy max)
RRF merge:          ~Xms
CrossEncoder:       ~Xms  ← thường là bottleneck
ContextBuilder:     ~Xms  ← sequential per-check, cũng chậm
Total:              ~Xms
```

### 5.2 Throughput

**Câu hỏi**: *"Hệ thống xử lý được bao nhiêu requests đồng thời?"*

**Metrics**:

```
- Requests per second (RPS) ở sustained load
- Max concurrent requests trước khi degrade
```

**Tại sao cần**: Khi nhiều agents chạy song song (ví dụ: đánh giá 10 AWS accounts cùng lúc), hệ thống cần handle nhiều requests đồng thời mà không degrade quality.

---

## 6. Metrics Không Chọn và Lý Do

Các metrics dưới đây phổ biến trong RAG evaluation nhưng **không phù hợp** với hệ thống hiện tại:

### 6.1 Faithfulness / Groundedness

**Đo gì**: Câu trả lời sinh ra có dựa trên context không (có bịa không).  
**Tại sao không chọn**: Hệ thống không có generation layer. RAG chỉ trả context, không sinh câu trả lời. Faithfulness nên đo ở agent layer, không phải RAG layer.

### 6.2 Answer Correctness / Answer Relevance

**Đo gì**: Câu trả lời có đúng không, có liên quan đến câu hỏi không.  
**Tại sao không chọn**: Tương tự — không có "answer" ở RAG layer. Các metrics này thuộc về agent evaluation, không phải RAG evaluation.

### 6.3 BLEU / ROUGE / BERTScore

**Đo gì**: Similarity giữa generated text và reference text.  
**Tại sao không chọn**: Đây là text generation metrics, không áp dụng cho retrieval system.

### 6.4 Aspect Critique (Harmfulness, Maliciousness)

**Đo gì**: Câu trả lời có harmful hoặc biased không.  
**Tại sao không chọn**: Không có generation → không có risk of harmful output từ RAG layer.

---

## 7. Framework Đánh Giá Tổng Hợp

### 7.1 Metrics Core — Bảng tóm tắt

| # | Metric | Nhóm | Câu hỏi chính | Ưu tiên |
|---|--------|------|----------------|---------|
| 1 | **Hit Rate @k** | Retrieval | Tìm được doc đúng không? | P0 — Phải có |
| 2 | **MRR** | Retrieval | Doc đúng ở vị trí nào? | P0 — Phải có |
| 3 | **NDCG @5** | Retrieval | Ranking tổng thể tốt không? | P0 — Phải có |
| 4 | **Service Precision** | Robustness | Đúng service không? | P0 — Safety-critical |
| 5 | **Context Precision** | Context | Bundle có sạch không? | P1 — Nên có |
| 6 | **Context Recall** | Context | Bundle có đủ không? | P1 — Nên có |
| 7 | **Robustness Gap** | Robustness | Nhất quán giữa các loại query? | P1 — Nên có |
| 8 | **Confidence Calibration** | Robustness | Confidence có đáng tin? | P1 — Nên có |
| 9 | **Latency P50/P90** | System | Có đủ nhanh không? | P0 — Phải có |
| 10 | **MAP @k** | Retrieval | Relevant docs tập trung ở đầu? | P2 — Tùy chọn |

### 7.2 Release Criteria (đề xuất cập nhật)

Dựa trên metrics đã chọn, đề xuất bổ sung release criteria:

| Criterion | Threshold | Ghi chú |
|-----------|-----------|---------|
| Hit Rate @5 (Checks) | ≥ 85% | Giữ nguyên |
| Hit Rate @5 (Maturity) | ≥ 80% | Giữ nguyên |
| **MRR (Combined)** | ≥ 0.70 | **Mới** — đảm bảo doc đúng ở vị trí cao |
| **NDCG @5 (Combined)** | ≥ 0.75 | **Mới** — đảm bảo ranking quality |
| Service Precision | ≥ 85% | Giữ nguyên |
| Forbidden Capability Rate | = 0% | Giữ nguyên |
| Empty Bundle Rate | = 0% | Giữ nguyên |
| **Robustness Gap (Top-1)** | ≤ 50pp | **Mới** — giảm khoảng cách giữa categories |
| Latency P50 | ≤ 1,500ms | Giữ nguyên (điều chỉnh target) |
| Latency P90 | ≤ 3,000ms | **Mới** — đo worst case |

### 7.3 Đánh giá theo stage

Để tối ưu hóa hiệu quả, nên đo metrics tại từng stage:

```
┌─────────────────────────────────────────────────────────┐
│  Stage 1: Retrieval (BM25 + Vector + RRF)               │
│  Metrics: Hit Rate, MRR, NDCG (đo trước rerank)         │
│  → Trả lời: Raw retrieval có tốt không?                 │
├─────────────────────────────────────────────────────────┤
│  Stage 2: Reranking (CrossEncoder)                       │
│  Metrics: NDCG lift, MRR lift (so sánh trước/sau rerank)│
│  → Trả lời: Reranker có cải thiện ranking không?         │
├─────────────────────────────────────────────────────────┤
│  Stage 3: Context Build                                  │
│  Metrics: Context Precision, Context Recall              │
│  → Trả lời: Bundle cuối cùng có chất lượng không?        │
├─────────────────────────────────────────────────────────┤
│  Stage 4: End-to-End                                     │
│  Metrics: Service Precision, Confidence Calibration,     │
│           Latency, Robustness Gap                        │
│  → Trả lời: Tổng thể hệ thống sẵn sàng production?      │
└─────────────────────────────────────────────────────────┘
```

**Reranker Lift** là metric đặc biệt quan trọng:

```
NDCG Lift = NDCG_after_rerank - NDCG_before_rerank
MRR Lift  = MRR_after_rerank  - MRR_before_rerank
```

Nếu lift ≤ 0 → reranker không đóng góp → có thể bỏ để giảm latency.
Nếu lift lớn → reranker quan trọng → cần giữ nhưng tối ưu tốc độ.

---

## 8. Ground Truth và Annotation

### 8.1 Yêu cầu Ground Truth

Tất cả metrics trên đều cần **ground truth** — tức labels đúng cho mỗi query. Hệ thống hiện tại đã có ground truth cho:

| Dữ liệu | Có sẵn | Nguồn |
|----------|--------|-------|
| Expected doc_id (single) | ✓ | benchmark_cases.json |
| Expected capability_id | ✓ | benchmark_cases.json |
| Forbidden capabilities | ✓ | benchmark_cases.json |
| Expected service | ✓ | benchmark_cases.json |
| **Multi-relevant docs** | ✗ | Cần annotation mới |
| **Graded relevance** | ✗ | Cần annotation mới |
| **Context ground truth** | ✗ | Cần annotation mới |

### 8.2 Chiến lược bổ sung Ground Truth

**Phase 1 — Binary multi-relevance** (ưu tiên cao):
- Với mỗi query trong benchmark_cases.json, annotation thêm field `all_relevant_doc_ids` (list thay vì single).
- Cho phép tính NDCG và MAP với binary relevance.
- Effort: ~2-4 giờ cho 60 cases.

**Phase 2 — Graded relevance** (ưu tiên trung bình):
- Annotation relevance score (0-3) cho top-10 results của mỗi query.
- Cho phép tính NDCG với graded relevance.
- Effort: ~4-8 giờ cho 60 × 10 = 600 judgments.

**Phase 3 — Context ground truth** (ưu tiên thấp):
- Annotation expected bundle content cho subset of queries.
- Cho phép tính Context Precision và Context Recall.
- Effort: ~4-6 giờ cho 20 cases.

---

## 9. So Sánh Với Các RAG Evaluation Frameworks Phổ Biến

| Framework | Metrics chính | Phù hợp? | Ghi chú |
|-----------|---------------|-----------|---------|
| **RAGAS** | Faithfulness, Answer Relevance, Context Precision/Recall | Một phần | Context metrics phù hợp, Answer/Faithfulness metrics không áp dụng (no generation) |
| **ARES** | LLM-as-judge cho context relevance, answer faithfulness | Ít | Thiết kế cho end-to-end QA, quá nặng cho retrieval-only system |
| **BEIR** | NDCG, Recall, MAP trên diverse datasets | Có | Retrieval metrics phù hợp, nhưng benchmark datasets không relevant (general domain) |
| **MTEB** | Embedding quality trên standard benchmarks | Một phần | Đo embedding model, không đo full pipeline |
| **Custom (đề xuất)** | Hit Rate + MRR + NDCG + Service Precision + Context P/R + Robustness + Latency | **Tốt nhất** | Thiết kế riêng cho kiến trúc context-only RAG serving agents |

**Kết luận**: Không framework nào sẵn có phù hợp hoàn toàn. Nên xây dựng custom framework lấy retrieval metrics từ IR tradition (NDCG, MRR, MAP) và context metrics lấy cảm hứng từ RAGAS, kết hợp với domain-specific metrics (Service Precision, Robustness Gap, Confidence Calibration).

---

## 10. Kế Hoạch Triển Khai

### Phase 1 — Quick Wins (tuần 1)

- [ ] Bổ sung MRR vào benchmark runner (đã có infrastructure, chỉ cần tính thêm)
- [ ] Bổ sung NDCG @5 với binary relevance (dùng existing `expected_doc_id`)
- [ ] Thêm latency P50/P90 vào benchmark report
- [ ] Tính Robustness Gap từ existing category breakdown

### Phase 2 — Ground Truth Enhancement (tuần 2-3)

- [ ] Annotation `all_relevant_doc_ids` cho 60 benchmark cases
- [ ] Re-run NDCG và MAP với multi-relevance ground truth
- [ ] Thêm Reranker Lift metric (đo NDCG trước/sau rerank)

### Phase 3 — Context Metrics (tuần 3-4)

- [ ] Annotation expected bundle content cho 20 queries
- [ ] Implement Context Precision và Context Recall measurement
- [ ] Confidence Calibration analysis

---

*Tài liệu tham khảo*:
- Manning, Raghavan, Schütze — "Introduction to Information Retrieval" (MRR, NDCG, MAP definitions)
- RAGAS framework — Context Precision / Context Recall concepts
- BEIR benchmark — Retrieval evaluation methodology

*Cập nhật lần cuối*: 02/04/2026
