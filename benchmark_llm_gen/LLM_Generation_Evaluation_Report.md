# Báo cáo Nghiên cứu: Framework Đánh giá LLM Generation trong Hệ thống RAG-Agent

> **Mục đích:** Xác định khung đánh giá (evaluation framework) cho chất lượng sinh văn bản của các agent khi sử dụng RAG context. Tài liệu này tập trung vào việc chốt **hướng đi đúng** và **chọn metrics core** để triển khai thực tế.
>
> **Phạm vi:** Hệ thống PDCA Security Assessment gồm 3 agent: Planning, Risk Evaluation, Report — tất cả sử dụng RAG để cung cấp context cho LLM.
>
> **Trạng thái hiện tại:** Retrieval evaluation đã hoàn thành (13/13 release criteria PASS). Generation evaluation chưa có.

---

## Mục lục

1. [Bối cảnh và Động lực](#1-bối-cảnh-và-động-lực)
2. [Khung Đánh giá Tổng quát (Evaluation Framework)](#2-khung-đánh-giá-tổng-quát)
3. [Core Metrics — Định nghĩa và Giải thích](#3-core-metrics--định-nghĩa-và-giải-thích)
   - 3.1 Structured Output Compliance
   - 3.2 Faithfulness
   - 3.3 Correctness
   - 3.4 Completeness
4. [Agent-specific Instantiation](#4-agent-specific-instantiation)
5. [Extension Layer — Hướng mở rộng](#5-extension-layer--hướng-mở-rộng)
6. [Tham khảo](#6-tham-khảo)

---

## 1. Bối cảnh và Động lực

### 1.1 Hệ thống hiện tại

```
User Request
  -> Planning Agent  (RAG: PlanningBundle → chọn Prowler checks hoặc group scan)
  -> Scanner Agent   (gọi Prowler API)
  -> Risk Agent      (RAG: RiskBundle → chấm điểm severity + reasoning)
  -> Remediation     (thực thi sửa lỗi)
  -> Report Agent    (RAG: ReportBundle → sinh báo cáo tổng hợp)
```

Mỗi agent có thể gọi RAG qua `build_context(consumer=...)` để nhận context bundle. Cách sử dụng context khác nhau: Risk Agent và Report Agent truyền trực tiếp vào LLM prompt, trong khi Planning Agent kết hợp RAG context với logic nội bộ (scoring, classification) và chỉ gọi LLM khi cần.

### 1.2 Tại sao cần đánh giá generation?

Retrieval evaluation trả lời: *"RAG có tìm đúng tài liệu không?"*
Generation evaluation trả lời: *"Agent có sử dụng context đúng cách để sinh output chất lượng không?"*

Một hệ thống có retrieval tốt nhưng generation kém vẫn thất bại:
- RAG trả về đúng check `s3_bucket_public_access`, nhưng Planning Agent không chọn nó.
- RAG cung cấp severity "Critical", nhưng Risk Agent đánh giá "Medium" mà không có lý do.
- RAG trả về đầy đủ findings, nhưng Report Agent sinh báo cáo thiếu thông tin hoặc bịa đặt (hallucination).

### 1.3 Nguyên tắc thiết kế framework

| Nguyên tắc | Giải thích |
|---|---|
| **Khung chung trước, agent-specific sau** | Định nghĩa 4 trục đánh giá chung, sau đó mới concretize metric cụ thể cho từng agent |
| **Core tách biệt khỏi extension** | Chỉ một số ít metrics để triển khai thật, phần còn lại là hướng mở rộng |
| **Chất lượng hơn số lượng** | Mỗi metric phải trả lời một câu hỏi rõ ràng, không chồng chéo |
| **Actionable** | Kết quả metric phải chỉ ra được điểm cần cải thiện cụ thể |

---

## 2. Khung Đánh giá Tổng quát

### 2.1 Bốn trục đánh giá (4 Evaluation Dimensions)

Framework đánh giá generation được xây dựng trên **4 trục chung**, áp dụng nhất quán cho mọi agent. Mỗi trục trả lời một câu hỏi khác nhau:

```
 STRUCTURED OUTPUT COMPLIANCE     "Output có đúng định dạng không?"
         |                         (Điều kiện tiên quyết — gate check)
         v
    FAITHFULNESS                   "Output có dựa trên context không?"
         |                         (Phát hiện hallucination)
         v
    CORRECTNESS                    "Output có đúng không?"
         |                         (Kết quả cuối cùng)
         v
    COMPLETENESS                   "Output có đầy đủ không?"
                                   (Không bỏ sót thông tin quan trọng)
```

**Tại sao sắp xếp theo thứ tự này?**

- **Structured Compliance** là gate check: nếu output không parse được JSON hoặc thiếu field bắt buộc, các metric phía sau không thể tính. Đây là điều kiện tiên quyết.
- **Faithfulness** là nền tảng chất lượng: nếu output bịa đặt thông tin không có trong context, việc đo correctness hay completeness đều vô nghĩa.
- **Correctness** đánh giá kết quả: output có thể faithful (dựa trên context) nhưng vẫn sai nếu LLM hiểu sai context hoặc context từ RAG đã sai.
- **Completeness** đánh giá bao phủ: output có thể đúng nhưng chưa đủ — thiếu checks quan trọng, thiếu evidence trong reasoning, thiếu findings trong report.

### 2.2 Core vs Extension

| Phân loại | Metrics | Mục đích |
|---|---|---|
| **Core Layer** (triển khai ngay) | Structured Compliance, Faithfulness, Correctness, Completeness | Framework đánh giá chính, đủ để báo cáo kết quả và ra quyết định |
| **Extension Layer** (hướng mở rộng) | RAG Ablation, G-Eval (coherence/actionability), Counterfactual robustness | Bổ sung thêm góc nhìn khi cần, không bắt buộc cho evaluation cơ bản |

### 2.3 Khung metric thống nhất ở cấp hệ thống

Mỗi trục có một điểm số chung (0–1), tính trung bình có trọng số từ các agent:

```
System Faithfulness   = w1*Faith(Planning) + w2*Faith(Risk) + w3*Faith(Report)
System Correctness    = w1*Corr(Planning)  + w2*Corr(Risk)  + w3*Corr(Report)
System Completeness   = w1*Comp(Planning)  + w2*Comp(Risk)  + w3*Comp(Report)
```

Trong đó `w1, w2, w3` là trọng số phản ánh mức độ quan trọng của từng agent (có thể điều chỉnh, ví dụ Risk Agent có trọng số cao hơn vì ảnh hưởng trực tiếp đến quyết định bảo mật).

Như vậy, có thể trả lời ngắn gọn: *"Overall generation quality của hệ thống là bao nhiêu?"* bằng cách báo cáo 4 con số: Structure, Faithfulness, Correctness, Completeness.

---

## 3. Core Metrics — Định nghĩa và Giải thích

### 3.1 Structured Output Compliance

#### Metric này đo gì?

**"Output của LLM có đúng định dạng và cấu trúc đã định nghĩa không?"**

Đây là metric **deterministic** (tính toán chính xác, không cần LLM judge), chi phí bằng 0, và bắt lỗi nghiêm trọng nhất (output không sử dụng được). Nó đóng vai trò **gate check**: nếu output không hợp lệ về cấu trúc, các metric còn lại không thể tính.

#### Cách tính

**JSON Parse Rate:**
```
Parse Rate = Số output parse được thành JSON hợp lệ / Tổng số output
```
Bất kỳ output nào không parse được đều là failure nghiêm trọng — pipeline sẽ gặp lỗi ngay từ bước đầu.

**Schema Compliance Rate:**
```
Schema Compliance = Số output thỏa mãn đầy đủ JSON schema / Tổng số output parse được
```
Kiểm tra: có đủ field bắt buộc không? Kiểu dữ liệu đúng không? Giá trị trong phạm vi cho phép không?

**Internal Consistency (riêng Risk Agent):**
```
Consistent = ai_severity tương ứng đúng khoảng ai_risk_score
  Critical: 9-10 | High: 7-8 | Medium: 4-6 | Low: 1-3
```
Risk Agent trả về 2 field liên quan (severity và score) — chúng phải nhất quán với nhau theo rubric đã định nghĩa trong system prompt.

#### Ví dụ

```json
// HỢP LỆ: parse OK, schema OK, consistency OK
{"ai_severity": "Critical", "ai_risk_score": 9, "ai_reasoning": "Public access to S3 bucket exposes data."}

// KHÔNG HỢP LỆ: 3 lỗi
{"ai_severity": "CRITICAL", "ai_risk_score": 15, "ai_reasoning": ""}
//  "CRITICAL" không đúng enum (phải là "Critical")
//  15 vượt phạm vi [0-10]
//  reasoning rỗng (bắt buộc phải có nội dung)
```

#### Đặc điểm

| Điểm mạnh | Giới hạn |
|---|---|
| Deterministic — không có variance, không cần LLM judge | Chỉ bắt lỗi **cấu trúc**, không đánh giá **nội dung** |
| Chi phí = 0, chạy được trên mọi test case | Một output đúng schema vẫn có thể sai hoàn toàn về mặt nội dung |
| Dễ tích hợp vào CI/CD | |

---

### 3.2 Faithfulness (Độ trung thực với context)

#### Metric này đo gì?

**"Bao nhiêu phần trăm nội dung trong output có thể xác minh được từ RAG context?"**

Faithfulness là metric **quan trọng nhất** trong hệ thống RAG vì nó trực tiếp phát hiện **hallucination** — khi LLM sinh ra thông tin không tồn tại trong context được cung cấp.

#### Tại sao faithfulness là core metric cho mọi agent?

Mỗi agent đều có phần output dạng văn bản (reasoning, narrative) mà LLM có thể bịa đặt:
- **Planning Agent**: `reasoning` giải thích tại sao chọn check này — có thể bịa đặt lý do không có trong PlanningBundle.
- **Risk Agent**: `ai_reasoning` phân tích rủi ro — có thể trích dẫn compliance mapping không tồn tại trong RiskBundle.
- **Report Agent**: Các đoạn narrative — có thể bịa đặt thông tin vụ việc hoặc số liệu không có trong findings.

#### Cách tính — Claim Decomposition + Verification

Phương pháp này (từ RAGAS framework, Es et al. 2023) gồm 3 bước:

**Bước 1 — Phân tách output thành các claims (mệnh đề nguyên tử)**

Mỗi claim là một nhận định độc lập chỉ chứa một sự kiện. Dùng LLM hoặc evaluator model để phân tách.

Ví dụ — Risk Agent output:
```
"S3 bucket có public access là rủi ro Critical vì dữ liệu nhạy cảm
có thể bị truy cập trái phép. Theo CIS Benchmark 1.3, đây là vi phạm mức độ cao."
```

Phân tách:
1. "S3 bucket có public access" — nhận định về trạng thái
2. "Đây là rủi ro Critical" — nhận định về mức độ
3. "Dữ liệu nhạy cảm có thể bị truy cập trái phép" — nhận định về hậu quả
4. "Theo CIS Benchmark 1.3, đây là vi phạm mức độ cao" — trích dẫn tiêu chuẩn

**Bước 2 — Xác minh từng claim với RAG context**

Với mỗi claim, xác định:
- **Supported**: Context chứa thông tin xác nhận claim này (bao gồm paraphrase và cross-language translation).
- **Not Supported**: Context không chứa thông tin này — LLM tự sinh ra (bao gồm cả trường hợp claim mâu thuẫn context).

> **Ghi chú triển khai:** Framework gốc phân biệt 3 loại (Supported/Not Supported/Contradicted).
> Trong thực tế, "Contradicted" được gộp vào "Not Supported" vì với LLM judge nhỏ (3B params),
> việc phân biệt "không có trong context" vs "ngược lại context" không đủ tin cậy.
> Cả hai đều được tính là not_supported khi chấm điểm.

**Bước 3 — Tính điểm**

```
Faithfulness = (Số claim Supported) / (Tổng số claims)
```

Phạm vi: [0, 1]. Giá trị 1.0 = mọi thứ trong output đều truy nguồn được về RAG context.

#### Ví dụ đánh giá cụ thể

**Input** — RiskBundle context:
```json
{
  "official_severity": "Critical",
  "compliance_mappings": ["CIS_AWS_1.3", "PCI_DSS_3.2"],
  "check_title": "S3 bucket has public read access enabled"
}
```

**Output tốt (Faithfulness = 1.0):**
```
"Public read access cho phép truy cập dữ liệu trái phép.
Theo PCI-DSS 3.2, đây là vi phạm bảo mật cấp cao."
```
| Claim | Kết quả | Lý do |
|---|---|---|
| "Public read access cho phép truy cập trái phép" | Supported | Context có "public read access enabled" |
| "Theo PCI-DSS 3.2, đây là vi phạm cấp cao" | Supported | compliance_mappings có "PCI_DSS_3.2" |

**Output có hallucination (Faithfulness = 0.5):**
```
"Public read access là vi phạm nghiêm trọng.
S3 bucket này đã từng bị data breach vào năm 2023."
```
| Claim | Kết quả | Lý do |
|---|---|---|
| "Public read access là vi phạm nghiêm trọng" | Supported | Context xác nhận severity Critical |
| "Đã từng bị data breach vào năm 2023" | **Not Supported** | Context không nói gì về lịch sử breach |

#### Công cụ thực hiện

| Phương pháp | Chi phí | Độ tin cậy | Khi nào dùng |
|---|---|---|---|
| **LLM-as-Judge** (RAGAS-style) | Cao (nhiều LLM calls) | Cao | Giai đoạn đầu: dễ hiểu, dễ debug, dễ điều chỉnh |
| **NLI Model** (DeBERTa-v3-large) | Thấp (chạy local) | Trung bình | Scale lên khi đã có pipeline ổn định |
| **MiniCheck** (Tang et al. 2024) | Thấp | Cao (~ GPT-4) | Production benchmarking: nhanh + chính xác |

**Khuyến nghị:** Bắt đầu với LLM-as-Judge để hiểu kết quả và debug. Khi pipeline ổn định, chuyển sang MiniCheck hoặc NLI model để giảm chi phí.

> **Thực tế triển khai (Risk Agent):** Sử dụng LLM-as-Judge với **local Ollama model (llama3.2, 3B params)**
> làm judge. Chi phí thấp (chạy local), nhưng judge model nhỏ có hạn chế: khó phân biệt trích dẫn nguồn bịa
> (vd "theo Gartner") vs nhận định chung. Kết quả faithfulness 0.950 — thực tế hơn rule-based (0.983)
> nhưng có thể chưa nghiêm ngặt bằng GPT-4 judge hoặc MiniCheck.

#### Đặc điểm

| Điểm mạnh | Giới hạn |
|---|---|
| Trực tiếp phát hiện hallucination — rủi ro #1 của RAG | Phụ thuộc chất lượng claim decomposition (bước 1) |
| Không cần ground truth (chỉ cần RAG context) | Claims "đúng khách quan" nhưng không có trong context vẫn bị tính Not Supported |
| Áp dụng cho mọi loại output | LLM-as-Judge có chi phí cao và có variance |

---

### 3.3 Correctness (Độ chính xác kết quả)

#### Metric này đo gì?

**"Kết quả cuối cùng của agent có đúng so với kết quả mong đợi (ground truth) không?"**

Faithfulness chỉ kiểm tra "có dựa trên context không", không kiểm tra "có đúng không". Một output có thể faithful (trích dẫn đúng context) nhưng vẫn sai kết quả (vì context từ RAG đã sai, hoặc LLM hiểu sai). Correctness đánh giá **đáp án cuối cùng**.

#### Đây là trục phụ thuộc agent nhiều nhất

Mỗi agent có loại output khác nhau, nên cách đo correctness cũng khác:

| Agent | Loại output | Bài toán tương ứng | Metric cụ thể |
|---|---|---|---|
| Planning | List of check IDs | Set selection / recommendation | Precision, Recall, F1 |
| Risk | Severity label (4 mức) | Ordinal classification | Accuracy, QWK |
| Report | HTML5 document (template + LLM narrative) | Hybrid: deterministic + open-ended | Core: deterministic data accuracy. Extension: LLM judge |

Tuy cách đo khác nhau, nhưng **ý nghĩa trục "Correctness" là nhất quán**: output có đúng không?

---

##### Planning Agent — Check Selection F1

Planning Agent output `checks_to_scan` (list of check IDs). So sánh với ground truth (expert-labeled relevant checks):

```
Precision = |Selected ∩ Relevant| / |Selected|
  "Trong các checks agent chọn, bao nhiêu là đúng?"

Recall = |Selected ∩ Relevant| / |Relevant|
  "Trong các checks cần chọn, agent tìm được bao nhiêu?"

F1 = 2 * Precision * Recall / (Precision + Recall)
  Cân bằng giữa chính xác và bao phủ.
```

**Ví dụ:**
```
Ground truth: [s3_bucket_public_access, s3_bucket_versioning, s3_bucket_encryption]
Agent output: [s3_bucket_public_access, s3_bucket_encryption, s3_bucket_logging]

Precision = 2/3 = 0.67
Recall    = 2/3 = 0.67
F1        = 0.67
```

F1 là metric tổng hợp tốt nhất cho Planning Agent vì nó phát cả hai loại lỗi: chọn sai (precision thấp) và bỏ sót (recall thấp).

---

##### Risk Agent — Severity Accuracy + Quadratic Weighted Kappa (QWK)

Risk Agent output `ai_severity` (Critical/High/Medium/Low). Đây là bài toán **ordinal classification** — phân loại theo thứ tự.

**Accuracy:**
```
Accuracy = Số dự đoán đúng / Tổng số dự đoán
```
Đơn giản nhưng có nhược điểm: coi "sai 1 bậc" (High thay vì Critical) giống như "sai 3 bậc" (Low thay vì Critical).

**Quadratic Weighted Kappa (QWK) — metric chính:**

QWK là metric **thiết kế riêng cho ordinal classification**. Nó phạt **nặng hơn** khi dự đoán sai xa, và phạt **nhẹ** khi sai gần:

| Dự đoán | Ground truth | Khoảng cách | QWK penalty |
|---|---|---|---|
| High | Critical | 1 bậc | Nhẹ |
| Medium | Critical | 2 bậc | Nặng |
| Low | Critical | 3 bậc | Rất nặng |

```
QWK = 1 - (Tổng trọng số bất đồng ý thực tế) / (Tổng trọng số bất đồng ý kỳ vọng)
```

Phạm vi: [-1, 1]. Giá trị 1.0 = đồng ý hoàn hảo, 0 = ngẫu nhiên, <0 = tệ hơn ngẫu nhiên.

**Tại sao QWK phù hợp?** Trong đánh giá rủi ro bảo mật, nhầm "Critical" thành "Low" nguy hiểm hơn nhiều so với nhầm thành "High". QWK phản ánh đúng mức độ nghiêm trọng của sai số này, trong khi Accuracy thì không.

---

##### Report Agent — Dual-layer Correctness

Report Agent output gồm 2 phần: (1) **template-rendered** (tables, cover page, charts, stats) — deterministic, kiểm tra chính xác bằng parsing; (2) **LLM narrative** (executive summary, analysis, recommendations) — free text, cần LLM judge.

*Deterministic correctness (core):*
- Bảng findings có đúng số dòng? Severity badges đúng case? Status colors đúng?
- Security Score trên cover page = `_calc_score(pre, post)`?
- Số liệu thống kê (total, pass, fail, fixed) khớp `report_data`?

*LLM-based correctness (extension):*
```
Prompt cho judge:
"So sánh phần narrative của report với dữ liệu findings/remediation gốc.
Narrative có trình bày đúng các sự kiện và kết quả không?
Score 1-5. Giải thích lý do."
```

Deterministic correctness là **core metric** (chi phí = 0, bắt regression). LLM judge thuộc **extension layer** (chi phí cao, chỉ đánh giá narrative).

---

### 3.4 Completeness (Độ đầy đủ)

#### Metric này đo gì?

**"Output có bao phủ đầy đủ thông tin quan trọng không, hay bỏ sót điều gì?"**

Completeness khác với Correctness: một output có thể **đúng nhưng chưa đủ**. Ví dụ:
- Planning Agent chọn đúng 2 checks, nhưng bỏ sót 3 checks quan trọng khác.
- Risk Agent đánh giá đúng severity, nhưng reasoning chỉ nói một câu chung chung, không đề cập compliance mapping có trong context.
- Report Agent viết đúng về 5 findings, nhưng bỏ qua 3 findings khác.

#### Tại sao Completeness là core metric chung?

Completeness không chỉ dành cho Report Agent — nó là vấn đề chung của mọi agent:

| Agent | Completeness đo gì? |
|---|---|
| **Planning** | Có bỏ sót check quan trọng nào không? (Recall trong F1 đã bao phủ phần này) |
| **Risk** | Reasoning có đề cập đủ các evidence chính từ RiskBundle không? (compliance mappings, maturity context) |
| **Report** | Report có bao phủ đủ findings và remediations không? |

#### Cách tính — Evidence Checklist

Phương pháp đơn giản và thực tế nhất: định nghĩa trước **danh sách evidence cần có** (evidence checklist) cho mỗi test case, rồi đếm tỷ lệ bao phủ.

**Bước 1 — Định nghĩa evidence checklist trong ground truth**

Mỗi test case có một trường `required_evidence`: danh sách các điểm mà output **phải đề cập**.

Ví dụ — Risk Agent test case:
```json
{
  "input": { "check_id": "s3_bucket_public_access", "..." : "..." },
  "rag_context": {
    "official_severity": "Critical",
    "compliance_mappings": ["CIS_AWS_1.3", "PCI_DSS_3.2"]
  },
  "expected": {
    "ai_severity": "Critical",
    "required_evidence": [
      "đề cập severity Critical hoặc rủi ro cao",
      "trích dẫn ít nhất 1 compliance mapping (CIS hoặc PCI-DSS)",
      "mô tả hậu quả của public access"
    ]
  }
}
```

**Bước 2 — Kiểm tra từng evidence trong output**

Có thể dùng:
- **Keyword matching** (đơn giản, nhanh): kiểm tra output có chứa "PCI-DSS" hoặc "CIS" không.
- **LLM-as-judge** (chính xác hơn): hỏi LLM "Output có đề cập đến [evidence item] không? Yes/No."

**Bước 3 — Tính điểm**

```
Completeness = (Số evidence items được đề cập) / (Tổng số required evidence)
```

#### Ví dụ

**Risk Agent output:**
```
"S3 bucket có public access là rủi ro Critical. Theo PCI-DSS 3.2, đây là vi phạm nghiêm trọng."
```

| Evidence item | Có trong output? |
|---|---|
| "Đề cập severity Critical" | Yes — "rủi ro Critical" |
| "Trích dẫn compliance mapping" | Yes — "PCI-DSS 3.2" |
| "Mô tả hậu quả public access" | No — chỉ nói "rủi ro" chung chung |

Completeness = 2/3 = 0.67

**Nhận xét:** Output đúng (Correctness cao) và faithful (không bịa đặt), nhưng **chưa đủ** — thiếu phân tích hậu quả cụ thể. Đây là thông tin mà Correctness và Faithfulness không bắt được, chỉ Completeness mới phát hiện.

#### Mối quan hệ với Recall

Với Planning Agent, Completeness thực chất trùng với **Recall** trong F1 (tỷ lệ checks đúng bị bỏ sót). Với Risk Agent và Report Agent, Completeness đo **mức độ chi tiết của reasoning/narrative** — điều mà Recall không áp dụng được.

#### Đặc điểm

| Điểm mạnh | Giới hạn |
|---|---|
| Phát hiện "đúng nhưng thiếu" — loại lỗi mà Correctness bỏ sót | Cần định nghĩa evidence checklist thủ công cho mỗi test case |
| Áp dụng cho cả structured output (Planning) lẫn free text (Risk, Report) | Chất lượng đánh giá phụ thuộc chất lượng checklist |
| Evidence checklist có thể tái sử dụng cho nhiều lần benchmark | Keyword matching có thể miss cách diễn đạt khác |

---

## 4. Agent-specific Instantiation

### 4.1 Tổng hợp — Mỗi trục đo bằng gì ở từng agent?

| Trục đánh giá | Planning Agent | Risk Agent | Report Agent |
|---|---|---|---|
| **Structure** | `valid_output_rate` (gộp schema + exclusivity + format) | JSON parse + enum + range + consistency | **Gate check:** 4 hard constraints (`html_valid`, `section_presence`, `no_template_leak`, `no_none_display`) + 2 soft (`cover_page`, `charts`) |
| **Faithfulness** | `grounded_reasoning_rate` (keyword-based, chỉ low-confidence cases) | `ai_reasoning` bám RiskBundle? (mọi case) | Core: `numerical_faithfulness` (số liệu trong narrative khớp `report_data`). Extension: `narrative_faithfulness` (claim-based LLM judge) |
| **Correctness** | `planning_correctness` = 0.7×F1 + 0.3×service_accuracy | Severity Accuracy + QWK | Core: 100% deterministic (`stats_accuracy`, `findings_table_accuracy`, `score_accuracy`, `status_color_accuracy`). Extension: `correctness_judge_mean` (LLM judge) |
| **Completeness** | Recall (bỏ sót checks?) + `action_type_accuracy` | Evidence checklist | Core: `findings_coverage` + `conditional_bypass_correctness`. Optional: `remediation_detail_coverage`, `scope_completeness` |

Các mục 4.2–4.4 dưới đây mô tả chi tiết cách instantiate 4 trục cho **từng agent riêng biệt**, bao gồm: output format, RAG context, metric cụ thể, và cách tính.

---

### 4.2 Risk Evaluation Agent — Instantiation

#### Output format

```json
{
    "ai_severity": "Critical" | "High" | "Medium" | "Low",
    "ai_risk_score": 0-10,
    "ai_reasoning": "Giải thích ngắn gọn 1-2 câu"
}
```

#### RAG context (RiskBundle)

```json
{
    "primary_finding": { "check_id": "...", "severity": "...", "title": "..." },
    "related_findings": [ { "check_id": "...", "severity": "...", "title": "..." } ],
    "control_mapping": [ { "check_id": "...", "capability_id": "..." } ],
    "maturity_context": [ { "capability_id": "...", "capability_name": "..." } ]
}
```

#### 4 trục đánh giá

**Structure — Structured Output Compliance:**

| Sub-metric | Cách tính | Ngưỡng |
|---|---|---|
| `json_parse_rate` | Output parse được JSON? | = 1.00 |
| `schema_compliance_rate` | Có đủ 3 fields (severity, risk_score, reasoning)? severity ∈ enum? score ∈ [0,10]? | >= 0.95 |
| `internal_consistency_rate` | severity khớp score range? Critical: 9-10, High: 7-8, Medium: 4-6, Low: 1-3 | (informational) |

**Faithfulness — Claim-based LLM-as-Judge:**

Theo RAGAS framework (Es et al. 2023):
1. Claim Decomposition: tách `ai_reasoning` thành câu đơn
2. Build context: finding description + RAG snapshot (official_severity, check_title, compliance_mappings)
3. Verification: LLM judge xác minh từng claim có support bởi context không
4. Score = supported_claims / total_claims

| Sub-metric | Cách tính | Ngưỡng |
|---|---|---|
| `faithfulness_mean` | Trung bình faithfulness score trên tất cả cases | >= 0.80 |

Fallback: rule-based heuristic (detect contradiction + hallucination patterns) khi LLM không available.

**Correctness — Severity Classification:**

| Sub-metric | Cách tính | Ngưỡng |
|---|---|---|
| `severity_accuracy` | % cases predicted severity = expected severity | >= 0.50 |
| `severity_qwk` | Quadratic Weighted Kappa (sklearn). Phạt nặng khi sai xa (Critical→Low), phạt nhẹ khi sai gần (Critical→High) | >= 0.45 |

Tại sao cần QWK? Accuracy coi mọi lỗi như nhau. QWK phản ánh mức nghiêm trọng: nhầm Critical thành Low nguy hiểm hơn nhiều so với nhầm thành High.

**Completeness — Evidence Checklist:**

Mỗi test case có `required_evidence` — danh sách keywords/phrases cần xuất hiện trong reasoning.

| Sub-metric | Cách tính | Ngưỡng |
|---|---|---|
| `evidence_completeness_mean` | Trung bình (evidence_found / total_required) | >= 0.45 |

Matching: lowercase + strip Vietnamese diacritics. Hỗ trợ alternatives: "encryption hoac ma hoa".

#### Benchmark dataset

30 test cases: 4 categories (exact, paraphrase, semantic_hard, risk) × 6 AWS services × 4 severity levels.
File: `benchmark_llm_gen/benchmark_gen_cases.json`

#### Trạng thái: **HOÀN THÀNH** — 6/6 release criteria PASS

---

### 4.3 Planning Agent — Instantiation

#### Đặc tính kiến trúc (khác biệt so với Risk Agent)

Planning Agent có kiến trúc **RAG-first, LLM-conditional**: phần lớn requests được xử lý bằng logic thuần (regex, keyword matching, deterministic scoring) mà không cần gọi LLM. LLM chỉ được gọi khi hệ thống có confidence thấp (ước tính ≤20% requests).

| Đặc điểm | Risk Agent | Planning Agent |
|---|---|---|
| LLM dependency | Mọi request đều gọi LLM | Phần lớn requests **không cần LLM** (0–1 calls) |
| Output source | LLM trực tiếp sinh JSON | Python code tổng hợp từ classification + RAG + scoring |
| Error behavior | Có thể fail JSON parse | Luôn trả valid dict — **không bao giờ silent default** |
| RAG dependency | Bắt buộc (RiskBundle) | Tùy loại request (có thể skip hoàn toàn) |

Hệ quả cho evaluation: Planning Agent được đánh giá như một **black-box system** — input là user request, output là assessment plan. Không cần phân tích internal flow trong báo cáo evaluation.

#### Output format

Output là Python dict với 2 dạng **loại trừ lẫn nhau** (mutually exclusive):

**Dạng 1 — Specific checks:**
```json
{
    "groups_to_scan": [],
    "checks_to_scan": ["s3_bucket_public_access", "s3_bucket_versioning"],
    "reasoning": "Giải thích lý do chọn checks"
}
```

**Dạng 2 — Group scan:**
```json
{
    "groups_to_scan": ["s3"],
    "checks_to_scan": [],
    "reasoning": "User requested a full scan for s3."
}
```

**Dạng 3 — Error (explicit failure):**
```json
{
    "groups_to_scan": [],
    "checks_to_scan": [],
    "reasoning": "",
    "error": "Could not determine assessment target."
}
```

> **Quy tắc output:**
> - `groups_to_scan` và `checks_to_scan` không bao giờ cùng non-empty.
> - Error output trả **empty lists** — không bao giờ default sang bất kỳ service nào.

#### RAG context (PlanningBundle)

```json
{
    "related_findings": [
        { "check_id": "s3_bucket_public_access", "service": "s3", "title": "...", "severity": "high" }
    ],
    "control_mapping_ids": ["block_public_access", "enable_versioning"],
    "maturity_capability_ids": ["data_protection", "access_control"]
}
```

#### 4 trục đánh giá

**Structure — Valid Output Rate:**

> **Khác biệt với Risk Agent:** Planning Agent output luôn là valid dict (do error handling nội bộ), nên `json_parse_rate` không có ý nghĩa. Structure được gộp thành **một metric duy nhất** kiểm tra tính hợp lệ tổng thể.

| Sub-metric | Cách tính | Ngưỡng |
|---|---|---|
| `valid_output_rate` | Output hợp lệ? Gộp kiểm tra: (1) đúng 1 trong 3 dạng, (2) groups và checks không cùng non-empty, (3) reasoning không rỗng (trừ error), (4) check IDs đúng format Prowler | = 1.00 |
| `llm_parse_success_rate` *(optional, debug)* | Tỷ lệ LLM refinement calls parse JSON thành công — chỉ áp dụng khi agent gọi LLM (low-confidence cases) | >= 0.90 |

> `valid_output_rate` gộp các sub-checks trước đó (schema valid, mutual exclusivity, check ID format, reasoning nonempty) thành 1 con số duy nhất. Một output fail bất kỳ sub-check nào đều bị tính là invalid.

**Faithfulness — Grounded Reasoning Rate:**

> **Scope hẹp:** Faithfulness chỉ có ý nghĩa khi reasoning do LLM sinh (low-confidence cases).
> Phần lớn requests có reasoning hardcoded → không thể hallucinate → không cần đo.

Thay vì claim decomposition (RAGAS-style, nặng), sử dụng **keyword-based grounding check** đơn giản hơn:

Kiểm tra reasoning có chứa:
- Check ID đã chọn (hoặc một phần của check ID)
- Keyword liên quan từ RAG context (service name, severity, compliance mapping)

| Sub-metric | Cách tính | Ngưỡng đề xuất |
|---|---|---|
| `grounded_reasoning_rate` | % cases (chỉ low-confidence) mà reasoning chứa ít nhất 1 check_id hoặc keyword từ context | >= 0.80 |

> **Tại sao không dùng claim-level RAGAS?** Planning Agent reasoning ngắn (1-2 câu) và focus vào justification cho check selection, không phải phân tích rủi ro chi tiết như Risk Agent. Keyword-based check đủ hiệu quả và chi phí thấp hơn nhiều.

**Correctness — Check Selection F1 + Service Accuracy + Planning Correctness:**

Đây là **trục quan trọng nhất** của Planning Agent — agent có chọn đúng checks/service không?

*Khi agent trả specific checks:*

```
Precision = |Selected ∩ Relevant| / |Selected|
Recall    = |Selected ∩ Relevant| / |Relevant|
F1        = 2 × Precision × Recall / (Precision + Recall)
```

| Sub-metric | Cách tính | Ngưỡng đề xuất |
|---|---|---|
| `check_selection_f1` | Harmonic mean of Precision and Recall | >= 0.60 |

Ví dụ:
```
Ground truth: [s3_bucket_public_access, s3_bucket_versioning, s3_bucket_encryption]
Agent output: [s3_bucket_public_access, s3_bucket_encryption, s3_bucket_logging]

Precision = 2/3 = 0.67  (s3_bucket_logging sai)
Recall    = 2/3 = 0.67  (thiếu s3_bucket_versioning)
F1        = 0.67
```

*Khi agent trả group scan:*

| Sub-metric | Cách tính | Ngưỡng đề xuất |
|---|---|---|
| `service_accuracy` | Agent chọn đúng service mong đợi? (binary: 0 hoặc 1) | >= 0.90 |

*Metric tổng hợp (con số duy nhất để trả lời "agent tốt hay không?"):*

| Sub-metric | Cách tính | Ngưỡng đề xuất |
|---|---|---|
| **`planning_correctness`** | **0.7 × F1_mean + 0.3 × service_accuracy** | >= 0.65 |

> Trọng số 0.7/0.3 phản ánh tỷ lệ specific vs group requests trong benchmark.
> Error cases (empty output) tính correctness = 0.

**Completeness — Recall + Action Type Accuracy:**

| Sub-metric | Cách tính | Ngưỡng đề xuất |
|---|---|---|
| `check_selection_recall` | Tái sử dụng Recall từ F1 (khi trả specific checks) | |
| `action_type_accuracy` | Agent chọn đúng **loại hành động**? (specific checks khi cần specific, group scan khi cần group) — binary per case | >= 0.85 |

Ví dụ `action_type_accuracy`:
- Request "scan all iam" → expected: group scan → agent trả `groups_to_scan` → **đúng**
- Request "check s3 encryption" → expected: specific checks → agent trả `groups_to_scan` → **sai** (over-broad)
- Request chứa check IDs → expected: specific checks → agent trả `checks_to_scan` = exact IDs → **đúng**

#### Benchmark dataset (cần tạo)

Benchmark được tổ chức theo **loại input** (user perspective), không theo internal flow:

| Input type | Số cases | Ví dụ request | Metric chính |
|---|---|---|---|
| Explicit check IDs | 5 | "chạy s3_bucket_public_access và s3_bucket_versioning" | F1 (= 1.0 expected), action_type |
| Group request | 5 | "scan all iam", "full scan s3" | service_accuracy, action_type |
| Specific intent | 15 | "kiểm tra S3 bucket có bị public access không" | F1, recall, action_type |
| Ambiguous | 5 | "security audit", "check my AWS" | service_accuracy, grounded_reasoning |

Tổng: ~30 test cases.

Mỗi test case:
```json
{
    "case_id": "plan_s3_public_001",
    "input_type": "specific_intent",
    "input": { "user_request": "kiểm tra xem S3 bucket có bị public access không" },
    "rag_context_snapshot": {
        "related_findings": [
            { "check_id": "s3_bucket_public_access", "service": "s3", "title": "S3 Bucket Public Access", "severity": "high", "score": 0.9 },
            { "check_id": "s3_bucket_level_public_access_block", "service": "s3", "title": "S3 Bucket Level Public Access Block", "severity": "high", "score": 0.85 }
        ],
        "control_mapping_ids": ["block_public_access"],
        "maturity_capability_ids": ["data_protection"],
        "confidence": "high"
    },
    "expected": {
        "expected_service": "s3",
        "relevant_checks": ["s3_bucket_public_access", "s3_bucket_level_public_access_block"],
        "acceptable_output_type": "specific_checks"
    }
}
```

```json
{
    "case_id": "plan_iam_group_001",
    "input_type": "group_request",
    "input": { "user_request": "scan all iam" },
    "expected": {
        "expected_service": "iam",
        "relevant_checks": [],
        "acceptable_output_type": "group_scan"
    }
}
```

#### Trạng thái: **CHƯA TRIỂN KHAI**

---

### 4.4 Report Agent — Instantiation

#### Đặc tính kiến trúc (khác biệt so với Risk/Planning Agent)

Report Agent có kiến trúc **template-first, LLM-enriched**: output chính là HTML5 đầy đủ (Jinja2 template + CSS), trong đó LLM chỉ viết các đoạn narrative xen kẽ giữa dữ liệu template-rendered. Report Agent **không sử dụng RAG** — toàn bộ context đến từ `report_data` dict do `build_report_data()` trong orchestrator gom sẵn.

| Đặc điểm | Risk Agent | Report Agent |
|---|---|---|
| LLM dependency | Mọi request đều gọi LLM | 7 top-level sections + N per-finding calls. **Conditional bypass** khi PASS=0 hoặc FAIL=0 |
| Output format | JSON (3 fields) | Full HTML5 document (cover page, TOC, 7 mục, charts) |
| RAG dependency | Bắt buộc (RiskBundle) | **Không dùng RAG** — context là `report_data` dict từ orchestrator |
| Post-processing | Không | `_clean()`: xóa placeholder `[...]`, ngôi thứ nhất, title trùng, collapse spaces |
| Error behavior | Có thể fail JSON parse | Fallback text khi LLM down + graceful "None" handling |
| Data integrity | Input là JSON đơn giản | `copy.deepcopy()` cho enrichment — không mutate input |

Hệ quả cho evaluation: Report Agent được đánh giá trên **2 tầng riêng biệt**: (1) tầng template — deterministic, kiểm tra bằng parsing/regex; (2) tầng LLM narrative — cần claim-based verification với `report_data` làm ground truth.

#### Output format

Report Agent sinh file HTML5 đầy đủ qua Jinja2 template rendering, pipeline 5 bước:

```
validate → derive (charts, score) → LLM sections → enrich findings → render HTML/MD/PDF
```

**7 LLM sections (top-level):**

| Section | LLM method | Word limit | Conditional bypass |
|---|---|---|---|
| Executive Summary | `write_exec_summary()` | 400 | Không |
| System Overview | `write_system_overview()` | 250 | Không |
| Assessment Goals | `write_assessment_goals()` | 200 | Không |
| Pass Findings Overview | `write_pass_findings_overview()` | 200 | **Có** — hardcoded text khi `pre.pass == 0` |
| Fail Findings Overview | `write_fail_findings_overview()` | 200 | **Có** — hardcoded text khi `pre.fail == 0` |
| Post-Remediation Analysis | `write_post_remediation_analysis()` | 300 | Không |
| Recommendations | `write_post_remediation_recommendations()` | 300 | Không |

**Per-finding LLM calls (N calls mỗi loại):**

| Method | Áp dụng cho | Word limit |
|---|---|---|
| `write_pass_remediation_detail()` | Mỗi finding trong `success_findings` | 350 |
| `write_fail_remediation_detail()` | Mỗi finding trong `failed_findings` | 350 |
| `write_manual_guide()` | Mỗi finding trong `manual_findings` | 300 |

**Output files:**

| File | Mô tả |
|---|---|
| `final_report.html` | Full HTML5 — file chính (cover page, TOC, CSS, severity badges) |
| `final_report.md` | Nội dung HTML (giống HTML file, backward compat) |
| `final_report.pdf` | PDF qua weasyprint/wkhtmltopdf (fallback chain, hoặc None) |
| `charts/severity_bar.png` | Bar chart mức độ nghiêm trọng |
| `charts/pass_fail_pie.png` | Pie chart PASS vs FAIL |

#### Input context (`report_data` dict — không phải RAG)

Report Agent nhận `report_data` dict đầy đủ từ `build_report_data()` trong orchestrator. Đây là **nguồn truth duy nhất** cho evaluation — mọi claim trong narrative đều phải truy nguồn về dict này:

```python
{
    "pre": {
        "total": int, "pass": int, "fail": int,
        "severity": {"critical": int, "high": int, "medium": int, "low": int}
    },
    "post": {
        "initial_pass": int, "initial_fail": int,
        "final_pass": int, "final_fail": int,
        "fixed": int, "failed": int, "manual": int
    },
    "findings_table": [{"stt", "finding", "service", "resource", "severity", "before", "after", "change"}],
    "success_findings": [...],
    "failed_findings": [...],
    "manual_findings": [...],
    "raw_pre_findings": [...],
    "environment": {"account_id": str, "region": str, "buckets": list},
    "scope": {"services": list, "date": str, "user_request": str}
}
```

> **Khác biệt quan trọng với Risk/Planning Agent:** Risk Agent nhận RAG context (RiskBundle) nên faithfulness đo "narrative bám RiskBundle". Report Agent nhận structured data nên faithfulness đo "narrative bám `report_data` dict" — verification dễ hơn vì ground truth là JSON cụ thể, không phải text context.

#### 4 trục đánh giá

> **Nguyên tắc phân trục:** Mỗi metric chỉ thuộc **đúng 1 trục**, không overlap. Phân biệt rõ:
> - **Structure** = HTML + template integrity (output có dùng được không?)
> - **Correctness** = data accuracy trên template-rendered layer (số liệu có đúng không?)
> - **Faithfulness** = LLM narrative vs `report_data` (LLM có bịa không?)
> - **Completeness** = coverage + bypass logic (có đủ không?)

**Structure — Gate Check (must-pass):**

> **Vai trò:** Gate check — nếu fail bất kỳ hard constraint nào, output không sử dụng được, các metric khác không cần tính. Tất cả đều **deterministic** (regex/parsing, chi phí = 0).

*Hard constraints (fail 1 = fail toàn bộ output):*

| Sub-metric | Cách tính | Ngưỡng |
|---|---|---|
| `html_valid` | Output là valid HTML5? (parse được bằng html.parser, có `<!DOCTYPE html>`, `<html lang="vi">`, charset UTF-8) | = 1.00 |
| `section_presence_rate` | % sections bắt buộc có trong HTML output. 7 sections: Executive Summary, Phạm vi & Phương pháp, Đánh giá trước khắc phục, Bảng chi tiết, Chi tiết thực thi, Đánh giá sau khắc phục, Khuyến nghị | = 1.00 |
| `no_template_leak` | Không có Jinja2 syntax lộ ra (`{{`, `{%`, `}}`) hoặc placeholder `[...]` từ `_clean()` failure (chỉ kiểm tra ngoài code blocks) | = 1.00 |
| `no_none_display` | Không có giá trị "None" hiển thị trong text (BUG-02: `f.get("action")` trả None) | = 1.00 |

*Soft constraints (quality checks, không block output):*

| Sub-metric | Cách tính | Ngưỡng |
|---|---|---|
| `cover_page_complete` | Cover page có đủ: Account ID, Region, Date, Report ID (format `RPT-YYYYMMDD-XXXX`), Security Score | = 1.00 |
| `chart_presence` | 2 charts tồn tại: `severity_bar.png` và `pass_fail_pie.png` | = 1.00 |

> **Gate logic:** Hard constraints fail → **STOP**, báo cáo lỗi, không tính metrics còn lại. Soft constraints fail → ghi nhận warning, tiếp tục đánh giá. Tách rõ vì: report thiếu `<!DOCTYPE html>` (broken) khác bản chất với report thiếu chart (chưa hoàn thiện nhưng vẫn đọc được).

**Correctness — Deterministic Data Accuracy:**

> **Scope:** Chỉ đo **template-rendered layer** (Jinja2 output). Đây là phần deterministic — không phụ thuộc LLM, kiểm tra chính xác bằng HTML parsing. Tất cả phải = 1.00 vì sai ở đây là bug template, không phải LLM variance.

| Sub-metric | Cách tính | Ngưỡng |
|---|---|---|
| `stats_accuracy` | Số liệu trong template (pre.total, pre.fail, post.fixed...) khớp với `report_data`? Kiểm tra bằng HTML parsing, extract text từ các element chứa stats | = 1.00 |
| `findings_table_accuracy` | Bảng chi tiết (mục 4) có đúng số dòng = `len(findings_table)`? Severity badges đúng case? (`row.change\|lower`) | = 1.00 |
| `score_accuracy` | Security Score trên cover page = `_calc_score(pre, post)`? | = 1.00 |
| `status_color_accuracy` | Fixed → xanh (`.status-fixed`), Manual → cam (`.status-manual`), Failed → đỏ (`.status-error`)? (BUG-03 regression check) | = 1.00 |

> **Phân biệt với Faithfulness:** Correctness kiểm tra phần **template render** (Jinja2 `{{ pre.total }}`). Faithfulness kiểm tra phần **LLM viết** (narrative text). Template sai = bug code. LLM sai = hallucination. Hai nguyên nhân gốc khác nhau, hai cách fix khác nhau.

**Faithfulness — Narrative vs Data (core = deterministic only):**

> **Đặc thù Report Agent:** Ground truth là `report_data` dict (structured JSON). Rủi ro chính = LLM bịa số liệu hoặc sự kiện không có trong data. Core metric chỉ cần **numerical faithfulness** (deterministic, chi phí = 0) — đã cover phần quan trọng nhất. Narrative claim verification (LLM judge) chuyển xuống extension layer để giảm chi phí và tăng độ ổn định.

*Core (deterministic, chi phí = 0):*

Kiểm tra số liệu trong LLM narrative khớp với `report_data`:
- Executive Summary nói "3 Critical findings" → `pre.severity.critical == 3`?
- Post-Analysis nói "đã khắc phục thành công 5 lỗi" → `post.fixed == 5`?
- Remediation detail nói "bucket my-bucket" → `success_findings` có resource "my-bucket"?

```
Numerical Faithfulness = (Số claims số liệu đúng) / (Tổng claims số liệu trong narrative)
```

| Sub-metric | Cách tính | Ngưỡng |
|---|---|---|
| **`numerical_faithfulness`** | Trích xuất số và named entities từ 7 LLM narrative sections, so khớp với `report_data`. Regex-based extraction + exact matching | **>= 0.90** |

> **Tại sao chỉ numerical cho core?** (1) Sai số liệu là lỗi nghiêm trọng nhất — decision-makers dựa vào con số. (2) Deterministic → ổn định, reproducible, chi phí = 0. (3) Cover phần rủi ro cao nhất: LLM hallucinate "5 Critical" khi thực tế có 3 nguy hiểm hơn LLM diễn đạt sai ý.

*Extension (LLM-as-Judge, chi phí cao):*

| Sub-metric | Cách tính | Ngưỡng |
|---|---|---|
| `narrative_faithfulness` | Claim decomposition + verification trên 3 sections chính (Executive Summary, Post-Analysis, Recommendations). LLM judge xác minh từng claim có support bởi `report_data` | >= 0.75 |
| `correctness_judge_mean` | LLM judge đánh giá narrative: "trình bày đúng sự kiện, kết quả, khuyến nghị hợp lý không?" Score 1-5 → normalize 0-1 | >= 0.70 |

> Cả `narrative_faithfulness` và `correctness_judge_mean` đều thuộc **extension layer** — chỉ triển khai khi core metrics đã ổn định và cần đánh giá sâu hơn chất lượng diễn đạt.

**Completeness — Findings Coverage & Bypass Logic:**

> **Core:** 2 metrics trọng tâm, đủ để phát hiện "report bỏ sót findings" và "bypass logic sai". Optional metrics bổ sung khi cần đánh giá chi tiết hơn.

*Core:*

| Sub-metric | Cách tính | Ngưỡng |
|---|---|---|
| `findings_coverage` | Matching `finding_id` hoặc `event_code` giữa HTML output và `report_data.findings_table` + `raw_pre_findings`. Coverage = found / total | >= 0.90 |
| `conditional_bypass_correctness` | Khi `pre.pass == 0`: pass_overview = hardcoded text (không gọi LLM). Khi `pre.fail == 0`: tương tự. Kiểm tra bypass logic đúng (BUG-04 regression) | = 1.00 |

*Optional (bổ sung khi cần, không bắt buộc phase 1):*

| Sub-metric | Cách tính | Ngưỡng |
|---|---|---|
| `remediation_detail_coverage` | % findings có LLM remediation detail (không phải chỉ liệt kê trong bảng). Kiểm tra `success_findings` có `llm_detail`, `manual_findings` có `llm_manual_guide` | >= 0.85 |
| `scope_completeness` | Report hiển thị đúng services (`scope.services \| join(', ') \| upper` → "S3" thay vì "['s3']"), date, account_id, region | = 1.00 |

> **Mối quan hệ giữa các trục:**
> - Structure fail → **STOP** (report broken)
> - Correctness fail → bug template/code (fix bằng code change)
> - Faithfulness fail → LLM hallucination (fix bằng prompt engineering hoặc `_clean()`)
> - Completeness fail → missing data hoặc logic error (fix bằng pipeline change)

#### Benchmark dataset (cần tạo)

Benchmark tổ chức theo **2 nhóm**: (A) scenario logic — đo xử lý luồng chính; (B) edge cases / robustness — bám sát các bug đã fix và data bất thường thực tế.

**Nhóm A — Scenario logic:**

| Scenario | Số cases | Đặc điểm | Metric trọng tâm |
|---|---|---|---|
| Standard (có cả PASS + FAIL) | 3 | Trường hợp thông thường, có remediation | Tất cả metrics |
| All PASS (no FAIL) | 2 | `pre.fail == 0` → conditional bypass cho fail_overview | `conditional_bypass_correctness`, faithfulness |
| All FAIL (no PASS) | 2 | `pre.pass == 0` → conditional bypass cho pass_overview | `conditional_bypass_correctness`, faithfulness |
| Minimal data | 2 | 1-2 findings, ít metadata → LLM có bịa đặt thêm không? | `numerical_faithfulness` |

**Nhóm B — Edge cases / Robustness (bám sát các bug đã fix):**

| Scenario | Số cases | Đặc điểm | Bug liên quan | Metric trọng tâm |
|---|---|---|---|---|
| Missing fields | 2 | `action=None`, thiếu `resource`, `description` rỗng | BUG-02 (None display) | `no_none_display`, `findings_table_accuracy` |
| Mixed case status | 2 | `change` = "FIXED", "fixed", "Fixed" lẫn lộn | BUG-03 (case-sensitive) | `status_color_accuracy` |
| Multi-service | 2 | `scope.services = ["s3", "iam"]` — kiểm tra join/upper format | BUG-05 (raw list display) | `scope_completeness`, `stats_accuracy` |
| High volume | 2 | 50+ findings, nhiều severity levels | Deep copy + coverage | `findings_coverage`, `findings_table_accuracy` |
| Zero severity counts | 1 | `severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}` | Chart zero data | `chart_presence`, `numerical_faithfulness` |
| Complex remediation mix | 2 | Cả 3 loại: success + failed + manual, với nested execution_output | Deep copy enrich | `remediation_detail_coverage`, `no_none_display` |

Tổng: ~20 test cases.

**Ví dụ test cases:**

*Nhóm A — Standard:*
```json
{
    "case_id": "report_standard_001",
    "group": "A_scenario",
    "scenario": "standard",
    "input": {
        "pre": { "total": 10, "pass": 7, "fail": 3, "severity": {"critical": 1, "high": 1, "medium": 1, "low": 0} },
        "post": { "initial_pass": 7, "initial_fail": 3, "final_pass": 9, "final_fail": 1, "fixed": 2, "failed": 0, "manual": 1 },
        "findings_table": [ {"stt": 1, "finding": "s3_bucket_public_access", "service": "s3", "severity": "critical", "before": "FAIL", "after": "PASS", "change": "Fixed"} ],
        "success_findings": [ {"finding_id": "f001", "action": "Block public access", "resource": "my-bucket", "description": "S3 bucket public access blocked"} ],
        "failed_findings": [],
        "manual_findings": [ {"finding_id": "f003", "description": "Enable S3 versioning", "manual_reason": "Requires business approval"} ],
        "raw_pre_findings": [ {"finding_id": "f001", "status": "FAIL", "severity": "critical", "event_code": "s3_bucket_public_access"} ],
        "environment": { "account_id": "123456789012", "region": "ap-southeast-1", "buckets": ["my-bucket"] },
        "scope": { "services": ["s3"], "date": "2026-04-05", "user_request": "Kiểm tra bảo mật S3" }
    },
    "expected": {
        "required_sections": ["executive_summary", "scope_method", "pre_assessment", "findings_table", "remediation_detail", "post_assessment", "recommendations"],
        "expected_finding_ids": ["f001", "f003"],
        "expected_stats": { "total": 10, "fail": 3, "fixed": 2, "manual": 1 },
        "expected_score_range": [60, 90],
        "bypass_sections": []
    }
}
```

*Nhóm A — All PASS:*
```json
{
    "case_id": "report_all_pass_001",
    "group": "A_scenario",
    "scenario": "all_pass",
    "input": {
        "pre": { "total": 5, "pass": 5, "fail": 0, "severity": {"critical": 0, "high": 0, "medium": 0, "low": 0} },
        "post": { "initial_pass": 5, "initial_fail": 0, "final_pass": 5, "final_fail": 0, "fixed": 0, "failed": 0, "manual": 0 },
        "findings_table": [],
        "success_findings": [], "failed_findings": [], "manual_findings": [],
        "raw_pre_findings": [ {"finding_id": "f001", "status": "PASS", "severity": "low", "event_code": "s3_bucket_versioning"} ],
        "environment": { "account_id": "123456789012", "region": "ap-southeast-1", "buckets": ["bucket-a"] },
        "scope": { "services": ["s3"], "date": "2026-04-05", "user_request": "Scan S3" }
    },
    "expected": {
        "required_sections": ["executive_summary", "scope_method", "pre_assessment", "findings_table", "post_assessment", "recommendations"],
        "expected_finding_ids": [],
        "expected_stats": { "total": 5, "fail": 0, "fixed": 0 },
        "bypass_sections": ["fail_overview"]
    }
}
```

*Nhóm B — Missing fields (BUG-02 regression):*
```json
{
    "case_id": "report_missing_fields_001",
    "group": "B_edge_case",
    "scenario": "missing_fields",
    "bug_regression": "BUG-02",
    "input": {
        "pre": { "total": 3, "pass": 1, "fail": 2, "severity": {"critical": 1, "high": 1, "medium": 0, "low": 0} },
        "post": { "initial_pass": 1, "initial_fail": 2, "final_pass": 2, "final_fail": 1, "fixed": 1, "failed": 1, "manual": 0 },
        "findings_table": [
            {"stt": 1, "finding": "s3_bucket_public_access", "service": "s3", "severity": "critical", "before": "FAIL", "after": "PASS", "change": "Fixed"},
            {"stt": 2, "finding": "s3_bucket_encryption", "service": "s3", "severity": "high", "before": "FAIL", "after": "FAIL", "change": "Failed"}
        ],
        "success_findings": [ {"finding_id": "f001", "action": null, "resource": null, "description": "S3 bucket public access"} ],
        "failed_findings": [ {"finding_id": "f002", "action": null, "resource": "my-bucket", "description": "", "execution_error": "Access denied"} ],
        "manual_findings": [],
        "raw_pre_findings": [
            {"finding_id": "f001", "status": "FAIL", "severity": "critical", "event_code": "s3_bucket_public_access"},
            {"finding_id": "f002", "status": "FAIL", "severity": "high", "event_code": "s3_bucket_encryption"}
        ],
        "environment": { "account_id": "123456789012", "region": "ap-southeast-1", "buckets": [] },
        "scope": { "services": ["s3"], "date": "2026-04-05", "user_request": "Check S3" }
    },
    "expected": {
        "must_not_contain": ["None", "null"],
        "expected_finding_ids": ["f001", "f002"],
        "expected_display_titles": ["S3 bucket public access", "Remediation Action"]
    }
}
```

*Nhóm B — Mixed case status (BUG-03 regression):*
```json
{
    "case_id": "report_mixed_case_001",
    "group": "B_edge_case",
    "scenario": "mixed_case_status",
    "bug_regression": "BUG-03",
    "input": {
        "pre": { "total": 4, "pass": 1, "fail": 3, "severity": {"critical": 1, "high": 1, "medium": 1, "low": 0} },
        "post": { "initial_pass": 1, "initial_fail": 3, "final_pass": 3, "final_fail": 1, "fixed": 1, "failed": 1, "manual": 1 },
        "findings_table": [
            {"stt": 1, "finding": "check_a", "service": "s3", "severity": "critical", "before": "FAIL", "after": "PASS", "change": "FIXED"},
            {"stt": 2, "finding": "check_b", "service": "s3", "severity": "high", "before": "FAIL", "after": "FAIL", "change": "failed"},
            {"stt": 3, "finding": "check_c", "service": "s3", "severity": "medium", "before": "FAIL", "after": "FAIL", "change": "Manual"}
        ],
        "success_findings": [{"finding_id": "f001", "action": "Fix A", "resource": "res-a", "description": "Check A"}],
        "failed_findings": [{"finding_id": "f002", "action": "Fix B", "resource": "res-b", "description": "Check B"}],
        "manual_findings": [{"finding_id": "f003", "description": "Check C", "manual_reason": "Need approval"}],
        "raw_pre_findings": [
            {"finding_id": "f001", "status": "FAIL", "severity": "critical", "event_code": "check_a"},
            {"finding_id": "f002", "status": "FAIL", "severity": "high", "event_code": "check_b"},
            {"finding_id": "f003", "status": "FAIL", "severity": "medium", "event_code": "check_c"}
        ],
        "environment": { "account_id": "111222333444", "region": "us-east-1", "buckets": ["res-a", "res-b"] },
        "scope": { "services": ["s3"], "date": "2026-04-05", "user_request": "Security scan" }
    },
    "expected": {
        "status_colors": {
            "FIXED": "status-fixed",
            "failed": "status-error",
            "Manual": "status-manual"
        }
    }
}
```

*Nhóm B — Multi-service (BUG-05 regression):*
```json
{
    "case_id": "report_multi_service_001",
    "group": "B_edge_case",
    "scenario": "multi_service",
    "bug_regression": "BUG-05",
    "input": {
        "pre": { "total": 8, "pass": 5, "fail": 3, "severity": {"critical": 1, "high": 1, "medium": 1, "low": 0} },
        "post": { "initial_pass": 5, "initial_fail": 3, "final_pass": 7, "final_fail": 1, "fixed": 2, "failed": 1, "manual": 0 },
        "findings_table": [
            {"stt": 1, "finding": "s3_check", "service": "s3", "severity": "critical", "before": "FAIL", "after": "PASS", "change": "Fixed"},
            {"stt": 2, "finding": "iam_check", "service": "iam", "severity": "high", "before": "FAIL", "after": "PASS", "change": "Fixed"},
            {"stt": 3, "finding": "ec2_check", "service": "ec2", "severity": "medium", "before": "FAIL", "after": "FAIL", "change": "Failed"}
        ],
        "success_findings": [
            {"finding_id": "f001", "action": "Block public access", "resource": "s3-bucket", "description": "S3 check"},
            {"finding_id": "f002", "action": "Rotate key", "resource": "iam-user", "description": "IAM check"}
        ],
        "failed_findings": [{"finding_id": "f003", "action": "Harden SG", "resource": "ec2-instance", "description": "EC2 check"}],
        "manual_findings": [],
        "raw_pre_findings": [
            {"finding_id": "f001", "status": "FAIL", "severity": "critical", "event_code": "s3_check"},
            {"finding_id": "f002", "status": "FAIL", "severity": "high", "event_code": "iam_check"},
            {"finding_id": "f003", "status": "FAIL", "severity": "medium", "event_code": "ec2_check"}
        ],
        "environment": { "account_id": "123456789012", "region": "ap-southeast-1", "buckets": ["s3-bucket"] },
        "scope": { "services": ["s3", "iam", "ec2"], "date": "2026-04-05", "user_request": "Full security audit" }
    },
    "expected": {
        "scope_display": "S3, IAM, EC2",
        "must_not_contain": ["['s3', 'iam', 'ec2']"],
        "expected_finding_ids": ["f001", "f002", "f003"]
    }
}
```

#### Trạng thái: **CHƯA TRIỂN KHAI**

---

### 4.5 Mức ưu tiên triển khai

**Giai đoạn 1 — Risk Agent (HOÀN THÀNH):**

| # | Metric | Trạng thái | Kết quả | Ghi chú |
|---|---|---|---|---|
| 1 | Structured Output Compliance | **Done** | 100% parse, 100% schema, 96.7% consistency | Deterministic |
| 2 | Faithfulness (claim-based) | **Done** | 0.950 (27/30 cases = 1.0) | LLM-as-Judge, llama3.2 judge |
| 3 | Severity Accuracy + QWK | **Done** | 83.3%, 0.941 | 5 cases sai đều adjacent error |
| 4 | Evidence Checklist | **Done** | 82.2% | Keyword matching + Vietnamese diacritics |
| 5 | RAG Ablation (extension→core) | **Done** | RAG Lift = +10.0pp | 4 iterations, Two-Pass technique |

Chi tiết đầy đủ: xem `benchmark_llm_gen/Risk_Agent_Evaluation_Report.md`

**Giai đoạn 2 — Planning Agent:**

| # | Metric | Trạng thái | Ưu tiên | Ghi chú |
|---|---|---|---|---|
| 5 | `valid_output_rate` (Structure) | Chưa | Cao | Gộp schema + exclusivity + format thành 1 metric |
| 6 | `grounded_reasoning_rate` (Faithfulness) | Chưa | Trung bình | Keyword-based, chỉ low-confidence cases |
| 7 | `check_selection_f1` (Correctness) | Chưa | **Cao — metric core** | Precision + Recall + F1 |
| 8 | `service_accuracy` (Correctness) | Chưa | **Cao — metric core** | Bổ sung cho F1 khi agent trả group scan |
| 9 | **`planning_correctness`** (Correctness tổng) | Chưa | **Cao — con số duy nhất** | 0.7 × F1 + 0.3 × service_accuracy |
| 10 | `action_type_accuracy` (Completeness) | Chưa | Cao | Agent chọn đúng loại hành động? |

**Giai đoạn 3 — Report Agent:**

*Core (triển khai ngay, tất cả deterministic):*

| # | Metric | Trạng thái | Ưu tiên | Trục | Ghi chú |
|---|---|---|---|---|---|
| 13 | Structure gate checks (4 hard + 2 soft) | Chưa | **Cao — gate check** | Structure | `html_valid`, `section_presence_rate`, `no_template_leak`, `no_none_display` + `cover_page_complete`, `chart_presence` |
| 14 | `stats_accuracy` + `findings_table_accuracy` + `score_accuracy` + `status_color_accuracy` | Chưa | **Cao** | Correctness | Template-rendered data khớp `report_data`? Regression cho BUG-03 |
| 15 | `numerical_faithfulness` | Chưa | **Cao — rủi ro chính** | Faithfulness | Trích xuất số/entities từ narrative, so khớp `report_data`. Deterministic |
| 16 | `findings_coverage` + `conditional_bypass_correctness` | Chưa | **Cao** | Completeness | Coverage + bypass logic (BUG-04 regression) |

*Optional (bổ sung sau khi core ổn định):*

| # | Metric | Trạng thái | Ưu tiên | Trục | Ghi chú |
|---|---|---|---|---|---|
| 17 | `remediation_detail_coverage` | Chưa | Trung bình | Completeness | % findings có LLM detail |
| 18 | `scope_completeness` | Chưa | Trung bình | Completeness | BUG-05 regression |

*Extension (cần LLM judge, chi phí cao):*

| # | Metric | Trạng thái | Ưu tiên | Trục | Ghi chú |
|---|---|---|---|---|---|
| 19 | `narrative_faithfulness` | Chưa | Thấp | Faithfulness | Claim decomposition, LLM-as-Judge |
| 20 | `correctness_judge_mean` | Chưa | Thấp | Correctness | LLM judge cho narrative quality |

### 4.6 Proposed Internal Release Criteria

> **Lưu ý:** Các ngưỡng là đề xuất nội bộ ban đầu, cần điều chỉnh sau khi có dữ liệu benchmark thực tế.

**Risk Agent (đã xác thực):**

| # | Tiêu chí | Ngưỡng | Thực tế | Trạng thái |
|---|---|---|---|---|
| 1 | json_parse_rate | = 1.00 | 1.00 | PASS |
| 2 | schema_compliance_rate | >= 0.95 | 1.00 | PASS |
| 3 | faithfulness_mean | >= 0.80 | 0.950 | PASS |
| 4 | severity_accuracy | >= 0.50 | 0.833 | PASS |
| 5 | severity_qwk | >= 0.45 | 0.941 | PASS |
| 6 | evidence_completeness_mean | >= 0.45 | 0.822 | PASS |

**Planning Agent (đề xuất):**

| # | Tiêu chí | Ngưỡng đề xuất | Trục | Ghi chú |
|---|---|---|---|---|
| 7 | `valid_output_rate` | = 1.00 | Structure | Gộp: schema valid + mutual exclusivity + check ID format + reasoning nonempty |
| 8 | `grounded_reasoning_rate` | >= 0.80 | Faithfulness | Keyword-based, chỉ low-confidence cases |
| 9 | `check_selection_f1` | >= 0.60 | Correctness | Khi agent trả specific checks |
| 10 | `service_accuracy` | >= 0.90 | Correctness | Khi agent trả group scan |
| 11 | **`planning_correctness`** | **>= 0.65** | Correctness | **0.7 × F1 + 0.3 × service_accuracy** — con số duy nhất |
| 12 | `action_type_accuracy` | >= 0.85 | Completeness | Agent chọn đúng loại hành động (specific vs group)? |

**Report Agent (đề xuất):**

*Core release criteria (tất cả deterministic, chi phí = 0):*

| # | Tiêu chí | Ngưỡng đề xuất | Trục | Ghi chú |
|---|---|---|---|---|
| 13 | `html_valid` | = 1.00 | Structure (gate) | Hard constraint — fail = report broken |
| 14 | `section_presence_rate` | = 1.00 | Structure (gate) | Hard constraint — 7 sections bắt buộc |
| 15 | `no_template_leak` | = 1.00 | Structure (gate) | Hard constraint — no Jinja2/placeholder leak |
| 16 | `no_none_display` | = 1.00 | Structure (gate) | Hard constraint — BUG-02 regression |
| 17 | `stats_accuracy` | = 1.00 | Correctness | Template-rendered stats khớp `report_data` |
| 18 | `findings_table_accuracy` | = 1.00 | Correctness | Bảng findings đúng số dòng, severity badges, status colors |
| 19 | `score_accuracy` | = 1.00 | Correctness | Security Score trên cover page = `_calc_score()` |
| 20 | `numerical_faithfulness` | >= 0.90 | Faithfulness | Số liệu trong LLM narrative khớp `report_data` |
| 21 | `findings_coverage` | >= 0.90 | Completeness | Finding IDs/event_codes xuất hiện trong HTML output |
| 22 | `conditional_bypass_correctness` | = 1.00 | Completeness | Bypass logic đúng khi PASS=0 hoặc FAIL=0 (BUG-04 regression) |

> **Đặc điểm:** 10 release criteria, tất cả deterministic. Không phụ thuộc LLM judge ở core layer → evaluation ổn định, reproducible, chi phí = 0. Benchmark dataset 20 test cases (9 scenario + 11 edge case) bám sát 6 bugs đã fix.

---

## 5. Extension Layer — Hướng mở rộng

Các metrics sau đây **không nằm trong core**, nhưng có giá trị bổ sung khi hệ thống đã có baseline benchmark ổn định.

### 5.1 RAG Ablation (Đo đóng góp của RAG)

**Câu hỏi:** "RAG context có thực sự giúp agent sinh output tốt hơn không?"

**Cách thực hiện:** Chạy cùng test cases với 2 điều kiện:
- **With RAG**: Agent nhận context bình thường.
- **Without RAG**: Agent chạy với `rag_available = False` (context rỗng).

```
RAG Lift = Metric(with_RAG) - Metric(without_RAG)
```

RAG Lift dương và đáng kể -> RAG đang đóng góp giá trị. RAG Lift ~ 0 -> RAG không có tác dụng. RAG Lift âm -> RAG đang làm hại.

**Tại sao ban đầu xếp ở extension?** Ablation cần chạy pipeline 2 lần cho mỗi test case, gấp đôi chi phí. Nó là công cụ **validation một lần** (chứng minh RAG có giá trị) hơn là metric chạy thường xuyên.

> **Thực tế triển khai (Risk Agent):** RAG Ablation được **nâng lên core** — thực hiện xuyên suốt
> 4 iterations cải tiến, không chỉ chạy 1 lần. Kết quả cho thấy RAG Lift biến thiên lớn
> (-10.0pp → 0.0pp → +3.3pp → +10.0pp) qua các phiên bản prompt, chứng minh ablation
> là công cụ thiết yếu để phát hiện và khắc phục vấn đề RAG integration.
> Khuyến nghị: đối với agent sử dụng RAG, nên thực hiện RAG Ablation như phần **core evaluation**,
> không phải extension.
>
> Kỹ thuật **Two-Pass RAG Integration** — phát triển trong quá trình evaluation — giải quyết
> vấn đề anchoring bias khi model nhỏ (3B) không xử lý được xung đột giữa finding.severity
> và rag_context.official_severity. Chi tiết: xem `benchmark_llm_gen/Risk_Agent_Evaluation_Report.md` mục 1.3 và 10.

### 5.2 G-Eval (LLM-as-Judge cho chất lượng tổng hợp)

**Câu hỏi:** "Output có mạch lạc, chuyên nghiệp, actionable không?"

G-Eval (Liu et al. 2023) sử dụng LLM mạnh (GPT-4, Claude) đánh giá output theo rubric do người định nghĩa, cho điểm 1–5.

**Phù hợp nhất cho Report Agent** — nơi chất lượng văn bản (coherence, actionability) là quan trọng nhưng khó đo bằng metric tự động.

**Có thể áp dụng cho Risk Agent** — đánh giá reasoning depth: reasoning có chỉ nói lại finding, hay có phân tích impact và trích dẫn evidence?

**Tại sao nằm ở extension?**
- Chi phí cao (nhiều LLM calls cho mỗi test case).
- Variance cao (chạy nhiều lần cho kết quả khác nhau).
- Khó chuẩn hóa (điểm 3.5 từ GPT-4 không tương đương điểm 3.5 từ Claude).
- Nên dùng **chọn lọc** khi core metrics đã ổn định.

### 5.3 Các hướng nâng cao khác

| Hướng | Mô tả | Giá trị |
|---|---|---|
| **Counterfactual robustness** | Thêm context sai có ý -> agent có phát hiện hay tin mù quáng? | Đánh giá khả năng chống nhiễu |
| **Partial context ablation** | Bỏ từng phần context (chỉ giữ mappings, bỏ maturity) -> metric giảm bao nhiêu? | Xác định phần context đóng góp nhiều nhất |
| **Inter-annotator agreement** | 2+ expert đánh giá độc lập, tính Cohen's Kappa | Đánh giá chất lượng ground truth |
| **Claim-level F1 cho Report** | Phân tách report và ground truth thành claims, tính TP/FP/FN | Đánh giá chi tiết nội dung report |

---

## 6. Tham khảo

### Frameworks

| Framework | Mô tả |
|---|---|
| **RAGAS** (Es et al. 2023) | Framework đánh giá RAG: Faithfulness, Answer Relevance, Context Precision/Recall, Answer Correctness |
| **DeepEval** (Confident AI) | Framework test-driven cho LLM: tích hợp CI/CD, hỗ trợ G-Eval, faithfulness, hallucination detection |

### Bài báo học thuật chính

| Bài báo | Năm | Đóng góp |
|---|---|---|
| Es et al., "RAGAS: Automated Evaluation of Retrieval Augmented Generation" | 2023 | Định nghĩa Faithfulness và Answer Relevance cho RAG. Framework được cite nhiều nhất. |
| Liu et al., "G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment" | 2023 | LLM-as-Judge với Chain-of-Thought + probability weighting. Tương quan với người Spearman ~0.5–0.7. |
| Min et al., "FActScore: Fine-grained Atomic Evaluation of Factual Precision" | 2023 | Phương pháp claim decomposition — nền tảng cho faithfulness và correctness trong RAGAS. |
| Tang et al., "MiniCheck: Efficient Fact-Checking of LLMs on Grounding Documents" | 2024 | Model fact-checking nhẹ, hiệu suất tương đương GPT-4 với chi phí thấp hơn nhiều. |
| Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" | 2023 | Phân tích bias của LLM judge (position, verbosity, self-enhancement). GPT-4 đồng ý với người >80%. |
| Saad-Falcon et al., "ARES: Automated Evaluation Framework for RAG" | 2024 | Đánh giá RAG với ít nhãn của người, cung cấp confidence intervals thống kê. |
| Gao et al., "Retrieval-Augmented Generation for Large Language Models: A Survey" | 2024 | Tổng quan evaluation methodology cho RAG systems. |
