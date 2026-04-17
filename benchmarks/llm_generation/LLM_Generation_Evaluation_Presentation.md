# LLM Generation Evaluation

## Bối cảnh

RAG Evaluation đã xong — trả lời câu hỏi "RAG có tìm đúng tài liệu không?". Generation Evaluation trả lời câu hỏi tiếp theo: "Agent có sử dụng context đúng cách để sinh output chất lượng không?". Một hệ thống retrieval tốt nhưng generation kém vẫn thất bại: RAG trả đúng check nhưng Planning Agent không chọn nó, RAG cung cấp severity "Critical" nhưng Risk Agent đánh "Medium" không lý do, RAG đầy đủ findings nhưng Report Agent bịa đặt số liệu.

Hệ thống gồm 3 agent cần đánh giá, mỗi agent có benchmark riêng:

- **Risk Evaluation Agent** — nhận finding + RAG context, sinh severity + risk_score + reasoning
- **Planning Agent** — nhận user request + RAG context, chọn Prowler checks hoặc group scan
- **Report Agent** — nhận scan results + RAG context, sinh báo cáo HTML hoàn chỉnh

Tài liệu thiết kế framework chi tiết trong [LLM_Generation_Evaluation_Report.md](benchmark_llm_gen/LLM_Generation_Evaluation_Report.md).

---

## Framework: 4 trục đánh giá

Cả 3 agent đều được đánh giá trên cùng 4 trục, theo thứ tự ưu tiên:

```
STRUCTURE       "Output có đúng định dạng không?"      ← gate check, nếu fail thì dừng
     ↓
FAITHFULNESS    "Output có dựa trên context không?"     ← phát hiện hallucination
     ↓
CORRECTNESS     "Output có đúng không?"                 ← so sánh với ground truth
     ↓
COMPLETENESS    "Output có đầy đủ không?"               ← không bỏ sót thông tin
```

Thứ tự này có lý do: Structure là điều kiện tiên quyết — output không parse được thì không tính gì tiếp. Faithfulness là nền tảng — output bịa đặt thì đo correctness vô nghĩa. Correctness đánh giá đáp án. Completeness đánh giá bao phủ.

Mỗi trục được cụ thể hóa (instantiate) khác nhau cho từng agent, nhưng ý nghĩa nhất quán.

---

## Dataset

### Risk Evaluation — 30 cases

File: [benchmark_gen_cases.json](benchmark_llm_gen/benchmark_gen_cases.json)

30 cases phủ 6 AWS services (S3, IAM, EC2, RDS, CloudTrail, KMS), chia 4 category (exact, paraphrase, semantic_hard, risk) và 4 mức severity (Critical, High, Medium, Low).

Mỗi case gồm: `input.finding` (finding từ Prowler scanner), `rag_context_snapshot` (context mà RAG trả về bao gồm official_severity, compliance_mappings, maturity_context), và `expected` (ground truth: ai_severity mong đợi + required_evidence phải xuất hiện trong reasoning). Ví dụ:

```json
{
  "case_id": "risk_s3_exact_001",
  "category": "exact",
  "service": "s3",
  "input": {
    "finding": {
      "status": "FAIL",
      "event_code": "s3_bucket_level_public_access_block",
      "service": "s3",
      "severity": "high",
      "description": "S3 Bucket Level Public Access Block is not configured..."
    }
  },
  "rag_context_snapshot": {
    "confidence": "medium",
    "official_severity": "medium",
    "compliance_mappings": ["block_public_access"],
    "maturity_context": [...]
  },
  "expected": {
    "ai_severity": "Medium",
    "required_evidence": ["public access hoac truy cap cong khai", "CIS hoac compliance"]
  }
}
```

### Planning Agent — 30 cases

File: [benchmark_planning_cases.json](benchmark_llm_gen/benchmark_planning_cases.json)

30 cases chia theo 4 loại input: explicit_checks (5 — user chỉ rõ check IDs), group_request (5 — user yêu cầu scan cả service), specific_intent (15 — user mô tả mục đích cụ thể), ambiguous (5 — yêu cầu mơ hồ). Mỗi case gồm user_request, RAG context snapshot, expected output (checks_to_scan hoặc groups_to_scan, acceptable_output_type).

