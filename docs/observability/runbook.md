# Langfuse Observability — Runbook

> Audience: on-call dev, LVTN reviewer. Operational reference cho Langfuse layer của PDCA AWS Security Agent.
> Tham chiếu spec: [LANGFUSE_INTEGRATION_GUIDE.md](../LANGFUSE_INTEGRATION_GUIDE.md), [LANGFUSE_IMPLEMENTATION_PLAN.md](../LANGFUSE_IMPLEMENTATION_PLAN.md).

---

## 1. Setup nhanh

| Use case | Hướng dẫn |
|---|---|
| Cloud dev / LVTN demo | [docs/observability/langfuse_setup.md §Option A](langfuse_setup.md) |
| Self-host production | [docs/observability/langfuse_setup.md §Option B](langfuse_setup.md) |
| Bench / CI | KHÔNG bật — runner đã set `LANGFUSE_ENABLED=false` (F.7 guard) |

Sau khi điền `.env`, verify:
```bash
python scripts/verify_langfuse_preflight.py
```

---

## 2. Env vars (Phase F)

| Var | Default | Ghi chú |
|---|---|---|
| `LANGFUSE_ENABLED` | `false` | Master switch. Pipeline chạy nguyên khi off. |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | — | Bắt buộc khi `enabled=true`. Thiếu key → settings tự fail-safe về `false`. |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Self-host: trỏ về internal URL. |
| `LANGFUSE_REDACT_MODE` | `full` | `full` mask account/ARN/bucket; `internal` chỉ mask credentials; `off` test only. |
| `LANGFUSE_ENVIRONMENT` | `dev` | Filter UI: `dev`/`staging`/`prod`. |
| `LANGFUSE_FLUSH_AT_NODE` | `true` | Flush sau mỗi node — đảm bảo HITL pause không mất trace. |
| `LANGFUSE_CIRCUIT_BREAKER_THRESHOLD` | `5` | Số fail liên tiếp trong window → trip. |
| `LANGFUSE_CIRCUIT_BREAKER_WINDOW_S` | `60` | Window tính fail rate. |
| `LANGFUSE_BENCH_ENABLED` | `false` | Bench runner OFF mặc định để bảo vệ quota. |
| `LANGFUSE_SAMPLE_RATE` | `1.0` | Production self-host nên giữ `1.0`. |

---

## 3. Module map (Phase F)

| File | Trách nhiệm |
|---|---|
| [pdca/observability/redaction.py](../../pdca/observability/redaction.py) | Mask AWS credentials/ARN/account/bucket trước khi gửi sang Langfuse. |
| [pdca/observability/context.py](../../pdca/observability/context.py) | `run_with_context()` — propagate `run_id` qua thread/asyncio (I-2). |
| [pdca/observability/langfuse_client.py](../../pdca/observability/langfuse_client.py) | Lazy singleton + circuit breaker + `flush_safe`. |
| [pdca/observability/tracing.py](../../pdca/observability/tracing.py) | `span()` ctx manager, `@traced` decorator, `start_trace`/`end_trace`. |
| [pdca/agents/shared/callbacks.py](../../pdca/agents/shared/callbacks.py) | `get_callbacks()` inject Langfuse handler bên cạnh TimerCallback (D12). |
| [pdca/graph/state.py](../../pdca/graph/state.py) | `_langfuse_parent_span_id` + `_langfuse_trace_id` cho HITL resume (D7). |

---

## 4. Failure modes & response

