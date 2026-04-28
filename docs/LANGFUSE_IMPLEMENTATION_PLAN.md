# Langfuse Integration — Implementation Plan

> **Mục tiêu**: Triển khai Langfuse vào PDCA AWS Security Agent theo spec [LANGFUSE_INTEGRATION_GUIDE.md](LANGFUSE_INTEGRATION_GUIDE.md), single-pass, production-ready.
> **Output**: 2 PR (Phase F + Phase I), tổng ~1000 LoC code + ~600 LoC test + docs.
> **Estimated effort**: 3–5 ngày/dev (1 dev) hoặc 2 ngày (2 dev parallel sau khi Phase F done).
> **Tham chiếu Decision/Invariant**: D1–D13, I-1 → I-5 trong [LANGFUSE_INTEGRATION_GUIDE.md §0+§2](LANGFUSE_INTEGRATION_GUIDE.md).

---

## 0. Pre-flight checklist

Trước khi bắt đầu coding:

- [ ] **P0.1** — Self-host Langfuse hoặc tạo account cloud dev. Lấy `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY`.
- [ ] **P0.2** — Confirm `langchain-ollama` đang cài có expose `usage_metadata`. Chạy nhanh:
      ```python
      from langchain_ollama import ChatOllama
      r = ChatOllama(model="gemma3:4b").invoke("hi")
      print(r.usage_metadata)  # phải có {input_tokens, output_tokens, total_tokens}
      ```
      Nếu None → cần upgrade.
- [ ] **P0.3** — Confirm git working tree clean (`REFACTOR_PLAN.md` R1 đã giải quyết).
- [ ] **P0.4** — Backup `data/checkpoints/pdca_state.db` nếu có session đang chờ HITL.
- [ ] **P0.5** — Branch: `feat/langfuse-foundation` cho Phase F; `feat/langfuse-instrumentation` cho Phase I.
- [ ] **P0.6** — Confirm Python ≥ 3.12 (đã yêu cầu trong README).

---

## Phase F — Foundation (1 PR)

**Goal**: Mọi infra observability sẵn sàng. Pipeline chạy nguyên với `LANGFUSE_ENABLED=false` (default).
**Estimated**: ~1.5–2 ngày. ~400 LoC code + ~300 LoC test.

### F1. Dependencies & settings

**Files**: `requirements.txt`, `pdca/config/settings.py`, `.env.example` (nếu có).

**Tasks**:
1. Thêm vào `requirements.txt`:
   ```
   langfuse>=3.0,<4.0
   langchain>=1.0,<2.0
   langchain-core>=1.0,<2.0
   langchain-ollama>=1.0,<2.0
   ```
   Pin chặt để tránh drift `usage_metadata` schema. **Pre-Flight verified**:
   môi trường hiện tại có `langchain==1.1.0`, `langchain-core==1.1.0`,
   `langchain-ollama==1.0.0` — pin ≥1.0,<2.0 align với thực tế.
   ChatOllama source đã expose `usage_metadata`, `eval_count`, `input_tokens`
   (verified bằng [scripts/verify_langfuse_preflight.py](../scripts/verify_langfuse_preflight.py)).
2. Thêm 10 setting mới vào `Settings` class theo §5.2 của INTEGRATION_GUIDE:
   - `langfuse_enabled` (bool, default False)
   - `langfuse_secret_key`, `langfuse_public_key` (Optional[str])
   - `langfuse_host` (str, default `https://cloud.langfuse.com`)
   - `langfuse_redact_mode` (Literal "full"|"internal"|"off", default "full")
   - `langfuse_environment` (Literal "dev"|"staging"|"prod", default "dev")
   - `langfuse_flush_at_node` (bool, default True)
   - `langfuse_circuit_breaker_threshold` (int, default 5)
   - `langfuse_circuit_breaker_window_s` (int, default 60)
   - `langfuse_bench_enabled` (bool, default False)
   - `langfuse_sample_rate` (float, default 1.0)
3. Thêm `model_validator`: nếu `langfuse_enabled=True` mà thiếu key → log warning + force `langfuse_enabled=False` (fail-safe).
4. Cập nhật `.env.example` (tạo nếu chưa có) với template Langfuse.

**DoD**:
- `pip install -r requirements.txt` thành công.
- `python -c "from pdca.config import settings; print(settings.langfuse_enabled)"` → `False`.
- Set fake key + `enabled=True` → settings load OK.

---

### F2. Redaction module

