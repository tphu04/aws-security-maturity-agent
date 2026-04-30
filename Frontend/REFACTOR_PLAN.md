# PDCA Refactor Plan — Agents & LangGraph

**Mục tiêu**: Làm sạch kiến trúc agents và LangGraph graph hiện tại, fix bugs, đạt chuẩn thiết kế đủ điều kiện để tích hợp Langfuse và xây dựng Chatbot UI sau này.

**Scope**: `pdca/agents/`, `pdca/graph/` (mới), `pdca/orchestrator.py`, `pdca/state.py`, `pdca/config/` (package mới — thay file cũ), `pdca/api_server.py`, `pdca/tools/` (package mới — thay file cũ — v1.6), `RAG/app/` (minor)

**Không trong scope hiện tại**: Chatbot UI (pdca/api/), Langfuse integration (chuẩn bị hook, chưa implement)

**Tác giả**: Phu
**Trạng thái**: Active — v1.7 (review polish: D1 reference tools/ package, ToolMeta.aliases removed, return-dict invariant fixed, sanitize→S3-specific, ExecutionAgent 3-guard, B18 rationale corrected)
**Cập nhật**: 2026-04-26

---

## Pre-implement Reconciliation (BẮT BUỘC làm trước Phase A)

> Đây là các bước reconcile state hiện tại của repo với plan. **Skip → plan sẽ conflict với working tree.**

### R1 — Resolve uncommitted changes

`git status` cho thấy 20 file dirty + 30+ file mới chưa commit (RAG/, pdca/, tests/, benchmarks/...).

- [ ] Xác định file nào là WIP có giá trị, file nào là experiment cần discard
- [ ] Commit hoặc stash riêng các thay đổi RAG/ (`RAG/app/api/routes/retrieve.py`, `RAG/app/core/models.py`, `RAG/app/main.py`, `RAG/app/services/report_context_service.py`...) **trước khi** chạy Phase D4 (CORS) để tránh merge conflict
- [ ] Commit hoặc discard `pdca/agents/report_module/rag_query_planner.py` (xem R3)
- [ ] Quyết định fate của các plan documents khác (xem R2)

### R2 — Reconcile multiple plan documents

Hiện có 3 plan markdown untracked cùng tồn tại:

| File | Status | Action |
|---|---|---|
| `REFACTOR_PLAN.md` (file này) | Canonical — Active | Giữ |
| `PRODUCTION_READINESS_PLAN.md` | Untracked | Review overlap, merge phần còn relevant vào file này hoặc archive |
| `REPORT_AGENT_IMPROVEMENT_PLAN.md` | Untracked | Review overlap, archive nếu đã được hoàn thành qua các commit gần đây |

- [ ] Đọc lướt 2 plan kia, đánh dấu phần nào đã done / đã obsolete / cần merge vào REFACTOR_PLAN
- [ ] Archive/delete để chỉ còn 1 source of truth

### R3 — Existing `rag_query_planner.py` đã có sẵn

`pdca/agents/report_module/rag_query_planner.py` (uncommitted, ~177 dòng) **đã implement**:
- `RAGQueryPlanner.plan(findings, scope_domains)` — dedup check_ids + severity_map + domains
- `RAGQueryPlanner.execute(req)` — gọi `client.build_report_context()` cho multi-query mode
- `RAGQueryPlanner.execute_legacy(check_ids)` — gọi `client.build_context()` cho single-query mode

**Implication cho B12**: KHÔNG move `_fetch_rag_for_report()` thô vào `data_builder.py` như plan v1.2 mô tả. Thay vào đó:
- `ReportDataBuilder` orchestrate: scope → call `RAGQueryPlanner` → assemble bundle
- `_fetch_rag_for_report()` và `_fetch_rag_multi_query()` ở orchestrator sẽ XÓA (logic đã sống trong `RAGQueryPlanner`)

- [ ] Commit `rag_query_planner.py` trước khi bắt đầu Phase B12
- [ ] Re-read plan B12 (đã rewrite ở v1.3) để phù hợp với reality

### R4 — Dead code phát hiện trong codebase

Verify với grep: `tools_maker.py` (`ToolMakerAgent`) chỉ được reference ở `PRODUCTION_READINESS_PLAN.md` — **0 import trong code**. Tương tự `assessment_agent.py` — chỉ ở docs, 0 import.

- [ ] Confirm bằng grep ngay trước khi bắt đầu Phase B (nhỡ codebase thay đổi)
- [ ] Plan đã update: B11 xóa `assessment_agent.py`, thêm B13 xóa `tools_maker.py` (xem bên dưới)

---

## Quyết định kiến trúc đã chốt

