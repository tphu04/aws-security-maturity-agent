# Langfuse UI — Hướng dẫn sử dụng cho PDCA AWS Security Agent

> Audience: LVTN reviewer + on-call dev. Hướng dẫn cách đọc/quan sát trace trên Langfuse UI
> sau khi pipeline PDCA đã chạy. Không bao gồm setup (xem [langfuse_setup.md](langfuse_setup.md))
> và không trùng lặp filter recipe của [dashboard.md](dashboard.md).
>
> URL self-host (sau setup theo Option B): http://localhost:3010
> URL cloud: https://cloud.langfuse.com

---

## 1. Login + Layout tổng quan

### 1.1 Đăng nhập
- Self-host bootstrap: `admin@pdca.local` + password sinh bởi `generate-secrets.sh`.
- Cloud: account đã tạo ở §Option A.

### 1.2 Sidebar trái
| Mục | Mục đích cho PDCA |
|---|---|
| **Home** | Số trace 24h gần nhất + chart token usage |
| **Tracing → Traces** | View chính — list trace `pdca.run` |
| **Tracing → Sessions** | Gom nhiều trace cùng `sessionId` (PDCA chưa dùng) |
| **Tracing → Observations** | List span phẳng (filter cross-trace) |
| **Evaluation → Scores** | Bảng giá trị `planning_top_score`, `risk_severity_*`, `outcome_fixed_ratio`, `validation_issues` |
| **Evaluation → Datasets** | (Phase J — chưa dùng) curated input cho regression |
| **Prompts** | (chưa dùng) prompt registry |
| **Dashboards** | Custom chart từ score + metadata |
| **Settings → API Keys** | Cặp `pk-lf-*` / `sk-lf-*` để dán vào PDCA `.env` |
| **Settings → Members** | Thêm reviewer vào project |

### 1.3 Project switcher (góc trên trái)
Self-host bootstrap đặt sẵn project **"PDCA AWS Security Agent"**. Nếu tạo mới, nhớ
update lại API key vào PDCA `.env`.

### 1.4 Environment filter (toolbar trên cùng)
PDCA gửi `LANGFUSE_ENVIRONMENT` = `dev` / `staging` / `prod`. Dùng dropdown này để
tách trace theo môi trường. Mặc định view tất cả.

---

## 2. Đọc 1 trace `pdca.run`

### 2.1 Mở trace
**Tracing → Traces** → click hàng có `name = pdca.run`.

Layout 3 cột:

```
┌─────────────────────────┬──────────────────────────────┐
│ Span tree (trái)        │ Detail panel (phải)          │
│ pdca.run                │ - Input/Output               │
│ ├─ node:environment     │ - Metadata                   │
│ │  ├─ aws:sts:...       │ - Scores                     │
│ │  └─ aws:s3:...        │ - Token usage (nếu LLM)      │
│ ├─ node:planning        │ - Timing                     │
│ │  └─ agent:Planning... │                              │
│ └─ ...                  │                              │
└─────────────────────────┴──────────────────────────────┘
```

### 2.2 Đọc span tree
Click 1 span ở cột trái → cột phải show chi tiết. Phím tắt:
- `↑/↓` — di chuyển span.
- `←/→` — collapse/expand subtree.
- `t` — toggle timing chart trên cùng (Gantt).

### 2.3 Trace topology PDCA tham chiếu
Tham chiếu tree đầy đủ ở [dashboard.md §Trace topology](dashboard.md). Nhanh:
- **`pdca.run`** = root, `input` = user_request, `metadata.pdca.outcome.tag` cho biết kết quả.
- **`node:*`** = mỗi bước LangGraph; duration = wall time của node.
- **`agent:*`** = body 1 agent; duration cho biết LLM round-trip nặng nhất.
- **`tool:*` / `rag:*` / `aws:*` / `scanner:*`** = external call; status = `error` khi fail.
- **`report.section.*`** = 1 section của báo cáo (~15 span).
- **Generation (icon ✨)** = LLM call do callback handler tự capture; có `model`, `usage`,
  `prompt`, `completion`.

### 2.4 Detail panel — các tab
| Tab | Nội dung |
|---|---|
| **Input** | JSON gửi vào span (đã redact AWS account/ARN nếu `LANGFUSE_REDACT_MODE=full`) |
| **Output** | JSON trả về |
| **Metadata** | Custom key (`pdca.*`), `runtime.python_version`, span `level` |
| **Scores** | Float/int score gắn vào trace (nếu là root) hoặc span |
| **Generation** (chỉ LLM) | `model`, `prompt`, `completion`, `usage.{prompt,completion,total}_tokens`, cost ước tính |
| **Events** | Log event tự định nghĩa (PDCA chưa dùng) |