**File mới**: `pdca/observability/redaction.py` + `tests/test_redaction.py`.

**Tasks**:
1. Implement `redact(value: Any, mode: str = None) -> Any`:
   - Mode đọc từ `settings.langfuse_redact_mode` nếu None.
   - Recursive: dict, list, str.
   - Hard-fail patterns (mọi mode): AWS access key (`AKIA[0-9A-Z]{16}`), AWS secret (40-char base64-ish heuristic) → replace `<REDACTED-CREDENTIAL>`.
   - Mode `"full"`:
     - Account ID 12-digit → `***<last 4>`.
     - ARN `arn:aws:svc:region:account:resource` → `arn:aws:svc:region:***:resource`.
     - Bucket name (heuristic: lowercase 3-63 với `.` `-`) → `bkt-<sha256[:8]>`.
   - Mode `"internal"`: chỉ hard-fail credentials, giữ ARN/account.
   - Mode `"off"`: identity.
2. Helper `redact_dict_keys(d, sensitive_keys=("aws_access_key_id","secret"))` strip trước khi recurse.
3. Wrapper `safe_redact(value)` — try/except, fallback `"<redaction-error>"`.

**Tests** (`tests/test_redaction.py`, ~15 case):
- AKIA pattern → REDACTED.
- ARN với account → masked theo mode.
- Nested dict (tool_params containing ARN) → recursive redact.
- List of OCSF findings → mỗi finding redacted.
- Mode `off` → identity.
- Exception trong redact (e.g. circular ref) → `<redaction-error>`, không raise.
- 12-digit không phải account_id (e.g. timestamp) — accept false positive (document trong docstring).

**DoD**:
- `pytest tests/test_redaction.py -v` pass.
- Coverage > 90% cho `redaction.py`.

---

### F3. Concurrency context helper

**File mới**: `pdca/observability/context.py` + `tests/test_observability_context.py`.

**Tasks**:
1. Re-export `set_run_id`, `get_run_id` từ `logger.py` (không tách ContextVar — single source).
2. Implement `run_with_context(run_id: str, fn, *args, **kwargs)`:
   ```
   ctx = contextvars.copy_context()
   def _runner():
       set_run_id(run_id)
       return fn(*args, **kwargs)
   return ctx.run(_runner)
   ```
3. Implement `@with_run_id(run_id_arg="run_id")` decorator (option dùng trong FastAPI dep tương lai).

**Tests**:
- 10 thread × `run_with_context(f"run_{i}", lambda: get_run_id())` → mỗi thread thấy `run_i` đúng (I-2).
- asyncio.gather 10 task tương tự.
- Nested `run_with_context` (override + restore).

**DoD**:
- `pytest tests/test_observability_context.py -v` pass.
- `tests/test_phase_c_graph.py` không regression.

---

### F4. Langfuse client + circuit breaker

**File mới**: `pdca/observability/langfuse_client.py` + `tests/test_langfuse_client.py`.

**Tasks**:
1. Module-level singletons (lazy):
   - `_langfuse: Optional[Langfuse] = None`
   - `_handler: Optional[CallbackHandler] = None`
   - `_breaker_state = {"failures": 0, "tripped_at": None}`
2. `get_langfuse_client() -> Optional[Langfuse]`:
   - Return None nếu `not settings.langfuse_enabled`.
   - Lazy init với try/except.
   - Nếu init fail → log warning 1 lần, return None.
3. `get_langfuse_handler() -> Optional[BaseCallbackHandler]`:
   - Wrap `CallbackHandler` từ `langfuse.langchain` (hoặc `langfuse.callback` tuỳ SDK version 3).
   - Return None nếu client None hoặc breaker tripped.
4. Circuit breaker:
   - `record_failure()`: tăng counter; nếu >= threshold trong window_s → set `tripped_at=now`.
   - `is_tripped() -> bool`: check `tripped_at` chưa quá window.
   - Reset auto sau window.
5. `flush_safe()`: try/except quanh `client.flush()`, log debug.
6. `shutdown()`: gọi cuối process (atexit).

**Tests**:
- Disabled → handler = None, không init client.
- Init fail → handler = None, log 1 lần.
- Breaker trip sau N fail → next call return None.
- Breaker reset sau window.

**DoD**:
- `pytest tests/test_langfuse_client.py -v` pass.
- `LANGFUSE_HOST=http://invalid.local LANGFUSE_ENABLED=true python -m pdca.orchestrator` → pipeline chạy được, log có "circuit breaker tripped" sau vài thử.

