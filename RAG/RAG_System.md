# RAG System - Phân tích Kiến trúc & Source Code

## Mục lục

1. [Tổng quan Kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Data Flow - Luồng dữ liệu](#2-data-flow---luồng-dữ-liệu)
3. [Phân tích Data Layer](#3-phân-tích-data-layer)
4. [Điểm mạnh](#4-điểm-mạnh)
5. [Điểm yếu & Nguồn gốc vấn đề](#5-điểm-yếu--nguồn-gốc-vấn-đề)
6. [Phần có thể tối ưu hoặc loại bỏ](#6-phần-có-thể-tối-ưu-hoặc-loại-bỏ)
7. [Đề xuất các bước tiếp theo](#7-đề-xuất-các-bước-tiếp-theo)

---

## 1. Tổng quan Kiến trúc

### 1.1 Thành phần hệ thống

Hệ thống RAG được xây dựng trên FastAPI, phục vụ 3 loại consumer (planning, risk, report) với kiến trúc phân tầng:

```
┌─────────────────────────────────────────────────────────────────┐
│                       API Layer (FastAPI)                        │
│  /v1/retrieve/checks  │  /v1/retrieve/maturity  │ /v1/context/build │
└──────────┬──────────────────────┬──────────────────────┬────────┘
           │                      │                      │
┌──────────▼──────────┐  ┌───────▼─────────┐  ┌────────▼─────────┐
│   CheckService      │  │ MaturityService │  │  ContextService  │
│                     │  │                 │  │   + ContextBuilder│
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
                    │  │ Merge   │ │Confidence│ │
                    │  └────┬────┘ └──────────┘ │
                    └───────┼────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
        ┌─────▼────┐  ┌────▼────┐  ┌─────▼──────┐
        │BM25 Index│  │ Chroma  │  │   Mapping  │
        │(Lexical) │  │(Vector) │  │   Index    │
        └──────────┘  └─────────┘  └────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     Data Layer                                   │
│  raw/ → normalizers.py → normalized/ → build_all.py → indexes/  │
│  577 prowler checks │ 78 capabilities │ 573 mappings             │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Corpus Registry (3 corpus)

| Corpus | Mô tả | Số lượng doc | Doc Type |
|--------|--------|-------------|----------|
| `prowler_checks` | Metadata các security check của Prowler (AWS) | 577 | `prowler_check` |
| `maturity_capabilities` | AWS Security Maturity Model capabilities | 78 | `maturity_capability` |
| `maturity_mappings` | Mapping check → capability | 573 | `maturity_mapping` |

### 1.3 Tích hợp với Orchestrator

Orchestrator (`graph_orchestator.py`) gọi RAG qua HTTP:
- **PlanningAgent** gọi `POST /v1/retrieve/checks` → nhận candidate checks → LLM re-rank
- **ContextService** cung cấp `POST /v1/context/build` → bundle context cho planning/risk/report
- Giao tiếp **loosely coupled** qua REST API trên port 8111

---

## 2. Data Flow - Luồng dữ liệu

### 2.1 Build Pipeline (Offline)

```
Raw JSON (prowler_checks.json, maturity_capabilities.json)
    │
    ▼
[gen_maturity_mapping.py] ──────► maturity_mappings.json (raw)
    │                              (auto-generated: BM25 scoring + heuristic)
    ▼
[build_all.py]
    ├── normalize_prowler_doc()  ──► normalized/prowler_checks.json
    ├── normalize_maturity_doc() ──► normalized/maturity_capabilities.json
    ├── normalize_mapping_doc()  ──► normalized/maturity_mappings.json
    │
    ├── Build BM25 per corpus ────► indexes/bm25/*.pkl
    ├── Build Chroma per corpus ──► indexes/chroma/
    └── Write manifest ───────────► indexes/manifest.json
```

**Quan trọng:** `gen_maturity_mapping.py` là script **tự động sinh mapping** giữa prowler check và maturity capability bằng BM25 scoring + heuristic rules. Đây là **nguồn gốc chính** của false-positive mappings.

### 2.2 Query Pipeline (Online)

```
Client request (query, service, consumer)
    │
    ▼
[SemanticRouter.route()] ─── Phân loại query type:
    │                         check_search / maturity_search /
    │                         mapping_resolution / context_build
    ▼
[RetrievalPipeline.retrieve()]
    ├── Exact lookup path (check_id / capability_id)
    │   └── BM25 exact match → score=1.0
    │
    └── Semantic search path
        ├── BM25 lexical search (top_k * 3)
        ├── Chroma vector search (top_k * 3)
        └── RRF merge + intent bonus + product penalty + metadata bonus
            │
            ▼
        [verify_retrieval()] → warnings
        [calculate_confidence()] → high/medium/low
            │
            ▼
        Response with results + meta + diagnostics
```

### 2.3 Context Build Pipeline (Online)

```
ContextBuildRequest (consumer, check_ids, findings, query)
    │
    ▼
[ContextService.build()]
    │
    ├── Step 1: Retrieve checks ──► CheckService.search()
    │   (per check_id + query-driven)
    │
    ├── Step 2: Resolve mappings ──► MappingService.resolve()
    │   (per selected check_id)
    │
    ├── Step 3: Retrieve maturity ─► MaturityService.search()
    │   (per capability_id from mappings)
    │
    └── Step 4: Build bundle ─────► ContextBuilder.build()
        ├── _select_checks() → requested + related checks
        ├── _select_mappings() → filtered mappings
        ├── _select_capabilities() → maturity context
        └── Build consumer-specific bundle:
            ├── PlanningBundle (findings + control_mapping_ids + capability_ids)
            ├── RiskBundle (primary_finding + related + mappings + maturity)
            └── ReportBundle (topics + findings + themes + practices)
```

---

## 3. Phân tích Data Layer

### 3.1 Raw Data Quality

**prowler_checks.json (577 docs)**
- Nguồn: Prowler metadata export
- Chất lượng tốt: có cấu trúc rõ ràng (CheckID, ServiceName, Severity, Description, Risk, Remediation)
- Remediation chứa code examples (CLI, Terraform, CloudFormation) → text rất dài
- Vấn đề: một số check có Description/Risk trùng lặp nội dung

**maturity_capabilities.json (78 docs)**
- Nguồn: AWS Security Maturity Model (crawled)
- Chất lượng trung bình:
  - Nhiều capability có `summary` rất dài (>500 từ), trộn lẫn hướng dẫn chi tiết + context business
  - `how_to_check` thường empty
  - `recommendation` trùng với `summary` trong phần lớn các doc
  - Không có `capability_id` rõ ràng từ nguồn → phải sinh từ `title` qua slugify
  - Tên capability quá dài, ví dụ: `"Cleanup unused and unintended external access using IAM Access Analyzer or CIEM solutions"` → gây nhiễu cho BM25 tokenization

**maturity_mappings.json (573 docs)** - **CRITICAL**
- Nguồn: **Auto-generated** bởi `gen_maturity_mapping.py`
- Phương pháp: BM25 bag-of-words scoring + synonym canonicalization + heuristic bonuses
- Chất lượng **THẤP** - đây là root cause chính:
  - `mapping_confidence` phần lớn là `"medium"` hoặc `"low"`
  - `review_status` = `"draft"` cho toàn bộ 573 mappings
  - Không có human review
  - False-positive nghiêm trọng: S3 encryption checks → Bedrock GenAI capabilities
  - `score` trung bình thấp (~0.38), `score_gap_vs_second` nhỏ (~0.047) → nhiều mapping mơ hồ

### 3.2 Normalization Quality

File `normalizers.py` thực hiện:
- Unicode NFKC normalization
- Whitespace cleaning
- Identifier normalization (snake_case)
- `retrieval_text` generation bằng cách concatenate tất cả fields quan trọng

**Vấn đề với retrieval_text:**
- Concatenate **tất cả fields** (id, name, domain, summary, guidance, how_to_check, recommendations, keywords, tags) thành một blob text
- Không có trọng số (weight) giữa title vs description vs remediation
- Remediation text (chứa code snippets) có thể chiếm >70% retrieval_text → dilute semantic signal
- Aliases (handcrafted) chỉ cover ~7 S3 checks → phần còn lại không có semantic enrichment

### 3.3 Index Quality

**BM25 Index:**
- Tokenization đơn giản: split on non-alphanumeric, lowercase
- Không có stemming, lemmatization
- Không loại stopwords khi build index (chỉ loại trong gen_maturity_mapping)
- k1=1.5, b=0.75 (standard defaults, chưa tuning)

**Chroma Vector Index:**
- Embedding model config: `intfloat/multilingual-e5-base` (nhưng không explicit binding)
- **Quyết định PO (2026-03-26):** Chuyển sang `all-MiniLM-L6-v2` với explicit binding
- Dùng **Chroma default embedding** (không explicit binding) → có thể dùng all-MiniLM-L6-v2 thay vì e5-base
- Distance conversion: `1/(1+distance)` → range [0, 0.5] cho hầu hết trường hợp
- 40+ collections trong chroma/ → có thể là orphaned collections từ builds trước

---

## 4. Điểm mạnh

### 4.1 Kiến trúc phân tầng rõ ràng

- **Separation of Concerns**: API routes → Services → Pipeline → Indexes. Mỗi layer có trách nhiệm rõ ràng.
- **Dependency Injection**: Services nhận pipeline qua constructor, dễ test và mock.
- **Corpus-aware design**: Mỗi corpus có BM25 index và Chroma collection riêng → tránh cross-corpus pollution.

### 4.2 Hybrid Retrieval với RRF

- Kết hợp BM25 (lexical) + Vector (semantic) qua **Reciprocal Rank Fusion** → tận dụng ưu điểm của cả hai.
- Exact lookup path riêng cho check_id/capability_id → không bị ảnh hưởng bởi ranking noise.
- Graceful degradation: vector failure không kill toàn bộ pipeline, fallback về lexical-only.

### 4.3 Quality Signals tốt

- **Verification system** (`verifier.py`): tự phát hiện exact_lookup_miss, service_mismatch, ambiguous_top_results.
- **Confidence estimation** (`confidence.py`): tính confidence dựa trên route type, score, ambiguity gap, verification warnings.
- **Review flags**: `review_recommended` được propagate từ pipeline lên response → consumer biết khi nào cần cẩn thận.

### 4.4 Context Builder đa consumer

- Bundle schema riêng cho mỗi consumer (PlanningBundle, RiskBundle, ReportBundle) → tối ưu payload cho từng use case.
- Coverage-aware selection cho planning: greedy intent diversification → tránh trả toàn bộ checks cùng 1 intent.
- Entity gating: ngăn capabilities Bedrock/SageMaker/WAF xuất hiện khi query không liên quan.

### 4.5 Build Pipeline tự contained

- `build_all.py` thực hiện full pipeline: normalize → validate → build BM25 → build vector → write manifest.
- Manifest tracking: version, build time, doc counts → dễ audit và rollback.
- Duplicate doc_id validation trước khi build.

### 4.6 Test & Benchmark infrastructure

- 15 test files covering API, service, contract, retrieval, vector, mapping.
- Benchmark framework với ground truth (expected doc_id), đo by category (exact, paraphrase, risk, semantic_hard).
- S3-specific benchmark với readiness criteria cho agent.

---

## 5. Điểm yếu & Nguồn gốc vấn đề

### 5.1 [CRITICAL] Auto-generated Mappings chất lượng thấp

**File:** `scripts/gen_maturity_mapping.py`

Đây là **root cause #1** của kết quả không như mong đợi:

- Mapping được sinh bằng BM25 bag-of-words scoring giữa prowler check text và maturity capability text.
- Kỹ thuật này không hiểu **semantic intent**. Ví dụ: "encryption" trong S3 check và "encryption" trong Bedrock capability đều match → false positive.
- `score` trung bình ~0.38 → rất thấp, cho thấy matching hời hợt.
- `score_gap_vs_second` ~0.047 → hầu như không phân biệt được best match vs second.
- Toàn bộ 573 mappings có `review_status: "draft"` → chưa ai xác nhận.
- Hậu quả: **agent nhận context sai từ governance layer**, dẫn đến reasoning/report sai ở mức semantics mặc dù technical facts đúng.

### 5.2 [HIGH] Retrieval Text thiếu structure

**File:** `app/ingestion/normalizers.py`, function `build_retrieval_text()`

- `retrieval_text` là plain concatenation của tất cả fields, không có trọng số.
- Prowler check: remediation text (chứa Terraform/CloudFormation code) chiếm phần lớn → BM25 match code tokens thay vì semantic meaning.
- Maturity capability: `summary` trùng `recommendation` → duplicate signal, inflate BM25 score cho common terms.
- Không có section markers (e.g., `[TITLE]`, `[RISK]`, `[REMEDIATION]`) → vector embedding không phân biệt importance.

### 5.3 [HIGH] Vector Index có thể không dùng đúng embedding model

**File:** `app/indexing/vector_index.py`

- Config khai báo `EMBEDDING_MODEL = "intfloat/multilingual-e5-base"` nhưng `VectorIndex` không truyền model vào Chroma.
- Chroma `create_collection()` được gọi **không có embedding function** → Chroma sẽ dùng **default embedding** (thường là `all-MiniLM-L6-v2`), **KHÔNG phải** `intfloat/multilingual-e5-base`.
- Hậu quả: Vector search quality có thể thấp hơn mong đợi vì model thực tế khác config.

### 5.4 [HIGH] Scoring heuristics quá nhiều hardcoded values

**File:** `app/retrieval/pipeline.py`, method `_merge_results()`

Hệ thống scoring có quá nhiều magic numbers:
- `intent_bonus = +0.18 / -0.18`
- `check_id_intent_boost = +0.30 / +0.22 / +0.12`
- `product_penalty = -0.20`
- `metadata_bonus = +0.03 (service) / +0.02 (domain)`

Các giá trị này **không có cơ sở empirical** (không thấy tuning log), khó debug khi kết quả sai, và khó maintain khi thêm services mới.

### 5.5 [HIGH] Handcrafted aliases không scale

**File:** `app/ingestion/normalizers.py`, functions `_check_aliases()`, `_capability_aliases()`

- Aliases được hardcode cho ~7 S3 checks và ~6 capabilities.
- Không cover 570+ checks còn lại → phần lớn checks không có semantic enrichment.
- Mỗi khi thêm service mới phải sửa code → vi phạm Open/Closed Principle.
- Aliases cho S3 rất chi tiết (30+ phrases mỗi check) nhưng IAM, EC2, RDS... = 0 aliases.

### 5.6 [MEDIUM] BM25 Index thiếu text processing nâng cao

**File:** `app/indexing/lexical_index.py`

- Không có stemming/lemmatization → "encrypted" và "encryption" là 2 token khác nhau.
- Không có stopword removal trong BM25 build → common words (the, is, are) ảnh hưởng scoring.
- Tokenization quá đơn giản: `re.split(r"[^a-z0-9_]+", text)` → mất ngữ cảnh compound words.

### 5.7 [MEDIUM] Context Builder quá phức tạp (55KB)

**File:** `app/context/context_builder.py`

- File 55KB với logic phức tạp: intent detection, coverage selection, entity gating, bundle building, evidence summary, prompt generation.
- Đảm nhận quá nhiều responsibility → khó test, khó debug, khó maintain.
- `_planning_coverage_select()` implement greedy algorithm nhưng thiếu unit test coverage.
- `_INTENT_CLUSTERS`, `_PRODUCT_ENTITY_GATES` được duplicate giữa context_builder.py, pipeline.py, và gen_maturity_mapping.py → inconsistency risk.

### 5.8 [MEDIUM] Trùng lặp logic giữa Pipeline và MappingService

**Files:** `app/retrieval/pipeline.py` và `app/services/mapping_service.py`

- `_mapping_sort_key()` được implement gần giống nhau ở cả 2 file.
- `_get_mapping_index()` load cùng normalized JSON ở cả 2 nơi → double memory.
- `_filter_mapping_candidates()` logic tương tự giữa pipeline và service.

### 5.9 [MEDIUM] Duplicate ContextBuildRequest definition

**File:** `app/core/models.py`

- `ContextBuildRequest` được define **2 lần** (line 144 và line 307).
- Class thứ 2 override class thứ nhất → class thứ nhất (đơn giản hơn) bị bỏ quên nhưng vẫn trong code.

### 5.10 [LOW] Orphaned Chroma collections

- 40+ UUID directories trong `data/indexes/chroma/` → phần lớn từ builds cũ.
- `_cleanup_legacy_vector_collection()` chỉ xóa 1 collection tên cũ, không dọn orphaned data.
- Tốn disk space và có thể gây confuse khi debug.

### 5.11 [LOW] Benchmark cho thấy retrieval accuracy thấp

Từ `benchmark_checks_report.json`:
- **Top-1 accuracy**: 8/20 = **40%**
- **Top-3 accuracy**: 12/20 = 60%
- **Top-5 accuracy**: 13/20 = 65%
- **Semantic hard category**: Top-1 = **0/5**, Top-5 = 1/5
- **Paraphrase category**: Top-1 = 1/5
- **Average latency**: 2.2s → chấp nhận được nhưng có thể tối ưu

Kết luận: **Hệ thống chỉ hoạt động tốt với exact queries, yếu rõ rệt với paraphrase và semantic queries.**

---

## 6. Phần có thể tối ưu hoặc loại bỏ

### 6.1 Loại bỏ / Thay thế

| Component | Hành động | Lý do |
|-----------|-----------|-------|
| Auto-generated mappings (`gen_maturity_mapping.py`) | **Thay thế** bằng LLM-assisted mapping + human review | BM25 bag-of-words không đủ semantic understanding, root cause của false positives |
| Handcrafted aliases trong `normalizers.py` | **Loại bỏ** dần khi cải thiện embedding/retrieval text | Không scale, chỉ cover <2% checks, tạo maintenance burden |
| Duplicate `ContextBuildRequest` (line 144) | **Xóa** class đầu tiên | Dead code, gây confuse |
| Duplicate `_mapping_sort_key()` | **Refactor** thành shared utility | DRY violation |
| `build.py` route (đã commented out) | **Xóa** hoặc implement đúng | Dead code |
| Orphaned Chroma collections | **Thêm cleanup** trong build_all.py | Disk waste |

### 6.2 Tối ưu

| Component | Hành động | Impact dự kiến |
|-----------|-----------|---------------|
| `retrieval_text` generation | **Restructure** với section weights | Cải thiện BM25 + vector accuracy |
| Vector embedding model binding | **Fix** explicit embedding function trong VectorIndex | Đảm bảo dùng đúng model đã config |
| BM25 tokenization | **Thêm** stemming + stopword removal | Cải thiện lexical recall |
| Scoring heuristics | **Thay** hardcoded bonuses bằng tunable config | Dễ tune, dễ reproduce |
| ContextBuilder | **Tách** thành Builder + IntentDetector + CoverageSelector | SRP, dễ test |
| Config overlap (INTENT_CLUSTERS, PRODUCT_GATES) | **Centralize** vào config module | Single source of truth |

---

## 7. Đề xuất các bước tiếp theo

### Phase 1: Fix Critical Issues (Ưu tiên cao nhất)

#### 1.1 Fix Vector Embedding Model Binding
- **Vấn đề**: Chroma không dùng embedding model đã config
- **Hành động**: Trong `VectorIndex.build_collection()` và `VectorIndex.query()`, pass explicit `embedding_function` dùng `intfloat/multilingual-e5-base` (hoặc model phù hợp hơn)
- **Tại sao**: Đây là fix đơn giản nhất mà có thể tạo improvement lớn nhất cho vector search quality

#### 1.2 Cải thiện Mapping Quality
- **Vấn đề**: 573 auto-generated mappings với quality thấp
- **Hành động**:
  1. Tạo **curated mapping** cho top-20 critical checks (S3, IAM, EC2) bằng tay
  2. Thêm `review_status: "approved"` cho curated mappings
  3. Filter mapping results: chỉ dùng `approved`/`reviewed` mappings cho agent context, `draft` mappings chỉ dùng cho debug
  4. Dài hạn: dùng LLM (Llama/GPT) để re-score mappings với semantic understanding
- **Tại sao**: Mapping sai → agent context sai → reasoning sai. Không fix được bằng tuning retrieval.

#### 1.3 Restructure Retrieval Text
- **Vấn đề**: retrieval_text là flat concatenation, code snippets dilute signal
- **Hành động**:
  1. **Loại bỏ code examples** khỏi retrieval_text (chỉ giữ description, risk, title)
  2. **Thêm field-level prefixes**: `"title: {title}\nrisk: {risk}\ndescription: {desc}"`
  3. Cho maturity: loại recommendation khi trùng summary
  4. Rebuild indexes sau khi thay đổi
- **Tại sao**: Retrieval text chất lượng hơn → cả BM25 và vector đều cải thiện

### Phase 2: Improve Retrieval Quality

#### 2.1 BM25 Enhancement
- Thêm **stemming** (PorterStemmer hoặc Snowball)
- Thêm **stopword removal** khi tokenize
- Tune k1/b parameters dựa trên benchmark results

#### 2.2 Scoring Config Externalization
- Di chuyển tất cả magic numbers (intent_bonus, product_penalty, etc.) ra file config (YAML/JSON)
- Tạo benchmark loop: thay đổi config → run benchmark → so sánh accuracy
- Document rationale cho mỗi parameter value

#### 2.3 Mở rộng Benchmark Coverage
- Thêm test cases cho IAM, EC2, RDS, Lambda (hiện chỉ focus S3)
- Thêm ground truth labels cho mỗi case: expected_check_id, expected_capability_id, **forbidden_capability_ids**
- Thêm metric: `forbidden_capability_rate = 0%` (hard requirement)

### Phase 3: Architecture Cleanup

#### 3.1 Refactor ContextBuilder
- Tách `ContextBuilder` (55KB) thành:
  - `IntentDetector`: phát hiện query intents
  - `CoverageSelector`: coverage-aware selection
  - `BundleFactory`: build consumer-specific bundles
  - `PromptFormatter`: format context cho LLM
- Mỗi component có unit test riêng

#### 3.2 Eliminate Duplication
- Merge `_mapping_sort_key()` thành shared utility
- Centralize `INTENT_CLUSTERS`, `PRODUCT_ENTITY_GATES` vào `app/core/constants.py`
- Xóa duplicate `ContextBuildRequest`

#### 3.3 Data Pipeline Improvements
- Thêm **data validation step** trong build_all.py: check for empty fields, duplicate content
- Thêm **mapping quality gate**: reject mappings với score < threshold
- Thêm **orphaned collection cleanup** trong build pipeline

### Phase 4: Advanced (Dài hạn)

#### 4.1 LLM-assisted Mapping Generation
- Dùng LLM để classify mapping: "Does prowler check X relate to maturity capability Y? Why?"
- Output: mapping_confidence (high/medium/low) với reasoning
- Human review queue cho medium/low confidence mappings

#### 4.2 Query Understanding Layer
- Thêm **query rewriting** trước khi search: LLM rewrite NL query thành technical query
- Thêm **query expansion**: detect service, intent, severity từ NL query
- Giảm phụ thuộc vào handcrafted aliases

#### 4.3 Re-ranking with Cross-encoder
- Sau hybrid retrieval, thêm **cross-encoder re-ranking** (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`)
- Cross-encoder hiểu context tốt hơn bi-encoder → cải thiện top-1 accuracy cho semantic queries

#### 4.4 Evaluation-Driven Development
- Setup **continuous benchmark**: mỗi code change → auto run benchmark → compare metrics
- Define **release criteria**: top-1 accuracy >= 70%, forbidden_capability_rate = 0%, empty_bundle_rate = 0%
- Block merge nếu benchmark regress

---

## Phụ lục: File Reference

### Core Files
| File | Vai trò | Độ phức tạp |
|------|---------|-------------|
| `app/main.py` | FastAPI app, lifespan, service wiring | Thấp |
| `app/core/config.py` | Configuration, paths, constants | Thấp |
| `app/core/models.py` | Pydantic models (27+ classes) | Trung bình |
| `app/core/errors.py` | Error helpers, error codes | Thấp |
| `app/ingestion/loaders.py` | JSON loaders | Thấp |
| `app/ingestion/normalizers.py` | Normalization + aliases | **Cao** |
| `app/indexing/lexical_index.py` | BM25 implementation | Trung bình |
| `app/indexing/vector_index.py` | Chroma wrapper | Thấp |
| `app/retrieval/pipeline.py` | Orchestrates retrieval | **Cao** |
| `app/retrieval/router.py` | Query classification | Trung bình |
| `app/retrieval/confidence.py` | Confidence scoring | Thấp |
| `app/retrieval/verifier.py` | Result verification | Trung bình |
| `app/services/check_service.py` | Check retrieval service | Trung bình |
| `app/services/maturity_service.py` | Maturity retrieval service | Trung bình |
| `app/services/mapping_service.py` | Mapping resolution service | Trung bình |
| `app/services/context_service.py` | Context orchestration | **Cao** |
| `app/context/context_builder.py` | Bundle building + prompt | **Rất cao** |
| `scripts/build_all.py` | Full build pipeline | Trung bình |
| `scripts/gen_maturity_mapping.py` | Auto mapping generation | **Cao** |

### Benchmark Metrics (Hiện tại)
| Metric | Giá trị | Target |
|--------|---------|--------|
| Top-1 accuracy (overall) | 40% | >= 70% |
| Top-1 accuracy (exact) | 100% | 100% |
| Top-1 accuracy (paraphrase) | 20% | >= 60% |
| Top-1 accuracy (semantic_hard) | 0% | >= 40% |
| Top-5 accuracy (overall) | 65% | >= 85% |
| False mapping rate | Unknown | 0% |
| Average latency | 2.2s | < 1.5s |

---

*Tài liệu này được tạo dựa trên phân tích source code tại thời điểm 2026-03-26.*
*Phiên bản index: rag-v2-2026-03-17 | Total docs: 1,228*