### Report Agent — 19 cases

File: [benchmark_report_cases.json](benchmark_llm_gen/benchmark_report_cases.json)

19 cases chia 2 nhóm: A_scenario (9 — kịch bản thực tế: standard, all_pass, all_fail, minimal, multi_service) và B_edge_case (10 — trường hợp biên: missing_fields, mixed_case_status, high_volume, zero_severity, complex_remediation). Input là report_data hoàn chỉnh (account_id, region, pre/post scan stats, findings_table, remediation_actions).

---

## Metrics chi tiết theo agent

### Risk Evaluation Agent

Source: [gen_metrics.py](benchmark_llm_gen/gen_metrics.py). Runner: [run_gen_benchmark.py](benchmark_llm_gen/run_gen_benchmark.py).

**Structure** (deterministic, cost=0):
- `json_parse_rate` — output parse được thành JSON?
- `schema_compliance_rate` — có đủ 3 field bắt buộc (severity, risk_score, reasoning)?
- `internal_consistency_rate` — severity và score có nhất quán không? Critical phải đi với score 9–10, High 7–8, Medium 4–6, Low 1–3.

**Faithfulness** (LLM-as-Judge, RAGAS-style):
- Tách reasoning thành các claims (mệnh đề nguyên tử) bằng regex
- Với mỗi claim, dùng LLM judge (llama3.2 local) kiểm tra: claim này có được support bởi RAG context + finding không?
- Score = supported_claims / total_claims
- Nếu không có Ollama, fallback sang rule-based: phát hiện hallucination patterns (ngày tháng bịa, số tiền, nguồn không tên), severity contradictions

**Correctness** (so với ground truth):
- `severity_accuracy` — exact match giữa agent severity và expected severity
- `severity_qwk` (Quadratic Weighted Kappa) — metric cho ordinal classification, phạt nặng khi sai xa (Critical→Low nặng hơn Critical→High). QWK = 1.0 là đồng ý hoàn hảo, 0 là ngẫu nhiên.

**Completeness** (evidence checklist):
- Với mỗi `required_evidence` trong expected, kiểm tra có xuất hiện trong reasoning không
- Hỗ trợ alternatives: `"encryption hoac ma hoa"` nghĩa là tìm "encryption" HOẶC "mã hóa"
- Vietnamese diacritics được strip khi so sánh
- Score = covered / total

### Planning Agent

Source: [planning_metrics.py](benchmark_llm_gen/planning_metrics.py). Runner: [run_planning_benchmark.py](benchmark_llm_gen/run_planning_benchmark.py).

**Structure**:
- `valid_output_rate` — schema hợp lệ (có groups_to_scan và checks_to_scan), mutual exclusivity (không cả hai cùng non-empty), reasoning có nội dung, check IDs đúng format Prowler (phải bắt đầu bằng service prefix hợp lệ, ≥12 ký tự)

**Faithfulness** (keyword grounding + negative checks):
- Positive: reasoning có đề cập evidence từ RAG context (check IDs, service names, severity levels)?
- Negative penalties: check ID bịa đặt (-0.3), output-reasoning mâu thuẫn (-0.3), phantom reference như "theo báo cáo" hay dollar amounts (-0.2)
- Output deterministic (hardcoded reasoning) tự động score 1.0

**Correctness** (F1 + service accuracy + selection analysis):
- Với specific_checks: tính Precision, Recall, F1 so với expected checks
- Với group_scan: service có đúng không?
- `planning_correctness` = 0.7 × F1_mean + 0.3 × service_accuracy
- 3 selection analysis metrics (chỉ áp dụng cho specific_checks cases có ground truth):
  - `over_selection_rate` = FP / |predicted| — đo model chọn dư bao nhiêu check. Giải thích trực tiếp vì sao Precision thấp. Ví dụ: expected {A,B}, predicted {A,B,C,D} → over-sel = 2/4 = 0.50
  - `under_selection_rate` = FN / |relevant| — đo model bỏ sót bao nhiêu check quan trọng. Liên quan trực tiếp đến risk hệ thống (bỏ sót = miss vulnerability). Ví dụ: expected {A,B,C}, predicted {A} → under-sel = 2/3 = 0.67
  - `exact_match` — predicted set == relevant set hoàn toàn (binary). Tiêu chuẩn khắt khe nhất, không cho phép thừa hay thiếu