---

### F5. Tracing primitives

**File mới**: `pdca/observability/tracing.py` + `tests/test_tracing.py`.

**Tasks**:
1. Context manager `span(name: str, *, input: Any = None, metadata: dict = None, kind: str = "span")`:
   - Acquire current trace từ `langfuse.context()` hoặc start new (với `trace_id=get_run_id()`).
   - Lazy: nếu handler None → yield no-op object có method `update(output=...)`, `set_status(...)`, `add_event(...)`.
   - Inject `pdca.schema_version="1.0"` vào metadata.
   - Run `redact(input)`, `redact(metadata)` trước khi gửi.
   - On exception: set status="error", capture exception type + redacted message.
2. `@traced(name: str, capture_args: bool = False, capture_return: bool = False)` decorator:
   - Wrap function với `span(name)`.
   - `capture_args=True` → input = redacted args/kwargs (skip `self`).
   - `capture_return=True` → output = redacted return.
3. `start_trace(run_id: str, **metadata) -> TraceHandle` + `end_trace(handle)`:
   - Mở trace ở entry point.
   - Update metadata sau (planning, verification node sẽ gọi).
4. `update_trace_metadata(**kwargs)` — convenience set attributes vào current trace.
5. `flush_at_node()` — gọi cuối mỗi node nếu `settings.langfuse_flush_at_node`.

**Tests** (mock Langfuse client):
- `with span("x")` → mock span created, redact called.
- Exception trong block → status=error, exception captured, re-raised.
- No-op khi handler None.
- `@traced` decorator đo function.
- Schema version injected.

**DoD**:
- `pytest tests/test_tracing.py -v` pass.

---

### F6. State + callbacks wiring

**Files**: `pdca/graph/state.py`, `pdca/agents/shared/callbacks.py`.

**Tasks**:
1. `pdca/graph/state.py`: thêm field
   ```python
   _langfuse_parent_span_id: NotRequired[Optional[str]]
   _langfuse_trace_id: NotRequired[Optional[str]]
   ```
   Document: dùng cho cross-process resume HITL.
2. `pdca/agents/shared/callbacks.py`:
   - Mở rộng `get_callbacks(extra=None) -> list`:
     ```
     handler = get_langfuse_handler()
     return [TimerCallback()] + ([handler] if handler else []) + list(extra or [])
     ```
   - Document: TimerCallback giữ song song (D12).
3. Kiểm tra mọi node hiện đang propagate `callbacks` vào agent constructor — đã có sẵn (verified).

**Tests**:
- `get_callbacks()` không enabled → chỉ TimerCallback.
- Enabled + handler ok → cả 2.
- `extra=[mock]` → 3 callback theo thứ tự.

**DoD**:
- `pytest tests/test_phase_c_graph.py` pass (không regression).

---

### F7. Bench runner guards

**Files**: `benchmarks/llm_generation/benchmark_*.py` (3 file), `benchmarks/rag/benchmark_*.py`.

**Tasks**:
1. Mỗi runner script (entry point), đầu file:
   ```python
   import os
   os.environ.setdefault("LANGFUSE_ENABLED", "false")
   ```
   (setdefault — cho phép explicit override khi dev cần debug).
2. Document trong từng `README.md` của benchmark folder.

**DoD**:
- Chạy 1 bench → không gửi observation lên Langfuse (manual verify trên UI).

---

### F8. Documentation Phase F

**Files**: `docs/observability/runbook.md` (mới), update `README.md`.

**Tasks**:
1. `docs/observability/runbook.md`:
   - Section: setup self-host (Docker compose link).
   - Section: failure modes & response (copy từ INTEGRATION_GUIDE §9).
   - Section: dashboard URL placeholder.
2. `README.md` — thêm env var Langfuse vào bảng env.

**DoD**:
- `runbook.md` review-ready.

---

### Phase F — Acceptance gate

Trước khi merge Phase F (theo INTEGRATION_GUIDE §7 F1–F5):

- [ ] **F1**. `pytest tests/test_redaction.py tests/test_observability_context.py tests/test_langfuse_client.py tests/test_tracing.py` pass.
- [ ] **F2**. `pytest tests/test_phase_c_graph.py tests/test_phase_d_api.py` pass nguyên.
- [ ] **F3**. `LANGFUSE_HOST=http://invalid.local LANGFUSE_ENABLED=true python scripts/run_e2e_auto.py` → pipeline complete; circuit breaker trip; log warning có dòng "circuit breaker tripped".
- [ ] **F4**. Audit redaction:
      ```python
      from pdca.observability.redaction import redact
      assert "AKIAIOSFODNN7EXAMPLE" not in str(redact("AKIAIOSFODNN7EXAMPLE"))
      assert "123456789012" not in str(redact("arn:aws:s3::123456789012:bucket"))
      ```