### 2.5 Timing
- Số bên cạnh tên span = duration ms.
- Trong Gantt: thanh ngang dài → bottleneck. Span nội dung trong span cha = parallel
  hay sequential nhìn ngay được.

---

## 3. 5 use case thực dụng

### 3.1 Debug 1 run fail
1. **Tracing → Traces** → filter `metadata.pdca.outcome.tag = "partial_failure"` (hoặc `degraded`).
2. Mở trace mới nhất.
3. Cột trái: tìm span có icon ⚠️ (đỏ) — `level=error`.
4. Detail panel → tab **Output**: thông điệp lỗi gốc.
5. Trace ngược lên cha: span node nào ôm lỗi? → biết nguyên nhân nằm ở RAG / scanner / AWS / LLM.

Mẹo: filter `level = ERROR` ở **Tracing → Observations** để list mọi span lỗi cross-trace.

### 3.2 Quan sát LLM token usage
1. **Tracing → Observations** → filter `type = generation`.
2. Group by `model` (nút cog ⚙ → Group).
3. Cột `usage.totalTokens` sort desc → section nào "ngốn" nhiều token nhất.
4. Click 1 generation → tab **Generation** xem prompt + completion thật.

Spike token = thường do prompt regression hoặc context window bị nhồi nhiều RAG hit.

### 3.3 So sánh 2 run
1. Mở trace A (tab 1), trace B (tab 2).
2. So sánh side-by-side:
   - Tổng latency (top right header).
   - Số observations (badge cạnh trace name).
   - Outcome tag.
   - `planning_top_score` ở tab Scores.

Hoặc: **Dashboards → New dashboard** → add chart `count of traces grouped by outcome.tag` →
xem trend qua thời gian.

### 3.4 Theo dõi HITL latency thật
1. **Tracing → Observations** → filter `name = "hitl:wait"`.
2. Cột `output.latency_human_ms` = thời gian human bấm approve/reject.
3. Sort desc → tail > 5 phút = workflow friction (reviewer phân tâm).

Histogram: **Dashboards → New widget → Histogram** → x-axis `output.latency_human_ms`.

### 3.5 Audit redaction
1. **Tracing → Traces** → mở 1 trace bất kỳ.
2. Tab **Input/Output** của bất kỳ span nào: search `123456789012` (account_id thực).
3. Kỳ vọng:
   - `LANGFUSE_REDACT_MODE=full` (cloud): KHÔNG có 12-digit raw, thấy `***1234`.
   - `LANGFUSE_REDACT_MODE=internal` (self-host): vẫn thấy account/ARN (private network).
4. Search `AKIA[A-Z0-9]{16}`: KHÔNG bao giờ được thấy bất kể mode (credentials luôn mask).

---

## 4. Filter syntax (Tracing & Observations)

Toolbar trên cùng → **Add filter**. Cú pháp filter PDCA hay dùng:

| Field | Operator | Value | Use |
|---|---|---|---|
| `name` | = | `pdca.run` | List chỉ root |
| `name` | starts with | `node:` | List node-level span |
| `name` | starts with | `report.section.` | List spans của ReportAgent |
| `level` | = | `ERROR` | Span lỗi |
| `metadata.pdca.outcome.tag` | = | `success` / `partial_failure` / `degraded` | Tag run |
| `metadata.aws.account_id_redacted` | = | `***1234` | Trace của 1 account |
| `metadata.pdca.risk.severity_dist.critical` | > | `0` | Run có CRITICAL finding |
| `usage.totalTokens` | > | `10000` | Generation tốn nhiều token |
| `latency` | > | `60000` | Span > 60s (chậm) |
| `timestamp` | between | last 24h | Date range filter ở góc phải toolbar |

Multi filter = AND. Combine filter rồi **Save** thành named view (icon ⭐) để re-use.

---

## 5. Score & Dashboard

### 5.1 Đọc score
Trace detail → tab **Scores**:

