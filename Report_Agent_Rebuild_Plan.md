# Report Agent — Tài liệu kỹ thuật

> **Version:** 4.0 (Final)
> **Cập nhật:** 2026-04-05
> **Trạng thái:** Production Ready — 28/28 tests passed
> **Scope:** `agents/report_agent.py` + `agents/report_module/*` + data flow trong `graph_orchestator.py`

---

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Kiến trúc](#2-kiến-trúc)
3. [Data Flow](#3-data-flow)
4. [Chi tiết từng file](#4-chi-tiết-từng-file)
5. [Template & Output](#5-template--output)
6. [LLM Strategy](#6-llm-strategy)
7. [Test Coverage](#7-test-coverage)
8. [Các bug đã fix](#8-các-bug-đã-fix)
9. [Hạn chế đã biết](#9-hạn-chế-đã-biết)
10. [Lịch sử thay đổi](#10-lịch-sử-thay-đổi)

---

## 1. Tổng quan

### 1.1 Nhiệm vụ

Report Agent là node cuối cùng trong pipeline PDCA. Nhiệm vụ duy nhất:

```
Nhận data đ���y đủ → Viết nội dung (LLM) → Render ra file (MD/HTML/PDF)
```

Report Agent **KHÔNG** tính toán số liệu, **KHÔNG** truy cập file scan, **KHÔNG** gom metadata.

### 1.2 Vị trí trong pipeline

```
EnvironmentAgent → PlanningAgent → ScannerAgent → ExecutionAgent
    → RescanAgent → AnalysisAgent ��� [build_report_data] → [ReportAgent] → Output Files
```

### 1.3 Nguyên tắc thiết kế

| # | Nguyên tắc | Mô tả |
|---|-----------|-------|
| 1 | **Mỗi agent sở hữu data của mình** | AnalysisAgent trả kết quả phân tích, không gom metadata |
| 2 | **Assembly ở orchestrator** | `build_report_data()` là nơi DUY NHẤT gom data từ state |
| 3 | **Report Agent nhận data đầy đủ** | `run(data)` — data có mọi thứ report cần |
| 4 | **Data chạy 1 chiều, không mutate** | Input là read-only, derived data tạo biến mới (deep copy) |

---

## 2. Kiến trúc

### 2.1 Cấu trúc files

```
agents/
├── report_agent.py              # 425 dòng — orchestrate render pipeline
└── report_module/
    ├── __init__.py
    ├── llm_writer.py            # 542 dòng — LLM calls + _clean() + fallback
    ├── template.py              # 361 dòng — Full HTML template + CSS
    ├── exporters.py             # 101 dòng — write_file, export_pdf
    ├── chart_util.py            # 77 dòng — matplotlib charts
    └── template_markdown.py     # (legacy — không dùng nữa)
```

### 2.2 Dependency diagram

```
graph_orchestator.py
    │
    ├── build_report_data()       # hàm thuần túy, gom data
    │
    └── ReportAgent
          │
          ├── LLMWriter            # inject BaseChatModel
          │     ├── _ask()         # fallback + _clean()
          │     └── _with_constraints()
          │
          ├─�� LLMTimerProxy        # đo hiệu suất
          │
          ├── chart_util           # make_severity_bar, make_pass_fail_pie
          │
          ├── template.py          # REPORT_TEMPLATE (full HTML)
          │
          └── exporters.py         # write_file, export_pdf
```

### 2.3 ReportAgent.run() — Pipeline 5 bước

```python
def run(self, data):
    # 1. Validate input keys
    self._validate_input(data)

    # 2. Derived data (biến mới, không mutate input)
    charts = self._make_charts(pre, ...)
    score  = self._calc_score(pre, post)

    # 3. LLM content (conditional bypass khi data trivial)
    llm = self._write_llm_sections(...)

    # 4. Enrich findings (deep copy, không mutate gốc)
    success = [self._enrich_success(f) for f in ...]

    # 5. Render HTML → MD → PDF
    return self._render(template_ctx)
```

**36 dòng code** (không tính docstring/comment).

---

## 3. Data Flow

### 3.1 Luồng chính (có remediation)

```
pre_scan.json ──→ đọc 1 LẦN (verification_node)
                       │
                  AnalysisAgent.run(pre_scan, post_scan, pipeline_ctx)
                       │
                  analysis_results → PDCAState
                       │
                  build_report_data(analysis, aws_context, plan, user_request)
                       │
                  report_data dict (đầy đủ, không thiếu)
                       │
                  ReportAgent.run(data=report_data)
                       │
                  Output: HTML, MD, PDF
```

### 3.2 Luồng phụ (no FAIL — skip verification)

```
route_after_risk → "report" (no FAIL findings)
       │
  report_node() — build analysis tối thiểu từ state["raw_findings"]
                   (KHÔNG đọc file lại)
       │
  build_report_data() → ReportAgent.run()
```

### 3.3 Cấu trúc report_data (output của build_report_data)

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

### 3.4 PDCAState fields liên quan

```python
class PDCAState(TypedDict):
    analysis_results: Dict[str, Any]   # output của AnalysisAgent.run()
    raw_findings: List[Dict]           # từ scanning_node (fallback khi skip verification)
    aws_context: Optional[AWSEnvironment]
    assessment_plan: Optional[AssessmentPlan]
    user_request: str
    final_report: str                  # output paths
```

---

## 4. Chi tiết từng file

### 4.1 report_agent.py (425 dòng)

| Class/Method | Mô tả |
|-------------|-------|
| `ReportTimer` | Tích l��y duration cho metrics |
| `LLMTimerProxy` | Proxy đo latency mỗi LLM call |
| `ReportAgent.__init__()` | Inject LLM hoặc auto-create Ollama. Type hints đầy đủ |
| `_create_llm()` | Factory: `llm_config["llm"]` hoặc ChatOllama |
| `run()` | Pipeline chính: validate → derive → LLM → enrich → render |
| `_validate_input()` | Kiểm tra 9 required keys |
| `_split_by_status()` | Tách raw_pre_findings thành pass/fail lists |
| `_make_charts()` | Chart dùng CÙNG object `pre` (fix BUG-01) |
| `_calc_score()` | Security score 0-100 |
| `_make_report_id()` | `RPT-YYYYMMDD-XXXX` |
| `_write_llm_sections()` | 7 LLM sections, conditional bypass khi PASS=0 / FAIL=0 |
| `_build_findings_ctx()` | Context builder cho PASS/FAIL findings (đã gộp, không trùng lặp) |
| `_enrich_success/failed/manual()` | `copy.deepcopy()` — không mutate input |
| `_render()` | Jinja2 render → write HTML + MD + PDF |
| `get_llm_metrics()` | Interface cho orchestrator đọc metrics |

### 4.2 llm_writer.py (542 dòng)

| Component | Mô tả |
|----------|-------|
| `_OUTPUT_CONSTRAINTS` | Block ràng buộc output append vào cuối mọi prompt |
| `__init__(llm=, temperature=0.3)` | Inject LLM hoặc auto-create, temperature configurable |
| `_ask(prompt, fallback)` | Gọi LLM → `_clean()` → trả text. Exception → fallback |
| `_clean()` | 4 rules: placeholder `[...]`, first person, duplicate title, collapse spaces |
| `_with_constraints(prompt, word_limit)` | Append output constraints |
| 10 `write_*()` methods | Mỗi method có prompt riêng + fallback riêng |

**Xử lý LLM 3 tầng:**

| Tầng | Cơ chế | Ví dụ |
|------|--------|-------|
| 1 | `_clean()` trong `_ask()` | Xóa `[placeholder]`, "chúng tôi", title trùng |
| 2 | Conditional bypass | PASS=0 → template text, không g���i LLM |
| 3 | Fallback khi LLM down | `"*Executive summary không khả dụng.*"` |

### 4.3 template.py (361 dòng)

- **Full HTML5**: `<!DOCTYPE html>`, `<html lang="vi">`, charset UTF-8
- **Cover page**: Account, Region, Date, Report ID, Security Score, Confidentiality notice
- **Table of Contents**: 7 mục
- **Tiếng Việt có dấu** đầy đủ
- **Severity badges**: `.sev-critical`, `.sev-high`, `.sev-medium`, `.sev-low`
- **Status colors**: `.status-fixed` (xanh), `.status-manual` (cam), `.status-error` (đỏ)
- **Case-insensitive**: `row.change|lower == 'fixed'`
- **Scope format**: `scope.services | join(', ') | upper` → "S3" thay vì "['s3']"

### 4.4 exporters.py (101 dòng)

| Function | Mô tả |
|---------|-------|
| `write_file(path, content)` | Tạo directory + ghi file UTF-8 |
| `render_html(markdown_text)` | Markdown → HTML (legacy, backward compat) |
| `export_pdf(html, path)` | Fallback chain: weasyprint → wkhtmltopdf → None |

PDF temp file cleanup qua `finally` block — không leak.

### 4.5 chart_util.py (77 dòng)

| Function | Mô tả |
|---------|-------|
| `make_pass_fail_pie()` | Pie chart. total=0 → "No data" (không tạo data giả) |
| `make_severity_bar()` | Bar chart. all=0 → "No data". `plt.close()` trong `finally` |

---

## 5. Template & Output

### 5.1 Cấu trúc báo cáo 7 mục

| Mục | Loại | Nguồn dữ liệu |
|-----|------|----------------|
| 1. Tóm tắt điều hành | LLM | `llm.executive_summary` |
| 2. Phạm vi và phương pháp | Template + LLM | `env`, `scope`, `llm.system_overview`, `llm.assessment_goals` |
| 3. Đánh giá trước khắc phục | Template + LLM | `pre`, `charts`, `llm.pass_overview`, `llm.fail_overview` |
| 4. Bảng chi tiết phát hiện | Template | `table` (findings_table) |
| 5. Chi tiết thực thi khắc phục | Template + LLM | `success`, `failed`, `manual` (enriched) |
| 6. Đánh giá sau khắc phục | Template + LLM | `post`, `llm.post_analysis` |
| 7. Khuyến nghị chiến lược | LLM | `llm.recommendations` |

### 5.2 Output files

| File | Mô tả |
|------|-------|
| `data/final_report.html` | Full HTML5 — file chính |
| `data/final_report.md` | HTML content (giống HTML, dùng html2text sau nếu cần) |
| `data/final_report.pdf` | PDF qua weasyprint/wkhtmltopdf (hoặc None nếu không có) |
| `data/charts/severity_bar.png` | Bar chart mức độ nghiêm trọng |
| `data/charts/pass_fail_pie.png` | Pie chart PASS vs FAIL |

---

## 6. LLM Strategy

### 6.1 10 LLM sections

| Method | Word limit | Fallback |
|--------|-----------|----------|
| `write_exec_summary` | 400 | *Executive summary không khả dụng.* |
| `write_system_overview` | 250 | *Mô tả hệ thống không khả dụng.* |
| `write_assessment_goals` | 200 | *Mục tiêu đánh giá không khả dụng.* |
| `write_pass_findings_overview` | 200 | *Phân tích PASS không khả dụng.* |
| `write_fail_findings_overview` | 200 | *Phân tích FAIL không khả dụng.* |
| `write_pass_remediation_detail` | 350 | *Phân tích kỹ thuật không khả dụng.* |
| `write_fail_remediation_detail` | 350 | *Phân tích lỗi không khả dụng.* |
| `write_manual_guide` | 300 | *Hướng dẫn thủ công không khả dụng.* |
| `write_post_remediation_analysis` | 300 | *Đánh giá hậu kiểm không khả dụng.* |
| `write_post_remediation_recommendations` | 300 | *Khuyến nghị không khả dụng.* |

### 6.2 Output constraints (append mọi prompt)

```
- KHÔNG vượt quá {word_limit} từ.
- KHÔNG tạo tiêu đề (đã có sẵn trong template).
- KHÔNG dùng ngôi thứ nhất (tôi, chúng tôi).
- KHÔNG dùng placeholder [text ở đây].
- KHÔNG lặp lại cùng 1 ý nhiều lần.
- Nếu data bằng 0 hoặc rỗng, nêu rõ sự thật. KHÔNG suy đoán.
- KHÔNG sử dụng emoji hay icon.
```

### 6.3 Post-processing: `_clean()`

| Rule | Regex/Logic |
|------|-------------|
| Xóa placeholder | `re.compile(r'\[.*?\]')` |
| Xóa ngôi thứ nhất | `[Cc]h��ng\s+tôi`, `[Tt]ôi` (IGNORECASE, cover cả không dấu) |
| Collapse spaces | `re.sub(r' {2,}', ' ', text)` |
| Xóa title trùng | Dòng đầu `**...**` chỉ xóa khi `len(lines) > 1` |

---

## 7. Test Coverage

**File:** `tests/test_report_rebuild.py` — **28/28 tests passed**

### Phân loại test

| Category | Tests | Mô tả |
|----------|-------|-------|
| **Hotfix** | 5 | Deep copy, Vietnamese, chart zero, safe access, LLM None |
| **Data Integrity** | 1 | Chart dùng cùng object `pre` |
| **Data Flow** | 4 | Input không mutate, no build_report_context, analysis_results state, build_report_data pure |
| **Bug Fixes** | 8 | BUG-01→06, _clean() placeholders, _clean() duplicate title |
| **Reliability** | 2 | LLM failure fallback, missing key error |
| **Output Quality** | 5 | Cover page, TOC, HTML5, report ID unique, footer |
| **Code Quality** | 3 | run() line count, file count, no dead imports |

### Mock infrastructure

| Class | Mục đích |
|-------|---------|
| `MockLLM` | Return deterministic text — test không cần Ollama |
| `FailingLLM` | Raise ConnectionError — test graceful degradation |
| `NoneReturnLLM` | Return None — test None handling |
| `make_test_data()` | Factory tạo report_data dict đầy đủ |

---

## 8. Các bug đã fix

| Bug | Mô tả | Nguyên nhân gốc | Fix |
|-----|-------|-----------------|-----|
| BUG-01 | Chart không khớp text | Data tính 3 lần từ 3 nơi | Chart và text dùng CÙNG object `pre` |
| BUG-02 | Tiêu đề hiển thị "None" | `f.get("action")` trả None | Fallback: `action or description or "Remediation Action"` |
| BUG-03 | "Fixed" hiển thị màu đỏ | `== 'FIXED'` case-sensitive | `row.change\|lower == 'fixed'` |
| BUG-04 | LLM hallucination khi PASS=0 | LLM suy đoán khi data rỗng | Conditional bypass: template text khi PASS=0 |
| BUG-05 | Scope hiển thị `['s3']` | Raw Python list trong template | `scope.services \| join(', ') \| upper` |
| BUG-06 | LLM dùng "chúng tôi" | Prompt constraint không đủ | `_clean()` regex + output constraints |

### Hotfix bổ sung

| Fix | File | Mô tả |
|-----|------|-------|
| Deep copy enrich | report_agent.py | `copy.deepcopy(f)` thay `dict(f)` |
| Chart zero data | chart_util.py | "No data" thay vì fake 50/50 |
| Safe dict access | graph_orchestator.py | `.get()` với defaults trong `build_report_data()` |
| Pre_scan 1 lần | graph_orchestator.py | Dùng `state["raw_findings"]` thay vì đọc file lại |
| LLM None check | llm_writer.py | `res is None` / `hasattr(res, "content")` |
| Vietnamese regex | llm_writer.py | `re.IGNORECASE`, cover cả có/không dấu |
| Template có dấu | template.py | Toàn bộ heading/label tiếng Việt có dấu |
| Temperature | llm_writer.py | Configurable, default 0.3 |
| Deduplicate | report_agent.py | `_build_findings_ctx()` gộp pass/fail |
| Type hints | report_agent.py | `Optional[str]`, `Optional[Dict]` trên `__init__` |
| Bare except | chart_util.py | `except (ValueError, TypeError)` |
| Title safety | llm_writer.py | Chỉ xóa title khi `len(lines) > 1` |

---

## 9. Hạn chế đã biết

| # | Vấn đề | Mức độ | Ghi chú |
|---|--------|--------|---------|
| 1 | `report_node` gọi `agent.run(report_context=...)` thay vì `agent.run(data=...)` | Medium | Backward compat kwarg, hoạt động đúng. Fix khi refactor |
| 2 | AnalysisAgent giả định finding mất = PASS | Medium | Hợp lệ với Prowler (consistent UIDs). Document rõ |
| 3 | Report ID chỉ 4 hex chars (65K giá trị) | Low | Đủ cho usecase hiện tại. Nâng 8 chars khi cần audit |
| 4 | Template không có Jinja2 `\| default('')` fallback | Low | `_validate_input()` đã chặn case thiếu key |
| 5 | `LLMTimerProxy` mất method signatures | Low | IDE completion không hoạt động, runtime không ảnh hưởng |
| 6 | Prompts hardcode tiếng Việt + AWS S3 | Low | By design cho scope hiện tại |

---

## 10. Lịch sử thay đổi

| Version | Ngày | Nội dung |
|---------|------|----------|
| 1.0 | 2026-04-05 | Bản plan gốc — phân tích hiện trạng, thiết kế mới |
| 2.0 | 2026-04-05 | Plan v2 — data flow first, 5 files, full HTML |
| 2.1 | 2026-04-05 | Sprint 1 hoàn thành — Data Flow + Foundation |
| 2.2 | 2026-04-05 | Sprint 2 hoàn thành — Report Agent Core |
| 2.3 | 2026-04-05 | Sprint 3 hoàn thành — LLM Writer + Template |
| 3.0 | 2026-04-05 | Sprint 4 hoàn thành — Integration + Test (23/23) |
| 3.1 | 2026-04-05 | Hotfix — deep copy, Vietnamese, chart, safe access (28/28) |
| **4.0** | **2026-04-05** | **Tài liệu viết lại hoàn toàn — Final** |

### Thống kê code

| Metric | Trước rebuild | Sau rebuild |
|--------|---------------|-------------|
| report_agent.py | 690 dòng (god method) | 425 dòng (pipeline 5 bước) |
| llm_writer.py | 513 dòng (no fallback) | 542 dòng (+_clean, +constraints, +fallback) |
| template | Markdown+HTML hybrid | Full HTML5 + CSS (361 dòng) |
| exporters.py | wkhtmltopdf only, temp leak | weasyprint→wkhtmltopdf, cleanup (101 dòng) |
| chart_util.py | Fake data khi total=0 | "No data" placeholder (77 dòng) |
| Tests | 0 | 28 tests, 3 mock LLM classes |
| Bugs | 6 known bugs | 0 known bugs |