- [ ] **F5**. Concurrency test pass (10 thread, 100% correctness).

**Merge criteria**: Tất cả test pass, code review approved, không regression test cũ.

---

## Phase I — Full instrumentation (1 PR)

**Goal**: Tất cả wire points instrumented; trace e2e đầy đủ trên Langfuse UI.
**Estimated**: ~2–3 ngày. ~600 LoC code + ~300 LoC test.
**Prerequisite**: Phase F merged.

### I1. Orchestrator lifecycle

**File**: `pdca/orchestrator.py`.

**Tasks**:
1. Trong `run_interactive_session()`:
   - `set_run_id(thread_id)` ngay sau khi tạo UUID.
   - `with start_trace(run_id=thread_id, user_request=user_request_text, environment=settings.langfuse_environment, ...) as trace:`
   - Stream loop bên trong.
   - `finally: flush_safe(); shutdown()`.
2. Trong `handle_task_review_interaction()`:
   - Đọc `parent_span_id` từ state.
   - Open span `hitl:wait` với `parent_observation_id`.
   - Sau `app.update_state(...)` — close span với `output={"decision": ..., "latency_human_ms": ...}`.
3. Exception handler — set trace status error.

**DoD**:
- 1 run E2E hiện tạo 1 trace có root + nested span ở Langfuse UI.

---

### I2. Node wrapping (12 file)

**Files**: `pdca/graph/nodes/*.py`.

**Pattern** — apply mỗi node:
```python
def <name>_node(state: PDCAState, config: RunnableConfig) -> dict:
    run_id = state.get("run_id", "")
    set_run_id(run_id)
    with span(f"node:{<name>}", metadata={"run_id": run_id}) as sp:
        # ... existing logic ...
        result = {...}
        sp.update(output={"delta_keys": list(result.keys()), "sizes": {...}})
        if settings.langfuse_flush_at_node:
            flush_safe()
        return result
```

**Per-node detail**:

| Node | Đặc thù |
|---|---|
| environment | Trace metadata update: `aws.account_id_redacted`, `aws.region`, `rag_available` |
| planning | Update trace metadata sau: `pdca.plan.checks_count, groups, fast_track` |
| scan_submit | Span attribute: `pending_jobs_count` |
| scan_poll | **GỘP**: 1 span `node:scan_poll_loop` cho toàn bộ loop (trong routing layer hoặc detect first-iteration). Mỗi `check_job_status` là sub-span. Cần helper detect "first iteration" — hoặc đơn giản: tạo span ở route entry, đóng ở route exit |
| scan_collect | Span output: `normalized_count`, `drained_count` |
| risk_evaluation | Update trace: `pdca.risk.severity_dist` |
| operational_planning | Span output: `task_count`, `manual_count` |
| review_task | Mở `hitl:wait` (xem I1) — node body chỉ persist `_langfuse_parent_span_id` vào state |
| reset_index | Light wrap |
| execution | Sub-span per task — xem I4 |
| verification | Update trace: `pdca.outcome.{fixed,failed,manual}` + tag |
| report | Sub-span `maturity:assess`; sections do `LLMWriter` tự generation |

**Special case `scan_poll`**:
- Vì routing → loop, mỗi iter là 1 node invoke độc lập.
- Approach: thêm flag `state["_scan_poll_loop_open"] = True` ở iteration đầu; iter cuối (router → scan_collect) flush + close.
- Hoặc đơn giản hơn: KHÔNG gộp, mỗi iter là 1 span `node:scan_poll[i]` với attribute `iteration_num` — accept tall trace nhưng đơn giản. **Khuyến nghị: chọn approach này cho Phase I**, optimize sau nếu cần.

**Tests**: `tests/test_node_tracing.py` — mock handler, run 1 node, assert span tree.

**DoD**:
- All 12 node có wrap, smoke test pass.

---

### I3. Agent span wrapping

**Files**: `pdca/agents/{planning,risk_evaluation,remediate_planner}_agent.py`, `pdca/agents/report_agent.py`.

