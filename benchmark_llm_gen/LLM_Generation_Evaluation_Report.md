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
  -> Planning Agent  (RAG: PlanningBundle -> chọn Prowler checks)
  -> Scanner Agent   (gọi Prowler API)
  -> Risk Agent      (RAG: RiskBundle -> chấm điểm severity + reasoning)
  -> Remediation     (thực thi sửa lỗi)
  -> Report Agent    (RAG: ReportBundle -> sinh báo cáo tổng hợp)
```

Mỗi agent gọi RAG qua `build_context(consumer=...)` để nhận context bundle, sau đó truyền vào LLM prompt để sinh output (JSON có cấu trúc hoặc văn bản tự do).

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
| Report | Văn bản tự do | Open-ended generation | LLM-based correctness judge |

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

##### Report Agent — LLM-based Correctness

Report Agent sinh văn bản tự do — không thể dùng Accuracy hay F1 trên tokens. Sử dụng **LLM-as-Judge** để đánh giá:

```
Prompt cho judge:
"So sánh report sinh ra với dữ liệu findings/remediation gốc.
Report có trình bày đúng các sự kiện, con số, và kết quả không?
Score 1-5. Giải thích lý do."
```

Đây là metric thuộc **extension layer** về mặt chi phí, nhưng về mặt khái niệm nó vẫn thuộc trục Correctness.

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
| **Structure** | Schema valid + mutual exclusivity + check ID format + internal LLM parse rate | JSON parse + enum + range + consistency | Section checklist |
| **Faithfulness** | `reasoning` bám PlanningBundle? (**chỉ Flow 3** — reasoning LLM-generated) | `ai_reasoning` bám RiskBundle? (mọi case) | Narrative bám findings? |
| **Correctness** | Check Selection F1 (Flows 1, 3) + Service Accuracy (Flows 2, 4) | Severity Accuracy + QWK | LLM-based judge (*extension*) |
| **Completeness** | Recall (bỏ sót checks?) + Flow Appropriateness | Evidence checklist | Findings coverage |

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

Planning Agent có kiến trúc **multi-step orchestration**, khác biệt cơ bản so với Risk Agent (single LLM call → direct output):

| Đặc điểm | Risk Agent | Planning Agent |
|---|---|---|
| Số LLM calls | 1 (evaluate finding) | 2 (translate_intent + rerank) |
| Output source | LLM trực tiếp sinh JSON | Python code tổng hợp từ nhiều nguồn |
| Error handling | Có thể fail JSON parse | Luôn trả valid dict (fallback chain) |
| RAG dependency | Bắt buộc (RiskBundle) | Tùy flow (có thể skip hoàn toàn) |
| Output variability | Đồng nhất (luôn cùng schema) | Thay đổi theo flow (checks vs groups) |

Hệ quả cho evaluation: **không thể áp dụng cùng methodology với Risk Agent**. Cần thiết kế metrics phản ánh đúng kiến trúc multi-step và multi-flow.

#### Output format

Output là Python dict với 2 dạng **loại trừ lẫn nhau** (mutually exclusive):

**Dạng 1 — Specific checks (normal flow, fast track):**
```json
{
    "groups_to_scan": [],
    "checks_to_scan": ["s3_bucket_public_access", "s3_bucket_versioning"],
    "reasoning": "Giải thích lý do chọn checks"
}
```

**Dạng 2 — Group scan (group request, low confidence, no candidates):**
```json
{
    "groups_to_scan": ["s3"],
    "checks_to_scan": [],
    "reasoning": "User requested a full scan for s3."
}
```

**Dạng 3 — Error fallback (exception):**
```json
{
    "groups_to_scan": ["s3"],
    "checks_to_scan": [],
    "error": "error message"
}
```

> **Ghi chú:** `groups_to_scan` và `checks_to_scan` không bao giờ cùng non-empty.
> Output luôn là valid dict do error handling trong `run()`, khác với Risk Agent nơi LLM output trực tiếp có thể fail parse.

#### Các flow thực thi (Decision Tree)

Planning Agent có **5 flow** riêng biệt, mỗi flow có đặc tính evaluation khác nhau:

```
run(user_request)
  │
  ├─ Flow 1: FAST TRACK
  │   Điều kiện: regex detect check IDs trong request (len > 8)
  │   LLM calls: 0
  │   RAG calls: 0
  │   Reasoning: hardcoded ("User explicitly provided check IDs")
  │   Output: checks_to_scan = detected IDs
  │
  ├─ Flow 2: GROUP SCAN
  │   Điều kiện: LLM translate_intent trả is_group_scan=true
  │   LLM calls: 1 (translate_intent)
  │   RAG calls: 0
  │   Reasoning: hardcoded ("User requested a full scan for {service}")
  │   Output: groups_to_scan = [service]
  │
  ├─ Flow 3: NORMAL RERANK (target flow)
  │   Điều kiện: RAG trả candidates + LLM rerank thành công
  │   LLM calls: 2 (translate_intent + rerank)
  │   RAG calls: 1 (build_context hoặc retrieve_checks)
  │   Reasoning: LLM-generated (rerank output)
  │   Output: checks_to_scan = top 5 từ rerank
  │
  ├─ Flow 4: LOW CONFIDENCE / NO CANDIDATES
  │   Điều kiện: RAG confidence=low, hoặc candidates rỗng
  │   LLM calls: 1-2
  │   RAG calls: 1
  │   Reasoning: hardcoded ("RAG confidence is low..." / "RAG returned no results...")
  │   Output: groups_to_scan = [service]
  │
  └─ Flow 5: EXCEPTION FALLBACK
      Điều kiện: bất kỳ exception nào
      LLM calls: 0-2
      RAG calls: 0-1
      Reasoning: không có (chỉ có error field)
      Output: groups_to_scan = ["s3"], error = message
