# Report Agent — Tài liệu kỹ thuật

> **Version:** 5.0
> **Cập nhật:** 2026-04-06
> **Trạng thái:** Production Ready — 32/32 tests passed
> **Scope:** `agents/report_agent.py` + `agents/report_module/*` + data flow + RAG integration

---

## 1. Tổng quan

Report Agent là node cuối cùng trong pipeline PDCA:

```
Nhận data đầy đủ + RAG knowledge → LLM viết nội dung → Render HTML/PDF
```

**Nguyên tắc:**
- Mỗi agent sở hữu data riêng — AnalysisAgent trả kết quả phân tích, không gom metadata
- `build_report_data()` là nơi DUY NHẤT gom data từ state cho report
- Report Agent nhận 1 dict đầy đủ, không đọc file, không query state
- Input là read-only — derived data tạo biến mới (deep copy)
- RAG context là optional — report vẫn hoạt động khi RAG down (graceful degradation)

---

## 2. Kiến trúc

### 2.1 Files

| File | Dòng | Chức năng |
|------|------|-----------|
| `agents/report_agent.py` | ~470 | Pipeline: validate → derive → LLM → enrich → render |
| `agents/report_module/llm_writer.py` | ~580 | 10 LLM sections + `_clean()` + fallback + RAG-enriched prompts |
| `agents/report_module/template.py` | 361 | Full HTML5 template + CSS (tiếng Việt có dấu) |
| `agents/report_module/exporters.py` | 101 | write_file, export_pdf (weasyprint → wkhtmltopdf) |
| `agents/report_module/chart_util.py` | 77 | Severity bar + Pass/Fail pie (no-data safe) |

### 2.2 Pipeline run()

```
data (from build_report_data + rag_context)
  │
  ├── _validate_input()          ← kiểm tra 9 required keys
  ├── _split_by_status()         ← derived: pass/fail lists
  ├── _make_charts()             ← derived: severity + pass/fail charts
  ├── _calc_score()              ← derived: security score 0-100
  ├── _make_report_id()          ← derived: RPT-YYYYMMDD-XXXX
  │
  ├── _build_rag_knowledge()     ← format RAG bundle → text cho LLM
  ├── _write_llm_sections()      ← 7 LLM sections (RAG-enriched prompts)
  │
  ├── _enrich_success/failed/manual()  ← deep copy + LLM detail (RAG risk)
  │
  └── _render()                  ← Jinja2 HTML → write files → PDF
```

---

## 3. Data Flow

### 3.1 Luồng chính

```
verification_node()
  ├── đọc pre_scan.json + post_scan.json (1 LẦN)
  ├── AnalysisAgent.run(pre_scan, post_scan, pipeline_ctx)
  └── state["analysis_results"] = {...}

report_node()
  ├── build_report_data(analysis, aws_context, plan, user_request)
  ├── _fetch_rag_for_report(raw_findings, rag_available)  ← RAG query
  │     └── RAGClient.build_context(consumer="report", check_ids=[...])
  │           └── report_bundle: key_findings, control_themes, recommended_practices
  ├── report_data["rag_context"] = rag_context
  └── ReportAgent.run(report_data)
```

### 3.2 Cấu trúc report_data

```python
{
    "pre":               {"total", "pass", "fail", "severity"},
    "post":              {"initial_pass/fail", "final_pass/fail", "fixed/failed/manual"},
    "findings_table":    [{"stt", "finding", "service", "resource", "severity", "before", "after", "change"}],
    "success_findings":  [...],
    "failed_findings":   [...],
    "manual_findings":   [...],
    "raw_pre_findings":  [...],
    "environment":       {"account_id", "region", "buckets"},
    "scope":             {"services", "date", "user_request"},
    "rag_context":       {"key_findings", "control_themes", "recommended_practices", "confidence"},
}
```

---

## 4. RAG Integration

### 4.1 Điểm tích hợp