**Pattern**:
```python
def run(self, ...):
    with span(f"agent:{self.__class__.__name__}", input={"summary": ...}) as sp:
        # existing logic
        sp.update(output={"summary": ...})
        return result
```

**Special**:
- `RiskEvaluationAgent`: 2 sub-span `risk.pass1` + `risk.pass2_rag` (manual, vì batched). LLM call bên trong tự thành generation qua callback.
- `ReportAgent`: existing `LLMTimerProxy` đã wrap mỗi section → giữ; thêm 1 span `agent:ReportAgent` bao ngoài.
- `EnvironmentAgent`: span `aws:sts` + `aws:s3` quanh boto3 call.
- `AnalysisAgent`: span `agent:AnalysisAgent` (không có LLM, chỉ logic).

**DoD**:
- Trace có tree node → agent → generation đúng.

---

### I4. External call wrapping

**Files**:
- `pdca/agents/shared/rag_client.py`
- `pdca/tools/scanner.py`, `pdca/tools/knowledge.py`
- `pdca/tools/remediation/s3.py`
- `pdca/agents/execution_agent.py`
- `pdca/agents/environment_agent.py`
- `pdca/agents/rescan_agent.py`

**Pattern RAGClient**:
```python
def retrieve_checks(self, query, ...):
    with span(f"rag:retrieve_checks", input={"query": query[:500], "top_k": top_k}) as sp:
        try:
            resp = self._session.post(...)
            resp.raise_for_status()
            data = resp.json()
            sp.update(output={"count": len(data.get("results", [])), "http_status": resp.status_code})
            return data
        except Exception as e:
            sp.set_status("error", str(e))
            return None
```

**Pattern tool (scanner/remediation)**:
- Wrap thân `@tool` function.
- Span name: `scanner:start_scan_by_group`, `tool:s3_block_account_public_access`, ...
- Input: redacted params.
- Output: status, success.

**Pattern ExecutionAgent.execute_task**:
```python
with span(f"tool:{tool_name}", input=redact(tool_params),
          metadata={"task_id": task_id, "finding_uid": finding_uid, "decision": decision}) as sp:
    # 3-guard logic...
    # tool.invoke(...)
    sp.update(output={"status": status, "success": success})
```

**DoD**:
- Click 1 trace → thấy đầy đủ rag/scanner/tool sub-span.

---

### I5. HITL pause + resume support

**Files**: `pdca/graph/nodes/review_task.py`, `pdca/orchestrator.py`.

**Tasks**:
1. `review_task_node`:
   - Đọc current span context từ Langfuse.
   - Persist `parent_span_id` + `trace_id` vào state.
   - Return state delta gồm 2 field này.
2. `handle_task_review_interaction` (orchestrator):
   - Đọc state → mở span `hitl:wait` với parent_observation_id.
   - Capture human latency.
   - Close với decision.
3. Cross-process resume: nếu `_langfuse_trace_id` đã có trong state khi resume → reuse trace_id. (Thực test scenario này manual — chatbot UI tương lai sẽ verify deeper.)

**Test**: integration test mock — pause → state có `_langfuse_parent_span_id` → resume close span.

**DoD**:
- HITL flow trace correctly trên UI; span `hitl:wait` có duration = thời gian thực user response.

---

### I6. Score hooks (quality signals)

**Files**: `pdca/graph/nodes/{planning,risk_eval,verification,report}.py`.

**Tasks**:
1. Sau planning node: `langfuse_client.score(trace_id=run_id, name="planning_top_score", value=top_score, comment="confidence_gate=PASS|FAIL")`.
2. Sau risk_eval: `score("risk_severity_critical", count_critical)`, `score("risk_severity_high", count_high)`.
3. Sau verification: `score("outcome_fixed_ratio", fixed/total)`, `score("outcome_manual_count", manual)`.
4. Sau report: `score("validation_issues", len(_validation_issues))`.
5. Trace tag cuối: `[success | partial_failure | degraded]` dựa `_degraded`, errors, validation issues.

**DoD**:
- Trong UI Langfuse filter trace theo `outcome=partial_failure` hoạt động.

---

### I7. LLMWriter section naming

**File**: `pdca/agents/report_module/llm_writer.py`.

**Tasks**:
1. Khi gọi LLM cho mỗi section (e.g. `executive_summary`, `findings_summary`, ...), set name vào callback context:
   - Cách đơn giản: dùng `RunnableConfig` với `run_name=f"report.section.{section_id}"` khi invoke.
   - Hoặc wrap với `span(f"report.section.{section_id}")` quanh `_ask()` call.
