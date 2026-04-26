# MVP Plan — Section-aware Multi-query RAG for Report Agent

> **Status:** Draft v1.1 — 2026-04-22 (updated after codebase analysis — OQ1–OQ4 resolved)
> **Owner:** Phu
> **Scope:** MVP (demo-ready) — 3 query types: Q1 (check lookup), Q2 (capability theme), Q3 (remediation how-to)
> **Deadline mục tiêu:** 4.5–6.5 ngày làm việc (cập nhật sau khi resolve OQ1–OQ4, xem §13.2)
> **Mục đích tài liệu:** Source of truth cho việc triển khai. Mọi quyết định kỹ thuật bám theo file này.

---

## 0. Bối cảnh & Mục tiêu

### 0.1 Vấn đề hiện tại

Report agent hiện chỉ gọi `rag.build_context(check_ids=[...])` một lần duy nhất trong [pdca/orchestrator.py:651](../pdca/orchestrator.py#L651). Bundle trả về dùng chung cho cả 4 section (executive / fail / pass / recommendation). Hệ quả:

- LLM bịa **remediation commands** ở section khuyến nghị (rủi ro cao nhất).
- **Pass analysis** không có grounding (RAG chỉ tập trung fail findings).
- Không khai thác corpus đã có: `maturity_capabilities.json`, HyDE module, mapping tables.
- Single query không đủ context cho LLM viết report phong phú.

### 0.2 Mục tiêu MVP

| # | Goal | Acceptance criteria |
|---|---|---|
| G1 | Report agent phát **3 loại query** chuyên biệt tới RAG | `rag_query_planner.py` thực thi Q1+Q2+Q3 song song, log chứng minh |
| G2 | Pass analysis + Recommendation **có grounding**, giảm hallucination | Benchmark faithfulness ≥ baseline + 10% |
| G3 | Không break pipeline hiện tại, có rollback | Flag `MULTI_QUERY_MODE` default `False`; tests cũ pass |
| G4 | Có số liệu so sánh cho thesis | Bảng metrics baseline vs MVP + ablation Q1 / Q1+Q2 / Q1+Q3 / Q1+Q2+Q3 |

### 0.3 Non-goals (gác lại Post-MVP)

- Q4 (compliance mapping), Q5 (maturity gap), Q6 (incident context)
- Crawl thêm nguồn (AWS docs, CIS full, NIST)
- Schema migration toàn phần — MVP dùng additive fields + optional endpoints
- UI/dashboard thay đổi

---

## 1. Kiến trúc MVP

### 1.1 Sơ đồ flow

```
Orchestrator (pdca/orchestrator.py)
        │
        ▼
Report Agent (pdca/agents/report_agent.py)
        │
        ▼
RAGQueryPlanner (NEW: pdca/agents/report_module/rag_query_planner.py)
        │  plan → execute(parallel asyncio.gather)
        ▼
RAGClient (pdca/agents/shared/rag_client.py)
        │  HTTP POST /v1/retrieve/report_context
        ▼
RAG Service (FastAPI, port 8005)
        │
        ├─► Q1 endpoint  /v1/retrieve/check          (existing — wrap build_context)
        ├─► Q2 endpoint  /v1/retrieve/capability     (NEW)
        └─► Q3 endpoint  /v1/retrieve/remediation    (NEW)
        │
        ▼
  ReportContextBundle  →  RAGViewFormatter (refactored)
        │
        ▼
  LLM Writer (4 sections)  →  final_report.{md,html,pdf}
```

### 1.2 Hai lựa chọn thiết kế & quyết định

**Lựa chọn A: Một wrapper endpoint `/v1/retrieve/report_context`** (CHOSEN)
- RAG side tự orchestrate Q1+Q2+Q3 song song.
- Client chỉ gọi 1 HTTP request → latency thấp, dễ cache, ít thay đổi phía client.
- Trade-off: thêm 1 route aggregate phía RAG.

**Lựa chọn B: Client gọi song song 3 endpoints**
- Logic aggregation phía client → code client phức tạp hơn.
- Nhiều HTTP overhead (3 connection).
- Bỏ.

→ **Chốt:** dùng Lựa chọn A. Endpoint lẻ (Q1/Q2/Q3) vẫn expose để benchmark riêng từng loại.

### 1.3 Data contract tổng thể

**Request** (client → RAG):
```python
POST /v1/retrieve/report_context
{
  "check_ids": ["s3_bucket_public_access_block", ...],
  "domains": ["s3", "iam"],           # from scope_detector
  "severity_map": {"s3_bucket_public_access_block": "HIGH", ...},
  "include_q2": true,
  "include_q3": true,
  "top_k_check": 10,
  "top_k_capability": 5,
  "top_k_remediation": 3
}
```

**Response** (`ReportContextBundle`):
```python
{
  "check_findings":    [ReportFinding, ...],         # Q1 (existing shape)
  "control_themes":    [ReportCapability, ...],      # Q1 (existing shape)
  "capability_details":[ReportCapabilityDetail, ...],# Q1 (existing shape)
  "capability_themes": [CapabilityTheme, ...],       # Q2 (NEW)
  "remediations":      [RemediationGuide, ...],      # Q3 (NEW)
  "confidence":        "high"|"medium"|"low",
  "diagnostics": {
    "q1_latency_ms": 120, "q2_latency_ms": 80,
    "q3_latency_ms": 200, "cache_hits": 0
  }
}
```

---

## 2. Phase 1 — Baseline Measurement *(0.5 ngày)*

### 2.1 Tại sao cần

Không có baseline → không chứng minh được MVP tốt hơn. Phase này **bắt buộc không skip**.

### 2.2 Tasks

| ID | Task | File | Output |
|---|---|---|---|
| T1.1 | Chạy benchmark v3 với config hiện tại | [benchmarks/llm_generation/run_report_benchmark_v3.py](../benchmarks/llm_generation/run_report_benchmark_v3.py) | `benchmarks/llm_generation/results/baseline_single_query.json` |
| T1.2 | Ghi lại 3 gap lớn nhất (qualitative) | đọc `benchmark_outputs/` | `docs/thesis-notes/baseline_gaps.md` |
| T1.3 | Decide concrete fields Q2/Q3 phải trả | dựa vào T1.2 | Update §3.2 §3.3 của file này nếu cần |

### 2.3 DoD Phase 1

- [ ] File `baseline_single_query.json` tồn tại với đủ metrics.
- [ ] File `baseline_gaps.md` liệt kê ít nhất 3 vấn đề cụ thể (ví dụ: "LLM bịa lệnh `aws s3api put-bucket-encryption --...`").
- [ ] Confirm schema Q2/Q3 trong plan này có giải quyết được gap đã phát hiện.

---

## 3. Phase 2 — RAG Side: Add Q2 & Q3 *(2 ngày)*

### 3.1 Nơi đặt code

| Layer | File | Change type |
|---|---|---|
| Routes | [RAG/app/api/routes/retrieve.py](../RAG/app/api/routes/retrieve.py) | Add 3 handlers |
| Models | [RAG/app/core/models.py](../RAG/app/core/models.py) | Add 4 Pydantic classes |
| Service | `RAG/app/services/report_context_service.py` | **NEW** file |
| Config | [RAG/app/core/scoring_config.json](../RAG/app/core/scoring_config.json) | Add Q2/Q3 top_k defaults |
| Tests | [RAG/tests/](../RAG/tests/) | Add `test_report_context.py` |

### 3.2 Q2 — Capability Theme Query *(0.5 ngày)*

**Endpoint:** `POST /v1/retrieve/capability`

**Input schema** (`CapabilityQueryRequest`):
```python
domain: str                    # "s3" | "iam" | "ec2" | ...
status: Literal["pass","fail","mixed"]
top_k: int = 5
```

**Output schema** (`CapabilityTheme`):
```python
domain: str
narrative: str                  # 2-3 câu overview
common_pitfalls: list[str]      # max 5
baselines: list[str]            # CIS/Well-Architected references, max 5
citations: list[Citation]       # {source, url, section}
```

**Retrieval strategy:**
- Semantic search trên [RAG/data/normalized/maturity_capabilities.json](../RAG/data/normalized/maturity_capabilities.json) (78 capabilities).
- Filter theo `domain` tag sau khi backfill (xem sub-task bên dưới), fallback keyword match trên `capability_id` + `retrieval_text`.
- Rerank bằng reranker có sẵn ([RAG/app/retrieval/reranker.py](../RAG/app/retrieval/reranker.py)).

**Implementation notes:**
- Reuse `ContextService` + `MaturityService` có sẵn, không viết retrieval mới.
- Các field sẵn có và coverage (đã đo 2026-04-22):
  - `stage`: **100%** (4 stages: `1 quickwins` / `2 foundational` / `3 efficient` / `4 optimized`)
  - `recommended_practices`: **91%** (71/78)
  - `risk_explanation`: **51%** (40/78)
  - `capability_id`, `keywords`: 100%
  - `domain`: **0% populated** dù schema đã khai báo → **cần backfill**

**Sub-task 2.1a — Backfill `domain` (BẮT BUỘC, +0.5 ngày):**
- File mới: `RAG/scripts/backfill_capability_domain.py`
- Logic derive domain từ 3 nguồn (ưu tiên thứ tự):
  1. Regex extract AWS service name từ `capability_id` (whitelist: `s3`, `iam`, `ec2`, `cloudfront`, `rds`, `guardduty`, `kms`, `vpc`, `cloudtrail`, `cloudwatch`, `resilience_hub`, …)
  2. Keyword match trên `keywords[]` + `capability_name`
  3. Fallback: `domain = "general"` (cho capabilities cross-service như `detect_common_threats`)
- Output: ghi đè `maturity_capabilities.json` in-place, commit vào git để reproducible.
- Validation: unit test golden samples (≥10 capabilities) trong `RAG/tests/test_domain_backfill.py`.
- Re-run indexing sau backfill: `python RAG/scripts/build_all.py`.

### 3.3 Q3 — Remediation How-to Query *(1 ngày)*

**Endpoint:** `POST /v1/retrieve/remediation`

**Input schema** (`RemediationQueryRequest`):
```python
check_id: str
severity: Literal["CRITICAL","HIGH","MEDIUM","LOW"]
cloud_context: dict | None = None    # optional: {region, account_type}
top_k: int = 3
```

**Output schema** (`RemediationGuide`):
```python
check_id: str
steps: list[RemediationStep]          # order, type (cli|iac|console), snippet, prerequisite
rollback: str | None
effort: Literal["low","medium","high"]
side_effects: list[str]
citations: list[Citation]
```

**Corpus coverage (đã đo 2026-04-22 — 577 prowler checks):**
- `remediation` field: **100%** (577/577) — lưu dưới dạng **string blob serialized dict**, ví dụ:
  `"{'CLI': 'aws cloudfront ...', 'NativeIaC': '...', 'Other': '...', 'Terraform': '...'}"`
- `remediation_recommendation` (narrative free-text): **100%**
- `remediation_url`: **99%** (573/577)
- ✅ Corpus **dư sức** cho Q3, không cần crawl thêm ở MVP.

**Retrieval strategy:**
1. **Parse step (BẮT BUỘC trước Q3):** convert string blob → structured dict trong [RAG/app/ingestion/normalizers.py](../RAG/app/ingestion/normalizers.py).
   - Dùng `ast.literal_eval` (an toàn hơn `eval`) để parse.
   - Output schema mới cho normalized record: `remediation_code: {cli, terraform, native_iac, other}` (dict thay vì string).
   - Re-run `python RAG/scripts/build_all.py` để rebuild index.
2. Expand `check_id` → natural query qua HyDE ([RAG/app/retrieval/hyde.py](../RAG/app/retrieval/hyde.py)) — ví dụ:
   `"s3_bucket_public_access_block"` → `"how to enable S3 bucket public access block using AWS CLI or Terraform"`.
3. Hybrid retrieval (BM25 + vector) trên `remediation_code` + `remediation_recommendation`.
4. Fallback: nếu parse fail cho 1 check → trả `steps=[]` + log warning, KHÔNG fabricate.

**Tests bắt buộc:**
- `RAG/tests/test_remediation_parser.py`: parse 10 samples thật, assert có `cli` hoặc `other` non-empty.
- Edge case: check với CLI rỗng (`'CLI': ''`) nhưng `NativeIaC` non-empty → vẫn trả được step.

### 3.4 Wrapper endpoint `/v1/retrieve/report_context` *(0.5 ngày)*

**File mới:** `RAG/app/services/report_context_service.py`

```python
class ReportContextService:
    async def build(self, req: ReportContextRequest) -> ReportContextBundle:
        q1_task = asyncio.create_task(self._q1_check(req))
        q2_task = asyncio.create_task(self._q2_capability(req)) if req.include_q2 else None
        q3_task = asyncio.create_task(self._q3_remediation(req)) if req.include_q3 else None
        results = await asyncio.gather(q1_task, q2_task, q3_task, return_exceptions=True)
        return self._merge(results, req)
```

- **Parallel** bằng `asyncio.gather` (FastAPI đã async).
- **Per-query timeout** 10s, tổng timeout 15s.
- **Graceful degradation**: nếu Q2 hoặc Q3 fail, Q1 vẫn trả → bundle partial (confidence="medium").
- **In-memory cache** (TTL 60s) key = sorted tuple of check_ids+domains. Cache đơn giản `dict` + threading lock (đủ cho MVP, không cần Redis).

### 3.5 Tests Phase 2

File mới: `RAG/tests/test_report_context.py`

| Test | Mục đích |
|---|---|
| `test_q2_returns_domain_narrative` | Q2 với `domain="s3"` có non-empty narrative |
| `test_q3_returns_remediation_steps_for_known_check` | Q3 với check_id có `Remediation.Code` → steps > 0 |
| `test_q3_empty_when_no_remediation_in_corpus` | Check_id không có Remediation → `steps=[]`, không bịa |
| `test_wrapper_parallel_executes_all` | Wrapper gọi cả 3, diagnostics latency > 0 |
| `test_wrapper_degrades_when_q2_fails` | Mock Q2 raise → Q1 vẫn trả, confidence="medium" |
| `test_wrapper_cache_hit` | Gọi 2 lần cùng input → lần 2 `cache_hits=1` |

### 3.6 DoD Phase 2

- [ ] 3 endpoints mới trả đúng schema, có OpenAPI docs ở `/docs`.
- [ ] 6 tests pass.
- [ ] `curl` manual test OK (script `scripts/smoke_rag_multi_query.sh` — NEW).
- [ ] Không break tests cũ: `pytest RAG/tests/ -q`.

---

## 4. Phase 3 — Report Agent Side *(2 ngày)*

### 4.1 File changes

| File | Change type |
|---|---|
| `pdca/agents/report_module/rag_query_planner.py` | **NEW** |
| [pdca/agents/report_module/rag_formatter.py](../pdca/agents/report_module/rag_formatter.py) | Refactor `for_*()` methods |
| [pdca/agents/shared/rag_client.py](../pdca/agents/shared/rag_client.py) | Add `build_report_context()` method |
| [pdca/config.py](../pdca/config.py) | Add `MULTI_QUERY_MODE` env flag (default `False`) |
| [pdca/orchestrator.py](../pdca/orchestrator.py) | Branch on flag tại L651 |
| [pdca/agents/report_module/scope_detector.py](../pdca/agents/report_module/scope_detector.py) | Expose `detected_domains` cho planner |

### 4.2 `RAGQueryPlanner` *(0.5 ngày)*

```python
# pdca/agents/report_module/rag_query_planner.py
class RAGQueryPlanner:
    def __init__(self, rag_client: RAGClient):
        self.client = rag_client

    def plan(
        self,
        findings: list[dict],
        scope_domains: list[str],
    ) -> ReportContextRequest:
        """Dedup check_ids, dedup domains, build severity_map."""

    def execute(self, req: ReportContextRequest) -> ReportContextBundle:
        """Call client.build_report_context, handle fallback."""
```

**Rules:**
- Dedup `check_ids` (order-preserving).
- Dedup `domains` — derive từ `scope_detector` output; nếu empty → fallback `["all"]`.
- `severity_map` từ findings.
- Nếu `MULTI_QUERY_MODE=False` → planner vẫn chạy nhưng gọi `build_context` cũ, trả bundle tương thích (legacy mode) — tránh duplicate code path.

### 4.3 Refactor `rag_formatter.py` *(1 ngày)*

**Binding section → query sources (MVP):**

| Section | Primary source | Secondary |
|---|---|---|
| `for_executive()` | Q1 `check_findings` (top-3 HIGH+) | Q2 `capability_themes` (domain summary) |
| `for_fail_analysis(check_id)` | Q1 `check_findings[check_id]` | Q3 `remediations[check_id]` |
| `for_pass_analysis()` | **Q2 `capability_themes`** (primary, NEW) | Q1 `control_themes` |
| `for_recommendations()` | **Q3 `remediations`** (primary, NEW) | Q2 baselines, Q1 `recommended_practices` |
| `for_per_finding(check_id)` | Q1 + Q3 | — |

**Backward compat:**
- Legacy mode: `capability_themes=[]`, `remediations=[]` → formatter rơi về behavior cũ.
- Không rewrite prompt template (llm_writer.py) trong MVP — chỉ thay đổi string content đưa vào.

### 4.4 Client method *(0.5 ngày)*

```python
# pdca/agents/shared/rag_client.py
def build_report_context(
    self,
    check_ids: list[str],
    domains: list[str],
    severity_map: dict[str, str],
    include_q2: bool = True,
    include_q3: bool = True,
) -> dict | None:
    """POST /v1/retrieve/report_context. Retry + graceful None on fail."""
```

- Reuse retry session có sẵn.
- Timeout 30s (wrapper đã timeout 15s phía server, +15s buffer).
- Log latency từng query từ `diagnostics`.

### 4.5 Orchestrator wiring

File: [pdca/orchestrator.py:630-710](../pdca/orchestrator.py#L630-L710)

```python
from pdca.config import MULTI_QUERY_MODE

if MULTI_QUERY_MODE and rag_healthy:
    planner = RAGQueryPlanner(rag_client)
    bundle = planner.execute(planner.plan(findings, scope_domains))
else:
    bundle = rag_client.build_context(...)  # legacy path
```

- Log rõ mode được dùng.
- Khi wrapper call fail → **không** auto-fallback legacy (để benchmark sạch). Thay vào đó, trả bundle rỗng như hiện tại, mode='legacy' chỉ kích hoạt khi flag `False`.

### 4.6 Tests Phase 3

| File | Test |
|---|---|
| `tests/test_rag_query_planner.py` (NEW) | dedup check_ids, dedup domains, build severity_map |
| [tests/test_rag_view_formatter.py](../tests/test_rag_view_formatter.py) | thêm cases cho `capability_themes` + `remediations` non-empty |
| [tests/test_report_smoke_e2e.py](../tests/test_report_smoke_e2e.py) | run 2 mode (flag on/off), assert không crash |

### 4.7 DoD Phase 3

- [ ] `MULTI_QUERY_MODE=true python scripts/run_e2e_auto.py "scan all s3 buckets"` chạy thành công, xuất ra report.
- [ ] Log chứng minh 3 queries được gọi.
- [ ] `MULTI_QUERY_MODE=false` → pipeline hoạt động **hệt như trước** refactor.
- [ ] Tests mới + cũ pass.

---

## 5. Phase 4 — Benchmark, Ablation & Demo *(1.5 ngày)*

### 5.1 Benchmark comparison *(0.5 ngày)*

```bash
MULTI_QUERY_MODE=false python benchmarks/llm_generation/run_report_benchmark_v3.py --mode full
# → results/baseline_single_query.json  (đã có từ Phase 1)

MULTI_QUERY_MODE=true python benchmarks/llm_generation/run_report_benchmark_v3.py --mode full
# → results/mvp_multi_query.json
```

**Metrics so sánh** (dùng [benchmarks/llm_generation/report_metrics_v3.py](../benchmarks/llm_generation/report_metrics_v3.py)):
- Faithfulness per section
- Grounding (% claims có evidence)
- Hallucination rate (đặc biệt ở Recommendation)
- Coverage (% fields có nội dung)
- Length/redundancy

### 5.2 Ablation *(0.5 ngày)*

Dùng [benchmarks/llm_generation/ablation_runner.py](../benchmarks/llm_generation/ablation_runner.py) với 4 configs:

| Config | include_q2 | include_q3 |
|---|---|---|
| baseline (Q1-only) | false | false |
| Q1+Q2 | true | false |
| Q1+Q3 | false | true |
| full MVP | true | true |

Output: `benchmarks/llm_generation/results/ablation_mvp.json` + markdown table.

### 5.3 Demo script *(0.5 ngày)*

File mới: `scripts/demo_multi_query_compare.py`

```
1. Degrade bucket (degrade_s3_for_e2e.py --bucket demo --degrade --yes)
2. Run baseline mode → save final_report_baseline.html
3. Run MVP mode → save final_report_mvp.html
4. Generate side-by-side diff summary → docs/thesis-notes/mvp_demo_findings.md
5. Revert bucket
```

### 5.4 DoD Phase 4

- [ ] 2 HTML reports xuất ra side-by-side.
- [ ] Bảng benchmark baseline vs MVP có số liệu cụ thể.
- [ ] Ablation table 4 configs.
- [ ] Screenshots + note khác biệt định tính trong `mvp_demo_findings.md`.

---

## 6. Phase 5 — Documentation *(0.5 ngày)*

| Task | File |
|---|---|
| Schema doc for `/v1/retrieve/report_context` | [docs/rag-integration.md](./rag-integration.md) |
| Update data contract `ReportContextBundle` | [docs/data-contracts.md](./data-contracts.md) |
| Design rationale (for thesis) | `docs/thesis-notes/mvp_design.md` (NEW) |
| Update env flag docs | [README.md](../README.md) — section "Biến môi trường" |

---

## 7. Timeline tổng hợp

| Day | Phase | Deliverable chính |
|---|---|---|
| **D1 AM** | Phase 1 | Baseline numbers + gap analysis |
| **D1 PM + D2** | Phase 2.1 + 2.2 | Q2 + Q3 endpoints + tests |
| **D3 AM** | Phase 2.3 | Wrapper + parallel + cache |
| **D3 PM – D4** | Phase 3 | Query planner + formatter refactor + orchestrator wiring |
| **D5** | Phase 4 | Benchmark + ablation + demo script |
| **D6 AM** | Phase 5 | Docs |
| **D6 PM** | Buffer | Bug fix |
| **D7** | Buffer | Polish demo + thesis write-up notes |

---

## 8. Rủi ro & Mitigation

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| ~~R1~~ | ~~Q3 corpus Remediation rỗng~~ | — | — | **RESOLVED** — coverage 100% (đo 2026-04-22). Không còn risk. |
| R2 | Latency 3 queries song song vẫn chậm (>5s) | Medium | Medium | Cache, giảm `top_k`. Nếu vẫn chậm → Q3 đổi thành on-demand (chỉ cho high-severity checks) |
| R3 | Benchmark improvement không rõ rệt | Medium | Medium | Vẫn là kết quả có giá trị — phân tích root cause, viết vào thesis phần "discussion" |
| R4 | Break E2E tests | Low | High | Flag default `False`; kiểm tra [tests/test_report_smoke_e2e.py](../tests/test_report_smoke_e2e.py) sau mỗi phase |
| R5 | HyDE module chưa integrate đúng với retriever | Medium | Low | Fallback: Q3 skip HyDE, dùng hybrid raw với check_id + check title |
| R6 | Scope detector không trả domain list chuẩn | Low | Medium | Validate output trong planner, fallback `["all"]` để Q2 vẫn chạy (trả narrative tổng) |
| **R7** | **Heuristic derive `domain` (OQ1) sai với capability cross-service** | Medium | Medium | Unit test golden samples ≥10 capabilities, whitelist service names. Fallback `domain="general"` thay vì guess bừa. Validate manual 78 records trước khi commit backfill. |
| **R8** | **Remediation string blob parse fail (ast.literal_eval edge cases)** | Low | Medium | Try/except wrap parser, log fail count. Nếu fail rate >5% → viết custom parser dựa regex thay vì literal_eval. |
| **R9** | **`GROQ_API_KEY` chưa có trong `.env` → judge benchmark fail** | Medium | High | Pre-flight check Phase 1 (xem §13 OQ3). Fallback dùng Gemini (chậm 20 phút/run nhưng chạy được). |

---

## 9. Rollout & rollback

- **Feature flag:** `MULTI_QUERY_MODE` trong `.env` (default `False`).
- **Canary:** bật flag cho benchmark trước, E2E production sau.
- **Rollback:** set flag `False` → pipeline về baseline. Code path cũ **không** bị xóa trong MVP (xóa ở giai đoạn sau MVP khi stable).

---

## 10. Post-MVP roadmap (tham khảo, không làm ở MVP)

1. Crawl AWS docs → mở rộng Q3 corpus.
2. Thêm Q4 (compliance mapping) — mapping table đã có sẵn một phần.
3. Thêm Q5 (maturity gap) — leverage `maturity_engine.py`.
4. Thêm Q6 (incident context) — cần nguồn threat intel.
5. Gỡ legacy code path (`_build_rag_knowledge` trong `report_agent.py` — xem §14.2).
6. Per-section LLM prompt tuning dựa trên bundle structure mới (xem §14.1, §14.3).
7. Integrate Q3 remediation steps vào per-finding enrichment (`_enrich_success`, `_enrich_failed`, `_enrich_manual` — xem §14.1).
8. Mở rộng RAG coverage cho 5 sections hiện không có RAG (xem §14.3).
9. Giảm LLM call count bằng batching per-finding và async parallelism (xem §14.4).
10. Fix LLM quality issues: temperature per-section, double call V1+V2, tool_code token waste (xem §14.5).

---

## 11. Checklist Definition of Done (toàn MVP)

- [ ] Phase 1 baseline đo xong, có file results.
- [ ] 3 endpoints RAG (Q1 wrapper reuse + Q2 + Q3) chạy, tests pass.
- [ ] Wrapper `/v1/retrieve/report_context` parallel + cache + graceful.
- [ ] `RAGQueryPlanner` + refactored `rag_formatter.py` hoạt động 2 mode.
- [ ] Flag `MULTI_QUERY_MODE` trong config + README documented.
- [ ] E2E với flag on → report xuất ra có nội dung từ Q2 + Q3.
- [ ] Benchmark v3 chạy 2 mode, có bảng so sánh.
- [ ] Ablation 4 configs, có bảng contribution.
- [ ] Demo script 1 lệnh.
- [ ] 2 HTML reports side-by-side.
- [ ] Docs updated: rag-integration.md, data-contracts.md, mvp_design.md.
- [ ] Tất cả tests (`tests/` + `RAG/tests/`) pass.

---

## 12. Questions đã chốt

| # | Question | Decision |
|---|---|---|
| Q1 | MVP scope | Q1 + Q2 + Q3 only (3 query types) |
| Q2 | Crawl mới ở MVP? | **Không.** Chỉ dùng corpus hiện có (`maturity_capabilities.json`, `prowler_checks.json`). Crawl ở Post-MVP. |
| Q3 | Flag default value | `False` (an toàn, không break ai đang dùng baseline) |
| Q4 | Phase 1 baseline bắt buộc? | **Bắt buộc.** Không có baseline → không có thesis contribution. |
| Q5 | Wrapper endpoint hay client-side aggregation | Wrapper endpoint (§1.2 Lựa chọn A) |
| Q6 | Fallback khi wrapper fail | Trả bundle rỗng như behavior hiện tại; KHÔNG auto-fallback legacy để benchmark sạch |

---

## 13. Open questions — ĐÃ RESOLVED (2026-04-22)

Tất cả 4 open questions đã được trả lời qua phân tích codebase. Ghi lại kết luận để làm evidence cho thesis.

- [x] **OQ1:** `maturity_capabilities.json` có field `domain` không?
  - **Kết quả:** Field tồn tại nhưng **0% populated** (78/78 rỗng).
  - **Action:** Thêm sub-task 2.1a backfill domain (§3.2) → **+0.5 ngày Phase 2.1**.
  - **Fields thay thế:** `stage` 100%, `capability_id` + `keywords` 100%, `recommended_practices` 91%, `risk_explanation` 51%.

- [x] **OQ2:** Coverage của `Remediation.Code` trong `prowler_checks.json`?
  - **Kết quả:** **100% coverage** (577/577). Lưu dưới dạng string blob serialized dict chứa `CLI`/`NativeIaC`/`Terraform`/`Other`.
  - **Action:** Thêm parse step bằng `ast.literal_eval` trong normalizer (§3.3). Corpus KHÔNG cần crawl thêm.
  - **Impact:** Risk R1 gỡ bỏ.

- [x] **OQ3:** Judge model có stable để so sánh benchmark?
  - **Kết quả:** **Stable đủ.** Judge primary = **Groq** `openai/gpt-oss-20b` (không phải Ollama), `temperature=0.3` + pinned seed + `JudgeCache` file-based. Gemini làm reference (bị giới hạn 20 RPD từ 2026).
  - **Action:** Pre-flight check `GROQ_API_KEY` trong `.env` trước Phase 1 (xem §13.1).
  - **Risk:** R9 — nếu key thiếu, fallback Gemini chạy được nhưng chậm (~20 phút/benchmark run).

- [x] **OQ4:** Có cần test fixture mới không?
  - **Kết quả:** **Không cần.** Đã có [tests/fixtures/report_baseline/](../tests/fixtures/report_baseline/) với 7 cases (A–G) + `fixture_builder.py` Python deterministic.
  - **Action:** Tests mới chỉ mock `ReportContextBundle` đơn giản, reuse input fixtures cũ cho E2E.
  - **Impact:** Tiết kiệm ~0.5 ngày Phase 3.

### 13.1 Pre-flight checklist (chạy 15 phút trước Phase 1)

```bash
# 1. Verify GROQ_API_KEY (R9 mitigation)
grep -E "^GROQ_API_KEY=" .env || echo "MISSING — add it or fallback Gemini"

# 2. Verify RAG service chạy
curl http://localhost:8005/health

# 3. Verify corpus files tồn tại + đúng count
python -c "import json; print('prowler:', len(json.load(open('RAG/data/normalized/prowler_checks.json'))))"
python -c "import json; print('capabilities:', len(json.load(open('RAG/data/normalized/maturity_capabilities.json'))))"
# Expected: prowler=577, capabilities=78

# 4. Verify judge cache dir writable
mkdir -p benchmarks/llm_generation/benchmark_outputs/judge_cache

# 5. Verify tests baseline pass trước khi refactor
pytest tests/ RAG/tests/ -q --ignore=tests/rag_evaluation
```

Nếu bất kỳ bước nào fail → dừng, fix trước khi vào Phase 1.

### 13.2 Timeline net effect sau khi resolve OQs

| Thay đổi | Δ |
|---|---|
| OQ1 — Backfill domain | +0.5 ngày (Phase 2.1a) |
| OQ2 — Corpus đã đủ, parser đơn giản | −0.5 ngày (Phase 2.2) |
| OQ3 — Cần pre-flight check | +0 ngày |
| OQ4 — Fixtures reusable | −0.5 ngày (Phase 3) |
| **Net** | **−0.5 ngày** |

→ **Timeline cập nhật: 4.5–6.5 ngày** (giảm nửa ngày so với draft ban đầu).

---

---

## 14. Điểm yếu chưa giải quyết — Cơ sở cho plan sau

> Phần này ghi nhận những điểm yếu đã phân tích nhưng **nằm ngoài scope MVP**. Mục đích: làm source of truth để xây dựng plan giai đoạn tiếp theo, tránh phát hiện lại từ đầu.
>
> Mỗi mục ghi rõ: vị trí code, nguyên nhân gốc, tác động, và hướng giải quyết đề xuất.

---

### 14.1 Per-finding enrichment chỉ dùng `risk_summary` — bỏ phí Q3 data

**Trạng thái sau MVP:** Cải thiện một phần — `for_per_finding()` sẽ có Q3 data, nhưng các enrich methods chưa gọi formatter này.

**Vị trí:**
- `pdca/agents/report_agent.py` — `_enrich_success()`, `_enrich_failed()`, `_enrich_manual()`
- `pdca/agents/report_module/rag_formatter.py` — `for_per_finding()`

**Vấn đề hiện tại:**
```python
# _enrich_success/_enrich_failed đều làm như này:
rag_risk = rag_map.get(check_id, {}).get("risk_summary", "")  # chỉ 1 field
```
`RAGViewFormatter.for_per_finding()` đã có sẵn interface trả `{"risk", "recommendation", "title"}` nhưng không được gọi. Sau MVP, Q3 sẽ bổ sung `steps` (CLI/IaC) vào bundle nhưng 3 enrich methods vẫn không nhận data mới nếu không refactor.

**Tác động:** `write_pass_remediation_detail` và `write_fail_remediation_detail` không có remediation steps thật → LLM vẫn phải suy đoán hướng khắc phục kỹ thuật chi tiết.

**Hướng giải quyết:**
1. Thay `_build_rag_finding_map` bằng `RAGViewFormatter.for_per_finding(check_id)` trong 3 enrich methods.
2. Update signature `write_pass_remediation_detail` / `write_fail_remediation_detail` nhận thêm `rag_recommendation: str`.
3. Loại bỏ `_build_rag_knowledge()` (legacy flat blob) sau khi migrate xong.

**Effort ước tính:** 0.5 ngày — thay thế cơ học, không cần logic mới.

---

### 14.2 Hai hệ thống format RAG tồn tại song song

**Trạng thái sau MVP:** Vẫn còn — legacy path giữ để backward compat với `MULTI_QUERY_MODE=False`.

**Vị trí:**
- `pdca/agents/report_agent.py:574-583` — `RAGViewFormatter` (path mới)
- `pdca/agents/report_agent.py:756-811` — `_build_rag_knowledge()` (legacy flat blob)

**Vấn đề:** Hai paths xử lý cùng `rag_context` với logic khác nhau. Khi thêm Q2/Q3 fields vào bundle, phải update cả hai nơi → dễ inconsistent, khó maintain.

**Hướng giải quyết:**
1. Sau khi MVP stable và `MULTI_QUERY_MODE=True` trở thành default → xóa `_build_rag_knowledge()` hoàn toàn.
2. Migrate các caller còn lại (per-finding enrich) sang `RAGViewFormatter.for_per_finding()`.
3. Xóa import và reference của hàm legacy.

**Điều kiện để làm:** MVP đã stable ít nhất 1 tuần, `MULTI_QUERY_MODE=False` không còn được dùng trong production/benchmark.

**Effort ước tính:** 0.5 ngày.

---

### 14.3 Năm sections LLM không nhận RAG context

**Trạng thái sau MVP:** Không thay đổi — nằm ngoài scope MVP hoàn toàn.

**Vị trí:** `pdca/agents/report_module/llm_writer.py`

| Section | Method | RAG cần bổ sung |
|---------|--------|----------------|
| System Overview | `write_system_overview()` | Q2 domain narrative (mô tả vai trò service) |
| Assessment Goals | `write_assessment_goals()` | Q2 baselines (CIS/Well-Architected references) |
| Post-Remediation Analysis V2 | `write_post_remediation_analysis_v2()` | Q1 risk context cho residual risks |
| Maturity Overview | `write_maturity_overview()` | Q2 capability guidance + risk_explanation |
| Action Plan | `write_action_plan()` | Q3 effort estimate per finding |

**Vấn đề nghiêm trọng nhất:** `write_maturity_overview` đưa ra nhận xét về domain strengths/weaknesses chỉ dựa trên điểm số (float) và nhãn stage — không có `guidance`, `risk_explanation`, `recommended_practices` từ maturity corpus. LLM nhận xét mà không có nền tảng kiến thức domain.

**Hướng giải quyết chung:**
1. Bổ sung `RAGViewFormatter` view mới: `for_maturity_overview()`, `for_action_plan()`.
2. Bind từng section với view tương ứng trong `_write_llm_sections()` và `_write_maturity_llm_sections()`.
3. Không cần endpoint RAG mới — Q2 bundle đã có data cần thiết sau MVP.

**Effort ước tính:** 1 ngày — chủ yếu viết formatter views và update 5 LLM writer methods.

---

### 14.4 LLM calls quá nhiều và sequential — latency tích lũy

**Trạng thái sau MVP:** Không thay đổi — plan không đề cập.

**Vị trí:** `pdca/agents/report_agent.py` — `_enrich_success()`, `_enrich_failed()`, `_enrich_manual()` trong vòng lặp

**Vấn đề:**
```
Tổng LLM calls điển hình (15 findings + 5 domains):
  9 cố định + 15 per-finding + 8 maturity = 32 calls sequential
  → 96–192 giây với gemma3:4b local
```

Ba nguồn gốc:
1. **Per-finding loop:** `write_pass_remediation_detail` × n_success, `write_fail_remediation_detail` × n_failed, `write_manual_guide` × n_manual — tất cả độc lập nhau nhưng chạy tuần tự.
2. **Maturity domain loop:** `write_domain_assessment()` × n_domains — độc lập nhau.
3. **Double call:** `write_post_remediation_analysis` (V1, dòng 640) và `write_post_remediation_analysis_v2` (V2, dòng 481) cùng gọi LLM cho cùng chủ đề. V1 là thừa, chỉ V2 được dùng trong template.

**Hướng giải quyết:**
1. **Quick win — xóa V1 double call:** Loại `write_post_remediation_analysis` (V1) khỏi `_write_llm_sections()`. Tiết kiệm 1 call ngay lập tức, không cần refactor lớn.
2. **Batch per-finding:** Gom tất cả findings vào 1 prompt thay vì 1 prompt/finding. Ví dụ: `write_remediation_batch(findings: list[dict]) -> dict[check_id, str]`.
3. **Async parallel:** Dùng `asyncio.gather` cho các calls độc lập (domain assessments, per-finding enrichment).

**Effort ước tính:** Quick win (xóa V1) = 15 phút. Batch + async = 1–2 ngày (cần đánh giá quality tradeoff khi batch).

---

### 14.5 LLM quality issues không liên quan RAG

**Trạng thái sau MVP:** Không thay đổi — nằm ngoài scope plan.

**Vị trí:** `pdca/agents/report_agent.py:109`, `pdca/agents/report_module/llm_writer.py:98,671`

**Ba vấn đề cụ thể:**

**a) Temperature 0.5 cho tất cả sections:**
```python
# report_agent.py dòng 109 — áp dụng cho mọi section
return ChatOllama(model=..., temperature=0.5)
```
Report sections kỹ thuật (RCA, remediation detail, số liệu cụ thể) cần temperature 0.1–0.2 để tránh drift. Sections narrative (executive summary) mới phù hợp 0.3–0.5.

Hướng giải quyết: Tạo 2 LLM instances trong `ReportAgent.__init__()` — `self.llm_precise` (temp=0.1) và `self.llm_narrative` (temp=0.4). `LLMTimerProxy` wraps cả hai. Các writer methods chọn instance phù hợp.

**b) Tool code inject vào prompt rồi cấm dùng:**
```python
# write_pass_remediation_detail prompt:
Source code của công cụ (tool_code):
{tool_code}  # ← Python source code nguyên bản, chiếm ~30% context window
# ...
- TUYỆT ĐỐI KHÔNG trích dẫn lại source code  # ← cấm ngay sau đó
```
Inject để phân tích kỹ thuật nhưng cấm trích dẫn — mâu thuẫn và lãng phí tokens. Với `gemma3:4b` context window ~8k tokens, source code dài chiếm tỉ lệ lớn.

