# BÁO CÁO PHÂN TÍCH KIẾN TRÚC & KẾ HOẠCH TÍCH HỢP
# RAG System ↔ Agent System

**Ngày:** 2026-03-27
**Phiên bản:** v1.0
**Mục đích:** Phân tích kiến trúc, đánh giá điểm mạnh/yếu, và lập kế hoạch tích hợp RAG System vào Agent System

---

## MỤC LỤC

1. [Tổng quan hai hệ thống](#1-tổng-quan-hai-hệ-thống)
2. [Phân tích kiến trúc RAG System](#2-phân-tích-kiến-trúc-rag-system)
3. [Phân tích kiến trúc Agent System](#3-phân-tích-kiến-trúc-agent-system)
4. [Phân tích luồng dữ liệu (Data Flow)](#4-phân-tích-luồng-dữ-liệu)
5. [Điểm mạnh và điểm yếu](#5-điểm-mạnh-và-điểm-yếu)
6. [Phân tích các điểm tích hợp hiện tại](#6-phân-tích-các-điểm-tích-hợp-hiện-tại)
7. [Đề xuất cải thiện trước khi tích hợp](#7-đề-xuất-cải-thiện-trước-khi-tích-hợp)
8. [Kế hoạch tích hợp chi tiết](#8-kế-hoạch-tích-hợp-chi-tiết)
9. [Kết luận](#9-kết-luận)

---

## 1. TỔNG QUAN HAI HỆ THỐNG

### 1.1 RAG System

**Mục đích:** Hệ thống Retrieval-Augmented Generation phục vụ truy xuất kiến thức bảo mật AWS, bao gồm Prowler security checks, maturity capabilities, và mappings giữa checks ↔ capabilities.

**Technology Stack:**
- Framework: FastAPI (port 8001)
- Vector DB: ChromaDB (persistent, all-MiniLM-L6-v2, 384 dims)
- Lexical Search: BM25 (custom implementation, k1=1.2, b=0.6)
- Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2
- Language: Python

**Dữ liệu:**
- 577 Prowler security checks
- 78 maturity capabilities
- 502 check-to-capability mappings

**Consumers:** 3 loại context (planning, risk, report)

### 1.2 Agent System

**Mục đích:** Hệ thống Agent tự động hóa quy trình PDCA (Plan-Do-Check-Act) cho bảo mật AWS — từ lập kế hoạch quét, đánh giá rủi ro, remediation, đến báo cáo.

**Technology Stack:**
- Orchestration: LangGraph (state machine)
- LLM: Ollama (local, port 11434)
- Agent Framework: LangChain
- AWS SDK: boto3
- Scanner API: Prowler (port 8000)
- Language: Python

**Agents:** 10 agents trong pipeline PDCA:
1. EnvironmentAgent → 2. PlanningAgent → 3. ScannerAgent → 4. MonitoringAgent → 5. RiskEvaluationAgent → 6. RemediationPlannerAgent → 7. ReviewTask (HITL) → 8. ExecutionAgent → 9. RescanAgent + AnalysisAgent → 10. ReportAgent

---

## 2. PHÂN TÍCH KIẾN TRÚC RAG SYSTEM

### 2.1 Kiến trúc phân lớp (Layered Architecture)

```
┌─────────────────────────────────────────────────────────┐
│                   API Layer (FastAPI)                    │
│  /health  /ready  /v1/retrieve/{checks,maturity}        │
│  /v1/context/build  /v1/resolve/mapping                 │
├─────────────────────────────────────────────────────────┤
│                   Service Layer                         │
│  CheckService  MaturityService  MappingService          │
│  ContextService                                         │
├─────────────────────────────────────────────────────────┤
│              Context Building Layer                     │
│  ContextBuilder → CoverageSelector → BundleFactory      │
│  IntentDetector    PromptFormatter    _helpers           │
├─────────────────────────────────────────────────────────┤
│              Retrieval Pipeline Layer                    │
│  SemanticRouter → RetrievalPipeline:                    │
│    Lexical (BM25) + Vector (Chroma) → RRF Merge         │
│    → Product Gate → CrossEncoder Rerank                 │
│    → Metadata Bonus → Verify → Confidence               │
├─────────────────────────────────────────────────────────┤
│                   Index Layer                           │
│  BM25Index (lexical)  │  VectorIndex (ChromaDB)         │
├─────────────────────────────────────────────────────────┤
│              Data Persistence Layer                     │
│  Normalized JSONs  │  BM25 Pickles  │  Chroma DB        │
│  Manifest.json                                          │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Các thành phần chính

| Thành phần | File | Vai trò |
|---|---|---|
| **SemanticRouter** | `app/retrieval/router.py` | Phân tích query → xác định query_type, corpus, filters, exact lookup |
| **RetrievalPipeline** | `app/retrieval/pipeline.py` | Orchestrate toàn bộ retrieval: lexical + vector → RRF → rerank → verify |
| **BM25Index** | `app/indexing/lexical_index.py` | Lexical search với BM25 scoring, exact ID lookup, structural matching |
| **VectorIndex** | `app/indexing/vector_index.py` | Semantic search qua ChromaDB + SentenceTransformer embeddings |
| **CrossEncoderReranker** | `app/retrieval/reranker.py` | Rerank top candidates bằng cross-encoder model |
| **ConfidenceCalculator** | `app/retrieval/confidence.py` | Tính confidence level (high/medium/low) dựa trên scores + verification |
| **Verifier** | `app/retrieval/verifier.py` | Kiểm tra quality: exact match, doc type, service match, ambiguity |
| **IntentDetector** | `app/context/intent_detector.py` | Detect query intents, control families, entity gating |
| **CoverageSelector** | `app/context/coverage_selector.py` | Chọn checks/mappings/capabilities phù hợp cho từng consumer |
| **BundleFactory** | `app/context/bundle_factory.py` | Tạo consumer-specific bundles (Planning/Risk/Report) |
| **PromptFormatter** | `app/context/prompt_formatter.py` | Format context thành prompt-ready text cho LLM |

### 2.3 Ba Corpus dữ liệu

| Corpus | Docs | Mô tả | Ví dụ doc_id |
|---|---|---|---|
| `prowler_checks` | 577 | AWS security checks từ Prowler | `check:s3_bucket_public_access` |
| `maturity_capabilities` | 78 | Security capability model | `block_public_access` |
| `maturity_mappings` | 502 | Links checks → capabilities | `mapping:s3_bucket_public_access→block_public_access` |

---

## 3. PHÂN TÍCH KIẾN TRÚC AGENT SYSTEM

### 3.1 Kiến trúc State Machine (LangGraph)

```
┌─────────────────────────────────────────────────────────┐
│            Graph Orchestrator (LangGraph)                │
│                                                         │
│  START → environment → planning → scanning → monitoring │
│    → risk_evaluation → [route_after_risk]               │
│        ├→ operational_planning → review_task (HITL)     │
│        │    → execution → verification → report → END  │
│        └→ report → END (nếu không có FAIL findings)    │
│                                                         │
│  State: PDCAState (TypedDict)                           │
│  Interrupt: review_task (Human-in-the-Loop)             │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Mô tả 10 Agents

| # | Agent | File | Chức năng | Sử dụng LLM? | Sử dụng RAG? |
|---|---|---|---|---|---|
| 1 | **EnvironmentAgent** | `agents/environment_agent.py` | Lấy AWS context (account, region, identity) | Không | Không |
| 2 | **PlanningAgent** | `agents/planning_agent.py` | Phân tích user request → xác định checks cần quét | **Có** (Ollama) | **Có** (retrieve/checks) |
| 3 | **ScannerAgent** | `agents/scanner_agent.py` | Launch scan jobs qua Scanner API | Không | Không |
| 4 | **MonitoringAgent** | `agents/monitoring_agent.py` | Poll job status, thu thập findings | Không | Không |
| 5 | **RiskEvaluationAgent** | `agents/risk_evaluation_agent.py` | Đánh giá rủi ro từng finding | **Có** (Ollama) | **Có** (context/build) |
| 6 | **RemediationPlannerAgent** | `agents/remediate_planner_agent.py` | Chọn tools remediation cho mỗi finding | **Có** (Ollama) | Không |
| 7 | **ReviewTask** | `graph_orchestator.py` | HITL — user approve/skip từng task | Không | Không |
| 8 | **ExecutionAgent** | `agents/execution_agent.py` | Thực thi remediation tools (boto3) | Không | Không |
| 9 | **RescanAgent + AnalysisAgent** | `agents/rescan_agent.py`, `agents/analysis_agent.py` | Quét lại + so sánh trước/sau | Không | Không |
| 10 | **ReportAgent** | `agents/report_agent.py` | Sinh báo cáo MD/HTML/PDF | **Có** (Ollama) | Không |

### 3.3 Tool System

| Nhóm | Tools | Mô tả |
|---|---|---|
| **Scanner** | `start_scan_by_check_ids`, `start_scan_by_group`, `check_job_status` | Giao tiếp với Prowler Scanner API (port 8000) |
| **S3 Remediation** | `s3_block_account_public_access`, `s3_enable_access_logging`, `s3_enable_kms_encryption`, ... | Thực thi remediation trực tiếp qua boto3 |
| **Manual** | `s3_enable_mfa_delete`, `s3_enable_object_lock`, `s3_prepare_replication` | Yêu cầu thao tác thủ công |

### 3.4 Inter-Agent Communication

```
┌──────────────────────────────────────────────────────────────────────┐
│                     PDCAState (Shared State)                         │
│                                                                      │
│  environment_node ──→ aws_context ──→ planning_node                  │
│  planning_node ──→ assessment_plan ──→ scanning_node                 │
│  scanning_node ──→ scan_job_ids ──→ monitoring_node                  │
│  monitoring_node ──→ raw_findings ──→ risk_evaluation_node           │
│  risk_evaluation_node ──→ prioritized_findings ──→ planning_node     │
│  remediation_planner ──→ remediation_tasks ──→ review_task           │
│  review_task ──→ task_execution_plan ──→ execution_node              │
│  execution_node ──→ execution_logs ──→ verification_node             │
│  verification_node ──→ report_context ──→ report_node                │
│  report_node ──→ final_report ──→ END                                │
│                                                                      │
│  File-based persistence:                                             │
│  - data/initial_scan_config.json (planning output)                   │
│  - data/pre_scan.json (monitoring output)                            │
│  - data/post_scan.json (rescan output)                               │
│  - data/analysis_diff.json (analysis output)                         │
│  - data/performance_metrics.json (system-wide metrics)               │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. PHÂN TÍCH LUỒNG DỮ LIỆU

### 4.1 RAG System — Luồng Offline (Build Pipeline)

```
Raw Data (JSON files)
  │
  ▼
Loaders (load_prowler_raw, load_maturity_raw, load_mappings_raw)
  │
  ▼
Normalizers
  ├─ normalize_prowler_doc()  → ProwlerCheckDoc + retrieval_text
  ├─ normalize_maturity_doc() → MaturityCapabilityDoc + retrieval_text + aliases
  └─ normalize_mapping_doc()  → MaturityMappingDoc + retrieval_text
  │
  ▼
Normalized JSON Files (data/normalized/)
  │
  ├─▼─ BM25Index.build() → BM25 Pickles (data/indexes/bm25/)
  └─▼─ VectorIndex.build_collection() → Chroma Collections (data/indexes/chroma/)
  │
  ▼
Manifest.json (metadata: version, doc counts, paths)
```

### 4.2 RAG System — Luồng Online (Query Pipeline)

```
API Request (query, check_id, service, consumer, ...)
  │
  ▼
SemanticRouter.route()
  ├─ Detect exact_check_id / exact_capability_id
  ├─ Detect query_type (check_search / maturity_search / mapping_resolution)
  ├─ Extract service, domain
  └─ Build RouteDecision (filters, doc_types, exact flags)
  │
  ▼
RetrievalPipeline.retrieve()
  │
  ├─ [Exact Path] ──→ BM25 direct lookup by ID ──→ Return with score=1.0
  │
  └─ [Hybrid Path]
      ├─ BM25Index.query(top_k*3) ──→ lexical_results
      ├─ VectorIndex.query(top_k*3) ──→ vector_results   [parallel execution]
      │
      ▼
    RRF Merge: score = Σ(1/(60+rank_i))
      │
      ▼
    Product Entity Gate (reject irrelevant e.g., bedrock capabilities)
      │
      ▼
    CrossEncoder Rerank (top 20 candidates)
      │
      ▼
    Metadata Bonus (+0.03 service match, +0.02 domain match)
      │
      ▼
    Verification (exact_lookup_miss, doc_type_mismatch, low_score, ambiguity)
      │
      ▼
    Confidence Calculation (high/medium/low based on thresholds + adjustments)
      │
      ▼
    ResponseEnvelope {results, meta: {confidence, verification, diagnostics}}
```

### 4.3 RAG System — Luồng Context Build (cho Agents)

```
ContextBuildRequest {consumer, findings, check_ids, service, domain}
  │
  ▼
ContextService.build()
  │
  ├─ Phase 1: Check Retrieval
  │   └─ Cho mỗi check_id → CheckService.search() → check_results
  │
  ├─ Phase 2: Mapping Resolution
  │   └─ Cho mỗi check_id → MappingService.resolve() → mapping_results
  │       (lookup in-memory index, rank by review_status → confidence)
  │
  ├─ Phase 3: Maturity Retrieval
  │   └─ MaturityService.search(domains) → maturity_results
  │
  └─ Phase 4: Context Bundle Construction
      └─ ContextBuilder.build()
          ├─ CoverageSelector.select_checks() → (requested, related)
          │   └─ Planning: planning_coverage_select() (diversify by intent + service)
          ├─ CoverageSelector.select_mappings() → filtered mappings
          │   └─ Entity gating, quality filter, rank by status/confidence
          ├─ CoverageSelector.select_capabilities() → filtered capabilities
          │   └─ Domain mismatch filter, top N by consumer
          ├─ BundleFactory.build_{consumer}_bundle()
          │   ├─ RiskBundle: primary_finding + related + control_mapping + maturity_context
          │   ├─ PlanningBundle: related_findings + control_mapping_ids + capability_ids
          │   └─ ReportBundle: primary_topics + key_findings + control_themes + practices
          └─ PromptFormatter.format() → prompt-ready text
              │
              ▼
          ContextBuildResponse {consumer, bundle, diagnostics, warnings}
```

### 4.4 Agent System — Luồng PDCA End-to-End

```
User Request: "Check S3 security"
  │
  ▼
[1] EnvironmentAgent.get_aws_context()
  │  → {account_id, region, identity_arn}
  │
  ▼
[2] PlanningAgent.run(user_request)
  │  ├─ Fast Track: Regex detect explicit check IDs
  │  ├─ LLM Translation: user request → {target_service, search_queries}
  │  ├─ ★ RAG Call: POST /v1/retrieve/checks (hybrid search)
  │  ├─ Service filtering: Hard-filter by target_service
  │  └─ LLM Re-ranking: Chain-of-Thought → top 5 check IDs
  │  → assessment_plan: {groups_to_scan, checks_to_scan, reasoning}
  │
  ▼
[3] ScannerAgent.run_batch()
  │  → scan_job_ids: [job_id_1, job_id_2, ...]
  │
  ▼
[4] MonitoringAgent.run(job_ids)
  │  ├─ Polling loop: check_job_status() every N seconds
  │  └─ Normalize findings via shared/normalizer.py
  │  → raw_findings: [{finding_uid, check_id, service, severity, status, ...}]
  │  → Persisted to data/pre_scan.json
  │
  ▼
[5] RiskEvaluationAgent.run(findings)
  │  ├─ Filter: chỉ lấy findings có status="FAIL"
  │  ├─ ★ RAG Call: POST /v1/context/build (consumer="risk", batch)
  │  │   → official_severity, compliance_mappings, maturity context
  │  ├─ LLM Scoring: per-finding evaluation against rubric
  │  └─ Sort by severity + risk_score
  │  → prioritized_findings: [{...finding, ai_severity, ai_risk_score, ai_reasoning}]
  │
  ▼
[route_after_risk] — Nếu không có FAIL → skip to report
  │
  ▼
[6] RemediationPlannerAgent.plan_remediation(findings)
  │  ├─ Cho mỗi FAIL finding:
  │  │   ├─ LLM chọn tool_name từ danh sách tools
  │  │   ├─ Auto-build tool_params từ finding data
  │  │   └─ Mark manual_required nếu tool yêu cầu
  │  → remediation_tasks: [{finding_id, tool_id, params, reasoning, manual_required}]
  │
  ▼
[7] ReviewTask (Human-in-the-Loop)
  │  ├─ Hiển thị từng task cho user
  │  └─ User approve/skip/modify
  │  → task_execution_plan: {task_id: "approve"/"skip"}
  │
  ▼
[8] ExecutionAgent.execute_all(tasks, decisions)
  │  ├─ Chỉ thực thi tasks được "approve"
  │  ├─ Tool execution qua boto3
  │  └─ Error handling: ClientError, BotoCoreError
  │  → execution_logs: [{task_id, tool_name, status, output, duration}]
  │
  ▼
[9] Verification
  │  ├─ RescanAgent: Quét lại cùng checks → data/post_scan.json
  │  └─ AnalysisAgent: So sánh pre_scan vs post_scan
  │     → analysis_diff: [{finding_uid, before_status, after_status, action}]
  │     → stats: {fixed, manual_required, failed, unchanged}
  │
  ▼
[10] ReportAgent.run(report_context)
   ├─ LLM generate executive summary
   ├─ Tables + statistics
   ├─ Charts (pie chart, severity bar)
   └─ Export: MD → HTML → PDF
   → data/final_report.{md,html,pdf}
```

---

## 5. ĐIỂM MẠNH VÀ ĐIỂM YẾU

### 5.1 RAG System

#### Điểm mạnh

| # | Điểm mạnh | Giải thích |
|---|---|---|
| 1 | **Kiến trúc phân lớp rõ ràng** | Separation of Concerns giữa API → Service → Retrieval → Index → Data. Dễ test, dễ thay thế từng lớp |
| 2 | **Hybrid Retrieval (BM25 + Vector)** | Kết hợp lexical precision (BM25 tốt cho exact terms) + semantic understanding (vector tốt cho paraphrase). RRF merge k=60 cân bằng hai nguồn |
| 3 | **Cross-Encoder Reranking** | Rerank top candidates bằng learned model thay vì heuristics. Cải thiện đáng kể ranking quality |
| 4 | **Consumer-Specific Context** | Bundle khác nhau cho Planning/Risk/Report agent. Mỗi agent nhận đúng thông tin cần thiết, giảm noise |
| 5 | **Quality Signals** | Confidence level + Verification warnings giúp agent biết khi nào cần cẩn trọng với kết quả |
| 6 | **Entity Gating** | Ngăn false positives (e.g., Bedrock capabilities không lọt vào S3 context). Forbidden capability rate = 0% |
| 7 | **Graceful Degradation** | Vector fail → lexical fallback. System không crash khi một component lỗi |
| 8 | **Configuration-Driven** | scoring_config.json externalize tất cả thresholds. Dễ tune mà không sửa code |
| 9 | **Benchmark Infrastructure** | 60+ test cases, release criteria rõ ràng, automated benchmarking |

#### Điểm yếu

| # | Điểm yếu | Mức độ | Ảnh hưởng |
|---|---|---|---|
| 1 | **Mapping quality thấp ngoài S3** | CRITICAL | 502 auto-generated mappings, chỉ S3 được curated. Agents sẽ nhận sai compliance mappings cho non-S3 services |
| 2 | **Semantic search yếu cho natural language** | HIGH | Semantic hard queries chỉ đạt 25% Top-1. Agents dùng câu tự nhiên sẽ nhận kết quả kém |
| 3 | **Latency vượt ngưỡng** | MEDIUM | 2.1s vs target 2.0s. Khi agent gọi nhiều RAG requests nối tiếp, latency tích lũy đáng kể |
| 4 | **URL endpoints không nhất quán** | HIGH | PlanningAgent dùng `localhost:8111/retrieve`, RiskAgent dùng `localhost:8001/v1/context/build`. Chứng tỏ API đã thay đổi nhưng agents chưa update đồng bộ |
| 5 | **Thiếu caching** | MEDIUM | Cùng check_id có thể được query nhiều lần trong một pipeline run mà không có cache |
| 6 | **BM25 thiếu stemming/lemmatization** | MEDIUM | Handcrafted aliases chỉ cover ~7 S3 checks. Mở rộng sang services khác rất tốn effort |

### 5.2 Agent System

#### Điểm mạnh

| # | Điểm mạnh | Giải thích |
|---|---|---|
| 1 | **PDCA Architecture** | Quy trình hoàn chỉnh: Plan → Do → Check → Act. Có verification loop (rescan + diff) |
| 2 | **Human-in-the-Loop** | User approve từng remediation task. Ngăn chặn thao tác nguy hiểm không mong muốn |
| 3 | **Deterministic Tool Execution** | ScannerAgent + ExecutionAgent không dùng LLM cho tool calling → an toàn, predictable |
| 4 | **Performance Metrics** | Track timing cho mọi step + LLM latency. Giúp identify bottlenecks |
| 5 | **Finding Normalization** | shared/normalizer.py chuẩn hóa OCSF format → internal format. Tạo consistent data flow |
| 6 | **Modular Agent Design** | Mỗi agent là independent class, dễ test và thay thế |

#### Điểm yếu

| # | Điểm yếu | Mức độ | Ảnh hưởng |
|---|---|---|---|
| 1 | **RAG integration không đồng bộ** | CRITICAL | PlanningAgent gọi endpoint cũ (`/retrieve`), RiskAgent gọi endpoint mới (`/v1/context/build`). RemediationPlannerAgent + ReportAgent không dùng RAG |
| 2 | **Hardcoded URLs** | HIGH | `localhost:8111`, `localhost:8001`, `localhost:8000` scattered trong code. Không dùng config centralized |
| 3 | **Thiếu error handling cho RAG calls** | HIGH | PlanningAgent gọi RAG nhưng nếu RAG down, fallback logic không robust |
| 4 | **RemediationPlannerAgent không dùng RAG** | MEDIUM | LLM chọn tool dựa trên description thuần túy. RAG context (remediation best practices, compliance) sẽ cải thiện chất lượng planning |
| 5 | **ReportAgent không dùng RAG** | MEDIUM | Report thiếu compliance context, maturity references. RAG sẽ enrich report quality |
| 6 | **Thiếu retry/circuit breaker cho API calls** | MEDIUM | Nếu RAG service slow/down, agent pipeline có thể hang |
| 7 | **JSON parsing fragile** | LOW | Nhiều regex-based JSON extraction. Nếu LLM output khác format, có thể fail silently |

---

## 6. PHÂN TÍCH CÁC ĐIỂM TÍCH HỢP HIỆN TẠI

### 6.1 Các Agent đã tích hợp RAG

#### PlanningAgent → RAG `/v1/retrieve/checks`

```
PlanningAgent
  │
  ├─ URL: http://localhost:8111/retrieve (⚠ ENDPOINT CŨ)
  │   và http://localhost:8001/v1/retrieve/checks
  ├─ Method: POST
  ├─ Payload: {query, service, top_k, retrieval_mode: "hybrid"}
  ├─ Sử dụng: Tìm check IDs phù hợp với user request
  └─ Kết quả: Danh sách check_ids → input cho ScannerAgent
```

**Vấn đề:**
- Gọi 2 URLs khác nhau (cũ + mới) → cần thống nhất
- Chỉ dùng `retrieve/checks`, không dùng `context/build` → thiếu maturity context cho planning
- Không truyền `consumer="planning"` → không nhận được PlanningBundle optimized

#### RiskEvaluationAgent → RAG `/v1/context/build`

```
RiskEvaluationAgent
  │
  ├─ URL: http://localhost:8001/v1/context/build
  ├─ Method: POST
  ├─ Payload: {consumer: "risk", findings: [...], include_mappings: true}
  ├─ Sử dụng: Lấy official_severity + compliance_mappings cho mỗi finding
  └─ Kết quả: RAG context → inject vào LLM prompt cho risk scoring
```

**Đánh giá:** Đây là tích hợp tốt nhất hiện tại. Đã dùng đúng endpoint mới, truyền consumer type, nhận được RiskBundle.

### 6.2 Các Agent CHƯA tích hợp RAG

| Agent | Cần RAG? | Consumer Type | Lý do |
|---|---|---|---|
| **RemediationPlannerAgent** | **Có** | `planning` | RAG cung cấp remediation best practices, compliance requirements. Giúp LLM chọn tool chính xác hơn |
| **ReportAgent** | **Có** | `report` | RAG cung cấp compliance themes, maturity context. Report sẽ giàu thông tin hơn |
| **AnalysisAgent** | Tùy chọn | `report` | RAG context giúp đánh giá mức độ cải thiện maturity sau remediation |
| **EnvironmentAgent** | Không | — | Chỉ lấy AWS metadata, không cần knowledge retrieval |
| **ScannerAgent** | Không | — | Deterministic tool execution, không cần reasoning |
| **MonitoringAgent** | Không | — | Polling + normalization, không cần reasoning |
| **ExecutionAgent** | Không | — | Deterministic tool execution |

---

## 7. ĐỀ XUẤT CẢI THIỆN TRƯỚC KHI TÍCH HỢP

### 7.1 RAG System — Cải thiện cần thiết

#### P0 (Bắt buộc trước khi tích hợp)

**[R-P0-1] Thống nhất API endpoints**
- Hiện tại: `/retrieve` (cũ) vs `/v1/retrieve/checks` (mới)
- Giải pháp: Loại bỏ hoàn toàn endpoint cũ, cập nhật tất cả agents dùng `/v1/*`
- Ảnh hưởng: PlanningAgent, graph_orchestator.py

**[R-P0-2] Đảm bảo S3 mapping quality**
- Hiện tại: S3 mappings đã curated → 100% agent readiness
- Kiểm tra: Verify rằng tất cả S3 checks có mapping chính xác
- Benchmark: S3 Agent Readiness = 100% (đã đạt)

**[R-P0-3] Thêm health check cho agents**
- Giải pháp: RAG API expose `/ready` endpoint → agents kiểm tra trước khi gọi
- Fallback: Nếu RAG down, agent vẫn hoạt động ở chế độ degraded

#### P1 (Nên làm trước tích hợp)

**[R-P1-1] Thêm response caching**
- Giải pháp: Cache kết quả theo (query, check_id, consumer) với TTL 5 phút
- Lý do: Trong 1 pipeline run, cùng check_id có thể được query bởi nhiều agents

**[R-P1-2] Cải thiện latency**
- Hiện tại: 2.1s average
- Giải pháp: Parallel BM25 + Vector search (đã implement), giảm reranker top_n từ 20 → 10 cho non-critical queries

**[R-P1-3] Batch endpoint**
- Giải pháp: Thêm `/v1/context/build/batch` cho phép gọi nhiều check_ids trong 1 request
- Lý do: RiskEvaluationAgent hiện gọi 1 request per finding → N requests cho N findings

### 7.2 Agent System — Cải thiện cần thiết

#### P0 (Bắt buộc trước khi tích hợp)

**[A-P0-1] Centralize API configuration**
- Hiện tại: URLs hardcoded scattered trong từng agent file
- Giải pháp: Tạo `config.py` hoặc `.env` chứa tất cả service URLs
  ```
  RAG_API_URL=http://localhost:8001
  SCANNER_API_URL=http://localhost:8000
  OLLAMA_URL=http://localhost:11434
  ```

**[A-P0-2] Cập nhật PlanningAgent → dùng endpoint mới**
- Hiện tại: `localhost:8111/retrieve` (endpoint cũ)
- Giải pháp: Chuyển sang `localhost:8001/v1/retrieve/checks` hoặc tốt hơn là `localhost:8001/v1/context/build` với `consumer="planning"`

**[A-P0-3] Thêm RAG error handling**
- Giải pháp: Wrap tất cả RAG calls trong try-except với:
  - Timeout: 10s
  - Retry: 1 lần
  - Fallback: Agent hoạt động mà không có RAG context (degraded mode)

#### P1 (Nên làm trước tích hợp)

**[A-P1-1] Tạo RAG Client class**
- Giải pháp: Shared client class cho tất cả agents, thay vì mỗi agent tự viết HTTP call
  ```python
  class RAGClient:
      def retrieve_checks(query, check_id, service, top_k) → dict
      def retrieve_maturity(query, capability_id, domain, top_k) → dict
      def build_context(consumer, findings, check_ids, ...) → dict
      def resolve_mapping(check_id, service) → dict
      def health_check() → bool
  ```

**[A-P1-2] Thêm confidence-based branching**
- Giải pháp: Agents kiểm tra `meta.confidence` từ RAG response
  - `high` → sử dụng kết quả trực tiếp
  - `medium` → sử dụng nhưng thêm caveat
  - `low` → fallback hoặc skip RAG context

---

## 8. KẾ HOẠCH TÍCH HỢP CHI TIẾT

### 8.1 Tổng quan Kế hoạch

```
Phase 0: Chuẩn bị hạ tầng          (Foundation)
Phase 1: Tích hợp PlanningAgent     (Đã có, cần fix)
Phase 2: Tích hợp RiskEvalAgent     (Đã có, cần optimize)
Phase 3: Tích hợp RemediationPlanner (Mới)
Phase 4: Tích hợp ReportAgent       (Mới)
Phase 5: End-to-End Testing         (Validation)
```

### 8.2 Phase 0: Chuẩn bị hạ tầng

**Mục tiêu:** Tạo shared infrastructure cho tất cả agents gọi RAG

**Công việc:**

| # | Task | Chi tiết | Output |
|---|---|---|---|
| 0.1 | Tạo `RAGClient` class | Shared HTTP client với retry, timeout, error handling | `agents/shared/rag_client.py` |
| 0.2 | Tạo centralized config | `.env` + `config.py` chứa service URLs | `config.py`, `.env` |
| 0.3 | Thêm RAG health check | Check RAG readiness trước pipeline run | Trong `environment_node` |
| 0.4 | Xóa endpoint cũ | Remove `/retrieve` (cũ), thống nhất `/v1/*` | RAG `routes/__init__.py` |

**RAGClient Interface:**

```python
class RAGClient:
    """Shared RAG API client cho tất cả agents"""

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url
        self.timeout = timeout

    def retrieve_checks(self, query: str = None, check_id: str = None,
                        service: str = None, top_k: int = 5,
                        retrieval_mode: str = "hybrid") -> dict:
        """Retrieve check documents"""

    def retrieve_maturity(self, query: str = None, capability_id: str = None,
                          domain: str = None, top_k: int = 5) -> dict:
        """Retrieve maturity capability documents"""

    def build_context(self, consumer: str, findings: list = None,
                      check_ids: list = None, service: str = None,
                      domain: str = None, top_k: int = 5,
                      include_mappings: bool = True,
                      include_maturity: bool = True) -> dict:
        """Build agent-ready context bundle"""

    def resolve_mapping(self, check_id: str, service: str = None) -> dict:
        """Resolve check-to-capability mapping"""

    def is_healthy(self) -> bool:
        """Check RAG service readiness"""
```

### 8.3 Phase 1: Cải thiện tích hợp PlanningAgent

**Hiện trạng:** PlanningAgent đã gọi RAG nhưng dùng endpoint cũ và chỉ dùng `retrieve/checks`

**Mục tiêu:** Chuyển sang `context/build` với `consumer="planning"` để nhận PlanningBundle

**Công việc:**

| # | Task | Chi tiết |
|---|---|---|
| 1.1 | Replace URL cũ | `localhost:8111/retrieve` → `RAGClient.build_context(consumer="planning")` |
| 1.2 | Cập nhật payload | Truyền `consumer="planning"`, `check_ids`, `service` |
| 1.3 | Parse PlanningBundle | Sử dụng `related_findings` + `control_mapping_ids` từ bundle |
| 1.4 | Fallback logic | Nếu RAG down → fallback về group scan |
| 1.5 | Confidence check | Nếu confidence="low" → mở rộng scope (group scan thay vì specific checks) |

**Luồng mới:**

```
PlanningAgent.run(user_request)
  │
  ├─ LLM Translation: request → {target_service, search_queries}
  │
  ├─ ★ RAGClient.build_context(
  │     consumer="planning",
  │     query=search_queries[0],
  │     service=target_service,
  │     top_k=10
  │   )
  │   → PlanningBundle:
  │     - related_findings: [{check_id, title, service, severity}]
  │     - control_mapping_ids: [capability_ids]
  │     - maturity_capability_ids: [capability_ids]
  │
  ├─ Extract check_ids từ related_findings
  ├─ LLM Re-ranking với maturity context
  └─ Return assessment_plan
```

### 8.4 Phase 2: Optimize tích hợp RiskEvaluationAgent

**Hiện trạng:** Đã tích hợp đúng cách, nhưng có thể optimize

**Công việc:**

| # | Task | Chi tiết |
|---|---|---|
| 2.1 | Chuyển sang RAGClient | Replace `requests.post()` → `RAGClient.build_context()` |
| 2.2 | Batch optimization | Gom nhiều check_ids vào 1 request thay vì N requests |
| 2.3 | Confidence-based scoring | Nếu RAG confidence="low" → giảm weight của compliance context trong prompt |
| 2.4 | Cache check details | Cache kết quả per check_id trong pipeline run |

### 8.5 Phase 3: Tích hợp RemediationPlannerAgent (MỚI)

**Hiện trạng:** Không dùng RAG. LLM chọn tool thuần dựa trên finding description.

**Mục tiêu:** RAG cung cấp remediation best practices + compliance context → LLM chọn tool chính xác hơn

**Công việc:**

| # | Task | Chi tiết |
|---|---|---|
| 3.1 | Thêm RAG call | `RAGClient.build_context(consumer="planning", findings=[finding])` |
| 3.2 | Extract remediation hints | Từ PlanningBundle: lấy remediation text + maturity guidance |
| 3.3 | Inject vào LLM prompt | Thêm RAG context vào system prompt |
| 3.4 | Fallback | Nếu RAG unavailable → giữ behavior hiện tại |

**Luồng mới:**

```
RemediationPlannerAgent.plan_remediation(finding)
  │
  ├─ ★ RAGClient.build_context(
  │     consumer="planning",
  │     findings=[{check_id, service, status}],
  │     include_mappings=True,
  │     include_maturity=True
  │   )
  │   → PlanningBundle:
  │     - related_findings (remediation text)
  │     - control_mapping_ids (compliance requirements)
  │     - maturity_capability_ids (best practices)
  │
  ├─ Build enriched prompt:
  │   - Finding details
  │   - RAG remediation hints
  │   - Compliance requirements
  │   - Available tools + descriptions
  │
  ├─ LLM chọn tool_name + reasoning
  └─ Build params + return task
```

**Lợi ích dự kiến:**
- LLM biết compliance requirements → chọn tool phù hợp hơn
- RAG cung cấp remediation text chính thức → giảm hallucination
- Maturity guidance → prioritize tools theo best practices

### 8.6 Phase 4: Tích hợp ReportAgent (MỚI)

**Hiện trạng:** Report dựa thuần vào findings data + LLM generation. Thiếu compliance framework, maturity context.

**Mục tiêu:** RAG cung cấp compliance themes + maturity assessment → report chuyên nghiệp hơn

**Công việc:**

| # | Task | Chi tiết |
|---|---|---|
| 4.1 | Thêm RAG call | `RAGClient.build_context(consumer="report", check_ids=[...])` |
| 4.2 | Extract report context | Từ ReportBundle: primary_topics, control_themes, recommended_practices |
| 4.3 | Inject vào report template | Thêm sections: Compliance Assessment, Maturity Evaluation |
| 4.4 | Update markdown template | Thêm sections cho RAG-enriched content |
| 4.5 | Fallback | Nếu RAG unavailable → generate report không có compliance section |

**Luồng mới:**

```
ReportAgent.run(report_context)
  │
  ├─ Extract unique check_ids từ report_context
  │
  ├─ ★ RAGClient.build_context(
  │     consumer="report",
  │     check_ids=unique_check_ids,
  │     include_mappings=True,
  │     include_maturity=True
  │   )
  │   → ReportBundle:
  │     - primary_topics: ["Data Protection", "Access Control"]
  │     - key_findings: [{summary, severity}]
  │     - control_themes: [{capability, domain, guidance}]
  │     - recommended_practices: [str]
  │
  ├─ Merge report_context + ReportBundle
  │
  ├─ LLM generate:
  │   - Executive Summary (enriched with maturity context)
  │   - Compliance Assessment (new section)
  │   - Maturity Evaluation (new section)
  │   - Remediation Results
  │   - Recommendations (enriched with best practices)
  │
  └─ Export MD → HTML → PDF
```

### 8.7 Phase 5: End-to-End Testing

**Công việc:**

| # | Task | Chi tiết | Pass Criteria |
|---|---|---|---|
| 5.1 | Unit tests cho RAGClient | Test mỗi method + error handling | 100% coverage |
| 5.2 | Integration test: Planning + RAG | PlanningAgent nhận đúng checks từ RAG | Check IDs match expected |
| 5.3 | Integration test: Risk + RAG | RiskAgent nhận đúng compliance context | Compliance mappings present |
| 5.4 | Integration test: Remediation + RAG | RemediationPlanner nhận remediation hints | Tool selection accuracy ≥ baseline |
| 5.5 | Integration test: Report + RAG | Report có compliance + maturity sections | Sections non-empty |
| 5.6 | E2E test: Full pipeline | Chạy full PDCA pipeline với RAG enabled | Pipeline completes without error |
| 5.7 | E2E test: RAG degraded mode | Chạy pipeline khi RAG down | Pipeline completes, report generated (degraded) |
| 5.8 | Performance test | Measure total pipeline latency | Latency overhead ≤ 5s vs baseline |
| 5.9 | S3 Scenario test | Full S3 security scan + remediation | All agents produce valid output |

### 8.8 Tóm tắt Dependencies giữa Phases

```
Phase 0 (Foundation) ──→ Phase 1 (PlanningAgent)
         │                     │
         ├──→ Phase 2 (RiskAgent - optimize)
         │                     │
         ├──→ Phase 3 (RemediationPlanner)
         │                     │
         └──→ Phase 4 (ReportAgent)
                               │
                               ▼
                    Phase 5 (E2E Testing)
```

Phase 0 là prerequisite cho tất cả. Phases 1-4 có thể làm song song sau khi Phase 0 xong. Phase 5 cần tất cả Phases 1-4 hoàn thành.

---

## 9. KẾT LUẬN

### 9.1 Đánh giá tổng thể

| Khía cạnh | RAG System | Agent System | Sau tích hợp (dự kiến) |
|---|---|---|---|
| **Architecture** | Mạnh (layered, modular) | Mạnh (state machine, PDCA) | Tương thích tốt |
| **Data Quality** | S3: Tốt, Others: Yếu | — | S3 sẵn sàng, Others cần curation |
| **Retrieval Quality** | Exact: 100%, Semantic: 25-65% | — | Đủ cho agent use cases |
| **Integration Readiness** | API ready, cần fix endpoints | 2/10 agents đã tích hợp | Cần thêm 2-3 agents |
| **Error Handling** | Graceful degradation | Fragile RAG calls | Cần RAGClient + retry |
| **Testing** | Benchmark infrastructure | Thiếu integration tests | Cần E2E test suite |

### 9.2 Rủi ro chính

| Rủi ro | Xác suất | Ảnh hưởng | Mitigation |
|---|---|---|---|
| RAG service down → pipeline fail | Trung bình | Cao | RAGClient với fallback/degraded mode |
| Sai compliance mappings (non-S3) | Cao | Cao | Chỉ tích hợp S3 trước, curation dần |
| Latency tích lũy | Trung bình | Trung bình | Caching + batch requests |
| LLM output format thay đổi | Thấp | Trung bình | Structured output + validation |

### 9.3 Khuyến nghị thứ tự ưu tiên

1. **Ngay lập tức:** Phase 0 (RAGClient + config centralization)
2. **Tiếp theo:** Phase 1 (Fix PlanningAgent integration)
3. **Song song:** Phase 2 (Optimize RiskAgent) + Phase 3 (Tích hợp RemediationPlanner)
4. **Sau đó:** Phase 4 (Tích hợp ReportAgent)
5. **Cuối cùng:** Phase 5 (E2E Testing)

### 9.4 Scope tích hợp khuyến nghị

- **Giai đoạn 1:** Chỉ S3 service (đã validated 100% agent readiness)
- **Giai đoạn 2:** Mở rộng sang IAM, EC2 sau khi curate mappings
- **Giai đoạn 3:** Full service coverage

---

*Báo cáo này được tạo dựa trên phân tích toàn bộ source code của RAG System và Agent System tại `c:\Users\trung\Desktop\DoAn`. Có thể dùng làm tài liệu tham khảo cho quá trình tích hợp.*