```

> **Hệ quả quan trọng cho evaluation:**
> - Faithfulness chỉ đo được ở **Flow 3** (reasoning LLM-generated). Flows 1, 2, 4, 5 có reasoning hardcoded → faithfulness = N/A.
> - Correctness (F1) chỉ áp dụng cho Flows 1, 3 (có `checks_to_scan`). Flows 2, 4, 5 trả `groups_to_scan` → cần metric riêng.
> - Benchmark cần cover tất cả 5 flows, không chỉ flow 3.

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

RAG retrieval có fallback chain nội bộ:
1. `build_context(consumer="planning")` → PlanningBundle (rich, có maturity context)
2. `retrieve_checks()` → basic results (không có maturity)
3. Empty result (RAG unavailable)

#### 4 trục đánh giá

**Structure — Structured Output Compliance:**

> **Khác biệt với Risk Agent:** Planning Agent output luôn là valid dict (do Python code tổng hợp + error handling), nên `json_parse_rate` gần như luôn = 1.0. Thay vào đó, Structure tập trung vào **chất lượng cấu trúc output** và **internal LLM parse success**.

| Sub-metric | Cách tính | Áp dụng flow | Ghi chú |
|---|---|---|---|
| `output_schema_valid` | Output có đúng 1 trong 3 dạng hợp lệ? (checks, groups, error) | Tất cả | Gate check — thay thế json_parse_rate |
| `mutual_exclusivity` | `groups_to_scan` và `checks_to_scan` không cùng non-empty? | Tất cả | Kiểm tra logic consistency |
| `reasoning_nonempty` | `reasoning` field tồn tại và không rỗng? (trừ error flow) | 1, 2, 3, 4 | |
| `valid_check_id_format` | Mỗi ID trong `checks_to_scan` match pattern `[a-z0-9]+_[a-z0-9_]+` và len > 8? | 1, 3 | Prowler check ID format |
| `internal_llm_parse_rate` | Tỷ lệ LLM calls nội bộ (translate_intent, rerank) parse JSON thành công | 2, 3, 4 | Đo chất lượng LLM interaction, không phải final output |

> **Ghi chú triển khai:** `internal_llm_parse_rate` cần instrument `parse_llm_json()` để log success/failure.
> Metric này quan trọng hơn `json_parse_rate` trên final output vì nó phát hiện vấn đề LLM formatting
> mà error handling che giấu.

**Faithfulness — Claim-based Verification (chỉ Flow 3):**

> **Phạm vi hẹp hơn Risk Agent:** Reasoning chỉ do LLM sinh trong Flow 3 (normal rerank).
> Các flow khác có reasoning hardcoded → faithfulness = N/A (không cần đo, không thể hallucinate).
> Benchmark cần tách rõ test cases theo flow để tránh đo faithfulness trên reasoning hardcoded.

Claim decomposition trên `reasoning` field (từ LLM rerank), verify với PlanningBundle context:
- Claim "chọn check X vì severity cao" → verify X tồn tại trong candidates VÀ severity đúng
- Claim "liên quan đến compliance Y" → verify Y có trong control_mapping_ids
- Claim "check X phù hợp với maturity capability Z" → verify Z có trong maturity_capability_ids

| Sub-metric | Cách tính | Ngưỡng đề xuất |
|---|---|---|
| `faithfulness_mean` | supported_claims / total_claims (chỉ trên Flow 3 cases) | >= 0.80 |

Fallback: rule-based heuristic (kiểm tra check_id trong reasoning có nằm trong candidates không).

**Correctness — Check Selection F1 + Service Accuracy:**

> **Vấn đề:** F1 chỉ áp dụng khi agent trả `checks_to_scan` (Flows 1, 3).
> Khi agent trả `groups_to_scan` (Flows 2, 4), cần metric khác: **Service Accuracy**.

*Correctness cho Flows 1, 3 (specific checks):*

So sánh `checks_to_scan` (predicted) với ground truth (expert-labeled relevant checks):

```
Precision = |Selected ∩ Relevant| / |Selected|
  → "Trong các checks agent chọn, bao nhiêu là đúng?"

