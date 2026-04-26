# Baseline Gaps — Report Agent (Single-query RAG)

> **Generated:** 2026-04-23
> **Benchmark run:** `benchmarks/llm_generation/results/baseline_single_query.json`
> **Model:** gemma3:4b @ Ollama, temperature=0.5
> **RAG mode:** Single query — `POST /v1/context/build` với `check_ids`
> **Total cases:** 30 | **Verdict:** PASS

---

## Tóm tắt metrics (baseline)

| Metric | Mean | Min case | Target MVP | Gap |
|---|---|---|---|---|
| structure_pass_rate | **1.0000** | — | ≥ 1.0 | none |
| off_scope_mention_rate | **0.0000** | — | ≤ 0.02 | none |
| scope_accuracy | **1.0000** | — | ≥ 1.0 | none |
| numerical_faithfulness | **0.9867** | 0.80 (`c4_post_remediation_delta`, `c5_rag_empty_fallback`) | baseline + 10% | **−13.3% in worst cases** |
| capability_grounding_rate | **0.9640** | 0.7778 (`c2_numbers_trap`, `c2_capability_absent_in_rag`) | ≥ baseline + 10% | **−18.7% in worst cases** |
| template_data_accuracy | **1.0000** | — | ≥ 1.0 | none |
| ndcg_at_5_severity | **0.9125** | 0.7489 (`c3_reversed_order_input`) | ≥ baseline + 10% | **−18.2% in worst case** |
| claim_support_rate | **N/A** | — | ≥ 0.85 | LLM judge chưa chạy |
| actionability_likert | **N/A** | — | ≥ 3.5 | LLM judge chưa chạy |

---

## Gap 1 — Hallucination số liệu trong section `recommendations`

**Section bị ảnh hưởng:** `recommendations`

**Biểu hiện cụ thể:**
- Cases `c4_post_remediation_delta` và `c5_rag_empty_fallback`: LLM tự bịa số "7" trong phần khuyến nghị (`hallucinated_numbers: ["7"]`)
- Cả hai case đều có định dạng pre/post-remediation (không có `findings` list chuẩn), RAG bundle trả về rỗng hoặc thiếu grounding
- `numerical_faithfulness = 0.80` (chỉ 4/5 sections sạch)

**Root cause:**
Section `write_post_remediation_recommendations` không có grounding từ RAG về số bước/hành động cụ thể. Khi RAG bundle rỗng (`c5_rag_empty_fallback`) hoặc không match được findings (`c4_post_remediation_delta`), LLM tự phát sinh con số ("7 bước", "7 khuyến nghị") không có trong input.

**Giải pháp MVP:** Q3 endpoint `POST /v1/retrieve/remediation` (§3.3 trong plan) — cung cấp authoritative remediation steps thay thế LLM fabrication. RAGViewFormatter `for_recommendations()` inject vào prompt → LLM bám vào số liệu thực.

---

## Gap 2 — Capability grounding yếu khi capability vắng mặt trong RAG bundle

**Section bị ảnh hưởng:** `pass_overview`, `fail_overview`

**Biểu hiện cụ thể:**
- `c2_capability_absent_in_rag` (score 0.7778): Case thiết kế để test capability không có trong RAG bundle → LLM vẫn đề cập capability đó nhưng thiếu grounding (2/9 capabilities ungrounded)
- `c2_numbers_trap` (score 0.7778): Case với numbers nhiều/dễ gây nhiễu → capability grounding giảm vì LLM bị distract bởi số liệu

**Root cause:**
Single Q1 query (`build_context(check_ids=[...])`) chỉ retrieve capabilities dựa trên check_ids cụ thể. Nếu một capability liên quan nhưng không map trực tiếp với check_id trong bundle, nó không được retrieve → LLM hallucinate nội dung capability đó.

**Giải pháp MVP:** Q2 endpoint `POST /v1/retrieve/capability` (§3.2 trong plan) — semantic search trên `maturity_capabilities.json` theo domain/status, trả về `CapabilityTheme` với narrative + common_pitfalls + baselines → cung cấp grounding đầy đủ hơn cho pass/fail analysis.

---

## Gap 3 — Severity ordering giảm khi input findings đến sai thứ tự

**Section bị ảnh hưởng:** `fail_overview` (severity ranking)

**Biểu hiện cụ thể:**
- `c3_reversed_order_input` (ndcg@5 = 0.7489): Input findings được sắp xếp ngược (severity thấp nhất đứng đầu) → output report không re-sort đúng → NDCG giảm 18.2% so với mean

**Root cause:**
Report agent truyền findings vào LLM theo thứ tự nhận được từ input. `RAGViewFormatter.for_fail_analysis()` có sort theo severity (`_sorted_findings()`), nhưng chỉ áp dụng cho RAG bundle findings — không áp dụng cho findings từ `report_data` trực tiếp. LLM không re-order đáng tin cậy.

**Giải pháp MVP:** Đây là quick win **không cần** Q1/Q2/Q3 — sort findings by severity trong `report_agent.py` trước khi truyền vào LLM writer (xem §14.6 backlog B2). Tuy nhiên Q1 enrichment cũng sẽ giúp vì RAG sort theo severity khi retrieve.

---

## Quyết định schema (T1.3)

Dựa trên 3 gaps:

- [x] **Q3 schema** (`RemediationGuide` §3.3) giải quyết Gap 1 — cần field `steps: list[str]` và `tool_commands: dict` để LLM không phải bịa số bước
- [x] **Q2 schema** (`CapabilityTheme` §3.2) giải quyết Gap 2 — `narrative` + `common_pitfalls` cung cấp grounding khi capability vắng mặt trong Q1 bundle
- [x] **Gap 3** không cần thay đổi schema MVP — fix bằng pre-sort trong report_agent.py (§14.6 B2, 15 phút)

**Kết luận:** Schema Q2/Q3 trong plan đúng hướng, không cần update §3.2–§3.3. **Proceed to Phase 2.**

---

## Metrics cần LLM judge (Day 2 — chưa chạy)

- `claim_support_rate` — measure hallucination ở level claim (câu), cần Groq/Gemini judge
- `actionability_likert` — measure xem khuyến nghị có actionable không (1-5 scale)

Hai metrics này có khả năng sẽ lộ thêm weakness, đặc biệt ở section `recommendations` (Gap 1 area). Chạy sau khi Phase 2 hoàn thành để so sánh baseline vs MVP.
