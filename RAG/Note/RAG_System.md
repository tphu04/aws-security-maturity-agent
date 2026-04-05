# RAG System - Phân tích Kiến trúc & Source Code

## Mục lục

1. [Tổng quan Kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Data Flow - Luồng dữ liệu](#2-data-flow---luồng-dữ-liệu)
3. [Phân tích Data Layer](#3-phân-tích-data-layer)
4. [Điểm mạnh](#4-điểm-mạnh)
5. [Điểm yếu còn tồn tại](#5-điểm-yếu-còn-tồn-tại)
6. [Phần có thể tối ưu tiếp](#6-phần-có-thể-tối-ưu-tiếp)
7. [Đề xuất các bước tiếp theo](#7-đề-xuất-các-bước-tiếp-theo)
8. [Changelog so với phiên bản trước](#8-changelog-so-với-phiên-bản-trước)

---

## 1. Tổng quan Kiến trúc

### 1.1 Thành phần hệ thống

Hệ thống RAG được xây dựng trên FastAPI, phục vụ 3 loại consumer (planning, risk, report) với kiến trúc phân tầng:

```
┌─────────────────────────────────────────────────────────────────┐
│                       API Layer (FastAPI)                        │
│  /v1/retrieve/checks  │  /v1/retrieve/maturity  │ /v1/context/build │
│                       │  /v1/resolve/mapping    │                   │
└──────────┬──────────────────────┬──────────────────────┬────────┘
           │                      │                      │
┌──────────▼──────────┐  ┌───────▼─────────┐  ┌────────▼─────────┐
│   CheckService      │  │ MaturityService │  │  ContextService  │
│                     │  │                 │  │                  │
└──────────┬──────────┘  └───────┬─────────┘  └────────┬─────────┘
           │                      │                      │
           └──────────────────────▼──────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │    RetrievalPipeline       │
                    │  ┌─────────┐ ┌──────────┐ │
                    │  │ Router  │ │ Verifier │ │
                    │  └────┬────┘ └──────────┘ │
                    │       │                    │
                    │  ┌────▼────┐ ┌──────────┐ │
                    │  │RRF Merge│ │Confidence│ │
                    │  └────┬────┘ └──────────┘ │
                    │       │                    │
                    │  ┌────▼──────────────────┐ │
                    │  │ CrossEncoder Reranker │ │
                    │  └──────────────────────┘ │
                    └───────┼────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
        ┌─────▼────┐  ┌────▼────┐  ┌─────▼──────┐
        │BM25 Index│  │ Chroma  │  │   Mapping  │
        │(Lexical) │  │(Vector) │  │   Index    │
        └──────────┘  └─────────┘  └────────────┘
                                          │
                    ┌─────────────────────┐│
                    │  ContextBuilder     ││
                    │  ├─IntentDetector   ││
                    │  ├─CoverageSelector ││
                    │  ├─BundleFactory    ││
                    │  └─PromptFormatter  ││
                    └─────────────────────┘│

┌─────────────────────────────────────────────────────────────────┐
│                     Data Layer                                   │
│  raw/ → normalizers.py → normalized/ → build_all.py → indexes/  │
│  577 prowler checks │ 78 capabilities │ ~503 mappings (gated)    │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Corpus Registry (3 corpus)

| Corpus | Mô tả | Số lượng doc | Doc Type |
|--------|--------|-------------|----------|
| `prowler_checks` | Metadata các security check của Prowler (AWS) | 577 | `prowler_check` |
| `maturity_capabilities` | AWS Security Maturity Model capabilities | 78 | `maturity_capability` |
| `maturity_mappings` | Mapping check → capability (auto-generated + curated) | ~503 (sau quality gate) | `maturity_mapping` |

### 1.3 Tích hợp với Orchestrator

Orchestrator (`graph_orchestator.py`) gọi RAG qua **RAGClient** (centralized HTTP client):
- **PlanningAgent** gọi `POST /v1/context/build` (consumer=`planning`) → nhận PlanningBundle
- **RiskEvaluationAgent** gọi `POST /v1/context/build` (consumer=`risk`) → nhận RiskBundle
- **RemediationPlannerAgent** gọi `POST /v1/context/build` → nhận context cho remediation
- **ReportAgent** gọi `POST /v1/context/build` (consumer=`report`) → nhận ReportBundle
- Giao tiếp **loosely coupled** qua REST API, URL quản lý tập trung tại `config.py`
- RAG health check tích hợp vào orchestrator startup

---

## 2. Data Flow - Luồng dữ liệu

### 2.1 Build Pipeline (Offline)

```
Raw JSON (prowler_checks.json, maturity_capabilities.json)
    │
    ▼
[gen_maturity_mapping.py] ──────► maturity_mappings.json (raw/auto-generated)
    │                              (BM25 scoring + heuristic + synonym canon.)
    │
    ├── maturity_mappings_curated.json ◄── Manual curation (21 S3 mappings, approved)
    │
    ▼
[build_all.py]
    ├── normalize_prowler_doc()  ──► normalized/prowler_checks.json
    │   └── build_retrieval_text_prefixed() (field-level prefixes, no code snippets)
    │   └── _check_aliases() (semantic enrichment)
    │   └── tokenize() (stemming + stopword removal)
    │
    ├── normalize_maturity_doc() ──► normalized/maturity_capabilities.json
    │   └── build_retrieval_text_prefixed() (truncated summary, skip duplicate recommendation)
    │   └── _capability_aliases() (semantic enrichment)
    │
    ├── normalize_mapping_doc()  ──► normalized/maturity_mappings.json
    │   └── Quality gate: min_score=0.25, min_score_gap=0.05
    │   └── Merge curated (approved) + auto-generated (draft)
    │
    ├── Build BM25 per corpus ────► indexes/bm25/*.pkl
    │   └── Tokenization: lowercase + split + stemming (Snowball) + stopword removal
    │   └── Parameters: k1=1.2, b=0.6
    │
    ├── Build Chroma per corpus ──► indexes/chroma/
    │   └── Embedding: all-MiniLM-L6-v2 (explicit SentenceTransformerEmbeddingFunction)
    │
    └── Write manifest ───────────► indexes/manifest.json
```

### 2.2 Query Pipeline (Online)

```
Client request (query, service, consumer)
    │
    ▼
[SemanticRouter.route()] ─── Phân loại query type:
    │                         check_search / maturity_search /
    │                         mapping_resolution / context_build
    │   Heuristics:
    │   ├── looks_like_check_id() (3+ parts, known service, 12+ chars)
    │   ├── looks_like_capability_id() (2-8 parts, 8+ chars, no spaces)
    │   ├── hint terms (MATURITY_HINT_TERMS / CHECK_HINT_TERMS)
    │   └── Fallback: check_search
    ▼
[RetrievalPipeline.retrieve()]
    ├── Exact lookup path (check_id / capability_id / mapping)
    │   └── BM25 exact match → score=1.0
    │
    └── Semantic search path (parallel via ThreadPoolExecutor)
        ├── BM25 lexical search (top_k * 3, min 10)
        ├── Chroma vector search (top_k * 3, min 10)
        └── RRF merge (k=60) + metadata bonus (service=+0.03, domain=+0.02)
            │
            ▼
        [CrossEncoderReranker.rerank()] → sigmoid-normalized scores [0,1]
        │   Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (~22MB)
        │   Passage extraction: retrieval_text → fallback title/description
            │
            ▼
        [verify_retrieval()] → warnings (severe / moderate)
        [calculate_confidence()] → high/medium/low (route-aware thresholds)
            │
            ▼
        Response with results + meta + diagnostics
```

### 2.3 Context Build Pipeline (Online)

```
ContextBuildRequest (consumer, check_ids, capability_ids, findings, query)
    │
    ▼
[ContextService.build()]
    │
    ├── Step 1: Retrieve checks ──► CheckService.search()
    │   ├── Per check_id: exact lookup (score=1.0)
    │   └── Query-driven: top_k=15 for planning, top_k=5 default
    │
    ├── Step 2: Resolve mappings ──► MappingService.resolve()
    │   ├── Per selected check_id
    │   └── filter_for_agent_context(): prefer approved/reviewed over draft
    │
    ├── Step 3: Retrieve maturity ─► MaturityService.search()
    │   ├── Per capability_id from mappings + requested capability_ids
    │   └── Filter to matching capabilities
    │
    ├── Step 4: Aggregate confidence + warnings
    │   └── Takes highest confidence from components
    │
    └── Step 5: Build context ────► ContextBuilder.build()
        │
        ├── IntentDetector
        │   ├── detect_query_intents() → QUERY_INTENT_CLUSTERS matching
        │   ├── infer_control_families() → CONTROL_INTENT_CLUSTERS matching
        │   ├── mapping_passes_entity_gate() → PRODUCT_ENTITY_GATES validation
        │   └── capability_domain_mismatch() → product-specific filtering
        │
        ├── CoverageSelector
        │   ├── select_checks() → (requested, related) with dedup
        │   │   └── planning_coverage_select(): 3-pass greedy
        │   │       Pass 1: One per detected intent
        │   │       Pass 2: New service coverage
        │   │       Pass 3: Fill by highest score
        │   │       Target: clamp(len(intents)*2, min=2, max=8)
        │   ├── select_mappings() → entity-gated, ranked by mapping_sort_key
        │   └── select_capabilities() → domain-filtered
        │
        ├── BundleFactory
        │   ├── build_planning_bundle() → findings + control_mapping_ids + capability_ids
        │   ├── build_risk_bundle() → primary_finding + related + mappings + maturity
        │   ├── build_report_bundle() → topics + findings + themes + practices
        │   └── evaluate_bundle_confidence() → semantic quality scoring
        │
        └── PromptFormatter
            ├── format() → PromptReadyContext (header + evidence + guidance)
            └── build_evidence_summary() → evidence items for diagnostics
```

---

## 3. Phân tích Data Layer

### 3.1 Raw Data Quality

**prowler_checks.json (577 docs)**
- Nguồn: Prowler metadata export
- Chất lượng tốt: có cấu trúc rõ ràng (CheckID, ServiceName, Severity, Description, Risk, Remediation)
- Remediation chứa code examples (CLI, Terraform, CloudFormation) → **đã được loại khỏi retrieval_text** (chỉ giữ `Remediation.Recommendation.Text`)
- Một số check có Description/Risk trùng lặp nội dung

**maturity_capabilities.json (78 docs)**
- Nguồn: AWS Security Maturity Model (crawled)
- Chất lượng trung bình:
  - Nhiều capability có `summary` rất dài (>500 từ) → **đã truncate xuống 300 từ max**
  - `recommendation` trùng với `summary` trong 97% docs → **đã skip khi trùng**
  - `how_to_check` thường empty
  - Không có `capability_id` rõ ràng từ nguồn → sinh từ `title` qua slugify

**maturity_mappings (~503 docs sau quality gate)** 
- Nguồn: **Auto-generated** bởi `gen_maturity_mapping.py` + **Curated** (21 S3 mappings)
- **Curated mappings** (21 docs):
  - `review_status: "approved"`, `mapping_confidence: "high"`
  - Cover top S3 critical checks → đảm bảo agent context đúng cho S3
- **Auto-generated mappings** (~482 docs sau quality gate):
  - Phương pháp: BM25 bag-of-words scoring + synonym canonicalization + heuristic bonuses
  - Quality gate loại bỏ: `score < 0.25` hoặc `score_gap_vs_second < 0.05`
  - Phần lớn `review_status: "draft"` → ContextService filter để prefer approved/reviewed
  - ~70 mapping bị loại bởi quality gate so với bản gốc 573

### 3.2 Normalization Quality

File `normalizers.py` (756 dòng) thực hiện:
- Unicode NFKC normalization
- Whitespace cleaning
- Identifier normalization (snake_case, dashes → underscores)
- **Tokenization nâng cao**: lowercase → split → Snowball stemming → stopword removal
  - Stopwords: 16 English standard + AWS domain-specific (aws, amazon, service, resource, check, account, configuration, setting)
- **Retrieval text với field-level prefixes**: `build_retrieval_text_prefixed()`
  - Prowler: `"check: {check_id}\nservice: {service}\ntitle: {title}\nrisk: {risk}\ndescription: {description}"`
  - Maturity: `"capability: {id}\ndomain: {domain}\ntitle: {title}\nsummary: {summary (truncated)}"`
  - **Không chứa code snippets** (Terraform/CloudFormation/CLI đã bị loại)
- **Alias generation**: `_check_aliases()` và `_capability_aliases()`
  - S3 checks: ~7 checks có 30+ phrases mỗi check
  - Capabilities: ~6 capability families có aliases
  - Phần còn lại không có semantic enrichment (limitation)

### 3.3 Index Quality

**BM25 Index** (`lexical_index.py`):
- Tokenization: lowercase + split + **Snowball stemming** + **stopword removal**
  - `"encrypted data"` → `["encrypt", "data"]`
  - `"encryption of data"` → `["encrypt", "data"]` (stemming đảm bảo match)
- Parameters: **k1=1.2, b=0.6** (tuned cho shorter retrieval texts sau restructure)
- Exact lookup: check_id, capability_id (score=1.0)
- Subsequence matching cho capability_id (fallback)

**Chroma Vector Index** (`vector_index.py`):
- Embedding model: **`all-MiniLM-L6-v2`** (384 dims) — **explicit binding** qua `SentenceTransformerEmbeddingFunction`
- Binding được truyền vào cả `build_collection()` và `get_collection()` → đảm bảo consistency
- Distance conversion: `1/(1+distance)` → similarity score
- Lazy model loading với suppressed logging (sentence_transformers, transformers, torch)
- Collection-per-corpus pattern: 3 collections (prowler_checks, maturity_capabilities, maturity_mappings)

**Cross-Encoder Reranker** (`reranker.py`):
- Model: **`cross-encoder/ms-marco-MiniLM-L-6-v2`** (~22MB, ~5ms per pair)
- Singleton pattern: lazy load trên first use, cached
- Output: sigmoid-normalized scores [0, 1]
- Passage extraction: `retrieval_text` → fallback `title + description + summary`
- Thay thế các handcrafted scoring heuristics cũ (intent_bonus, product_penalty)

---

## 4. Điểm mạnh

### 4.1 Kiến trúc phân tầng rõ ràng

- **Separation of Concerns**: API routes → Services → Pipeline → Indexes. Mỗi layer có trách nhiệm rõ ràng.
- **Dependency Injection**: Services nhận pipeline qua constructor, dễ test và mock.
- **Corpus-aware design**: Mỗi corpus có BM25 index và Chroma collection riêng → tránh cross-corpus pollution.

### 4.2 Hybrid Retrieval với RRF + Cross-Encoder

- Kết hợp BM25 (lexical) + Vector (semantic) qua **Reciprocal Rank Fusion** (k=60).
- **Cross-encoder reranking** sau RRF merge: `cross-encoder/ms-marco-MiniLM-L-6-v2` cải thiện top-1 accuracy cho semantic queries.
- Exact lookup path riêng cho check_id/capability_id → không bị ảnh hưởng bởi ranking noise.
- Graceful degradation: vector failure không kill toàn bộ pipeline, fallback về lexical-only.
- Parallel search: BM25 + Vector search chạy đồng thời qua `ThreadPoolExecutor`.

### 4.3 Quality Signals tốt

- **Verification system** (`verifier.py`): tự phát hiện exact_lookup_miss, service_mismatch, ambiguous_top_results, low_score_top1, weak_domain_alignment.
  - Severe warnings → force confidence=low.
  - Moderate warnings → penalty high→medium.
- **Confidence estimation** (`confidence.py`): route-aware thresholds cho từng query type.
- **Review flags**: `review_recommended` propagate từ pipeline lên response → consumer biết khi nào cần cẩn thận.

### 4.4 Context Builder modular (đã refactor)

ContextBuilder (trước đây 55KB monolith) đã được **tách thành 6 module** (tổng ~1,408 dòng):
- `context_builder.py` (157 dòng): Facade, orchestrate
- `coverage_selector.py` (383 dòng): Coverage-aware selection, planning diversification
- `bundle_factory.py` (346 dòng): Consumer-specific bundles + confidence evaluation
- `intent_detector.py` (133 dòng): Query intent detection, entity gating
- `prompt_formatter.py` (210 dòng): Prompt-ready context formatting
- `_helpers.py` (179 dòng): Shared utilities (compression, extraction, normalization)

Bundle schema riêng cho mỗi consumer:
- **PlanningBundle**: findings + control_mapping_ids + capability_ids (ID-focused cho scope determination)
- **RiskBundle**: primary_finding + related + mappings + maturity (detailed cho violation analysis)
- **ReportBundle**: topics + findings + themes + practices (narrative-focused)

### 4.5 Centralized Configuration & Constants

- **`config.py`**: Tất cả paths, model names, BM25 params, scoring config tập trung một nơi.
- **`constants.py`**: Single source of truth cho `CONTROL_INTENT_CLUSTERS`, `QUERY_INTENT_CLUSTERS`, `PRODUCT_ENTITY_GATES`, `KNOWN_SERVICES`, hint terms.
  - Trước đây bị duplicate giữa pipeline.py, context_builder.py, gen_maturity_mapping.py → **đã centralize**.
- **`scoring_config.json`**: Externalized scoring parameters (RRF k, metadata bonus, reranker config, confidence thresholds, ambiguity, verification).
  - Cho phép tune parameters mà không cần sửa code.
  - `load_scoring_config()` với deep merge support + cache + reload.
- **`utils.py`**: Shared `mapping_sort_key()` — **single implementation** thay vì duplicate giữa pipeline và mapping_service.

### 4.6 Mapping Quality Control

- **Curated mappings** (`maturity_mappings_curated.json`): 21 S3 mappings với `review_status: "approved"`.
- **Quality gate** trong build pipeline: `min_score=0.25`, `min_score_gap=0.05` → loại ~70 low-quality mappings.
- **Product entity gates**: 11 gates (bedrock, genai, sagemaker, guardduty, macie, inspector, waf, shield, securityhub) → ngăn false-positive cross-product mappings.
- **Mapping ranking**: Deterministic via `(review_status_rank, confidence_rank, score, capability_id)`.
  - approved(10) > reviewed(5) > auto_high(2) > draft(1)
- **ContextService filtering**: `filter_for_agent_context()` prefer approved/reviewed; draft mappings chỉ dùng khi không có lựa chọn tốt hơn.

### 4.7 Build Pipeline tự contained

- `build_all.py` thực hiện full pipeline: normalize → validate → build BM25 → build vector → write manifest.
- Manifest tracking: version, build time, doc counts → dễ audit và rollback.
- Duplicate doc_id validation trước khi build.
- Merge curated + auto-generated mappings.

### 4.8 Test & Benchmark infrastructure

- **19 test items** (files + directories) covering API, service, contract, retrieval, vector, mapping, bundle, coverage, intent, semantic confidence.
- **Benchmark framework**:
  - `benchmark_topk_accuracy.py`: 60+ test cases across 4 categories (exact, paraphrase, risk, semantic_hard).
  - `benchmark_s3_agent_readiness.py`: S3-specific benchmark với readiness criteria cho 3 consumers.
  - Ground truth labels: expected doc_id, forbidden_capability_ids.
  - Automated regression detection.

---

## 5. Điểm yếu còn tồn tại

### 5.1 [HIGH] Retrieval accuracy cho Risk & Semantic queries còn thấp

- **Risk queries**: Top-1 = 16.7% (target ≥ 40%)
- **Semantic hard queries**: Top-1 = 25%, Top-5 = 37.5% (target ≥ 40% top-1)
- **Root cause**: `all-MiniLM-L6-v2` (384 dims) có semantic discrimination yếu cho complex queries. Cross-encoder cải thiện nhưng chưa đủ cho risk-phrased queries (e.g., "what if someone accesses bucket publicly" vs "block_public_access").
- Score gaps giữa top candidates rất nhỏ (~0.001) → ranking không ổn định.

### 5.2 [HIGH] Auto-generated Mappings vẫn chiếm phần lớn

**File:** `scripts/gen_maturity_mapping.py`

- ~482 mappings vẫn `review_status: "draft"` (sau quality gate).
- Chỉ 21 curated mappings (S3 only) → các service khác (IAM, EC2, RDS...) vẫn phụ thuộc auto-generated.
- BM25 bag-of-words scoring không hiểu semantic intent → false positive vẫn có thể xảy ra ngoài S3.
- ContextService filter giảm thiểu impact, nhưng không loại bỏ hoàn toàn.

### 5.3 [MEDIUM] Handcrafted aliases không scale

**File:** `app/ingestion/normalizers.py`

- Aliases hardcode cho ~7 S3 checks và ~6 capabilities.
- 570+ checks còn lại không có semantic enrichment.
- Mỗi khi thêm service mới phải sửa code → vi phạm Open/Closed Principle.

### 5.4 [MEDIUM] Latency chưa đạt target

- Average latency: **2,144ms** (target ≤ 2,000ms).
- Cross-encoder reranking thêm ~5ms per pair nhưng overall pipeline vẫn hơi chậm.
- Nguyên nhân: multiple sequential service calls trong ContextService (check → mapping → maturity).

### 5.5 [LOW] Orphaned Chroma collections

- Có thể còn UUID directories trong `data/indexes/chroma/` từ builds cũ.
- `delete_collection()` chỉ xóa collection theo tên, không dọn orphaned data.

---

## 6. Phần có thể tối ưu tiếp

### 6.1 Tối ưu

| Component | Hành động | Impact dự kiến |
|-----------|-----------|---------------|
| Embedding model | Nâng cấp lên model lớn hơn (e.g., `all-MiniLM-L12-v2` hoặc `bge-small-en-v1.5`) | Cải thiện semantic discrimination cho risk/semantic queries |
| Curated mappings | Mở rộng curation sang IAM, EC2, RDS (top-20 checks mỗi service) | Giảm phụ thuộc auto-generated mappings |
| Query rewriting | Thêm LLM-based query rewriting trước search | Cải thiện risk/paraphrase recall |
| Batch operations | ContextService batch retrieve thay vì sequential per-check | Giảm latency |
| Handcrafted aliases | Thay bằng LLM-generated aliases hoặc query expansion | Scale tốt hơn, cover nhiều services |
| Orphaned cleanup | Thêm full cleanup trong build pipeline | Tiết kiệm disk |

### 6.2 Đã hoàn thành (từ bản trước)

| Vấn đề cũ | Giải pháp đã implement | Status |
|-----------|------------------------|--------|
| Vector embedding không explicit binding | `SentenceTransformerEmbeddingFunction(all-MiniLM-L6-v2)` explicit | ✅ Done |
| Retrieval text flat concatenation + code noise | Field-level prefixes + loại code snippets + truncate | ✅ Done |
| Mapping quality thấp, 0% filtering | Quality gate (min_score, min_score_gap) + 21 curated S3 | ✅ Done |
| BM25 thiếu stemming/stopwords | Snowball stemmer + stopword removal + tuned k1/b | ✅ Done |
| Scoring heuristics hardcoded | Cross-encoder reranker + externalized scoring_config.json | ✅ Done |
| ContextBuilder monolith (55KB) | Tách thành 6 module (ContextBuilder, CoverageSelector, BundleFactory, IntentDetector, PromptFormatter, _helpers) | ✅ Done |
| Duplicate logic (mapping_sort_key, constants) | Centralized utils.py + constants.py | ✅ Done |
| Duplicate ContextBuildRequest | Cleaned up, single definition | ✅ Done |
| Agent integration scattered URLs | Centralized config.py + RAGClient | ✅ Done |

---

## 7. Đề xuất các bước tiếp theo

### Phase 1: Cải thiện Retrieval cho Risk & Semantic queries

#### 1.1 Query Rewriting / Expansion
- **Vấn đề**: Risk-phrased queries dùng language khác hoàn toàn so với retrieval text
- **Hành động**: Thêm lightweight LLM-based query rewriting trước khi search
- **Tại sao**: "what if someone accesses bucket publicly" cần được rewrite thành "s3 block public access" để match

#### 1.2 Nâng cấp Embedding Model
- **Vấn đề**: `all-MiniLM-L6-v2` (384 dims) có semantic discrimination yếu
- **Hành động**: Đánh giá `bge-small-en-v1.5` hoặc `all-MiniLM-L12-v2` trên benchmark
- **Tại sao**: Model lớn hơn có thể cải thiện Top-1 accuracy cho semantic/risk queries mà không tăng latency đáng kể

#### 1.3 Mở rộng Curated Mappings
- **Vấn đề**: Chỉ S3 có curated mappings (21 docs)
- **Hành động**: Curate top-20 mappings cho IAM, EC2, RDS
- **Tại sao**: Mapping sai → agent context sai, không fix được bằng tuning retrieval

### Phase 2: Performance & Scale

#### 2.1 Batch Context Building
- **Vấn đề**: ContextService gọi sequential per-check (N requests)
- **Hành động**: Batch retrieve checks + parallel mapping resolution
- **Tại sao**: Giảm latency từ ~2.1s xuống target ≤ 2s

#### 2.2 LLM-assisted Alias Generation
- **Vấn đề**: Handcrafted aliases chỉ cover ~7 S3 checks
- **Hành động**: Dùng LLM để generate aliases cho top-100 checks
- **Tại sao**: Scale tốt hơn, cover nhiều services, giảm maintenance burden

### Phase 3: Dài hạn

#### 3.1 LLM-assisted Mapping Generation
- Dùng LLM để classify mapping: "Does prowler check X relate to maturity capability Y?"
- Output: mapping_confidence (high/medium/low) với reasoning
- Human review queue cho medium/low confidence mappings

#### 3.2 Evaluation-Driven Development
- Setup **continuous benchmark**: mỗi code change → auto run benchmark → compare metrics
- Define **release criteria**: top-1 accuracy >= 70%, forbidden_capability_rate = 0%, latency <= 2s
- Block merge nếu benchmark regress

---

## 8. Changelog so với phiên bản trước

Tài liệu này được cập nhật từ phiên bản 2026-03-26 sau **10 optimization slices**. Các thay đổi chính:

### Kiến trúc
- **ContextBuilder refactored**: 55KB monolith → 6 module chuyên biệt (1,408 dòng tổng)
- **Constants centralized**: `CONTROL_INTENT_CLUSTERS`, `PRODUCT_ENTITY_GATES`, `KNOWN_SERVICES` vào `constants.py`
- **Shared utility**: `mapping_sort_key()` vào `utils.py`, loại bỏ duplicate
- **Agent integration**: Centralized `config.py` + `RAGClient` thay scattered hardcoded URLs
- **CrossEncoder Reranker**: Thêm module `reranker.py` thay thế handcrafted scoring heuristics

### Data Quality
- **Retrieval text restructured**: Field-level prefixes, loại code snippets, truncate summary 300 từ
  - Avg doc size: Prowler 126→118 từ, Maturity 437→248 từ (-43%)
- **Mapping quality gate**: `min_score=0.25`, `min_score_gap=0.05` → loại ~70 low-quality mappings
- **Curated mappings**: 21 S3 check-to-capability mappings (`approved` status)
- **Product entity gates**: 11 gates ngăn false-positive cross-product mappings

### Search Quality
- **BM25 enhanced**: Snowball stemming + stopword removal + tuned k1=1.2, b=0.6
- **Vector index explicit binding**: `SentenceTransformerEmbeddingFunction(all-MiniLM-L6-v2)`
- **Cross-encoder reranking**: `cross-encoder/ms-marco-MiniLM-L-6-v2` sau RRF merge
- **Scoring externalized**: `scoring_config.json` cho tất cả thresholds

### Benchmark Metrics

| Metric | Phiên bản cũ (2026-03-26) | Hiện tại (sau 10 slices) | Target |
|--------|---------------------------|--------------------------|--------|
| Top-1 accuracy (overall) | 40% | **65.85%** | ≥ 70% |
| Top-1 accuracy (exact) | 100% | **100%** | 100% |
| Top-1 accuracy (paraphrase) | 20% | **66.7%** | ≥ 60% ✅ |
| Top-1 accuracy (risk) | N/A | **16.7%** | ≥ 40% |
| Top-1 accuracy (semantic_hard) | 0% | **25%** | ≥ 40% |
| Top-5 accuracy (overall) | 65% | **85.37%** | ≥ 80% ✅ |
| Maturity Top-1 | 0% | **73.68%** | ≥ 60% ✅ |
| Maturity Top-5 | 0% | **100%** | ≥ 80% ✅ |
| Service precision | Unknown | **87.8%** | ≥ 85% ✅ |
| Forbidden capability rate | Unknown | **0%** | 0% ✅ |
| Empty bundle rate | Unknown | **0%** | 0% ✅ |
| Average latency | 2.2s | **2.14s** | ≤ 2.0s |

**S3 Agent Readiness**: ✅ READY cho cả 3 consumers (Planning, Risk, Report).

---

## Phụ lục: File Reference

### Core Files
| File | Vai trò | Dòng code | Độ phức tạp |
|------|---------|-----------|-------------|
| `app/main.py` | FastAPI app, lifespan, service wiring | ~80 | Thấp |
| `app/core/config.py` | Configuration, paths, scoring config, caching | 200 | Trung bình |
| `app/core/models.py` | Pydantic models (request/response contracts) | ~350 | Trung bình |
| `app/core/constants.py` | Centralized intent clusters, entity gates, services | 229 | Trung bình |
| `app/core/errors.py` | Error helpers, error codes | ~50 | Thấp |
| `app/core/utils.py` | Shared mapping_sort_key | 43 | Thấp |
| `app/ingestion/loaders.py` | JSON loaders (raw data) | ~60 | Thấp |
| `app/ingestion/normalizers.py` | Normalization + aliases + tokenization + stemming | 756 | **Cao** |
| `app/indexing/lexical_index.py` | BM25 implementation (stemming, stopwords, exact lookup) | ~250 | Trung bình |
| `app/indexing/vector_index.py` | Chroma wrapper (explicit embedding binding) | 231 | Trung bình |
| `app/retrieval/pipeline.py` | Orchestrates retrieval (RRF, parallel search, rerank) | 869 | **Cao** |
| `app/retrieval/router.py` | Query classification (heuristic routing) | ~200 | Trung bình |
| `app/retrieval/reranker.py` | Cross-encoder reranking (singleton, lazy load) | 96 | Trung bình |
| `app/retrieval/confidence.py` | Route-aware confidence scoring | ~100 | Trung bình |
| `app/retrieval/verifier.py` | Result verification (severe/moderate warnings) | ~150 | Trung bình |
| `app/services/check_service.py` | Check retrieval service | ~100 | Trung bình |
| `app/services/maturity_service.py` | Maturity retrieval + exact match reranking | ~120 | Trung bình |
| `app/services/mapping_service.py` | Mapping resolution + agent context filtering | ~200 | Trung bình |
| `app/services/context_service.py` | Context orchestration (check→mapping→maturity→build) | 707 | **Cao** |
| `app/context/context_builder.py` | Facade, delegates to modules | 157 | Thấp |
| `app/context/coverage_selector.py` | Coverage-aware selection, planning diversification | 383 | **Cao** |
| `app/context/bundle_factory.py` | Consumer-specific bundles + confidence eval | 346 | Trung bình |
| `app/context/intent_detector.py` | Intent detection, entity gating | 133 | Trung bình |
| `app/context/prompt_formatter.py` | Prompt formatting, evidence summary | 210 | Trung bình |
| `app/context/_helpers.py` | Shared utilities | 179 | Thấp |
| `scripts/build_all.py` | Full build pipeline | ~200 | Trung bình |
| `scripts/gen_maturity_mapping.py` | Auto mapping generation | ~300 | **Cao** |

### Scoring Configuration (scoring_config.json defaults)
| Parameter | Value | Mô tả |
|-----------|-------|-------|
| `rrf.k` | 60 | RRF ranking constant |
| `exact_match_bonus` | 2.0 | Bonus cho exact ID match |
| `metadata_bonus.service_match` | 0.03 | Bonus khi service khớp |
| `metadata_bonus.domain_match` | 0.02 | Bonus khi domain khớp |
| `reranker.enabled` | true | Cross-encoder reranking on/off |
| `reranker.model` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model |
| `reranker.top_n` | 20 | Max candidates cho reranking |
| `search_top_k_multiplier` | 3 | Multiply top_k cho BM25/vector search |
| `search_top_k_minimum` | 10 | Minimum search candidates |
| `confidence_thresholds.check_search.high` | 0.70 | Threshold cho high confidence |
| `confidence_thresholds.check_search.medium` | 0.35 | Threshold cho medium confidence |
| `ambiguity.gap_high_to_medium` | 0.10 | Score gap penalty threshold |
| `verification.low_score_threshold` | 0.15 | Threshold cho low_score warning |

### Release Criteria (7/8 PASS)
| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| Checks Top-1 Accuracy | ≥ 60% | 65.85% | ✅ PASS |
| Checks Top-5 Accuracy | ≥ 80% | 85.37% | ✅ PASS |
| Maturity Top-1 Accuracy | ≥ 60% | 73.68% | ✅ PASS |
| Maturity Top-5 Accuracy | ≥ 80% | 100% | ✅ PASS |
| Forbidden Capability Rate | = 0% | 0% | ✅ PASS |
| Empty Bundle Rate | = 0% | 0% | ✅ PASS |
| Service Precision | ≥ 85% | 87.8% | ✅ PASS |
| Average Latency | ≤ 2000ms | 2144ms | ❌ FAIL |

---

*Tài liệu này được cập nhật dựa trên phân tích source code tại thời điểm 2026-04-02.*
*Cập nhật từ phiên bản 2026-03-26 sau 10 optimization slices.*
*Phiên bản index: rag-v2-2026-03-17 | Embedding: all-MiniLM-L6-v2 | Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2*