**Completeness**:
- `action_type_accuracy` — output type (specific_checks hay group_scan) có khớp expected type không?

### Report Agent

Source: [report_metrics.py](benchmark_llm_gen/report_metrics.py). Runner: [run_report_benchmark.py](benchmark_llm_gen/run_report_benchmark.py).

Toàn bộ metrics là **deterministic** (cost=0, không cần LLM judge).

**Structure** (gate check):
- Hard constraints (fail 1 cái = fail cả case): `html_valid` (có DOCTYPE, lang="vi", charset=utf-8), `section_presence_rate` (7 sections bắt buộc), `no_template_leak` (không leak Jinja2/placeholder), `no_none_display` (không hiện "None" trên giao diện)
- Soft constraints (cảnh báo): cover page đầy đủ, charts có mặt

**Correctness** (template data accuracy):
- `stats_accuracy` — số liệu pre/post trong HTML khớp input (total, pass, fail, severity breakdown)
- `findings_table_accuracy` — số dòng table + severity badges đúng
- `score_accuracy` — Security Score hiển thị = _calc_score(pre, post)
- `status_color_accuracy` — CSS classes (status-fixed, status-manual, status-error) đúng

**Faithfulness** (numerical claims):
- Trích xuất tất cả số > 1 trong các sections LLM viết (Executive Summary, Assessment Goals, etc.)
- Build tập known_numbers từ report_data + các giá trị dẫn xuất
- Score = verified_numbers / total_numbers. Không có number → 1.0

**Completeness**:
- `findings_coverage` — finding identifiers có xuất hiện trong HTML
- `conditional_bypass_correctness` — khi pre.pass=0 hoặc pre.fail=0, text bypass hardcoded có hiện đúng không

---

## Benchmark Flow

Cả 3 agent dùng chung pipeline 4 bước. Source: [benchmark_generation.py](benchmark_llm_gen/benchmark_generation.py), [benchmark_planning.py](benchmark_llm_gen/benchmark_planning.py), [benchmark_report.py](benchmark_llm_gen/benchmark_report.py).

```
1. Load cases từ JSON
2. Run inference: tạo agent instance, gọi agent.run(input), capture output + latency
3. Evaluate: với mỗi (case, inference), tính 4 metrics
4. Aggregate: mean per metric, breakdown theo category/service, kiểm tra release criteria
```

Hỗ trợ 3 mode: `--mode full` (inference + evaluate), `--mode inference-only` (chỉ chạy agent, lưu output), `--mode evaluate-only --inference-dir <path>` (đánh giá output đã có). Cho phép tách inference (tốn thời gian, cần RAG server) khỏi evaluation (nhanh, offline).

---

## Kết quả

### Risk Evaluation Agent — PASS 6/6

File: [gen_benchmark_latest.json](benchmark_llm_gen/benchmark_outputs/gen_benchmark_latest.json). 30 cases, model qwen3:8b + RAG context.

```
criterion                           threshold    actual     passed
──────────────────────────────────────────────────────────────────
json_parse_rate_min                  ≥ 1.00       1.0000     ✓
schema_compliance_rate_min           ≥ 0.95       1.0000     ✓
faithfulness_mean_min                ≥ 0.80       0.9500     ✓
severity_accuracy_min                ≥ 0.50       0.8333     ✓
severity_qwk_min                     ≥ 0.45       0.9409     ✓
evidence_completeness_mean_min       ≥ 0.45       0.8222     ✓
```

Theo category:

```
Category        Cases   Severity Acc   Faithfulness   Completeness
exact              8        87.5%          93.8%          70.8%
paraphrase         8        87.5%          91.7%          93.8%
semantic_hard      7        71.4%         100.0%          78.6%
risk               7        85.7%          95.2%          85.7%
```

Theo service:

```
Service       Cases   Severity Accuracy
S3               8       100.0%
RDS              4       100.0%
KMS              2       100.0%
IAM              8        75.0%
CloudTrail       3        66.7%
EC2              5        60.0%
```

**Nhận xét:**