Recall = |Selected ∩ Relevant| / |Relevant|
  → "Trong các checks cần chọn, agent tìm được bao nhiêu?"

F1 = 2 × Precision × Recall / (Precision + Recall)
```

| Sub-metric | Cách tính | Ngưỡng đề xuất |
|---|---|---|
| `check_selection_precision` | \|Selected ∩ Relevant\| / \|Selected\| | |
| `check_selection_recall` | \|Selected ∩ Relevant\| / \|Relevant\| | |
| `check_selection_f1` | Harmonic mean of Precision and Recall | >= 0.60 |

Ví dụ:
```
Ground truth: [s3_bucket_public_access, s3_bucket_versioning, s3_bucket_encryption]
Agent output: [s3_bucket_public_access, s3_bucket_encryption, s3_bucket_logging]

Precision = 2/3 = 0.67  (s3_bucket_logging sai)
Recall    = 2/3 = 0.67  (thiếu s3_bucket_versioning)
F1        = 0.67
```

*Correctness cho Flows 2, 4 (group scan):*

Khi agent fallback sang group scan, đánh giá **service identification**:

| Sub-metric | Cách tính | Ngưỡng đề xuất |
|---|---|---|
| `service_accuracy` | `groups_to_scan[0]` có đúng service mong đợi? (binary: 0 hoặc 1) | >= 0.90 |

Ví dụ: User request "check IAM users" → expected service = "iam". Nếu agent trả `groups_to_scan: ["iam"]` → đúng. Nếu trả `["s3"]` (silent default) → sai.

> **Tổng hợp Correctness toàn agent:**
> `correctness_overall = w_specific * F1_mean + w_group * service_accuracy`
> Với trọng số phản ánh tỷ lệ flow trong benchmark (ví dụ: 70% specific, 30% group).

*Correctness cho Flow 5 (exception):*

Exception flow luôn tính correctness = 0 (agent failed).

**Completeness — Recall + Flow Appropriateness:**

Đối với Flows 1, 3: Completeness trùng với **Recall** trong F1.

Bổ sung metric **flow appropriateness** cho toàn bộ flows:

| Sub-metric | Cách tính | Ngưỡng đề xuất |
|---|---|---|
| `check_selection_recall` | Tái sử dụng Recall từ F1 (Flows 1, 3) | |
| `flow_appropriateness` | Agent chọn đúng flow cho request? (specific khi cần specific, group khi cần group) | >= 0.85 |

Ví dụ flow_appropriateness:
- Request "scan all iam" → expected: group scan → agent trả groups_to_scan → đúng
- Request "check s3 encryption" → expected: specific checks → agent trả groups_to_scan → **sai** (over-broad)
- Request "s3_bucket_public_access s3_bucket_versioning" → expected: fast track → agent trả checks_to_scan = exact IDs → đúng

#### Benchmark dataset (cần tạo)

Benchmark cần **cover tất cả 5 flows** với phân bổ hợp lý:

| Flow | Số cases đề xuất | Ví dụ request |
|---|---|---|
| Fast track (flow 1) | 5 | "chạy s3_bucket_public_access và s3_bucket_versioning" |
| Group scan (flow 2) | 5 | "scan all iam", "check s3 group" |
| Normal rerank (flow 3) | 15 | "kiểm tra S3 bucket có bị public access không" |
| Low confidence (flow 4) | 3 | Requests mơ hồ, service không rõ |
| Exception (flow 5) | 2 | Edge cases gây lỗi |

Tổng: ~30 test cases (tương đương Risk Agent benchmark).

Mỗi test case cần:
```json
{
    "case_id": "plan_s3_public_001",
    "expected_flow": "normal_rerank",
    "input": { "user_request": "kiểm tra xem S3 bucket có bị public access không" },
    "rag_context_snapshot": {
        "related_findings": [
            { "check_id": "s3_bucket_public_access", "service": "s3", "title": "S3 Bucket Public Access", "severity": "high" },
            { "check_id": "s3_bucket_level_public_access_block", "service": "s3", "title": "S3 Bucket Level Public Access Block", "severity": "high" },
            { "check_id": "s3_account_level_public_access_blocks", "service": "s3", "title": "S3 Account Level Public Access Blocks", "severity": "high" }
        ],
        "control_mapping_ids": ["block_public_access"],
        "maturity_capability_ids": ["data_protection"]
    },
    "expected": {
        "expected_service": "s3",
        "relevant_checks": ["s3_bucket_public_access", "s3_bucket_level_public_access_block", "s3_account_level_public_access_blocks"],
        "required_reasoning_evidence": ["public access", "s3"],
        "acceptable_output_type": "specific_checks"
    }
}
```

```json
{
    "case_id": "plan_iam_group_scan_001",
    "expected_flow": "group_scan",
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

#### Output format

Agent sinh file report (markdown → html → pdf) gồm nhiều sections, mỗi section do LLM viết:

| Section | LLM method | Mô tả |
|---|---|---|
| Executive Summary | `write_exec_summary()` | Tóm tắt cho C-level (CTO/CISO) |
| System Overview | `write_system_overview()` | Thông tin hệ thống AWS |
| Assessment Goals | `write_assessment_goals()` | Mục tiêu đánh giá |
| Pass Findings | `write_pass_findings_overview()` | Tổng quan findings đạt |
| Fail Findings | `write_fail_findings_overview()` | Tổng quan findings lỗi |
| Remediation Detail | `write_pass/fail_remediation_detail()` | Chi tiết xử lý từng finding |
| Manual Guide | `write_manual_guide()` | Hướng dẫn xử lý thủ công |
| Post-Remediation | `write_post_remediation_analysis()` | Phân tích sau xử lý |
| Recommendations | `write_post_remediation_recommendations()` | Khuyến nghị |

#### RAG context

Report Agent **không sử dụng RAG** trực tiếp. Context đến từ các agent trước (findings, remediation results) được truyền qua `ctx` dict.

#### 4 trục đánh giá

**Structure — Section Checklist:**

| Sub-metric | Cách tính |
|---|---|
| `section_presence_rate` | % sections bắt buộc có trong report (Executive Summary, Findings, Remediation, Recommendations) |
| `markdown_valid` | Report parse được thành valid markdown? |
| `no_template_leak` | Không có placeholder hoặc template syntax lộ ra (ví dụ: `{{variable}}`) |

**Faithfulness — Narrative Grounding:**

Verify các claims trong narrative có dựa trên findings/context thực tế:
- Executive Summary nói "3 Critical findings" → kiểm tra findings data có đúng 3 Critical
- Remediation detail nói "S3 bucket đã được fix" → kiểm tra success_findings có case đó
- **Không bịa đặt thêm findings, số liệu, hoặc sự kiện** không có trong context

| Sub-metric | Cách tính |
|---|---|
| `faithfulness_mean` | Claim-based verification trên narrative sections |

Đây là nơi faithfulness quan trọng nhất — report narrative dài, LLM dễ bịa đặt.

**Correctness — LLM-based Judge (*extension layer*):**

Report Agent sinh free text — không thể dùng Accuracy hay F1. Sử dụng LLM-as-Judge:
```
Prompt: "So sánh report với findings/remediation gốc.
Report có trình bày đúng các sự kiện, con số, và kết quả không?
Score 1-5. Giải thích lý do."
```

| Sub-metric | Cách tính |
|---|---|
| `correctness_judge_mean` | Trung bình LLM judge scores (1-5 → normalize về 0-1) |

Thuộc extension layer do chi phí cao (nhiều LLM calls).

**Completeness — Findings Coverage:**

Report phải đề cập đầy đủ findings — không bỏ sót:

```
Findings Coverage = (Số findings xuất hiện trong report) / (Tổng findings trong input context)
```

| Sub-metric | Cách tính |
|---|---|
| `findings_coverage` | Matching finding_id hoặc event_code giữa report text và input findings |
| `remediation_coverage` | % findings có remediation detail (thay vì chỉ được liệt kê) |

#### Benchmark dataset (cần tạo)

Mỗi test case cần:
```json
{
    "case_id": "report_basic_001",
    "input": {
        "ctx": { ... },
        "report_context": { ... }
    },
    "expected": {
        "required_sections": ["executive_summary", "findings", "remediation", "recommendations"],
        "expected_finding_ids": ["finding_001", "finding_002"],
        "expected_stats": { "total_findings": 10, "critical": 3 }
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
| 5 | Structure (schema + mutual exclusivity + check ID format) | Chưa | Cao | Khác Risk Agent: focus internal LLM parse, không phải final output parse |
| 6 | Faithfulness (claim-based, Flow 3 only) | Chưa | Trung bình | Scope hẹp hơn Risk Agent — chỉ LLM-generated reasoning |
| 7 | Check Selection F1 (Flows 1, 3) | Chưa | **Cao — metric core mới** | Precision + Recall + F1 |
| 8 | Service Accuracy (Flows 2, 4) | Chưa | **Cao — metric core mới** | Bổ sung cho F1 khi agent trả group scan |
| 9 | Flow Appropriateness (Completeness) | Chưa | Cao | Agent chọn đúng flow cho request? |

**Giai đoạn 3 — Report Agent:**

| # | Metric | Trạng thái | Ưu tiên |
|---|---|---|---|
| 9 | Section Checklist | Chưa | Cao — deterministic |
| 10 | Faithfulness (narrative) | Chưa | **Cao — rủi ro hallucination lớn nhất** |
| 11 | Findings Coverage | Chưa | Cao |
| 12 | LLM-based Correctness | Chưa | Thấp — extension layer |

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
| 7 | output_schema_valid | = 1.00 | Structure | Thay json_parse_rate (output luôn valid dict) |
| 8 | mutual_exclusivity | = 1.00 | Structure | groups và checks không cùng non-empty |
| 9 | valid_check_id_format | >= 0.95 | Structure | Chỉ Flows 1, 3 |
| 10 | internal_llm_parse_rate | >= 0.90 | Structure | Đo LLM formatting quality |
| 11 | faithfulness_mean | >= 0.80 | Faithfulness | Chỉ Flow 3 (LLM-generated reasoning) |
| 12 | check_selection_f1 | >= 0.60 | Correctness | Flows 1, 3 |
| 13 | service_accuracy | >= 0.90 | Correctness | Flows 2, 4 |
| 14 | flow_appropriateness | >= 0.85 | Completeness | Tất cả flows |

**Report Agent (đề xuất):**

| # | Tiêu chí | Ngưỡng đề xuất | Trục |
|---|---|---|---|
| 11 | section_presence_rate | = 1.00 | Structure |
| 12 | faithfulness_mean | >= 0.75 | Faithfulness |
| 13 | findings_coverage | >= 0.80 | Completeness |

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