2. Đảm bảo generation trong UI có name có ý nghĩa (không phải `ChatOllama` mặc định).

**DoD**:
- 15 generation trong 1 report node có 15 name khác nhau.

---

### I8. Tests integration

**Files**: `tests/test_langfuse_integration.py` (mới).

**Tasks**:
1. Mock `Langfuse` client (in-memory store của trace/span/generation).
2. Run 1 E2E mock pipeline → assert tree shape match §4 trace flow của INTEGRATION_GUIDE.
3. Test redaction E2E: prompt có ARN → assert generation.input redacted.
4. Test HITL span lifecycle.
5. Test failure injection: handler raise → pipeline still complete.

**Coverage target**: > 80% cho `pdca/observability/`.

**DoD**:
- `pytest tests/test_langfuse_integration.py -v` pass.

---

### I9. Documentation Phase I

**Files**: `docs/observability/runbook.md` (extend), `docs/observability/dashboard.md` (mới).

**Tasks**:
1. `runbook.md`:
   - Update với observed failure modes thực tế gặp khi dev.
2. `dashboard.md`:
   - 5 view requirement (run timeline, per-node latency, token usage, error explorer, HITL latency).
   - Filter recipes (ví dụ: `outcome=partial_failure`, `account_id=<redacted>`, `model=gemma3:4b`).
   - Screenshot placeholder.
3. Update `README.md` với link tới observability docs.

**DoD**:
- Document review-ready cho LVTN report.

---

### Phase I — Acceptance gate

Theo INTEGRATION_GUIDE §7 I1–I7 + §10 production checklist:

- [ ] **I1**. Run 1 E2E thật với self-host (hoặc cloud dev) → UI có trace đầy đủ tree.
- [ ] **I2**. Click 1 generation → thấy prompt + completion + token + ARN đã redacted.
- [ ] **I3**. Filter `outcome=partial_failure` hoạt động.
- [ ] **I4**. `LANGFUSE_HOST=http://invalid.local` → pipeline complete; log "circuit breaker tripped".
- [ ] **I5**. HITL test (manual): pause → check UI có `hitl:wait status=waiting` → decide → span đóng.
- [ ] **I6**. Bench run với default → UI không có trace mới.
- [ ] **I7**. Audit security: grep prompt/completion trong UI:
      ```bash
      # Pseudo: export 1 trace JSON, grep
      langfuse export <trace_id> | grep -E "AKIA[0-9A-Z]{16}|[0-9]{12}"
      # Phải = 0 hit
      ```
- [ ] **Performance**: 1 E2E latency với/không Langfuse → diff < 5%.
- [ ] **Memory**: span buffer < 50MB/run.
- [ ] **Code review**: 2 reviewer.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Langfuse SDK v3 API thay đổi | Medium | High (block Phase F) | Pin version chặt; document version dùng trong runbook |
| `langchain_ollama` không expose `usage_metadata` đúng | Medium | Medium | P0.2 verify trước; nếu thiếu → patch tay qua `on_llm_end` đọc `response.llm_output` |
| Span tall ở scan_poll | Low | Low | Accept ở Phase I; optimize sau nếu UX kém |
| Performance regression > 5% | Low | Medium | Bench trước/sau; nếu fail → giảm `flush_at_node` xuống node quan trọng |
| Redaction false negative (lộ data) | Medium | **Critical** | Test rộng; whitelist regime cho mode `full`; audit thủ công 1 trace trước khi prod |
| Cross-process resume không work khi build chatbot UI | Medium | Medium | Document scenario là "manual verify"; fix trong Phase chatbot UI nếu thật sự dùng |
| Langfuse host self-host setup phức tạp | Medium | Low | Chấp nhận dùng cloud cho dev; doc setup self-host cho prod |
| Token usage = 0 trong UI | Low | Low | Verify P0.2; pin version |
| Test mock Langfuse client phức tạp | Medium | Low | Dùng `unittest.mock` + factory pattern; minimal API surface |

---

## Timeline (1 dev, full-time)