- Agent đánh giá rủi ro đáng tin cậy cho production. Khi sai severity thì chỉ sai lệch 1 bậc (ví dụ High thay vì Critical), không xảy ra trường hợp đánh giá sai nghiêm trọng kiểu Critical thành Low — điều có thể dẫn đến bỏ qua lỗ hổng nguy hiểm.
- Agent hầu như không bịa đặt. Reasoning đều truy nguồn được về RAG context hoặc finding gốc. 5% not_supported không phải hallucination thực sự mà là các câu meta-reasoning ("dựa trên draft_reasoning, giữ lại mô tả...") — noise của phương pháp claim decomposition.
- Chất lượng đồng đều giữa các loại query: agent không phụ thuộc vào cách finding được diễn đạt. Tuy nhiên với semantic_hard, agent có xu hướng "chơi an toàn" — đánh severity thấp hơn thực tế khi không chắc chắn, dẫn đến under-estimate rủi ro.
- EC2 và CloudTrail là 2 services agent đánh giá kém nhất. Đây là hệ quả trực tiếp từ RAG: khi RAG trả context không chính xác (cross-service confusion ở CloudTrail, nhiều checks tương tự ở EC2), agent nhận context sai nên phán đoán sai. Chất lượng generation bị bottleneck bởi chất lượng retrieval.
- Agent có xu hướng viết reasoning ngắn gọn khi finding rõ ràng (exact), dẫn đến bỏ sót compliance mappings trong lập luận. Ngược lại khi finding mô tả dài hơn (paraphrase), agent viết chi tiết hơn. Điều này ảnh hưởng đến khả năng audit reasoning sau này.

### Planning Agent — PASS 9/9

File: [planning_benchmark_latest.json](benchmark_llm_gen/benchmark_outputs/planning_benchmark_latest.json). 30 cases.

```
criterion                           threshold    actual     passed
──────────────────────────────────────────────────────────────────
valid_output_rate_min                ≥ 1.00       1.0000     ✓
grounded_reasoning_rate_min          ≥ 0.80       1.0000     ✓
check_selection_f1_min               ≥ 0.60       0.6562     ✓
service_accuracy_min                 ≥ 0.90       1.0000     ✓
planning_correctness_min             ≥ 0.65       0.7593     ✓
action_type_accuracy_min             ≥ 0.85       1.0000     ✓
over_selection_rate_max              ≤ 0.40       0.3633     ✓
under_selection_rate_max             ≤ 0.40       0.2000     ✓
exact_match_rate_min                 ≥ 0.20       0.3500     ✓
```

3 metrics bổ sung đo chi tiết hơn hành vi chọn check:
- **Over-selection rate** (FP/|predicted|) = 0.363 — 36.3% checks agent chọn là thừa, giải thích trực tiếp vì sao Precision thấp
- **Under-selection rate** (FN/|relevant|) = 0.200 — 20% checks quan trọng bị bỏ sót, liên quan trực tiếp đến risk hệ thống
- **Exact Match rate** = 35% — chỉ 7/20 cases chọn đúng hoàn toàn (tiêu chuẩn khắt khe nhất)

Theo input type:

```
Input Type        Cases   F1 Mean   Svc Acc   Over-sel   Under-sel   EM
explicit_checks      5     1.000      n/a       0.00       0.00     100%
group_request        5      n/a      100%        —          —        —
specific_intent     15     0.542      n/a       0.48       0.27      13%
ambiguous            5      n/a       n/a        —          —        —
```

Theo service:

```
Service       Cases   F1 Mean
S3               6     0.814
KMS              3     0.700
CloudTrail       3     0.633
IAM              7     0.613
RDS              5     0.583
EC2              6     0.475
```

**Nhận xét:**

