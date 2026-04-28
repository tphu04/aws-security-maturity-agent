# Langfuse Integration — Open Questions Analysis

> Tài liệu này đào sâu vào source code hiện tại để trả lời 8 open questions trong [LANGFUSE_INTEGRATION_GUIDE.md](LANGFUSE_INTEGRATION_GUIDE.md). Mỗi câu trả lời gồm: **Evidence** (dẫn chứng code), **Phân tích**, **Khuyến nghị** (phù hợp định hướng REFACTOR_PLAN: chatbot UI + multi-run + production).

---

## Q1. Ollama OpenAI-compat endpoint trả token usage không?

### Evidence
- 4 agent đều dùng `langchain_ollama.ChatOllama` (KHÔNG dùng OpenAI-compat của BaseAgent):
  - [planning_agent.py:242](../pdca/agents/planning_agent.py#L242) — `format="json"`, `temperature=0`.
  - [risk_evaluation_agent.py:127](../pdca/agents/risk_evaluation_agent.py#L127) — `format="json"`.
  - [remediate_planner_agent.py:79](../pdca/agents/remediate_planner_agent.py#L79).
  - [report_module/llm_writer.py:124](../pdca/agents/report_module/llm_writer.py#L124).
- `BaseAgent.client` (OpenAI client) chỉ được gọi qua `BaseAgent.call_llm()` — grep cho thấy **không node/agent nào trong runtime path đang gọi method này**. Nó là dead-ish code (giữ làm escape hatch).

### Phân tích
- `ChatOllama` (langchain-ollama) gọi native API `/api/chat` của Ollama. Response chứa `prompt_eval_count`, `eval_count`, `eval_duration` ở root payload. `langchain_ollama` map sang `AIMessage.usage_metadata = {input_tokens, output_tokens, total_tokens}` và `response_metadata.{eval_count, prompt_eval_count, ...}` (kể từ phiên bản gần đây).
- Langfuse `CallbackHandler` LangChain version reads `response.llm_output` / `generations[].message.usage_metadata` → tự động capture token counts.
- **Cost**: Ollama local → không có $ cost, nhưng token vẫn hữu ích để cảnh báo prompt blowout (đặc biệt `report` node với nhiều section + maturity context).

### Khuyến nghị
- **KHÔNG cần code thêm** — Langfuse handler sẽ pick up tự động từ `usage_metadata`.
- **Verify ở Phase L1**: chạy 1 run, mở 1 generation trong UI, xác nhận field `usage` hiển thị. Nếu không có (Ollama hoặc langchain_ollama version cũ), pin version hoặc patch tay qua `on_llm_end` callback.
- **KHÔNG dùng** `BaseAgent.call_llm()` cho code mới — nếu mở rộng dùng OpenAI-compat (Ollama hỗ trợ `/v1/chat/completions` cũng trả `usage`), thì cũng OK; nhưng nhất quán nên giữ `ChatOllama`.

---

## Q2. Langfuse self-hosted vs cloud — chọn cái nào?

### Evidence
- Settings hiện default: `langfuse_host = "https://cloud.langfuse.com"` ([settings.py:69](../pdca/config/settings.py#L69)).
- **Dữ liệu sẽ bay qua trace**:
  - `aws_context.account_id`, `identity_arn`, danh sách `buckets` ([environment_agent.py:57–69](../pdca/agents/environment_agent.py#L57)).
  - `finding_id`, `resource_id`, `region`, raw OCSF chứa ARN (`arn:aws:s3:::company-data-...`) trong prompt của Risk/Remediation/Report agent.
  - `tool_params` (boto3) — bao gồm bucket name khách hàng, IAM policy ARN.
  - Source code tool (`AnalysisAgent._load_tool_source`) — chỉ open-source code internal, không nhạy cảm.
- README + REFACTOR_PLAN không nêu chính sách data residency → **chưa xác định từ tài liệu**, nhưng theo bản chất hệ thống (audit AWS production của tổ chức), AWS account_id + resource ARN là PII tổ chức.

### Phân tích
- **Cloud Langfuse**:
  - Pro: zero-ops, free tier 50K observations/tháng (đủ cho dev/staging).
  - Con: AWS findings/ARN/account_id rời AWS → có thể vi phạm policy nội bộ của khách hàng (nếu sản phẩm bán cho enterprise/banking).
  - Con: latency network từ VN → cloud (cloud.langfuse.com ở EU).
- **Self-hosted Langfuse** (Docker compose, hoặc Kubernetes — Postgres + Clickhouse):
  - Pro: data ở lại — phù hợp đề tài ĐATN/LVTN sau này thương mại hoá; phù hợp khách hàng có ràng buộc compliance.
  - Pro: unlimited events.
  - Con: ops overhead. Cần resource (Postgres + Clickhouse + Web). Đối với scope đồ án có thể quá nặng.

### Khuyến nghị
- **Phase L0–L3 (dev)**: dùng **cloud Langfuse** với account riêng (free tier đủ); **redact** bucket name + ARN suffix trước khi gửi (xem Q chính trong section 6 của guide).
- **Production / khi có khách hàng thực**: chuyển sang **self-hosted**. Cấu trúc đã hỗ trợ — chỉ đổi `LANGFUSE_HOST` env.
- **Thêm vào `pdca/config/settings.py`** một field `langfuse_redact_pii: bool = True` (default an toàn) → áp dụng ở Phase L2 khi wrap span boto3/RAG để mask `arn:aws:*:*:<account>:` thành `arn:...:<redacted>:`.
- **Document trong README** chính sách: "AWS findings không gửi ra cloud Langfuse khi `LANGFUSE_HOST != localhost`". Đây là decision policy, không phải technical.

---

## Q3. Resume từ checkpoint — Langfuse có nhận append vào trace cũ?

### Evidence
- [orchestrator.py:113](../pdca/orchestrator.py#L113): `thread_id = str(uuid.uuid4())` — **mỗi lần `run_interactive_session()` tạo thread_id MỚI**. Không có flow resume từ run cũ trong CLI hiện tại.
- [scripts/run_e2e_auto.py](../scripts/run_e2e_auto.py) cũng tạo `uuid.uuid4()` mới mỗi lần.
- `SqliteSaver` lưu state theo `thread_id`. Resume = dùng cùng `thread_id` khi gọi lại `app.stream(None, config={...})`. **Hiện chưa có code nào làm việc này** — REFACTOR_PLAN ghi chatbot UI tương lai sẽ cần.
- HITL flow trong cùng 1 process: `app.stream → pause → app.update_state → app.stream` — vẫn cùng `thread_id`, KHÔNG phải resume cross-process.

### Phân tích
- **Tình huống thực tế cần resume cross-process**: chatbot UI khi user đóng browser rồi quay lại. Hiện chưa có.
- **Tình huống resume hiện tại** (HITL trong cùng CLI session): trace VẪN MỞ — Langfuse handler chưa flush, span của các node trước đó chưa đóng → không có vấn đề "append vào trace cũ", chỉ là continue working trace.
- **Khi cross-process resume xuất hiện** (Phase chatbot UI):
  - Langfuse SDK cho phép tạo `trace(id=run_id, ...)` với cùng `id` → SDK sẽ **append** events vào trace đã tồn tại trên server (trace là collection of observations).
  - Nhưng `Span` cha (e.g. `node:execution`) đã bị đóng ở process trước → khi process mới mở span con, span đó sẽ trở thành **root-level** trong trace, làm mất hierarchy.
  - **Workaround**: lưu `span_id` cha vào PDCAState (e.g. field `parent_span_id_review_task`) khi pause. Khi resume → tạo span con với `parent_observation_id=<saved>`.

### Khuyến nghị
- **Phase L1–L4**: KHÔNG xử lý cross-process resume — vì không có flow nào kích hoạt nó. Document giả định "1 trace = 1 process".
- **Phase L5 (chatbot UI)**:
  - Thêm field `_langfuse_node_span_id`, `_langfuse_review_task_span_id` vào PDCAState (NotRequired).
  - Khi pause `review_task`, ghi `span_id` hiện tại + flush.
  - Khi resume từ HTTP endpoint, tạo new span với `parent_observation_id` đọc từ state.
  - Đây cũng là điểm nhạy với SqliteSaver: span_id phải JSON-serializable (string).
- **POC ngắn** (~1h): mở 1 trace, kết thúc, sau đó SDK call lại với `trace_id` cũ → confirm Langfuse UI gộp. Trước khi commit Phase L5.

---

## Q4. Concurrency — `run_id` ContextVar có an toàn?

### Evidence
- [pdca/observability/logger.py:14](../pdca/observability/logger.py#L14): `_run_id_var: ContextVar[str] = ContextVar(...)`.
- [pdca/api_server.py:25](../pdca/api_server.py#L25): FastAPI `BackgroundTasks` được dùng cho 3 endpoint `/v1/scan/*`. BackgroundTasks chạy **trong cùng event loop** sau response (không phải threadpool riêng nếu hàm sync? Thực ra FastAPI BackgroundTasks với hàm sync chạy trên threadpool).
- [pdca/api_server.py](../pdca/api_server.py) — worker `_run_prowler_command_worker` là sync function → BackgroundTasks sẽ chạy trên threadpool của starlette.
- Toàn bộ `pdca/agents/`, `pdca/graph/nodes/` là **sync** — `grep "async def"` không trả kết quả nào trong `pdca/`.
- CLI hiện tại: 1 process = 1 run, không multi-thread.

### Phân tích
- **`ContextVar` semantics**:
  - Trong asyncio: mỗi task có copy context → safe.
  - Trong threading: mỗi thread có separate context → safe **nhưng** child thread không inherit từ parent thread mặc định (cần `contextvars.copy_context().run(...)`).
- **Case hiện tại — CLI**: single-thread sync → ContextVar OK.
- **Case Scanner API hiện tại**: Mỗi request là 1 thread của uvicorn worker; `BackgroundTasks` của FastAPI chạy task trên cùng event loop, nhưng worker là sync → starlette dùng `run_in_threadpool` → thread mới. ContextVar không tự inherit → log của worker không có `run_id`. **Hiện tại OK** vì worker không call `set_run_id` (api_server không phần của graph), nhưng cần lưu ý.
- **Case chatbot UI tương lai (REFACTOR_PLAN Phase 3)**: nhiều user → nhiều run cùng lúc. Phải:
  - Set `run_id` ở mỗi request (FastAPI dependency hoặc middleware).
  - Khi `app.stream()` chạy đồng bộ trong endpoint, OK.
  - Khi spawn background work (e.g. SSE long-running), phải `copy_context()` thủ công.

### Khuyến nghị
- **Phase L1**: 
  - Thêm helper `pdca/observability/logger.py:run_with_run_id(run_id, fn, *args)` wrap `contextvars.copy_context().run(...)` — sẵn sàng cho threading scenario.
  - Document invariant: "Mọi entry-point HTTP/CLI phải gọi `set_run_id(run_id)` ngay đầu request handler".
- **Langfuse SDK** dùng riêng OTLP-style context (`Langfuse.context()`), KHÔNG share `ContextVar` của project. Ổn — không xung đột. Nhưng cần cùng pattern: set trace context đầu request.
- **Phase L5 (chatbot UI)**: thêm FastAPI middleware:
  - Generate / read `run_id` từ header hoặc body.
  - `set_run_id(run_id)` + start Langfuse trace với cùng id.
  - Đảm bảo middleware chạy trước graph stream.
- **Test cần thêm** (đã ghi trong SYSTEM_OVERVIEW open Q): "Multi-run concurrency với threadpool" — assertion: log line của run A không lẫn `run_id` của run B.

---

## Q5. PlanningAgent không kế thừa BaseAgent — callbacks propagation OK?

### Evidence
- [planning_agent.py:230–248](../pdca/agents/planning_agent.py#L230-L248):
  ```python
  class PlanningAgent:
      def __init__(self, model_name, api_key=None, base_url=..., rag_client=None, callbacks=None):
          self.rag_client = rag_client
          self.callbacks = list(callbacks or [])
          self.llm = ChatOllama(..., callbacks=self.callbacks)
  ```
- KHÔNG `extends BaseAgent`, KHÔNG `super().__init__()`. Comment ở line 240 ghi rõ: *"planning_agent không có local TimerCallback — chỉ propagate external callbacks (Langfuse handler)"*.
- So với [risk_evaluation_agent.py:117–132](../pdca/agents/risk_evaluation_agent.py#L117) — extends BaseAgent + có `TimerCallback`:
  ```python
  super().__init__(model_name, api_key, base_url, callbacks=callbacks)
  self.timer = TimerCallback()
  self.llm = ChatOllama(..., callbacks=[self.timer] + self.callbacks)
  ```
- Node-side wiring đã đúng cho cả 2: [graph/nodes/planning.py:18–41](../pdca/graph/nodes/planning.py#L18) và [risk_eval.py:18–33](../pdca/graph/nodes/risk_eval.py#L18) đều extract `callbacks` từ `RunnableConfig` rồi truyền vào agent constructor.

### Phân tích
- **Mechanism propagation giống nhau**: cả Planning và Risk đều passes `callbacks` vào `ChatOllama(callbacks=...)`. Langfuse handler là một `BaseCallbackHandler` LangChain — sẽ nhận `on_llm_start/on_llm_end` từ `ChatOllama.invoke()` chain.
- **Khác biệt duy nhất**: PlanningAgent không có TimerCallback. KHÔNG ảnh hưởng Langfuse — TimerCallback và Langfuse handler độc lập.
- **Risk thực tế**: Nếu dùng `agent.llm.invoke(prompt)` trực tiếp thì handler attached. Nhưng nếu dùng pattern `(prompt | self.llm | StrOutputParser()).invoke(...)` (pipe operator — LangChain LCEL), handler vẫn attach vì callbacks đã ở chỗ `self.llm`. Verify trong [planning_agent.py:801, 854](../pdca/agents/planning_agent.py#L801): cả 2 chỗ đều dùng pipe → OK.
- **Không có gọi llm trực tiếp ở chỗ khác**: grep `self.llm` trong planning chỉ ra LCEL pipeline.

### Khuyến nghị
- **KHÔNG cần refactor PlanningAgent** để kế thừa BaseAgent — overhead lớn, không add value. Pattern hiện tại đã consistent về mặt callbacks contract.
- **Document invariant** (thêm vào docstring `BaseAgent` hoặc `shared/callbacks.py`): *"Mọi agent có LLM PHẢI accept `callbacks: list = None` ở constructor và pass vào `ChatOllama(callbacks=...)`"*.
- **Test smoke** (Phase L1): mock 1 callback, instantiate Planning + Risk, gọi `.run()` mock-LLM, assert `on_llm_start` được trigger ở cả 2.

---

## Q6. Subprocess Prowler — propagate trace context?

### Evidence
- [api_server.py:284–326](../pdca/api_server.py#L284): worker build argv `[sys.executable, "-m", "prowler", "aws", ...]`, gọi `subprocess.run(argv, ..., env=env)`.
- `env` chứa `AWS_*` keys + `PYTHONIOENCODING`. KHÔNG có Langfuse env.
- Prowler là **third-party Python tool** — không biết đến Langfuse.
- Bridge hiện có: trong PDCA process, span `scanner:start_scan_by_group` có attribute `job_id`. Ở api_server process, `job_id` được lưu DB. Có thể cross-ref qua DB hoặc Langfuse search.

### Phân tích
- **Không có giá trị thực** khi push `LANGFUSE_TRACE_ID` env vào subprocess Prowler:
  - Prowler không emit Langfuse events.
  - PDCA process đã capture span "scanner:start_scan_by_group" với job_id, latency, finding count — đủ observability cho phía PDCA.
- **Thật sự nên trace** là `api_server` (FastAPI process riêng) — NẾU coi nó là một service trong system. Nhưng:
  - api_server hiện không gọi LLM, không có business logic phức tạp.
  - Đã có structured log + SQLite job DB → đủ.
  - Trace overhead ở api_server không justify.

### Khuyến nghị
- **KHÔNG instrument** subprocess Prowler hoặc api_server với Langfuse ở Phase L1–L4.
- **Bridge identifier**: ở span `scanner:*` (PDCA side), set attribute `job_id` + `scanner_db_path = "data/jobs/scanner_jobs.db"`. Khi cần debug deep → lookup DB bằng job_id.
- **Phase L5+ (nếu cần)**: api_server có thể có Langfuse riêng với trace_id = job_id; PDCA span scanner sẽ có `linked_trace_id=job_id`. Nhưng feature này chỉ giá trị khi:
  - Prowler chạy nhiều phút và cần trace từng giai đoạn.
  - Có nhiều worker scan parallel cần debug.
  - Hiện chưa cần.

---

## Q7. Cost ngân sách — số trace/ngày dự kiến

### Evidence — đếm LLM call/run (worst case)

| Node | LLM calls (per run) | Ghi chú |
|---|---|---|
| environment | 0 | Pure boto3 |
| planning | 0–4 | Confidence gate skip LLM ~80% (comment line 226). Khi gate FAIL: 1 refinement call. Multi-intent split: +1 splitter + 1 refine. Validate IDs cũng dùng RAG, không LLM. |
| scan_submit/poll/collect | 0 | HTTP only |
| risk_evaluation | `2 × ceil(N/20)` | Pass1 + Pass2 batched theo `_RAG_BATCH_CHUNK_SIZE=20` ([risk_evaluation_agent.py:54](../pdca/agents/risk_evaluation_agent.py#L54)). N=100 findings → ~10 calls. |
| operational_planning | `K` (= số FAIL findings) | 1 call/finding chọn tool |
| review_task | 0 | HITL pause |
| execution | 0 | boto3 |
| verification | 0 | RescanAgent + AnalysisAgent (không LLM) |
| report | ~15–20 | LLMWriter mỗi section. Comment ở [llm_writer.py:69](../pdca/agents/report_module/llm_writer.py#L69) chỉ rằng có ~15 sections. |

**Tổng/run điển hình** (N=50 findings, K=10 FAIL):
- 0 (env) + 1 (planning, có refine) + 6 (risk = 2×3) + 10 (ops) + 0 + 15 (report) = **~32 LLM call**.

**Tổng/run worst-case** (N=200, K=50):
- 0 + 4 + 20 + 50 + 0 + 20 = **~94 LLM call**.

### Span estimation per run

| Loại | Số lượng |
|---|---|
| LLM generation | 32–94 |
| Node span | 12 |
| Agent span | ~7 |
| RAG HTTP span | ~5–15 (env health, planning validate + retrieve, risk batched, report) |
| Scanner HTTP span | 1 submit + (poll_count) iterations + N rescan = ~10–60 |
| boto3 tool span | K (= 10–50) |
| HITL wait | 1 |

**Tổng observation/run**: ~70 (typical) – ~250 (heavy).

### Estimation per day

Trong source code:
- CLI E2E ad-hoc: ~5–20 run/ngày khi đang dev.
- Benchmarks ([benchmarks/llm_generation/](../benchmarks/llm_generation/)): `benchmark_planning_cases.json`, `benchmark_report_cases.json` — số case hàng chục đến hàng trăm. **Một bench run = N cases × ~30 calls = vài trăm đến vài nghìn call** → hàng nghìn observation.
- Tests: pytest mock LLM cho phần lớn → không gửi Langfuse (nếu LANGFUSE_HOST chỉ ở dev env file).

### Phân tích
- **Free tier Langfuse cloud**: 50K observations/tháng = ~1,600/ngày = ~6 run typical/ngày HOẶC 1 bench run nhỏ/ngày.
- **Hobby tier ($29/mo)**: 100K observations.
- **Pro tier**: 500K+/mo.
- Đối với đồ án LVTN/ĐATN: **free tier đủ cho phát triển hàng ngày**, NHƯNG bench run sẽ "ăn" quota nhanh.

### Khuyến nghị
- **Phase L0**: thêm 2 setting:
  - `langfuse_enabled: bool = False` — guard dev khỏi accidentally gửi.
  - `langfuse_sample_benchmarks: bool = False` — bench run skip Langfuse trừ khi explicit bật.
- **Convention**: `benchmarks/` luôn set `LANGFUSE_ENABLED=false` mặc định trong runner script. Khi cần debug 1 case bench cụ thể → bật bằng env override.
- **Phase L5 production / shipping**: tự động tier up self-host (unlimited).
- **Cost monitoring**: dashboard Langfuse có "Usage" tab — check tuần đầu để calibrate sample rate nếu cần.

---

## Q8. Migrate benchmarks → Langfuse Datasets?

### Evidence
- [benchmarks/llm_generation/](../benchmarks/llm_generation/) đã có:
  - `benchmark_planning_cases.json`, `benchmark_planning_cases_mini.json`.
  - `benchmark_report_cases.json` (3 phiên bản: full, mini, v3).
  - `benchmark_gen_cases.json`.
  - `release_criteria_*.json` — pass/fail rule cho từng metric.
  - Runner: `benchmark_planning.py`, `benchmark_generation.py`, `benchmark_report.py` + metric files (`planning_metrics.py`, `report_metrics.py`, `gen_metrics.py`).
  - Reports markdown đã viết tay (`Planning_Agent_Evaluation_Report.md`, `Risk_Agent_Evaluation_Report.md`...).
- [benchmarks/rag/](../benchmarks/rag/) — riêng cho RAG retrieval, có `release_criteria.json`.

### Phân tích
- **Schema bench hiện tại đã sạch**: 1 case = `{request, expected, ...}` + judge function chấm điểm → match 1-1 với Langfuse Dataset Item structure (`{input, expected_output}`).
- **Lợi ích migrate**:
  - Run regression sau mỗi thay đổi prompt → so sánh tự động giữa các "Experiment" trong UI.
  - Score trace của production: nếu có session nào giống case bench → so với expected để spot regression realtime.
  - Visual diff prompt giữa runs.
- **Chi phí migrate**:
  - Phải viết adapter `case → Langfuse dataset item`.
  - Phải đẩy criteria check vào Langfuse `score(...)` call thay vì local pass/fail markdown.
  - Đụng vào benchmark code đang stable → risk regression bench logic.
  - Dataset Items count vào quota observation (nếu cloud free tier).

### Khuyến nghị
- **Phase L1–L3: KHÔNG migrate**. Lý do:
  - Bench hiện tại đang phục vụ tốt LVTN reports (đã có markdown output).
  - Quota ưu tiên cho production trace.
- **Phase L4 trở đi (post-cleanup)**: migrate **chọn lọc** — chỉ Planning + Risk (số case nhỏ, value cao cho prompt tuning). Report bench giữ local vì có 15 section × N case = bùng nổ.
- **Pattern migrate khuyến nghị**:
  1. Thêm `benchmarks/llm_generation/_langfuse_adapter.py` đọc `benchmark_*_cases.json` → push lên Langfuse Dataset 1 lần.
  2. Modify runner: chạy mỗi case trong context `langfuse.dataset_item(...)` → trace tự link với item.
  3. Score qua existing metric functions.
  4. Markdown report tiếp tục được generate local (đảm bảo không break LVTN deliverables).
- **KHÔNG migrate `release_criteria_*.json`** sang Langfuse — đó là thresholds business logic, giữ ở repo cho audit trail.

---

## Tổng hợp action items theo phase

| Open Q | Phase action |
|---|---|
| Q1 (token usage) | L1 verify; nếu thiếu → pin `langchain_ollama` version |
| Q2 (cloud vs self-host) | L0 doc policy; L5 self-host khi production |
| Q3 (resume checkpoint) | L1–L4 skip; L5 lưu `parent_span_id` vào PDCAState |
| Q4 (concurrency) | L1 thêm `run_with_run_id` helper + invariant doc; L5 FastAPI middleware |
| Q5 (PlanningAgent) | L1 smoke test propagation; KHÔNG refactor |
| Q6 (subprocess Prowler) | KHÔNG instrument; chỉ link qua `job_id` attribute |
| Q7 (cost) | L0 `langfuse_enabled` flag + `sample_benchmarks` flag; bench runner default off |
| Q8 (datasets) | L1–L3 không migrate; L4+ migrate Planning + Risk có chọn lọc |

---

## Các invariant bổ sung (rút ra từ phân tích)

1. **Mọi agent có LLM PHẢI accept `callbacks: list = None` constructor** — đã đúng, ghi vào docstring `BaseAgent` để tránh regression.
2. **Bench runner default `LANGFUSE_ENABLED=false`** — bảo vệ quota.
3. **Redact `arn:aws:*:*:<account>:` ở span attribute boto3/RAG** khi `langfuse_host` ≠ self-hosted internal — bảo vệ dữ liệu khách hàng.
4. **Trace ID = run_id = thread_id** — không tạo extra UUID. Đã sẵn sàng từ Phase C.
5. **Cross-process resume** chỉ giải quyết khi build chatbot UI; không pre-mature optimize.