| Day | Tasks |
|---|---|
| Day 1 (sáng) | P0 + F1 (deps + settings) + F2 (redaction) start |
| Day 1 (chiều) | F2 finish + F3 (context) |
| Day 2 (sáng) | F4 (langfuse_client) + F5 (tracing) |
| Day 2 (chiều) | F6 (state + callbacks) + F7 (bench guards) + F8 (docs) + Phase F gate |
| Day 3 (sáng) | I1 (orchestrator) + I2 (12 node wrap) start |
| Day 3 (chiều) | I2 finish + I3 (agents) |
| Day 4 (sáng) | I4 (external calls) — RAG + scanner + tools |
| Day 4 (chiều) | I4 finish (execution + env) + I5 (HITL) |
| Day 5 (sáng) | I6 (scores) + I7 (LLMWriter naming) + I8 (tests) |
| Day 5 (chiều) | I9 (docs) + Phase I gate + manual E2E verify |

**Buffer**: +1 ngày cho debugging SDK quirks và UI verification.

---

## Parallelization (2 dev)

Sau Phase F merged:
- Dev A: I1 + I2 + I5 (orchestrator + nodes + HITL).
- Dev B: I3 + I4 + I7 (agents + external + LLMWriter naming).
- Both: I6 + I8 + I9 (scores + tests + docs).

Tiết kiệm 1.5 ngày.

---

## Definition of Done — toàn project

Tham chiếu LVTN gate trong [INTEGRATION_GUIDE §10](LANGFUSE_INTEGRATION_GUIDE.md):

- [ ] All 13 decision (D1–D13) reflected trong code (grep keyword check).
- [ ] All 5 invariant (I-1 → I-5) có test.
- [ ] Acceptance F1–F5, I1–I7 pass.
- [ ] Self-host Langfuse setup document hoặc compose file ở `deploy/langfuse/`.
- [ ] Redaction audit: 1 trace demo, grep không lộ secret.
- [ ] Performance overhead < 5%.
- [ ] Failure injection test pass.
- [ ] Runbook + dashboard doc reviewed.
- [ ] 2 PR merged vào `main`.
- [ ] Demo trace recorded cho LVTN slides.

---

## Out of scope (defer)

Items KHÔNG làm trong 2 phase này, document để future work:

1. **Langfuse Datasets migration** (Q8) — sau khi production stable.
2. **api_server.py instrumentation** (Q6) — không cần, scanner job_id link đủ.
3. **Async pipeline migration** — orthogonal, theo REFACTOR_PLAN Phase E.
4. **Alerting/Slack integration** — Langfuse có webhook, làm sau.
5. **Multi-tenancy filter ở dashboard** — chỉ relevant khi build chatbot UI multi-user.
6. **Langfuse Prompt Management** — prompt hiện đang ở code, migrate sau.
7. **Cost dashboard với external Ollama pricing model** — Ollama local zero $, chưa cần.

---

## Appendix — File change summary

### Phase F (estimated)
- New: 4 file (`context.py, redaction.py, langfuse_client.py, tracing.py`).
- New tests: 4 file.
- Modified: 3 file (`settings.py, callbacks.py, state.py`, `requirements.txt`).
- Modified bench: 4 file (env guard).
- Docs: 1–2 file.
- **Total: ~12 file change, ~700 LoC.**

### Phase I (estimated)
- Modified: ~25 file (12 node + 5 agent + 4 tool + orchestrator + report module + ...).
- New tests: 1–2 file.
- Docs: 2 file.
- **Total: ~30 file change, ~900 LoC.**

### Grand total: ~42 file change, ~1600 LoC (code + test + doc).


---

## Phase F — Result log (2026-04-28)

> Branch: `feat/langfuse-foundation`. Phase F implementation closed; ready for review/merge.

### Files delivered

| Slice | File | Status |
|---|---|---|
| F1 | `requirements.txt` (pin langfuse>=3,<4 + langchain>=1,<2 trio) | ✅ |
| F1 | `pdca/config/settings.py` (10 Langfuse settings + `_enforce_langfuse_fail_safe` validator) | ✅ |
| F1 | `.env.example` (Phase F template) | ✅ |
| F2 | `pdca/observability/redaction.py` + `tests/test_redaction.py` (9 case) | ✅ |
| F3 | `pdca/observability/context.py` + `tests/test_observability_context.py` (4 case) | ✅ |
| F4 | `pdca/observability/langfuse_client.py` + `tests/test_langfuse_client.py` (6 case) | ✅ |
| F5 | `pdca/observability/tracing.py` + `tests/test_tracing.py` (5 case) | ✅ |
| F6 | `pdca/graph/state.py` (`_langfuse_parent_span_id`, `_langfuse_trace_id`) + `pdca/agents/shared/callbacks.py` (handler injection) | ✅ |
| F7 | 16 bench entry points patched với `os.environ.setdefault("LANGFUSE_ENABLED", "false")` | ✅ |
| F8 | `docs/observability/runbook.md` + README env table extended | ✅ |