- Agent đáng tin cậy ở mức "hiểu đúng user muốn gì" — luôn scan đúng service, chọn đúng loại hành động (scan cụ thể vs scan toàn bộ). Không bao giờ bịa check ID không tồn tại. Đây là nhờ thiết kế kết hợp logic nội bộ với RAG thay vì phụ thuộc hoàn toàn vào LLM.
- **Over-selection là vấn đề chính, không phải under-selection** (0.363 vs 0.200). Agent có xu hướng chọn thừa gấp đôi so với bỏ sót. Trong security context, đây là trade-off chấp nhận được: chọn thừa chỉ tốn thêm thời gian scan, bỏ sót có thể miss vulnerability. Tuy nhiên, over-selection 0.484 cho specific_intent vẫn quá cao — gần nửa số checks agent chọn là không cần thiết.
- **Exact Match phân hóa rõ rệt**: explicit_checks đạt 100% (trivially exact do FAST_TRACK), nhưng specific_intent chỉ 13.3% (2/15 cases). Điều này cho thấy agent "gần đúng nhưng không hoàn hảo" — phần lớn cases sai do thêm 1-3 FP, không phải hoàn toàn sai hướng. EM thấp + F1 khá = agent cần tinh chỉnh selection threshold, không cần thay đổi kiến trúc.
- Khoảng cách giữa "user nói rõ" và "user mô tả mục đích" rất lớn (F1 từ 1.0 xuống 0.54, EM từ 100% xuống 13%). Đây là gap chính cần cải thiện — agent cần map tốt hơn từ intent sang checks cụ thể, có thể bằng cách bổ sung intent-to-checks mapping trong RAG.
- **Under-selection tập trung ở IAM compound queries**: "kiểm tra MFA cho tất cả users" cần 3 checks (user MFA + root MFA + hardware MFA) nhưng agent chỉ tìm 1. RAG không recall đủ checks liên quan cho các query phức hợp. 20% under-selection nghĩa là cứ 5 checks quan trọng, có 1 bị bỏ sót — rủi ro cần giảm thiểu.
- EC2 là service agent chọn checks kém nhất — nhiều checks tương tự (security groups, ports, instances) khiến agent không phân biệt được checks nào quan trọng cho intent cụ thể. Vấn đề này nhất quán với RAG evaluation: confusion ở tầng retrieval lan sang tầng planning.
- Agent xử lý yêu cầu mơ hồ tốt — default sang group scan (scan toàn bộ service) thay vì đoán sai. Đây là hành vi an toàn: thà scan thừa còn hơn scan thiếu.

### Report Agent — FAIL (8/10 PASS)

File: [report_benchmark_latest.json](benchmark_llm_gen/benchmark_outputs/report_benchmark_latest.json). 19 cases.

```
criterion                           threshold    actual     passed
──────────────────────────────────────────────────────────────────
html_valid_min                       ≥ 1.00       1.0000     ✓
section_presence_rate_min            ≥ 1.00       1.0000     ✓
no_template_leak_min                 ≥ 1.00       1.0000     ✓
no_none_display_min                  ≥ 1.00       0.9474     ✗
stats_accuracy_min                   ≥ 1.00       1.0000     ✓
findings_table_accuracy_min          ≥ 1.00       1.0000     ✓
score_accuracy_min                   ≥ 1.00       1.0000     ✓
numerical_faithfulness_min           ≥ 0.90       0.7192     ✗
findings_coverage_min                ≥ 0.90       1.0000     ✓
conditional_bypass_correctness_min   ≥ 1.00       1.0000     ✓
```

2 criteria FAIL:
- `no_none_display` = 94.7% (1/19 cases hiện "None" trên giao diện) — lỗi ở edge case missing_fields
- `numerical_faithfulness` = 71.9% (target ≥ 90%) — LLM narrative chứa số liệu không trace được về report_data

Theo nhóm:

```
Group          Cases   Gate Pass   Stats Acc   Faithfulness   Coverage
A_scenario        9      100%       100%         62.4%         100%
B_edge_case      10       90%       100%         80.5%         100%
```

Theo scenario:

```
Scenario              Cases   Faithfulness
multi_service            2       96.2%
complex_remediation      2       82.4%
missing_fields           2       79.2%
mixed_case_status        2       78.2%
all_fail                 2       77.5%
standard                 3       76.5%
all_pass                 2       67.5%
high_volume              1       66.7%
zero_severity            1       66.7%
minimal                  2       20.8%
```

**Nhận xét:**