| # | Quyết định | Lý do |
|---|---|---|
| 1 | LangGraph là engine duy nhất — không có "legacy engine" | Đã là LangGraph, không cần migrate |
| 2 | **Scan: INLINE nodes trong main graph** (không subgraph) — `scan_submit → scan_poll ⇄ scan_poll → scan_collect` | v1.3 đã định subgraph nhưng `subgraph.invoke()` đồng bộ KHÔNG checkpoint per iteration. Inline nodes mới đạt mục tiêu "1 checkpoint/poll" mà plan yêu cầu |
| 3 | **Report Subgraph: KHÔNG** | Chỉ có giá trị khi làm fan-out section song song — chưa cần |
| 4 | **Risk Eval Fan-out: KHÔNG** (với Ollama local) | Ollama concurrency = 1-2, fan-out không demonstrate được speed gain |
| 5 | State: giữ TypedDict, thêm Pydantic chỉ tại LLM output boundary | Migration toàn bộ quá tốn công, không đủ ROI |
| 6 | Checkpointer: MemorySaver → **SqliteSaver** | Prerequisite cho Chatbot UI (session survive restart) |
| 7 | `TimerCallback`: gom về `shared/callbacks.py` | Sau này swap 1 nơi sang Langfuse handler |
| 8 | `BaseAgent`: bỏ dual init (OpenAI + ChatOllama) | Mỗi agent chỉ dùng 1 loại client |
| 9 | File-based coupling: loại bỏ | Pass data qua LangGraph state, không qua filesystem |
| 10 | Mọi node nhận `config: RunnableConfig` | Chuẩn LangGraph — Langfuse inject qua đây sau này |
| 11 | `run_id` trong PDCAState từ đầu | = Langfuse trace_id về sau |
| 12 | Không dùng `print()`, `input()` trong graph code | Prerequisite cho web server model (chatbot UI) |
| 13 | Scanner API: GET → **POST** cho tạo job | GET không có side effect — tạo job là side effect |
| 14 | Scanner API: thêm `/v1/` prefix | Nhất quán với RAG API, dễ version sau này |
| 15 | Scanner job database: **SQLite** thay in-memory dict | In-memory mất hết khi restart — blocking khi có HITL dài |
| 16 | Thêm **CORS** cho cả hai API | Prerequisite cho browser-based chatbot UI |
| 17 | `RAG_API_URL` default: `8000` → **`8005`** | Bug: RAG chạy port 8005, config sai dẫn đến kết nối lỗi |
| 18 | `pdca/tools.py`: URL hardcoded → dùng `settings` | Nhất quán, configurable qua `.env` |
| 19 | `RAGQueryPlanner` đã có sẵn — **REUSE**, không tạo mới | `pdca/agents/report_module/rag_query_planner.py` đã implement đủ legacy + multi-query path |
| 20 | `monitoring_agent.py` → **DELETE** sau Phase C5 | Logic poll đã chuyển sang inline node `scan_poll` — file thành dead code |
| 21 | `assessment_agent.py` + `tools_maker.py` → **DELETE** ở Phase B | Verified 0 import — không deprecate, xóa luôn |
| 22 | Scan state `pending_jobs`: dùng **dict**, KHÔNG dùng `Set` | Set không JSON-serializable → break SqliteSaver checkpoint + Chatbot UI streaming |
| 23 | `SqliteSaver` factory: dùng `sqlite3.connect()` + `SqliteSaver(conn)`, KHÔNG dùng `.from_conn_string()` | `from_conn_string()` trả context manager — không phù hợp factory pattern |
| 24 | `pdca/config.py` (file) → **`pdca/config/`** (package thật) | File + package cùng tên không cohabit được trong Python — plan v1.3 viết "tạo `config/settings.py` + sửa `config.py`" sẽ fail import |
| 25 | Tách `raw_findings` (accumulate) vs `normalized_findings` (set once) trong scan state | `Annotated[List, operator.add]` reducer = append, KHÔNG replace. Ghi normalized vào cùng field gây bug `[raw1, raw2, ..., normalized_packet]` |
| 26 | `time.sleep()` trong `scan_poll` chấp nhận tạm — đánh dấu **tech debt cho Phase E** (async migration) | Block worker thread trong web server nhưng plan này không in scope cho async/Chatbot UI |
| 27 | `scan_started_at` dùng **`time.time()`** (Unix epoch), KHÔNG `time.monotonic()` | Monotonic là process-local — sau restart resume từ SqliteSaver, monotonic của process mới khác epoch → timeout check vô nghĩa. Wall-clock survive restart. NTP jitter ±vài giây không ảnh hưởng timeout 300s |
| 28 | `raw_findings` **KHÔNG** dùng `Annotated[..., operator.add]` reducer — explicit append trong scan_poll | Reducer = append, không reset. `scan_submit` không thể clear. Explicit `state.get("raw_findings", []) + new_raw` cho semantic nhất quán với `pending_jobs/completed_jobs` (đều no-reducer) |
| 29 | `pydantic-settings` package: thêm vào `requirements.txt` + import explicit | Pydantic v2 tách `BaseSettings` ra package riêng. Thiếu sẽ `ImportError` ngay khi load settings.py |
| 30 | Pydantic field `ollama_base_url` dùng `AliasChoices("OLLAMA_BASE_URL", "OLLAMA_URL")` | Code cũ dùng env var `OLLAMA_URL`. Field name mới map sang `OLLAMA_BASE_URL`. Không alias → silent regression cho user upgrade |
| 31 | Callbacks đọc từ `config["callbacks"]` (chuẩn LangChain) **VÀ** fallback `config["configurable"]["callbacks"]` | Langfuse dùng pattern chuẩn `config={"callbacks": [handler]}`. Plan v1.4 chỉ check `configurable` → Langfuse silent broken |
| 32 | CORS: cấm combo `allow_origins=["*"]` + `allow_credentials=True` | Vi phạm CORS spec — browser luôn block. Settings tự validate: `["*"]` ép `credentials=False` |
| 33 | `pdca/tools.py` (file 950 dòng) → **`pdca/tools/`** (package, tách theo concern: scanner, knowledge, remediation/s3) | Monolithic file gom HTTP scanner + boto3 remediation + RAG knowledge + 4 export list. Mỗi loại có dependency khác hẳn. Tách để scale (sau này thêm `iam.py`, `ec2.py`) và để test isolated |
| 34 | **`ToolRegistry`** singleton thay 4 export lists (`AVAILABLE_FUNCTIONS`, `SCANNER_AGENT_TOOLS`, `REMEDIATION_TOOLS`, `ALL_TOOLS`) + `TOOLS_MAP` | Hiện 4 list overlap, naming mâu thuẫn (key `remediate_*` alias trong `AVAILABLE_FUNCTIONS` ≠ tool.name thật). Registry: 1 nguồn duy nhất, metadata-rich (category, manual_only), `get_for(category)` & `get_by_name()` — loại bỏ `ALWAYS_MANUAL_TOOLS` set rời rạc trong remediate_planner_agent.py |
| 35 | Mọi `@tool` function **return `dict`** — KHÔNG `json.dumps()` | Hiện mixed: vài tool return dict, vài tool return JSON string. ExecutionAgent có `parse_tool_output()` patch nhưng root cause là tool tự bất nhất. Chuẩn hóa giúp LLM tool-calling nhất quán + bỏ JSON parsing thừa |
| 36 | Plan output dùng key **`tool_name`**, KHÔNG `tool_id` | Hiện `remediate_planner_agent.plan_remediation()` trả `{"tool_id": ...}` nhưng `state.RemediationTask.tool_name` + `execution_agent` đọc `task["tool_name"]`. Orchestrator phải dịch `plan["tool_id"] → "tool_name"` ([orchestrator.py:313-314](pdca/orchestrator.py#L313-L314)) — bug-magnet. Đổi planner trả thẳng `tool_name`, xóa dịch ở orchestrator |
| 37 | `ScannerAgent.ALLOWED_GROUPS` (hardcode 9 services) → `settings.scanner_allowed_services` (default toàn bộ Prowler-supported) + xóa `ALLOWED_GROUPS_LIST` (84 services, 0 import) | Whitelist nằm trong agent class khó override. `ALLOWED_GROUPS_LIST` ở `tools.py` là dead config — đã build sẵn nhưng không ai import. Move sang settings để vừa configurable vừa chỉ giữ 1 nguồn |

---

## Kiến trúc Target

```
pdca/
├── config/
│   └── settings.py          ← Pydantic BaseSettings (thay config.py đơn giản)
│
├── api_server.py            ← Scanner/Prowler API (refactored: POST, /v1/, SQLite jobs)
│
├── observability/
│   └── logger.py            ← JSON logger + run_id context var
│
├── tools/                   ← MỚI v1.6: package thay file tools.py monolithic
│   ├── __init__.py          ← public API: REGISTRY, get_tools_for(), TOOLS_MAP shim (backward compat)
│   ├── registry.py          ← ToolRegistry singleton + ToolMeta metadata
│   ├── schemas.py           ← Pydantic input schemas (ScanGroupInput, JobStatusInput, ScanChecksInput)
│   ├── _common.py           ← ToolResult helpers + sanitize_s3_bucket_name (T10, v1.7)
│   ├── scanner.py           ← 4 scanner tools — HTTP client (settings.scanner_api_url)
│   ├── knowledge.py         ← 1 RAG lookup tool (settings.rag_api_url)
│   └── remediation/
│       ├── __init__.py
│       └── s3.py            ← 13 S3 tools (đã chuẩn hóa return dict, fix T7 bug, sanitize T10)
│       (Tương lai: iam.py, ec2.py, rds.py, ... — mỗi service 1 file)
│
├── agents/                  ← Pure business logic, không biết LangGraph
│   ├── base_agent.py        ← Refactored: bỏ dual init
│   ├── environment_agent.py
│   ├── planning_agent.py
│   ├── scanner_agent.py
│   ├── monitoring_agent.py
│   ├── rescan_agent.py
│   ├── risk_evaluation_agent.py
│   ├── remediate_planner_agent.py
│   ├── execution_agent.py
│   ├── analysis_agent.py
│   ├── report_agent.py
│   ├── report_module/
│   │   ├── data_builder.py  ← MỚI: extract từ orchestrator
│   │   └── ... (giữ nguyên các file khác)
│   └── shared/
│       ├── callbacks.py     ← MỚI: TimerCallback dùng chung
│       ├── rag_client.py    ← giữ nguyên (đã tốt)
│       ├── normalizer.py
│       └── utils.py
│
├── graph/                   ← MỚI: LangGraph layer
│   ├── __init__.py
│   ├── state.py             ← move + mở rộng từ pdca/state.py (thêm scan accumulator fields)
│   ├── graph.py             ← build_graph() thuần topology
│   ├── checkpointer.py      ← SqliteSaver factory
│   ├── routing.py           ← routing functions (read-only) — bao gồm route_scan_poll
│   └── nodes/               ← mỗi file = 1 node function (thin wrapper)
│       ├── __init__.py
│       ├── environment.py
│       ├── planning.py
│       ├── scan_submit.py   ← submit jobs lên scanner API
│       ├── scan_poll.py     ← poll 1 lần, accumulate raw_findings (LOOP qua conditional edge)
│       ├── scan_collect.py  ← normalize raw → normalized_findings (set once)
│       ├── risk_eval.py
│       ├── remediation.py
│       ├── review_task.py
│       ├── reset_index.py
│       ├── execution.py
│       ├── verification.py
│       └── report.py
│       (KHÔNG còn subgraphs/ — xem decision #2 v1.4)
│
└── orchestrator.py          ← Giữ lại như thin wrapper gọi graph.py
                                (backward compat, xóa sau)
```

### Graph Topology sau refactor

```
START
  │
  ▼
environment ──────────────────────────────────────────────────┐
  │                                                            │
  ▼                                                            │ (parallel
planning                                                       │  tương lai)
  │
  ▼
scan_submit
  │
  ▼
scan_poll ◄────────── (still pending) ──────┐
  │                                          │
  │                                          │  (mỗi vòng = 1 checkpoint
  ├──── (all done / timeout) ──────►         │   của parent SqliteSaver)
  ▼                                          │
scan_collect                                 │
  │                                          │
  │                              route_scan_poll
  │
  ▼
risk_evaluation
  │
  ├─── (có FAIL findings) ──►  operational_planning
  │                                    │
  │                                    ▼
  │                            review_task ◄──────┐
  │                                    │           │ (HITL loop)
  │                                    ▼           │
  │                            route_review  ──────┘
  │                                    │
  │                            reset_index_node
  │                                    │
  │                                    ▼
  │                                execution
  │                                    │
  │                                    ▼
  │                              verification
  │                                    │
  └─── (không FAIL) ──────────────►  report
                                        │
                                       END
```

---

## Hooks chuẩn bị cho Langfuse & Chatbot UI

> Những điểm này phải có trong code NGAY BÂY GIỜ dù chưa implement Langfuse/UI

### Hook 1 — `config: RunnableConfig` trong mọi node

```python
# Mọi node function phải có signature này
def planning_node(state: PDCAState, config: RunnableConfig) -> dict:
    # FIX v1.5: chuẩn LangChain — top-level config["callbacks"], fallback configurable (decision #31)
    callbacks = (
        config.get("callbacks")
        or config.get("configurable", {}).get("callbacks", [])
        or []
    )
    # callbacks = [] bây giờ
    # callbacks = [LangfuseCallbackHandler(...)] khi tích hợp Langfuse
```

### Hook 2 — `run_id` trong state

```python
# PDCAState
run_id: str  # = thread_id của LangGraph = trace_id của Langfuse sau này
```

### Hook 3 — `callbacks` parameter trong agents có LLM

```python
# Agent constructors
class RiskEvaluationAgent(BaseAgent):
    def __init__(self, ..., callbacks: list = None):
        self.callbacks = callbacks or []
        self.llm = ChatOllama(..., callbacks=[self.timer] + self.callbacks)
        #                                     ^^^^^^^^^^^   ^^^^^^^^^^^^^
        #                                     local timer   Langfuse sau này
```

### Hook 4 — Python `logging`, không `print()`

```python
# Thay vì print(f"[Node] doing X...")
logger = logging.getLogger(__name__)
logger.info("doing X", extra={"run_id": state.get("run_id", "")})
```

### Hook 5 — `get_checkpointer(mode)` factory

```python
# Chatbot UI cần SqliteSaver để session survive HTTP requests
# Test cần MemorySaver để chạy không cần file
checkpointer = get_checkpointer(mode="sqlite")  # prod
checkpointer = get_checkpointer(mode="memory")  # test
```

---

## Phase A — Foundation & Bug Fixes

> **Ưu tiên cao nhất.** Đây là những thay đổi độc lập, không phụ thuộc vào nhau.
> Hoàn thành Phase A trước khi làm bất cứ thứ gì khác.

### A1 — `pdca/agents/shared/callbacks.py` *(file mới)*

**Mục đích**: Gom `TimerCallback` đang duplicate ở 3 files về 1 nơi. Đây là điểm swap sang Langfuse handler về sau.

- [ ] Tạo `pdca/agents/shared/callbacks.py`
- [ ] Di chuyển `TimerCallback(BaseCallbackHandler)` vào đây
- [ ] Thêm factory `get_callbacks(extra: list = None) -> list` trả `[TimerCallback()] + (extra or [])`
- [ ] Xóa `class TimerCallback` local khỏi `scanner_agent.py`, `risk_evaluation_agent.py`, `remediate_planner_agent.py`
- [ ] Cập nhật imports trong 3 file trên

**Langfuse hook**: Sau này `get_callbacks(extra=[langfuse_handler])` — chỉ sửa 1 dòng.

**Exit**: Import `from pdca.agents.shared.callbacks import TimerCallback, get_callbacks` không lỗi.

---

### A2 — Convert `pdca/config.py` → `pdca/config/` package thật

> **Bug fix v1.4**: Plan v1.3 viết "tạo `pdca/config/settings.py`" + "sửa `pdca/config.py` cũ". Hai cái không cohabit được — Python không cho phép `pdca/config.py` (file) và `pdca/config/` (directory) cùng tồn tại. Phải xóa file cũ và convert thành package.

**Mục đích**: Thay `pdca/config.py` (raw `os.environ.get`) bằng Pydantic v2 `BaseSettings` có validation, đồng thời giữ backward compat cho code cũ đang `from pdca.config import RAG_API_URL`.

**Step-by-step (làm đúng thứ tự)**:

- [ ] **B1**. Xác định callers hiện tại: `grep -rn "from pdca.config\|import pdca.config" pdca/ tests/ benchmarks/ scripts/` — list tất cả import paths đang dùng (sẽ thấy `from pdca.config import RAG_API_URL`, `from pdca.config import OLLAMA_MODEL`, etc.)
- [ ] **B2**. `git rm pdca/config.py` — xóa file cũ trước khi tạo package (tránh conflict)
- [ ] **B3**. `mkdir pdca/config`
- [ ] **B4**. Tạo `pdca/config/settings.py` với class `Settings(BaseSettings)` (xem block code bên dưới)
- [ ] **B5**. Tạo `pdca/config/__init__.py` re-export (xem code bên dưới)
- [ ] **B6**. Verify: `python -c "from pdca.config import settings, RAG_API_URL, OLLAMA_MODEL; print(settings.rag_api_url, RAG_API_URL)"` — cả hai phải work, cùng giá trị
- [ ] **B7**. Verify import paths cũ không break: chạy `pytest tests/ -q --collect-only` (không cần execute, chỉ collect — sẽ fail import nếu broken)

**`pdca/config/settings.py`** (v1.5 — đã có imports đầy đủ + alias):

```python
"""Centralized config — Pydantic v2 BaseSettings.

NOTE: Yêu cầu `pydantic-settings>=2.0` trong requirements.txt (decision #29).
"""
from typing import Optional
from pydantic import Field, AliasChoices, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Service URLs
    rag_api_url: str = "http://localhost:8005"
    scanner_api_url: str = "http://127.0.0.1:8000"
    # OLLAMA_URL alias cho backward-compat với .env cũ (decision #30)
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias=AliasChoices("OLLAMA_BASE_URL", "OLLAMA_URL"),
    )
    ollama_model: str = "gemma3:4b"
    ollama_api_key: str = "ollama"

    # Timeouts & limits
    llm_timeout_s: float = 60.0
    rag_timeout_s: float = 10.0
    poll_max_iterations: int = 60
    poll_interval_s: float = 5.0
    poll_timeout_s: float = 300.0

    # Features
    multi_query_mode: bool = False

    # AWS (dùng cho api_server.py — Phase D)
    aws_profile: str = "default"
    aws_default_region: str = "us-east-1"

    # Scanner API behaviour (Phase D)
    cleanup_scan_output: bool = True
    # CORS — decision #32: cấm combo wildcard + credentials
    cors_origins: list[str] = ["*"]            # Dev: allow all; Prod: explicit list
    cors_allow_credentials: bool = False       # AUTO-OVERRIDE nếu cors_origins=["*"]

    # Langfuse (empty now — hook cho tương lai)
    langfuse_secret_key: Optional[str] = None
    langfuse_public_key: Optional[str] = None
    langfuse_host: str = "https://cloud.langfuse.com"

    @model_validator(mode="after")
    def _enforce_cors_spec(self) -> "Settings":
        """CORS spec: wildcard origins KHÔNG được kết hợp với credentials.
        Browser block request nếu vi phạm. Force credentials=False khi wildcard.
        """
        if "*" in self.cors_origins and self.cors_allow_credentials:
            import warnings
            warnings.warn(
                "cors_origins=['*'] không tương thích allow_credentials=True "
                "(CORS spec). Forcing cors_allow_credentials=False. "
                "Để bật credentials, set cors_origins thành explicit domain list."
            )
            object.__setattr__(self, "cors_allow_credentials", False)
        return self


settings = Settings()
```

**`pdca/config/__init__.py`** (backward-compat re-export):

```python
"""pdca.config — package facade.

Exposes:
- `settings`: canonical Pydantic BaseSettings instance (USE THIS for new code)
- Legacy module-level constants: kept for backward compat. Will be removed
  after Phase B/C khi tất cả callers đã migrate sang `settings.xxx`.
"""
from pdca.config.settings import settings

# --- Backward-compat constants (DO NOT add new ones here) ---
RAG_API_URL = settings.rag_api_url
SCANNER_API_URL = settings.scanner_api_url
OLLAMA_BASE_URL = settings.ollama_base_url
OLLAMA_MODEL = settings.ollama_model
OLLAMA_API_KEY = settings.ollama_api_key
MULTI_QUERY_MODE = settings.multi_query_mode

__all__ = [
    "settings",
    # Legacy
    "RAG_API_URL", "SCANNER_API_URL",
    "OLLAMA_BASE_URL", "OLLAMA_MODEL", "OLLAMA_API_KEY",
    "MULTI_QUERY_MODE",
]
```

- [ ] Cập nhật `orchestrator.py` và agents dần dần để dùng `settings.xxx` thay vì legacy constants. **Không bắt buộc trong Phase A** — backward compat đã giữ. Migration có thể làm song song với Phase B/C.
- [ ] **Sau khi tất cả Phase B/C/D xong**: grep còn caller nào dùng legacy constants không, nếu hết → xóa constants khỏi `__init__.py` (giữ chỉ `settings`).

**Exit**:
- `from pdca.config import settings` ✓
- `from pdca.config import RAG_API_URL` (backward compat) ✓
- `python -c "from pdca.config import settings; print(settings.ollama_model)"` in ra giá trị đúng
- `pytest tests/ -q --collect-only` không có ImportError mới

---

### A3 — `pdca/observability/logger.py` *(file mới)*

**Mục đích**: JSON structured logging với `run_id` context var — Langfuse correlation hook.

- [ ] Tạo `pdca/observability/__init__.py`
- [ ] Tạo `pdca/observability/logger.py`:

```python
import logging, json
from contextvars import ContextVar

_run_id_var: ContextVar[str] = ContextVar("run_id", default="")

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "run_id": _run_id_var.get(),
        }
        if hasattr(record, "__dict__"):
            for k, v in record.__dict__.items():
                if k not in ("msg", "args", "levelname", "name", "pathname",
                             "filename", "module", "exc_info", "exc_text",
                             "stack_info", "lineno", "funcName", "created",
                             "msecs", "relativeCreated", "thread",
                             "threadName", "processName", "process",
                             "message", "taskName"):
                    payload[k] = v
        return json.dumps(payload, ensure_ascii=False)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger

def set_run_id(run_id: str) -> None:
    _run_id_var.set(run_id)
```

**Exit**: `logger = get_logger("test"); logger.info("hello", extra={"node": "planning"})` in ra JSON có `run_id`, `level`, `msg`, `node`.

---

### A4 — Bug fix: `environment_agent.py` — missing `buckets` + crash on no credentials

> **Verify trước khi sửa**: Code hiện tại ([environment_agent.py:43-47](pdca/agents/environment_agent.py#L43-L47)) thu thập `bucket_names` ở dòng 29-34 nhưng KHÔNG include vào return dict. Try/except `NoCredentialsError` ĐÃ tồn tại (dòng 49-53) nhưng `raise Exception(...)` thay vì degrade. Action là **đổi behavior** chứ không phải thêm try/except mới.

- [ ] Thêm `"buckets": bucket_names` vào return dict của `get_aws_context()` (success branch)
- [ ] Đổi behavior của `except NoCredentialsError` block (đã tồn tại):
  - Bỏ `raise Exception(...)` → return `{"account_id": "unknown", "region": "us-east-1", "identity_arn": "unknown", "buckets": [], "_degraded": True}`
  - Đổi `print()` → `logger.warning(...)`
- [ ] Đổi behavior của `except ClientError` (dòng 55-57): cũng degrade thay vì raise
- [ ] Thay các `print()` còn lại (dòng 37, 50, 56, 60) → `logger.warning/info/error`
- [ ] Xóa các comment-out prints (dòng 35, 39-41) — dead code

**Exit**: `EnvironmentAgent().get_aws_context()` khi không có credentials trả dict với `_degraded=True`, không raise exception. Khi có credentials, return dict có key `buckets` (list).

---

### A5 — Bug fix: `monitoring_agent.py` + `rescan_agent.py` — infinite loop

**monitoring_agent.py**:
- [ ] Nhận `max_iterations: int = None` và `timeout_s: float = None` trong `__init__`
- [ ] Fallback về `settings.poll_max_iterations` và `settings.poll_timeout_s`
- [ ] Thêm `started_at = time.monotonic()` trước `while active_jobs:`
- [ ] Điều kiện thoát: `iteration >= max_iterations` hoặc `time.monotonic() - started_at > timeout_s`
- [ ] Khi timeout: raise `RuntimeError(f"Scan timeout: {len(active_jobs)} jobs vẫn pending sau {timeout_s}s")`
- [ ] Tách `time.sleep()` ra helper `_sleep(interval)` (để sau dễ swap sang async)

**rescan_agent.py**:
- [ ] `poll()`: thêm `max_iterations` và `timeout_s` giống trên
- [ ] `__init__`: nhận `config: dict = None` — nếu không None thì dùng thay vì đọc file
- [ ] `load_initial_config()`: giữ lại nhưng chỉ gọi khi `config=None` (backward compat)

**Exit**: Test với mock luôn trả "pending" → raise `RuntimeError` sau `max_iterations`.

---

### A6 — Bug fix: `orchestrator.py` — state mutation trong router (fix tạm)

> **Lưu ý**: Đây là fix tạm. Phase C sẽ xóa hoàn toàn `orchestrator.py` và chuyển sang `pdca/graph/`.

- [ ] Thêm `reset_index_node(state) -> dict` trả `{"current_task_index": 0}`
- [ ] Sửa `route_review_next_task`: xóa hai dòng `state["current_task_index"] = 0`
- [ ] Sửa routing map: `"reset_then_execute": "reset_index"` thay vì `"execution": "execution"`
- [ ] Thêm `wf.add_node("reset_index", reset_index_node)` vào `build_graph()`
- [ ] Thêm `wf.add_edge("reset_index", "execution")`
- [ ] Sửa `review_task_node`: trả `{}` (empty dict, không return field rác `_hitl_pause`)

**Exit**: HITL loop không còn mutate state dict local. `current_task_index` được reset đúng cách qua state update.

---

### Checkpoint Phase A

- [ ] `pytest tests/ -q` không có test nào bị break thêm so với trước
- [ ] `from pdca.agents.shared.callbacks import TimerCallback` ✓
- [ ] `from pdca.config.settings import settings` ✓
- [ ] `from pdca.observability.logger import get_logger` ✓
- [ ] `EnvironmentAgent().get_aws_context()` không crash khi thiếu credentials
- [ ] Orchestrator chạy được end-to-end với fixture mock

---

## Phase B — Agent Refactor

> Mỗi agent độc lập — có thể làm song song hoặc theo thứ tự tùy ý.
> Tất cả agents phải pass existing tests sau khi sửa.

### B1 — `base_agent.py` — Bỏ dual init

**Vấn đề**: Mỗi agent kế thừa `BaseAgent` đang init cả `openai.OpenAI` lẫn `ChatOllama`, dù mỗi agent chỉ dùng 1.

- [ ] `BaseAgent.__init__` chỉ lưu config metadata:

```python
class BaseAgent:
    def __init__(self, model_name: str, api_key: str, base_url: str,
                 callbacks: list = None):
        self.model_name = model_name
        self.api_key = api_key or "ollama"
        self.base_url = base_url
        self.callbacks = callbacks or []    # ← Langfuse hook
        # Không init LLM ở đây
```

- [ ] `call_llm()`: tạo `openai.OpenAI` client lazily (chỉ khi được gọi lần đầu, dùng `@cached_property` hoặc `if not hasattr`)
- [ ] Xóa `self.llm = ChatOllama(...)` khỏi `BaseAgent.__init__`
- [ ] Kiểm tra các subclass không bị break: `RiskEvaluationAgent`, `RemediationPlannerAgent`, `ScannerAgent` (đã không kế thừa sau B2)

**Exit**: `BaseAgent("gemma3:4b", "ollama", "http://localhost:11434")` không init ChatOllama. Import thành công.

---

### B2 — `scanner_agent.py` — Bỏ kế thừa BaseAgent + LLM init thừa

**Vấn đề**: `ScannerAgent` kế thừa `BaseAgent` nhưng `run_batch()` là pure HTTP calls, không gọi LLM.

- [ ] Bỏ `class ScannerAgent(BaseAgent):` → `class ScannerAgent:`
- [ ] Bỏ `super().__init__(...)` trong `__init__`
- [ ] Bỏ `self.lc_llm = ChatOllama(...)` và `print(f"[ScannerModule] Init LangChain...")`
- [ ] Bỏ `self.timer = TimerCallback()` và `get_llm_metrics()` (scanner không gọi LLM)
- [ ] `__init__` nhận `scanner_url: str = None` thay vì `model_name, api_key, base_url`:

```python
class ScannerAgent:
    def __init__(self, scanner_url: str = None):
        from pdca.config.settings import settings
        self.scanner_url = scanner_url or settings.scanner_api_url
        self.tools_map = {tool.name: tool for tool in SCANNER_AGENT_TOOLS}
```

- [ ] Cập nhật `scanning_node` trong orchestrator: `ScannerAgent()` thay vì `ScannerAgent(OLLAMA_MODEL, ...)`
- [ ] **Đổi return type của `run_batch()`** (yêu cầu từ C4):
  - Trước: `List[str]` (chỉ job_ids)
  - Sau: `List[Dict]` với shape `{"job_id": str, "task_type": "group"|"checks"|"custom", "task_value": str}` để `scan_submit_node` giữ context job vào `pending_jobs` dict
- [ ] Update tests gọi `run_batch()` để parse format mới

**Exit**: `ScannerAgent()` init xong không in gì ra, không connect Ollama. `run_batch(...)` trả list[dict] có đủ 3 keys.

---

### B3 — `risk_evaluation_agent.py` — Shared callbacks + Langfuse hook

- [ ] Xóa `class TimerCallback` local → `from pdca.agents.shared.callbacks import TimerCallback`
- [ ] Thêm `callbacks: list = None` vào `__init__` signature
- [ ] Lưu `self.callbacks = callbacks or []`
- [ ] `ChatOllama` init: `callbacks=[self.timer] + self.callbacks`
- [ ] Không thay đổi logic 2-pass scoring

**Exit**: `RiskEvaluationAgent(..., callbacks=[])` init thành công, `get_llm_metrics()` hoạt động bình thường.

---

### B4 — `remediate_planner_agent.py` — Shared callbacks + logging

- [ ] Xóa `class TimerCallback` local → import từ shared
- [ ] Thêm `callbacks: list = None` vào `__init__`
- [ ] `ChatOllama` init: `callbacks=[self.timer] + self.callbacks`
- [ ] Thay `print(...)` → `logger.info/warning/error`
- [ ] `SYSTEM_PROMPT` giữ nguyên trong file (chưa cần move ra YAML)

**Exit**: Không còn `print()` trong file. Import shared callback thành công.

---

### B5 — `environment_agent.py` — Logging cleanup

> A4 đã fix bugs + cleanup print. B5 chỉ verify không còn `print()` sót.

- [ ] Verify `grep -n "print(" pdca/agents/environment_agent.py` trả 0
- [ ] Nếu còn → thay nốt `logger.info/warning/error`

---

### B5.5 — `planning_agent.py` — Shared callbacks + Langfuse hook

> **GAP từ v1.2**: planning_agent.py 991 dòng, có ChatOllama init ([planning_agent.py:238](pdca/agents/planning_agent.py#L238)) nhưng không xuất hiện trong Phase B v1.2.

- [ ] Thêm `callbacks: list = None` vào `__init__` signature
- [ ] Lưu `self.callbacks = callbacks or []`
- [ ] `ChatOllama` init: `callbacks=self.callbacks` (planning agent KHÔNG có local TimerCallback — không cần shared TimerCallback wrap; chỉ cần Langfuse hook)
- [ ] Verify `grep -n "print(" pdca/agents/planning_agent.py` — đã confirm 0 occurrence (file đã dùng logger), nhưng verify lại
- [ ] Không thay đổi logic planning

**Exit**: `PlanningAgent(..., callbacks=[])` init thành công. Existing tests `test_planning_agent_coverage.py` xanh.

---

### B6 — `monitoring_agent.py` — KHÔNG cleanup, mark for deletion

> **Quyết định #20**: `monitoring_agent.py` sẽ bị XÓA sau Phase C5 vì inline node `scan_poll` (xem C4 v1.4) thay thế hoàn toàn. Không lãng phí công logging cleanup file sắp xóa.

- [ ] Thêm docstring `"""DEPRECATED — sẽ xóa sau C5. Logic poll đã chuyển sang pdca/graph/nodes/scan_poll.py"""`
- [ ] **Không** thay print → logger (sắp xóa)
- [ ] **Không** tách `_sleep` helper (sắp xóa)
- [ ] Sau C5: grep `MonitoringAgent` toàn codebase → nếu 0 import (sau khi orchestrator dùng inline scan nodes) → xóa file (xem C5.1)

**Exit**: File còn nguyên hành vi cũ (vẫn pass tests cũ nếu có), nhưng đánh dấu deprecated.

---

### B7 — `rescan_agent.py` — Decouple từ file + logging

> A5 đã fix poll loop. B7 bổ sung decouple config và cleanup logging.

- [ ] `__init__` nhận `config: dict = None` — nếu passed thì dùng thay vì đọc file
- [ ] Thay `print()` → `logger.info/warning/error`

---

### B8 — `analysis_agent.py` — Bỏ dual API confusion

**Vấn đề**: Constructor nhận `before_path`/`after_path` nhưng `run()` nhận data trực tiếp — hai API không nhất quán.

- [ ] Bỏ `before_path` và `after_path` khỏi `__init__` parameter list
- [ ] `load()` method: giữ nhưng add docstring `@deprecated — dùng run(pre_scan=..., post_scan=...)` và default path hardcode bên trong nếu cần backward compat
- [ ] `run()` chỉ nhận `pre_scan: dict`, `post_scan: dict`, `pipeline_context: list`
- [ ] Thay `print()` → `logger.info/warning`

**Exit**: `AnalysisAgent()` init không cần params. `run(pre_scan={...}, post_scan={...})` hoạt động.

---

### B9 — `execution_agent.py` — Logging cleanup

- [ ] Thay toàn bộ `print()` → `logger.info/warning/error`
- [ ] Không thay đổi logic (agent này hoạt động đúng)

---

### B10 — `report_agent.py` + `report_module/` — Logging cleanup + callbacks (FIX v1.5)

> **GAP từ v1.4**: Checkpoint Phase B nói "tất cả agents có LLM có `callbacks`" nhưng B10 cũ chỉ "logging cleanup" — bỏ sót `ReportAgent.__init__` và `LLMWriter` đang init LLM mà không nhận callbacks. Langfuse sẽ không trace được report stage.

**Logging tasks**:
- [ ] Thay `print()` → `logger.info/warning/error` trong `report_agent.py`
- [ ] Thay `print()` → logger trong `report_module/llm_writer.py`, `report_module/maturity_engine.py`

**Callbacks tasks (NEW v1.5 — Langfuse hook)**:
- [ ] `ReportAgent.__init__` thêm `callbacks: list = None`, lưu `self.callbacks = callbacks or []`
- [ ] `ReportAgent` propagate `callbacks` xuống bất kỳ LLM client nào nó tạo (qua `LLMWriter` hoặc trực tiếp)
- [ ] `LLMWriter` (trong `report_module/llm_writer.py`): constructor thêm `callbacks: list = None`, pass vào `ChatOllama(..., callbacks=self.callbacks)`
- [ ] Verify grep: `grep -rn "ChatOllama\|openai\.OpenAI" pdca/agents/report_module/ pdca/agents/report_agent.py` → mọi LLM init đều nhận callbacks param
- [ ] Không thay đổi logic report generation

**Exit**: `ReportAgent(callbacks=[]).run(...)` không break. LLM calls trong report stage có thể trace qua Langfuse khi thêm handler.

---

### B11 — `assessment_agent.py` — XÓA luôn

> **Verify v1.3**: `grep "assessment_agent" pdca/ tests/ RAG/` trả 0 import code. Chỉ xuất hiện ở `*.md` plan docs. → Xóa luôn, không deprecate.

- [ ] Re-verify ngay trước khi xóa: `grep -rn "assessment_agent\|AssessmentAgent" pdca/ tests/ RAG/ benchmarks/ scripts/` (loại trừ `*.md`)
- [ ] Nếu kết quả vẫn = 0 → `git rm pdca/agents/assessment_agent.py`
- [ ] Nếu phát hiện import ẩn → fallback về phương án deprecate cũ, log lý do trong commit message

**Exit**: File không còn trong cây source. `pytest tests/ -q` vẫn xanh.

---

### B12.5 — `tools_maker.py` — XÓA luôn (B13 cũ tách ra)

> Verified: chỉ xuất hiện ở `PRODUCTION_READINESS_PLAN.md` — 0 import trong code. `ToolMakerAgent` là experiment chưa từng được wire vào pipeline.

- [ ] Re-verify: `grep -rn "ToolMakerAgent\|tools_maker" pdca/ tests/ RAG/ benchmarks/ scripts/` (loại `*.md`)
- [ ] Nếu = 0 → `git rm pdca/agents/tools_maker.py`

**Exit**: File không còn. Không có test nào break.

---

### B12 — `report_module/data_builder.py` *(file mới — orchestrate, không duplicate)*

**Cập nhật v1.3**: `RAGQueryPlanner` ([rag_query_planner.py](pdca/agents/report_module/rag_query_planner.py)) ĐÃ tồn tại với `execute()` (multi-query) và `execute_legacy()` (single-query). B12 KHÔNG re-implement fetch logic — chỉ orchestrate.

**Phân chia trách nhiệm**:
- `RAGQueryPlanner` (đã có): thuần fetch — biết cách gọi RAG client, normalize bundle
- `ReportDataBuilder` (mới): orchestrate — chọn path, gọi planner, ghép vào context dict, xử lý degradation

**Tasks**:
- [ ] (Prereq R3) Commit `rag_query_planner.py` nếu chưa
- [ ] Tạo `pdca/agents/report_module/data_builder.py`
- [ ] Move `build_report_data(analysis, aws_context, plan, user_request) -> dict` từ orchestrator → `ReportDataBuilder.build_context(...)`
- [ ] Move `_extract_post_findings(analysis) -> list` từ orchestrator → `ReportDataBuilder._extract_post_findings(...)`
- [ ] **KHÔNG** move `_fetch_rag_for_report()` / `_fetch_rag_multi_query()` thô — thay vào đó:
  - `ReportDataBuilder._fetch_rag(rag_client, findings, scope_info) -> dict`:
    - `planner = RAGQueryPlanner(rag_client)`
    - if `settings.multi_query_mode`:
      - `req = planner.plan(findings, scope_info.get("domains", []))`
      - `return planner.execute(req)`
    - else:
      - `check_ids = planner._dedup_check_ids(findings)`  (helper đã public-ish)
      - `return planner.execute_legacy(check_ids)`
  - Wrap trong try/except để giữ graceful degradation (return `{}` nếu RAG fail)
- [ ] Expose entry point: `ReportDataBuilder.build(state_data: dict, rag_client: Any | None) -> dict`
- [ ] Cập nhật `orchestrator.report_node` (tạm thời ở Phase B): xóa cả `_fetch_rag_for_report()` và `_fetch_rag_multi_query()` (logic đã sống ở planner), gọi `ReportDataBuilder.build(state_data, rag_client)`
- [ ] Verify `tests/test_rag_view_formatter.py`, `tests/integration/test_report_rag_flow.py`, `tests/test_rag_query_planner.py` vẫn xanh

**Exit**:
- `from pdca.agents.report_module.data_builder import ReportDataBuilder` ✓
- `orchestrator.py` không còn `_fetch_rag_for_report` và `_fetch_rag_multi_query` (~250 dòng đi)
- `report_node` còn ~20 dòng
- Logic output không thay đổi (verified bằng existing RAG tests)

---

### B13 — Tách `pdca/tools.py` (950 dòng) → `pdca/tools/` package *(v1.6, decision #33)*

> **Vấn đề**: `pdca/tools.py` hiện gom: 4 input schemas + 4 scanner tools + 1 RAG tool + 13 S3 remediation tools + 4 export lists + 1 dead config (`ALLOWED_GROUPS_LIST` 84 services). Mỗi loại có dependency hoàn toàn khác (HTTP client / boto3 / RAG client). Không có chiến lược tách concern → khó scale (sau này thêm IAM, EC2 tools), khó test isolated.
>
> **Lưu ý naming**: Python KHÔNG cho phép `pdca/tools.py` (file) cohabit với `pdca/tools/` (directory) — cùng vấn đề như `pdca/config.py` ở A2. Step-by-step bắt buộc.

**Step-by-step (làm đúng thứ tự)**:

- [ ] **S1**. Identify callers: `grep -rn "from pdca.tools\|import pdca.tools" pdca/ tests/ benchmarks/ scripts/` — list 5+ import paths đang dùng (`REMEDIATION_TOOLS`, `SCANNER_AGENT_TOOLS`, `AVAILABLE_FUNCTIONS`, `ALL_TOOLS`)
- [ ] **S2**. `git mv pdca/tools.py pdca/tools_legacy.py.bak` — backup tạm
- [ ] **S3**. `mkdir pdca/tools && mkdir pdca/tools/remediation`
- [ ] **S4**. Tạo `pdca/tools/schemas.py` — move 4 Pydantic input schemas (`ScanGroupInput`, `ScanFileInput`, `JobStatusInput`, `ScanChecksInput`)
- [ ] **S5**. Tạo `pdca/tools/_common.py` — `ToolResult` helper + `sanitize_s3_bucket_name()` (xem code bên dưới — v1.7)
- [ ] **S6**. Tạo `pdca/tools/scanner.py` — move 4 scanner tools (`start_scan_by_group/file/check_ids`, `check_job_status`). Dùng `settings.scanner_api_url` (đã có ở A2). Mỗi tool tự register vào REGISTRY (xem B14)
- [ ] **S7**. Tạo `pdca/tools/knowledge.py` — move `lookup_security_knowledge`. Dùng `settings.rag_api_url`
- [ ] **S8**. Tạo `pdca/tools/remediation/s3.py` — move 13 S3 tools. Áp dụng B15 (return dict), B16 fixes (T7 bug, T10 sanitize)
- [ ] **S9**. Tạo `pdca/tools/__init__.py` — re-export public API + backward-compat shim (xem code bên dưới)
- [ ] **S10**. Verify imports cũ không break: `python -c "from pdca.tools import REMEDIATION_TOOLS, SCANNER_AGENT_TOOLS, AVAILABLE_FUNCTIONS, ALL_TOOLS; print(len(REMEDIATION_TOOLS), len(SCANNER_AGENT_TOOLS))"` — phải work qua shim
- [ ] **S11**. Chạy `pytest tests/ -q --collect-only` — 0 ImportError
- [ ] **S12**. `rm pdca/tools_legacy.py.bak`

**`pdca/tools/__init__.py`** (backward-compat shim):

```python
"""pdca.tools — package facade.

Public API (mới — dùng cho code mới):
- REGISTRY: ToolRegistry singleton (xem B14)
- get_tools_for(category): list[BaseTool] cho 1 category

Legacy exports (backward-compat — sẽ deprecate sau Phase C):
- REMEDIATION_TOOLS, SCANNER_AGENT_TOOLS, AVAILABLE_FUNCTIONS, ALL_TOOLS, TOOLS_MAP
"""
from pdca.tools.registry import REGISTRY, get_tools_for

# Auto-register: import side effects khiến mỗi module gọi REGISTRY.register()
from pdca.tools import scanner, knowledge   # noqa: F401
from pdca.tools.remediation import s3       # noqa: F401

# --- Backward-compat (DO NOT add new entries — dùng REGISTRY thay) ---
SCANNER_AGENT_TOOLS = REGISTRY.for_category("scanner") + REGISTRY.for_category("knowledge")
REMEDIATION_TOOLS = REGISTRY.for_category("remediation")
ALL_TOOLS = SCANNER_AGENT_TOOLS + REMEDIATION_TOOLS
TOOLS_MAP = {t.name: t for t in ALL_TOOLS}
AVAILABLE_FUNCTIONS = TOOLS_MAP   # alias key đã chuẩn hóa về tool.name (decision #34)

__all__ = [
    "REGISTRY", "get_tools_for",
    # Legacy
    "SCANNER_AGENT_TOOLS", "REMEDIATION_TOOLS", "ALL_TOOLS",
    "TOOLS_MAP", "AVAILABLE_FUNCTIONS",
]
```

**Exit**:
- `from pdca.tools import REMEDIATION_TOOLS` ✓ (qua shim)
- `from pdca.tools import REGISTRY; print(len(REGISTRY.all()))` = 18
- `pdca/tools.py` (file) không tồn tại — chỉ còn `pdca/tools/` (directory)
- `pytest tests/ -q --collect-only` 0 ImportError

---

### B14 — `ToolRegistry` thay 4 export lists *(v1.6, decision #34)*

> **Vấn đề**: 4 list (`AVAILABLE_FUNCTIONS` dict, `SCANNER_AGENT_TOOLS`, `REMEDIATION_TOOLS`, `ALL_TOOLS`) overlap. `AVAILABLE_FUNCTIONS` dùng key alias `"remediate_*"` ≠ tool.name thật ([tools.py:821-832](pdca/tools.py#L821-L832)) → 2 nguồn truth khác nhau. `ALWAYS_MANUAL_TOOLS` ([remediate_planner_agent.py:16](pdca/agents/remediate_planner_agent.py#L16)) là set độc lập — không gắn vào tool definition.

**Tasks**:

- [ ] Tạo `pdca/tools/registry.py`:

```python
"""ToolRegistry — single source of truth cho tool catalog.

Mỗi tool tự register vào REGISTRY khi module được import.
Metadata-rich: category, manual_only, alias.
"""
from dataclasses import dataclass
from typing import Optional
from langchain_core.tools import BaseTool


@dataclass
class ToolMeta:
    tool: BaseTool
    category: str           # "scanner" | "knowledge" | "remediation"
    manual_only: bool = False
    # NOTE v1.7: bỏ field `aliases` — backward-compat đã được handle qua
    # AVAILABLE_FUNCTIONS = TOOLS_MAP shim trong pdca/tools/__init__.py.
    # Nếu sau này cần alias resolution thực sự, add lại + implement trong .get().


class ToolRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, ToolMeta] = {}

    def register(
        self, tool: BaseTool, *, category: str, manual_only: bool = False,
    ) -> BaseTool:
        if tool.name in self._by_name:
            raise ValueError(f"Tool '{tool.name}' đã được register")
        self._by_name[tool.name] = ToolMeta(
            tool=tool, category=category, manual_only=manual_only,
        )
        return tool

    def get(self, name: str) -> Optional[BaseTool]:
        meta = self._by_name.get(name)
        return meta.tool if meta else None

    def meta(self, name: str) -> Optional[ToolMeta]:
        return self._by_name.get(name)

    def is_manual_only(self, name: str) -> bool:
        meta = self._by_name.get(name)
        return meta.manual_only if meta else False

    def for_category(self, category: str) -> list[BaseTool]:
        return [m.tool for m in self._by_name.values() if m.category == category]

    def all(self) -> list[BaseTool]:
        return [m.tool for m in self._by_name.values()]


REGISTRY = ToolRegistry()


def get_tools_for(category: str) -> list[BaseTool]:
    return REGISTRY.for_category(category)
```

- [ ] Mỗi tool module register vào REGISTRY ngay sau định nghĩa:

```python
# pdca/tools/scanner.py (ví dụ)
@tool(args_schema=ScanGroupInput)
def start_scan_by_group(group: str): ...

REGISTRY.register(start_scan_by_group, category="scanner")
```

- [ ] Move `ALWAYS_MANUAL_TOOLS` set khỏi `remediate_planner_agent.py` → register flag `manual_only=True` trong `s3.py`:

```python
# pdca/tools/remediation/s3.py
REGISTRY.register(s3_enable_object_lock, category="remediation", manual_only=True)
REGISTRY.register(s3_enable_mfa_delete, category="remediation", manual_only=True)
REGISTRY.register(s3_prepare_replication, category="remediation", manual_only=True)
REGISTRY.register(s3_remove_cross_account_principals, category="remediation", manual_only=True)
REGISTRY.register(s3_enable_intelligent_tiering, category="remediation", manual_only=True)
# Auto-fix tools:
REGISTRY.register(s3_block_account_public_access, category="remediation")
# ... etc
```

- [ ] Cập nhật `remediate_planner_agent.py`:
  - Xóa `ALWAYS_MANUAL_TOOLS = {...}` set
  - Thay `is_manual = tool_name in ALWAYS_MANUAL_TOOLS` → `is_manual = REGISTRY.is_manual_only(tool_name)`
  - Thay `tools_map = {t.name: t for t in REMEDIATION_TOOLS}` → dùng `REGISTRY.get(name)` trực tiếp

- [ ] Cập nhật `analysis_agent._load_tool_description()` ([analysis_agent.py:486](pdca/agents/analysis_agent.py#L486)): thay `next((t for t in REMEDIATION_TOOLS ...))` → `REGISTRY.get(tool_name)`

- [ ] Cập nhật `orchestrator.py:39 TOOLS_MAP = {t.name: t for t in ALL_TOOLS}` — vẫn import qua shim (không break), nhưng add comment `# DEPRECATED: dùng REGISTRY.get(name)`

**Exit**:
- `from pdca.tools import REGISTRY` ✓
- `REGISTRY.is_manual_only("s3_enable_object_lock")` = `True`
- `REGISTRY.for_category("scanner")` không rỗng (3 tool nếu B18 xóa `start_scan_by_file`, 4 nếu giữ)
- `REGISTRY.for_category("knowledge")` có ≥ 1 tool
- `REGISTRY.for_category("remediation")` có ≥ 12 tool (12 nếu B18 xóa `s3_force_private_acl`, 13 nếu giữ)
- `ALWAYS_MANUAL_TOOLS` không còn xuất hiện trong `remediate_planner_agent.py`

---

### B15 — Chuẩn hóa tool return type + fix bugs *(v1.6, decisions #35, T6/T7/T8/T10)*

> **Vấn đề T6**: Tool return type mixed — vài tool `return dict`, vài tool `return json.dumps(dict)`. `ExecutionAgent.parse_tool_output()` ([execution_agent.py:53-65](pdca/agents/execution_agent.py#L53-L65)) là patch downstream cho cái lỗi upstream.
>
> **Vấn đề T7**: [tools.py:204-207](pdca/tools.py#L204-L207) — `s3_prepare_replication` gọi `json.dump(result)` (thiếu file handle) trong except branch, không return → raise NameError + UnboundLocalError downstream.
>
> **Vấn đề T8**: ~15 `print()` trong tool functions.
>
> **Vấn đề T10**: `s3_secure_transport` build IAM policy với f-string `arn:aws:s3:::{resource_id}` không validate — risk nhỏ về policy injection.

**Tasks**:

- [ ] Tạo `pdca/tools/_common.py`:

```python
"""Shared helpers cho tools — chuẩn hóa result + sanitize input.

NOTE v1.7: `sanitize_s3_bucket_name` là S3-specific (regex theo S3 spec).
Khi thêm services khác (IAM, EC2, RDS), thêm sanitizer riêng cho từng loại
ARN/identifier — KHÔNG generic hóa hàm này.
"""
import re
from typing import Any, Optional

# Bucket name regex theo S3 rules (RFC: lowercase, 3-63 chars, dot/dash)
_S3_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$")


def sanitize_s3_bucket_name(raw: str) -> str:
    """Strip ARN prefix + whitespace, validate against S3 bucket name spec.

    Raises ValueError nếu không hợp lệ. Mỗi tool gọi nó BÊN TRONG try/except
    chính của tool và return ToolResult.failed nếu raise — đảm bảo invariant
    "tool luôn return dict" (decision #35).
    """
    if not isinstance(raw, str):
        raise ValueError(f"bucket name phải là string, got {type(raw).__name__}")
    s = raw.strip()
    if s.startswith("arn:aws:s3:::"):
        s = s.split(":::", 1)[1].split("/", 1)[0]
    if not _S3_BUCKET_RE.match(s):
        raise ValueError(f"bucket name không hợp lệ: {raw!r}")
    return s


class ToolResult:
    """Builder cho dict result chuẩn — luôn return dict, KHÔNG json.dumps()."""

    @staticmethod
    def success(*, resource: str, action: str, **extra: Any) -> dict:
        return {"success": True, "status": "remediated",
                "resource": resource, "action": action, **extra}

    @staticmethod
    def already_compliant(*, resource: str, message: str = "") -> dict:
        return {"success": True, "status": "skipped",
                "resource": resource, "message": message}

    @staticmethod
    def manual_required(*, resource: str, remaining: list[str], reason: str) -> dict:
        return {"success": False, "status": "manual_required", "manual_required": True,
                "resource": resource, "remaining_actions": remaining, "reason": reason,
                "verification": {"before": {}, "after": {}, "passed": False}}

    @staticmethod
    def failed(*, resource: str, error: str, **extra: Any) -> dict:
        return {"success": False, "status": "failed",
                "resource": resource, "error": error, **extra}
```

- [ ] **Refactor toàn bộ 13 S3 tools** dùng `ToolResult`:
  - Mọi `return json.dumps({...})` → `return ToolResult.xxx(...)`
  - Mọi `return {"success": ...}` thủ công → dùng `ToolResult.xxx(...)`
  - Tool input có bucket name → wrap `sanitize_s3_bucket_name()` trong try/except (T10) — xem pattern bên dưới
  - Annotation `-> str` ở các tool đang return dict → đổi `-> dict`

**Pattern chuẩn cho mỗi tool (FIX v1.7 — invariant "luôn return dict")**:

```python
@tool
def s3_secure_transport(resource_id: str, region: str = "us-east-1") -> dict:
    """[AUTO-FIX] ... (giữ docstring format hiện tại — analysis_agent parse)"""
    # T10: sanitize có thể raise ValueError — bắt và convert sang ToolResult.failed
    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    try:
        # ... boto3 logic chính ...
        client.put_bucket_policy(Bucket=bucket, Policy=...)
        return ToolResult.success(resource=bucket, action="enforced SSL policy")
    except ClientError as e:
        return ToolResult.failed(resource=bucket, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=bucket, error=f"unexpected: {e}")
```

→ ExecutionAgent **luôn** nhận dict, không bao giờ phải bắt `ValueError` từ tool boundary.

- [ ] **Fix bug T7 trong `s3_prepare_replication`**:
  ```python
  # TRƯỚC (line 200-205):
  except ClientError:
      result["reason"] = "Bucket not found during replication check."
      json.dump(result)   # ← BUG: NameError + missing return

  # SAU:
  except ClientError as e:
      return ToolResult.failed(
          resource=bucket,
          error=f"Bucket not found during replication check: {e}",
      )
  ```

- [ ] **Logging T8**: Mọi `print(f"[Tool] ...")` → `logger.info(...)`. Thêm `logger = logging.getLogger(__name__)` đầu mỗi tool file

- [ ] **ExecutionAgent cleanup**: `parse_tool_output()` bây giờ chỉ cần handle dict (post-B15 không có tool return string). Giữ branch JSON-string làm safety net + add deprecation comment:
  ```python
  def parse_tool_output(self, raw_result: Any):
      if isinstance(raw_result, dict):
          return raw_result
      # Safety net — sau B15 mọi tool return dict, branch này không nên hit
      logger.warning("Tool returned non-dict — should be fixed in tools layer")
      ...
  ```

- [ ] **(NEW v1.7) ExecutionAgent guards — defense-in-depth trước khi invoke tool**:

> Manual_only flag và category đã có trong REGISTRY (B14). Nhưng planner/graph có thể được điều khiển từ HITL UI hoặc bug logic — ExecutionAgent là **last line of defense**, không tin task["tool_name"] mù quáng. Add 3 guard:

```python
# pdca/agents/execution_agent.py — execute_task()
from pdca.tools import REGISTRY

def execute_task(self, task: Dict[str, Any], decision: str) -> Dict[str, Any]:
    task_id = task["task_id"]
    tool_name = task["tool_name"]

    # GUARD 0 (đã có): decision != approve → skip
    if decision != "approve":
        return self._build_log(task_id, tool_name, "skipped",
                               f"Task {task_id} skipped.", 0)

    # GUARD 1 (NEW v1.7): tool phải tồn tại trong REGISTRY
    meta = REGISTRY.meta(tool_name)
    if meta is None:
        logger.error("Refused: tool not registered",
                     extra={"task_id": task_id, "tool_name": tool_name})
        return self._build_log(task_id, tool_name, "error",
                               "Tool không tồn tại trong REGISTRY", 0)

    # GUARD 2 (NEW v1.7): chỉ tools category="remediation" được execute ở đây
    # Scanner/knowledge tools KHÔNG được chạy trong remediation path —
    # nếu task["tool_name"] trỏ tới scanner tool thì có gì sai upstream.
    if meta.category != "remediation":
        logger.error("Refused: non-remediation tool in execution path",
                     extra={"task_id": task_id, "tool_name": tool_name,
                            "category": meta.category})
        return self._build_log(task_id, tool_name, "error",
                               f"Category '{meta.category}' không được execute "
                               f"ở remediation path", 0)

    # GUARD 3 (NEW v1.7): manual_only — REGISTRY là source of truth.
    # Không tin task["manual_required"] vì nó có thể bị HITL UI override.
    if meta.manual_only:
        logger.warning("Refused: manual_only tool",
                       extra={"task_id": task_id, "tool_name": tool_name})
        return self._build_log(task_id, tool_name, "manual_required",
                               "Tool yêu cầu thao tác thủ công — execution refused", 0)

    # ... existing inject region/account_id + tool.invoke(...) logic ...
```

- [ ] Verify guards bằng test mới (xem Test Impact Phase B v1.7):
  - Inject task với `tool_name` không tồn tại → assert status="error", message chứa "không tồn tại"
  - Inject task với `tool_name="lookup_security_knowledge"` (category=knowledge) → assert refused
  - Inject task với `tool_name="s3_enable_object_lock"` (manual_only) + decision="approve" → assert status="manual_required" (KHÔNG execute thật)

**Exit**:
- `grep -rn "json\.dumps\|json\.dump" pdca/tools/` chỉ còn ở `s3_enable_access_logging` (build BucketPolicy JSON — legitimate, không phải return value)
- `grep -rn "print(" pdca/tools/` = 0
- `s3_prepare_replication.invoke({"resource_id": "nonexistent-bucket"})` không raise — return dict `{"success": False, "status": "failed"}`
- **(FIX v1.7)** `s3_secure_transport.invoke({"resource_id": "invalid; DROP TABLE--"})` không raise — return dict `{"success": False, "status": "failed", "error": <ValueError msg từ sanitize>}` (invariant: tool LUÔN return dict)
- Mọi tool gọi `tool.invoke({...})` đều nhận lại `dict` — KHÔNG nhận `str`, KHÔNG raise

---

### B16 — `tool_id` → `tool_name` rename *(v1.6, decision #36)*

> **Vấn đề T3**: `remediate_planner_agent.plan_remediation()` ([line 200-210](pdca/agents/remediate_planner_agent.py#L200-L210)) trả `{"tool_id": tool_name, "params": tool_params}`. Nhưng `state.RemediationTask.tool_name` + `execution_agent` đọc `task["tool_name"]`. Orchestrator dịch ([orchestrator.py:313-314](pdca/orchestrator.py#L313-L314)):
> ```python
> "tool_name": plan["tool_id"],
> "tool_params": plan["params"],
> ```
> Bug-magnet — rename 1 phía mà quên phía kia → silent break.

**Tasks**:

- [ ] Sửa `remediate_planner_agent.plan_remediation()` return dict:
  ```python
  # TRƯỚC:
  plans.append({
      "finding_id": finding_id,
      "tool_id": tool_name,
      "params": tool_params,
      ...
  })

  # SAU:
  plans.append({
      "finding_id": finding_id,
      "tool_name": tool_name,    # ← canonical key
      "tool_params": tool_params,
      ...
  })
  ```

- [ ] Xóa dịch ở orchestrator:
  ```python
  # TRƯỚC ([orchestrator.py:310-318]):
  state["remediation_tasks"].append({
      "task_id": ...,
      "finding_id": plan["finding_id"],
      "tool_name": plan["tool_id"],
      "tool_params": plan["params"],
      ...
  })

  # SAU:
  state["remediation_tasks"].append({
      "task_id": ...,
      **plan,   # tool_name/tool_params đã đúng key
      ...
  })
  ```

- [ ] Verify: `grep -rn "tool_id\|\\bparams\\b" pdca/agents/remediate_planner_agent.py pdca/orchestrator.py` — 0 hit cho `"tool_id"` (chỉ còn nếu có legitimate khác)

**Exit**:
- `RemediationPlannerAgent.plan_remediation([finding])[0]["tool_name"]` ✓ (không còn `["tool_id"]`)
- Orchestrator không còn dòng `"tool_name": plan["tool_id"]`
- `pytest tests/test_remediation_planner.py -q` xanh (nếu có); pipeline E2E xanh

---

### B17 — `ScannerAgent.ALLOWED_GROUPS` → settings *(v1.6, decision #37)*

> **Vấn đề T4**: [scanner_agent.py:38-48](pdca/agents/scanner_agent.py#L38-L48) hardcode 9 services. [tools.py:837-920](pdca/tools.py#L837-L920) define `ALLOWED_GROUPS_LIST` 84 services nhưng **0 import** — dead config.

**Tasks**:

- [ ] Add vào `pdca/config/settings.py`:
  ```python
  # Scanner whitelist — None = no filter (allow all Prowler-supported services)
  scanner_allowed_services: Optional[list[str]] = None
  ```

- [ ] `ScannerAgent._normalize_groups()`: thay `if group not in self.ALLOWED_GROUPS:` → check `settings.scanner_allowed_services`:
  ```python
  allowed = settings.scanner_allowed_services
  if allowed is not None and group not in allowed:
      logger.warning("Skipping unsupported group", extra={"group": group})
      continue
  ```

- [ ] Xóa class attr `ScannerAgent.ALLOWED_GROUPS = {...}` (9 services)
- [ ] Xóa `ALLOWED_GROUPS_LIST` khỏi `pdca/tools/` (đã ko còn ai dùng — verified 0 import)

**Exit**:
- `grep -rn "ALLOWED_GROUPS_LIST" pdca/` = 0
- `ScannerAgent` không còn class attr `ALLOWED_GROUPS`
- Default behavior: cho phép mọi group (backward-compat khi `scanner_allowed_services=None`)

---

### B18 — Cleanup tool zero-usage / functional overlap *(v1.6, FIX v1.7 rationale, T12)*

> **2 tool ứng cử viên xóa (lý do khác nhau)**:
>
> 1. **`start_scan_by_file`** — *zero-usage trong pipeline*: PlanningAgent chỉ output `groups_to_scan` hoặc `checks_to_scan`, chưa bao giờ ra path tới custom JSON file. Tool này chỉ tồn tại như API endpoint `/scan/custom` mà không có upstream caller.
>
> 2. **`s3_force_private_acl`** — *functional overlap với `s3_disable_bucket_acls`*: Cả hai cùng giải quyết "ACL findings". `s3_force_private_acl` dùng `put_bucket_acl(ACL="private")` — approach **lỗi thời** trên S3 hiện đại. `s3_disable_bucket_acls` dùng `BucketOwnership=BucketOwnerEnforced` — approach **được AWS khuyến nghị** (ACL bị disable hoàn toàn). Giữ cả hai khiến planner LLM phải chọn arbitrary; planner có thể pick approach lỗi thời.
>
> *(FIX v1.7: lý do cũ "không có entry trong AVAILABLE_FUNCTIONS → planner không pick được" là sai về mặt kỹ thuật — planner build prompt từ `REMEDIATION_TOOLS` list, không từ `AVAILABLE_FUNCTIONS` dict. Lý do thực sự là functional overlap.)*

**Tasks**:

- [ ] Re-verify ngay trước khi xóa:
  - `grep -rn "start_scan_by_file\|/scan/custom" pdca/ tests/ benchmarks/ scripts/` (loại `*.md`)
  - `grep -rn "s3_force_private_acl" pdca/ tests/ benchmarks/ scripts/`
- [ ] Nếu cả hai = 0 hit (sau B13 file split):
  - Xóa `start_scan_by_file` khỏi `pdca/tools/scanner.py` + bỏ `REGISTRY.register` line
  - Xóa `s3_force_private_acl` khỏi `pdca/tools/remediation/s3.py` + bỏ register
  - Xóa `ScanFileInput` khỏi `pdca/tools/schemas.py`
- [ ] **Cẩn thận**: nếu test E2E nào còn reference `start_scan_by_file` qua API endpoint `/scan/custom` (Phase D2) → giữ tool, chỉ remove khỏi `SCANNER_AGENT_TOOLS` list (LLM ko pick nhưng API endpoint vẫn work)

**Exit**:
- 16 tools còn lại trong REGISTRY (giảm từ 18)
- `pytest tests/ -q` xanh
- API endpoint `/scan/custom` (Phase D) — đã quyết: giữ hoặc xóa tùy verify ở bước trên

---

### Checkpoint Phase B

- [ ] Không còn `class TimerCallback` duplicate (chỉ tồn tại ở `shared/callbacks.py`) — verify bằng `grep -rn "class TimerCallback" pdca/` → 1 hit
- [ ] `ScannerAgent()` không in `[ScannerModule] Init LangChain` khi khởi tạo
- [ ] `AnalysisAgent()` init không cần file path params
- [ ] Tất cả agents có LLM (planning, scanner-NO, risk_eval, remediate_planner, planning) có `callbacks: list = None` trong `__init__`
- [ ] `assessment_agent.py` đã bị **xóa** (`git rm`)
- [ ] `tools_maker.py` đã bị **xóa**
- [ ] `monitoring_agent.py` có docstring DEPRECATED (chưa xóa, chờ C5.1)
- [ ] `ReportDataBuilder.build({}, None)` importable và không crash (None rag_client → degrade)
- [ ] `orchestrator.py` không còn `_fetch_rag_for_report` và `_fetch_rag_multi_query`
- [ ] Không còn `print()` trong `pdca/agents/` — verify bằng `grep -rn "^[^#]*print(" pdca/agents/ --include="*.py"` → 0 hit (loại trừ comments)
- [ ] **(v1.6)** `pdca/tools.py` (file) không tồn tại — chỉ còn `pdca/tools/` (directory)
- [ ] **(v1.6)** `from pdca.tools import REGISTRY; len(REGISTRY.all())` ≥ 16 (giảm từ 18 nếu B18 xóa 2 dead tools)
- [ ] **(v1.6)** `grep -rn "json\.dumps" pdca/tools/` chỉ còn ở build BucketPolicy/SNS-Policy (không phải tool return value)
- [ ] **(v1.6)** `grep -rn "print(" pdca/tools/` = 0
- [ ] **(v1.6)** `grep -rn "ALWAYS_MANUAL_TOOLS\|ALLOWED_GROUPS_LIST\|tool_id" pdca/` = 0 hits
- [ ] **(v1.6)** `REGISTRY.is_manual_only("s3_enable_object_lock")` = `True`
- [ ] `pytest tests/ -q` vẫn xanh, đặc biệt: `test_planning_agent_coverage.py`, `test_rag_query_planner.py`, `test_rag_view_formatter.py`, `tests/integration/test_report_rag_flow.py`

---

## Phase C — LangGraph Restructure

> Phase lớn nhất. Làm tuần tự từ C1 → C8. Không skip bước.

### C1 — Mở rộng `pdca/state.py` + tạo `pdca/graph/state.py`

> **Hai bước**: (1) Thêm fields mới vào `pdca/state.py` hiện tại. (2) Copy/move sang `pdca/graph/state.py` — đây là vị trí chuẩn cho Phase C trở đi.
>
> **v1.4 + FIX v1.5**: Field `raw_findings` giữ shape `List[Dict]` (no reducer) — scan_poll explicit `state.get("raw_findings", []) + new_raw`. Tách `normalized_findings: List[Dict]` (set once by scan_collect) để tránh bug raw+normalized lẫn lộn. Toàn bộ scan-flow fields đều no-reducer cho semantic nhất quán (xem decision #25 + #28).

- [ ] Thêm `run_id: str` (default `""`) vào `pdca/state.py` — Langfuse trace_id hook
- [ ] Thêm `errors: Annotated[list[dict], operator.add]` — accumulate lỗi thay vì crash
- [ ] Thêm `pre_scan_snapshot: Optional[Dict]` — thay file coupling với `pre_scan.json`
- [ ] Thêm `post_scan_snapshot: Optional[Dict]` — thay file coupling với `post_scan.json`
- [ ] **NEW v1.4 / FIX v1.5**: Giữ `raw_findings: List[Dict]` (replace, **KHÔNG** Annotated reducer). scan_poll explicit `state.get("raw_findings", []) + new_raw`. Lý do: reducer = append, không reset → scan_submit không clear được. Đồng nhất semantic với `pending_jobs/completed_jobs` (decision #28)
- [ ] **NEW v1.4**: Thêm `normalized_findings: List[Dict]` — set ONCE bởi `scan_collect`, no reducer
- [ ] **NEW v1.4**: Thêm `pending_jobs: Dict[str, ScanJobMeta]` — JSON-serializable (không Set)
- [ ] **NEW v1.4**: Thêm `completed_jobs: Dict[str, ScanJobMeta]` — meta + status sau khi xong/fail/timeout
- [ ] **NEW v1.4 / FIX v1.5**: Thêm `scan_started_at: float` — **wall-clock** timestamp (`time.time()`, Unix epoch) cho timeout check. KHÔNG dùng `time.monotonic()` vì process-local — sau resume từ SqliteSaver sẽ vô nghĩa (decision #27)
- [ ] **NEW v1.4**: Thêm `scan_poll_count: int` — đếm iteration cho max_iter check
- [ ] **NEW v1.4**: Thêm class `ScanJobMeta(TypedDict, total=False)` — xem C4
- [ ] **DEPRECATED v1.4**: `scan_job_ids: List[str]` — vestigial, giữ để không break code cũ trong Phase A/B; sẽ xóa cuối Phase C khi orchestrator/tests đã migrate
- [ ] Giữ nguyên các fields hiện tại khác
- [ ] Tạo `pdca/graph/state.py` = copy từ `pdca/state.py` đã update (cả hai file tồn tại song song trong Phase C)
- [ ] Giữ `pdca/state.py` re-export từ `pdca/graph/state.py` để backward compat:
  ```python
  # pdca/state.py (sau C1)
  from pdca.graph.state import (
      PDCAState, AWSEnvironment, AssessmentPlan,
      RemediationTask, ExecutionLog, ScanJobMeta,
  )
  __all__ = ["PDCAState", "AWSEnvironment", "AssessmentPlan",
             "RemediationTask", "ExecutionLog", "ScanJobMeta"]
  ```

```python
class ScanJobMeta(TypedDict, total=False):
    """Metadata 1 scan job — giữ context để debug + retry."""
    task_type: str       # "group" | "checks" | "custom"
    task_value: str      # group name / check_ids joined / filename
    status: str          # "pending" | "completed" | "failed" | "timeout"


class PDCAState(TypedDict):
    # --- Identity ---
    run_id: str                                          # NEW: Langfuse hook

    # --- Existing fields (giữ nguyên) ---
    performance_metrics: Dict[str, Any]
    user_request: str
    aws_context: Optional[AWSEnvironment]
    cycle_iteration: int
    rag_available: bool
    assessment_plan: Optional[AssessmentPlan]
    scan_job_ids: List[str]                              # DEPRECATED v1.4 — xóa cuối Phase C

    # --- v1.4 / FIX v1.5: explicit append (no reducer) ---
    raw_findings: List[Dict]                             # set by scan_poll = state.get("raw_findings", []) + new_raw

    # --- NEW v1.4: scan flow state ---
    normalized_findings: List[Dict]                      # NEW: set once by scan_collect
    pending_jobs: Dict[str, ScanJobMeta]                 # NEW: dict, KHÔNG Set
    completed_jobs: Dict[str, ScanJobMeta]               # NEW: meta + status
    scan_started_at: float                               # NEW v1.4 / FIX v1.5: time.time() Unix epoch (NOT monotonic — survive SqliteSaver restart)
    scan_poll_count: int                                 # NEW: iteration counter

    # --- Existing fields tiếp tục ---
    prioritized_findings: List[Dict]
    remediation_tasks: List[RemediationTask]
    task_execution_plan: Dict[str, str]
    current_task_index: int
    execution_logs: Annotated[List[ExecutionLog], operator.add]
    pipeline_context: List[Dict]
    verification_results: Dict[str, Any]
    analysis_results: Dict[str, Any]
    final_report: str

    # --- NEW: Decouple từ filesystem ---
    pre_scan_snapshot: Optional[Dict]                    # NEW
    post_scan_snapshot: Optional[Dict]                   # NEW

    # --- NEW: Error accumulation ---
    errors: Annotated[List[Dict], operator.add]          # NEW
```

**Quan trọng — semantics (v1.5: tất cả no-reducer, explicit replace)**:
| Field | Reducer | Ai write | Pattern |
|---|---|---|---|
| `raw_findings` | **none (replace)** | `scan_submit` (reset `[]`), `scan_poll` (append) | `scan_poll` return `{"raw_findings": state.get("raw_findings", []) + new_raw}` |
| `normalized_findings` | none (replace) | `scan_collect` | 1 lần duy nhất sau khi tất cả poll xong |
| `pending_jobs` | none (replace) | `scan_submit` (init), `scan_poll` (subset) | Mỗi node return = full new dict |
| `completed_jobs` | none (replace) | `scan_poll` (merge then return full) | Mỗi node return = full merged dict |

→ Downstream nodes (`risk_eval`, `verification`, etc.) đọc `state["normalized_findings"]`, KHÔNG đọc `raw_findings` (raw chỉ là intermediate).
→ Đồng nhất "no-reducer" cho toàn bộ scan-flow fields giúp scan_submit có thể reset clean trong multi-cycle hoặc manual re-trigger (decision #28).

---

### C2 — Tạo `pdca/graph/checkpointer.py`

> **Bug fix v1.3**: `SqliteSaver.from_conn_string(path)` trả về **context manager**, không phải saver instance. Dùng trực tiếp sẽ fail. Phải tự tạo `sqlite3.Connection` rồi truyền vào `SqliteSaver(conn)`.

- [ ] Tạo `pdca/graph/__init__.py`
- [ ] Tạo `pdca/graph/checkpointer.py`:

```python
import os
import sqlite3
from langgraph.checkpoint.memory import MemorySaver

DEFAULT_DB_PATH = "data/checkpoints/pdca_state.db"


def get_checkpointer(mode: str = "sqlite", db_path: str = DEFAULT_DB_PATH):
    """
    Factory trả checkpointer phù hợp với môi trường.
    mode="sqlite"  → dùng cho dev/prod (state survive restart)
    mode="memory"  → dùng cho test (không cần file)

    NOTE: SqliteSaver giữ reference tới sqlite3.Connection — caller
    chịu trách nhiệm giữ checkpointer sống suốt vòng đời graph (thường
    là singleton ở module level hoặc app lifespan).
    """
    if mode == "memory":
        return MemorySaver()

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        import warnings
        warnings.warn(
            "SqliteSaver not available, falling back to MemorySaver. "
            "Run: pip install langgraph-checkpoint-sqlite"
        )
        return MemorySaver()

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    # check_same_thread=False vì FastAPI/uvicorn dùng nhiều thread
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn)
```

- [ ] Thêm vào `requirements.txt`: `langgraph-checkpoint-sqlite`
- [ ] **(v1.5)** Verify `pydantic-settings>=2.0` đã có trong `requirements.txt` (đã add ở A2 — xem decision #29)
- [ ] Verify bằng smoke test:
  ```python
  from pdca.graph.checkpointer import get_checkpointer
  cp = get_checkpointer("sqlite")
  # Phải có method .get_tuple, .put, .list — không phải context manager
  assert hasattr(cp, "put") and hasattr(cp, "get_tuple")
  ```

**Exit**: `get_checkpointer("sqlite")` tạo file `data/checkpoints/pdca_state.db` và trả về object có method `.put`/`.get_tuple` (không phải context manager). `get_checkpointer("memory")` trả `MemorySaver`.

---

### C3 — Tạo `pdca/graph/routing.py` — Read-only routing functions

- [ ] Tạo `pdca/graph/routing.py`
- [ ] Move routing functions từ `orchestrator.py`, đảm bảo **không mutate state**:

```python
from typing import Literal
from pdca.graph.state import PDCAState

def route_after_risk(state: PDCAState) -> Literal["operational_planning", "report"]:
    fails = [f for f in state.get("prioritized_findings", [])
             if f.get("status") == "FAIL"]
    return "operational_planning" if fails else "report"


def route_review_task(state: PDCAState) -> Literal["review_task", "reset_then_execute"]:
    """
    Quyết định tiếp tục review hay chuyển sang execute.
    KHÔNG mutate state — chỉ đọc.
    """
    tasks = [t for t in state.get("remediation_tasks", [])
             if not t.get("manual_required", False)]
    idx = state.get("current_task_index", 0)
    return "review_task" if idx < len(tasks) else "reset_then_execute"
```

---

### C4 — Inline scan nodes trong main graph (KHÔNG subgraph)

> **Bug fix v1.4**: Plan v1.3 dùng subgraph + `subgraph.invoke()` nhưng KHÔNG đạt mục tiêu "1 checkpoint per poll iteration" vì `.invoke()` đồng bộ chỉ cho parent thấy state trước/sau scanning_node — không có checkpoint giữa các poll. v1.4 inline 3 node `scan_submit / scan_poll / scan_collect` vào main graph để parent's `SqliteSaver` thật sự checkpoint mỗi entry vào `scan_poll`.

**Tại sao chọn inline thay vì subgraph**:
- ✅ Mỗi entry vào `scan_poll` = 1 checkpoint của parent (đúng claim plan đã đặt)
- ✅ Crash giữa poll → resume từ poll iteration đó với `pending_jobs` còn lại (state survive)
- ✅ Đơn giản hơn: không cần quản lý sub-thread_id, không có subgraph state confusion
- ❌ Mất "hierarchical subgraph" trong sơ đồ — nhưng luận văn đã có 8-agent architecture đủ thể hiện hierarchy

**Trade-off đã chấp nhận**: `time.sleep(poll_interval_s)` trong `scan_poll` block worker thread trong web server. Tech debt cho **Phase E (async migration, post-Langfuse)** — out of scope cho plan này.

**3 nodes mới (sẽ tạo trong C5)**:
| Node | Trách nhiệm | Reads | Writes |
|---|---|---|---|
| `scan_submit` | Submit jobs lên scanner API, init `pending_jobs` dict | `assessment_plan` | `pending_jobs`, `completed_jobs={}`, `scan_started_at`, `scan_poll_count=0` |
| `scan_poll` | 1 vòng poll: check pending, append findings xong, sleep nếu còn pending | `pending_jobs`, `scan_started_at`, `scan_poll_count`, `raw_findings` | `pending_jobs` (subset), `completed_jobs` (merge), `raw_findings` (explicit append, no reducer — decision #28), `scan_poll_count++` |
| `scan_collect` | Normalize toàn bộ `raw_findings` → `normalized_findings` (set once) | `raw_findings` | `normalized_findings`, `pre_scan_snapshot` |

**Routing**:
| Function | Đọc | Trả |
|---|---|---|
| `route_scan_poll(state)` | `pending_jobs`, `scan_poll_count`, `scan_started_at` | `"scan_poll"` (vẫn còn pending + chưa max iter + chưa timeout) hoặc `"scan_collect"` |

**State fields mới cần thêm vào `PDCAState`** (xem C1 đã update):
- `pending_jobs: Dict[str, ScanJobMeta]` — JSON-serializable
- `completed_jobs: Dict[str, ScanJobMeta]`
- `raw_findings: List[dict]` — set bởi `scan_submit` (`[]` reset) và `scan_poll` (`state.get("raw_findings", []) + new_raw`). KHÔNG reducer (FIX v1.5 — decision #28)
- `normalized_findings: List[dict]` — set ONCE bởi scan_collect, **không có reducer**
- `scan_started_at: float`
- `scan_poll_count: int`

**Tasks C4 (chỉ là spec — implementation ở C5)**:
- [ ] **KHÔNG** tạo `pdca/graph/subgraphs/` (xóa khỏi kiến trúc target nếu lỡ tạo)
- [ ] Định nghĩa `ScanJobMeta` TypedDict trong `pdca/graph/state.py` (cùng file PDCAState):

```python
class ScanJobMeta(TypedDict, total=False):
    """Metadata 1 scan job — giữ context để debug + retry."""
    task_type: str       # "group" | "checks" | "custom"
    task_value: str      # group name / check_ids joined / filename
    status: str          # "pending" | "completed" | "failed" | "timeout"
```

- [ ] Định nghĩa `route_scan_poll` trong `pdca/graph/routing.py`:

```python
def route_scan_poll(state: PDCAState) -> Literal["scan_poll", "scan_collect"]:
    """Còn pending + chưa max iter + chưa timeout → poll tiếp; ngược lại collect.

    Dùng time.time() (Unix epoch) — KHÔNG monotonic — vì state được persist
    vào SqliteSaver và phải có ý nghĩa across process restart (decision #27).
    """
    pending = state.get("pending_jobs") or {}
    if not pending:
        return "scan_collect"
    if state.get("scan_poll_count", 0) >= settings.poll_max_iterations:
        return "scan_collect"
    if time.time() - state.get("scan_started_at", 0) > settings.poll_timeout_s:
        return "scan_collect"
    return "scan_poll"
```

**Exit C4**: Spec rõ ràng để C5 implement. C1 state đã có 6 field mới. Routing function đã định nghĩa. 0 file `subgraphs/` được tạo.

---

<details>
<summary><strong>HISTORICAL — code subgraph cũ (v1.3, đã loại bỏ trong v1.4)</strong></summary>

Approach v1.3 dùng `StateGraph` riêng (`ScanState` + `submit_node/poll_node/collect_node`) compile thành sub-graph, gọi qua `_scan_subgraph.invoke({...})` từ `scanning_node` của main graph.

**Lý do loại bỏ trong v1.4**:
- `subgraph.invoke()` đồng bộ → parent's `SqliteSaver` chỉ checkpoint trước/sau `scanning_node`, KHÔNG checkpoint giữa các poll iteration
- Mục tiêu "1 checkpoint per poll" trong plan v1.3 KHÔNG đạt được với design này — crash giữa poll thì resume restart từ submit
- Inline nodes (xem C4 v1.4) đơn giản hơn và đạt đúng mục tiêu

**Full code obsolete**: xem git history `git log --all -p -- REFACTOR_PLAN.md` (commits trước v1.4).

</details>

---

### C5 — Tạo `pdca/graph/nodes/*.py` — Node functions

> Mỗi file là 1 function mỏng: nhận state + config, gọi agent, trả state update. **Không chứa business logic.**

**Pattern chuẩn cho mọi node**:

```python
import logging
from langchain_core.runnables import RunnableConfig
from pdca.graph.state import PDCAState
from pdca.config.settings import settings

logger = logging.getLogger(__name__)

def xxx_node(state: PDCAState, config: RunnableConfig) -> dict:
    run_id = state.get("run_id", "")
    # Langfuse hook: callbacks inject từ config
    # FIX v1.5: chuẩn LangChain — top-level config["callbacks"], fallback configurable (decision #31)
    callbacks = (
        config.get("callbacks")
        or config.get("configurable", {}).get("callbacks", [])
        or []
    )
    
    logger.info("xxx_node start", extra={"run_id": run_id})
    # ... gọi agent ...
    logger.info("xxx_node done", extra={"run_id": run_id})
    return { ... }
```

**Các file cần tạo** (v1.4 — 3 scan nodes inline thay vì 1 scanning.py):

- [ ] `pdca/graph/nodes/__init__.py`
- [ ] `pdca/graph/nodes/environment.py` — gọi `EnvironmentAgent`, gọi `RAGClient.is_healthy()`
- [ ] `pdca/graph/nodes/planning.py` — gọi `PlanningAgent`, pass `rag_client` nếu available
- [ ] `pdca/graph/nodes/scan_submit.py` — submit jobs lên scanner API (xem code bên dưới)
- [ ] `pdca/graph/nodes/scan_poll.py` — 1 vòng poll, accumulate raw findings (xem code bên dưới)
- [ ] `pdca/graph/nodes/scan_collect.py` — normalize raw → normalized + write snapshot (xem code bên dưới)
- [ ] `pdca/graph/nodes/risk_eval.py` — gọi `RiskEvaluationAgent`, pass `callbacks`
- [ ] `pdca/graph/nodes/remediation.py` — gọi `RemediationPlannerAgent`, pass `callbacks`
- [ ] `pdca/graph/nodes/execution.py` — gọi `ExecutionAgent`
- [ ] `pdca/graph/nodes/verification.py` — gọi `RescanAgent` với config từ state (không đọc file), gọi `AnalysisAgent`. Dùng `state["pre_scan_snapshot"]` thay vì đọc `pre_scan.json`
- [ ] `pdca/graph/nodes/report.py` — gọi `ReportDataBuilder.build()` rồi `ReportAgent.run()`. Không chứa logic RAG hay maturity inline.
- [ ] `pdca/graph/nodes/reset_index.py` — `return {"current_task_index": 0}`
- [ ] `pdca/graph/nodes/review_task.py` — `return {}` (interrupt_before sẽ pause trước khi node này chạy)

**3 scan node implementations** (v1.4 — inline trong main graph, checkpoint per poll):

```python
# pdca/graph/nodes/scan_submit.py
import time
import logging
from langchain_core.runnables import RunnableConfig
from pdca.graph.state import PDCAState

logger = logging.getLogger(__name__)


def scan_submit_node(state: PDCAState, config: RunnableConfig) -> dict:
    """Submit scan jobs, init pending_jobs dict + scan timing fields."""
    from pdca.agents.scanner_agent import ScannerAgent
    plan = state.get("assessment_plan") or {}
    agent = ScannerAgent()

    # ScannerAgent.run_batch() v1.4 trả List[Dict{job_id, task_type, task_value}]
    submitted = agent.run_batch(
        target_groups=plan.get("groups_to_scan", []),
        specific_checks=plan.get("checks_to_scan", []),
    )
    pending = {
        item["job_id"]: {
            "task_type": item.get("task_type", "unknown"),
            "task_value": item.get("task_value", ""),
            "status": "pending",
        }
        for item in submitted
    }
    logger.info("scan submitted", extra={"job_count": len(pending),
                                          "run_id": state.get("run_id", "")})
    return {
        "pending_jobs": pending,
        "completed_jobs": {},
        "raw_findings": [],                # FIX v1.5: no reducer — explicit reset OK (decision #28)
        "scan_started_at": time.time(),    # FIX v1.5: wall-clock survive restart (decision #27)
        "scan_poll_count": 0,
    }
```

```python
# pdca/graph/nodes/scan_poll.py
import json
import time
import logging
from langchain_core.runnables import RunnableConfig
from pdca.graph.state import PDCAState
from pdca.config import settings

logger = logging.getLogger(__name__)


def scan_poll_node(state: PDCAState, config: RunnableConfig) -> dict:
    """Poll 1 vòng. Mỗi entry vào node này = 1 checkpoint của parent SqliteSaver.

    Lưu ý: time.sleep block worker thread — chấp nhận trong Phase C.
    Migration sang asyncio.sleep là Phase E (post-Langfuse).
    """
    from pdca.tools import AVAILABLE_FUNCTIONS

    check_status = AVAILABLE_FUNCTIONS["check_job_status"]
    pending = dict(state.get("pending_jobs") or {})  # copy local
    completed_meta_delta: dict = {}
    new_raw: list = []
    still_pending: dict = {}

    # Timeout check (route_scan_poll cũng check, nhưng double-guard)
    # FIX v1.5: time.time() khớp với scan_submit (decision #27)
    elapsed = time.time() - state.get("scan_started_at", 0)
    if elapsed > settings.poll_timeout_s:
        logger.warning("scan timeout", extra={"elapsed_s": elapsed,
                                                "pending": len(pending)})
        for jid, meta in pending.items():
            meta = {**meta, "status": "timeout"}
            completed_meta_delta[jid] = meta
        return {
            "pending_jobs": {},
            "completed_jobs": {**state.get("completed_jobs", {}),
                                **completed_meta_delta},
            "scan_poll_count": state.get("scan_poll_count", 0) + 1,
        }

    for job_id, meta in pending.items():
        try:
            raw = check_status.invoke({"job_id": job_id})
            data = json.loads(raw) if isinstance(raw, str) else raw
            api_resp = data.get("data", data)
            status = api_resp.get("status")

            if status == "completed":
                result = api_resp.get("result", [])
                if isinstance(result, list):
                    new_raw.extend(result)
                elif result:
                    new_raw.append(result)
                completed_meta_delta[job_id] = {**meta, "status": "completed"}
                logger.info("job completed", extra={"job_id": job_id})
            elif status == "failed":
                completed_meta_delta[job_id] = {**meta, "status": "failed"}
                logger.warning("job failed", extra={"job_id": job_id})
            else:
                still_pending[job_id] = meta
        except Exception as e:
            logger.error("poll error", extra={"job_id": job_id,
                                                "error": str(e)})
            still_pending[job_id] = meta  # retry next iteration

    if still_pending:
        time.sleep(settings.poll_interval_s)  # Tech debt — see decision #26

    return {
        "pending_jobs": still_pending,
        "completed_jobs": {**state.get("completed_jobs", {}),
                            **completed_meta_delta},
        # FIX v1.5: explicit append (no reducer) — scan_submit có thể reset bằng []
        "raw_findings": state.get("raw_findings", []) + new_raw,
        "scan_poll_count": state.get("scan_poll_count", 0) + 1,
    }
```

```python
# pdca/graph/nodes/scan_collect.py
import json
import os
import logging
from langchain_core.runnables import RunnableConfig
from pdca.graph.state import PDCAState
from pdca.agents.shared.normalizer import normalize_results

logger = logging.getLogger(__name__)


def scan_collect_node(state: PDCAState, config: RunnableConfig) -> dict:
    """Normalize toàn bộ raw_findings — set ONCE, no reducer (replace semantic)."""
    raw = state.get("raw_findings") or []
    normalized_pkg = normalize_results(raw) if raw else {"findings": []}
    findings = normalized_pkg.get("findings", [])

    logger.info("scan collect done", extra={
        "raw_count": len(raw),
        "normalized_count": len(findings),
        "completed_jobs": len(state.get("completed_jobs", {})),
    })

    # Optional artifact để debug — KHÔNG phải primary data path
    try:
        os.makedirs("data/artifacts", exist_ok=True)
        with open("data/artifacts/pre_scan.json", "w", encoding="utf-8") as f:
            json.dump(normalized_pkg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("Could not write pre_scan artifact",
                       extra={"error": str(e)})

    return {
        "normalized_findings": findings,        # set once — no reducer
        "pre_scan_snapshot": normalized_pkg,    # state-passed, no file coupling
    }
```

**Lưu ý semantic về state (v1.5: tất cả no-reducer, explicit replace)**:
- `raw_findings` KHÔNG có reducer — `scan_poll` return `{"raw_findings": state.get("raw_findings", []) + new_raw}` để explicit append. `scan_submit` reset bằng `[]`
- `normalized_findings` KHÔNG có reducer → `scan_collect` return `{"normalized_findings": [...]}` sẽ REPLACE (set once)
- Tách 2 field để tránh bug `[raw1, raw2, ..., normalized_packet]` từ v1.4. v1.5 thêm: cùng no-reducer pattern cho phép `scan_submit` reset clean trong multi-cycle (decision #28)
- Downstream nodes (risk_eval, etc.) dùng `state["normalized_findings"]`, không dùng `raw_findings`

---

### C5.1 — XÓA `pdca/agents/monitoring_agent.py` *(bắt buộc sau C5)*

> Sau khi C5 wire 3 inline scan nodes vào main graph, `MonitoringAgent` không còn được gọi từ đâu. Plan B6 đã đánh dấu deprecated nhưng chưa xóa.

- [ ] Verify: `grep -rn "MonitoringAgent\|monitoring_agent" pdca/ tests/ benchmarks/ scripts/` (loại trừ `*.md`)
- [ ] Nếu kết quả = 0 (sau khi orchestrator/graph dùng `scan_submit/scan_poll/scan_collect`):
  - `git rm pdca/agents/monitoring_agent.py`
- [ ] Nếu phát hiện import sót → fix call site trước rồi mới xóa
- [ ] Cập nhật Files table: monitoring_agent.py → `[D]` Deleted

**Exit**: File không còn trong cây source. `pytest tests/ -q` xanh.

---

### C6 — Tạo `pdca/graph/graph.py` — Topology thuần túy

- [ ] Tạo `pdca/graph/graph.py`
- [ ] `build_graph(checkpointer=None)` chỉ chứa: add_node, add_edge, add_conditional_edges, compile

```python
import uuid
from langgraph.graph import StateGraph, END, START
from langchain_core.runnables import RunnableConfig

from pdca.graph.state import PDCAState
from pdca.graph.checkpointer import get_checkpointer
from pdca.graph.routing import (
    route_after_risk, route_review_task, route_scan_poll,
)
from pdca.graph.nodes import (
    environment_node, planning_node,
    scan_submit_node, scan_poll_node, scan_collect_node,    # v1.4: 3 inline nodes
    risk_eval_node, remediation_node, review_task_node,
    reset_index_node, execution_node, verification_node, report_node,
)


def build_graph(checkpointer=None):
    wf = StateGraph(PDCAState)

    # Nodes
    wf.add_node("environment",          environment_node)
    wf.add_node("planning",             planning_node)
    # v1.4: scan loop inline trong main graph (KHÔNG subgraph)
    # → mỗi entry vào scan_poll = 1 checkpoint của parent SqliteSaver
    wf.add_node("scan_submit",          scan_submit_node)
    wf.add_node("scan_poll",            scan_poll_node)
    wf.add_node("scan_collect",         scan_collect_node)
    wf.add_node("risk_evaluation",      risk_eval_node)
    wf.add_node("operational_planning", remediation_node)
    wf.add_node("review_task",          review_task_node)
    wf.add_node("reset_index",          reset_index_node)
    wf.add_node("execution",            execution_node)
    wf.add_node("verification",         verification_node)
    wf.add_node("report",               report_node)

    # Linear edges
    wf.add_edge(START,              "environment")
    wf.add_edge("environment",      "planning")
    wf.add_edge("planning",         "scan_submit")
    wf.add_edge("scan_submit",      "scan_poll")
    wf.add_edge("scan_collect",     "risk_evaluation")
    wf.add_edge("operational_planning", "review_task")
    wf.add_edge("reset_index",      "execution")
    wf.add_edge("execution",        "verification")
    wf.add_edge("verification",     "report")
    wf.add_edge("report",           END)

    # Conditional edges
    wf.add_conditional_edges(
        "scan_poll", route_scan_poll,
        {"scan_poll": "scan_poll", "scan_collect": "scan_collect"},
    )
    wf.add_conditional_edges(
        "risk_evaluation", route_after_risk,
        {"operational_planning": "operational_planning", "report": "report"},
    )
    wf.add_conditional_edges(
        "review_task", route_review_task,
        {"review_task": "review_task", "reset_then_execute": "reset_index"},
    )

    cp = checkpointer or get_checkpointer()
    return wf.compile(checkpointer=cp, interrupt_before=["review_task"])
```

---

### C7 — Cập nhật `orchestrator.py` thành thin wrapper

Sau khi `pdca/graph/graph.py` hoàn chỉnh:

- [ ] `orchestrator.py` chỉ giữ `run_interactive_session()` và `handle_task_review_interaction()` như CLI entrypoint
- [ ] `build_graph()` trong `orchestrator.py` → delegate sang `from pdca.graph.graph import build_graph`
- [ ] Xóa tất cả node functions, helper functions, routing functions (đã chuyển sang `pdca/graph/`)
- [ ] Giữ lại `run_interactive_session()` để không break CLI usage hiện tại

---

### Checkpoint Phase C

- [ ] `from pdca.graph.graph import build_graph; g = build_graph(checkpointer=get_checkpointer("memory"))` không lỗi
- [ ] **0 file** trong `pdca/graph/subgraphs/` (directory không tồn tại — v1.4 inline nodes)
- [ ] 3 file `scan_submit.py`, `scan_poll.py`, `scan_collect.py` tồn tại trong `pdca/graph/nodes/`
- [ ] Không còn `input()` trong graph nodes
- [ ] `time.sleep()` chỉ còn TRONG `scan_poll.py` (đánh dấu tech debt — decision #26)
- [ ] Không còn file `open()` trong nodes (chỉ còn trong agents và optional artifact saving ở `scan_collect`)
- [ ] `run_id` được set trong initial state khi `build_graph()` chạy
- [ ] `pytest tests/ -q` xanh
- [ ] State snapshot sau khi resume có `current_task_index` đúng (test HITL flow)
- [ ] `data/checkpoints/pdca_state.db` được tạo khi dùng SqliteSaver
- [ ] **Verify per-poll checkpoint**: chạy graph với mock scanner trả pending → kill mid-poll → resume → verify `pending_jobs` còn lại đúng (không restart submit)
- [ ] State có cả `raw_findings` (length > 0) và `normalized_findings` (length > 0) sau scan_collect, KHÔNG bị overlap shape

---

## Phase D — API Hardening

> Làm sau Phase A (D1 gắn với A2 settings) và sau Phase B (D2, D3 gắn với logging cleanup).
> Mục tiêu: cả hai API sẵn sàng để Chatbot UI gọi từ browser.

### Tổng quan vấn đề phát hiện

| API | Vấn đề | Mức độ |
|---|---|---|
| Scanner | `MOCK_JOB_DATABASE` in-memory — mất khi restart | Nghiêm trọng |
| Scanner | `GET /scan/*` tạo resource — sai HTTP semantics | Nghiêm trọng |
| Scanner | Không có `/v1/` prefix — không nhất quán với RAG | Trung bình |
| Scanner | `YOUR_PROFILE_NAME = "default"` hardcoded trong worker | Trung bình |
| Scanner | `os.remove()` bị comment — output files tích lũy vô hạn | Nhỏ |
| Scanner | `print()` toàn bộ, không logging | Nhỏ |
| Scanner | Không có CORS | Blocker cho Chatbot UI |
| RAG | Mixed sync/async endpoints — không nhất quán | Nhỏ |
| RAG | 3 response format khác nhau cho các endpoints | Nhỏ |
| RAG | Không có CORS | Blocker cho Chatbot UI |
| Config | `RAG_API_URL` default `8000` — sai, RAG chạy `8005` | Bug thực sự |
| tools.py | `API_SERVER_URL` hardcoded, không dùng settings | Nhỏ |

---

### D1 — Fix port bug + hardcoded URL *(làm trong Phase A, gắn với A2)*

> **Ưu tiên cao nhất trong Phase D — đây là bug thực sự.**
>
> **NOTE v1.7**: B13 đã chuyển `pdca/tools.py` → `pdca/tools/` package. D1 thao tác trên các file con của package, KHÔNG còn `pdca/tools.py` (file). `print()` cleanup đã được B15 cover (mọi tool dùng logger qua `_common.py` pattern) — D1 không lặp.

- [ ] `pdca/config/settings.py`: `rag_api_url` default → `"http://localhost:8005"` (đã làm ở A2)
- [ ] **(v1.7)** `pdca/tools/scanner.py`: xóa hằng `API_SERVER_URL` hardcoded; mỗi tool đọc `settings.scanner_api_url` từ `pdca.config.settings`
- [ ] **(v1.7)** `pdca/tools/scanner.py`: cập nhật endpoint paths sang `/v1/scan/group`, `/v1/scan/checks`, `/v1/scan/custom`, `/v1/job/{job_id}` (sau D2) — đổi `requests.get(...)` → `requests.post(...)` cho 3 scan tools (xem D2)
- [ ] **(v1.7)** `pdca/tools/knowledge.py`: dùng `settings.rag_api_url` (lazy import KHÔNG còn cần — settings module-level OK)

**Exit**: `settings.rag_api_url` trả `"http://localhost:8005"`. `grep -rn "API_SERVER_URL\|http://127.0.0.1:8000" pdca/tools/` = 0 hit. Mọi scanner tool gọi `settings.scanner_api_url + "/v1/..."`.

---

### D2 — Scanner API: HTTP Semantics + Versioning + Logging

**File**: `pdca/api_server.py`

#### D2.1 — GET → POST cho scan endpoints

```python
# TRƯỚC
@app.get("/scan/check")
def run_simple_scan(group: str, tasks: BackgroundTasks): ...

# SAU
class ScanGroupRequest(BaseModel):
    group: str

@app.post("/v1/scan/group")
def run_simple_scan(payload: ScanGroupRequest, tasks: BackgroundTasks): ...
```

- [ ] Tạo Pydantic request models: `ScanGroupRequest`, `ScanChecksRequest`, `ScanCustomRequest`
- [ ] Đổi `@app.get("/scan/check")` → `@app.post("/v1/scan/group")`
- [ ] Đổi `@app.get("/scan/specific")` → `@app.post("/v1/scan/checks")`
- [ ] Đổi `@app.get("/scan/custom")` → `@app.post("/v1/scan/custom")`
- [ ] Đổi `@app.get("/job/status")` → `@app.get("/v1/job/{job_id}")` (RESTful path param)
- [ ] Đổi `@app.get("/job/list")` → `@app.get("/v1/jobs")`
- [ ] **(v1.7)** Cập nhật `pdca/tools/scanner.py` (sau B13) và `pdca/agents/scanner_agent.py` để gọi đúng endpoint mới
- [ ] Cập nhật `pdca/agents/rescan_agent.py` URL paths

**Backward compat**: Không cần giữ endpoint cũ — tất cả callers (`pdca/tools/scanner.py` v1.7, `ScannerAgent`, `RescanAgent`) đều trong cùng codebase và được cập nhật đồng thời trong step này.

#### D2.2 — AWS profile từ settings, không hardcoded

- [ ] Thêm vào `settings.py`: `aws_profile: str = "default"` và `aws_default_region: str = "us-east-1"`
- [ ] Thay `YOUR_PROFILE_NAME = "default"` → `settings.aws_profile`
- [ ] Thay `YOUR_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")` → `settings.aws_default_region`

#### D2.3 — Logging thay print

- [ ] Thay toàn bộ `print(f"Job {job_id}: ...")` → `logger.info/error(..., extra={"job_id": job_id})`
- [ ] Thêm `logger = get_logger("pdca.api_server")` ở đầu file

#### D2.4 — Bật lại file cleanup sau scan

- [ ] Bỏ comment `# os.remove(full_output_path)`
- [ ] Thêm config: `cleanup_scan_output: bool = True` trong settings
- [ ] Chỉ xóa khi `settings.cleanup_scan_output is True`

**Exit**:
- `curl -X POST http://localhost:8000/v1/scan/group -d '{"group":"s3"}'` trả `{"job_id": "...", "status": "pending"}`
- `curl http://localhost:8000/v1/job/{job_id}` trả job status
- Không còn `print()` trong file

---

### D3 — Scanner API: SQLite Job Database

**Vấn đề chính**: `MOCK_JOB_DATABASE: Dict = {}` in-memory → mất khi restart → MonitoringAgent poll 404 mãi.

**Giải pháp**: SQLite đơn giản dùng `sqlite3` built-in, không cần thêm dependency.

```python
# pdca/api_server.py
import sqlite3
from contextlib import contextmanager

JOB_DB_PATH = "data/jobs/scanner_jobs.db"

def _init_job_db():
    os.makedirs(os.path.dirname(JOB_DB_PATH), exist_ok=True)
    with sqlite3.connect(JOB_DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")   # ← concurrent write-safe
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id      TEXT PRIMARY KEY,
                status      TEXT NOT NULL DEFAULT 'pending',
                task_type   TEXT,
                task_value  TEXT,
                submitted_at REAL,
                started_at  REAL,
                ended_at    REAL,
                result_json TEXT,   -- findings JSON
                error_json  TEXT,
                summary     TEXT
            )
        """)

@contextmanager
def _job_db():
    conn = sqlite3.connect(JOB_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
```

- [ ] Tạo `_init_job_db()` và gọi khi app khởi động (lifespan hoặc module level)
- [ ] Thay `MOCK_JOB_DATABASE[job_id] = {...}` → INSERT vào SQLite
- [ ] Thay `MOCK_JOB_DATABASE.get(job_id)` → SELECT FROM jobs
- [ ] `_run_prowler_command_worker`: UPDATE status/result → SQLite
- [ ] `GET /v1/job/{job_id}`: SELECT row → trả dict
- [ ] `GET /v1/jobs`: SELECT với LIMIT/OFFSET (thêm pagination)
- [ ] Thêm `limit: int = 50` và `offset: int = 0` query param cho `/v1/jobs`

**Exit**:
- Server restart không mất job history
- Job được query thành công sau restart
- `/v1/jobs?limit=10&offset=0` hoạt động

---

### D4 — CORS cho cả hai API *(prerequisite bắt buộc cho Chatbot UI)*

> **FIX v1.5 (decision #32)**: Combo `allow_origins=["*"]` + `allow_credentials=True` vi phạm CORS spec — browser **luôn block** kể cả khi server response có header. Phải chọn 1 trong 2 mode rõ ràng. Settings đã có validator auto-force `credentials=False` nếu wildcard (xem A2).

#### D4.1 — Scanner API CORS

- [ ] Thêm vào `pdca/api_server.py`:

```python
from fastapi.middleware.cors import CORSMiddleware
from pdca.config import settings

# settings.cors_allow_credentials đã được validator auto-force False nếu
# settings.cors_origins == ["*"] (xem A2). Code dưới đây an toàn cho cả 2 mode.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] Settings đã có `cors_origins`, `cors_allow_credentials`, validator `_enforce_cors_spec` (xem A2)
- [ ] Document trong `.env.example`:
  - **Mode dev (mặc định)**: `CORS_ORIGINS=["*"]` (validator force credentials=False)
  - **Mode prod**: `CORS_ORIGINS=["https://chat.example.com"]` + `CORS_ALLOW_CREDENTIALS=true`

#### D4.2 — RAG API CORS

- [ ] Thêm CORS middleware vào `RAG/app/main.py` với cùng pattern (đọc từ `pdca.config.settings`)

**Exit**:
- `curl -H "Origin: http://localhost:3000" http://localhost:8000/v1/jobs` trả `Access-Control-Allow-Origin` header
- Mode wildcard: response KHÔNG có `Access-Control-Allow-Credentials: true` (browser sẽ accept)
- Mode explicit: cả hai header xuất hiện đúng cặp

---

### D5 — RAG API: Minor cleanup *(optional, low priority)*

> Chỉ làm nếu có thời gian. Không block Chatbot UI.

- [ ] Đổi sync endpoints → async cho nhất quán:
  ```python
  # retrieve_checks, retrieve_maturity, build_context → thêm async
  async def retrieve_checks(...) -> ResponseEnvelope: ...
  ```
- [ ] Deprecate `/retrieve/capability` và `/retrieve/remediation` — thay bằng note trong doc rằng dùng `/retrieve/report_context` trực tiếp
- [ ] Thêm `X-Request-ID` header vào response để trace request

**Exit**: `/retrieve/checks` và `/retrieve/report_context` đều async. Không break existing RAGClient.

---

### Checkpoint Phase D

- [ ] `RAG_API_URL` default là `http://localhost:8005` — đúng port
- [ ] **(v1.7)** `pdca/tools/scanner.py` không còn hardcoded URL — dùng `settings.scanner_api_url`
- [ ] `curl -X POST http://localhost:8000/v1/scan/group -d '{"group":"s3"}'` thành công
- [ ] `curl http://localhost:8000/v1/job/{job_id}` thành công sau server restart
- [ ] CORS headers xuất hiện trong response của cả hai API
- [ ] **(v1.7)** Không còn `print()` trong `pdca/api_server.py` và `pdca/tools/` (đã verify ở Checkpoint Phase B)
- [ ] `ScannerAgent` và `RescanAgent` gọi đúng endpoint `/v1/scan/*` mới

---

## Kiểm tra cuối — Entry Conditions cho Langfuse & Chatbot UI

Sau khi hoàn thành **tất cả Phase A + B + C + D**, kiểm tra checklist này:

### Điều kiện cho Langfuse

- [ ] Tất cả agents có LLM: có `callbacks: list = None` trong `__init__`
- [ ] `TimerCallback` ở `pdca/agents/shared/callbacks.py` — 1 nơi duy nhất
- [ ] `run_id` tồn tại trong `PDCAState`
- [ ] Tất cả node functions có `config: RunnableConfig` là param thứ 2
- [ ] Python `logging` được dùng thay `print()` trong tất cả agents và nodes
- [ ] `get_callbacks()` factory sẵn sàng nhận extra handlers

**Khi đó, tích hợp Langfuse chỉ cần**:
1. `pip install langfuse`
2. Thêm `langfuse_secret_key`, `langfuse_public_key` vào `.env`
3. Sửa `get_callbacks()` để trả thêm `LangfuseCallbackHandler`
4. Truyền `callbacks=get_callbacks()` qua `config["configurable"]` khi invoke graph

### Điều kiện cho Chatbot UI

**Graph layer:**
- [ ] `build_graph()` export được từ `pdca.graph.graph`
- [ ] `get_checkpointer("sqlite")` hoạt động — session survive restart
- [ ] Không có `input()` hay `print()` nào trong `pdca/graph/` (nodes, routing, subgraphs)
- [ ] HITL flow hoạt động qua state update (không qua CLI `input()`)
- [ ] `graph.astream()` hoạt động (LangGraph async streaming cho SSE)

**API layer (Phase D):**
- [ ] Scanner API có CORS — browser có thể gọi trực tiếp
- [ ] RAG API có CORS
- [ ] Scanner API dùng POST cho tạo job — idempotent-safe
- [ ] Scanner job database persistent (SQLite) — session survive restart
- [ ] `rag_api_url` default đúng port `8005`

**Khi đó, xây chatbot UI chỉ cần**:
1. Tạo `pdca/api/app.py` với FastAPI
2. `POST /runs` → `graph.ainvoke(initial_state, config={"thread_id": run_id})`
3. `GET /runs/{id}/stream` → `graph.astream(None, config=...)` → SSE
4. `GET /runs/{id}/pending` → `graph.get_state(config).values["remediation_tasks"]`
5. `POST /runs/{id}/decisions` → `graph.update_state(config, {"task_execution_plan": decisions}); graph.ainvoke(None, config=...)`

---

## Tổng hợp Files

| File | Action | Phase |
|---|---|---|
| `pdca/agents/shared/callbacks.py` | **[F]** TimerCallback dùng chung | A1 |
| `pdca/config.py` | **[D]** XÓA file (convert sang package) — v1.4 | A2 |
| `pdca/config/__init__.py` | **[F]** export settings + backward-compat constants | A2 |
| `pdca/config/settings.py` | **[F]** Pydantic Settings | A2 |
| `pdca/observability/__init__.py` | **[F]** | A3 |
| `pdca/observability/logger.py` | **[F]** JSON logger + run_id | A3 |
| `pdca/agents/environment_agent.py` | **[M]** fix buckets + graceful (đổi behavior except) | A4, B5 |
| `pdca/agents/monitoring_agent.py` | **[M→D]** A5 fix loop + B6 mark deprecated, **C5.1 XÓA** | A5, B6, C5.1 |
| `pdca/agents/rescan_agent.py` | **[M]** fix poll + decouple + logging | A5, B7 |
| `pdca/orchestrator.py` | **[M]** fix state mutation bug (tạm) | A6 |
| `pdca/agents/base_agent.py` | **[M]** bỏ dual init | B1 |
| `pdca/agents/scanner_agent.py` | **[M]** bỏ BaseAgent + LLM init thừa + đổi run_batch return type | B2, C4 |
| `pdca/agents/risk_evaluation_agent.py` | **[M]** shared callbacks | B3 |
| `pdca/agents/remediate_planner_agent.py` | **[M]** shared callbacks + logging | B4 |
| `pdca/agents/planning_agent.py` | **[M]** thêm callbacks param (Langfuse hook) | B5.5 |
| `pdca/agents/analysis_agent.py` | **[M]** bỏ dual API confusion | B8 |
| `pdca/agents/execution_agent.py` | **[M]** logging cleanup | B9 |
| `pdca/agents/report_agent.py` | **[M]** logging cleanup | B10 |
| `pdca/agents/report_module/llm_writer.py` | **[M]** logging cleanup | B10 |
| `pdca/agents/report_module/maturity_engine.py` | **[M]** logging cleanup | B10 |
| `pdca/agents/assessment_agent.py` | **[D]** XÓA — verified 0 import | B11 |
| `pdca/agents/tools_maker.py` | **[D]** XÓA — dead code | B12.5 |
| `pdca/tools.py` | **[D]** XÓA file (convert sang package) — v1.6 | B13 |
| `pdca/tools/__init__.py` | **[F]** v1.6 — facade + backward-compat shim | B13 |
| `pdca/tools/registry.py` | **[F]** v1.6 — ToolRegistry singleton | B14 |
| `pdca/tools/schemas.py` | **[F]** v1.6 — Pydantic input schemas | B13 |
| `pdca/tools/_common.py` | **[F]** v1.6 — ToolResult + `sanitize_s3_bucket_name` (v1.7) | B15 |
| `pdca/tools/scanner.py` | **[F]** v1.6 — 4 scanner tools (HTTP) | B13 |
| `pdca/tools/knowledge.py` | **[F]** v1.6 — 1 RAG lookup tool | B13 |
| `pdca/tools/remediation/__init__.py` | **[F]** v1.6 | B13 |
| `pdca/tools/remediation/s3.py` | **[F]** v1.6 — 13 (hoặc 12 sau B18) S3 tools, đã chuẩn hóa | B13, B15, B18 |
| `pdca/agents/remediate_planner_agent.py` | **[M]** v1.6 — bỏ `ALWAYS_MANUAL_TOOLS`, dùng REGISTRY, đổi `tool_id`→`tool_name` | B14, B16 |
| `pdca/agents/scanner_agent.py` | **[M]** v1.6 — bỏ `ALLOWED_GROUPS` class attr, đọc từ settings | B17 |
| `pdca/agents/analysis_agent.py` | **[M]** v1.6 — `_load_tool_description` dùng REGISTRY thay iterate REMEDIATION_TOOLS | B14 |
| `pdca/agents/execution_agent.py` | **[M]** v1.6 — `parse_tool_output` add deprecation warn cho non-dict input | B15 |
| `pdca/orchestrator.py` | **[M]** v1.6 — xóa dịch `tool_id`→`tool_name` ở line 313-314 | B16 |
| `pdca/agents/report_module/rag_query_planner.py` | **[E]** Existing — chỉ commit (đã implement đủ) | R3 |
| `pdca/agents/report_module/data_builder.py` | **[F]** orchestrate planner + build context | B12 |
| `pdca/state.py` | **[M]** re-export từ graph/state.py (backward compat) | C1 |
| `pdca/graph/state.py` | **[F]** move + mở rộng từ pdca/state.py | C1 |
| `pdca/graph/__init__.py` | **[F]** | C2 |
| `pdca/graph/checkpointer.py` | **[F]** SqliteSaver factory | C2 |
| `pdca/graph/routing.py` | **[F]** routing functions read-only (incl. `route_scan_poll`) | C3, C4 |
| ~~`pdca/graph/subgraphs/__init__.py`~~ | **[X]** v1.4 không tạo (inline nodes) | ~~C4~~ |
| ~~`pdca/graph/subgraphs/scan_subgraph.py`~~ | **[X]** v1.4 không tạo (inline nodes) | ~~C4~~ |
| `pdca/graph/nodes/__init__.py` | **[F]** | C5 |
| `pdca/graph/nodes/environment.py` | **[F]** | C5 |
| `pdca/graph/nodes/planning.py` | **[F]** | C5 |
| `pdca/graph/nodes/scan_submit.py` | **[F]** v1.4 — submit jobs | C5 |
| `pdca/graph/nodes/scan_poll.py` | **[F]** v1.4 — 1 vòng poll, append raw, time.sleep | C5 |
| `pdca/graph/nodes/scan_collect.py` | **[F]** v1.4 — normalize + snapshot | C5 |
| `pdca/graph/nodes/risk_eval.py` | **[F]** | C5 |
| `pdca/graph/nodes/remediation.py` | **[F]** | C5 |
| `pdca/graph/nodes/review_task.py` | **[F]** | C5 |
| `pdca/graph/nodes/reset_index.py` | **[F]** | C5 |
| `pdca/graph/nodes/execution.py` | **[F]** | C5 |
| `pdca/graph/nodes/verification.py` | **[F]** bỏ file coupling | C5 |
| `pdca/graph/nodes/report.py` | **[F]** thin wrapper | C5 |
| `pdca/graph/graph.py` | **[F]** topology + compile | C6 |
| `pdca/orchestrator.py` | **[M]** thin wrapper → delegate graph.py | C7 |
| `requirements.txt` | **[M]** thêm `langgraph-checkpoint-sqlite` + `pydantic-settings>=2.0` (v1.5) | A2, C2 |
| `pdca/tools/scanner.py` | **[M]** v1.7 — bỏ `API_SERVER_URL` hardcoded, dùng `settings.scanner_api_url`, đổi endpoint `/v1/...` + GET→POST | D1, D2 |
| `pdca/tools/knowledge.py` | **[M]** v1.7 — dùng `settings.rag_api_url` (bỏ lazy import) | D1 |
| `pdca/api_server.py` | **[M]** POST, /v1/, SQLite jobs, CORS, logging | D2, D3, D4 |
| `RAG/app/main.py` | **[M]** thêm CORS middleware | D4 |

**Tổng** (v1.7):
- **25 files mới (`[F]`)**: callbacks.py, config/__init__.py, config/settings.py, observability/{__init__,logger}.py, graph/{__init__,state,checkpointer,routing,graph}.py, graph/nodes/{__init__,environment,planning,scan_submit,scan_poll,scan_collect,risk_eval,remediation,review_task,reset_index,execution,verification,report}.py, report_module/data_builder.py, tools/{__init__,registry,schemas,_common,scanner,knowledge}.py, tools/remediation/{__init__,s3}.py
- **1 file existing-cần-commit (`[E]`)**: rag_query_planner.py
- **19 files sửa (`[M]`)**: agents (env, base, scanner ×2, risk_eval, remediate_planner ×2, planning, rescan, analysis ×2, execution ×2 v1.7 với guards, report, llm_writer, maturity_engine), state.py, orchestrator.py (×3), api_server.py, RAG/main.py, requirements.txt, **tools/scanner.py + tools/knowledge.py (v1.7 — D1 modify)**
- **5 files xóa (`[D]`)**: `pdca/config.py` (→package), `pdca/tools.py` (→package, v1.6), `assessment_agent.py`, `tools_maker.py`, `monitoring_agent.py`
- **0 files trong `pdca/graph/subgraphs/`** — directory không tồn tại (v1.4 inline scan nodes)

> Một số file xuất hiện nhiều lần:
> - `pdca/orchestrator.py`: A6 (fix tạm) → B12 (xóa fetch helpers) → B16 (xóa tool_id dịch, v1.6) → C7 (cleanup cuối) — 4 commits
> - `pdca/agents/monitoring_agent.py`: A5 (fix loop) → B6 (mark deprecated) → C5.1 (xóa) — life cycle 3 step
> - `pdca/agents/scanner_agent.py`: B2 (refactor) → B17 (bỏ ALLOWED_GROUPS, v1.6) → C4 (đổi `run_batch` return type → List[Dict])
> - `pdca/agents/remediate_planner_agent.py`: B4 (shared callbacks + logging) → B14 (REGISTRY thay ALWAYS_MANUAL_TOOLS, v1.6) → B16 (đổi `tool_id`→`tool_name`, v1.6)
> - `pdca/agents/analysis_agent.py`: B8 (bỏ dual API) → B14 (dùng REGISTRY thay iterate REMEDIATION_TOOLS, v1.6)
> - `pdca/agents/execution_agent.py`: B9 (logging cleanup) → B15 (parse_tool_output deprecation warn, v1.6)
> - `pdca/state.py` & `pdca/graph/state.py`: C1 cập nhật cả 2 với scan accumulator fields mới (raw vs normalized)

---

## Test Impact Per Phase

> Liệt kê test files có khả năng break ở mỗi phase. Mục đích: biết trước cái gì cần update, không bị surprise khi `pytest` đỏ.

### Phase A
| Test file | Tại sao có thể break | Action |
|---|---|---|
| `tests/test_e2e_modes.py` | A6 đổi orchestrator routing (`reset_index_node`) | Update routing assertions nếu có |
| `tests/test_orchestrator_maturity.py` | A6 — review_task node trả `{}` thay vì `{"_hitl_pause": True}` | Bỏ assertion về `_hitl_pause` field |
| Bất kỳ test nào dùng `RAG_API_URL` | A2/D1 đổi default port `8000` → `8005` | Update fixtures hoặc env override trong conftest |

### Phase B
| Test file | Tại sao có thể break | Action |
|---|---|---|
| `tests/test_planning_agent_coverage.py` | B5.5 thêm `callbacks` param vào `__init__` | Thêm `callbacks=[]` hoặc dùng default; backward-compatible nếu default=None |
| Bất kỳ test nào init `ScannerAgent(model_name, ...)` | B2 đổi signature → `ScannerAgent(scanner_url=None)` | Update constructor calls |
| Bất kỳ test nào parse `ScannerAgent.run_batch()` output | C4 đổi return từ `List[str]` → `List[Dict]` | Update parsers |
| `tests/test_rag_view_formatter.py`, `tests/integration/test_report_rag_flow.py`, `tests/test_rag_query_planner.py` | B12 thay đường gọi RAG (qua `RAGQueryPlanner` thay vì inline) | Verify output shape không đổi; nếu mock RAG thì point sang `RAGQueryPlanner` mock |
| Test gọi `AnalysisAgent(before_path=..., after_path=...)` | B8 bỏ `__init__` params | Update để dùng `AnalysisAgent().run(pre_scan=..., post_scan=...)` |
| Test import `assessment_agent` hoặc `ToolMakerAgent` | B11/B12.5 xóa file | Verify không có import (đã grep — 0 result) |
| **(v1.6)** Test import `from pdca.tools import REMEDIATION_TOOLS` etc. | B13 chuyển từ file sang package | Backward-compat shim — không cần đổi import path; nếu test sâu access internal → update sang `REGISTRY.get()` |
| **(v1.6)** Test parse `tool.invoke(...)` output expect string | B15 chuẩn hóa return dict — vài tool trước trả `json.dumps()` | Update assertions: `isinstance(result, dict)` thay vì `json.loads(result)` |
| **(v1.6)** Test mock `s3_prepare_replication` với invalid bucket | B15 fix bug T7 (NameError → ToolResult.failed) | Update assertion sang dict shape `{"success": False, "status": "failed"}` |
| **(v1.6 → SUPERSEDED v1.7)** Test gọi `s3_secure_transport("invalid; DROP TABLE--")` | B15 v1.7 đảm bảo invariant return dict — KHÔNG raise | Đã thay bằng row v1.7 bên dưới (assert `result["status"] == "failed"`) |
| **(v1.6)** Test access `plan["tool_id"]` hoặc `plan["params"]` từ `RemediationPlannerAgent.plan_remediation()` | B16 đổi key → `tool_name` / `tool_params` | Update key access |
| **(v1.6)** Test access `ScannerAgent.ALLOWED_GROUPS` class attr | B17 xóa class attr, dùng `settings.scanner_allowed_services` | Đổi sang `settings.scanner_allowed_services` hoặc remove assertion (default=None = no filter) |
| **(v1.6)** Test gọi `AVAILABLE_FUNCTIONS["remediate_s3_*"]` (alias key) | B14 alias key gone — `AVAILABLE_FUNCTIONS` giờ = `TOOLS_MAP` (key = tool.name) | Đổi key sang tool.name thật (e.g., `s3_block_account_public_access`) |
| **(v1.6)** Test gọi `start_scan_by_file` hoặc `s3_force_private_acl` | B18 xóa nếu verify 0 caller | Remove test hoặc giữ để đánh dấu API endpoint vẫn live (Phase D) |
| **(v1.7)** Test mong tool raise `ValueError` cho input invalid | B15 v1.7 fix invariant — tool LUÔN return dict (sanitize raise nội bộ, tool wrap → ToolResult.failed) | Đổi `with pytest.raises(ValueError)` → `assert result["status"] == "failed"` |
| **(v1.7) NEW**: Test ExecutionAgent guards (3 case mới) | B15 v1.7 thêm 3 guard cho execute_task | Test cases: (1) `tool_name` không có trong REGISTRY → status="error", (2) `tool_name` có category="knowledge" → status="error", (3) `tool_name` manual_only + decision="approve" → status="manual_required" (KHÔNG execute thật, AWS API ko bị gọi) |

### Phase C (v1.4 — inline nodes)
| Test file | Tại sao có thể break | Action |
|---|---|---|
| Mọi test invoke `build_graph()` | C7 chuyển `pdca/orchestrator.build_graph` → delegate `pdca/graph/graph.build_graph` | Verify import path vẫn work qua re-export |
| Test verify `MemorySaver` instance | C2 default thành SqliteSaver | Override với `get_checkpointer("memory")` trong test fixtures |
| Test mocks `MonitoringAgent.run()` | C5 dùng inline scan nodes thay vì `MonitoringAgent` | Mock `pdca.tools.AVAILABLE_FUNCTIONS["check_job_status"]` cho `scan_poll`; mock `ScannerAgent.run_batch` cho `scan_submit` |
| Test access `state["raw_findings"]` cho final findings | v1.4 đổi semantic: `raw_findings` là intermediate accumulator | Đổi sang `state["normalized_findings"]` |
| Test gọi `state["scan_job_ids"]` | v1.4 mark deprecated | Migrate sang `state["pending_jobs"]` keys hoặc `state["completed_jobs"]` keys |
| Test mocks single `scanning_node` | v1.4 split thành 3 nodes — không còn `scanning_node` | Update để mock 3 nodes hoặc test integration qua graph |
| Test HITL flow | C6 `interrupt_before=["review_task"]`, `route_review_task` không mutate state | Update để dùng `graph.update_state(...)` thay vì mutate trực tiếp |
| Test simulating crash mid-scan | v1.4 mới — verify checkpoint per poll | **TEST MỚI**: kill graph giữa `scan_poll`, resume, assert `pending_jobs` không restart từ submit |

### Phase D
| Test file | Tại sao có thể break | Action |
|---|---|---|
| Test gọi `requests.get("/scan/check")` etc. | D2 đổi sang POST + `/v1/` | Update URLs + HTTP method + body |
| Test polling job qua `/job/status?job_id=...` | D2 đổi sang `/v1/job/{job_id}` | Update path param style |
| Test rely on `MOCK_JOB_DATABASE` reset giữa runs | D3 dùng SQLite persistent | Add fixture cleanup: xóa `data/jobs/scanner_jobs.db` trong `setup`/`teardown` |
| Test CORS preflight | D4 thêm CORS middleware | Test mới (optional) |

### Smoke check sau mỗi phase
```bash
pytest tests/ -q --tb=short
# Track regression count vs trước phase
```

---

## Ghi chú quan trọng

> **Thứ tự làm**: R (reconcile) → A → B → C → D. Không làm ngược.
> D1 là ngoại lệ: làm song song với A2 (cùng liên quan đến settings).
>
> **R bắt buộc trước A**: Working tree dirty + multiple plan docs cần resolve trước, không refactor trên repo lộn xộn.
>
> **Không làm trong plan này**: Report subgraph, Risk Eval fan-out, Chatbot UI, Langfuse handler, pdca/api/ HTTP layer. Các thứ này đến sau khi plan này hoàn thành.
>
> **Test sau mỗi phase**: Chạy `pytest tests/ -q` để đảm bảo không break regression. Tham khảo "Test Impact Per Phase" để biết test nào sẽ cần update.
>
> **Commit convention**: Mỗi phase là 1 PR riêng. Mỗi agent fix là 1 commit riêng. R-task có thể gộp 1 PR cleanup.
>
> **D5 (RAG async cleanup)**: Không bắt buộc, làm cuối cùng nếu có thời gian.
>
> **Decisions thay đổi giữa version**: Xem changelog cuối file. Mọi quyết định cũ trong v1.0-v1.2 vẫn valid trừ khi version mới override.

---

*Plan version: 1.7 — 2026-04-26*
*v1.0: Tổng hợp từ session phân tích kiến trúc*
*v1.1: Bổ sung Phase D — API Hardening*
*v1.2: Review & fix trước implement — monitoring.py removed from node tree, graph/state.py explicit step, settings hoàn chỉnh, B5-B7 clarified, B11 assessment deprecated, B12 data_builder decision chốt, D2 backward compat đơn giản hóa, D3 WAL mode, entry conditions updated*
*v1.3: Verified vs codebase + 4 bug fixes + 2 gap fills + dead code cleanup:*
  - *NEW: Pre-implement Reconciliation section (R1-R4) — uncommitted files, multiple plans, existing rag_query_planner, dead code*
  - *FIX C2: SqliteSaver phải dùng `sqlite3.connect()` + `SqliteSaver(conn)`, KHÔNG `from_conn_string()` (context manager bug)*
  - *FIX C4: ScanState dùng `Dict[str, ScanJobMeta]` thay vì `Set[str]` (JSON-serializable + giữ job metadata)*
  - *FIX A4: Đổi behavior except hiện tại, KHÔNG thêm try/except mới (try/except đã tồn tại)*
  - *DOC C4: Subgraph checkpoint inheritance qua parent + `astream(subgraphs=True)`*
  - *NEW B5.5: planning_agent.py — gap thiếu trong Phase B v1.2*
  - *CHG B6: monitoring_agent.py KHÔNG cleanup logging — sắp xóa ở C5.1*
  - *CHG B11: assessment_agent.py XÓA luôn (verified 0 import), không deprecate*
  - *NEW B12.5: tools_maker.py XÓA (dead code)*
  - *NEW C5.1: explicit deletion step cho monitoring_agent.py*
  - *REWRITE B12: dùng existing RAGQueryPlanner thay vì re-implement fetch logic*
  - *CHG B2: ScannerAgent.run_batch() đổi return type → List[Dict] để giữ job metadata cho scan_subgraph*
  - *NEW Test Impact Per Phase section: liệt kê test sẽ break theo từng phase*
  - *Files table: thêm planning_agent.py, đánh dấu 3 file [D]Deleted, 1 file [E]Existing-cần-commit*
*v1.4: Pre-implement final pass — config package + scan loop architectural fix:*
  - *FIX A2: `pdca/config.py` (file) → `pdca/config/` (package) thật. Plan v1.3 viết "tạo `config/settings.py` + sửa `config.py`" sẽ FAIL import vì Python không cohabit file+package cùng tên. Step-by-step: `git rm config.py` → `mkdir config` → `settings.py` (Pydantic) → `__init__.py` (re-export backward-compat).*
  - *FIX C4: Bỏ `scan_subgraph` (decision #2 đảo ngược). Plan v1.3 viết "1 checkpoint per poll" nhưng `subgraph.invoke()` ĐỒNG BỘ KHÔNG checkpoint giữa các poll iteration. Inline 3 nodes `scan_submit / scan_poll / scan_collect` vào main graph để parent's SqliteSaver thật sự checkpoint mỗi entry vào scan_poll. Mất hierarchical subgraph trong sơ đồ nhưng đạt mục tiêu kỹ thuật.*
  - *FIX C1 state: tách `raw_findings` (Annotated accumulator, scan_poll append) vs `normalized_findings` (set once by scan_collect). Plan v1.3 dùng chung `completed_findings` field gây bug `[raw1, raw2, ..., normalized_packet]` do `operator.add` reducer = append KHÔNG replace. Thêm `pending_jobs/completed_jobs/scan_started_at/scan_poll_count` vào PDCAState. `scan_job_ids` mark deprecated.*
  - *DOC C5: 3 file mới scan_submit.py / scan_poll.py / scan_collect.py với code đầy đủ thay cho 1 scanning.py invoke subgraph.*
  - *DOC C6: build_graph topology cập nhật — wire 3 scan nodes + `route_scan_poll` conditional edge.*
  - *NEW decision #24-#26: config-package, raw/normalized-split, time.sleep tech-debt-acknowledgment.*
  - *Files table: `pdca/config.py [D]`, 3 scan_*.py [F], subgraphs/* gạch bỏ [X].*
  - *Architecture target tree + Graph topology diagram cập nhật để khớp inline design.*
  - *Test Impact Phase C: thêm test crash recovery mid-poll (mới); update mocks (không còn scanning_node single).*
*v1.5: Pre-implement final pass v2 — review feedback hardening:*
  - *FIX A2 (decision #29): thêm explicit `from pydantic_settings import BaseSettings, SettingsConfigDict` + `from pydantic import Field, AliasChoices, model_validator` đầu code block. requirements.txt thêm `pydantic-settings>=2.0`. Plan v1.4 dùng `BaseSettings` mà không import → ImportError.*
  - *FIX A2 (decision #30): `ollama_base_url` dùng `Field(validation_alias=AliasChoices("OLLAMA_BASE_URL", "OLLAMA_URL"))` để backward-compat với code cũ dùng env var `OLLAMA_URL`. Tránh silent regression cho user upgrade.*
  - *FIX C1 + C4 + C5 (decision #27): `scan_started_at` dùng `time.time()` (Unix epoch) thay vì `time.monotonic()` (process-local). Monotonic không survive SqliteSaver restart → timeout check vô nghĩa sau resume → âm thầm phá feature crash recovery mà v1.4 vừa fix. CRITICAL bug.*
  - *FIX C1 + C5 (decision #28): `raw_findings` bỏ reducer `Annotated[..., operator.add]`. scan_poll explicit `state.get("raw_findings", []) + new_raw`. scan_submit có thể reset bằng `[]`. Đồng nhất no-reducer semantic với pending_jobs/completed_jobs.*
  - *FIX Hook 1 + C5 pattern (decision #31): callbacks đọc `config.get("callbacks") or config.get("configurable", {}).get("callbacks", [])` — chuẩn LangChain RunnableConfig top-level + fallback configurable. Plan v1.4 chỉ check configurable → Langfuse silent broken.*
  - *FIX B10: thêm explicit task `callbacks` cho `ReportAgent.__init__` và `LLMWriter`. v1.4 chỉ "logging cleanup" — bỏ sót LLM init params.*
  - *FIX A2 + D4 (decision #32): CORS spec compliance — cấm combo `allow_origins=["*"]` + `allow_credentials=True` (browser block). Settings có validator auto-force `cors_allow_credentials=False` khi wildcard. D4 code đọc từ settings.*
  - *CLEANUP Files table: xóa stale `pdca/config.py [M]` entry (đã có `[D]` từ v1.4). Scope đầu file `pdca/config.py` → `pdca/config/`.*
  - *CLEANUP historical block: rút từ 207 dòng full code → 13 dòng tóm tắt lý do + git history reference. Tránh người implement copy nhầm code obsolete.*
  - *Decisions matrix mới: #27-#32 (6 quyết định review-driven).*
*v1.6: Tools layer restructure — pdca/tools.py (950 dòng monolithic) → pdca/tools/ package + chuẩn hóa:*
  - *NEW B13 (decision #33): tách `pdca/tools.py` → `pdca/tools/` package với 8 file mới (`__init__.py`, `registry.py`, `schemas.py`, `_common.py`, `scanner.py`, `knowledge.py`, `remediation/__init__.py`, `remediation/s3.py`). Step-by-step `git mv` → `mkdir` → tạo file mới → verify imports. Backward-compat shim qua `__init__.py` re-export.*
  - *NEW B14 (decision #34): `ToolRegistry` singleton thay 4 export lists overlap (`AVAILABLE_FUNCTIONS` dict alias-key, `SCANNER_AGENT_TOOLS`, `REMEDIATION_TOOLS`, `ALL_TOOLS`) + `TOOLS_MAP`. Mỗi tool tự register với metadata `category` + `manual_only`. `ALWAYS_MANUAL_TOOLS` set rời rạc trong `remediate_planner_agent.py` → flag `manual_only=True` ở registration.*
  - *NEW B15 (decision #35, T6/T7/T8/T10): chuẩn hóa mọi tool return `dict` (không `json.dumps()`). Thêm `ToolResult` builder + `sanitize_resource_id()` ở `_common.py`. FIX bug T7: `s3_prepare_replication` gọi `json.dump(result)` thiếu file handle → NameError + missing return → đổi sang `ToolResult.failed()`. T10: sanitize input để chặn IAM policy injection. T8: `print` → logger trong tools.*
  - *NEW B16 (decision #36, T3): `RemediationPlannerAgent.plan_remediation()` đổi key return từ `tool_id`/`params` → `tool_name`/`tool_params`. Xóa dịch ở `orchestrator.py:313-314`. Bug-magnet trước đây — rename 1 phía mà quên phía kia → silent break pipeline.*
  - *NEW B17 (decision #37, T4): `ScannerAgent.ALLOWED_GROUPS` (hardcode 9 services class attr) → `settings.scanner_allowed_services` (Optional[list], default None = no filter). Xóa `ALLOWED_GROUPS_LIST` (84 services, 0 import — dead config). Whitelist giờ configurable qua .env.*
  - *NEW B18 (T12): xóa 2 tool zero-usage sau verify (`start_scan_by_file`, `s3_force_private_acl`). REGISTRY giảm 18 → 16 tool.*
  - *Decisions matrix mới: #33-#37 (5 quyết định tools layer).*
  - *Files table: thêm 8 file mới `pdca/tools/*`, đánh dấu `pdca/tools.py [D]`, expand các agent đã đụng (remediate_planner ×3 phase, scanner ×3, analysis ×2, execution ×2, orchestrator ×4 commits).*
  - *Architecture target: thêm subtree `pdca/tools/` với comment cho tương lai (iam.py, ec2.py, rds.py).*
  - *Test Impact Phase B: thêm 7 row mới — backward-compat shim, dict return assertion, T7 bug fix shape, T10 ValueError, tool_name key migration, ALLOWED_GROUPS removal, dead tool removal.*
  - *Checkpoint Phase B: thêm 6 row mới verify tools layer (file→package, REGISTRY size, json.dumps cleanup, print=0, ALWAYS_MANUAL_TOOLS gone, manual_only flag work).*
*v1.7: Review polish trên v1.6 — 7 điểm:*
  - *FIX D1 (point 1): Phase D1 stale với `pdca/tools.py` (đã xóa ở B13). Đổi reference sang `pdca/tools/scanner.py` + `pdca/tools/knowledge.py`. Files Table xóa dòng `pdca/tools.py [M]` ở D1, thêm 2 entry mới cho 2 file con. Note rõ "B15 đã cover print cleanup — D1 không lặp".*
  - *FIX B14 (point 2): Bỏ field `aliases: list[str]` khỏi `ToolMeta` + param `aliases=` khỏi `register()` — field dead, `get()` không resolve, backward-compat đã handle qua `AVAILABLE_FUNCTIONS = TOOLS_MAP` shim. Cleanup dataclass import (bỏ `field`).*
  - *FIX B15 (point 3, CRITICAL invariant fix): Mâu thuẫn "mọi tool return dict" vs Exit "raise ValueError" → tool wrap `sanitize_*()` trong try/except, return `ToolResult.failed()` thay vì raise. ExecutionAgent LUÔN nhận dict — đảm bảo decision #35. Pattern code chi tiết trong B15.*
  - *FIX B15 (point 4): Đổi tên `sanitize_resource_id` → `sanitize_s3_bucket_name` — hàm dùng regex S3-specific, generic naming gây nhầm lẫn khi tương lai thêm IAM/EC2 tools. Thêm note rõ trong `_common.py`.*
  - *FIX B18 (point 5): Sửa lý do xóa `s3_force_private_acl` — lý do cũ ("không có entry trong AVAILABLE_FUNCTIONS → planner không pick") sai về cơ chế (planner đọc REMEDIATION_TOOLS list, không đọc AVAILABLE_FUNCTIONS dict). Lý do thực sự: **functional overlap** với `s3_disable_bucket_acls` (BucketOwnerEnforced là approach modern thay cho `put_bucket_acl ACL=private`).*
  - *NEW B15 (point 6, defense-in-depth): ExecutionAgent thêm 3 guard trước khi invoke tool: (G1) tool tồn tại trong REGISTRY, (G2) category=="remediation", (G3) `meta.manual_only` → refuse. REGISTRY là source of truth, không tin task["manual_required"] (HITL UI có thể override). Code pattern chi tiết + 3 test case mới.*
  - *FIX B14 (point 7): Exit count rigid (`len(scanner)=4`) → flexible — tùy B18 giữ/xóa `start_scan_by_file` thì scanner=3 hoặc 4. Đổi sang assertion structural ("không rỗng", "≥ N tool").*
  - *Test Impact Phase B: thêm 2 row v1.7 — (a) ValueError → dict invariant migration, (b) 3 ExecutionAgent guard test cases mới.*
  - *Files Table: thêm 2 entry `pdca/tools/scanner.py [M]` + `pdca/tools/knowledge.py [M]` cho D1 v1.7. Tổng files [M] = 19 (tăng 1).*