### Acceptance gate F1–F5

| Gate | Command | Kết quả |
|---|---|---|
| F1 | `pytest tests/test_redaction.py tests/test_observability_context.py tests/test_langfuse_client.py tests/test_tracing.py -v` | **24 / 24 PASS** |
| F2 | `pytest tests/test_phase_c_graph.py tests/test_phase_d_api.py` | **56 / 56 PASS** (no regression) |
| F3 | `LANGFUSE_HOST=http://invalid.local LANGFUSE_ENABLED=true ... ` smoke | **Pipeline không crash**. Với SDK v3 thật, OTEL export failure bị SDK log nội bộ (`Failed to export span batch...`) và không raise nên breaker không trip ở path này; breaker vẫn được unit-test cho wrapper/client exceptions. |
| F4 | `redact("AKIA…")` + `redact("arn:aws:s3::123456789012:bucket")` | **AKIA → REDACTED, account → `***9012`** |
| F5 | 10-thread + 10-asyncio task isolation test | **PASS** (test_observability_context) |

### Issues encountered & resolved

1. **Test `test_nested_dict_and_lists_are_redacted_recursively` failed** — ARN regex chỉ thay account, để lại bucket name trong resource segment.
   - Fix: `_arn_sub` split resource trên `/` và hash mỗi segment thoả `_looks_like_bucket` (S3 service).
2. **Test `test_span_creates_observation_with_redacted_input_and_schema` failed** ở 2 điểm:
   - `trace_id` không được set vì `@contextmanager` chạy lazy → `get_run_id()` đọc rỗng sau khi `run_with_context` thoát. Fix: tách `span()` thành wrapper capture `run_id` eager + `_span_impl` chứa thân ctx manager.
   - String `"1.0"` (schema version) bị treat là bucket-like vì có `.` Fix: thêm `_MIN_BUCKET_LEN = 6` để loại false positive như "1.0", "v0.1", IP octet.
3. **Langfuse SDK v3 API khác giả định ban đầu** — `CallbackHandler` không nhận `secret_key`/`host`; `start_as_current_span` dùng `trace_context`, và trace id phải là 32 lowercase hex.
   - Fix: `get_langfuse_handler()` inspect signature và truyền đúng kwargs; `Langfuse(mask=_mask_for_langfuse)` bật redaction SDK boundary; `start_trace()` mở root span với `trace_context`; UUID `run_id` được map sang `uuid.hex` khi gửi Langfuse, đồng thời giữ `pdca.run_id` gốc trong metadata.
4. **Langfuse SDK đã cài vào venv** — `pip install -r requirements.txt` pass; `pip check` pass. Có phát sinh mismatch OpenTelemetry do package cũ trong venv, đã đồng bộ lên `opentelemetry-exporter-otlp-proto-grpc==1.41.1`.

### Risks giải quyết theo bảng risk register

| Risk | Mitigation đã apply |
|---|---|
| Langfuse SDK v3 API thay đổi | Pin `langfuse>=3.0,<4.0`. Dual import path (`langfuse.langchain` fallback `langfuse.callback`) ở `get_langfuse_handler`. |
| `langchain_ollama` không expose `usage_metadata` | Đã verify ở Pre-Flight (P0.2). Pin `>=1.0,<2.0`. |
| Performance regression > 5% | Đã có `flush_at_node` setting toggle; `get_langfuse_client()` early-return khi disabled. Bench đo formal vào Phase I.6. |
| Redaction false negative | Test 9 case + audit smoke. Mode `full` mặc định cho cloud (`.env.example`). |
| Cross-process resume | `PDCAState._langfuse_parent_span_id` + `_langfuse_trace_id` là first-class field — sẵn cho Phase I.5. |
| Test mock Langfuse phức tạp | `tests/test_tracing.py` dùng minimal `FakeClient` ~30 LoC; `tests/test_langfuse_client.py` dùng monkeypatch + `_reset_for_tests()` helper. |

### Next steps

1. Tạo PR `feat/langfuse-foundation` từ `main` → squash merge.
2. Sau merge, branch `feat/langfuse-instrumentation` cho Phase I (theo §Phase I).
3. Phase I.1 (orchestrator lifecycle) là entry — xem [docs/LANGFUSE_INTEGRATION_GUIDE.md §4](LANGFUSE_INTEGRATION_GUIDE.md) cho trace topology.