- Kiến trúc hybrid (template + LLM) chứng minh hiệu quả: mọi số liệu trong bảng, biểu đồ, cover page đều chính xác 100%. Không một con số nào bị template render sai. Report có thể tin tưởng được ở phần dữ liệu cứng.
- Vấn đề nằm ở phần văn bản do LLM viết (executive summary, assessment goals). LLM có thói quen bịa số liệu khi viết narrative — ví dụ report_data có 10 checks nhưng LLM viết "hệ thống đã kiểm tra 15 controls". Người đọc nhìn bảng thấy đúng, đọc narrative thấy số khác — gây mất tin tưởng.
- Hiện tượng bịa số tỉ lệ nghịch với lượng data đầu vào. Khi input phong phú (multi_service), LLM có đủ số thật để trích dẫn nên faithfulness cao. Khi input rất ít (minimal — 1–2 findings), LLM không đủ material nhưng vẫn cố viết narrative dài, nên bịa thêm số để "lấp đầy". Đây là hành vi inherent của LLM, cần giải quyết bằng constraining prompt hoặc post-processing.
- Lỗi hiển thị "None" trên giao diện là bug template, không phải lỗi LLM — xảy ra khi input thiếu field. Fix bằng code, không cần thay đổi model hay prompt.
- Nhìn chung Report Agent chưa sẵn sàng release. Tuy nhiên 2 failures đều có hướng sửa rõ ràng và không ảnh hưởng đến phần dữ liệu cứng (bảng, biểu đồ, score). Rủi ro thực tế: người đọc có thể thấy số trong narrative không khớp số trong bảng.

---

## Tổng hợp 3 agent

```
Agent              Structure   Faithfulness   Correctness                               Completeness        Verdict
Risk Evaluation    100%        95.0%          83.3% acc, 0.94 QWK                       82.2% evidence      PASS 6/6
Planning           100%        100%           65.6% F1, 100% svc, EM=35%               100% action type    PASS 9/9
                                              over-sel=0.363, under-sel=0.200
Report             94.7%       71.9%          100% (deterministic)                      100% coverage       FAIL 8/10
```

**Nhận xét tổng hợp:**

- Hệ thống ổn định về mặt kỹ thuật — output luôn đúng format, pipeline không bị break. System prompt và output parsing được thiết kế tốt, đây là nền tảng quan trọng cho production.
- Có một pattern rõ ràng: agent càng phải sinh nhiều free text, càng dễ hallucinate. Planning gần như không sinh text tự do nên faithfulness 100%. Risk viết reasoning ngắn nên 95%. Report viết narrative dài nên chỉ 71.9%. Đây là insight quan trọng cho thiết kế: nên tối thiểu hóa phần LLM tự viết, tối đa hóa phần template/deterministic.
- Correctness của 3 agent đo những thứ khác nhau về bản chất, không nên so trực tiếp. Nhưng nhìn chung: phần deterministic (template rendering, format parsing) luôn đúng, phần cần LLM phán đoán (severity, check selection) có sai số chấp nhận được.
- **Planning Agent selection analysis** cung cấp insight sâu hơn F1: over-selection (0.363) chiếm ưu thế so với under-selection (0.200), nghĩa là agent có xu hướng chọn thừa hơn bỏ sót. Trong security context đây là hành vi an toàn, nhưng over-selection 0.484 cho specific_intent vẫn cần cải thiện. Exact Match 35% cho thấy phần lớn cases "gần đúng" — agent cần tinh chỉnh selection threshold, không cần thay đổi kiến trúc.
- EC2 là service yếu nhất xuyên suốt từ RAG đến cả 3 agent. Nguyên nhân gốc nằm ở dữ liệu: EC2 có nhiều checks tương tự nhau, gây confusion ở mọi tầng. Cải thiện cần bắt đầu từ document enrichment ở tầng RAG, không phải sửa từng agent.
- Report Agent là mắt xích yếu nhất nhưng cả 2 failures đều sửa được: bug template (fix code) và LLM bịa số (constraining prompt hoặc post-processing filter). Phần dữ liệu cứng của report hoàn toàn chính xác — rủi ro giới hạn ở phần narrative.

Release criteria cho từng agent: [release_criteria_gen.json](benchmark_llm_gen/release_criteria_gen.json), [release_criteria_planning.json](benchmark_llm_gen/release_criteria_planning.json), [release_criteria_report.json](benchmark_llm_gen/release_criteria_report.json).