Hướng giải quyết: Thay `tool_code` bằng `tool_summary` — một đoạn mô tả kỹ thuật 2–3 câu được pre-computed từ code (hoặc lấy từ `tool_description` đã có). Loại raw source code khỏi prompt hoàn toàn.

**c) `_PLACEHOLDER` regex xóa mọi `[...]`:**
```python
_PLACEHOLDER = re.compile(r'\[.*?\]')  # strip tất cả [...]
```
Xóa cả content hợp lệ như `[CIS 1.1]`, `[IAM Policy]`, `[2024]` trong output LLM. Với report kỹ thuật, square brackets thường là citation/reference hợp lệ.

Hướng giải quyết: Thu hẹp regex chỉ match placeholders thật — ví dụ pattern `\[(?:text|nội dung|liệt kê|điền|your|insert)\s`, hoặc chỉ strip khi toàn bộ nội dung trong brackets là whitespace/lowercase generic words.

**Effort ước tính:** Temperature fix = 1 giờ. Tool_code fix = 2 giờ. Regex fix = 1 giờ.

---

### 14.6 Tổng hợp backlog cho plan tiếp theo

| ID | Điểm yếu | Effort | Priority | Dependency |
|----|----------|--------|----------|-----------|
| B1 | Xóa V1 double call post-remediation | 15 phút | Cao | Không có |
| B2 | Fix temperature per-section (precise vs narrative) | 1 giờ | Cao | Không có |
| B3 | Fix `_PLACEHOLDER` regex quá rộng | 1 giờ | Trung bình | Không có |
| B4 | Loại `tool_code` khỏi prompt, thay bằng summary | 2 giờ | Trung bình | Không có |
| B5 | Migrate per-finding enrich sang `for_per_finding()` + Q3 data | 0.5 ngày | Cao | MVP Phase 2+3 done |
| B6 | Xóa `_build_rag_knowledge()` legacy path | 0.5 ngày | Trung bình | B5 done |
| B7 | Bổ sung RAG cho 5 sections thiếu (formatter views mới) | 1 ngày | Cao | MVP Phase 2+3 done |
| B8 | Batch per-finding LLM calls | 1–2 ngày | Trung bình | Đánh giá quality tradeoff |
| B9 | Async parallel LLM calls (domain assessments + per-finding) | 1 ngày | Trung bình | Không có |

**Quick wins không cần MVP hoàn thành (B1–B4):** Tổng ~5 giờ, có thể làm song song với Phase 2 của MVP mà không ảnh hưởng benchmark.

---

**End of plan v1.1** — Khi triển khai, bám theo file này. Mọi thay đổi scope phải cập nhật ở đây trước khi code.
