# BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG RAG SYSTEM

> **Ngày:** 2026-04-02 (cập nhật từ bản gốc 2026-03-26)
> **Phiên bản Index:** `rag-v2-2026-03-17`
> **Embedding Model:** `all-MiniLM-L6-v2`
> **Benchmark Tag:** `slice-10-clean`

---

## MỤC LỤC

1. [Tổng Quan Hệ Thống](#1-tổng-quan-hệ-thống)
2. [Kiến Trúc & Data Flow](#2-kiến-trúc--data-flow)
3. [Phân Tích Điểm Mạnh](#3-phân-tích-điểm-mạnh)
4. [Phân Tích Điểm Yếu](#4-phân-tích-điểm-yếu)
5. [Đánh Giá Chất Lượng Truy Vấn & Benchmark](#5-đánh-giá-chất-lượng-truy-vấn--benchmark)
6. [Đề Xuất Bước Tiếp Theo](#6-đề-xuất-bước-tiếp-theo)
7. [Kết Luận](#7-kết-luận)

---

## 1. TỔNG QUAN HỆ THỐNG

### 1.1 Mục Đích

RAG System được thiết kế để cung cấp ngữ cảnh (context) cho các AI Agent trong hệ thống đánh giá bảo mật AWS. Hệ thống truy vấn và tổng hợp thông tin từ 3 nguồn dữ liệu (corpus):

| Corpus | Số lượng | Mô tả |
|--------|----------|-------|
| **Prowler Checks** | 577 | Các kiểm tra bảo mật AWS từ Prowler |
| **Maturity Capabilities** | 78 | Năng lực bảo mật theo AWS Security Maturity Model |
| **Maturity Mappings** | 502 | Ánh xạ giữa Check → Capability |

**Tổng: 1,157 documents** được index dưới dạng hybrid (BM25 lexical + ChromaDB vector).

### 1.2 Tech Stack

- **Framework:** FastAPI
- **Vector DB:** ChromaDB (persistent, explicit SentenceTransformerEmbeddingFunction)
- **Lexical Index:** BM25 (custom implementation, Snowball stemming, pickle serialized)
- **Embedding:** `all-MiniLM-L6-v2` (SentenceTransformers, 384 dims)
- **Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (sigmoid scores [0,1])
- **Merge Strategy:** Reciprocal Rank Fusion (RRF, k=60) + CrossEncoder rerank
- **Language:** Python 3.x, Pydantic v2

### 1.3 API Endpoints

| Endpoint | Chức năng |
|----------|-----------|
| `POST /v1/retrieve/checks` | Truy vấn Prowler checks |
| `POST /v1/retrieve/maturity` | Truy vấn Maturity capabilities |
| `POST /v1/resolve/mapping` | Resolve mapping Check → Capability |
| `POST /v1/context/build` | Build context bundle cho Agent |
| `GET /health` | Health check cơ bản |
| `GET /ready` | Readiness probe (lexical, vector, mapping, hybrid) |
| `GET /build-info` | Build information và readiness details |

---

## 2. KIẾN TRÚC & DATA FLOW

### 2.1 Tổng Quan Kiến Trúc

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Layer (FastAPI)                       │
│  routes/retrieve.py  │  routes/resolve.py  │  routes/health.py  │
└──────────┬───────────┴──────────┬──────────┴────────────────────┘
           │                      │
           ▼                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                       Services Layer                             │
│  CheckService  │  MaturityService  │  MappingService             │
│                     ContextService (orchestrator)                 │
└──────────┬──────────┬──────────┬──────────┬─────────────────────┘
           │          │          │          │
           ▼          ▼          ▼          ▼
┌───────────────────┐ ┌─────────────────────────────────────────┐
│ RetrievalPipeline │ │          Context Module                  │
│  ├─ Router        │ │  ├─ IntentDetector                      │
│  ├─ BM25 Index    │ │  ├─ CoverageSelector                   │
│  ├─ Vector Index  │ │  ├─ BundleFactory                      │
│  ├─ RRF Merger    │ │  └─ PromptFormatter                    │
│  ├─ Reranker (CE) │ └─────────────────────────────────────────┘
│  ├─ Verifier      │
│  └─ Confidence    │
└──────────┬────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│                        Data Layer                                │
│  indexes/bm25/*.pkl  │  indexes/chroma/{uuid}/  │  manifest.json │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Offline Pipeline (Build)

```
Raw JSON (3 sources)
    │
    ├── gen_maturity_mapping.py ──► Auto-generate 502 mappings (BM25 + heuristics)
    │
    ▼
build_all.py
    │
    ├── normalize_prowler_doc()   ──► normalized/prowler_checks.json
    ├── normalize_maturity_doc()  ──► normalized/maturity_capabilities.json
    ├── normalize_mapping_doc()   ──► normalized/maturity_mappings.json
    │
    ├── BM25Index.build() × 3    ──► indexes/bm25/*.pkl
    ├── VectorIndex.build() × 3  ──► indexes/chroma/{uuid}/
    │
    └── Write manifest.json       ──► Version tracking & metadata
```

**Đặc điểm chính của Normalization:**
- Unicode NFKC normalization
- Snake_case cho identifiers
- Keyword/tag extraction với stopword filtering
- Stemming via SnowballStemmer
- Prefixed retrieval text (check:, service:, title:, description:, ...)
- Code snippet removal (chỉ giữ Recommendation.Text)
- Overlap detection: skip recommendations trùng summary >80%

### 2.3 Online Pipeline (Query)

```
HTTP Request (query, service, consumer, retrieval_mode)
    │
    ▼
SemanticRouter.route()
    ├── Detect exact_check_id / exact_capability_id
    ├── Infer query_type: check_search | maturity_search | mapping_resolution | context_build
    └── Build filters (service, domain, doc_type)
    │
    ▼
RetrievalPipeline.retrieve()
    │
    ├── [Exact Path] ──► Lookup by ID, score = 1.0
    │
    └── [Semantic Path]
        ├── BM25 search ──┐
        │                 ├── Parallel (ThreadPoolExecutor, 2 workers)
        ├── Chroma search ┘   top_k × 3 candidates mỗi index (min 10)
        │
        ├── Step 1: RRF Merge (k=60, pure rank fusion)
        ├── Step 2: Separate exact matches (bonus = 2.0)
        ├── Step 3: Product Gate filter (binary remove)
        ├── Step 4: Hydrate candidates (load full doc content)
        ├── Step 5: CrossEncoder Rerank (ms-marco-MiniLM-L-6-v2, top 20)
        │           → sigmoid scores [0, 1]
        ├── Step 6: Metadata bonus (+0.03 service, +0.02 domain)
        ├── Step 7: Combine exact + reranked, truncate to top_k
        │
        ├── verify_retrieval() ──► warnings list
        └── calculate_confidence() ──► high | medium | low
    │
    ▼
ResponseEnvelope (results + meta + diagnostics)
```

### 2.4 Context Build Pipeline

```
ContextBuildRequest (consumer, check_ids, findings, query)
    │
    ▼
ContextService.build()
    │
    ├── Step 1: Retrieve checks ──► CheckService.search() per check_id
    ├── Step 2: Resolve mappings ──► MappingService.resolve() per check_id
    ├── Step 3: Retrieve maturity ──► MaturityService.search() per capability_id
    │
    └── Step 4: Build consumer bundle
        ├── CoverageSelector ──► Select checks/mappings/capabilities
        ├── BundleFactory ──► Planning | Risk | Report bundle
        ├── IntentDetector ──► Entity gating & control family inference
        └── PromptFormatter ──► Evidence summary + prompt-ready context
    │
    ▼
ContextBuildResponse (payload + diagnostics)
```

**3 Consumer Types:**
- **Planning:** findings + control_mapping_ids + capability_ids → cho Planning Agent
- **Risk:** primary_finding + related_findings + maturity_context → cho Risk Evaluation Agent
- **Report:** topics + findings + control_themes + recommended_practices → cho Report Agent

---

## 3. PHÂN TÍCH ĐIỂM MẠNH

### 3.1 Kiến Trúc Phân Tầng Rõ Ràng (Layered Architecture)

Hệ thống tuân thủ **Separation of Concerns** với 4 tầng riêng biệt:

| Tầng | Trách nhiệm | File chính |
|------|-------------|------------|
| **API** | HTTP handling, request validation | `routes/*.py` |
| **Services** | Business orchestration | `services/*.py` |
| **Retrieval** | Search logic, scoring, verification | `retrieval/*.py` |
| **Data/Index** | Storage abstraction | `indexing/*.py`, `ingestion/*.py` |

**Tại sao đây là điểm mạnh:**
- Mỗi tầng có thể thay đổi độc lập mà không ảnh hưởng tầng khác
- Dễ test từng tầng riêng biệt (unit test cho retrieval, integration test cho services)
- Tuân thủ **Single Responsibility Principle** — mỗi module chỉ làm một việc

### 3.2 Hybrid Retrieval với RRF

Hệ thống kết hợp **BM25 (lexical)** và **ChromaDB (vector)** qua **Reciprocal Rank Fusion**:

```
Final_Score(doc) = 1/(k + rank_bm25) + 1/(k + rank_vector) + bonuses
```

**Tại sao đây là điểm mạnh:**
- BM25 mạnh với exact keyword matching (check_id, service name)
- Vector search mạnh với semantic similarity (paraphrase, risk queries)
- RRF là phương pháp merge được chứng minh hiệu quả trong IR research
- Không cần normalize scores giữa hai hệ thống (chỉ dùng rank)

**Bằng chứng:** Sau khi enable hybrid đúng cách (Slice 1-2), Vector Visible đạt 100% (từ 0%), Top-5 accuracy tăng từ 65% lên 85%.

### 3.3 Externalized Scoring Configuration

Toàn bộ scoring parameters được tách ra `scoring_config.json`:

```json
{
  "rrf": { "k": 60 },
  "exact_match_bonus": 2.0,
  "metadata_bonus": { "service_match": 0.03, "domain_match": 0.02 },
  "reranker": { "enabled": true, "model": "cross-encoder/ms-marco-MiniLM-L-6-v2", "top_n": 20 },
  "product_gate": "filter",
  "confidence_thresholds": { ... },
  "ambiguity": { ... },
  "verification": { ... }
}
```

**Tại sao đây là điểm mạnh:**
- Tuning scoring **không cần sửa code** — chỉ edit JSON file
- Hỗ trợ `reload_scoring_config()` để hot-reload khi cần
- Benchmark có thể chạy lại với config khác nhau → dễ A/B testing
- Tuân thủ **Open/Closed Principle** — open for extension (config), closed for modification (code)

### 3.4 Route-Aware Confidence & Verification

Hệ thống có **post-retrieval quality signals** đa tầng:

**Verifier** phát hiện 9 loại warning, chia thành 2 mức:

*Severe (force confidence → low):*
- `exact_lookup_miss` — Expected exact nhưng không tìm thấy
- `exact_lookup_mismatch` — Tìm thấy nhưng doc_id không khớp
- `mapping_missing` — Check không có mapping
- `top1_doc_type_mismatch` — Top-1 sai document type
- `top1_filter_mismatch` — Top-1 không pass filters

*Moderate (degrade confidence):*
- `service_mismatch_top1` — Top-1 khác service so với query
- `weak_domain_alignment` — Domain không phù hợp
- `ambiguous_top_results` — Gap giữa top-1 và top-2 < 0.05
- `low_score_top1` — Score < 0.15

**Confidence** có threshold riêng theo query_type:
- `mapping_resolution`: high ≥ 0.99 (rất strict)
- `check_search`: high ≥ 0.70, medium ≥ 0.35
- `maturity_search`: high ≥ 0.60, medium ≥ 0.30
- `default`: high ≥ 0.65, medium ≥ 0.30

**Tại sao đây là điểm mạnh:**
- Agent có thể dựa vào `confidence` + `warnings` để quyết định có tin tưởng kết quả hay không
- **Fail-safe design**: Khi không chắc chắn, hệ thống báo `medium/low` confidence thay vì trả kết quả sai
- Diagnostics giúp debug production issues nhanh chóng

### 3.5 Multi-Consumer Context Builder

Module Context được thiết kế theo **Strategy Pattern** với 3 consumer types:

| Consumer | Bundle Output | Use Case |
|----------|--------------|----------|
| Planning | findings + mappings + capabilities | Lập kế hoạch remediation |
| Risk | primary_finding + maturity_context | Đánh giá rủi ro |
| Report | topics + themes + practices | Tổng hợp báo cáo |

**Tại sao đây là điểm mạnh:**
- **Single retrieval, multiple presentations** — dữ liệu truy vấn 1 lần, format khác nhau cho từng Agent
- BundleFactory + PromptFormatter tách biệt logic selection và formatting
- Dễ thêm consumer mới (ví dụ: Compliance Agent) mà không sửa retrieval logic

### 3.6 Centralized Constants & Intent Clusters

`constants.py` tập trung toàn bộ domain knowledge:

- **6 CONTROL_INTENT_CLUSTERS**: public_access, encryption_at_rest, encryption_in_transit, identity_access, logging_monitoring, resilience_backup
- **11 PRODUCT_ENTITY_GATES**: bedrock, sagemaker, guardduty, macie, ...
- **29 KNOWN_SERVICES**: s3, iam, ec2, rds, eks, lambda, vpc, guardduty, bedrock, ...

**Tại sao đây là điểm mạnh:**
- Một nơi duy nhất để cập nhật domain knowledge
- Entity gating ngăn false positive mappings (ví dụ: S3 check → Bedrock capability)
- Tuân thủ **DRY Principle** — không duplicate magic strings

### 3.7 Build Pipeline Có Validation

`build_all.py` thực hiện full pipeline với validation:

1. Normalize 3 corpus sources
2. Build BM25 indexes
3. Build Chroma vector indexes
4. **Validate** counts và write manifest
5. Cleanup orphaned collections

**Tại sao đây là điểm mạnh:**
- Reproducible builds — từ raw data → production indexes
- Manifest tracking version, counts, timestamps
- Orphaned collection cleanup ngăn disk bloat

### 3.8 Comprehensive Benchmark Framework

Benchmark system bao gồm:

- **60 test cases** across 6 services, 4 categories
- **Release criteria** với 8 quality gates
- **Comparison tool** so sánh baseline vs current
- **Per-category breakdown**: exact, paraphrase, risk, semantic_hard
- **S3 Agent Readiness benchmark** cho 3 consumer types

**Tại sao đây là điểm mạnh:**
- Có thể **đo lường impact** của mọi thay đổi
- Release criteria tạo quality gate trước khi deploy
- Category breakdown chỉ ra chính xác đâu cần cải thiện

---

## 4. PHÂN TÍCH ĐIỂM YẾU

### 4.1 [MEDIUM] Latency Vượt Ngưỡng

**Hiện trạng:** Average latency = **2,144ms** (ngưỡng: 2,000ms)

| Loại Query | Avg Latency |
|------------|-------------|
| Checks (exact) | 2,132ms |
| Checks (paraphrase) | 2,116ms |
| Checks (risk) | 2,210ms |
| Checks (semantic_hard) | 2,155ms |
| Maturity | 2,048ms |

**Phân tích nguyên nhân:**
- BM25 search + Vector search đã chạy **song song** (ThreadPoolExecutor, 2 workers), nhưng vẫn chưa đủ nhanh
- ChromaDB persistent mode có I/O overhead trên Windows
- `search_top_k_multiplier = 3` → retrieve 3× top_k candidates từ mỗi index rồi merge
- Cross-encoder reranking thêm ~100ms cho 20 candidates
- ContextService gọi sequential per-check (N requests cho N check_ids) → tổng latency cộng dồn

**Tác động:**
- Đây là **chỉ tiêu duy nhất** khiến Release Criteria FAIL
- Trong context Agent system, mỗi context build gọi 3-5 retrieval → tổng latency có thể 6-10s
- Tuy nhiên, với corpus size nhỏ (1,157 docs), đây không phải bottleneck thực sự — có thể optimize đáng kể

### 4.2 [MEDIUM] Semantic Hard & Risk Categories Vẫn Yếu

**Hiện trạng (Checks):**

| Category | Top-1 | Top-5 |
|----------|-------|-------|
| Exact | 18/18 (100%) | 18/18 (100%) |
| Paraphrase | 6/9 (66.7%) | 9/9 (100%) |
| **Risk** | **1/6 (16.7%)** | **5/6 (83.3%)** |
| **Semantic Hard** | **2/8 (25%)** | **3/8 (37.5%)** |

**Phân tích nguyên nhân:**
- `all-MiniLM-L6-v2` là model nhẹ (384 dims), semantic discrimination yếu với các query phức tạp
- Risk queries thường dùng ngôn ngữ khác biệt so với retrieval text (ví dụ: "what happens if someone accesses my bucket publicly" vs "block_public_access")
- Semantic hard cases có score gap rất nhỏ giữa top-1 và top-2 (~0.001) → ranking không ổn định

**Tác động:**
- Agent nhận được context sai khi hỏi câu hỏi về risk hoặc semantic phức tạp
- Top-5 vẫn khá (83-100% cho risk), nghĩa là correct answer có trong candidates nhưng bị rank sai

### 4.3 [MEDIUM] Auto-Generated Mappings Chưa Được Review

**Hiện trạng:**
- **21 mappings curated** cho S3 có `review_status: "approved"` (từ `maturity_mappings_curated.json`)
- **~481 mappings** còn lại có `review_status: "draft"` (auto-generated bởi `gen_maturity_mapping.py`)
- Quality gate đã loại ~70 low-quality mappings (min_score=0.25, min_score_gap=0.05)
- MappingService ranking: approved(10) > reviewed(5) > auto_high(2) > draft(1)
- `filter_for_agent_context()` prefer approved/reviewed khi build context

**Đã giải quyết một phần:**
- Entity gating trong `constants.py` đã ngăn false positive rõ ràng (S3 → Bedrock)
- `maturity_mappings_curated.json` đã có 21 approved S3 mappings
- Forbidden capability rate = 0% trong benchmark

**Tác động còn lại:**
- Mappings cho services ngoài S3 chưa được curate
- Agent có thể nhận mapping không chính xác cho IAM, EC2, RDS, CloudTrail, KMS
- Confidence cho mapping_resolution phải ≥ 0.99 → rất ít mapping đạt "high" confidence

### 4.4 [LOW] Scoring Vẫn Dùng Một Số Heuristics

**Hiện trạng:** Scoring pipeline đã chuyển từ nhiều handcrafted bonuses sang **CrossEncoder Reranker** (ms-marco-MiniLM-L-6-v2), nhưng vẫn còn metadata bonuses:

```
metadata_bonus:     +0.03 (service match) + 0.02 (domain match)
exact_match_bonus:  2.0 (luôn đứng đầu kết quả)
```

**Phân tích:**
- CrossEncoder đã thay thế phần lớn scoring heuristics cũ (intent_bonus, check_id_boost, product_penalty)
- Metadata bonus chỉ là fine-tuning nhỏ trên top của cross-encoder scores
- Product gate filtering vẫn dùng PRODUCT_ENTITY_GATES (binary filter, không phải scoring)
- Scoring parameters externalized trong `scoring_config.json` → thay đổi không cần code change

**Tác động:**
- Khi thêm service mới hoặc intent mới, cần update constants.py + scoring_config.json
- CrossEncoder có thể không optimal cho domain AWS security — nhưng hiện tại hoạt động tốt hơn heuristics
- Đã được mitigate bằng benchmark framework (regression detection)

### 4.5 [LOW] Aliases Chưa Scale

**Hiện trạng:**
- Chỉ ~7 S3 checks và ~6 maturity capabilities có handcrafted aliases
- 570+ checks còn lại không có aliases
- Aliases giúp đáng kể cho semantic search (bridge gap giữa user language và technical term)

**Tác động:**
- Paraphrase và semantic queries cho non-S3 services có thể hoạt động kém hơn
- Tuy nhiên, prefixed retrieval text (Slice 2) đã bù đắp phần nào bằng keywords và synonyms

---

## 5. ĐÁNH GIÁ CHẤT LƯỢNG TRUY VẤN & BENCHMARK

### 5.1 Release Criteria Assessment

| Tiêu chí | Ngưỡng | Thực tế | Trạng thái |
|-----------|--------|---------|------------|
| Checks Top-1 Accuracy | ≥ 60% | **65.85%** | **PASS** |
| Checks Top-5 Accuracy | ≥ 80% | **85.37%** | **PASS** |
| Maturity Top-1 Accuracy | ≥ 60% | **73.68%** | **PASS** |
| Maturity Top-5 Accuracy | ≥ 80% | **100%** | **PASS** |
| Forbidden Capability Rate | = 0% | **0%** | **PASS** |
| Empty Bundle Rate | = 0% | **0%** | **PASS** |
| Service Precision | ≥ 85% | **87.8%** | **PASS** |
| Average Latency | ≤ 2000ms | **2144ms** | **FAIL** |

**Kết quả: 7/8 tiêu chí PASS, 1 FAIL (latency)**

### 5.2 Tiến Bộ Qua Các Iteration

| Metric | Initial | Slice 1 | Slice 2 | Slice 10 (Latest) |
|--------|---------|---------|---------|-------------------|
| Checks Top-1 | 40% | 35% | 35% | **65.85%** |
| Checks Top-5 | 65% | 75% | 85% | **85.37%** |
| Maturity Top-1 | 0% | 40% | 40% | **73.68%** |
| Maturity Top-5 | 0% | 60% | 60% | **100%** |
| Service Precision | N/A | 95% | 100% | **87.8%** |
| Avg Latency | 2.2s | 3.2s | 2.3s | **2.14s** |

**Nhận xét:**
- **Checks Top-1** cải thiện rõ rệt: 40% → 65.85% (+25.85 pp) — nhờ intent bonuses, entity gating, prefixed text
- **Maturity** từ 0% lên 73.68%/100% — nhờ fix embedding model binding và enable hybrid retrieval
- **Latency** giảm từ 3.2s → 2.14s — nhờ retrieval text optimization giảm document size

### 5.3 Phân Tích Theo Category

**Checks (41 cases):**

| Category | Cases | Top-1 | Top-3 | Top-5 | Nhận xét |
|----------|-------|-------|-------|-------|----------|
| Exact | 18 | 100% | 100% | 100% | Hoàn hảo — exact lookup hoạt động đúng |
| Paraphrase | 9 | 66.7% | 88.9% | 100% | Tốt — Top-5 = 100%, Top-1 cần cải thiện |
| Risk | 6 | 16.7% | 66.7% | 83.3% | Yếu top-1, nhưng recall tốt |
| Semantic Hard | 8 | 25% | 37.5% | 37.5% | Điểm yếu chính — cần reranking |

**Maturity (19 cases):**

| Category | Cases | Top-1 | Top-3 | Top-5 | Nhận xét |
|----------|-------|-------|-------|-------|----------|
| Exact | 7 | 100% | 100% | 100% | Hoàn hảo |
| Paraphrase | 6 | 83.3% | 100% | 100% | Rất tốt |
| Semantic Hard | 6 | 33.3% | 83.3% | 100% | Recall tốt, precision cần cải thiện |

### 5.4 Phân Tích Theo Service

| Service | Cases | Top-1 | Top-5 | Service Precision | Nhận xét |
|---------|-------|-------|-------|-------------------|----------|
| S3 | 10 | 60% | 90% | 100% | Đã được curate mappings |
| IAM | 9 | 66.7% | 88.9% | 100% | Tốt |
| EC2 | 9 | 77.8% | 88.9% | 88.9% | Tốt nhất top-1 |
| RDS | 5 | 60% | 80% | 60% | Service precision thấp |
| CloudTrail | 5 | 40% | 60% | 60% | Yếu nhất — cần aliases |
| KMS | 3 | 100% | 100% | 100% | Hoàn hảo (ít cases) |

### 5.5 S3 Agent Readiness

Benchmark chuyên biệt cho 3 consumer types (9 test cases):

| Consumer | Status | Check Hit | Capability Hit | Forbidden | Bundle Complete | Latency |
|----------|--------|-----------|----------------|-----------|-----------------|---------|
| Planning | **READY** | 100% | 100% | 0% | 100% | 1,578ms |
| Risk | **READY** | 100% | 100% | 0% | 100% | 1,581ms |
| Report | **READY** | 100% | 100% | 0% | 100% | 1,284ms |

**Kết luận:** S3 service đã **sẵn sàng tích hợp** vào Agent System cho cả 3 consumer types.

### 5.6 Confidence Distribution

Trong S3 Agent Readiness benchmark:
- High: 0/9 (0%)
- Medium: 9/9 (100%)
- Low: 0/9 (0%)

**Nhận xét:** Không có case nào đạt "high" confidence — đây là do confidence thresholds khá strict. Tuy nhiên, "medium" confidence vẫn là mức chấp nhận được cho Agent usage — Agent nên flag `review_recommended = true` nhưng vẫn sử dụng kết quả.

---

## 6. ĐỀ XUẤT BƯỚC TIẾP THEO

### 6.1 Tích Hợp S3 Vào Agent System (Ưu tiên cao — Sẵn sàng)

**Lý do:** S3 Agent Readiness benchmark cho thấy 100% check hit, 100% capability hit, 0% forbidden, 100% bundle complete cho cả 3 consumer types.

**Hành động:**
1. Tích hợp RAG API endpoints vào Scanner Agent / Risk Agent / Report Agent
2. Agent sử dụng `POST /v1/context/build` với `consumer` tương ứng
3. Agent kiểm tra `confidence` và `warnings` trong response:
   - `confidence = high/medium` → sử dụng context
   - `confidence = low` hoặc có `exact_lookup_miss` → fallback hoặc flag cho user
4. Xử lý `review_recommended` — Agent thông báo cho user khi context cần review

### 6.2 Optimize Latency (Ưu tiên cao — Release Criteria)

**Mục tiêu:** Giảm average latency xuống < 2,000ms

**Đã implement:**
- ✅ **Parallel search:** BM25 và Chroma search chạy đồng thời (ThreadPoolExecutor, 2 workers)

**Hành động đề xuất (chưa implement):**
1. **Batch context building:** ContextService gọi sequential per-check — chuyển sang batch retrieval
2. **Giảm search_top_k_multiplier:** Từ 3 xuống 2 (giảm candidates cần merge/rerank)
3. **Reduce reranker pool:** Từ top_n=20 xuống 10-15 (giảm cross-encoder compute)
4. **Pre-warm models:** Load embedding + cross-encoder models during startup (hiện lazy load)
5. **Cache warming:** Pre-load BM25 indexes và Chroma collections khi server start
6. **Index optimization:** Xem xét HNSW parameters cho ChromaDB (ef_search, M)

**Dự kiến impact:** Batch context + reduce reranker pool có thể giảm 20-30% latency.

### 6.3 Cải Thiện Semantic Hard & Risk Categories (Ưu tiên trung bình)

**Mục tiêu:** Nâng Top-1 cho risk (16.7% → >50%) và semantic_hard (25% → >40%)

**Đã implement:**
- ✅ **Cross-encoder reranking:** `cross-encoder/ms-marco-MiniLM-L-6-v2` rerank top-20 candidates — cải thiện ranking nhưng chưa đủ cho risk/semantic_hard

**Hành động đề xuất (chưa implement):**
1. **Upgrade embedding model:** Chuyển sang `bge-small-en-v1.5` hoặc `all-MiniLM-L12-v2` (semantic discrimination tốt hơn)
2. **LLM-based query rewriting:** Rewrite risk queries thành technical queries trước khi search (ví dụ: "what if someone accesses my bucket publicly" → "s3 block public access")
3. **Thêm aliases/synonyms** cho top-20 checks quan trọng nhất (theo frequency trong scan results)
4. **Expand benchmark cases** — thêm 10-15 risk/semantic_hard cases để có statistical significance

### 6.4 Curate Mappings Cho Các Services Khác (Ưu tiên trung bình)

**Hiện trạng:** Chỉ S3 có curated mappings. IAM, EC2, RDS, CloudTrail, KMS vẫn dùng auto-generated.

**Hành động đề xuất:**
1. Curate mappings cho **IAM** và **EC2** (nhiều checks nhất sau S3)
2. Sử dụng LLM-assisted mapping generation (thay vì pure BM25 heuristics) cho các service còn lại
3. Implement `review_status` workflow: draft → reviewed → approved
4. MappingService đã có logic prefer approved mappings — chỉ cần data

### 6.5 Mở Rộng Agent Integration (Ưu tiên thấp — Sau khi S3 stable)

**Hành động:**
1. Sau khi S3 integration stable, mở rộng sang IAM, EC2
2. Thêm consumer type mới nếu cần (ví dụ: Compliance Agent)
3. Implement feedback loop: Agent report quality → benchmark cases update
4. Xem xét caching layer giữa Agent và RAG API (repeated queries cho cùng scan)

---

## 7. KẾT LUẬN

### 7.1 Đánh Giá Tổng Thể

RAG System đã đạt được **mức chất lượng tốt** sau quá trình optimization qua 10 slices:

| Khía cạnh | Đánh giá | Chi tiết |
|-----------|----------|----------|
| **Kiến trúc** | Tốt | Layered, separation of concerns, extensible |
| **Code Quality** | Tốt | Clean code, DRY, externalized config |
| **Retrieval Accuracy** | Tốt | 7/8 release criteria PASS |
| **Safety** | Tốt | 0% forbidden capability, entity gating |
| **Latency** | Cần cải thiện | 2,144ms vs 2,000ms target |
| **Semantic Understanding** | Trung bình | Risk/semantic_hard categories yếu |
| **Data Quality** | Trung bình | S3 curated, các service khác chưa |

### 7.2 Verdict: Sẵn Sàng Tích Hợp Cho S3

**RAG System đã sẵn sàng tích hợp vào Agent System** cho service S3, với các điều kiện:

1. **Agent phải kiểm tra** `confidence` và `warnings` trước khi sử dụng context
2. **Latency** cần được optimize (parallel search) trước khi scale lên nhiều services
3. **Mappings** cho các services khác cần được curate trước khi enable

### 7.3 Metrics Tổng Hợp

```
┌─────────────────────────────────────────────────┐
│         RAG SYSTEM QUALITY SCORECARD            │
├─────────────────────────────────────────────────┤
│                                                 │
│  Combined Top-1 Accuracy:    68.33%  (target ≥60%) ✓  │
│  Combined Top-5 Accuracy:    90.00%  (target ≥80%) ✓  │
│  Service Precision:          87.80%  (target ≥85%) ✓  │
│  Forbidden Capability Rate:   0.00%  (target =0%)  ✓  │
│  Empty Bundle Rate:           0.00%  (target =0%)  ✓  │
│  Average Latency:          2144ms   (target ≤2000) ✗  │
│                                                 │
│  S3 Planning Readiness:     READY               │
│  S3 Risk Readiness:         READY               │
│  S3 Report Readiness:       READY               │
│                                                 │
│  Release Verdict:  7/8 PASS — CONDITIONAL PASS  │
│  Integration:      S3 READY, others PENDING     │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

*Báo cáo này dựa trên phân tích source code, benchmark data (60 test cases, 9 S3 agent readiness cases), và các tài liệu kỹ thuật của RAG System. Cập nhật ngày 2026-04-02 từ bản gốc 2026-03-26.*