| Score | Ý nghĩa nhanh | Ngưỡng đỏ |
|---|---|---|
| `planning_top_score` | RAG confidence × severity weighting top finding | < 0.3 → planning yếu |
| `risk_severity_critical` | Số lượng CRITICAL findings | > 0 → cần escalate |
| `risk_severity_high` | Số lượng HIGH findings | > 5 → backlog quá tải |
| `outcome_fixed_ratio` | Auto-fix success / total findings | < 0.5 → low automation |
| `outcome_manual_count` | Findings cần manual | > 10 → workflow friction |
| `validation_issues` | Section bị validator reject | > 2 → LLMWriter regression |

Chi tiết origin: [dashboard.md §Score schema](dashboard.md).

### 5.2 Tạo dashboard custom
**Dashboards → New dashboard** → drag widget:

1. **Line chart** — trend `outcome_fixed_ratio` 7 ngày → biết bot có "khá" hơn theo thời gian không.
2. **Bar chart** — count traces group by `metadata.pdca.outcome.tag` → ratio thành công.
3. **Histogram** — `latency` của `name = node:scan_poll` → poll iteration creep.
4. **Table** — top 10 trace có `validation_issues > 0` → backlog cho LLMWriter cải tiến.

Save layout → share URL với reviewer.

---

## 6. Quan sát realtime khi chạy E2E

Khi orchestrator đang chạy 1 run, mở Langfuse UI ở 1 tab khác:
1. **Tracing → Traces** → bật **Live mode** (toggle ⚡ góc phải).
2. Trace mới sẽ tự xuất hiện ở top khi `start_trace()` được gọi.
3. Span con stream về theo từng node (do `flush_at_node()` flush sau mỗi node).
4. Refresh không cần — Langfuse SSE đẩy update.

> Nếu trace không xuất hiện sau 10s: check `LANGFUSE_FLUSH_AT_NODE=true` trong PDCA `.env`,
> và kiểm tra circuit breaker chưa trip (`docker logs langfuse-langfuse-worker-1 | grep -i error`).

---

## 7. Phím tắt + tips

| Phím | Tác dụng |
|---|---|
| `g` rồi `t` | Tracing → Traces |
| `g` rồi `o` | Tracing → Observations |
| `g` rồi `d` | Dashboards |
| `/` | Focus filter input |
| `Esc` | Đóng detail panel |
| `j` / `k` | Next / previous trace trong list |

Tips:
- **Pin** filter combo hay dùng (icon 📌) — sticky cho cả team.
- **Star** trace mẫu để quote trong LVTN slide (icon ⭐).
- **Export trace** → menu ⋯ trong detail header → JSON. Dùng để audit redaction offline:
  ```bash
  grep -E "AKIA[0-9A-Z]{16}|[0-9]{12}" exported_trace.json
  # Kỳ vọng 0 hit nếu redact mode=full.
  ```

---

## 8. Troubleshooting UI

| Triệu chứng | Hành động |
|---|---|
| Trace list trống | (a) Check environment filter; (b) check `LANGFUSE_ENABLED=true` ở PDCA; (c) check circuit breaker chưa trip. |
| Generation thiếu `usage.totalTokens` | ChatOllama version cũ — pin `langchain-ollama>=1.0`. |
| Span thiếu input/output | Pipeline raise giữa chừng → check `level=error` ở span cha. |
| Latency hiển thị 0ms | Span ended ngay sau enter (no-op khi disabled) — kiểm tra ENV. |
| Score không xuất hiện | `score_safe` chỉ emit khi value khác None; node có thể đã skip — check node log. |
| UI báo "Failed to load trace" | Clickhouse migration chưa xong — `docker compose restart clickhouse langfuse-worker`. |

Khi nghi ngờ data integrity: **Settings → Activity logs** xem audit trail của project.

---

## 9. Reference cho LVTN slide

Trace mẫu nên screenshot vào `docs/observability/screenshots/`:

| Screenshot | Mô tả slide |
|---|---|
| `01_trace_tree_full.png` | Full trace `pdca.run` 12-level — chứng minh end-to-end traceability |
| `02_node_latency_chart.png` | Bar chart per-node duration — chỉ ra bottleneck (thường là `node:report`) |
| `03_hitl_distribution.png` | Histogram `hitl:wait.latency_human_ms` — workflow human factor |
| `04_score_dashboard.png` | Dashboard 6 score → bảng đo chất lượng định lượng |
| `05_redaction_proof.png` | Side-by-side raw account_id `123456789012` vs UI hiển thị `***1234` |

Toàn bộ filter/topology spec: [dashboard.md](dashboard.md).
Operational: [runbook.md](runbook.md).
