# KẾ HOẠCH IMPLEMENT CHI TIẾT THEO SLICES
# Tích hợp RAG System ↔ Agent System

**Ngày tạo:** 2026-03-27
**Phiên bản:** v1.1
**Tài liệu tham chiếu:** [Integration_Analysis_Report.md](Integration_Analysis_Report.md) — Mục 7 & 8, [Agent_Refactor_Plan.md](Agent_Refactor_Plan.md)
**Trạng thái:** Draft — Chưa bắt đầu implement

---

## MỤC LỤC

1. [Tổng quan Kế hoạch](#1-tổng-quan-kế-hoạch)
2. [Quy ước & Định nghĩa](#2-quy-ước--định-nghĩa)
3. [Slice 0.1 — Tạo Centralized Configuration](#slice-01--tạo-centralized-configuration)
4. [Slice 0.2 — Tạo RAGClient Class](#slice-02--tạo-ragclient-class)
5. [Slice 0.3 — Thêm RAG Health Check vào Pipeline](#slice-03--thêm-rag-health-check-vào-pipeline)
6. [Slice 0.4 — Dọn dẹp Endpoint cũ (RAG Side)](#slice-04--dọn-dẹp-endpoint-cũ-rag-side)
7. [Slice RS-1 — Shared Utilities & Infrastructure (Agent Refactor)](#slice-rs-1--shared-utilities--infrastructure-agent-refactor)
8. [Slice RS-2 — Refactor PlanningAgent Code Quality](#slice-rs-2--refactor-planningagent-code-quality)
9. [Slice RS-3 — Refactor RiskEvaluationAgent Code Quality](#slice-rs-3--refactor-riskevaluationagent-code-quality)
10. [Slice RS-4 — Orchestrator Wiring & Cleanup](#slice-rs-4--orchestrator-wiring--cleanup)
11. [Slice 1.1 — PlanningAgent: Chuyển sang RAGClient](#slice-11--planningagent-chuyển-sang-ragclient)
12. [Slice 1.2 — PlanningAgent: Chuyển sang PlanningBundle](#slice-12--planningagent-chuyển-sang-planningbundle)
13. [Slice 2.1 — RiskEvaluationAgent: Chuyển sang RAGClient](#slice-21--riskevaluationagent-chuyển-sang-ragclient)
14. [Slice 2.2 — RiskEvaluationAgent: Batch & Confidence](#slice-22--riskevaluationagent-batch--confidence)
15. [Slice 3.1 — Tích hợp RAG vào RemediationPlannerAgent](#slice-31--tích-hợp-rag-vào-remediationplanneragent)
16. [Slice 4.1 — Tích hợp RAG vào ReportAgent](#slice-41--tích-hợp-rag-vào-reportagent)
17. [Slice 5.1 — Unit Tests cho RAGClient](#slice-51--unit-tests-cho-ragclient)
18. [Slice 5.2 — Integration Tests per Agent](#slice-52--integration-tests-per-agent)
19. [Slice 5.3 — End-to-End & Degraded Mode Tests](#slice-53--end-to-end--degraded-mode-tests)
20. [Dependency Map & Execution Order](#dependency-map--execution-order)
21. [Tổng hợp Rủi ro & Mitigation](#tổng-hợp-rủi-ro--mitigation)

---

## 1. TỔNG QUAN KẾ HOẠCH

### 1.1 Mục tiêu tổng thể

Tích hợp RAG System (port 8001) vào Agent System (LangGraph pipeline) để:
- **4 agents** sử dụng RAG context thông qua 1 **shared RAGClient**
- Pipeline hoạt động **graceful** khi RAG không khả dụng (degraded mode)
- Tất cả API endpoints **thống nhất** dưới schema `/v1/*`

### 1.2 Hiện trạng (As-Is)

| Component | Trạng thái hiện tại | Vấn đề |
|---|---|---|
| `agents/shared/rag_client.py` | **Chưa tồn tại** | Mỗi agent tự gọi `requests.post()` |
| `config.py` (Agent System root) | **Chưa tồn tại** | URLs hardcoded trong từng file |
| `.env` | Tồn tại, có `OLLAMA_URL` | **Thiếu** `RAG_API_URL`, `SCANNER_API_URL` |
| `graph_orchestator.py:37` | `RETRIEVAL_API_URL = "http://localhost:8111/retrieve"` | Endpoint **cũ**, không còn hoạt động |
| `planning_agent.py:101` | `http://localhost:8001/v1/retrieve/checks` | Đúng endpoint nhưng **raw requests**, không dùng `context/build` |
| `risk_evaluation_agent.py:92` | `http://localhost:8001/v1/context/build` | Đúng endpoint nhưng **raw requests** |
| `remediate_planner_agent.py` | Không gọi RAG | Chỉ dùng LLM thuần |
| `report_agent.py` | Không gọi RAG | Dùng data enriched từ upstream |

### 1.3 Kết quả mong đợi (To-Be)

```
                ┌────────────────────┐
                │     .env / config  │  ← Single source of truth
                └────────┬───────────┘
                         │
                ┌────────▼───────────┐
                │     RAGClient      │  ← Shared client (retry, timeout, fallback)
                │ agents/shared/     │
                └──┬──┬──┬──┬───────┘
                   │  │  │  │
          ┌────────┘  │  │  └────────┐
          ▼           ▼  ▼           ▼
   PlanningAgent  RiskAgent  RemediationPlanner  ReportAgent
   (context/build) (context/build) (context/build) (context/build)
   consumer=planning consumer=risk  consumer=planning consumer=report
```

### 1.4 Phân chia Phase → Slices

| Phase | Slices | Mô tả | Dependency |
|---|---|---|---|
| **Phase 0** | 0.1, 0.2, 0.3, 0.4 | Foundation: config, client, health, cleanup | Không |
| **Phase RS** | RS-1, RS-2, RS-3, RS-4 | **Agent Refactor:** shared utils, code quality, fix data flow | RS-1 không dependency; RS-2, RS-3 depend RS-1; RS-4 depend RS-2+RS-3 |
| **Phase 1** | 1.1, 1.2 | PlanningAgent RAG integration | Phase 0 + RS-2 |
| **Phase 2** | 2.1, 2.2 | RiskEvaluationAgent RAG optimization | Phase 0 + RS-3 |
| **Phase 3** | 3.1 | Tích hợp mới RemediationPlannerAgent | Phase 0 |
| **Phase 4** | 4.1 | Tích hợp mới ReportAgent | Phase 0 |
| **Phase 5** | 5.1, 5.2, 5.3 | Testing toàn diện | Phase 1-4 |

> **Note v1.1:** Phase RS được thêm sau khi phân tích code quality của PlanningAgent và RiskEvaluationAgent (xem [Agent_Refactor_Plan.md](Agent_Refactor_Plan.md)). Phase RS nên chạy **song song với Phase 0** và hoàn thành **trước** Phase 1-2 để đảm bảo code base sạch trước khi tích hợp RAGClient.

---

## 2. QUY ƯỚC & ĐỊNH NGHĨA

### 2.1 Ticket ID Format

Mỗi slice được đánh ID theo format: `SLICE-{phase}.{number}` (ví dụ: `SLICE-0.1`)

### 2.2 Trạng thái

| Trạng thái | Ý nghĩa |
|---|---|
| `NOT_STARTED` | Chưa bắt đầu |
| `IN_PROGRESS` | Đang implement |
| `REVIEW` | Đã xong, cần review |
| `DONE` | Hoàn thành và verified |
| `BLOCKED` | Bị chặn bởi dependency |

### 2.3 Severity trong tiêu chí hoàn thành

- **MUST** — Bắt buộc để slice được coi là `DONE`
- **SHOULD** — Nên có, nhưng có thể defer sang slice khác
- **NICE** — Optional, cải thiện chất lượng

---

## SLICE 0.1 — Tạo Centralized Configuration

**Ticket:** `SLICE-0.1`
**Phase:** 0 — Foundation
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P0 (Bắt buộc)
**Tham chiếu:** [A-P0-1] trong Integration_Analysis_Report.md § 7.2

### Mục tiêu

Tạo **single source of truth** cho tất cả service URLs và configuration, loại bỏ hardcoded URLs rải rác trong codebase.

### Bối cảnh hiện tại

Hiện tại, 3 vị trí khác nhau định nghĩa URLs:
- `graph_orchestator.py:35-37` — `OLLAMA_BASE_URL`, `RETRIEVAL_API_URL`
- `planning_agent.py:42` — `self.retrieval_api_url = "http://localhost:8111/retrieve"`
- `risk_evaluation_agent.py:92` — `url = "http://localhost:8001/v1/context/build"` (inline)

`.env` hiện tại chỉ có `OLLAMA_URL` và AWS credentials, **thiếu** RAG và Scanner URLs.

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Cập nhật `.env` | Thêm `RAG_API_URL=http://localhost:8001`, `SCANNER_API_URL=http://localhost:8000` | `.env` updated |
| 2 | Tạo `config.py` | Module Python đọc `.env` bằng `os.environ.get()` với defaults, expose các constants: `RAG_API_URL`, `SCANNER_API_URL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_API_KEY` | `config.py` (project root) |
| 3 | Cập nhật `graph_orchestator.py` | Import từ `config.py` thay vì hardcode. Xóa dòng 35-37 (hardcoded URLs). Replace bằng `from config import ...` | `graph_orchestator.py` modified |
| 4 | Cập nhật `planning_agent.py` | Constructor nhận `rag_base_url` thay vì hardcode. Xóa `self.retrieval_api_url = "http://localhost:8111/retrieve"` (dòng 42) | `planning_agent.py` modified |
| 5 | Cập nhật `risk_evaluation_agent.py` | Constructor nhận `rag_base_url` thay vì hardcode URL inline (dòng 92) | `risk_evaluation_agent.py` modified |
| 6 | Verify | Grep toàn bộ codebase: không còn hardcoded `localhost:8001`, `localhost:8111`, `localhost:8000`, `localhost:11434` ngoài `.env` và `config.py` | Grep result clean |

### Luồng dữ liệu sau khi hoàn thành

```
.env (file)
  │ load_dotenv()
  ▼
config.py (module)
  │ export: RAG_API_URL, SCANNER_API_URL, OLLAMA_BASE_URL, ...
  ▼
graph_orchestator.py
  │ import config → truyền vào constructor của agents
  ▼
Agent.__init__(rag_base_url=config.RAG_API_URL, ...)
```

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `.env`, `graph_orchestator.py`, `planning_agent.py`, `risk_evaluation_agent.py` | Files cần sửa |
| Library | `python-dotenv` | Đã có trong project (imported tại `graph_orchestator.py:8`) |
| Tài liệu | [Integration_Analysis_Report.md § 7.2 A-P0-1](Integration_Analysis_Report.md) | Phân tích gốc |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | `config.py` tồn tại, export tối thiểu 4 constants: `RAG_API_URL`, `SCANNER_API_URL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | MUST |
| 2 | `.env` chứa tất cả URLs với giá trị mặc định hợp lệ | MUST |
| 3 | `config.py` sử dụng `os.environ.get()` với default values (hoạt động ngay cả khi không có `.env`) | MUST |
| 4 | Grep `localhost:8001\|localhost:8111\|localhost:8000\|localhost:11434` chỉ xuất hiện trong `.env` và `config.py` | MUST |
| 5 | `graph_orchestator.py` import từ `config.py` | MUST |
| 6 | Pipeline chạy được bình thường sau thay đổi (smoke test) | MUST |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| `.env` bị thiếu trên máy khác → agents dùng sai URL | Trung bình | Cao | `config.py` có default values cho mọi field |
| Thay đổi constructor signature → break existing code | Cao | Trung bình | Dùng keyword arguments với defaults, giữ backward compatibility tạm thời |

---

## SLICE 0.2 — Tạo RAGClient Class

**Ticket:** `SLICE-0.2`
**Phase:** 0 — Foundation
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P0 (Bắt buộc)
**Dependency:** SLICE-0.1 (cần `config.py` để lấy `RAG_API_URL`)
**Tham chiếu:** [A-P1-1] trong Integration_Analysis_Report.md § 7.2

### Mục tiêu

Tạo **shared HTTP client** (`agents/shared/rag_client.py`) cung cấp interface thống nhất cho tất cả agents gọi RAG API. Bao gồm: retry, timeout, error handling, graceful fallback.

### Bối cảnh hiện tại

- `planning_agent.py:99-148` — Tự viết `requests.post()`, parse response, handle errors
- `risk_evaluation_agent.py:90-130` — Tự viết `requests.post()`, parse response khác format
- Hai agent parse response **khác nhau** (planning đọc `data.results`, risk đọc `data.payload.risk_bundle`)
- Không có retry, timeout chỉ set ở risk agent (10s), planning agent (15s)

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Thiết kế interface | Xác định 5 public methods: `retrieve_checks()`, `retrieve_maturity()`, `build_context()`, `resolve_mapping()`, `is_healthy()` | Design doc (inline) |
| 2 | Implement `RAGClient.__init__()` | Nhận `base_url`, `timeout`, `max_retries`. Tạo `requests.Session()` với retry adapter | `agents/shared/rag_client.py` |
| 3 | Implement `is_healthy()` | `GET /ready` → return bool | Trong `rag_client.py` |
| 4 | Implement `retrieve_checks()` | `POST /v1/retrieve/checks` → parse & return standardized dict | Trong `rag_client.py` |
| 5 | Implement `retrieve_maturity()` | `POST /v1/retrieve/maturity` → parse & return standardized dict | Trong `rag_client.py` |
| 6 | Implement `build_context()` | `POST /v1/context/build` → parse & return dict. Đây là method chính cho agents | Trong `rag_client.py` |
| 7 | Implement `resolve_mapping()` | `POST /v1/resolve/mapping` → parse & return dict | Trong `rag_client.py` |
| 8 | Error handling | Mỗi method: try-except bọc ngoài, log lỗi, return `None` hoặc empty dict khi fail. **Không raise exception** — để agent tự quyết fallback | Trong từng method |
| 9 | Logging | Dùng `logging.getLogger(__name__)` — log mỗi request (URL, params) ở DEBUG, log errors ở WARNING | Trong `rag_client.py` |

### Thiết kế Interface chi tiết

```
RAGClient
├── __init__(base_url: str, timeout: float = 10.0, max_retries: int = 1)
│     → Tạo requests.Session() với HTTPAdapter(max_retries=Retry(...))
│
├── is_healthy() → bool
│     → GET {base_url}/ready
│     → Return True nếu status 200 và JSON chứa {"status": "ok"}
│     → Return False nếu timeout/error
│
├── retrieve_checks(query, check_id, service, top_k, retrieval_mode) → dict | None
│     → POST {base_url}/v1/retrieve/checks
│     → Return: {"results": [...], "meta": {...}} hoặc None
│
├── retrieve_maturity(query, capability_id, domain, top_k) → dict | None
│     → POST {base_url}/v1/retrieve/maturity
│     → Return: {"results": [...], "meta": {...}} hoặc None
│
├── build_context(consumer, findings, check_ids, service, ...) → dict | None
│     → POST {base_url}/v1/context/build
│     → Return: {"payload": {...}, "meta": {...}} hoặc None
│     → Đây là method CHÍNH, consumer = "planning" | "risk" | "report"
│
└── resolve_mapping(check_id, service) → dict | None
      → POST {base_url}/v1/resolve/mapping
      → Return: {"mappings": [...]} hoặc None
```

### Luồng dữ liệu nội bộ (mỗi method call)

```
Agent gọi RAGClient.build_context(consumer="risk", check_ids=[...])
  │
  ├─ Tạo payload dict
  ├─ POST → RAG API (timeout=10s)
  │    ├─ Success (200) → parse JSON → return data
  │    ├─ Retry-able error (500, 503, timeout) → retry 1 lần
  │    │    ├─ Retry success → return data
  │    │    └─ Retry fail → log WARNING → return None
  │    └─ Non-retry error (400, 422) → log WARNING → return None
  │
  └─ Agent nhận dict hoặc None → tự quyết fallback
```

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `agents/shared/` directory | Đã tồn tại (chứa `normalizer.py`) |
| Library | `requests`, `urllib3.util.retry` | Đã có trong project |
| Tài liệu | RAG API route definitions tại `RAG/app/api/routes/` | Để verify request/response format |
| Tham chiếu | `planning_agent.py:99-148`, `risk_evaluation_agent.py:90-130` | Code hiện tại cần thay thế |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | File `agents/shared/rag_client.py` tồn tại với class `RAGClient` | MUST |
| 2 | 5 public methods implement đầy đủ: `is_healthy`, `retrieve_checks`, `retrieve_maturity`, `build_context`, `resolve_mapping` | MUST |
| 3 | Mỗi method có error handling: **không raise exception ra ngoài**, return `None` khi fail | MUST |
| 4 | Timeout configurable qua constructor (default 10s) | MUST |
| 5 | Retry logic: tối đa 1 retry cho server errors (5xx) và timeout | MUST |
| 6 | Logging: mỗi request log ở DEBUG, errors log ở WARNING | SHOULD |
| 7 | `build_context()` parse đúng response format: `data.payload.{consumer}_bundle` | MUST |
| 8 | Type hints cho tất cả public methods | SHOULD |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| RAG API response format thay đổi → client parse sai | Thấp | Cao | `build_context()` log raw response ở DEBUG level để troubleshoot. Defensive parsing với `.get()` |
| Retry logic gây latency tăng gấp đôi khi RAG down | Trung bình | Trung bình | Timeout ngắn (10s), chỉ retry 1 lần. Tổng worst-case = 20s, chấp nhận được |
| Thread safety khi nhiều agents gọi đồng thời | Thấp | Thấp | `requests.Session()` thread-safe by default |

---

## SLICE 0.3 — Thêm RAG Health Check vào Pipeline

**Ticket:** `SLICE-0.3`
**Phase:** 0 — Foundation
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P0 (Bắt buộc)
**Dependency:** SLICE-0.2 (cần `RAGClient.is_healthy()`)
**Tham chiếu:** [R-P0-3] trong Integration_Analysis_Report.md § 7.1

### Mục tiêu

Pipeline kiểm tra RAG readiness **trước khi bắt đầu** PDCA cycle. Kết quả lưu vào `PDCAState` để các agents downstream biết RAG có khả dụng hay không → quyết định gọi RAG hay fallback.

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Thêm field `rag_available` vào `PDCAState` | Type: `bool`, default: `False` | `AgentState.py` modified |
| 2 | Cập nhật `environment_node` trong `graph_orchestator.py` | Sau khi EnvironmentAgent chạy xong, gọi `RAGClient.is_healthy()` → set `state["rag_available"]` | `graph_orchestator.py` modified |
| 3 | Tạo instance RAGClient trong orchestrator | `rag_client = RAGClient(base_url=config.RAG_API_URL)` → truyền vào agents cần | `graph_orchestator.py` modified |

### Luồng dữ liệu

```
environment_node(state)
  │
  ├─ EnvironmentAgent.run() → AWS context
  │
  ├─ RAGClient.is_healthy()
  │    ├─ True  → state["rag_available"] = True
  │    │          print("✅ RAG Service: Available")
  │    └─ False → state["rag_available"] = False
  │              print("⚠️ RAG Service: Unavailable — pipeline sẽ chạy degraded mode")
  │
  └─ return state
      │
      ▼ (downstream agents)
  if state["rag_available"]:
      rag_data = rag_client.build_context(...)
  else:
      rag_data = None  # fallback
```

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `AgentState.py`, `graph_orchestator.py` | Files cần sửa |
| Dependency | SLICE-0.2 (`RAGClient`) | Phải hoàn thành trước |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | `PDCAState` có field `rag_available: bool` | MUST |
| 2 | `environment_node` gọi `RAGClient.is_healthy()` và set state | MUST |
| 3 | Pipeline **không crash** khi RAG service down (health check return False gracefully) | MUST |
| 4 | Console output hiển thị rõ trạng thái RAG (Available/Unavailable) | SHOULD |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| Health check timeout chậm → delay pipeline start | Thấp | Thấp | Timeout cho health check = 3s (ngắn hơn default 10s) |
| RAG available lúc check nhưng down giữa pipeline | Thấp | Trung bình | Mỗi agent vẫn có try-except riêng (defense in depth) |

---

## SLICE 0.4 — Dọn dẹp Endpoint cũ (RAG Side)

**Ticket:** `SLICE-0.4`
**Phase:** 0 — Foundation
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P0 (Bắt buộc)
**Dependency:** Không (có thể làm song song với 0.1-0.3)
**Tham chiếu:** [R-P0-1] trong Integration_Analysis_Report.md § 7.1

### Mục tiêu

Xóa bỏ hoàn toàn endpoint cũ `/retrieve` trong RAG API. Đảm bảo toàn bộ codebase chỉ sử dụng endpoints `/v1/*`.

### Bối cảnh hiện tại

- `RAG/app/api/routes/__init__.py` — Nơi đăng ký routes. Cần verify endpoint cũ `/retrieve` còn được đăng ký không
- `graph_orchestator.py:37` — `RETRIEVAL_API_URL = "http://localhost:8111/retrieve"` — endpoint cũ, sai port

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Kiểm tra `RAG/app/api/routes/__init__.py` | Xác định endpoint cũ `/retrieve` có còn được đăng ký không | Audit result |
| 2 | Xóa route cũ (nếu có) | Remove registration của `/retrieve` endpoint | `routes/__init__.py` modified |
| 3 | Xóa file route cũ (nếu có) | Kiểm tra `RAG/app/api/routes/build.py` (đã bị xóa trong git status). Confirm không còn orphaned route files | Cleanup done |
| 4 | Grep verification | Search toàn bộ codebase cho `/retrieve` (không có prefix `/v1`) để tìm references còn sót | Grep clean |
| 5 | Xóa `RETRIEVAL_API_URL` trong `graph_orchestator.py` | Biến này reference endpoint cũ port 8111, không còn dùng | `graph_orchestator.py` modified |

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `RAG/app/api/routes/__init__.py`, `graph_orchestator.py` | Files cần kiểm tra/sửa |
| Context | Git status cho thấy `RAG/app/api/routes/build.py` đã bị xóa (` D`) | Confirm đã cleanup |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | Grep `/retrieve` (without `/v1/`) trong cả RAG và Agent codebase → 0 results (ngoại trừ comments) | MUST |
| 2 | Grep `localhost:8111` → 0 results | MUST |
| 3 | RAG API chỉ expose endpoints `/v1/*`, `/health`, `/ready` | MUST |
| 4 | Pipeline chạy bình thường sau cleanup | MUST |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| External service (ngoài project) vẫn gọi endpoint cũ | Thấp | Thấp | RAG chỉ serve local agents, không có external consumers |

---

## SLICE RS-1 — Shared Utilities & Infrastructure (Agent Refactor)

**Ticket:** `SLICE-RS-1`
**Phase:** RS — Agent Refactor
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P0 (Bắt buộc — prerequisite cho RS-2, RS-3)
**Dependency:** Không
**Tham chiếu:** [Agent_Refactor_Plan.md](Agent_Refactor_Plan.md) — RS-1, Issues PA-04, RA-01, RA-02

### Mục tiêu

Tạo **shared utility module** (`agents/shared/utils.py`) chứa các functions dùng chung giữa PlanningAgent và RiskEvaluationAgent, loại bỏ code duplicate và fix data flow.

### Bối cảnh — Tại sao cần slice này

Phân tích source code phát hiện **3 pattern duplicate nghiêm trọng** giữa 2 agents:

| Pattern | PlanningAgent | RiskEvaluationAgent | Vấn đề |
|---|---|---|---|
| Check ID extraction | `run():155` (regex) | `run():159-175` + `run():196-204` (**2 lần**) | 3 nơi, 3 implementation khác nhau |
| JSON parsing | `_clean_json()` dòng 52-64 | `_extract_json_from_text()` dòng 82-89 | Gần giống, nhưng khác regex pattern |
| Check ID sanitization | `_sanitize_id()` dòng 82-98 | Không có (tự xử lý inline) | Chỉ 1 agent có, agent kia thiếu |

**Phát hiện quan trọng nhất:** Normalizer (`agents/shared/normalizer.py:38-39`) đã extract `event_code` (= Prowler check ID) vào mỗi finding. Nhưng RiskEvaluationAgent **hoàn toàn bỏ qua** field này, tự viết 22 dòng regex để extract lại — phức tạp và dễ lỗi.

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Tạo `agents/shared/utils.py` | Module mới chứa shared utilities | File mới |
| 2 | Implement `extract_check_id(finding: dict) → str \| None` | Logic ưu tiên: (1) `finding.get("event_code")` ← normalizer đã có; (2) `finding.get("check_id")`; (3) regex fallback từ `finding_id`. Một function thay thế ~44 dòng duplicate | Trong `utils.py` |
| 3 | Implement `parse_llm_json(text: str) → dict` | Merge logic tốt nhất từ cả 2 agents: try ` ```json ``` ` block → regex `\{[\s\S]*\}` → remove control chars → `json.loads()` → return `{}` nếu fail | Trong `utils.py` |
| 4 | Implement `sanitize_check_id(raw_id: str) → str` | Move `PlanningAgent._sanitize_id()` vào shared module. Xóa prefix `check:`/`capability:`, xóa suffix `_overview`/`_risk`/... | Trong `utils.py` |
| 5 | Setup logging convention | Tạo helper hoặc document convention: mỗi agent dùng `logger = logging.getLogger(__name__)` thay vì `print()` | Convention doc |

### Luồng dữ liệu — Trước vs Sau

```
TRƯỚC:
  Normalizer output: {event_code: "s3_bucket_public_access", finding_id: "prowler-aws-..."}
       │
       ▼ RiskEvaluationAgent
  cid = f.get("check_id")        ← MISS (field không tồn tại)
     or f.get("CheckID")          ← MISS
     or f.get("checkId")          ← MISS
  → Fallback: 22 dòng regex      ← Phức tạp, dễ lỗi
       │
       ▼ Result: "s3_bucket_public_access" (nếu may mắn regex match đúng)

SAU:
  Normalizer output: {event_code: "s3_bucket_public_access", ...}
       │
       ▼ extract_check_id(finding)
  return finding.get("event_code")  ← HIT ngay lần đầu, 1 dòng
       │
       ▼ Result: "s3_bucket_public_access" (guaranteed correct)
```

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `planning_agent.py:52-98`, `risk_evaluation_agent.py:82-89, 159-204` | Code cần extract |
| Source code | `agents/shared/normalizer.py:38-39` | Verify `event_code` field |
| Thư mục | `agents/shared/` | Đã tồn tại |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | File `agents/shared/utils.py` tồn tại với 3 public functions: `extract_check_id`, `parse_llm_json`, `sanitize_check_id` | MUST |
| 2 | `extract_check_id()` ưu tiên `event_code` trước regex fallback | MUST |
| 3 | `parse_llm_json()` handle được cả ` ```json ``` ` block và raw JSON | MUST |
| 4 | Tất cả functions return giá trị mặc định khi input invalid (không raise exception) | MUST |
| 5 | Type hints cho tất cả public functions | SHOULD |
| 6 | Unit tests cho 3 functions (tối thiểu 3 test cases mỗi function) | SHOULD |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| `event_code` không tồn tại trong một số findings (từ nguồn không phải normalizer) | Thấp | Trung bình | `extract_check_id()` có fallback chain: `event_code` → `check_id` → regex |
| Import circular dependency khi agents import shared/utils | Thấp | Thấp | `utils.py` không import từ agents — chỉ dùng stdlib |

---

## SLICE RS-2 — Refactor PlanningAgent Code Quality

**Ticket:** `SLICE-RS-2`
**Phase:** RS — Agent Refactor
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P0 (Bắt buộc)
**Dependency:** SLICE-RS-1
**Tham chiếu:** [Agent_Refactor_Plan.md](Agent_Refactor_Plan.md) — RS-2, Issues PA-03, PA-05, PA-06, PA-07

### Mục tiêu

Refactor PlanningAgent để: (1) tách God Method `run()` thành methods nhỏ testable, (2) **giữ metadata trong retrieval** thay vì chỉ trả về IDs → cải thiện chất lượng re-ranking, (3) fix silent S3 default khi LLM fail.

### Bối cảnh — Các vấn đề code quality nghiêm trọng

**[PA-03] God Method `run()` — 84 dòng, 4 luồng trộn lẫn:**
Method `run()` (dòng 149-233) chứa: regex parsing, LLM call #1, RAG API call, LLM call #2, fallback logic, error handling — tất cả trong 1 method. Không thể test từng phần riêng lẻ.

**[PA-05] Re-ranking mất metadata — Lỗi data flow nghiêm trọng nhất:**
```
RAG API trả về:
  {doc_id: "check:s3_...", score: 0.85,
   metadata: {severity: "high", title: "S3 Bucket Public...", service: "s3"}}
                    ↓
  _call_retrieval_service() CHỈ LẤY doc_id, BỎ MẤT score/severity/title
                    ↓
  RERANK_PROMPT nhận: ["s3_bucket_public_access", ...]  ← Chỉ tên ID, không context
                    ↓
  LLM re-ranking KHÔNG CÓ ĐỦ thông tin để rank tốt ★
```

**[PA-07] Silent default S3:** LLM translation fail → `_clean_json()` return `{}` → `target_svc` default `"s3"`. User hỏi "check IAM" mà LLM lỗi → scan S3 không báo.

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Import shared utils | `from agents.shared.utils import extract_check_id, parse_llm_json, sanitize_check_id` — xóa `_clean_json()`, `_sanitize_id()` nội bộ | Imports updated |
| 2 | Tách `run()` thành 4 methods | `_detect_explicit_checks()`, `_translate_intent()`, `_retrieve_candidates()`, `_rerank_and_select()`. `run()` chỉ orchestrate ~15 dòng | 4 methods mới |
| 3 | `_retrieve_candidates()` trả `List[Dict]` | Giữ metadata (title, severity, service, score) thay vì chỉ IDs. Return `[{"check_id": ..., "title": ..., "severity": ..., "score": ...}]` | Data flow fix |
| 4 | Cập nhật `RERANK_PROMPT` | Nhận enriched candidates thay vì list strings. LLM có severity + title để rank chính xác hơn | Prompt updated |
| 5 | Fix error handling `_translate_intent()` | Khi parse fail → log WARNING + try keyword matching trước khi default. Thêm `_infer_service_from_keywords(request)` | Error handling improved |
| 6 | Mở rộng service whitelist | Tăng `valid_services` từ 10 → ≥20 services (cover Prowler supported services) | Whitelist expanded |
| 7 | Fix indentation | Chuẩn PEP 8: 4 spaces toàn bộ file | Code style |
| 8 | Replace `print()` → `logging` | `logger = logging.getLogger(__name__)` | Observability |

### Luồng dữ liệu sau refactor

```
run(user_request)
  │
  ├─ _detect_explicit_checks(request) → Dict | None
  │    Regex detect check IDs trong input → fast return nếu tìm thấy
  │
  ├─ _translate_intent(request) → Dict
  │    LLM call → parse JSON → validate service name
  │    ★ Nếu parse fail: keyword matching fallback → KHÔNG silent default S3
  │
  ├─ Nếu is_group_scan → return group plan (early exit)
  │
  ├─ _retrieve_candidates(request, intent) → List[Dict]
  │    RAG call → GIỮ METADATA (title, severity, score)
  │    ★ Return [{check_id, title, severity, service, score}]
  │
  └─ _rerank_and_select(request, candidates, target_svc) → Dict
       LLM call với ENRICHED candidates
       ★ LLM biết severity + title → rank chính xác hơn
```

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `agents/planning_agent.py` | File chính |
| Dependency | SLICE-RS-1 (`agents/shared/utils.py`) | Shared functions |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | `run()` ≤ 20 dòng (orchestration only) | MUST |
| 2 | Mỗi sub-method ≤ 30 dòng | MUST |
| 3 | `_retrieve_candidates()` trả về `List[Dict]` với ít nhất `check_id`, `title`, `severity` | MUST |
| 4 | `RERANK_PROMPT` nhận enriched candidates (không chỉ IDs) | MUST |
| 5 | LLM parse fail → log WARNING, keyword fallback trước default | MUST |
| 6 | `_clean_json()` và `_sanitize_id()` đã xóa, dùng shared utils | MUST |
| 7 | Toàn bộ file dùng 4-space indent | MUST |
| 8 | Không còn `print()`, dùng `logging` | SHOULD |
| 9 | `valid_services` ≥ 20 services | SHOULD |
| 10 | Re-ranking output quality ≥ baseline (verify bằng test thủ công) | MUST |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| Enriched candidates quá dài → RERANK_PROMPT exceed LLM context | Trung bình | Trung bình | Limit 10 candidates, truncate description nếu cần |
| Tách method thay đổi behavior → regression | Trung bình | Cao | Test thủ công: cùng input, compare output trước/sau refactor |
| Keyword matching fallback bắt nhầm service | Thấp | Thấp | Chỉ match exact service names, không fuzzy match |

---

## SLICE RS-3 — Refactor RiskEvaluationAgent Code Quality

**Ticket:** `SLICE-RS-3`
**Phase:** RS — Agent Refactor
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P0 (Bắt buộc)
**Dependency:** SLICE-RS-1
**Tham chiếu:** [Agent_Refactor_Plan.md](Agent_Refactor_Plan.md) — RS-3, Issues RA-01 đến RA-08

### Mục tiêu

Refactor RiskEvaluationAgent để: (1) dùng `event_code` thay 22 dòng regex, (2) tách `run()` thành methods, (3) fix field `extended_description` luôn empty, (4) validate LLM output, (5) fix SYSTEM_PROMPT.

### Bối cảnh — Các vấn đề nghiêm trọng

**[RA-02] Không dùng `event_code` — lỗi data flow nghiêm trọng nhất:**
Normalizer đã extract `event_code` (= check ID). Agent bỏ qua, tự viết 22 dòng regex × 2 lần.

**[RA-06] `extended_description` luôn empty:**
`_fetch_risk_context_batch()` build context_map với keys: `severity`, `title`, `mappings`.
Nhưng LLM prompt reference `rag_data.get("description")` → **luôn trả về `""`**.
LLM nhận RAG context nhưng 1 field quan trọng luôn trống — lãng phí prompt token.

**[RA-04] Unsafe merge `ai_data.update(parsed)`:**
LLM output không validate → bất kỳ field nào (kể cả `status`, `service`) có thể bị ghi đè nếu LLM hallucinate.

**[RA-08] Không check HTTP status:** `requests.post()` rồi `response.json()` mà không `raise_for_status()` → API trả 500 vẫn parse silently.

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Import shared utils | `from agents.shared.utils import extract_check_id, parse_llm_json` — xóa `_extract_json_from_text()` nội bộ | Imports updated |
| 2 | Replace check_id extraction | Xóa 2 blocks regex (dòng 159-175, 196-204). Thay bằng `extract_check_id(finding)` (1 dòng) | ~44 dòng → ~2 dòng |
| 3 | Tách `run()` thành methods | `_filter_fail_findings()`, `_fetch_rag_context()`, `_score_single_finding()`, `_score_findings()`, `_sort_by_priority()` | 5 methods mới, `run()` ≤ 15 dòng |
| 4 | Fix `extended_description` | Đổi `rag_data.get("description", "")` → `rag_data.get("title", "")` trong llm_view. Rename field thành `check_title` cho rõ nghĩa | Data flow fix |
| 5 | Validate LLM output | Thay `ai_data.update(parsed)` bằng whitelist validation: chỉ cho phép `ai_severity` (enum), `ai_risk_score` (int 0-10), `ai_reasoning` (str) | Security fix |
| 6 | Fix SYSTEM_PROMPT | Xóa `._` thừa dòng 41. Thêm hướng dẫn cụ thể cách dùng `rag_context` fields | Prompt improved |
| 7 | Thêm `response.raise_for_status()` | Trong `_fetch_risk_context_batch()` sau `requests.post()` | HTTP error handling |
| 8 | Fix indentation | Chuẩn PEP 8: 4 spaces toàn bộ file | Code style |
| 9 | Replace `print()` → `logging` | `logger = logging.getLogger(__name__)` | Observability |

### Luồng dữ liệu sau refactor

```
run(normalized_findings)
  │
  ├─ _filter_fail_findings(findings) → List[Dict]
  │    Lọc status=="FAIL"
  │
  ├─ _fetch_rag_context(fail_findings) → Dict[str, Any]
  │    ★ extract_check_id(f) thay vì 22 dòng regex
  │    → Batch RAG call → context_map
  │
  ├─ _score_findings(fail_findings, rag_context_map) → List[Dict]
  │    For each finding:
  │      ├─ _score_single_finding(finding, rag_data)
  │      │    ├─ Build llm_view (★ dùng "check_title" thay "description")
  │      │    ├─ LLM.invoke()
  │      │    ├─ ★ Validate output (whitelist 3 fields, type check)
  │      │    └─ Merge vào finding
  │      └─ Append result
  │
  └─ _sort_by_priority(scored_findings) → List[Dict]
       Sort by (severity_map, risk_score) desc
```

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `agents/risk_evaluation_agent.py` | File chính |
| Source code | `agents/shared/normalizer.py:87-100` | Verify normalized finding schema |
| Dependency | SLICE-RS-1 (`agents/shared/utils.py`) | Shared functions |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | Không còn inline regex cho check_id extraction — dùng `extract_check_id()` | MUST |
| 2 | `run()` ≤ 15 dòng | MUST |
| 3 | `llm_view` dùng `check_title` (từ RAG `title`) thay vì `extended_description` (luôn empty) | MUST |
| 4 | LLM output validate: chỉ 3 fields allowed, `ai_severity` phải thuộc enum, `ai_risk_score` phải int 0-10 | MUST |
| 5 | SYSTEM_PROMPT không còn ký tự rác `._` | MUST |
| 6 | `_fetch_risk_context_batch()` có `response.raise_for_status()` | MUST |
| 7 | `_extract_json_from_text()` đã xóa, dùng `parse_llm_json()` từ shared | MUST |
| 8 | Toàn bộ file dùng 4-space indent | MUST |
| 9 | Không còn `print()`, dùng `logging` | SHOULD |
| 10 | Output (enriched findings) giữ nguyên schema → downstream không break | MUST |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| Validate quá strict → reject valid LLM output | Trung bình | Trung bình | Log rejected fields ở DEBUG level. Default values hợp lý (`"Medium"`, `5`) |
| Tách method thay đổi output format → downstream break | Thấp | Cao | Enriched finding schema giữ nguyên các keys hiện có. Chỉ rename internal logic |
| `event_code` không chính xác cho edge cases | Thấp | Thấp | `extract_check_id()` có regex fallback |

---

## SLICE RS-4 — Orchestrator Wiring & Cleanup

**Ticket:** `SLICE-RS-4`
**Phase:** RS — Agent Refactor
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P0 (Bắt buộc)
**Dependency:** SLICE-RS-2, SLICE-RS-3
**Tham chiếu:** [Agent_Refactor_Plan.md](Agent_Refactor_Plan.md) — RS-4, Issues PA-02, PA-08

### Mục tiêu

Cập nhật `graph_orchestator.py` để: (1) xóa biến chết `RETRIEVAL_API_URL`, (2) wiring mới phù hợp với refactored agents.

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Xóa `RETRIEVAL_API_URL` | Dòng 37: `RETRIEVAL_API_URL = "http://localhost:8111/retrieve"` — biến này KHÔNG được reference ở bất kỳ đâu trong file. Xóa | Dead code removed |
| 2 | Verify `planning_node` wiring | Confirm PlanningAgent constructor phù hợp sau refactor RS-2. Nếu signature thay đổi → update dòng 143-147 | Orchestrator compatible |
| 3 | Verify `risk_evaluation_node` wiring | Confirm RiskEvaluationAgent constructor phù hợp sau refactor RS-3. Update dòng 227 nếu cần | Orchestrator compatible |
| 4 | Smoke test | Chạy pipeline end-to-end → verify không crash | Pipeline works |

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `graph_orchestator.py` | File chính |
| Dependency | SLICE-RS-2, SLICE-RS-3 | Agents đã refactor xong |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | `RETRIEVAL_API_URL` đã xóa | MUST |
| 2 | `planning_node` tạo PlanningAgent thành công sau refactor | MUST |
| 3 | `risk_evaluation_node` tạo RiskEvaluationAgent thành công sau refactor | MUST |
| 4 | Pipeline chạy end-to-end không crash (smoke test) | MUST |
| 5 | Comment `# Lúc này Agent đã được sửa để gọi API nội bộ ở port 8111` (dòng 142) đã xóa/update | SHOULD |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| Constructor signature thay đổi → node tạo agent fail | Trung bình | Cao | RS-2/RS-3 phải giữ backward-compatible constructor (keyword args với defaults) |

---

## SLICE 1.1 — PlanningAgent: Chuyển sang RAGClient

**Ticket:** `SLICE-1.1`
**Phase:** 1 — PlanningAgent RAG Integration
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P0 (Bắt buộc)
**Dependency:** SLICE-0.1, SLICE-0.2, **SLICE-RS-2** (agent phải được refactor trước)
**Tham chiếu:** [A-P0-2] trong Integration_Analysis_Report.md § 7.2, Phase 1 trong § 8.3

### Mục tiêu

Replace toàn bộ raw `requests.post()` calls trong `PlanningAgent._retrieve_candidates()` (đã refactor từ RS-2) bằng `RAGClient.retrieve_checks()`. Loại bỏ hardcoded URL.

### Bối cảnh hiện tại

`planning_agent.py:99-148` — Method `_call_retrieval_service()`:
- Hardcode URL `http://localhost:8001/v1/retrieve/checks` (dòng 101)
- Tự parse response: `data.get("data", {}).get("results", [])`
- Tự filter theo service (hard filter dòng 123-125)
- Tự sanitize IDs (dòng 137-141)

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Thêm `rag_client` vào constructor | `PlanningAgent.__init__(..., rag_client: RAGClient = None)` | Constructor updated |
| 2 | Truyền `rag_client` từ orchestrator | Trong `graph_orchestator.py`, khi tạo PlanningAgent, truyền shared RAGClient instance | Orchestrator updated |
| 3 | Refactor `_call_retrieval_service()` | Replace `requests.post(url, json=payload)` → `self.rag_client.retrieve_checks(query, service, top_k)` | Method simplified |
| 4 | Giữ nguyên post-processing | Logic filter service, sanitize IDs giữ nguyên (đã work) | Không thay đổi |
| 5 | Thêm fallback khi `rag_client` là `None` | Nếu `rag_client` không được truyền → log warning, return `[]` | Backward compatible |

### Luồng dữ liệu sau refactor

```
PlanningAgent._call_retrieval_service(query, target_svc)
  │
  ├─ [OLD] requests.post("http://localhost:8001/v1/retrieve/checks", json=payload)
  │
  ├─ [NEW] self.rag_client.retrieve_checks(
  │           query=enhanced_query,
  │           service=target_svc,
  │           top_k=10,
  │           retrieval_mode="hybrid"
  │         )
  │    → return dict | None
  │
  ├─ if result is None → return []  (RAG unavailable)
  │
  ├─ [GIỮA NGUYÊN] filter by service
  ├─ [GIỮA NGUYÊN] sanitize IDs
  └─ return clean_ids[:5]
```

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `planning_agent.py`, `graph_orchestator.py` | Files cần sửa |
| Dependency | SLICE-0.2 (`RAGClient`), SLICE-0.1 (`config.py`) | Phải hoàn thành trước |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | `planning_agent.py` không còn `import requests` hoặc `requests.post()` | MUST |
| 2 | `planning_agent.py` không còn hardcoded URL | MUST |
| 3 | PlanningAgent nhận `rag_client` qua constructor | MUST |
| 4 | PlanningAgent hoạt động bình thường khi `rag_client=None` (fallback) | MUST |
| 5 | Kết quả planning (check IDs output) giống hoặc tốt hơn trước refactor | MUST |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| `RAGClient.retrieve_checks()` trả về format khác `requests.post()` → parse lỗi | Trung bình | Cao | Verify format bằng test trước khi refactor. RAGClient nên standardize response |
| PlanningAgent post-processing logic bị break | Thấp | Cao | Giữ nguyên post-processing, chỉ thay input source |

---

## SLICE 1.2 — PlanningAgent: Chuyển sang PlanningBundle

**Ticket:** `SLICE-1.2`
**Phase:** 1 — PlanningAgent Enhancement
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P1 (Nên làm)
**Dependency:** SLICE-1.1
**Tham chiếu:** Phase 1 (task 1.2-1.5) trong Integration_Analysis_Report.md § 8.3

### Mục tiêu

Nâng cấp PlanningAgent từ `retrieve_checks()` (chỉ lấy check IDs) sang `build_context(consumer="planning")` (nhận PlanningBundle đầy đủ: checks + mappings + maturity). Tận dụng maturity context cho LLM re-ranking chính xác hơn.

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Thay `retrieve_checks()` → `build_context()` | Gọi `rag_client.build_context(consumer="planning", query=..., service=..., top_k=10)` | `_call_retrieval_service()` updated |
| 2 | Parse PlanningBundle | Extract `related_findings`, `control_mapping_ids`, `maturity_capability_ids` | New parsing logic |
| 3 | Enriched re-ranking | Truyền maturity context vào `RERANK_PROMPT` để LLM biết compliance requirements khi chọn checks | `RERANK_PROMPT` updated |
| 4 | Confidence-based branching | Đọc `meta.confidence` từ response. Nếu `low` → mở rộng scope sang group scan | Branching logic added |
| 5 | Fallback chain | `build_context()` fail → try `retrieve_checks()` → fail → group scan | Robust fallback |

### Luồng dữ liệu mới

```
PlanningAgent.run(user_request)
  │
  ├─ LLM Translation → {target_service, search_queries}
  │
  ├─ ★ rag_client.build_context(
  │     consumer="planning",
  │     query=search_queries[0],
  │     service=target_service,
  │     top_k=10
  │   )
  │   │
  │   ├─ Success → PlanningBundle:
  │   │   - related_findings: [{check_id, title, service, severity}]
  │   │   - control_mapping_ids: [capability_ids]
  │   │   - maturity_capability_ids: [capability_ids]
  │   │   - meta.confidence: "high" | "medium" | "low"
  │   │
  │   ├─ None (fail) → Fallback: rag_client.retrieve_checks(...)
  │   │   ├─ Success → basic check IDs only
  │   │   └─ None → Fallback: group scan
  │   │
  │   └─ confidence == "low" → override: group scan
  │
  ├─ Extract check_ids từ related_findings
  ├─ LLM Re-ranking (enriched với maturity context)
  └─ Return assessment_plan
```

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `planning_agent.py` | File chính cần sửa |
| Tài liệu | RAG PlanningBundle format tại `RAG/app/core/models.py` | Verify field names |
| Dependency | SLICE-1.1 (RAGClient integrated) | Phải hoàn thành trước |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | PlanningAgent gọi `build_context(consumer="planning")` thay vì `retrieve_checks()` | MUST |
| 2 | PlanningAgent parse được PlanningBundle fields (`related_findings`, `control_mapping_ids`) | MUST |
| 3 | Confidence-based branching: `low` confidence → group scan | SHOULD |
| 4 | Fallback chain hoạt động: `build_context` → `retrieve_checks` → group scan | MUST |
| 5 | LLM re-ranking prompt có maturity context | NICE |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| PlanningBundle format khác expected → parse sai | Trung bình | Cao | Verify format bằng manual API call trước. Log raw response ở DEBUG |
| Maturity context quá dài → LLM context overflow | Thấp | Trung bình | Truncate maturity context tới 500 chars trong prompt |

---

## SLICE 2.1 — RiskEvaluationAgent: Chuyển sang RAGClient

**Ticket:** `SLICE-2.1`
**Phase:** 2 — RiskEvaluationAgent RAG Optimization
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P0 (Bắt buộc)
**Dependency:** SLICE-0.1, SLICE-0.2, **SLICE-RS-3** (agent phải được refactor trước)
**Tham chiếu:** Phase 2 (task 2.1) trong Integration_Analysis_Report.md § 8.4

### Mục tiêu

Replace raw `requests.post()` trong `RiskEvaluationAgent._fetch_risk_context_batch()` bằng `RAGClient.build_context()`. Loại bỏ inline URL, thống nhất error handling.

### Bối cảnh hiện tại

`risk_evaluation_agent.py:90-130` — Method `_fetch_risk_context_batch()`:
- Hardcode URL `http://localhost:8001/v1/context/build` (dòng 92)
- Tự format `check_ids` với prefix `check:` (dòng 94)
- Parse nested response: `data.payload.risk_bundle.related_findings` (dòng 103-104)
- Parse `control_mapping` (dòng 105)
- Tự build `context_map` (dòng 107-126)

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Thêm `rag_client` vào constructor | `RiskEvaluationAgent.__init__(..., rag_client: RAGClient = None)` | Constructor updated |
| 2 | Truyền `rag_client` từ orchestrator | Trong `graph_orchestator.py`, khi tạo RiskEvaluationAgent, truyền shared RAGClient instance | Orchestrator updated |
| 3 | Refactor `_fetch_risk_context_batch()` | Replace `requests.post()` → `self.rag_client.build_context(consumer="risk", check_ids=...)` | Method simplified |
| 4 | Giữ nguyên context_map building | Logic build `context_map` từ findings + mappings giữ nguyên | Không thay đổi |
| 5 | Fallback | Nếu `rag_client` is None hoặc `build_context()` returns None → return `{}` (existing behavior) | Backward compatible |

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `risk_evaluation_agent.py`, `graph_orchestator.py` | Files cần sửa |
| Dependency | SLICE-0.2 (`RAGClient`) | Phải hoàn thành trước |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | `risk_evaluation_agent.py` không còn `import requests` hoặc `requests.post()` | MUST |
| 2 | `risk_evaluation_agent.py` không còn hardcoded URL | MUST |
| 3 | RiskEvaluationAgent nhận `rag_client` qua constructor | MUST |
| 4 | Output (context_map) format giữ nguyên → downstream code không bị break | MUST |
| 5 | Agent hoạt động bình thường khi `rag_client=None` | MUST |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| `RAGClient.build_context()` return format khác raw `requests.post()` → context_map sai | Trung bình | Cao | RAGClient `build_context()` nên return raw `data` dict, để agent tự extract bundle |

---

## SLICE 2.2 — RiskEvaluationAgent: Batch & Confidence

**Ticket:** `SLICE-2.2`
**Phase:** 2 — RiskEvaluationAgent Enhancement
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P1 (Nên làm)
**Dependency:** SLICE-2.1
**Tham chiếu:** Phase 2 (tasks 2.2-2.4) trong Integration_Analysis_Report.md § 8.4

### Mục tiêu

Optimize hiệu suất RiskEvaluationAgent: (1) batch nhiều check_ids vào 1 RAG call thay vì N calls, (2) dùng confidence level để điều chỉnh weight của RAG context trong scoring prompt, (3) cache kết quả per pipeline run.

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Batch optimization | Hiện tại `_fetch_risk_context_batch()` đã gom check_ids. Verify rằng RAGClient gửi đúng batch. Nếu API chưa hỗ trợ batch → đề xuất thêm batch endpoint | Verify & optimize |
| 2 | Confidence-based scoring | Đọc `meta.confidence` từ RAGClient response. Thêm hint vào LLM prompt: `"RAG confidence: {level}. Nếu low, ít tin tưởng vào compliance data."` | Prompt updated |
| 3 | In-memory cache | Tạo `dict` cache trong instance: `self._rag_cache: Dict[str, dict]`. Key = check_id, value = rag_data. Reset mỗi `run()` call | Simple caching |
| 4 | Metrics tracking | Log cache hit/miss rate vào `get_llm_metrics()` | Metrics enhanced |

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `risk_evaluation_agent.py` | File cần sửa |
| Dependency | SLICE-2.1 | Phải hoàn thành trước |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | Batch: Chỉ 1 RAG call cho tất cả unique check_ids (không N calls) | MUST |
| 2 | Confidence hint trong LLM prompt khi `meta.confidence` available | SHOULD |
| 3 | In-memory cache hoạt động: same check_id trong cùng run → không gọi RAG lại | SHOULD |
| 4 | Metrics có cache hit rate | NICE |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| Batch quá lớn (>50 check_ids) → RAG timeout | Thấp | Trung bình | Chunk batch thành groups of 20 |

---

## SLICE 3.1 — Tích hợp RAG vào RemediationPlannerAgent

**Ticket:** `SLICE-3.1`
**Phase:** 3 — New Integration
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P1 (Nên làm)
**Dependency:** SLICE-0.1, SLICE-0.2
**Tham chiếu:** Phase 3 trong Integration_Analysis_Report.md § 8.5

### Mục tiêu

RemediationPlannerAgent hiện **không dùng RAG** — LLM chọn remediation tool thuần dựa trên finding description. Tích hợp RAG để cung cấp remediation best practices + compliance context → LLM chọn tool chính xác hơn.

### Bối cảnh hiện tại

`remediate_planner_agent.py`:
- Nhận `finding` dict (đã enriched từ RiskEvaluationAgent, có field `compliance`)
- LLM system prompt mô tả available tools + yêu cầu chọn tool
- **Không gọi RAG trực tiếp** — chỉ dùng `finding.get("compliance", [])` có sẵn từ upstream
- Hạn chế: compliance data chỉ là list capability_ids, thiếu remediation text + maturity guidance

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Thêm `rag_client` vào constructor | `RemediationPlannerAgent.__init__(..., rag_client: RAGClient = None)` | Constructor updated |
| 2 | Truyền `rag_client` từ orchestrator | Trong `graph_orchestator.py` → truyền shared RAGClient | Orchestrator updated |
| 3 | Thêm RAG call trong `plan_remediation()` | Trước khi gọi LLM, fetch context: `rag_client.build_context(consumer="planning", check_ids=[check_id], include_mappings=True)` | New RAG call |
| 4 | Extract remediation hints | Từ PlanningBundle: lấy `remediation_text`, `remediation_url` từ `related_findings`. Lấy `capability guidance` từ `maturity_capability_ids` | Parsing logic |
| 5 | Inject vào LLM prompt | Thêm section `### Remediation Context (từ RAG)` vào system prompt với: remediation hints, compliance requirements, maturity guidance | Prompt enriched |
| 6 | Fallback | Nếu `rag_client` is None hoặc call fails → giữ behavior hiện tại (LLM chọn tool không có RAG context) | Graceful degradation |

### Luồng dữ liệu mới

```
RemediationPlannerAgent.plan_remediation(finding)
  │
  ├─ Extract check_id từ finding
  │
  ├─ [NEW] if self.rag_client and state.get("rag_available"):
  │     rag_data = self.rag_client.build_context(
  │         consumer="planning",
  │         check_ids=[check_id],
  │         include_mappings=True,
  │         include_maturity=True
  │     )
  │     │
  │     ├─ Success → Extract:
  │     │   - remediation_text (từ related_findings)
  │     │   - compliance requirements (từ control_mapping_ids)
  │     │   - maturity guidance (từ maturity_capability_ids)
  │     │
  │     └─ Fail → rag_data = None
  │
  ├─ Build LLM prompt:
  │   - Finding details (existing)
  │   - Available tools (existing)
  │   - ★ RAG remediation context (new, nếu có)
  │
  ├─ LLM → chọn tool_name + reasoning
  └─ Return remediation task
```

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `remediate_planner_agent.py`, `graph_orchestator.py` | Files cần sửa |
| Tham chiếu | `agent_tools.py` (REMEDIATION_TOOLS) | Danh sách tools hiện có |
| Dependency | SLICE-0.2 (`RAGClient`) | Phải hoàn thành trước |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | RemediationPlannerAgent nhận `rag_client` qua constructor | MUST |
| 2 | `plan_remediation()` gọi `build_context()` khi RAG available | MUST |
| 3 | LLM prompt chứa RAG remediation context khi available | MUST |
| 4 | Agent hoạt động bình thường khi RAG unavailable (fallback) | MUST |
| 5 | Tool selection accuracy không giảm so với baseline (verify bằng test) | MUST |
| 6 | RAG context được truncate nếu quá dài (tránh LLM context overflow) | SHOULD |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| RAG context quá dài → LLM prompt exceed context window | Trung bình | Cao | Truncate RAG context tới 800 tokens. Chỉ lấy `remediation_text` + top 3 mappings |
| RAG remediation text khác language với prompt (VN vs EN) | Thấp | Thấp | RAG data hiện đều bằng English, phù hợp với LLM |
| Tool selection thay đổi → regression | Trung bình | Trung bình | A/B test: chạy cùng input với và không RAG, compare results |

---

## SLICE 4.1 — Tích hợp RAG vào ReportAgent

**Ticket:** `SLICE-4.1`
**Phase:** 4 — New Integration
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P1 (Nên làm)
**Dependency:** SLICE-0.1, SLICE-0.2
**Tham chiếu:** Phase 4 trong Integration_Analysis_Report.md § 8.6

### Mục tiêu

ReportAgent hiện tạo report thuần dựa vào findings data + LLM generation. Tích hợp RAG để bổ sung: **Compliance Assessment section**, **Maturity Evaluation section**, và **enriched recommendations** dựa trên best practices từ knowledge base.

### Bối cảnh hiện tại

`report_agent.py`:
- Sử dụng Jinja2 templates + LLM (LLMWriter) để generate markdown report
- Input: `report_context` dict chứa enriched findings, metrics, charts
- Output: MD → HTML → PDF
- **Không gọi RAG** — report chỉ dựa vào data đã có trong pipeline state

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Thêm `rag_client` vào constructor | `ReportAgent.__init__(..., rag_client: RAGClient = None)` | Constructor updated |
| 2 | Truyền `rag_client` từ orchestrator | Trong `graph_orchestator.py` → truyền shared RAGClient | Orchestrator updated |
| 3 | Thêm RAG call trong `run()` | Extract unique check_ids từ report_context → `rag_client.build_context(consumer="report", check_ids=[...])` | New RAG call |
| 4 | Parse ReportBundle | Extract `primary_topics`, `key_findings`, `control_themes`, `recommended_practices` | Parsing logic |
| 5 | Merge vào report_context | Thêm fields: `compliance_assessment`, `maturity_evaluation`, `rag_recommendations` | Enriched context |
| 6 | Cập nhật markdown template | Thêm sections: `## Compliance Assessment`, `## Maturity Evaluation` | Template updated |
| 7 | Fallback | Nếu RAG unavailable → generate report không có compliance/maturity sections (omit sections) | Graceful degradation |

### Luồng dữ liệu mới

```
ReportAgent.run(report_context, state)
  │
  ├─ Extract unique check_ids từ report_context["findings"]
  │
  ├─ [NEW] if self.rag_client and state.get("rag_available"):
  │     rag_data = self.rag_client.build_context(
  │         consumer="report",
  │         check_ids=unique_check_ids,
  │         include_mappings=True,
  │         include_maturity=True
  │     )
  │     │
  │     ├─ Success → ReportBundle:
  │     │   - primary_topics: ["Data Protection", "Access Control"]
  │     │   - key_findings: [{summary, severity}]
  │     │   - control_themes: [{capability, domain, guidance}]
  │     │   - recommended_practices: [str]
  │     │
  │     └─ Fail → rag_data = None
  │
  ├─ Merge:
  │   report_context["compliance_assessment"] = rag_data.control_themes
  │   report_context["maturity_evaluation"] = rag_data.recommended_practices
  │   report_context["primary_topics"] = rag_data.primary_topics
  │
  ├─ LLM generate report (enriched)
  │   - Executive Summary ← enriched with primary_topics
  │   - ★ Compliance Assessment ← NEW section
  │   - ★ Maturity Evaluation ← NEW section
  │   - Remediation Results (existing)
  │   - Recommendations ← enriched with best practices
  │
  └─ Export: MD → HTML → PDF
```

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Source code | `report_agent.py`, `agents/report_module/template_markdown.py`, `graph_orchestator.py` | Files cần sửa |
| Tài liệu | RAG ReportBundle format tại `RAG/app/core/models.py` | Verify field names |
| Dependency | SLICE-0.2 (`RAGClient`) | Phải hoàn thành trước |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | ReportAgent nhận `rag_client` qua constructor | MUST |
| 2 | `run()` gọi `build_context(consumer="report")` khi RAG available | MUST |
| 3 | Generated report có section "Compliance Assessment" khi RAG data available | MUST |
| 4 | Generated report có section "Maturity Evaluation" khi RAG data available | SHOULD |
| 5 | Report generate thành công khi RAG unavailable (sections omitted gracefully) | MUST |
| 6 | MD, HTML, PDF đều render đúng với new sections | MUST |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| ReportBundle data quá lớn → report quá dài | Trung bình | Thấp | Limit: top 10 control_themes, top 5 recommended_practices |
| Jinja2 template break khi thêm new sections | Thấp | Trung bình | Test template rendering riêng trước khi integrate |
| Non-S3 services có mapping chất lượng thấp → compliance section misleading | Cao | Cao | Thêm caveat: "Compliance data available for S3 only. Other services pending curation." |

---

## SLICE 5.1 — Unit Tests cho RAGClient

**Ticket:** `SLICE-5.1`
**Phase:** 5 — Testing
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P0 (Bắt buộc)
**Dependency:** SLICE-0.2
**Tham chiếu:** Phase 5 (task 5.1) trong Integration_Analysis_Report.md § 8.7

### Mục tiêu

Viết unit tests cho `RAGClient` class, mock HTTP calls, verify error handling và response parsing.

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Tạo test file | `tests/test_rag_client.py` | New file |
| 2 | Test `is_healthy()` | Mock `GET /ready` → assert True. Mock timeout → assert False | 2 test cases |
| 3 | Test `retrieve_checks()` | Mock success response → verify parsed output. Mock 500 → verify retry + return None | 3 test cases |
| 4 | Test `build_context()` | Mock success → verify bundle parsing per consumer type (planning, risk, report) | 3 test cases |
| 5 | Test timeout & retry | Mock timeout → verify retry happens → verify final return None | 2 test cases |
| 6 | Test `resolve_mapping()` | Mock success → verify output | 1 test case |

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Library | `pytest`, `unittest.mock` (hoặc `responses` library) | Mock HTTP calls |
| Source code | `agents/shared/rag_client.py` | Module under test |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | Tối thiểu 10 test cases covering tất cả 5 public methods | MUST |
| 2 | Test coverage ≥ 90% cho `rag_client.py` | SHOULD |
| 3 | Tất cả tests pass | MUST |
| 4 | Tests chạy offline (không cần RAG service running) | MUST |
| 5 | Error handling paths (timeout, 500, parse error) đều được test | MUST |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| Mock response format lệch với actual API → tests pass nhưng production fail | Trung bình | Cao | Capture actual API responses làm fixture data |

---

## SLICE 5.2 — Integration Tests per Agent

**Ticket:** `SLICE-5.2`
**Phase:** 5 — Testing
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P1 (Nên làm)
**Dependency:** SLICE-1.1, 1.2, 2.1, 3.1, 4.1 (tất cả agent slices)
**Tham chiếu:** Phase 5 (tasks 5.2-5.5) trong Integration_Analysis_Report.md § 8.7

### Mục tiêu

Test từng agent individually với **RAG service đang chạy** (integration test, không mock). Verify rằng mỗi agent nhận đúng data từ RAG và produce đúng output.

### Các bước thực hiện

| # | Bước | Chi tiết | Output |
|---|---|---|---|
| 1 | Test PlanningAgent + RAG | Input: "check S3 public access" → Verify output chứa `s3_bucket_public_access` hoặc tương tự | 1 test |
| 2 | Test RiskAgent + RAG | Input: normalized FAIL findings (S3) → Verify `rag_context` có compliance mappings | 1 test |
| 3 | Test RemediationPlanner + RAG | Input: enriched finding → Verify LLM prompt chứa RAG remediation context | 1 test |
| 4 | Test ReportAgent + RAG | Input: report_context → Verify output report chứa "Compliance Assessment" section | 1 test |
| 5 | Test tất cả agents khi RAG down | Stop RAG → chạy mỗi agent → Verify output (degraded) không crash | 4 tests |

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Infrastructure | RAG service running (port 8001) | Required for integration tests |
| Infrastructure | Ollama running (port 11434) | Required for agents using LLM |
| Test data | Sample S3 findings (normalized format) | Có thể lấy từ `data/post_scan.json` |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | PlanningAgent: check_ids output phù hợp với query | MUST |
| 2 | RiskAgent: compliance field non-empty cho S3 checks | MUST |
| 3 | RemediationPlanner: tool selection hợp lý | MUST |
| 4 | ReportAgent: report chứa compliance sections | MUST |
| 5 | Degraded mode: tất cả agents complete without crash khi RAG down | MUST |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| RAG service không start được trong CI → tests fail | Trung bình | Trung bình | Mark integration tests với `@pytest.mark.integration`, skip trong CI nếu cần |
| LLM output non-deterministic → flaky tests | Cao | Trung bình | Assert on structure (fields exist) chứ không assert exact values |

---

## SLICE 5.3 — End-to-End & Degraded Mode Tests

**Ticket:** `SLICE-5.3`
**Phase:** 5 — Testing
**Trạng thái:** `NOT_STARTED`
**Ưu tiên:** P0 (Bắt buộc)
**Dependency:** SLICE-5.2
**Tham chiếu:** Phase 5 (tasks 5.6-5.9) trong Integration_Analysis_Report.md § 8.7

### Mục tiêu

Chạy **full PDCA pipeline** end-to-end với RAG enabled và disabled. Verify toàn bộ flow hoàn thành, report được generate, và latency overhead chấp nhận được.

### Các bước thực hiện

| # | Bước | Chi tiết | Pass Criteria |
|---|---|---|---|
| 1 | E2E: Full pipeline (RAG on) | Chạy `graph_orchestator.py` với request "check s3 group". RAG + Ollama + Scanner đều running | Pipeline completes. Report generated (MD + HTML + PDF) |
| 2 | E2E: Degraded mode (RAG off) | Stop RAG service → Chạy cùng request | Pipeline completes. Report generated (without compliance sections). Console shows "RAG Unavailable" warning |
| 3 | Performance baseline | Measure pipeline latency với RAG on vs off | RAG overhead ≤ 5 seconds total |
| 4 | S3 Scenario | Full S3 scan + risk eval + remediation + report | All agents produce valid output. Report has S3-specific compliance data |

### Tài nguyên cần thiết

| Loại | Tài nguyên | Ghi chú |
|---|---|---|
| Infrastructure | RAG (8001), Ollama (11434), Scanner/Prowler (8000) | All services |
| AWS | Valid AWS credentials (read-only sufficient for scan-only test) | Có trong `.env` |
| Time | ~5-10 minutes per full pipeline run | Account for LLM + scan latency |

### Tiêu chí hoàn thành

| # | Tiêu chí | Mức |
|---|---|---|
| 1 | Full pipeline completes without error (RAG on) | MUST |
| 2 | Full pipeline completes without error (RAG off — degraded) | MUST |
| 3 | Report generated successfully in cả 2 modes | MUST |
| 4 | RAG latency overhead ≤ 5s | SHOULD |
| 5 | S3 scenario: compliance data present in report | MUST |
| 6 | Console output: rõ ràng RAG status (Available/Unavailable) | SHOULD |

### Rủi ro & Mitigation

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| AWS credentials expired → scan fails | Trung bình | Cao | Verify credentials trước khi chạy E2E |
| Full pipeline run quá lâu → timeout | Trung bình | Trung bình | Set generous timeout (15 minutes). Có thể dùng mock scanner cho faster E2E |

---

## DEPENDENCY MAP & EXECUTION ORDER

### Dependency Graph

```
SLICE-0.1 (Config) ──→ SLICE-0.2 (RAGClient) ─┬──→ SLICE-5.1 (Unit Tests RAGClient)
    │                                           │
    └──→ SLICE-0.3 (Health Check)               ├──→ SLICE-1.1 (Planning/RAGClient)
                                                │         └──→ SLICE-1.2 (Planning/Bundle)
SLICE-0.4 (Cleanup) ──→ (independent)          │
                                                ├──→ SLICE-2.1 (Risk/RAGClient)
                                                │         └──→ SLICE-2.2 (Risk/Batch)
SLICE-RS-1 (Shared Utils) ──┬──→ SLICE-RS-2 (PlanningAgent Refactor) ──┐
     (no dependency)        │                                           ├──→ SLICE-RS-4 (Orchestrator)
                            └──→ SLICE-RS-3 (RiskAgent Refactor) ──────┘
                                                │
                                                ├──→ SLICE-3.1 (Remediation/RAG)
                                                │
                                                └──→ SLICE-4.1 (Report/RAG)

DEPENDENCY CONSTRAINTS:
  SLICE-1.1 requires: 0.1 + 0.2 + RS-2
  SLICE-2.1 requires: 0.1 + 0.2 + RS-3
  SLICE-5.2 requires: 1.1, 1.2, 2.1, 3.1, 4.1
  SLICE-5.3 requires: 5.2
```

### Execution Order khuyến nghị

| Sprint | Slices | Có thể song song? | Ước tính effort |
|---|---|---|---|
| **Sprint 1** | 0.1 → 0.2 → 0.3 | Tuần tự (dependency chain) | Nhỏ-Trung bình |
| **Sprint 1** | 0.4 | Song song với 0.1-0.3 | Nhỏ |
| **Sprint 1** | RS-1 → RS-2, RS-3 (song song) → RS-4 | **Song song với Phase 0** | Trung bình |
| **Sprint 2** | 1.1, 2.1 | Song song (depend 0.2 + RS-2/RS-3) | Trung bình |
| **Sprint 2** | 5.1 | Song song với 1.1, 2.1 | Nhỏ |
| **Sprint 3** | 1.2, 2.2, 3.1, 4.1 | Song song (independent) | Trung bình-Lớn |
| **Sprint 4** | 5.2 → 5.3 | Tuần tự | Trung bình |

### Critical Path

```
               ┌─ 0.1 → 0.2 ─┐
               │              ├──→ 1.1 → 1.2 ──→ 5.2 → 5.3
RS-1 → RS-2 ──┘              │                    ↑
RS-1 → RS-3 ──→ 2.1 ─────────┘    3.1, 4.1 ──────┘
```

**Hai track song song** hội tụ tại Sprint 2:
- Track A: Phase 0 (0.1 → 0.2)
- Track B: Phase RS (RS-1 → RS-2/RS-3)
- Cả 2 phải xong trước khi bắt đầu 1.1 / 2.1

---

## TỔNG HỢP RỦI RO & MITIGATION

### Rủi ro Level Hệ thống

| # | Rủi ro | Xác suất | Ảnh hưởng | Slices liên quan | Mitigation |
|---|---|---|---|---|---|
| R1 | RAG service down giữa pipeline → agent fail | Trung bình | Cao | Tất cả | RAGClient return None + agent fallback (SLICE-0.2, 0.3) |
| R2 | Non-S3 mapping quality thấp → compliance data sai | Cao | Cao | 3.1, 4.1 | Scope giới hạn S3 trước. Thêm caveat trong report |
| R3 | Latency tích lũy: 4 agents × 10s timeout = +40s | Trung bình | Trung bình | 1.2, 2.2, 3.1, 4.1 | Caching (2.2), batch (2.2), health check skip (0.3) |
| R4 | Constructor signature change → break orchestrator | Cao | Trung bình | RS-2, RS-3, RS-4, 1.1, 2.1 | Keyword args với defaults, backward compatible. RS-4 verify wiring |
| R5 | LLM prompt quá dài sau thêm RAG context → truncation/error | Trung bình | Cao | 1.2, 3.1 | Truncate RAG context, limit tokens |
| R6 | RAGClient response format lệch API thực tế | Trung bình | Cao | 0.2 | Capture actual API responses làm reference. Integration tests (5.2) |
| R7 | Refactor thay đổi behavior → regression | Trung bình | Cao | RS-2, RS-3 | Test cùng input trước/sau refactor, compare output |
| R8 | LLM output validation quá strict → reject valid responses | Trung bình | Trung bình | RS-3 | Log rejected fields ở DEBUG, sensible defaults |
| R9 | Re-ranking quality giảm sau đổi prompt format | Thấp | Cao | RS-2 | A/B test: cùng query, compare check selection |

### Mitigation tổng quát (áp dụng cho tất cả slices)

1. **Defense in depth:** Mỗi agent có try-except riêng, bất kể RAGClient đã handle errors
2. **Backward compatibility:** Mọi thay đổi constructor đều dùng keyword args với default `None`
3. **Incremental rollout:** S3 service trước, mở rộng service khác sau khi mapping quality đạt yêu cầu
4. **Smoke test sau mỗi slice:** Chạy pipeline nhanh (dry run) để verify không break existing functionality

---

## CHECKLIST TỔNG HỢP

### Phase 0 — Foundation

| Slice | Mô tả | Priority | Status |
|---|---|---|---|
| 0.1 | Centralized Configuration | P0 | `NOT_STARTED` |
| 0.2 | RAGClient Class | P0 | `NOT_STARTED` |
| 0.3 | RAG Health Check | P0 | `NOT_STARTED` |
| 0.4 | Cleanup Old Endpoints | P0 | `NOT_STARTED` |

### Phase RS — Agent Refactor (Code Quality & Data Flow)

| Slice | Mô tả | Priority | Status | Giải quyết issues |
|---|---|---|---|---|
| RS-1 | Shared Utilities (`extract_check_id`, `parse_llm_json`, `sanitize_check_id`) | P0 | `NOT_STARTED` | PA-04, RA-01, RA-02 |
| RS-2 | PlanningAgent: tách `run()`, giữ metadata re-ranking, fix silent S3 default | P0 | `NOT_STARTED` | PA-03, PA-05, PA-06, PA-07 |
| RS-3 | RiskAgent: dùng `event_code`, validate LLM output, fix empty fields, fix prompt | P0 | `NOT_STARTED` | RA-02, RA-04, RA-06, RA-07, RA-08 |
| RS-4 | Orchestrator: xóa dead code, verify wiring sau refactor | P0 | `NOT_STARTED` | PA-02, PA-08 |

### Phase 1-4 — RAG Integration

| Slice | Mô tả | Priority | Status |
|---|---|---|---|
| 1.1 | PlanningAgent → RAGClient | P0 | `NOT_STARTED` |
| 1.2 | PlanningAgent → PlanningBundle | P1 | `NOT_STARTED` |
| 2.1 | RiskAgent → RAGClient | P0 | `NOT_STARTED` |
| 2.2 | RiskAgent Batch & Confidence | P1 | `NOT_STARTED` |
| 3.1 | RemediationPlanner + RAG | P1 | `NOT_STARTED` |
| 4.1 | ReportAgent + RAG | P1 | `NOT_STARTED` |

### Phase 5 — Testing

| Slice | Mô tả | Priority | Status |
|---|---|---|---|
| 5.1 | Unit Tests RAGClient | P0 | `NOT_STARTED` |
| 5.2 | Integration Tests per Agent | P1 | `NOT_STARTED` |
| 5.3 | E2E & Degraded Mode Tests | P0 | `NOT_STARTED` |

**Tổng: 17 slices** — 10 P0 (bắt buộc) + 7 P1 (nên làm)

---

*Tài liệu này được tạo dựa trên [Integration_Analysis_Report.md](Integration_Analysis_Report.md), [Agent_Refactor_Plan.md](Agent_Refactor_Plan.md), và phân tích trực tiếp source code. Cập nhật trạng thái của mỗi slice khi implement.*
