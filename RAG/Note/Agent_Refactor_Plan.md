# PHÂN TÍCH & KẾ HOẠCH REFACTOR
# PlanningAgent & RiskEvaluationAgent

**Ngày:** 2026-03-27
**Phiên bản:** v1.0
**Scope:** `agents/planning_agent.py`, `agents/risk_evaluation_agent.py`, và các file liên quan

---

## MỤC LỤC

1. [Phân tích PlanningAgent](#1-phân-tích-planningagent)
2. [Phân tích RiskEvaluationAgent](#2-phân-tích-riskevaluationagent)
3. [Vấn đề chung (Cross-cutting)](#3-vấn-đề-chung-cross-cutting)
4. [Kế hoạch Refactor](#4-kế-hoạch-refactor)

---

## 1. PHÂN TÍCH PLANNINGAGENT

**File:** `agents/planning_agent.py` (233 dòng)

### 1.1 Kiến trúc hiện tại

```
PlanningAgent
├── __init__(model_name, api_key, base_url)
│     → Hardcode self.retrieval_api_url = "http://localhost:8111/retrieve"  ← DEAD URL
│     → Hardcode self.valid_services = [...] ← Trùng lặp với RAG constants
│
├── _clean_json(text) → Dict
├── _sanitize_service_name(raw_svc) → str
├── _sanitize_id(raw_id) → str
├── _call_retrieval_service(query, target_svc) → List[str]
│     → Hardcode URL http://localhost:8001/v1/retrieve/checks ← URL THỰC SỰ DÙNG
│
└── run(user_request) → Dict
      ├── Bước 0: Fast Track (regex detect check IDs)
      ├── Bước 1: LLM Translation (user request → intent)
      ├── Luồng 1: Group scan (nếu is_group_scan)
      ├── Luồng 2: RAG retrieval → LLM re-ranking
      └── Fallback: group scan
```

### 1.2 Đánh giá chi tiết

#### [PA-01] Không kế thừa BaseAgent — Thiết kế không nhất quán
- **Vấn đề:** Tất cả agents khác (Risk, Remediation, Report, ...) kế thừa `BaseAgent`. PlanningAgent là **ngoại lệ duy nhất**, tự tạo `ChatOllama` instance riêng.
- **Hệ quả:** Không thống nhất interface. `graph_orchestator.py:143` tạo PlanningAgent với signature khác các agent khác. Không dùng được `BaseAgent.call_llm()`.
- **Mức nghiêm trọng:** Trung bình

#### [PA-02] Hai URL hardcoded — một cái chết, một cái live
- **Vấn đề:**
  - Dòng 42: `self.retrieval_api_url = "http://localhost:8111/retrieve"` — **URL CHẾT**, không được dùng ở bất kỳ đâu trong file. Biến này tồn tại nhưng không bao giờ được reference.
  - Dòng 101: `url = "http://localhost:8001/v1/retrieve/checks"` — URL thực sự được dùng, nhưng hardcode inline trong method.
- **Hệ quả:** Gây nhầm lẫn khi đọc code. Dòng 42 cho tín hiệu sai. Developer mới sẽ tưởng agent dùng port 8111 nhưng thực tế dùng port 8001.
- **Mức nghiêm trọng:** Cao

#### [PA-03] `run()` là God Method — 84 dòng, 4 luồng logic trộn lẫn
- **Vấn đề:** Method `run()` (dòng 149-233) xử lý tất cả:
  1. Regex parsing (Fast Track)
  2. LLM call #1 (Translation)
  3. RAG API call
  4. LLM call #2 (Re-ranking)
  5. Fallback logic
  6. Error handling
- **Hệ quả:** Khó test từng phần riêng lẻ. Khó mở rộng (thêm 1 luồng mới = sửa cả method). Vi phạm Single Responsibility Principle.
- **Mức nghiêm trọng:** Cao

#### [PA-04] Check ID extraction logic bị duplicate
- **Vấn đề:** `_sanitize_id()` (dòng 82-98) thực hiện logic gần giống với `_sanitize_id()` conceptually, nhưng logic tương tự cũng có trong `_call_retrieval_service()` (dòng 137-141) khi clean IDs. Và regex ở `run()` dòng 155 (`re.findall(r'\b[a-z0-9]+_[a-z0-9_]+\b', ...)`) cũng là 1 dạng ID extraction.
- **Hệ quả:** 3 nơi xử lý check_id formatting → không consistent, khó maintain.
- **Mức nghiêm trọng:** Trung bình

#### [PA-05] LLM Re-ranking prompt nhận input nghèo
- **Vấn đề:** `RERANK_PROMPT` (dòng 30-35) nhận `candidates` là `List[str]` (chỉ check IDs), **không có metadata** (title, severity, service, description). LLM phải "đoán" check nào relevant chỉ dựa vào tên ID.
- **Hệ quả:** LLM re-ranking kém hiệu quả. Ví dụ: ID `s3_bucket_level_public_access_block` không nói rõ severity hay context → LLM không có đủ thông tin để rank.
- **Data flow:** `_call_retrieval_service()` trả về `List[str]` (dòng 144), nhưng RAG API response thực tế chứa `metadata` (severity, service, title) — bị bỏ qua hoàn toàn.
- **Mức nghiêm trọng:** Cao

#### [PA-06] Service whitelist cứng, không extensible
- **Vấn đề:** `self.valid_services` (dòng 50) hardcode 10 services. RAG System có `KNOWN_SERVICES` với 28 services tại `RAG/app/core/constants.py`.
- **Hệ quả:** Nếu user hỏi về `guardduty`, `waf`, `config`, ... PlanningAgent sẽ fallback về regex matching hoặc default `"s3"` — behavior sai.
- **Mức nghiêm trọng:** Trung bình

#### [PA-07] Không có fallback khi LLM parse fail
- **Vấn đề:** `_clean_json()` return `{}` khi parse fail (dòng 64). Sau đó `run()` dòng 174: `target_svc = self._sanitize_service_name(t_data.get("target_service", "s3"))` → default về `"s3"`.
- **Hệ quả:** Bất kỳ lỗi LLM nào cũng silently default về S3 scan. User hỏi "check IAM policies" mà LLM trả về JSON sai → agent sẽ scan S3 mà không báo lỗi.
- **Mức nghiêm trọng:** Cao

#### [PA-08] Agent được instantiate MỖI LẦN gọi node
- **Vấn đề:** `graph_orchestator.py:143` tạo `PlanningAgent()` mới mỗi khi `planning_node()` được gọi. Điều này có nghĩa mỗi lần pipeline chạy, agent + LLM instance được tạo mới.
- **Hệ quả:** Lãng phí resource. Không giữ được state giữa các lần gọi (nếu cần).
- **Mức nghiêm trọng:** Thấp (nhưng không clean)

#### [PA-09] Inconsistent indentation
- **Vấn đề:** Methods `_sanitize_id`, `_call_retrieval_service`, `run` dùng 8 spaces indent thay vì 4 spaces chuẩn Python (PEP 8). Còn `_clean_json`, `_sanitize_service_name` dùng đúng 4 spaces.
- **Hệ quả:** Code khó đọc, không consistent. Có khả năng copy-paste từ nguồn khác.
- **Mức nghiêm trọng:** Thấp

### 1.3 Data Flow — Điểm mất dữ liệu

```
RAG API Response (data.results):
┌─────────────────────────────────────────┐
│ {                                       │
│   "doc_id": "check:s3_bucket_...",      │ ← Được lấy
│   "score": 0.85,                        │ ← BỊ BỎ
│   "metadata": {                         │
│     "service": "s3",                    │ ← Dùng để filter, rồi BỎ
│     "severity": "high",                 │ ← BỊ BỎ ★
│     "title": "S3 Bucket Public...",     │ ← BỊ BỎ ★
│     "description": "Ensure S3..."       │ ← BỊ BỎ ★
│   }                                     │
│ }                                       │
└─────────────────────────────────────────┘
          │
          ▼ _call_retrieval_service()
    ["s3_bucket_public_access", ...]   ← Chỉ còn lại IDs (List[str])
          │
          ▼ RERANK_PROMPT
    LLM nhận List[str], không có context → Re-ranking kém ★
```

**Điểm mất dữ liệu:** `_call_retrieval_service()` dòng 118-144 chỉ extract `doc_id` → bỏ mất toàn bộ `score`, `severity`, `title`, `description`. Đây là **tổn thất lớn nhất** về chất lượng.

---

## 2. PHÂN TÍCH RISKEVALUATIONAGENT

**File:** `agents/risk_evaluation_agent.py` (292 dòng)

### 2.1 Kiến trúc hiện tại

```
RiskEvaluationAgent(BaseAgent)
├── __init__(model_name, api_key, base_url)
│     → Override self.llm (tạo ChatOllama mới với format="json" + callbacks)
│
├── get_llm_metrics() → Dict
├── _extract_json_from_text(text) → str
├── _fetch_risk_context_batch(check_ids) → Dict[str, Any]
│     → Hardcode URL http://localhost:8001/v1/context/build
│
└── run(normalized_findings) → list
      ├── Bước 1: Filter FAIL findings
      ├── Bước 2: Extract unique check_ids (complex regex logic)
      ├── Bước 3: Batch RAG fetch
      ├── Bước 4: Loop N findings × LLM call
      ├── Bước 5: Parse + merge AI output
      └── Bước 6: Sort by severity + score
```

### 2.2 Đánh giá chi tiết

#### [RA-01] Check ID extraction logic bị DUPLICATE trong cùng file
- **Vấn đề:** Logic extract `check_id` từ finding xuất hiện **2 lần** gần giống hệt nhau:
  - Dòng 159-180: Trong vòng lặp batch extraction (trước khi gọi RAG)
  - Dòng 196-204: Trong vòng lặp per-finding scoring (khi build llm_view)
- **Code smell:** 22 dòng logic regex copy-paste.
- **Hệ quả:** Nếu sửa logic extract ở 1 nơi mà quên nơi kia → inconsistency. Nếu normalizer output format thay đổi → phải sửa 2 chỗ.
- **Mức nghiêm trọng:** Cao

#### [RA-02] Normalizer đã có `event_code` nhưng agent không dùng
- **Vấn đề:** `normalizer.py` dòng 38-39 đã extract `event_code` (chính là Prowler check ID) và lưu vào normalized finding. Nhưng RiskEvaluationAgent **KHÔNG dùng** `finding.get("event_code")` — thay vào đó tự viết 22 dòng regex để extract lại từ `finding_id`/`uid`/`id`.
- **Root cause:** Agent viết trước khi normalizer được update, hoặc developer không biết normalizer đã cung cấp field này.
- **Data flow mismatch:**
  ```
  Normalizer output:
    {"event_code": "s3_bucket_public_access",    ← SẴN CÓ, nhưng bị ignore
     "finding_id": "prowler-aws-s3_bucket_public_access-123..."}

  RiskEvaluationAgent:
    cid = f.get("check_id")                      ← Không có field này
       or f.get("CheckID")                       ← Không có field này
       or f.get("checkId")                       ← Không có field này
    # Fallback → regex extract từ finding_id     ← Phức tạp, dễ lỗi
  ```
- **Mức nghiêm trọng:** Cao — Đây là lỗi thiết kế nghiêm trọng nhất.

#### [RA-03] N LLM calls — O(N) latency, không parallelizable
- **Vấn đề:** `run()` dòng 188-275 loop qua từng finding, gọi `self.llm.invoke()` **tuần tự**. Nếu có 30 FAIL findings và mỗi LLM call mất 3s → 90 giây chỉ cho bước risk eval.
- **Hệ quả:** Bottleneck lớn nhất trong pipeline. Latency tỷ lệ thuận với số findings.
- **Mức nghiêm trọng:** Cao

#### [RA-04] `ai_data.update(parsed)` — unsafe merge có thể ghi đè fields bất kỳ
- **Vấn đề:** Dòng 246: `ai_data.update(parsed)`. Nếu LLM trả về JSON có field bất kỳ (ví dụ `{"status": "PASS"}` do hallucination), nó sẽ ghi đè vào `ai_data` mà không validation.
- **Hệ quả:** LLM output không được validate → field bất ngờ có thể leak vào finding dict → downstream agents nhận data sai.
- **Mức nghiêm trọng:** Trung bình

#### [RA-05] `severity` field bị overwrite — mất traceability
- **Vấn đề:** Dòng 260: `"severity": ai_data.get("ai_severity", finding.get("severity"))`. Agent ghi đè field `severity` gốc bằng AI severity.
- **Mitigation có sẵn:** Dòng 265 lưu `"prowler_severity"`. Nhưng naming không rõ ràng — `severity` bây giờ là AI severity, phải biết `prowler_severity` mới là gốc.
- **Mức nghiêm trọng:** Thấp (đã có mitigation, nhưng naming nên cải thiện)

#### [RA-06] RAG context field name mismatch
- **Vấn đề:** Dòng 221: `"extended_description": rag_data.get("description", "")`. Nhưng `_fetch_risk_context_batch()` dòng 113-117 build `context_map` với keys: `severity`, `title`, `mappings` — **không có key `description`**.
- **Hệ quả:** `rag_context.extended_description` LUÔN là empty string `""`. Field này tồn tại trong LLM prompt nhưng không bao giờ có data.
- **Mức nghiêm trọng:** Trung bình

#### [RA-07] SYSTEM_PROMPT có ký tự rác
- **Vấn đề:** Dòng 41: `"Bạn là Chuyên gia An ninh mạng AWS (Senior AWS Security Analyst)._"` — có dấu `._` thừa cuối câu.
- **Hệ quả:** Không ảnh hưởng chức năng nhưng cho thấy prompt chưa được review kỹ.
- **Mức nghiêm trọng:** Thấp

#### [RA-08] `_fetch_risk_context_batch()` không check HTTP status
- **Vấn đề:** Dòng 98: `response = requests.post(url, json=payload, timeout=10)` rồi dòng 99: `data = response.json()`. Không có `response.raise_for_status()`. Nếu API trả về 500 với body JSON error → code vẫn parse bình thường → return empty context silently.
- **So sánh:** PlanningAgent dòng 115 có `response.raise_for_status()`.
- **Mức nghiêm trọng:** Trung bình

#### [RA-09] Inconsistent indentation (giống PA-09)
- **Vấn đề:** `_fetch_risk_context_batch()`, `run()` dùng 8 spaces indent thay vì 4.
- **Mức nghiêm trọng:** Thấp

#### [RA-10] `print()` thay vì `logging` — không configurable
- **Vấn đề:** Toàn bộ logging dùng `print()` với emoji. Không thể filter, disable, hoặc redirect output.
- **Mức nghiêm trọng:** Thấp (nhưng ảnh hưởng production readiness)

### 2.3 Data Flow — Phân tích luồng

```
normalized_findings (từ Normalizer)
  │
  │ Normalizer output fields:
  │ {finding_uid, finding_id, event_code, service,     ★ event_code = check_id
  │  resource_id, account_id, region, severity,
  │  status, description, remediation_text, remediation_url}
  │
  ▼ Bước 1: Filter status=="FAIL"
fail_findings
  │
  ▼ Bước 2: Extract check_ids  ← DUPLICATE LOGIC, KHÔNG DÙNG event_code
unique_check_ids
  │
  ▼ Bước 3: _fetch_risk_context_batch()
rag_context_map: {check_id → {severity, title, mappings}}
  │                                   ↑
  │                    ★ Không có "description" nhưng
  │                      LLM prompt reference "description"
  │
  ▼ Bước 4: PER-FINDING loop
  ┌──────────────────────────────────────────────┐
  │ For each finding:                             │
  │  ├─ Extract check_id ← DUPLICATE (lần 2)     │
  │  ├─ Lookup rag_context_map[check_id]          │
  │  ├─ Build llm_view (finding + rag_context)    │
  │  ├─ LLM.invoke() ← SEQUENTIAL, blocking      │
  │  ├─ Parse JSON output ← unsafe .update()      │
  │  └─ Merge into enriched_finding               │
  └──────────────────────────────────────────────┘
  │
  ▼ Bước 5: Sort by (severity_map, risk_score)
sorted_results → return
```

---

## 3. VẤN ĐỀ CHUNG (CROSS-CUTTING)

### 3.1 Bảng tổng hợp vấn đề

| ID | Agent | Vấn đề | Severity | Category |
|---|---|---|---|---|
| PA-01 | Planning | Không kế thừa BaseAgent | Trung bình | Architecture |
| PA-02 | Planning | 2 URL hardcoded, 1 URL chết | Cao | Configuration |
| PA-03 | Planning | God Method `run()` 84 dòng | Cao | Clean Code |
| PA-04 | Planning | Check ID logic duplicate | Trung bình | DRY |
| PA-05 | Planning | Re-ranking nhận input nghèo (chỉ IDs, mất metadata) | Cao | Data Flow |
| PA-06 | Planning | Service whitelist cứng (10/28 services) | Trung bình | Extensibility |
| PA-07 | Planning | LLM parse fail → silent default S3 | Cao | Error Handling |
| PA-08 | Planning | Agent instantiate mỗi lần node chạy | Thấp | Performance |
| PA-09 | Planning | Inconsistent indentation | Thấp | Code Style |
| RA-01 | Risk | Check ID extraction duplicate TRONG CÙNG FILE | Cao | DRY |
| RA-02 | Risk | Không dùng `event_code` từ normalizer (tự regex) | Cao | Data Flow |
| RA-03 | Risk | N sequential LLM calls → O(N) latency | Cao | Performance |
| RA-04 | Risk | `ai_data.update(parsed)` unsafe merge | Trung bình | Security |
| RA-05 | Risk | `severity` bị overwrite, naming unclear | Thấp | Data Integrity |
| RA-06 | Risk | `extended_description` luôn empty | Trung bình | Data Flow |
| RA-07 | Risk | Ký tự rác trong SYSTEM_PROMPT | Thấp | Code Quality |
| RA-08 | Risk | Không check HTTP status code | Trung bình | Error Handling |
| RA-09 | Risk | Inconsistent indentation | Thấp | Code Style |
| RA-10 | Risk | `print()` thay vì `logging` | Thấp | Observability |

### 3.2 Pattern lặp lại giữa 2 agents

| Pattern | Biểu hiện |
|---|---|
| **Hardcoded URLs** | Cả 2 agent đều hardcode RAG URL inline thay vì nhận từ config |
| **JSON parsing boilerplate** | `_clean_json()` và `_extract_json_from_text()` gần giống nhau — nên là shared util |
| **Check ID sanitization** | `_sanitize_id()` ở Planning, regex extraction ở Risk — cùng mục đích, khác implementation |
| **RAG response parsing** | Mỗi agent tự parse RAG response format riêng — nên abstract qua RAGClient |
| **Print-based logging** | Cả 2 dùng `print()` với emoji, không dùng `logging` module |
| **Error handling catch-all** | Cả 2 dùng `except Exception as e: print(...)` — swallow mọi lỗi |

---

## 4. KẾ HOẠCH REFACTOR

### 4.1 Tổng quan

Chia refactor thành **4 Refactor Slices (RS)**, theo thứ tự dependency:

```
RS-1: Shared Utilities & Infrastructure
  │
  ├──→ RS-2: Refactor PlanningAgent
  │
  └──→ RS-3: Refactor RiskEvaluationAgent
            │
            └──→ RS-4: Orchestrator Wiring & Cleanup
```

---

### RS-1: Shared Utilities & Infrastructure

**Mục tiêu:** Tạo foundation chung cho cả 2 agents, loại bỏ code duplicate.

**Giải quyết:** PA-01, PA-02, PA-04, PA-09, RA-01, RA-02, RA-09, RA-10, và các pattern chung ở 3.2.

#### Bước 1.1 — Extract `_extract_check_id(finding)` vào shared module

**Hiện tại:** 3 nơi có logic extract check_id:
- `planning_agent.py:155` (regex trong run)
- `risk_evaluation_agent.py:159-175` (batch extraction)
- `risk_evaluation_agent.py:196-204` (per-finding extraction)

**Đề xuất:** Tạo function `extract_check_id(finding: dict) -> str | None` trong `agents/shared/normalizer.py` (hoặc file mới `agents/shared/utils.py`).

Logic ưu tiên:
```
1. finding.get("event_code")            ← Normalizer ĐÃ CÓ, ưu tiên cao nhất
2. finding.get("check_id")              ← Nếu finding từ nguồn khác
3. Regex extract từ finding_id           ← Fallback cuối cùng
```

**Lợi ích:** Loại bỏ ~44 dòng duplicate code giữa 2 agents. Tận dụng `event_code` có sẵn → không cần regex.

**Tiêu chí hoàn thành:**
- Function tồn tại, return `str | None`
- RiskEvaluationAgent dùng function này → xóa 2 block regex
- PlanningAgent dùng function này cho Fast Track logic

#### Bước 1.2 — Extract `parse_llm_json(text)` vào shared module

**Hiện tại:**
- `planning_agent.py:52-64` — `_clean_json()`: regex `\{.*\}`, remove control chars
- `risk_evaluation_agent.py:82-89` — `_extract_json_from_text()`: regex `\{[\s\S]*\}`

**Đề xuất:** Tạo function `parse_llm_json(text: str) -> dict` trong `agents/shared/utils.py`. Merge logic tốt nhất từ cả 2:
```
1. Try: trích ```json ... ``` block
2. Try: regex \{[\s\S]*\}  (dotall)
3. Remove control characters
4. json.loads()
5. Return {} nếu fail (log warning)
```

**Tiêu chí hoàn thành:**
- Function tồn tại, return `dict` (never raise)
- Cả 2 agents import từ shared module

#### Bước 1.3 — Extract `sanitize_check_id(raw_id)` vào shared module

**Hiện tại:** `planning_agent.py:82-98` — `_sanitize_id()`

**Đề xuất:** Move vào `agents/shared/utils.py`. Dùng chung cho cả PlanningAgent và RAGClient (khi nào tạo).

#### Bước 1.4 — Setup logging thay print

**Đề xuất:** Mỗi agent tạo logger riêng:
```python
import logging
logger = logging.getLogger(__name__)
```

Replace `print(f"[PlanningAgent] ...")` → `logger.info(...)`, `logger.warning(...)`, `logger.debug(...)`.

**Lý do:** Cho phép config log level per-agent, redirect output, disable emoji cho production.

**Tiêu chí hoàn thành:**
- Không còn `print()` trong 2 agent files
- Console output giữ nguyên format khi `logging.basicConfig(level=INFO)`

#### Bước 1.5 — Chuẩn hoá indentation

**Đề xuất:** Format cả 2 files theo PEP 8 (4 spaces). Có thể dùng `black` hoặc `ruff format`.

**Tiêu chí hoàn thành:**
- Toàn bộ code trong 2 files dùng 4 spaces indent

---

### RS-2: Refactor PlanningAgent

**Mục tiêu:** Clean architecture, cải thiện data flow, tăng chất lượng re-ranking.

**Giải quyết:** PA-03, PA-05, PA-06, PA-07, PA-08.

#### Bước 2.1 — Kế thừa BaseAgent (hoặc giữ standalone có lý do)

**Option A (Khuyến nghị):** Kế thừa `BaseAgent`:
```python
class PlanningAgent(BaseAgent):
    def __init__(self, model_name, api_key, base_url):
        super().__init__(model_name, api_key, base_url)
        # Override self.llm với format="json"
        self.llm = ChatOllama(model=model_name, base_url=base_url, temperature=0, format="json")
```

**Option B:** Giữ standalone nhưng document rõ lý do (ví dụ: không cần OpenAI client từ BaseAgent).

**Tiêu chí hoàn thành:**
- PlanningAgent hoặc kế thừa BaseAgent, hoặc có docstring giải thích tại sao không

#### Bước 2.2 — Tách `run()` thành các private methods rõ ràng

Tách God Method `run()` thành 4 methods:

```python
def run(self, user_request: str) -> Dict[str, Any]:
    # Orchestrate 4 bước
    explicit = self._detect_explicit_checks(user_request)
    if explicit:
        return explicit

    intent = self._translate_intent(user_request)
    if intent.get("is_group_scan"):
        return self._build_group_plan(intent["target_service"])

    candidates = self._retrieve_candidates(user_request, intent)
    return self._rerank_and_select(user_request, candidates, intent["target_service"])

def _detect_explicit_checks(self, request: str) -> Dict | None:
    """Bước 0: Fast Track — detect check IDs trong user request."""

def _translate_intent(self, request: str) -> Dict:
    """Bước 1: LLM translation — user request → {target_service, is_group_scan, search_queries}."""

def _retrieve_candidates(self, request: str, intent: Dict) -> List[Dict]:
    """Bước 2: Gọi RAG, trả về candidates CÓ METADATA (không chỉ IDs)."""

def _rerank_and_select(self, request: str, candidates: List[Dict], target_svc: str) -> Dict:
    """Bước 3: LLM re-ranking với enriched context."""
```

**Lợi ích:**
- Mỗi method testable riêng lẻ
- Dễ debug: log rõ bước nào fail
- Dễ mở rộng: thêm bước mới = thêm method, không sửa run()

**Tiêu chí hoàn thành:**
- `run()` ≤ 20 dòng (orchestration only)
- Mỗi sub-method ≤ 30 dòng
- Unit test được cho từng method

#### Bước 2.3 — `_retrieve_candidates()` giữ metadata, trả về `List[Dict]`

**Vấn đề gốc:** PA-05 — metadata bị bỏ.

**Đề xuất:** Thay vì return `List[str]`, return `List[Dict]`:

```python
def _retrieve_candidates(self, request, intent) -> List[Dict]:
    # ... gọi RAG ...
    candidates = []
    for item in results:
        candidates.append({
            "check_id": sanitize_check_id(item.get("doc_id", "")),
            "title": item.get("metadata", {}).get("title", ""),
            "severity": item.get("metadata", {}).get("severity", ""),
            "service": item.get("metadata", {}).get("service", ""),
            "score": item.get("score", 0),
        })
    return candidates
```

**Impact trên re-ranking:** `RERANK_PROMPT` nhận đầy đủ context:
```
CANDIDATES (Enriched):
[
  {"check_id": "s3_bucket_public_access", "title": "S3 Bucket Public Access Block",
   "severity": "high", "service": "s3", "score": 0.85},
  ...
]
```

→ LLM có thể rank dựa trên severity, title, relevance score — **chất lượng tốt hơn đáng kể**.

**Tiêu chí hoàn thành:**
- `_retrieve_candidates()` trả về `List[Dict]` với ít nhất `check_id`, `title`, `severity`
- `RERANK_PROMPT` được cập nhật nhận enriched candidates
- Re-ranking output quality ≥ baseline (verify bằng test)

#### Bước 2.4 — Cải thiện error handling: không silent default S3

**Đề xuất:** Khi LLM translation fail, **log rõ ràng** và trả về plan có `error` field:

```python
def _translate_intent(self, request):
    raw = (prompt | self.llm | StrOutputParser()).invoke({"request": request})
    parsed = parse_llm_json(raw)
    if not parsed or "target_service" not in parsed:
        logger.warning("LLM translation failed. Raw output: %s", raw[:200])
        # Fallback: dùng keyword matching thay vì default S3
        svc = self._infer_service_from_keywords(request)
        return {"target_service": svc, "is_group_scan": True, "search_queries": []}
    return parsed
```

Thêm `_infer_service_from_keywords()`: scan request cho known service names trước khi default.

**Tiêu chí hoàn thành:**
- LLM parse fail → log WARNING với raw output
- Fallback dùng keyword matching trước khi default

#### Bước 2.5 — Mở rộng service whitelist

**Đề xuất:** Load services từ config thay vì hardcode:

```python
# Option A: Import từ RAG constants (nếu RAG là dependency)
from RAG.app.core.constants import KNOWN_SERVICES

# Option B: Define list đầy đủ hơn trong config
VALID_SERVICES = ['s3', 'iam', 'ec2', 'rds', 'vpc', 'lambda', 'cloudtrail',
                  'kms', 'eks', 'sns', 'sqs', 'guardduty', 'waf', 'config',
                  'cloudwatch', 'secretsmanager', 'dynamodb', 'elasticache', ...]
```

**Tiêu chí hoàn thành:**
- Whitelist ≥ 20 services (covering Prowler supported services)

---

### RS-3: Refactor RiskEvaluationAgent

**Mục tiêu:** Loại bỏ code duplicate, fix data flow, cải thiện performance.

**Giải quyết:** RA-01, RA-02, RA-03, RA-04, RA-05, RA-06, RA-07, RA-08.

#### Bước 3.1 — Dùng `event_code` thay vì regex extraction

**Thay đổi cốt lõi:**

```python
# TRƯỚC (22 dòng regex × 2 lần):
cid = f.get("check_id") or f.get("CheckID") or f.get("checkId")
if not cid:
    raw_str = f.get("finding_id") or f.get("uid") or ...
    match = re.search(r'prowler-[^-]+-([a-z0-9_]+)-\d+', raw_str)
    ...

# SAU (1 dòng, dùng shared function):
from agents.shared.utils import extract_check_id
cid = extract_check_id(finding)  # Ưu tiên event_code → regex fallback
```

**Impact:** Xóa ~44 dòng code, xóa dependency trùng lặp.

**Tiêu chí hoàn thành:**
- `run()` không còn inline regex cho check_id extraction
- Import `extract_check_id` từ shared module
- Test: input normalized finding → output đúng check_id

#### Bước 3.2 — Tách `run()` thành methods rõ ràng

```python
def run(self, normalized_findings: list) -> list:
    fail_findings = self._filter_fail_findings(normalized_findings)
    if not fail_findings:
        return []

    rag_context_map = self._fetch_rag_context(fail_findings)
    scored_findings = self._score_findings(fail_findings, rag_context_map)
    return self._sort_by_priority(scored_findings)

def _filter_fail_findings(self, findings: list) -> list:
    """Filter chỉ lấy status=FAIL."""

def _fetch_rag_context(self, findings: list) -> Dict[str, Any]:
    """Extract unique check_ids → batch RAG call → return context map."""

def _score_single_finding(self, finding: dict, rag_data: dict) -> dict:
    """Build LLM prompt → invoke → parse → merge vào finding."""

def _score_findings(self, findings: list, rag_context_map: dict) -> list:
    """Loop qua findings, gọi _score_single_finding cho từng cái."""

def _sort_by_priority(self, findings: list) -> list:
    """Sort by (severity, risk_score) desc."""
```

**Tiêu chí hoàn thành:**
- `run()` ≤ 15 dòng
- Mỗi sub-method ≤ 30 dòng

#### Bước 3.3 — Fix `extended_description` luôn empty

**Nguyên nhân gốc:** `_fetch_risk_context_batch()` dòng 113-117 build context_map với:
```python
context_map[clean_id] = {
    "severity": f.get("severity"),
    "title": f.get("title"),
    "mappings": []
}
```
Không có key `"description"`. Nhưng dòng 221: `rag_data.get("description", "")`.

**Đề xuất:** Thêm `"title"` vào llm_view thay vì `"extended_description"` (vì RAG thực sự trả về `title`, không phải `description`):

```python
"rag_context": {
    "official_severity": rag_data.get("severity", "Unknown"),
    "check_title": rag_data.get("title", ""),          # ← Fix: dùng đúng field
    "compliance_mappings": rag_data.get("mappings", []),
}
```

**Tiêu chí hoàn thành:**
- LLM prompt nhận được `check_title` non-empty khi RAG data available
- Không còn field luôn-empty trong prompt

#### Bước 3.4 — Validate LLM output thay vì unsafe merge

**Thay đổi:**

```python
# TRƯỚC:
ai_data.update(parsed)  # parsed có thể chứa bất kỳ field nào

# SAU:
ALLOWED_AI_FIELDS = {"ai_severity", "ai_risk_score", "ai_reasoning"}
validated = {k: v for k, v in parsed.items() if k in ALLOWED_AI_FIELDS}

# Validate values
if validated.get("ai_severity") not in ("Critical", "High", "Medium", "Low"):
    validated["ai_severity"] = ai_data["ai_severity"]  # keep default
if not isinstance(validated.get("ai_risk_score"), int) or not (0 <= validated["ai_risk_score"] <= 10):
    validated["ai_risk_score"] = ai_data["ai_risk_score"]

ai_data.update(validated)
```

**Tiêu chí hoàn thành:**
- Chỉ 3 fields được phép update từ LLM output
- `ai_severity` phải thuộc enum, `ai_risk_score` phải là int 0-10
- LLM output với fields lạ bị ignore

#### Bước 3.5 — Fix SYSTEM_PROMPT ký tự rác + cải thiện rubric

**Thay đổi:**
- Xoá `._` thừa ở dòng 41
- Thêm instruction rõ ràng hơn về cách dùng `rag_context`:

```
LƯU Ý QUAN TRỌNG:
- Tham khảo "rag_context.check_title" để hiểu rõ lỗ hổng.
- Tham khảo "rag_context.official_severity" — nếu official_severity là "high" hoặc "critical",
  ai_risk_score KHÔNG NÊN dưới 7.
- Tham khảo "rag_context.compliance_mappings" — nếu có mappings, lỗ hổng này vi phạm
  compliance framework → tăng điểm thêm 1-2.
```

**Tiêu chí hoàn thành:**
- Không còn ký tự rác
- Prompt có hướng dẫn cụ thể cách dùng từng field trong rag_context

#### Bước 3.6 — Thêm HTTP status check trong `_fetch_risk_context_batch()`

**Thay đổi:**
```python
response = requests.post(url, json=payload, timeout=10)
response.raise_for_status()  # ← Thêm dòng này
data = response.json()
```

**Tiêu chí hoàn thành:**
- HTTP errors (4xx, 5xx) được catch và log rõ ràng
- Return `{}` khi API error (behavior giữ nguyên, nhưng log tốt hơn)

#### Bước 3.7 (Optional/Future) — Parallel LLM calls cho performance

**Vấn đề:** RA-03 — N sequential calls.

**Đề xuất (Phase sau):** Dùng `asyncio` hoặc `ThreadPoolExecutor` cho parallel LLM calls:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def _score_findings(self, findings, rag_context_map):
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(self._score_single_finding, f, rag_context_map.get(extract_check_id(f), {})): f
            for f in findings
        }
        results = []
        for future in as_completed(futures):
            results.append(future.result())
        return results
```

**Lý do đặt Phase sau:** Cần verify Ollama xử lý concurrent requests tốt. Cần test kỹ. Đây là optimization, không phải bug fix.

**Tiêu chí hoàn thành:**
- Latency giảm ≥ 50% khi ≥ 4 findings
- Output identical với sequential mode

---

### RS-4: Orchestrator Wiring & Cleanup

**Mục tiêu:** Cập nhật cách orchestrator khởi tạo và gọi 2 agents.

#### Bước 4.1 — Xoá biến chết `RETRIEVAL_API_URL`

`graph_orchestator.py:37` — `RETRIEVAL_API_URL = "http://localhost:8111/retrieve"` không được dùng bởi bất kỳ code nào. Xóa.

#### Bước 4.2 — Agents nhận config qua constructor thay vì hardcode

```python
# planning_node: truyền config
agent = PlanningAgent(
    model_name=OLLAMA_MODEL,
    api_key=OLLAMA_API_KEY,
    base_url=OLLAMA_BASE_URL,
    rag_base_url=RAG_API_URL,        # ← Mới
)

# risk_evaluation_node: tương tự
risk_agent = RiskEvaluationAgent(
    OLLAMA_MODEL, OLLAMA_API_KEY, OLLAMA_BASE_URL,
    rag_base_url=RAG_API_URL,        # ← Mới
)
```

#### Bước 4.3 (Optional) — Agent singleton thay vì recreate mỗi node call

```python
# Tạo 1 lần ở module level hoặc trong builder function
_planning_agent = None

def get_planning_agent():
    global _planning_agent
    if _planning_agent is None:
        _planning_agent = PlanningAgent(...)
    return _planning_agent
```

Hoặc đơn giản hơn: tạo agents ở top-level, truyền vào nodes.

---

### 4.2 Thứ tự thực hiện & Dependencies

```
RS-1 (Shared Utils)        ← LÀM TRƯỚC, không dependency
  │
  ├──→ RS-2 (PlanningAgent Refactor)     ← Depend RS-1
  │
  └──→ RS-3 (RiskEvalAgent Refactor)     ← Depend RS-1
            │
            └──→ RS-4 (Orchestrator)     ← Depend RS-2 + RS-3
```

**RS-2 và RS-3 có thể làm song song** sau khi RS-1 xong.

### 4.3 Checklist tổng hợp

| # | Bước | Giải quyết issues | Priority |
|---|---|---|---|
| 1.1 | Extract `extract_check_id()` | RA-01, RA-02, PA-04 | P0 |
| 1.2 | Extract `parse_llm_json()` | Cross-cutting | P0 |
| 1.3 | Extract `sanitize_check_id()` | PA-04 | P0 |
| 1.4 | Setup logging | RA-10 | P1 |
| 1.5 | Fix indentation | PA-09, RA-09 | P1 |
| 2.1 | PlanningAgent kế thừa BaseAgent | PA-01 | P1 |
| 2.2 | Tách `run()` thành methods | PA-03 | P0 |
| 2.3 | `_retrieve_candidates()` giữ metadata | PA-05 | P0 |
| 2.4 | Error handling, không silent default S3 | PA-07 | P0 |
| 2.5 | Mở rộng service whitelist | PA-06 | P1 |
| 3.1 | Dùng `event_code` thay regex | RA-02 | P0 |
| 3.2 | Tách `run()` thành methods | RA-01 | P0 |
| 3.3 | Fix `extended_description` empty | RA-06 | P0 |
| 3.4 | Validate LLM output | RA-04 | P0 |
| 3.5 | Fix SYSTEM_PROMPT | RA-07 | P1 |
| 3.6 | HTTP status check | RA-08 | P0 |
| 3.7 | Parallel LLM calls | RA-03 | P2 (Future) |
| 4.1 | Xoá `RETRIEVAL_API_URL` chết | PA-02 | P0 |
| 4.2 | Config injection qua constructor | PA-02, PA-08 | P0 |
| 4.3 | Agent singleton | PA-08 | P2 (Optional) |

**Tổng:** 9 P0 (phải làm) + 5 P1 (nên làm) + 2 P2 (optional/future)

---

*Tài liệu này phân tích dựa trên source code thực tế tại commit hiện tại. Cập nhật khi implement.*
