# KẾ HOẠCH TỔNG THỂ — GIAI ĐOẠN HOÀN THIỆN HỆ THỐNG

> **Version:** 3.2  
> **Ngày tạo:** 2026-04-13  
> **Team:** 2 thành viên (A — Agent & Orchestrator, B — RAG & Evaluation)  
> **Phạm vi:** Toàn bộ hệ thống AWS Security Maturity Agent

---

## Mục lục

1. [Tổng quan hiện trạng](#1-tổng-quan-hiện-trạng)
2. [Checklist tổng thể](#2-checklist-tổng-thể)
3. [Phân công & Dependencies](#3-phân-công--dependencies)
4. [Giai đoạn 1: Rebuild Report Agent](#4-giai-đoạn-1-rebuild-report-agent)
5. [Giai đoạn 2: Hoàn thiện Evaluation](#5-giai-đoạn-2-hoàn-thiện-evaluation)
6. [Giai đoạn 3: Refactor toàn bộ Codebase](#6-giai-đoạn-3-refactor-toàn-bộ-codebase)
7. [Giai đoạn 4: Báo cáo tổng hợp & Luận văn](#7-giai-đoạn-4-báo-cáo-tổng-hợp--luận-văn)

---

## 1. Tổng quan hiện trạng

### 1.1 Trạng thái các thành phần

| Thành phần | Trạng thái | Chi tiết |
|---|---|---|
| **RAG System** | Hoàn thành | Top-5 Acc 90.3%, MRR 0.811. Hybrid (BM25+Vector) vượt trội. 11/13 release criteria PASS — 2 FAIL: latency P90 và robustness với negative cases |
| **Planning Agent** | Hoàn thành | Refactored (RAG-first, LLM-conditional). Benchmark 66 test cases: F1 0.843, Service Acc 83.3%, Valid Output 100%. Điểm yếu: multi-service queries (0% acc) |
| **Risk Agent** | Cần refine + chốt | Two-Pass v3 đã refactor. Benchmark 30 cases: Acc 83.3%, QWK 0.941. 6/6 criteria PASS. Phát hiện 5 vấn đề thuật toán cụ thể có thể cải thiện — cần refine trước khi chốt evaluation chính thức |
| **Report Agent** | Cần rebuild | Kế hoạch rebuild đã có (`Report_Agent_Rebuild_Plan.md` v4.0 Final, 28 tests thiết kế). Evaluation cũ đã chạy (19 cases, gate pass 94.7%) nhưng **sẽ không còn giá trị sau rebuild** — cần evaluation mới |
| **Codebase** | Cần refactor | Nhiều vấn đề: god classes (`pipeline.py` 1051 dòng, orchestrator 1006 dòng), mixed LLM interfaces, hardcoded config rải rác, thiếu logging/timeout |
| **Luận văn** | Cần cập nhật | Chương 6 (Evaluation) và Chương 7 (Kết luận) lỗi thời — ghi "tính đến 12/2025" |

### 1.2 Kết quả evaluation toàn hệ thống

| Component | Metric chính | Giá trị | Release Criteria | Trạng thái |
|---|---|---|---|---|
| **RAG Retrieval** | Top-1 / Top-5 Accuracy | 76.4% / 90.3% | 11/13 PASS | Đã chốt |
| **RAG Retrieval** | MRR / NDCG@5 | 0.811 / 0.834 | — | Đã chốt |
| **Planning Agent** | Check F1 / Service Acc | 0.843 / 83.3% | Đã có criteria | Đã chốt |
| **Planning Agent** | Valid Output / Grounded Reasoning | 100% / 87.9% | — | Đã chốt |
| **Risk Agent** | Severity Acc / QWK | 83.3% / 0.941 | 6/6 PASS | Cần refine → re-run → chốt |
| **Risk Agent** | Faithfulness / Evidence Completeness | 0.950 / 82.2% | — | Cần refine → re-run → chốt |
| **Report Agent (cũ)** | Gate Pass / Stats Acc | 94.7% / 100% | Đã có criteria | Sẽ không còn giá trị sau rebuild |
| **Report Agent (mới)** | — | Chưa có | Cần thiết kế mới | Chưa thực hiện |

### 1.3 Evaluation infrastructure đã có

Hệ thống benchmark đã khá trưởng thành — cần tận dụng lại khi thiết kế evaluation cho Report Agent mới:

| Component | Files đã có | Trạng thái |
|---|---|---|
| Generation Benchmark | `gen_metrics.py`, `run_gen_benchmark.py`, `gen_benchmark_cases.json`, `release_criteria_gen.json` | Production-ready |
| Planning Benchmark | `planning_metrics.py`, `run_planning_benchmark.py`, `release_criteria_planning.json` | Production-ready |
| Report Benchmark | `report_metrics.py`, `run_report_benchmark.py`, `release_criteria_report.json` | Đã có nhưng dành cho Report Agent **cũ** — cần adapt |
| RAG Benchmark | `benchmark_retrieval.py`, `benchmark_context.py`, `release_criteria.json` | Production-ready |

---

## 2. Checklist tổng thể

### Giai đoạn 1 — Rebuild Report Agent

- [ ] **1.1** `report_agent.py` rebuilt thành pipeline 5 bước
- [ ] **1.2** `llm_writer.py` rebuilt với `_clean()`, output constraints, fallback 3 tầng
- [ ] **1.3** Template HTML5 mới (tiếng Việt có dấu, severity badges, case-insensitive)
- [ ] **1.4** `exporters.py` và `chart_util.py` cập nhật
- [ ] **1.5** 28/28 unit tests pass
- [ ] **1.6** 6 bugs (BUG-01 → BUG-06) đã fix và không tái xuất hiện
- [ ] **1.7** Pipeline PDCA chạy end-to-end với Report Agent mới — output HTML/MD/PDF đúng

### Giai đoạn 2 — Hoàn thiện Evaluation

**2A — Risk Agent: Refine trước khi chốt**
- [ ] **2.1** Phân tích 5 vấn đề thuật toán đã xác định từ benchmark insights
- [ ] **2.2** Implement các cải thiện có priority cao (Pass 2 rules, rubric High vs Critical)
- [ ] **2.3** Implement các cải thiện có priority trung bình (evidence preservation, confidence-aware logic)
- [ ] **2.4** Chạy lại benchmark sau khi refine — so sánh với baseline TP-v3 (83.3%)
- [ ] **2.5** Chốt kết quả chính thức với bảng tóm tắt cho luận văn

**2B — Report Agent mới: Evaluation sau rebuild**
- [ ] **2.6** Report Agent **mới**: adapt evaluation framework từ bản cũ (4 trục)
- [ ] **2.7** Report Agent **mới**: tạo/cập nhật dataset (15–25 cases, input/output format mới)
- [ ] **2.8** Report Agent **mới**: chạy benchmark và thu thập kết quả
- [ ] **2.9** Report Agent **mới**: kiểm tra release criteria

**2C — Tổng hợp**
- [ ] **2.10** Cross-component analysis (RAG lift, E2E quality, model comparison)

### Giai đoạn 3 — Refactor Codebase

- [ ] **3.1** Tách `graph_orchestrator.py`: node functions ra `nodes/`, sửa tên file
- [ ] **3.2** Tách `pipeline.py` (1051 dòng) thành 4–5 modules nhỏ
- [ ] **3.3** Tách `normalizers.py` (500+ dòng) thành 3 modules
- [ ] **3.4** Consolidate LLM interface trong BaseAgent (chỉ giữ LangChain)
- [ ] **3.5** Centralize config — tạo `agent_config.py`
- [ ] **3.6** Thêm timeout cho concurrent operations và polling loops
- [ ] **3.7** Structured logging thay thế `print()` toàn bộ codebase
- [ ] **3.8** Type hints đầy đủ cho public methods
- [ ] **3.9** Xoá dead code, deprecated methods
- [ ] **3.10** Không file nào vượt 400 dòng
- [ ] **3.11** Tests vẫn pass, benchmark không regression sau refactor

### Giai đoạn 4 — Báo cáo & Luận văn

- [ ] **4.1** `Evaluation_Summary_Report.md` hoàn thành
- [ ] **4.2** Luận văn: Chương 4.9.9, Chương 5 cập nhật theo code mới
- [ ] **4.3** Luận văn: Chương 6.5 (RAG), 6.6.1 (Planning) cập nhật số liệu
- [ ] **4.4** Luận văn: Chương 6.6.2 (Risk) viết lại đầy đủ
- [ ] **4.5** Luận văn: Chương 6.6.3 (Report) viết mới cho agent đã rebuild
- [ ] **4.6** Luận văn: Chương 7 (Kết luận) viết lại — phản ánh 04/2026
- [ ] **4.7** PDF luận văn compile thành công

---

## 3. Phân công & Dependencies

### 3.1 Dependency Graph

```
         ┌──────────────────────┐     ┌────────────────────┐
         │  GĐ1: Rebuild        │     │  GĐ2a: Risk Agent  │
         │  Report Agent        │     │  Review & Chốt     │
         │  [Người A]           │     │  [Người B]         │
         └──────────┬───────────┘     └──────────┬─────────┘
                    │                             │
                    ▼                             │
         ┌──────────────────────┐                 │
         │  GĐ2b: Report Agent  │◄────────────────┘
         │  Evaluation MỚI      │
         │  [Người B]           │
         └──────────┬───────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
┌───────────────┐     ┌─────────────────┐
│  GĐ3: Refactor│     │  GĐ4a: Báo cáo  │
│  Codebase     │     │  tổng hợp       │
│  [A và B]     │     │  [Người B]      │
└───────┬───────┘     └────────┬────────┘
        │                      │
        └──────────┬────────────┘
                   ▼
          ┌─────────────────┐
          │  GĐ4b: Luận văn │
          │  [A và B]       │
          └─────────────────┘
```

### 3.2 Phân công theo người

#### Người A — Agent & Orchestrator

| Giai đoạn | Công việc | Phụ thuộc |
|---|---|---|
| **GĐ1** | Rebuild Report Agent theo plan v4.0 (Sprint 1–4) | Không |
| **GĐ3** | Refactor orchestrator: tách node functions ra `nodes/`, sửa tên file | GĐ1 xong |
| **GĐ3** | Refactor agent layer: consolidate LLM interface, centralize config, timeout, logging | Song song với orchestrator |
| **GĐ3** | Code quality (phạm vi agents + orchestrator): type hints, dead code, file size | — |
| **GĐ4** | Luận văn: Chương 4.9.9 (Reporting Module), Chương 5 (Hiện thực) | GĐ1 + GĐ3 xong |

#### Người B — RAG & Evaluation & Báo cáo

| Giai đoạn | Công việc | Phụ thuộc |
|---|---|---|
| **GĐ2A** | Risk Agent: phân tích benchmark insights → refine thuật toán → re-run → chốt | Không |
| **GĐ2B** | Report Agent mới: adapt framework, cập nhật dataset, chạy benchmark | GĐ1 xong (Người A) |
| **GĐ2** | Tổng hợp cross-component analysis | GĐ2a + GĐ2b xong |
| **GĐ3** | Refactor RAG: tách `pipeline.py`, `normalizers.py`, timeout, BM25 normalize, startup validation | Song song với Người A |
| **GĐ3** | Code quality (phạm vi RAG): type hints, dead code, file size | — |
| **GĐ4** | Báo cáo tổng hợp `Evaluation_Summary_Report.md` | GĐ2 xong |
| **GĐ4** | Luận văn: Chương 6 (toàn bộ), Chương 7 (Kết luận) | GĐ2 + báo cáo xong |

### 3.3 Tiến độ làm việc song song

| Thời điểm | Người A | Người B |
|---|---|---|
| **Bắt đầu** | GĐ1: Rebuild Report Agent | GĐ2A: Risk Agent refine & chốt |
| **Sau GĐ1 xong** | GĐ3: Refactor orchestrator + agents | GĐ2B: Report Agent evaluation mới |
| **Sau GĐ2 xong** | GĐ3 (tiếp tục) | GĐ3: Refactor RAG + Báo cáo tổng hợp |
| **Cuối** | GĐ4: Luận văn (Chương 4, 5) | GĐ4: Luận văn (Chương 6, 7) |

---

## 4. Giai đoạn 1: Rebuild Report Agent

> **Mục tiêu:** Áp dụng kế hoạch rebuild đã thiết kế trong `Report_Agent_Rebuild_Plan.md` v4.0, đưa Report Agent từ trạng thái god method sang pipeline rõ ràng, testable, production-ready.
>
> **Tham chiếu chi tiết:** `Report_Agent_Rebuild_Plan.md` v4.0 Final

### 4.1 Vấn đề của Report Agent hiện tại

Report Agent hiện tại có những vấn đề nghiêm trọng cần giải quyết:

- **God method**: `run()` làm mọi thứ — gom data, tính toán, gọi LLM, render — trong 1 hàm 690 dòng
- **Data không nhất quán**: Charts, text và bảng số liệu tính từ 3 nguồn khác nhau → số liệu lệch (BUG-01)
- **LLM không kiểm soát**: Không có post-processing, không có fallback khi LLM down, không có output constraints → hallucination (BUG-04, BUG-06)
- **Template lỗi**: Case-sensitive comparison (BUG-03), raw Python list trong output (BUG-05), không có tiếng Việt có dấu
- **Không có tests**: 0 unit tests, không thể verify behavior khi thay đổi

### 4.2 Mục tiêu sau rebuild

| Khía cạnh | Trước | Sau |
|---|---|---|
| **Architecture** | God method 690 dòng | Pipeline 5 bước: Validate → Derive → LLM → Enrich → Render |
| **Data integrity** | 3 nguồn data khác nhau → lệch | 1 nguồn duy nhất (`report_data` dict từ orchestrator) |
| **LLM quality** | Không kiểm soát output | `_clean()` post-processing + output constraints + 3-layer fallback |
| **Template** | Markdown+HTML hybrid, lỗi | Full HTML5 + CSS, tiếng Việt có dấu, case-insensitive |
| **Testing** | 0 tests | 28 tests (7 categories), 3 mock LLM classes |
| **Known bugs** | 6 | 0 |

### 4.3 Nguyên tắc thiết kế cốt lõi

1. **Mỗi agent sở hữu data của mình** — Report Agent KHÔNG đi gom data, chỉ nhận data đầy đủ từ orchestrator qua `report_data` dict
2. **Assembly tại orchestrator** — `build_report_data()` là nơi DUY NHẤT gom data từ PDCAState, là hàm thuần tuý (pure function)
3. **Data 1 chiều, không mutate** — Input là read-only; khi cần chỉnh sửa, dùng `copy.deepcopy()`
4. **LLM là optional** — Khi LLM down hoặc data trivial (PASS=0, FAIL=0), report vẫn sinh được với fallback text

### 4.4 Kế hoạch thực hiện

**Sprint 1 — Data Flow & Foundation:**
- Mục tiêu: Đảm bảo data chạy đúng từ orchestrator đến Report Agent
- Tạo `build_report_data()` — hàm thuần tuý gom đủ 9 required keys từ state
- Cập nhật `report_node()` để truyền `data=report_data` thay vì state trực tiếp
- Kết quả đạt được: Data 1 chiều, có validate, không thiếu key

**Sprint 2 — Report Agent Core:**
- Mục tiêu: Chuyển `run()` từ god method sang pipeline 5 bước
- Tách logic thành các methods nhỏ: `_validate_input()`, `_make_charts()`, `_calc_score()`, `_enrich_*()`, `_render()`
- Charts và text dùng CÙNG 1 object data (fix BUG-01)
- Kết quả đạt được: `run()` chỉ còn ~36 dòng logic, mỗi method có 1 trách nhiệm duy nhất

**Sprint 3 — LLM Writer & Template:**
- Mục tiêu: Kiểm soát chất lượng LLM output và tạo template chuyên nghiệp
- `llm_writer.py`: thêm `_clean()` (4 rules post-processing), output constraints, fallback 3 tầng (clean → bypass → fallback text)
- Template HTML5 mới: tiếng Việt có dấu, severity badges màu chính xác, case-insensitive comparison
- Fix BUG-03 (case-sensitive), BUG-05 (raw list), BUG-06 (first person)
- Kết quả đạt được: LLM output sạch, template chuyên nghiệp, không còn 6 bugs cũ

**Sprint 4 — Integration & Testing:**
- Mục tiêu: Đảm bảo rebuild không làm hỏng pipeline và đạt đủ test coverage
- 28 tests chia 7 categories: Hotfix, Data Integrity, Data Flow, Bug Fixes, Reliability, Output Quality, Code Quality
- 3 mock LLM classes để test không cần Ollama
- Chạy pipeline PDCA end-to-end để verify output HTML/MD/PDF
- Kết quả đạt được: 28/28 pass, pipeline E2E chạy thành công

---

## 5. Giai đoạn 2: Hoàn thiện Evaluation

> **Mục tiêu:** Đưa từng agent về trạng thái tốt nhất trước khi chốt evaluation chính thức, sau đó tổng hợp kết quả toàn hệ thống.
>
> **Nguyên tắc cốt lõi:** Kết quả evaluation một khi đã chốt sẽ đưa vào luận văn và không thay đổi nữa. Vì vậy, thứ tự đúng là: **cải thiện agent trước → chạy evaluation → chốt**. Không chốt trên agent còn vấn đề đã biết.

---

### Tại sao cần phân biệt "Agent-level refactor" và "System-level refactor"

Có hai loại thay đổi khác nhau về bản chất:

| Loại | Phạm vi | Thời điểm | Ảnh hưởng evaluation |
|---|---|---|---|
| **Agent-level refactor** | Thuật toán, LLM strategy, prompt của từng agent | TRƯỚC khi chốt evaluation | Có — thay đổi output của agent |
| **System-level refactor** | Kiến trúc, cấu trúc thư mục, code quality chung | SAU khi chốt evaluation (GĐ3) | Không — chỉ thay đổi structure, không thay đổi behavior |

Giai đoạn 2 xử lý **agent-level refactor** cho Risk Agent (agent duy nhất còn vấn đề thuật toán đã biết) và evaluation cho Report Agent sau rebuild. Giai đoạn 3 xử lý phần còn lại.

---

### 5.1 Risk Agent — Refine trước khi chốt

#### Tại sao cần refine, không chỉ chốt

Risk Agent Two-Pass v3 đã PASS tất cả 6 release criteria (Acc 83.3%, QWK 0.941). Tuy nhiên, từ phân tích benchmark đã xác định được **5 vấn đề cụ thể ở cấp độ thuật toán** mà nếu được cải thiện có thể đẩy accuracy lên đáng kể trước khi công bố kết quả chính thức. Vì kết quả sau khi chốt sẽ ghi vào luận văn, nên đây là cơ hội duy nhất để cải thiện.

Ngoài ra, việc refine trước khi chốt còn cho phép ghi nhận **câu chuyện cải thiện** (improvement narrative) trong luận văn — từ Single-Pass (66.7%) → TP-v0 (70%) → TP-v1 (76.7%) → TP-v2 (80%) → TP-v3 (83.3%) → **TP-v4 (mục tiêu)** — đây là bằng chứng về quá trình nghiên cứu có chiều sâu.

#### 5 vấn đề đã xác định và hướng cải thiện

**Vấn đề 1 — Pass 2 rules quá conservative với Critical findings** *(Priority: Cao)*

- **Hiện tượng**: 4/5 case sai đều là trường hợp underprediction của Critical (IAM privilege escalation, EC2 public exposure). Pass 2 hạ severity xuống khi có mâu thuẫn giữa LLM draft và RAG official, kể cả khi finding description rõ ràng là Critical.
- **Nguyên nhân**: Pass 2 rules hiện tại đối xử đối xứng giữa nâng và hạ severity — nhưng trong security context, việc bỏ sót Critical nguy hiểm hơn nhiều so với false alarm.
- **Hướng cải thiện**: Tách riêng rules cho ascending (draft→higher) và descending (draft→lower). Quy tắc ascending nên aggressive hơn khi finding có dấu hiệu privilege escalation hoặc public exposure.

**Vấn đề 2 — Rubric Pass 1 không phân biệt rõ High vs Critical** *(Priority: Cao)*

- **Hiện tượng**: Llama3.2 dự đoán 0 case "High" trong khi ground truth có 4 case High. Tất cả bị predict thành Critical hoặc Medium.
- **Nguyên nhân**: Rubric hiện tại định nghĩa High (7-8) và Critical (9-10) theo thang điểm nhưng không có ví dụ cụ thể phân biệt ngưỡng — model 3.2B không đủ khả năng tự suy ra ranh giới.
- **Hướng cải thiện**: Thêm ví dụ cụ thể vào SYSTEM_PROMPT_PASS1: High = "misconfiguration cần thêm bước để exploit", Critical = "đường thẳng đến compromise (public access + sensitive data, admin privilege grant trực tiếp)".

**Vấn đề 3 — Pass 2 reasoning mô tả quá trình điều chỉnh thay vì mô tả lỗ hổng** *(Priority: Trung bình)*

- **Hiện tượng**: Faithfulness nhỏ hơn expected (0.950 vs 0.967 no-RAG). 3/30 cases có reasoning kiểu "Đã điều chỉnh từ High xuống Medium vì official severity là Medium..." — mô tả mechanics của Two-Pass thay vì giải thích tại sao finding nguy hiểm.
- **Nguyên nhân**: Pass 2 output template không bắt buộc giữ lại evidence gốc từ finding description.
- **Hướng cải thiện**: Khi severity thay đổi, Pass 2 phải dẫn chiếu cụ thể bằng chứng từ finding description trước khi giải thích lý do điều chỉnh.

**Vấn đề 4 — Confidence từ RAG chưa được tận dụng đúng cách** *(Priority: Trung bình)*

- **Hiện tượng**: RAG cung cấp confidence level (high/medium/low) nhưng chỉ được inject là một câu prose hint — không có trọng lượng cấu trúc. Với low-confidence RAG match, model vẫn có thể anchor vào RAG severity sai.
- **Hướng cải thiện**: Biến confidence thành constraint cấu trúc trong Pass 2: nếu confidence=low thì Pass 2 cần justify explicitly tại sao tin RAG hơn finding description.

**Vấn đề 5 — 0 High predictions (systematic bias)** *(Priority: Thấp — có thể được giải quyết bởi vấn đề 1+2)*

- **Hiện tượng**: Không có case nào được predict là High — model thiên về Critical hoặc Medium/Low.
- **Hướng cải thiện**: Theo dõi xem vấn đề 1+2 có giải quyết được không. Nếu không, xem xét thêm few-shot examples cho High severity.

#### Kế hoạch thực hiện

| Bước | Nội dung | Kết quả đạt được |
|---|---|---|
| **1. Baseline** | Verify TP-v3 current state — chạy benchmark để có baseline chính xác | Số liệu baseline để so sánh |
| **2. Implement Priority Cao** | Fix Pass 2 rules (vấn đề 1) + Cập nhật rubric Pass 1 (vấn đề 2) | Kỳ vọng tăng accuracy lên ~87–90% |
| **3. Evaluate** | Chạy lại benchmark 30 cases. Ghi nhận impact của từng thay đổi | Kết quả trung gian |
| **4. Implement Priority Trung bình** | Fix evidence preservation (vấn đề 3) + Confidence-aware logic (vấn đề 4) | Kỳ vọng tăng faithfulness, completeness |
| **5. Final Evaluate** | Chạy benchmark lần cuối. So sánh toàn bộ với TP-v3 baseline | Kết quả chính thức |
| **6. Chốt** | Nếu kết quả tốt hơn hoặc bằng → đánh dấu "Final". Tạo bảng tóm tắt cho luận văn | Báo cáo Final |

#### Ranh giới quan trọng: Được phép thay đổi gì trong giai đoạn này

| Được phép (agent-level refactor) | Không được phép |
|---|---|
| Cải thiện SYSTEM_PROMPT_PASS1, SYSTEM_PROMPT_PASS2 | Thay đổi kiến trúc Two-Pass (đây là điều đang evaluate) |
| Điều chỉnh Pass 2 adjustment rules | Thêm Pass 3 hoặc thay đổi số lượng LLM calls |
| Cập nhật output template của Pass 2 | Thay đổi RAG integration strategy |
| Fix code quality (logging, type hints, config) | Thay đổi batch size, caching strategy |
| Thêm ví dụ vào rubric | Thay đổi evaluation metrics hoặc test cases |

#### Kết quả mong đợi

- Risk Agent version mới (TP-v4) với accuracy cao hơn TP-v3 (mục tiêu: ≥87%)
- Improvement narrative rõ ràng: Single-Pass → Two-Pass → TP-v4
- Kết quả chính thức được chốt với bảng so sánh trước/sau
- Phân tích RAG lift: âm với Single-Pass → dương và tăng dần qua các version Two-Pass

### 5.2 Report Agent MỚI — Thiết kế và Thực hiện Evaluation

> **Điều kiện bắt buộc:** Giai đoạn 1 phải HOÀN THÀNH trước. Report Agent phải đã rebuild, 28/28 tests pass, pipeline E2E chạy được.
>
> **Lưu ý:** Report Agent sau khi rebuild là một agent hoàn toàn mới về kiến trúc — không cần agent-level refactor thêm vì đã được thiết kế đúng từ đầu. Giai đoạn này chỉ tập trung vào evaluation.

#### Tại sao cần evaluation mới

- Report Agent cũ và mới có **kiến trúc hoàn toàn khác** (god method vs pipeline 5 bước)
- Output format thay đổi (Markdown+HTML hybrid → Full HTML5)
- LLM strategy thay đổi (không có fallback → 3-layer fallback với `_clean()`)
- Dataset cũ (19 cases) được thiết kế cho agent cũ — input/output spec không còn phù hợp
- Tuy nhiên, **framework 4 trục** (Structure, Correctness, Faithfulness, Completeness) và **cấu trúc release criteria** vẫn còn giá trị — cần adapt, không cần tạo lại từ đầu

#### Những gì cần thiết kế lại

**a) Adapt Framework đánh giá:**

Framework cũ đã có 4 trục tốt, nhưng metric cụ thể cần cập nhật cho agent mới:

| Trục | Metric cũ (Report Agent cũ) | Cần adapt cho Report Agent mới |
|---|---|---|
| **Structure** | HTML valid, section presence, no template leak, no None display | Thêm: HTML5 doctype, cover page validation, severity badge colors, tiếng Việt có dấu |
| **Correctness** | Stats accuracy, findings table accuracy, score accuracy, status color accuracy | Giữ nguyên — vẫn relevant. Thêm: verify `_calc_score()` formula, verify derived data từ cùng 1 nguồn |
| **Faithfulness** | Numerical faithfulness (71.92%) | Cải thiện: thêm claim-based faithfulness cho LLM sections. Kiểm tra `_clean()` có hoạt động đúng không |
| **Completeness** | Findings coverage, bypass correctness | Thêm: service coverage, severity distribution coverage, khuyến nghị cho từng vấn đề |

**b) Tạo/cập nhật Dataset:**

Dataset cũ có 19 test cases với 10 scenarios. Cần review và cập nhật:
- Giữ lại các scenarios hợp lệ: standard, all_pass, all_fail, minimal, mixed, multi_service, high_volume
- Cập nhật input format: `report_data` dict theo spec mới (9 required keys thay vì format cũ)
- Cập nhật expected output: phù hợp với template HTML5 mới
- Thêm scenarios mới nếu cần: test `_clean()` effectiveness, test fallback khi LLM down
- Mục tiêu: 15–25 test cases

**c) Cập nhật Release Criteria:**

| Metric | Threshold đề xuất | Lý do |
|---|---|---|
| Structure Gate Pass | >= 95% | Agent mới có `_validate_input()` nên phải đạt cao hơn |
| Data Correctness (Stats + Findings + Score) | 100% | Số liệu phải chính xác tuyệt đối |
| Faithfulness | >= 0.80 | Agent mới có `_clean()` và constraints — phải đạt cao hơn agent cũ (71.92%) |
| Completeness | >= 85% | Agent mới có coverage selector — phải cover đủ findings quan trọng |
| LLM Fallback Rate | < 15% | Fallback chỉ xảy ra khi LLM down, không phải vì output kém |

#### Kế hoạch thực hiện

1. **Adapt `report_metrics.py`**: Cập nhật metrics cho agent mới — thêm HTML5 checks, claim-based faithfulness, `_clean()` effectiveness
2. **Cập nhật dataset**: Review 19 cases cũ, cập nhật input/output format, thêm scenarios mới
3. **Cập nhật `release_criteria_report.json`**: Thresholds mới phản ánh agent mới
4. **Adapt `run_report_benchmark.py`**: Đảm bảo runner tương thích với agent mới
5. **Chạy benchmark**: Tối thiểu 2 configs (llama3.2 with/without RAG) để đo RAG lift
6. **Phân tích kết quả**: So sánh với agent cũ, xác định cải thiện, ghi nhận hạn chế

#### Kết quả mong đợi

- Framework evaluation adapted cho Report Agent mới
- Dataset 15–25 test cases với input/output format mới
- Kết quả benchmark chính thức với release criteria PASS/FAIL
- So sánh trước/sau rebuild (agent cũ vs agent mới) — chứng minh rebuild có giá trị

### 5.3 Tổng hợp Cross-component Analysis

Sau khi cả Risk và Report Agent đều có kết quả chính thức, cần tổng hợp kết quả toàn hệ thống:

1. **RAG lift analysis**: RAG ảnh hưởng thế nào đến từng agent downstream? (Planning: dương, Risk: ban đầu âm → cải thiện qua Two-Pass, Report: cần đo)
2. **Improvement narrative**: Trình bày hành trình cải thiện từng agent — đặc biệt Risk Agent từ Single-Pass đến TP-v4 là câu chuyện nghiên cứu có giá trị cao
3. **E2E pipeline quality**: Từ RAG → Planning → Risk → Report, chất lượng có "decay" không?
4. **Model comparison**: llama3.2 vs qwen3:8b across toàn bộ pipeline
5. **Strengths & Weaknesses**: Điểm mạnh (hybrid retrieval, Two-Pass architecture, 3-layer fallback), điểm yếu (multi-service queries, negative cases, latency)

**Output:** `Evaluation_Summary_Report.md` — tài liệu duy nhất gom toàn bộ kết quả, phục vụ trực tiếp cho luận văn Chương 6.

---

## 6. Giai đoạn 3: Refactor toàn bộ Codebase

> **Mục tiêu:** Đưa toàn bộ codebase đạt chuẩn production-level — code sạch, kiến trúc rõ ràng, dễ bảo trì, dễ mở rộng.
>
> **Nguyên tắc:** Refactor từng phần, test sau mỗi thay đổi, git commits nhỏ theo từng concern. Không làm hỏng chức năng đang chạy.
>
> **Phạm vi của GĐ3:** Tập trung vào **system-level refactor** — kiến trúc, cấu trúc thư mục, và code quality của toàn bộ hệ thống. Các agent đã hoàn thiện thuật toán ở GĐ1 (Report) và GĐ2 (Risk). GĐ3 **không thay đổi thuật toán hay LLM strategy** của bất kỳ agent nào — chỉ cải thiện cách tổ chức code.

### 6.1 Orchestrator Layer — Tách trách nhiệm

#### Vấn đề

`graph_orchestator.py` là file lớn nhất (1006 dòng), chứa mọi thứ: 10+ node functions, routing logic, data assembly helpers, và interactive session. Tên file còn sai chính tả (`orchestator` thay vì `orchestrator`). Việc tất cả node functions nằm chung 1 file khiến khó đọc, khó test và khó phân công.

#### Mục tiêu

- Sửa tên file: `graph_orchestrator.py`
- Tách node functions ra thư mục `nodes/` — mỗi node là 1 file độc lập, có thể test riêng
- `graph_orchestrator.py` chỉ còn: `build_graph()` (định nghĩa topology + edges), routing functions, và `run_interactive_session()`
- Mục tiêu: orchestrator chỉ còn ~200–300 dòng

#### Cấu trúc `nodes/` mục tiêu

| File | Chứa gì |
|---|---|
| `nodes/environment_node.py` | `environment_node()` — setup AWS context, check RAG health |
| `nodes/planning_node.py` | `planning_node()` — gọi PlanningAgent |
| `nodes/scanning_node.py` | `scanning_node()` — gọi ScannerAgent |
| `nodes/monitoring_node.py` | `monitoring_node()` — poll job status |
| `nodes/risk_node.py` | `risk_evaluation_node()` — gọi RiskEvaluationAgent |
| `nodes/remediation_nodes.py` | `operational_planning_node()`, `review_task_node()`, `execution_node()` |
| `nodes/verification_node.py` | `verification_node()` — rescan + analysis |
| `nodes/report_node.py` | `report_node()` + `build_report_data()` |

#### Kết quả đạt được

- Mỗi node function nằm ở file riêng — dễ đọc, dễ test, dễ phân công
- Orchestrator chỉ là "bản đồ" của hệ thống — đọc orchestrator là hiểu toàn bộ flow
- Thêm node mới chỉ cần tạo file + đăng ký trong `build_graph()`

### 6.2 Agent Layer — Consolidate và Standardize

#### Vấn đề

- `BaseAgent` có 2 LLM interfaces (`self.client` OpenAI + `self.llm` LangChain) — confusing và dư thừa
- Constants hardcoded rải rác trong từng agent: `ALLOWED_GROUPS`, `BATCH_SIZE`, `POLLING_INTERVAL`, `ALWAYS_MANUAL_TOOLS`
- Polling loops (monitoring, rescan) không có max timeout — có thể chạy vô hạn
- Agents dùng `print()` thay vì structured logging
- Deprecated code còn sót (ví dụ: `run_scan()` trong scanner_agent)

#### Mục tiêu

- **1 LLM interface duy nhất**: Xoá `self.client` (OpenAI), chỉ giữ `self.llm` (LangChain) với `call_llm()` là interface chính
- **1 file config**: Tạo `agents/agent_config.py` gom tất cả constants, cho phép override qua env vars
- **Timeout bảo vệ**: Mỗi polling loop có `MAX_POLL_DURATION`, mỗi concurrent op có timeout
- **Structured logging nhất quán**: `logging.getLogger(__name__)` toàn bộ — DEBUG cho chi tiết, INFO cho flow, WARNING cho degradation, ERROR cho failures
- **Xoá dead code**: Không deprecated methods, không commented-out code

#### Kết quả đạt được

- Đọc bất kỳ agent nào cũng thấy cùng 1 pattern: init → run → output
- Thay đổi config (ví dụ: batch size, polling interval) chỉ cần sửa 1 file
- Không bao giờ bị "hang" vì polling loop vô hạn
- Log output có cấu trúc, có thể grep/filter

### 6.3 RAG System — Tách God Class

#### Vấn đề

- `pipeline.py` là file phức tạp nhất hệ thống (1051 dòng) với 10+ trách nhiệm: exact lookup, lexical search, vector search, result merge, hydration, verification, confidence, reranking, response building
- `normalizers.py` quá lớn (500+ dòng): mixed text cleaning, tokenization, alias generation
- `ThreadPoolExecutor` không có timeout — có thể hang khi HyDE hoặc vector search chậm
- BM25 scores không normalize về [0,1] — sai lệch khi merge với vector scores (vector scores đã ở [0,1])
- Không có validation khi khởi động — missing index files chỉ phát hiện khi query đầu tiên fail

#### Mục tiêu

- **Tách `pipeline.py`** thành 4–5 modules theo trách nhiệm:
  - `pipeline.py` (orchestrator, ~200 dòng) — chỉ điều phối flow
  - `exact_resolver.py` — xử lý exact match (check ID, capability ID)
  - `search_executor.py` — điều phối lexical + vector search song song
  - `result_merger.py` — RRF fusion, dedup, hydration
  - `response_builder.py` — build response, confidence + verification
- **Tách `normalizers.py`** thành 3 modules: `text_cleaning.py`, `tokenization.py`, `aliases.py`
- **Timeout** cho mỗi `future.result()` call
- **BM25 normalization** về [0,1] trước khi merge
- **Startup validation**: kiểm tra index files tồn tại khi app khởi động

#### Kết quả đạt được

- Đọc `pipeline.py` là hiểu flow tổng thể, không bị ngợp trong chi tiết
- Sửa 1 component (ví dụ: reranking) không cần hiểu toàn bộ pipeline
- Hệ thống không bao giờ "hang" im lặng vì missing timeout
- Search scores nhất quán, merge công bằng

### 6.4 Infrastructure & Code Quality

#### Config & Dependencies

- Thống nhất cách đọc config: tất cả từ env vars với defaults rõ ràng
- Tạo/cập nhật `requirements.txt` đầy đủ, pin versions cho reproducibility
- Đảm bảo `__init__.py` đúng và import paths nhất quán

#### Code Quality Standards — áp dụng toàn bộ codebase

| Tiêu chí | Standard |
|---|---|
| **Naming** | snake_case functions/variables, PascalCase classes. Fix sai chính tả |
| **Type hints** | Tất cả public methods có type hints (params + return) |
| **Error handling** | Specific exceptions, log trước khi raise. Không `except Exception` chung chung |
| **Logging** | `logging.getLogger(__name__)` nhất quán |
| **Constants** | Không magic numbers/strings. Tất cả constants có tên, đặt trong config |
| **File size** | Không file nào vượt 400 dòng — nếu vượt phải tách |
| **Single Responsibility** | 1 file = 1 trách nhiệm chính |
| **Dead code** | Xoá hết — không comment out, không deprecated |

### 6.5 Cấu trúc thư mục mục tiêu

```
DoAn/
├── graph_orchestrator.py        # ~200–300 dòng — build_graph() + routing + session
├── AgentState.py
├── config.py
├── api_server.py
├── requirements.txt             # Đầy đủ, pin versions
│
├── nodes/                       # MỚI — tách từ orchestrator
│   ├── environment_node.py
│   ├── planning_node.py
│   ├── scanning_node.py
│   ├── monitoring_node.py
│   ├── risk_node.py
│   ├── remediation_nodes.py
│   ├── verification_node.py
│   └── report_node.py
│
├── agents/
│   ├── base_agent.py            # Consolidated — chỉ LangChain interface
│   ├── agent_config.py          # MỚI — centralized constants
│   ├── [11 agent files]         # Mỗi agent < 400 dòng, structured logging
│   ├── shared/
│   └── report_module/           # Rebuilt (GĐ1)
│
├── RAG/app/
│   ├── retrieval/
│   │   ├── pipeline.py          # ~200 dòng — orchestrator only
│   │   ├── exact_resolver.py    # MỚI
│   │   ├── search_executor.py   # MỚI
│   │   ├── result_merger.py     # MỚI
│   │   └── response_builder.py  # MỚI
│   └── ingestion/
│       ├── normalizers.py       # ~100 dòng — orchestrator only
│       ├── text_cleaning.py     # MỚI
│       ├── tokenization.py      # MỚI
│       └── aliases.py           # MỚI
│
├── benchmark_llm_gen/           # Evaluation framework
├── tests/
└── docs/                        # Báo cáo evaluation
```

---

## 7. Giai đoạn 4: Báo cáo tổng hợp & Luận văn

> **Mục tiêu:** Tổng hợp kết quả evaluation và cập nhật luận văn phản ánh trạng thái thực tế (04/2026).

### 7.1 Báo cáo tổng hợp Evaluation

Tạo `Evaluation_Summary_Report.md` — 1 tài liệu duy nhất gom toàn bộ:

1. **Tổng quan phương pháp**: Unified Framework 4 trục, dataset design, release criteria
2. **Kết quả RAG**: Overall + Strategy Comparison (BM25 vs Vector vs Hybrid) + Confidence Distribution
3. **Kết quả Planning Agent**: Accuracy + Latency + RAG Lift + Điểm yếu (multi-service)
4. **Kết quả Risk Agent**: Accuracy + QWK + Faithfulness + RAG Lift (âm với llama3.2, dương với qwen3:8b)
5. **Kết quả Report Agent mới**: 4 trục + so sánh trước/sau rebuild
6. **Cross-component Analysis**: RAG impact, E2E quality, model comparison
7. **Kết luận**: Strengths, Weaknesses, Hướng cải thiện

### 7.2 Cập nhật Luận văn

| Chương | Cần làm | Điều kiện |
|---|---|---|
| 4.9.9 Reporting Module | Cập nhật mô tả architecture mới (pipeline 5 bước, 5 files) | GĐ1 xong |
| 5 Hiện thực hệ thống | Cập nhật theo code refactored (`nodes/`, pipeline tách, report rebuild) | GĐ1 + GĐ3 xong |
| 6.5 RAG Evaluation | Bổ sung số liệu mới nhất, ablation study chi tiết | Đã có data |
| 6.6.1 Planning Evaluation | Cập nhật 66 test cases, F1 0.843, điểm yếu multi-service | Đã có data |
| 6.6.2 Risk Evaluation | Viết lại: Two-Pass v3, 30 cases, RAG lift âm/dương, phân tích chi tiết | GĐ2 (Risk chốt) xong |
| 6.6.3 Report Evaluation | Viết mới hoàn toàn: framework adapted, kết quả agent đã rebuild | GĐ2 (Report eval) xong |
| 7 Kết luận & Hướng phát triển | Viết lại: phản ánh 04/2026, kết quả thực tế, hạn chế, hướng đi | Tất cả GĐ xong |

---

> **Ghi chú:** Kế hoạch này là tài liệu sống. Cập nhật khi có thay đổi về tiến độ hoặc yêu cầu. Mỗi giai đoạn nên review kết quả trước khi chuyển sang giai đoạn tiếp.