| Nơi | Cách dùng RAG | Tác dụng |
|-----|---------------|----------|
| `_fetch_rag_for_report()` | `RAGClient.build_context(consumer="report")` | Lấy report_bundle |
| `_build_rag_knowledge()` | Format bundle → text block | Chuyển RAG data thành prompt text |
| `_write_llm_sections()` | Inject `rag_knowledge` vào 4 sections | LLM viết dựa trên knowledge base |
| `_enrich_success/failed()` | `rag_risk` từ check_id lookup | Per-finding risk description chính thức |
| `_enrich_manual()` | `rag_context` dict cho manual guide | Thông tin check title + risk cho hướng dẫn |

### 4.2 RAG-enriched LLM sections

| LLM Method | RAG param | Dữ liệu RAG inject |
|-----------|-----------|---------------------|
| `write_exec_summary` | `rag_knowledge` | key_findings + control_themes + practices |
| `write_pass_findings_overview` | `rag_knowledge` | key_findings + control_themes |
| `write_fail_findings_overview` | `rag_knowledge` | key_findings + control_themes |
| `write_pass_remediation_detail` | `rag_risk` | Risk description từ Prowler check |
| `write_fail_remediation_detail` | `rag_risk` | Risk description từ Prowler check |
| `write_manual_guide` | `rag_context` | Check title + risk_summary |
| `write_post_remediation_recommendations` | `rag_knowledge` | Recommended practices |

### 4.3 Graceful Degradation

```
RAG available  → rag_context = {key_findings, control_themes, ...}
RAG down       → rag_context = {} → rag_knowledge = "" → prompts không có RAG block
RAG lỗi       → exception caught → return {} → LLM hoạt động bình thường
```

Report **LUÔN** xuất được — RAG chỉ làm giàu thêm nội dung.

---

## 5. LLM Strategy

### 5.1 Xử lý 3 tầng

| Tầng | Cơ chế | Mô tả |
|------|--------|-------|
| 1 | `_clean()` | Xóa placeholders, first person, duplicate titles, collapse spaces |
| 2 | Conditional bypass | PASS=0 / FAIL=0 → template text, không gọi LLM |
| 3 | Fallback | LLM down → `"*Section không khả dụng.*"` |

### 5.2 Output constraints (mọi prompt)

```
- KHÔNG vượt quá {word_limit} từ
- KHÔNG tạo tiêu đề
- KHÔNG dùng ngôi thứ nhất
- KHÔNG dùng placeholder
- KHÔNG lặp lại cùng 1 ý
- Nếu data rỗng → nêu sự thật, KHÔNG suy đoán
- KHÔNG emoji
```

---

## 6. Test Coverage — 32/32 passed

| Category | Tests |
|----------|-------|
| RAG Integration | 4 (context in LLM, empty graceful, knowledge builder, finding map) |
| Hotfix | 5 (deep copy, Vietnamese, chart zero, safe access, LLM None) |
| Data Integrity | 1 (chart = pre object) |
| Data Flow | 4 (no mutate, no build_report_context, state field, pure function) |
| Bug Fixes | 8 (BUG-01→06, _clean() tests) |
| Reliability | 2 (LLM failure, missing key) |
| Output Quality | 5 (cover page, TOC, HTML5, ID unique, footer) |
| Code Quality | 3 (line count, file count, no dead imports) |

---

## 7. Các bug đã fix

| Bug | Fix |
|-----|-----|
| BUG-01: Chart ≠ text | Chart + text dùng CÙNG object `pre` |
| BUG-02: Title "None" | Fallback: `action or description or "Remediation Action"` |
| BUG-03: Fixed = đỏ | `row.change\|lower == 'fixed'` → `.status-fixed` (xanh) |
| BUG-04: LLM hallucinate PASS=0 | Conditional bypass → template text |
| BUG-05: `['s3']` raw | `scope.services \| join(', ') \| upper` |
| BUG-06: "chúng tôi" | `_clean()` regex IGNORECASE |