| Triệu chứng | Khả năng | Hành động |
|---|---|---|
| Pipeline chạy bình thường, UI không có trace | `LANGFUSE_ENABLED=false` hoặc thiếu key (auto fail-safe) | Check `python -c "from pdca.config import settings; print(settings.langfuse_enabled)"` |
| Log có `Langfuse circuit breaker tripped` | Wrapper/client init/flush raise liên tiếp | Pipeline tiếp tục chạy; reset breaker tự động sau `CIRCUIT_BREAKER_WINDOW_S` |
| SDK log `Failed to export span batch...` nhưng breaker chưa trip | Langfuse SDK v3 tự nuốt lỗi OTEL export | Pipeline vẫn tiếp tục; verify host/key. Đây là residual của SDK export path, không phải crash pipeline. |
| Log `Langfuse init failed; observability disabled for this call` | Sai key / host unreachable | Verify lại `.env`; xem stack trace ở debug log |
| Trace có root nhưng thiếu generation | LangChain version mismatch | Pin `langchain>=1.0,<2.0`, `langchain-ollama>=1.0,<2.0` (đã pin ở `requirements.txt`) |
| Token usage = 0 trên UI | ChatOllama version thiếu `usage_metadata` | Chạy `python scripts/verify_langfuse_preflight.py` để verify P0.2 |
| Account_id rò rỉ trong UI | `LANGFUSE_REDACT_MODE` sai | Force `full` cho cloud; audit bằng `redact()` REPL |
| `safe_redact` trả `<redaction-error>` | Circular ref / bug | Log structured có `run_id` — mở issue, tạm thời observation đó mất nội dung |

---

## 5. Manual smoke test (sau Phase F merged)

```bash
# 1. Settings load OK với enabled=false
python -c "from pdca.config import settings; assert settings.langfuse_enabled is False"

# 2. Settings fail-safe khi enabled=true mà thiếu key
LANGFUSE_ENABLED=true python -c "from pdca.config import Settings; s=Settings(); assert s.langfuse_enabled is False"

# 3. Client lazy: disabled → None, không init thật
python -c "
from pdca.observability.langfuse_client import get_langfuse_client, get_langfuse_handler
assert get_langfuse_client() is None
assert get_langfuse_handler() is None
"

# 4. Redaction smoke
python -c "
from pdca.observability.redaction import redact
assert 'AKIAIOSFODNN7EXAMPLE' not in str(redact('AKIAIOSFODNN7EXAMPLE', mode='off'))
assert '123456789012' not in str(redact('arn:aws:s3::123456789012:bucket/x', mode='full'))
"

# 5. Host invalid (acceptance F3 smoke) — pipeline phải chạy được.
# Langfuse SDK v3 có thể chỉ log export failure thay vì raise, nên breaker
# không bắt buộc trip trong smoke này.
LANGFUSE_ENABLED=true LANGFUSE_PUBLIC_KEY=pk LANGFUSE_SECRET_KEY=sk \
LANGFUSE_HOST=http://invalid.local python -c "
from pdca.observability.langfuse_client import get_langfuse_client
for _ in range(10): get_langfuse_client()
from pdca.observability.langfuse_client import is_tripped
print('pipeline-safe, breaker tripped:', is_tripped())
"
```

---

## 6. Test commands

```bash
# Phase F unit tests
pytest tests/test_redaction.py tests/test_observability_context.py \
       tests/test_langfuse_client.py tests/test_tracing.py -v

# Regression Phase C/D
pytest tests/test_phase_c_graph.py tests/test_phase_d_api.py -v
```

Acceptance gate F1–F5 chi tiết: [LANGFUSE_IMPLEMENTATION_PLAN.md §Phase F — Acceptance gate](../LANGFUSE_IMPLEMENTATION_PLAN.md).

---

## 7. Branch + PR convention

| Phase | Branch | Status |
|---|---|---|
| F (Foundation) | `feat/langfuse-foundation` | Active — PR Phase F |
| I (Instrumentation) | `feat/langfuse-instrumentation` | Pending — sau Phase F merged |

KHÔNG branch chéo từ feat → feat. Luôn rebase lên `main` mới nhất.

---

## 8. Dashboard placeholder

Sẽ điền sau Phase I — xem `docs/observability/dashboard.md` (TBD).

5 view planned theo [INTEGRATION_GUIDE §6](../LANGFUSE_INTEGRATION_GUIDE.md):
1. Run timeline (trace tree).
2. Per-node latency.
3. Token usage (model breakdown).
4. Error explorer.
5. HITL latency distribution.
