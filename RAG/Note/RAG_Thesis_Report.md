# BÁO CÁO CHI TIẾT VỀ HỆ THỐNG RAG (RETRIEVAL-AUGMENTED GENERATION)

**Phiên bản index**: rag-v2-2026-03-17
**Ngày báo cáo**: 02/04/2026 (cập nhật từ bản gốc 26/03/2026)
**Embedding model**: all-MiniLM-L6-v2 (384 chiều)
**Tổng số tài liệu đã đánh chỉ mục**: 1.157 documents

---

## MỤC LỤC

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Kiến trúc Logic (Logical Architecture)](#2-kiến-trúc-logic-logical-architecture)
3. [Kiến trúc Luồng xử lý (Flow Architecture)](#3-kiến-trúc-luồng-xử-lý-flow-architecture)
4. [Kiến trúc Source Code](#4-kiến-trúc-source-code)
5. [Phân tích chi tiết các thành phần](#5-phân-tích-chi-tiết-các-thành-phần)
   - 5.1 [Knowledge Engineering Layer](#51-knowledge-engineering-layer)
   - 5.2 [Knowledge Storage Layer](#52-knowledge-storage-layer)
   - 5.3 [Query Intelligence Layer](#53-query-intelligence-layer)
   - 5.4 [Retrieval Intelligence Layer](#54-retrieval-intelligence-layer)
   - 5.5 [Context Construction Layer](#55-context-construction-layer)
   - 5.6 [Generation Layer](#56-generation-layer)
6. [Luồng dữ liệu End-to-End](#6-luồng-dữ-liệu-end-to-end)
7. [Những điểm quan trọng trong quá trình Implementation](#7-những-điểm-quan-trọng-trong-quá-trình-implementation)
8. [Đánh giá chất lượng truy vấn và Benchmark](#8-đánh-giá-chất-lượng-truy-vấn-và-benchmark)
9. [Phân tích điểm mạnh và điểm yếu](#9-phân-tích-điểm-mạnh-và-điểm-yếu)
10. [Kết luận và hướng phát triển](#10-kết-luận-và-hướng-phát-triển)

---

## 1. Tổng quan hệ thống

### 1.1 Mục đích

Hệ thống RAG được thiết kế để phục vụ ba loại agent (consumer) trong quy trình đánh giá bảo mật AWS:

| Consumer | Mục đích | Đặc điểm context |
|----------|----------|-------------------|
| **Planning Agent** | Lập kế hoạch quét bảo mật, quyết định checks cần thực hiện | Đa dạng hóa checks theo intent, coverage rộng |
| **Risk Evaluation Agent** | Đánh giá rủi ro cho từng finding cụ thể | Primary finding + related checks + control mapping |
| **Report Agent** | Tổng hợp báo cáo bảo mật | Key findings + control themes + recommended practices |

### 1.2 Phạm vi dữ liệu

Hệ thống quản lý ba corpus (kho tài liệu) chính:

| Corpus | Số lượng | Mô tả |
|--------|----------|-------|
| **prowler_checks** | 577 documents | Các kiểm tra bảo mật AWS từ Prowler framework |
| **maturity_capabilities** | 78 documents | Năng lực bảo mật theo mô hình maturity |
| **maturity_mappings** | 502 documents | Ánh xạ giữa checks và capabilities |

### 1.3 Công nghệ sử dụng

| Thành phần | Công nghệ | Vai trò |
|------------|-----------|---------|
| Framework | FastAPI | REST API server |
| Vector Database | ChromaDB (persistent) | Lưu trữ và truy vấn vector embeddings |
| Lexical Search | BM25 (custom implementation) | Tìm kiếm từ khóa |
| Embedding Model | all-MiniLM-L6-v2 (SentenceTransformers) | Chuyển đổi text → vector 384 chiều |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 | Xếp hạng lại kết quả truy vấn |
| Merge Strategy | Reciprocal Rank Fusion (RRF, k=60) | Kết hợp kết quả lexical + vector |

---

## 2. Kiến trúc Logic (Logical Architecture)

Kiến trúc logic của hệ thống được tổ chức thành **5 tầng (layer)** với trách nhiệm rõ ràng, tuân theo nguyên tắc **Separation of Concerns**:

### 2.1 Sơ đồ tổng quan các tầng

```
┌─────────────────────────────────────┐
│       Query Intelligence Layer      │  ← Tiếp nhận và phân tích truy vấn
│  - Query Interface (User / Agent)   │
│  - Query Normalization              │
│  - Query Intent Abstraction         │
│  - Semantic Routing                 │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│    Retrieval Intelligence Layer     │  ← Tìm kiếm và xếp hạng kết quả
│  - Query Embedding                  │
│  - Hybrid Candidate Retrieval       │
│  - Metadata-aware Filtering         │
│  - Retrieval Parameterization       │
│  - Re-ranking                       │
└──────┬──────────────┬───────────────┘
       │              │
       ▼              ▼
┌──────────────┐ ┌────────────────────┐
│  Knowledge   │ │ Context            │
│  Storage     │ │ Construction Layer │  ← Xây dựng context cho agent
│  Layer       │ │ - Context Prep     │
│ - Vector     │ │ - Context Packaging│
│   Store      │ └─────────┬──────────┘
│ - Vector     │           │
│   Index      │           ▼
│ - Metadata   │ ┌────────────────────┐
│   Index      │ │  Generation Layer  │  ← Tạo prompt và gọi LLM
│              │ │ - Context Selection│
└──────┬───────┘ │ - Prompt Composit. │
       ▲         │ - LLM Inference    │
       │         └────────────────────┘
┌──────┴───────┐
│  Knowledge   │
│  Engineering │  ← Xử lý dữ liệu offline
│  Layer       │
│ - Data Clean │
│ - Chunking   │
│ - Metadata   │
│ - Embedding  │
└──────────────┘
```

### 2.2 Mô tả từng tầng

**Query Intelligence Layer** — Tầng đầu tiên tiếp nhận truy vấn từ user hoặc agent. Thực hiện chuẩn hóa (lowercase, stopword removal, stemming), phát hiện intent (encryption, public_access, iam, logging...), và định tuyến semantic (quyết định corpus nào cần truy vấn, đường đi exact hay hybrid).

**Retrieval Intelligence Layer** — Tầng cốt lõi thực hiện tìm kiếm song song trên BM25 (lexical) và ChromaDB (vector), sau đó kết hợp bằng RRF, lọc theo metadata, và xếp hạng lại bằng cross-encoder. Đây là tầng quyết định chất lượng kết quả truy vấn.

**Knowledge Storage Layer** — Lưu trữ dữ liệu đã được đánh chỉ mục dưới dạng BM25 pickle files (cho lexical search) và ChromaDB collections (cho vector search). Mỗi corpus có cả hai loại index.

**Context Construction Layer** — Chọn lọc và đóng gói kết quả truy vấn thành context phù hợp cho từng loại agent (planning, risk, report). Bao gồm logic coverage-aware selection và consumer-specific bundling.

**Knowledge Engineering Layer** — Pipeline offline xử lý dữ liệu thô (raw JSON) thành dạng chuẩn hóa, tạo embeddings, và xây dựng indexes. Chỉ chạy khi cần rebuild dữ liệu.

**Generation Layer** — Định dạng context thành prompt sẵn sàng cho LLM, bao gồm header (metadata, confidence), evidence block (checks, mappings, capabilities), và guidance block (hướng dẫn theo consumer type).

### 2.3 Nguyên tắc thiết kế

Kiến trúc logic tuân theo các nguyên tắc:

1. **Separation of Concerns**: Mỗi tầng có trách nhiệm rõ ràng, không phụ thuộc chéo.
2. **Graceful Degradation**: Nếu vector search không khả dụng, hệ thống vẫn hoạt động với lexical-only mode.
3. **Consumer-Aware Design**: Cùng một retrieval pipeline phục vụ nhiều loại consumer với context khác nhau.
4. **Configuration-Driven**: Tất cả tham số scoring, thresholds được externalize ra file JSON, cho phép tuning không cần sửa code.

---

## 3. Kiến trúc Luồng xử lý (Flow Architecture)

Flow Architecture mô tả cách dữ liệu di chuyển qua hệ thống theo hai luồng chính: **Knowledge Indexing** (offline) và **Query Retrieval & Generation** (online).

### 3.1 Knowledge Indexing Flow (Offline Pipeline)

```
RAG Knowledge Sources
    │
    ▼
Data Cleaning & Normalization
    │  ← normalizers.py: Unicode NFKC, snake_case, stopword removal, stemming
    │     Tạo semantic aliases cho high-impact checks
    ▼
Semantic Chunking
    │  ← Mỗi document là một đơn vị nguyên tử (không split)
    │     Text được tổ hợp từ nhiều fields: check_id + service + description + risk + remediation
    ▼
Metadata Modeling
    │  ← Gắn metadata: doc_type, service, severity, domain, keywords, tags
    │     Tạo reverse indexes: check_id → doc_id, capability_id → doc_ids
    ▼
Embedding Pipeline
    │  ← all-MiniLM-L6-v2 tạo dense embeddings 384 chiều
    │     Lưu vào ChromaDB collections
    ▼
┌───────────┬─────────────┐
│  Storage  │    Index    │
│ (Chroma)  │   (BM25)   │
└───────────┴─────────────┘
```

**Chi tiết quá trình Normalization:**

Normalizers là thành phần quan trọng nhất trong offline pipeline, đảm bảo tính nhất quán giữa build-time và query-time:

- **Prowler Check normalization** (`normalize_prowler_doc`): Kết hợp check_id, service, title, description, risk, remediation, keywords thành `retrieval_text`. Đặc biệt, hệ thống sử dụng **semantic aliases** — danh sách 20+ alias thủ công cho các checks quan trọng (ví dụ: `s3_account_level_public_access_blocks` có aliases: "public access", "prevent public exposure", "block public s3"...). Điều này giúp bridge gap giữa natural language query và technical check ID.

- **Maturity Capability normalization** (`normalize_maturity_doc`): Tương tự, kết hợp capability_id, name, domain, summary, risk_explanation, guidance, recommended_practices.

- **Maturity Mapping normalization** (`normalize_mapping_doc`): Kết hợp check_id, capability_id, mapping_reason, mapping_type, mapping_confidence. Sử dụng capability name lookup để resolve canonical IDs.

- **Token normalization**: Tất cả text đều qua quy trình: lowercase → split on non-alphanumeric → remove stopwords (English + AWS-specific) → Snowball stemming → token list.

**Chi tiết quá trình Auto-Generation Mappings:**

Script `gen_maturity_mapping.py` tự động tạo 502 mappings giữa prowler checks và maturity capabilities bằng:

1. **Overlap scoring**: Đếm token overlap giữa check text và capability text
2. **Phrase hit detection**: Boost điểm cho 14 important phrases (ví dụ: "public access", "encryption at rest")
3. **Canonical synonyms**: 40+ synonym mappings (ví dụ: "bucket" → "storage", "encrypted" → "encrypt")
4. **Intent & product bonuses/penalties**: Sử dụng `CONTROL_INTENT_CLUSTERS` và `PRODUCT_ENTITY_GATES` từ constants
5. **Quality labeling**: Tự động gán mapping_confidence (high/medium/low) và review_status

### 3.2 Query Retrieval & Generation Flow (Online Pipeline)

```
User / Agent Query
    │
    ▼
Query Normalization ──────────────────────────────── Query Abstraction
    │  ← normalize_query(): lowercase,             │  ← SemanticRouter:
    │     index normalization                       │     - looks_like_check_id()
    │                                               │     - looks_like_capability_id()
    │                                               │     - extract_service()
    │                                               │     - detect query hints
    ▼                                               ▼
Query Intent Abstraction ──────► Retrieval Parameterization
    │  ← IntentDetector:                    │  ← RouteDecision:
    │     detect_query_intents()            │     query_type, corpus, filters,
    │     infer_control_families()          │     exact_check_id, retrieval_mode
    │                                       │
    └───────────────┬───────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  Query Embedding         Keyword Extraction
        │                       │
        ▼                       ▼
  Vector Search            BM25/FT Search
  (ChromaDB)               (Pickle indexes)
        │                       │
        └───────────┬───────────┘
                    ▼
              RRF Merger ──────► Product Gate Filter
                    │               │  ← Loại bỏ capability-check pairs không tương thích
                    ▼               │     (ví dụ: Bedrock capability + S3 check)
              Re-ranking ◄──────────┘
                    │  ← CrossEncoderReranker:
                    │     ms-marco-MiniLM-L-6-v2
                    │     Sigmoid normalization → [0, 1]
                    ▼
         ┌──────────────────────────────────────────┐
         │        CONTEXT CONSTRUCTION               │
         │                                           │
         │  Context Preparation                      │
         │    ← CoverageSelector:                    │
         │      - Planning: diversify by intents     │
         │      - Risk: primary + related            │
         │      - Report: key findings + themes      │
         │                                           │
         │  Context Packaging                        │
         │    ← BundleFactory:                       │
         │      - PlanningBundle                     │
         │      - RiskBundle                         │
         │      - ReportBundle                       │
         │                                           │
         └────────────────┬──────────────────────────┘
                          ▼
         ┌──────────────────────────────────────────┐
         │            GENERATION                     │
         │                                           │
         │  Prompt Composition                       │
         │    ← PromptFormatter:                     │
         │      - Header (consumer, confidence)      │
         │      - Evidence block (checks, mappings)  │
         │      - Guidance block (instructions)      │
         │                                           │
         │  LLM Inference ──► Final Answer           │
         │                                           │
         │  Evaluation                               │
         │    ← Verification + Confidence scoring    │
         └──────────────────────────────────────────┘
```

### 3.3 Ba đường đi chính trong Retrieval

Hệ thống hỗ trợ ba đường đi (path) khác nhau tùy theo loại truy vấn:

**Path 1 — Exact Lookup** (khi query là check_id hoặc capability_id):
```
Query "s3_bucket_level_public_access_block"
  → SemanticRouter nhận diện exact_check_id
  → O(1) lookup trong BM25 reverse index
  → Trả về document trực tiếp, score=1.0
  → Confidence = high (nếu tìm thấy)
```

**Path 2 — Hybrid Search** (khi query là natural language):
```
Query "how to prevent s3 bucket from being publicly exposed"
  → SemanticRouter: service=s3, intents=[public_access]
  → Song song: BM25 search + ChromaDB vector search
  → RRF merge (k=60)
  → Product Gate filter
  → Cross-encoder rerank (top 20)
  → Metadata bonus (+0.03 service match, +0.02 domain match)
  → Verification + Confidence calculation
```

**Path 3 — Mapping Resolution** (khi cần resolve check → capability):
```
check_id "s3_account_level_public_access_blocks"
  → Direct lookup trong mapping index
  → Filter by service, domain
  → Sort by: review_status → confidence → score → capability_id
  → Trả về best mapping + top-5 candidates
```

---

## 4. Kiến trúc Source Code

### 4.1 Cấu trúc thư mục

```
RAG/app/
├── main.py                          # Entry point, FastAPI lifespan, DI setup (126 lines)
├── api/
│   └── routes/
│       ├── __init__.py              # Router aggregation
│       ├── health.py                # Health check endpoint (79 lines)
│       ├── retrieve.py              # /v1/retrieve/checks, /v1/retrieve/maturity, /v1/context/build
│       └── resolve.py               # /v1/resolve/mapping
├── core/
│   ├── config.py                    # Configuration, paths, corpus registry (200 lines)
│   ├── models.py                    # Pydantic data models (342 lines)
│   ├── constants.py                 # Keyword clusters, intent patterns (229 lines)
│   ├── utils.py                     # Utility functions (mapping_sort_key) (43 lines)
│   ├── errors.py                    # Error helpers, error codes (48 lines)
│   └── scoring_config.json          # Externalized scoring parameters
├── ingestion/
│   ├── loaders.py                   # JSON loaders (62 lines)
│   └── normalizers.py               # Text normalization, document builders (756 lines)
├── indexing/
│   ├── lexical_index.py             # BM25 implementation (351 lines)
│   └── vector_index.py              # ChromaDB wrapper (231 lines)
├── retrieval/
│   ├── pipeline.py                  # Hybrid retrieval orchestration (869 lines)
│   ├── router.py                    # Semantic routing (344 lines)
│   ├── confidence.py                # Confidence estimation (121 lines)
│   ├── verifier.py                  # Result verification (156 lines)
│   └── reranker.py                  # Cross-encoder reranking (96 lines)
├── context/
│   ├── context_builder.py           # Context building facade (157 lines)
│   ├── coverage_selector.py         # Coverage-aware selection (383 lines)
│   ├── bundle_factory.py            # Consumer-specific bundles (346 lines)
│   ├── intent_detector.py           # Intent & entity gate detection (133 lines)
│   ├── prompt_formatter.py          # LLM-ready formatting (210 lines)
│   ├── _helpers.py                  # Utility functions (179 lines)
│   └── __init__.py
└── services/
    ├── context_service.py           # Orchestration service (707 lines)
    ├── mapping_service.py           # Mapping resolution (304 lines)
    ├── check_service.py             # Check retrieval wrapper (153 lines)
    └── maturity_service.py          # Maturity retrieval wrapper (253 lines)
```

### 4.2 Mapping Kiến trúc Logic ↔ Source Code

Bảng dưới đây ánh xạ mỗi tầng trong Logical Architecture sang các file source code tương ứng:

| Logical Layer | Source Files | Trách nhiệm chính |
|---------------|-------------|-------------------|
| **Knowledge Engineering** | `ingestion/normalizers.py`, `scripts/build_all.py`, `scripts/gen_maturity_mapping.py` | Chuẩn hóa dữ liệu, tạo embeddings, build indexes |
| **Knowledge Storage** | `indexing/lexical_index.py`, `indexing/vector_index.py`, `data/indexes/` | Lưu trữ BM25 pickle + ChromaDB collections |
| **Query Intelligence** | `retrieval/router.py`, `context/intent_detector.py`, `ingestion/normalizers.py` (query normalization) | Phân tích query, routing, intent detection |
| **Retrieval Intelligence** | `retrieval/pipeline.py`, `retrieval/reranker.py`, `retrieval/verifier.py`, `retrieval/confidence.py` | Hybrid search, merge, rerank, verify, confidence |
| **Context Construction** | `context/context_builder.py`, `context/coverage_selector.py`, `context/bundle_factory.py`, `services/context_service.py` | Selection, bundling, orchestration |
| **Generation** | `context/prompt_formatter.py`, `core/models.py` (PromptReadyContext) | Format prompt cho LLM |

### 4.3 Dependency Graph giữa các module

```
main.py
  ├── api/routes/ (HTTP endpoints)
  │     └── services/ (CheckService, MaturityService, MappingService, ContextService)
  │           ├── retrieval/pipeline.py (RetrievalPipeline)
  │           │     ├── retrieval/router.py (SemanticRouter)
  │           │     ├── indexing/lexical_index.py (BM25Index)
  │           │     ├── indexing/vector_index.py (VectorIndex)
  │           │     ├── retrieval/reranker.py (CrossEncoderReranker)
  │           │     ├── retrieval/verifier.py (verify_retrieval)
  │           │     └── retrieval/confidence.py (calculate_confidence)
  │           └── context/context_builder.py (ContextBuilder)
  │                 ├── context/coverage_selector.py (CoverageSelector)
  │                 ├── context/bundle_factory.py (BundleFactory)
  │                 ├── context/intent_detector.py (IntentDetector)
  │                 └── context/prompt_formatter.py (PromptFormatter)
  └── core/
        ├── config.py (Configuration + scoring_config.json)
        ├── models.py (Pydantic models)
        ├── constants.py (Keyword clusters)
        └── utils.py (Utility functions)
```

---

## 5. Phân tích chi tiết các thành phần

### 5.1 Knowledge Engineering Layer

#### 5.1.1 Data Cleaning & Normalization (`normalizers.py` — 756 dòng)

Đây là file lớn nhất trong hệ thống, chịu trách nhiệm đảm bảo tính nhất quán giữa dữ liệu build-time và query-time.

**Quy trình chuẩn hóa text:**
```
Input text
  → lowercase()
  → split trên ký tự non-alphanumeric
  → remove ENGLISH_STOPWORDS + AWS_STOPWORDS
  → Snowball stemming (English)
  → Output: token list
```

**Hệ thống Semantic Aliases:**

Một trong những quyết định thiết kế quan trọng nhất — hệ thống alias thủ công cho các checks có tần suất sử dụng cao. Ví dụ cho check `s3_account_level_public_access_blocks`:

```
Aliases: "public access", "prevent public exposure", "block public s3",
         "s3 public access block", "account level public access",
         "prevent public bucket", "s3 bucket public access",
         ... (20+ aliases)
```

**Ý nghĩa**: Khi user hỏi "how to prevent public access to S3 buckets", các aliases giúp BM25 match được check_id kỹ thuật mà không cần dựa hoàn toàn vào vector search. Đây là một dạng **manual query expansion** - bù đắp cho điểm yếu của lexical search khi query dùng ngôn ngữ tự nhiên.

**Text Overlap Detection:**

Hệ thống kiểm tra trùng lặp giữa description, risk, remediation trước khi concatenate vào `retrieval_text`, tránh inflating BM25 scores cho terms lặp lại.

#### 5.1.2 Build Pipeline (`scripts/build_all.py`)

Quy trình build hoàn chỉnh:

```
1. Load raw JSON sources (prowler metadata, maturity model, curated mappings)
2. Optional: Auto-generate mappings via gen_maturity_mapping.py
3. Normalize documents (normalize_prowler_doc, normalize_maturity_doc, normalize_mapping_doc)
4. Persist normalized artifacts (JSON files)
5. Build BM25 indexes per corpus (tokenize → compute IDF → serialize to pickle)
6. Build ChromaDB vector collections per corpus (embed → store)
7. Generate manifest.json (version, counts, paths, timestamps)
```

#### 5.1.3 Mapping Generation (`scripts/gen_maturity_mapping.py`)

Thuật toán auto-generate maturity mappings:

```
For each (check, capability) pair:
  score = 0.0

  # 1. Token overlap
  score += count_overlapping_tokens(check_text, capability_text)

  # 2. Phrase hits
  for phrase in IMPORTANT_PHRASES:
    if phrase in check_text AND phrase in capability_text:
      score += phrase_boost

  # 3. Synonym normalization
  tokens = apply_canonical_synonyms(tokens)  # "bucket" → "storage"

  # 4. Intent alignment
  check_intents = infer_control_families(check_text)
  cap_intents = infer_control_families(capability_text)
  if check_intents ∩ cap_intents:
    score += intent_bonus

  # 5. Product gating
  if capability has product-specific entity (bedrock, sagemaker):
    if check does NOT contain required signals:
      score += product_penalty  # negative

  # 6. Assign confidence
  if score >= high_threshold: confidence = "high"
  elif score >= medium_threshold: confidence = "medium"
  else: confidence = "low"
```

### 5.2 Knowledge Storage Layer

#### 5.2.1 BM25 Lexical Index (`indexing/lexical_index.py`)

**Cấu trúc dữ liệu:**
```python
class BM25Index:
    doc_texts: Dict[str, str]              # doc_id → full text
    doc_metadata: Dict[str, dict]          # doc_id → metadata
    term_freq: Dict[str, Counter]          # doc_id → {token: count}
    doc_freq: Dict[str, int]              # token → document count
    doc_lengths: Dict[str, int]           # doc_id → token count
    check_id_to_doc_id: Dict[str, str]    # O(1) exact lookup
    capability_id_to_doc_ids: Dict[str, List[str]]  # reverse index
```

**Công thức BM25:**

$$BM25(D, Q) = \sum_{q_i \in Q} IDF(q_i) \cdot \frac{f(q_i, D) \cdot (k_1 + 1)}{f(q_i, D) + k_1 \cdot \left(1 - b + b \cdot \frac{|D|}{avgdl}\right)}$$

Trong đó:
- $k_1 = 1.2$ — term frequency saturation (giá trị chuẩn, ngăn term xuất hiện nhiều lần dominate scoring)
- $b = 0.6$ — document length normalization (thấp hơn giá trị mặc định 0.75, phù hợp cho short text documents)
- $IDF(q_i) = \log\left(1 + \frac{N - df + 0.5}{df + 0.5}\right)$ — Inverse Document Frequency

**Tại sao b=0.6?** Prowler checks và maturity capabilities là các documents tương đối ngắn (~100-500 tokens). Giá trị b=0.6 giảm mức phạt cho documents ngắn, giúp chúng không bị penalize quá mức so với documents dài hơn.

#### 5.2.2 Vector Index (`indexing/vector_index.py`)

**Kiến trúc ChromaDB:**
```python
class VectorIndex:
    client: chromadb.PersistentClient     # Persistent storage
    embedding_fn: SentenceTransformerEmbeddingFunction  # all-MiniLM-L6-v2

    def query(name, query_text, top_k, filters):
        collection = client.get_collection(name, embedding_function=embedding_fn)
        results = collection.query(query_texts=[query_text], n_results=top_k)
        # Distance → similarity conversion
        score = 1.0 / (1.0 + distance)  # Euclidean distance normalization
        return [{doc_id, score, metadata, matched_by: ["vector"]}]
```

**Embedding Model Details:**
- Model: `all-MiniLM-L6-v2` (Sentence-Transformers)
- Dimensions: 384
- Size: ~80 MB
- Speed: ~14k sentences/sec (CPU)
- Pretrained trên 1 billion sentence pairs
- Distance metric: Euclidean (L2) — default của ChromaDB

### 5.3 Query Intelligence Layer

#### 5.3.1 Semantic Router (`retrieval/router.py`)

SemanticRouter quyết định **đường đi** của truy vấn qua hệ thống. Đây là component quan trọng vì routing sai sẽ dẫn đến toàn bộ pipeline trả về kết quả không chính xác.

**Thuật toán routing:**

```python
def route(query, explicit_type, provider, service, domain) → RouteDecision:

    # 1. Kiểm tra exact check_id
    if looks_like_check_id(query):
        # Strict: ≥3 underscore parts, first part = known AWS service, length ≥12
        return RouteDecision(
            query_type="check_search",
            exact_check_id=query,
            requires_exact_lookup=True
        )

    # 2. Kiểm tra exact capability_id
    if looks_like_capability_id(query):
        # Conservative: 2-8 underscore parts, no spaces, length 8-100
        return RouteDecision(
            query_type="maturity_search",
            exact_capability_id=query,
            requires_exact_lookup=True
        )

    # 3. Kiểm tra explicit_type từ caller
    if explicit_type == "mapping_resolution":
        return RouteDecision(query_type="mapping_resolution", ...)
    if explicit_type == "maturity_search":
        return RouteDecision(query_type="maturity_search", ...)

    # 4. Infer từ query hints
    maturity_score = count_matches(query, MATURITY_HINT_TERMS)
    check_score = count_matches(query, CHECK_HINT_TERMS)

    if maturity_score > check_score:
        return RouteDecision(query_type="maturity_search", ...)
    else:
        return RouteDecision(query_type="check_search", ...)  # default
```

**Thách thức routing đã gặp:**

Trong quá trình phát triển, một vấn đề lớn được phát hiện: router misclassify natural language queries thành check IDs. Ví dụ, query "prevent_public_access" (4 underscores, ≥12 chars) ban đầu bị nhận nhầm là check_id. Giải pháp: thêm điều kiện strict — part đầu tiên phải thuộc `KNOWN_SERVICES` (29 AWS services trong whitelist).

#### 5.3.2 Intent Detector (`context/intent_detector.py`)

IntentDetector hoạt động ở hai cấp độ:

**Cấp 1 — Query Intent Detection** (9 intents):
```
encryption, public_access, iam, logging, network,
backup, access_control, root, secrets
```

Mỗi intent có danh sách keywords ngắn. Ví dụ intent `encryption`:
```
["encrypt", "kms", "ssl", "tls", "at rest", "in transit", "cmk"]
```

**Cấp 2 — Control Family Inference** (6 families):
```
public_access, encryption_at_rest, encryption_in_transit,
identity_access, logging_monitoring, resilience_backup
```

Mỗi family có danh sách phrases dài hơn, phục vụ cho coverage selection và entity gating.

**Entity Gating (`mapping_passes_entity_gate`):**

Đây là mechanism quan trọng để ngăn false positive mappings. Ví dụ:
- Capability `generative_ai_data_protection_with_amazon_bedrock` chứa entity "bedrock"
- Check `s3_bucket_default_encryption` KHÔNG chứa signal nào liên quan đến Bedrock
- → Gate reject mapping này, ngăn S3 encryption check bị map sang Bedrock capability

```python
PRODUCT_ENTITY_GATES = {
    "bedrock": ["bedrock", "genai", "gen_ai", "generative", "llm", "foundationmodel", ...],
    "sagemaker": ["sagemaker", "ml", "model", "training", "endpoint"],
    "guardduty": ["guardduty", "guard_duty", "threat", "malware"],
    "waf": ["waf", "web_acl", "rate_limit", "sql_injection", "xss"],
    ...  # 11 entities total (bedrock, genai, generative, prompt, sagemaker,
         #   guardduty, macie, inspector, waf, shield, securityhub)
}
```

### 5.4 Retrieval Intelligence Layer

#### 5.4.1 Retrieval Pipeline (`retrieval/pipeline.py` — 869 dòng)

Đây là file lớn nhất và phức tạp nhất trong hệ thống, orchestrate toàn bộ quá trình retrieval.

**Luồng xử lý chính của `retrieve()`:**

```
1. Route query → RouteDecision
2. Dispatch theo query_type:
   ├── mapping_resolution → _resolve_mapping_exact()
   ├── exact check_id → _resolve_check_exact()
   ├── exact capability_id → _resolve_maturity_exact()
   └── semantic query → _hybrid_search()
3. Verify results → warnings
4. Calculate confidence → high/medium/low
5. Build ResponseEnvelope → return
```

**Thuật toán Hybrid Merge (`_merge_results`) — 7 bước:**

```
Bước 1: RRF (Reciprocal Rank Fusion)
  Với mỗi document d xuất hiện trong kết quả:
    rrf_score(d) = Σ 1/(k + rank_i(d))    // k=60, i ∈ {lexical, vector}

  Ý nghĩa: RRF là rank-based fusion, không phụ thuộc vào scale khác nhau
  giữa BM25 scores và cosine similarity. k=60 là giá trị chuẩn trong
  information retrieval literature, đảm bảo top-ranked results đóng góp
  nhiều hơn nhưng không quá dominate.

Bước 2: Tách Exact Matches
  Documents có matched_by chứa "exact" được tách riêng,
  gán bonus score = 2.0 (luôn đứng đầu kết quả)

Bước 3: Product Gate Filter
  Với mỗi candidate:
    if capability chứa product-specific entity (bedrock, sagemaker...):
      if check context KHÔNG chứa required signals:
        → Loại bỏ candidate

  Mục đích: Ngăn false positive mappings giữa unrelated domains

Bước 4: Hydrate Candidates
  Load full document content từ normalized storage
  (BM25 và Chroma chỉ lưu doc_id + metadata nhỏ)

Bước 5: Cross-Encoder Reranking
  Với top-20 candidates:
    raw_score = cross_encoder.predict([(query, passage)])
    normalized_score = sigmoid(raw_score) = 1 / (1 + exp(-raw_score))
  Sort theo normalized_score descending

  Model: ms-marco-MiniLM-L-6-v2 (~22 MB)
  Output range: raw ∈ [-3, +3], sau sigmoid ∈ [0, 1]

Bước 6: Metadata Bonus
  if document.service == query_service: score += 0.03
  if document.domain == query_domain: score += 0.02

  Mục đích: Ưu tiên documents cùng service/domain với query

Bước 7: Combine & Truncate
  Prepend exact matches (luôn đứng đầu)
  Append reranked results
  Truncate to top_k
```

#### 5.4.2 Cross-Encoder Reranker (`retrieval/reranker.py`)

**Tại sao cần Reranker?**

BM25 và vector search đều là **bi-encoder** approaches — query và document được encode độc lập. Cross-encoder thực hiện **joint encoding** — cả query và passage đi qua model cùng lúc, cho phép model học được interaction patterns giữa query tokens và passage tokens.

```python
class CrossEncoderReranker:
    _instance = None  # Singleton (ClassVar)
    _model_name = None

    def rerank(query, candidates, top_n=20):
        pairs = [(query, self._extract_passage(c)) for c in candidates]
        raw_scores = self._model.predict(pairs)
        # Sigmoid normalization → [0, 1]
        scores = 1.0 / (1.0 + np.exp(-np.asarray(raw_scores)))

        for candidate, score in zip(candidates, scores):
            candidate["score"] = float(score)

        candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return candidates[:top_n]
```

**Singleton pattern** đảm bảo model chỉ được load một lần vào memory, tránh overhead khi xử lý nhiều requests.

#### 5.4.3 Result Verification (`retrieval/verifier.py`)

Verification là **quality gate** cuối cùng trước khi trả kết quả. Phân loại warnings thành hai mức:

**Severe warnings** (fail verification, force low confidence):
- `exact_lookup_miss` — Yêu cầu exact match nhưng không tìm thấy
- `exact_lookup_mismatch` — Tìm thấy nhưng doc_id không khớp
- `mapping_missing` — Mapping resolution không có kết quả
- `top1_doc_type_mismatch` — Top-1 result sai doc_type
- `top1_filter_mismatch` — Top-1 result không pass filters

**Moderate warnings** (degrade confidence):
- `service_mismatch_top1` — Top-1 result khác service so với query
- `low_score_top1` — Score < 0.15
- `ambiguous_top_results` — Gap giữa top-1 và top-2 < 0.05
- `weak_domain_alignment` — Domain không phù hợp

#### 5.4.4 Confidence Scoring (`retrieval/confidence.py`)

**Thuật toán đánh giá confidence:**

```
1. Bắt đầu: base_confidence = "low"

2. Kiểm tra exact hit:
   if exact_check_id/exact_mapping/exact_capability_id matched:
     base_confidence = "high"

3. Kiểm tra score thresholds (query-type specific):
   mapping_resolution: high ≥ 0.99
   check_search: high ≥ 0.70, medium ≥ 0.35
   maturity_search: high ≥ 0.60, medium ≥ 0.30
   default: high ≥ 0.65, medium ≥ 0.30

4. Ambiguity penalties:
   if gap(top1 - top2) < 0.10: demote high → medium
   if gap(top1 - top2) < 0.03: demote → low

5. Verification penalties:
   if exact required but missed: demote by 1 level
   if verification failed: confidence = "low"

6. Output: Confidence.high | Confidence.medium | Confidence.low
```

### 5.5 Context Construction Layer

#### 5.5.1 Context Service (`services/context_service.py`)

ContextService là **orchestration layer** điều phối toàn bộ context building pipeline qua 4 giai đoạn:

```
Phase 1: Check Retrieval
  ← Collect check_ids từ request (explicit hoặc từ findings)
  ← Gọi CheckService.retrieve() cho mỗi check_id
  ← Merge results

Phase 2: Mapping Resolution
  ← Extract check_ids từ Phase 1
  ← Gọi MappingService.resolve() cho mỗi check_id
  ← Filter: chỉ giữ approved/reviewed mappings

Phase 3: Maturity Retrieval
  ← Extract capability_ids từ Phase 2
  ← Gọi MaturityService.retrieve() cho mỗi capability_id
  ← Filter: chỉ giữ requested capabilities

Phase 4: Bundle & Context
  ← Aggregate confidence và warnings từ tất cả phases
  ← Gọi ContextBuilder.build()
  ← Return ContextBuildResponse với diagnostics
```

**Error Handling:** Mỗi phase capture exceptions riêng, trả về partial success với warnings. Điều này đảm bảo nếu một phase fail, các phases khác vẫn tiếp tục.

#### 5.5.2 Coverage Selector (`context/coverage_selector.py`)

CoverageSelector quyết định **chọn items nào** dựa trên consumer type:

**Chiến lược cho Planning Agent:**
```
1. Detect active intents từ query (IntentDetector)
   Ví dụ: "prevent public access and encrypt S3"
   → intents = [public_access, encryption]

2. Tính dynamic target:
   target = clamp(n_intents * 2, min=2, max=8)
   → 2 intents * 2 = 4 checks target

3. Multi-pass selection:
   Pass 1: Chọn 1 representative check cho mỗi intent
   Pass 2: Bổ sung checks từ services chưa covered
   Pass 3: Fill remaining bằng highest score
```

**Chiến lược cho Risk Agent:**
```
- Requested checks: primary_finding (luôn đầu tiên)
- Related checks: sorted by score, different service preferred
- Max related: 3 (tránh overwhelming LLM context)
```

**Chiến lược cho Report Agent:**
```
- Key findings: top checks by severity × score
- Control themes: diverse capabilities across domains
- Recommended practices: consolidated, deduped, max 5
```

#### 5.5.3 Bundle Factory (`context/bundle_factory.py`)

BundleFactory tạo payload cụ thể cho từng consumer:

| Field | Planning | Risk | Report |
|-------|----------|------|--------|
| primary_finding | — | Full check details (risk, remediation, severity) | — |
| related_findings | All checks | Supporting checks | — |
| control_mapping | — | check → capability list with confidence | — |
| control_mapping_ids | List of capability IDs | — | — |
| maturity_context | — | Capability summaries | — |
| maturity_capability_ids | List of capability IDs | — | — |
| primary_topics | — | — | Service list |
| key_findings | — | — | Check summaries |
| control_themes | — | — | Capability summaries |
| recommended_practices | — | — | Top 5 practices |

**Confidence Re-evaluation:**

BundleFactory cũng thực hiện **semantic confidence check** — đánh giá lại confidence dựa trên bundle completeness:
- Planning: Kiểm tra coverage so với detected intents
- Risk: Kiểm tra sự hiện diện của mapping và quality
- Report: Validate evidence completeness

### 5.6 Generation Layer

#### 5.6.1 Prompt Formatter (`context/prompt_formatter.py`)

PromptFormatter tạo **PromptReadyContext** gồm 3 phần:

**Header:**
```
[Context for {consumer} agent]
Query: {query}
Confidence: {high|medium|low}
Review recommended: {yes|no}
Warnings: {warning_list}
```

**Evidence Block:**
```
[Requested Checks]
- s3_bucket_level_public_access_block (service: s3): Ensures S3 bucket has public access block...

[Related Checks]
- s3_account_level_public_access_blocks (service: s3): Account-level public access blocks...

[Selected Mappings]
- s3_bucket_level_public_access_block → block_public_access (confidence: high):
  S3 bucket public access block directly enforces...

[Selected Capabilities]
- Block Public Access: Prevent public access to S3 buckets by default...
```

**Guidance Block** (consumer-specific instructions):
- **Planning**: "Use checks to decide which to scan next. Prefer exact/top-ranked matches."
- **Risk**: "Use checks as primary evidence. Use mappings/capabilities as supporting context."
- **Report**: "Use checks as factual evidence. Use mappings/capabilities for control intent and best practices."

---

## 6. Luồng dữ liệu End-to-End

### 6.1 Ví dụ End-to-End: Risk Agent đánh giá S3 Public Access

```
INPUT:
  ContextBuildRequest {
    consumer: "risk",
    query: null,
    check_ids: ["s3_bucket_level_public_access_block"],
    findings: [{check_id: "s3_bucket_level_public_access_block", status: "FAIL"}],
    include_mappings: true,
    include_maturity: true
  }

PHASE 1 — CHECK RETRIEVAL:
  → CheckService.retrieve("s3_bucket_level_public_access_block")
  → SemanticRouter: exact_check_id detected
  → BM25Index exact lookup: O(1)
  → Result: {doc_id: "check:s3_bucket_level_public_access_block", score: 1.0}
  → Confidence: high

PHASE 2 — MAPPING RESOLUTION:
  → MappingService.resolve("s3_bucket_level_public_access_block")
  → Mapping index lookup: [
      {capability_id: "block_public_access", confidence: "high",
       review_status: "approved", mapping_type: "direct"}
    ]
  → Filter: approved ✓
  → Result: best = block_public_access

PHASE 3 — MATURITY RETRIEVAL:
  → MaturityService.retrieve("block_public_access")
  → SemanticRouter: exact_capability_id detected
  → BM25Index exact lookup: O(1)
  → Result: {doc_id: "capability:block_public_access",
             domain: "data_protection", stage: "1 quickwins"}

PHASE 4 — BUNDLE & CONTEXT:
  → ContextBuilder.build(consumer="risk", checks, mappings, capabilities)
  → CoverageSelector: primary = s3_bucket_level_public_access_block
  → BundleFactory.build_risk_bundle():
      primary_finding: {
        check_id: "s3_bucket_level_public_access_block",
        service: "s3",
        severity: "medium",
        risk: "Without S3 bucket level public access blocks...",
        remediation: "Enable bucket level public access blocks..."
      }
      control_mapping: [{
        check_id: "s3_bucket...",
        capability_id: "block_public_access",
        confidence: "high",
        rationale: "S3 bucket public access block directly enforces..."
      }]
      maturity_context: [{
        capability_name: "Block Public Access",
        summary: "Prevent public access to S3 buckets by default...",
        recommended_practices: ["Enable S3 Block Public Access...", ...]
      }]
  → PromptFormatter.format() → PromptReadyContext

OUTPUT:
  ContextBuildResponse {
    consumer: "risk",
    confidence: "high",
    review_recommended: false,
    payload: {risk_bundle: {...}},
    diagnostics: {selected_checks: [...], selected_mappings: [...], ...}
  }
```

### 6.2 Ví dụ End-to-End: Planning Agent — Semantic Query

```
INPUT:
  RetrieveChecksRequest {
    query: "how to prevent s3 buckets from being publicly exposed",
    top_k: 5,
    retrieval_mode: "hybrid"
  }

PHASE 1 — QUERY INTELLIGENCE:
  → normalize_query(): "how to prevent s3 buckets from being publicly exposed"
  → SemanticRouter.route():
    - looks_like_check_id? NO (contains spaces)
    - extract_service(): "s3" (known service detected)
    - query_type: "check_search"
    - filters: {service: "s3"}
  → IntentDetector.detect_query_intents(): ["public_access"]

PHASE 2 — PARALLEL RETRIEVAL:
  → BM25Index.query("prevent s3 bucket publicly exposed", top_k=15):
    Tokens: ["prevent", "s3", "bucket", "public", "expos"]  (after stemming)
    Results: [
      {doc_id: "check:s3_bucket_level_public_access_block", score: 8.2},
      {doc_id: "check:s3_account_level_public_access_blocks", score: 7.8},
      {doc_id: "check:s3_bucket_public_access", score: 6.5},
      ...
    ]
    (aliases "public access", "prevent public exposure" boost these results)

  → VectorIndex.query(same query, top_k=15):
    Embedding: all-MiniLM-L6-v2 encodes to 384-dim vector
    Results: [
      {doc_id: "check:s3_bucket_level_public_access_block", score: 0.72},
      {doc_id: "check:s3_bucket_public_access", score: 0.68},
      {doc_id: "check:s3_bucket_policy_public_write_access", score: 0.61},
      ...
    ]

PHASE 3 — MERGE & RERANK:
  → RRF Merge (k=60):
    s3_bucket_level_public_access_block:
      rrf = 1/(60+1) + 1/(60+1) = 0.0328  (rank 1 in both)
    s3_account_level_public_access_blocks:
      rrf = 1/(60+2) + 1/(60+4) = 0.0318
    ...

  → Product Gate: all candidates pass (no product-specific entities)

  → CrossEncoderReranker.rerank(query, top-20):
    Pairs: [(query, passage1), (query, passage2), ...]
    Raw scores: [2.1, 1.8, 1.5, ...]
    Sigmoid: [0.89, 0.86, 0.82, ...]
    Final ranking matches expectation

  → Metadata Bonus:
    service=s3 match: +0.03 for all S3 checks

PHASE 4 — VERIFICATION & CONFIDENCE:
  → verify_retrieval():
    - top1_service = "s3" ✓ (matches query service)
    - top1_doc_type = "prowler_check" ✓
    - No severe warnings
    - valid = True

  → calculate_confidence():
    - top1_score = 0.92 (after rerank) > 0.70 → high
    - ambiguity_gap = 0.92 - 0.89 = 0.03 < 0.10 → demote to medium
    - Final: Confidence.medium

OUTPUT:
  ResponseEnvelope {
    status: "ok",
    data: [
      {doc_id: "check:s3_bucket_level_public_access_block", score: 0.92, ...},
      {doc_id: "check:s3_account_level_public_access_blocks", score: 0.89, ...},
      {doc_id: "check:s3_bucket_public_access", score: 0.85, ...},
      ...
    ],
    meta: {confidence: "medium", review_recommended: false, ...}
  }
```

---

## 7. Những điểm quan trọng trong quá trình Implementation

### 7.1 Quyết định thiết kế quan trọng

#### 7.1.1 Hybrid Retrieval thay vì Single-Method

**Vấn đề**: Lexical search (BM25) mạnh với exact terms nhưng yếu với paraphrase. Vector search mạnh về semantic nhưng yếu với exact IDs và technical terms.

**Giải pháp**: Kết hợp cả hai bằng RRF (Reciprocal Rank Fusion).

**Kết quả đo được**:
- Exact queries: Top-1 accuracy 100% (18/18) — BM25 xử lý tốt
- Paraphrase queries: Top-3 accuracy 100% (9/9) — Vector search bổ trợ
- Semantic hard queries: Top-1 chỉ 12.5% (1/8) — vẫn là thách thức

#### 7.1.2 Externalized Scoring Configuration

**Vấn đề**: Cần tune nhiều tham số (RRF k, confidence thresholds, metadata bonuses) nhưng mỗi lần tune phải sửa code và redeploy.

**Giải pháp**: `scoring_config.json` externalize tất cả tham số. Hỗ trợ `reload_scoring_config()` để hot-reload.

```json
{
  "rrf": { "k": 60 },
  "exact_match_bonus": 2.0,
  "metadata_bonus": { "service_match": 0.03, "domain_match": 0.02 },
  "reranker": { "enabled": true, "model": "cross-encoder/ms-marco-MiniLM-L-6-v2", "top_n": 20 },
  "confidence_thresholds": {
    "check_search": { "high": 0.70, "medium": 0.35 },
    "maturity_search": { "high": 0.60, "medium": 0.30 }
  },
  "ambiguity": { "gap_high_to_medium": 0.10, "gap_to_low": 0.03 },
  "verification": { "ambiguity_threshold": 0.05, "low_score_threshold": 0.15 }
}
```

#### 7.1.3 Consumer-Aware Context thay vì One-Size-Fits-All

**Vấn đề**: Ba loại agent cần context rất khác nhau từ cùng một knowledge base.

**Giải pháp**: CoverageSelector + BundleFactory + PromptFormatter tạo pipeline context riêng cho mỗi consumer, trong khi chia sẻ chung retrieval pipeline.

**Ưu điểm**: Một retrieval call có thể phục vụ nhiều consumers, giảm duplicate computation.

#### 7.1.4 Product Entity Gating

**Vấn đề phát hiện trong benchmark**: S3 encryption check bị map sang "generative_ai_data_protection_with_amazon_bedrock" capability — một false positive nghiêm trọng vì Bedrock và S3 là domains hoàn toàn khác nhau.

**Giải pháp**: `PRODUCT_ENTITY_GATES` (11 entities) kiểm tra sự hiện diện của product-specific keywords trong cả capability và check. Nếu capability chứa "bedrock" nhưng check context không có signal nào liên quan → reject mapping.

**Kết quả**: Forbidden capability rate = 0% trên toàn bộ benchmark (60 cases).

### 7.2 Khó khăn gặp phải và cách giải quyết

#### 7.2.1 Embedding Model Mismatch

**Khó khăn**: Ban đầu config.py khai báo `intfloat/multilingual-e5-base` nhưng ChromaDB sử dụng default embedding function khác. Dẫn đến query-time và build-time embeddings không nhất quán.

**Giải quyết** (Slice 1 trong Optimization Plan):
- Đổi sang `all-MiniLM-L6-v2` — model nhỏ gọn, nhanh, phù hợp cho domain English-only
- Truyền explicit `SentenceTransformerEmbeddingFunction` vào cả `create_collection()` và `get_collection()`
- Kết quả: Checks Top-5 accuracy tăng từ 65% → 75% (+10%)

#### 7.2.2 Query Routing False Positives

**Khó khăn**: `looks_like_check_id()` ban đầu quá lỏng lẻo, natural language queries có underscore (ví dụ "prevent_public_access") bị nhận nhầm là check_id, dẫn đến exact lookup thất bại.

**Giải quyết**:
- Thêm constraint: part đầu tiên phải thuộc `KNOWN_SERVICES` (29 AWS services)
- Thêm minimum length: ≥12 characters
- Thêm minimum parts: ≥3 underscore-separated parts

#### 7.2.3 BM25 Không Hoạt Động cho Maturity Corpus

**Khó khăn** (phát hiện qua Tuning report): Maturity queries trả về Top-1 = 0% ban đầu. Nguyên nhân: BM25 index cho maturity corpus bị lỗi canonicalization (snake_case vs kebab-case).

**Giải quyết**:
- Chuẩn hóa tất cả capability IDs sang snake_case
- Rebuild BM25 index với text đã chuẩn hóa
- Kết quả: Maturity Top-1 tăng từ 0% → 89.5%

#### 7.2.4 Latency Vượt Ngưỡng

**Khó khăn**: Average latency 2.1-2.9s vượt ngưỡng release criteria 2000ms.

**Nguyên nhân phân tích**:
- Cold start: Model loading lần đầu (~500ms cho embedding, ~300ms cho cross-encoder)
- Cross-encoder reranking: ~100ms cho 20 candidates
- Parallel BM25 + Vector search: ~800ms
- Context hydration: ~200ms

**Giải pháp tiềm năng** (chưa implement):
- Pre-warm models during startup
- Cache frequently queried results
- Reduce cross-encoder candidate pool (20 → 10)
- Optimize ChromaDB query parameters

### 7.3 Các phần hoạt động tốt

1. **Exact Lookup Path**: 100% accuracy (18/18 cases), latency thấp nhất
2. **Product Entity Gating**: 0% forbidden capability rate — không có false positive nào lọt qua
3. **Semantic Aliases**: Giúp BM25 match natural language queries với technical check IDs
4. **Graceful Degradation**: Hệ thống vẫn hoạt động khi vector search down, lexical-only mode tự động kích hoạt
5. **Consumer-Specific Bundles**: S3 Agent Readiness benchmark đạt 100% pass rate cho cả 3 consumers (planning, risk, report)
6. **Comprehensive Diagnostics**: Mọi response đều chứa diagnostics đầy đủ, giúp debug và improve

---

## 8. Đánh giá chất lượng truy vấn và Benchmark

### 8.1 Phương pháp đánh giá

Hệ thống sử dụng **benchmark-driven evaluation** với hai cấp độ:

**Cấp 1 — Retrieval Benchmark** (60 cases):
- Đánh giá chất lượng truy vấn thuần túy (retrieval accuracy)
- 41 check cases + 19 maturity cases
- 4 độ khó: exact, paraphrase, risk, semantic_hard
- 6 AWS services: S3, IAM, EC2, RDS, CloudTrail, KMS

**Cấp 2 — Agent Readiness Benchmark** (9 cases, S3-focused):
- Đánh giá chất lượng context cho từng agent consumer
- 3 planning + 3 risk + 3 report cases
- Metrics: check hit rate, capability hit rate, bundle completeness, forbidden rate

### 8.2 Release Criteria

| Metric | Ngưỡng | Ý nghĩa |
|--------|--------|---------|
| Checks Top-1 Accuracy | ≥ 60% | Kết quả đầu tiên phải đúng ít nhất 60% |
| Checks Top-5 Accuracy | ≥ 80% | Kết quả đúng phải nằm trong top 5 ít nhất 80% |
| Maturity Top-1 Accuracy | ≥ 60% | Tương tự cho maturity queries |
| Maturity Top-5 Accuracy | ≥ 80% | Tương tự cho maturity queries |
| Forbidden Capability Rate | = 0% | Không chấp nhận false positive mapping |
| Service Precision | ≥ 85% | Top-1 result phải đúng service |
| Average Latency | ≤ 2000ms | Thời gian phản hồi tối đa |
| Empty Bundle Rate | = 0% | Không chấp nhận bundle rỗng |

### 8.3 Kết quả Benchmark

#### 8.3.1 Retrieval Benchmark — Checks (41 cases)

| Metric | Kết quả | Release Criteria | Đánh giá |
|--------|---------|-----------------|----------|
| HTTP 200 Rate | 100% (41/41) | — | ✅ |
| **Hit@1** | **65.85%** (27/41) | ≥ 60% | ✅ PASS |
| **Hit@3** | **80.49%** (33/41) | — | — |
| **Hit@5** | **85.37%** (35/41) | ≥ 80% | ✅ PASS |
| Service Precision | 87.80% (36/41) | ≥ 85% | ✅ PASS |
| Forbidden Capability Rate | 0% | = 0% | ✅ PASS |
| Average Latency | 2798.92 ms | ≤ 2000ms | ❌ FAIL |

**Phân tích theo category:**

| Category | Cases | Top-1 | Top-3 | Top-5 | Avg Latency |
|----------|-------|-------|-------|-------|-------------|
| **exact** | 18 | **100%** (18/18) | 100% | 100% | 2571 ms |
| **paraphrase** | 9 | **55.6%** (5/9) | 100% | 100% | 2924 ms |
| **risk** | 6 | **33.3%** (2/6) | 66.7% | 66.7% | 2962 ms |
| **semantic_hard** | 8 | **12.5%** (1/8) | 25% | 25% | 3048 ms |

**Nhận xét**:
- Exact queries đạt 100% — lexical exact lookup hoạt động hoàn hảo
- Paraphrase: Top-1 thấp (55.6%) nhưng Top-3/5 = 100% — kết quả đúng luôn nằm trong top results nhưng không phải ở vị trí số 1
- Semantic hard: Chỉ 12.5% Top-1 — đây là điểm yếu lớn nhất, model embedding chưa đủ khả năng capture deep semantic similarity

#### 8.3.2 Retrieval Benchmark — Maturity (19 cases)

| Metric | Kết quả | Release Criteria | Đánh giá |
|--------|---------|-----------------|----------|
| HTTP 200 Rate | 100% (19/19) | — | ✅ |
| **Hit@1** | **73.68%** (14/19) | ≥ 60% | ✅ PASS |
| **Hit@3** | **89.47%** (17/19) | — | — |
| **Hit@5** | **100%** (19/19) | ≥ 80% | ✅ PASS |
| Forbidden Capability Rate | 0% | = 0% | ✅ PASS |
| Average Latency | 2889 ms | ≤ 2000ms | ❌ FAIL |

**Phân tích theo category:**

| Category | Cases | Top-1 | Top-3 | Top-5 |
|----------|-------|-------|-------|-------|
| **exact** | 7 | **100%** (7/7) | 100% | 100% |
| **paraphrase** | 6 | **100%** (6/6) | 100% | 100% |
| **semantic_hard** | 6 | **16.7%** (1/6) | 66.7% | 100% |

**Nhận xét**: Maturity queries có kết quả tốt hơn checks overall. Đặc biệt paraphrase đạt 100% Top-1 — có thể do maturity capabilities có text mô tả phong phú hơn, giúp cả BM25 và vector search match tốt hơn.

#### 8.3.3 Combined Summary

| Metric | Kết quả | Criteria | Verdict |
|--------|---------|----------|---------|
| Combined Top-1 | **68.33%** (41/60) | ≥ 60% | ✅ PASS |
| Combined Top-5 | **90.00%** (54/60) | ≥ 80% | ✅ PASS |
| Checks Top-1 | 65.85% | ≥ 60% | ✅ PASS |
| Checks Top-5 | 85.37% | ≥ 80% | ✅ PASS |
| Maturity Top-1 | 73.68% | ≥ 60% | ✅ PASS |
| Maturity Top-5 | 100% | ≥ 80% | ✅ PASS |
| Forbidden Rate | 0% | = 0% | ✅ PASS |
| Service Precision | 87.80% | ≥ 85% | ✅ PASS |
| **Average Latency** | **2144 ms** | ≤ 2000ms | ❌ FAIL |

**Release Verdict: FAIL** (chỉ vì latency vượt ngưỡng 144ms)

#### 8.3.4 Agent Readiness Benchmark — S3 (9 cases)

| Consumer | Cases | Check Hit Rate | Capability Hit Rate | Service Precision | Forbidden Rate | Avg Latency |
|----------|-------|---------------|--------------------|--------------------|----------------|-------------|
| **Planning** | 3 | 100% ✅ | 100% ✅ | 100% ✅ | 0% ✅ | 1578 ms |
| **Risk** | 3 | 100% ✅ | 100% ✅ | 100% ✅ | 0% ✅ | 1581 ms |
| **Report** | 3 | 100% ✅ | 100% ✅ | 100% ✅ | 0% ✅ | 1284 ms |

**Consumer Readiness: ALL READY** — Cả 3 consumers đều đạt tiêu chuẩn cho S3 use case.

#### 8.3.5 Cải thiện qua thời gian

So sánh hai lần chạy benchmark:

| Metric | Baseline (08:55) | Current (09:14) | Thay đổi |
|--------|-----------------|-----------------|---------|
| Combined Top-1 | 65.00% | 68.33% | **+3.33%** ↑ |
| Combined Top-5 | 88.33% | 90.00% | **+1.67%** ↑ |
| Service Precision | 85.40% | 87.80% | **+2.40%** ↑ |
| Avg Latency | 2060 ms | 2144 ms | +84 ms ↓ |

### 8.4 Phân tích lỗi chi tiết

#### Trường hợp thất bại tiêu biểu:

**1. Semantic Hard — Check Search:**
- Query: "make object storage private by default"
- Expected: `s3_bucket_level_public_access_block`
- Actual Top-1: `s3_bucket_default_encryption` (sai — encryption ≠ privacy)
- Phân tích: Từ "default" gây nhiễu, BM25 match "default" với "default_encryption". Vector search cũng không đủ phân biệt "private" vs "encrypted".

**2. Risk — Check Search:**
- Query: "misconfiguration that allows public reads on cloud storage"
- Expected: `s3_bucket_public_access`
- Actual Top-1: `s3_bucket_object_lock` (sai)
- Phân tích: Query không chứa keyword "s3" trực tiếp, dùng "cloud storage" — BM25 không match. Vector search match "public reads" nhưng reranker ưu tiên candidate khác.

**3. Semantic Hard — Maturity Search:**
- Query: "ensure compliance monitoring across accounts"
- Expected: `audit_api_calls`
- Actual Top-1: `centralized_security_monitoring` (gần đúng nhưng không match expected)
- Phân tích: Cả hai capabilities đều liên quan đến monitoring, nhưng "compliance" gần hơn với "centralized_security" trong vector space.

---

## 9. Phân tích điểm mạnh và điểm yếu

### 9.1 Điểm mạnh

| Điểm mạnh | Chi tiết | Bằng chứng |
|-----------|----------|-----------|
| **Hybrid Retrieval** | Kết hợp lexical + vector + reranking, cover nhiều loại query | Top-1: 100% exact, 55.6% paraphrase, Top-5: 90% overall |
| **Zero False Positives** | Product Entity Gating ngăn hoàn toàn mapping sai domain | Forbidden capability rate = 0% (60/60 cases) |
| **Graceful Degradation** | Vector fail → lexical-only, mapping fail → partial success | Readiness checks: lexical_ready, vector_ready, hybrid_ready |
| **Consumer-Aware Design** | 3 consumers, 3 bundle types, 3 selection strategies | Agent readiness: 100% pass rate cho cả 3 consumers |
| **Deterministic Ranking** | `mapping_sort_key()` đảm bảo kết quả reproducible | Stable sort trên review_status → confidence → score → id |
| **Comprehensive Diagnostics** | Mọi response có verification, confidence, warnings | Debug-friendly, benchmark-driven improvement |
| **Externalized Configuration** | scoring_config.json cho phép tune không sửa code | A/B testing possible, hot-reload supported |

### 9.2 Điểm yếu

| Điểm yếu | Chi tiết | Tác động |
|-----------|----------|---------|
| **Semantic Hard Accuracy** | Top-1 chỉ 12.5% cho check semantic_hard queries | Người dùng hỏi bằng ngôn ngữ tự nhiên phức tạp sẽ không nhận được kết quả tốt nhất ở vị trí đầu tiên |
| **Latency** | 2144ms trung bình, vượt ngưỡng 2000ms | Chưa đạt release criteria, ảnh hưởng trải nghiệm real-time |
| **Auto-Generated Mappings** | 502 mappings tạo bằng heuristics, chưa review hết | Có thể chứa false positives ở services ngoài S3 |
| **Single Embedding Model** | all-MiniLM-L6-v2 là model nhỏ, 384 dims | Hạn chế khả năng semantic understanding cho complex queries |
| **No Learning-to-Rank** | Ranking dùng heuristic bonuses, không có trained model | Các bonus (service_match: 0.03, domain_match: 0.02) được tune thủ công |
| **Service Precision Marginal** | 87.8% chỉ vượt ngưỡng 85% một chút | Có thể fail nếu thêm services phức tạp hơn |

### 9.3 Cơ hội cải thiện

1. **Upgrade Embedding Model**: Chuyển sang model lớn hơn (ví dụ: `bge-base-en-v1.5`, 768 dims) để improve semantic understanding
2. **Query Expansion**: Tự động mở rộng query bằng synonyms hoặc LLM rewriting trước khi search
3. **Learning-to-Rank**: Train model ranking riêng trên benchmark data thay vì dùng heuristic bonuses
4. **Caching Layer**: Cache results cho frequent queries, giảm latency
5. **Model Pre-warming**: Load models during startup thay vì lazy loading
6. **Curated Mappings**: Mở rộng manual review cho mappings ngoài S3
7. **Batch Retrieval**: Support batch queries trong ContextService, giảm round trips

---

## 10. Kết luận và hướng phát triển

### 10.1 Kết luận

Hệ thống RAG đã được thiết kế và triển khai thành công với kiến trúc **5 tầng rõ ràng** (Knowledge Engineering → Knowledge Storage → Query Intelligence → Retrieval Intelligence → Context Construction → Generation), tuân theo nguyên tắc **Separation of Concerns** và **Graceful Degradation**.

**Những thành tựu chính:**
- **Kiến trúc layered, modular**: Mỗi thành phần có thể phát triển và test độc lập
- **Hybrid Retrieval Pipeline**: Kết hợp BM25 + Vector + Cross-encoder Reranking, đạt 90% Top-5 accuracy trên 60 test cases
- **Zero false positive mappings**: Product Entity Gating ngăn hoàn toàn mapping sai domain
- **Consumer-Aware Context Building**: Phục vụ 3 loại agent với context tối ưu, đạt 100% agent readiness cho S3 use case
- **Benchmark-driven development**: 60 retrieval cases + 9 agent readiness cases + automated release criteria evaluation

**Hạn chế còn tồn tại:**
- Semantic hard queries chưa đạt accuracy cao (12.5% Top-1 cho checks)
- Latency vượt ngưỡng release criteria (~144ms)
- Auto-generated mappings cần review thêm cho services ngoài S3

### 10.2 Hướng phát triển

Dựa trên **Optimization Plan** đã lập, hệ thống sẽ tiếp tục phát triển theo 4 giai đoạn:

| Giai đoạn | Mục tiêu | Metrics kỳ vọng |
|-----------|----------|-----------------|
| **Phase 1: Data Foundation** (Completed) | Fix embedding model, canonicalization | ✅ Checks Top-5: 65% → 85% |
| **Phase 2: Retrieval Quality** | Improve semantic search, query expansion | Target: Top-1 ≥ 75% |
| **Phase 3: Code Cleanup** | Refactor, remove duplication, optimize | Target: Latency ≤ 1500ms |
| **Phase 4: Evaluation Loop** | Continuous benchmark, more test cases | Target: 100+ cases, more services |

### 10.3 Đóng góp về mặt học thuật

Hệ thống RAG này đóng góp vào lĩnh vực nghiên cứu qua các điểm:

1. **Thiết kế kiến trúc RAG production-grade** cho domain bảo mật AWS — một ứng dụng cụ thể và thực tế của RAG system
2. **Consumer-Aware Context Construction** — phương pháp xây dựng context khác nhau cho các agents khác nhau từ cùng một knowledge base
3. **Product Entity Gating** — kỹ thuật domain-specific filtering ngăn false positive mappings giữa các product domains
4. **Benchmark-driven RAG evaluation framework** — hệ thống đánh giá toàn diện từ retrieval accuracy đến agent readiness
5. **Hybrid Retrieval với RRF + Cross-encoder** — implementation thực tế của state-of-the-art retrieval pipeline với detailed performance analysis

---

## PHỤ LỤC

### A. Bảng viết tắt

| Viết tắt | Đầy đủ |
|----------|--------|
| RAG | Retrieval-Augmented Generation |
| BM25 | Best Matching 25 (thuật toán ranking) |
| RRF | Reciprocal Rank Fusion |
| IDF | Inverse Document Frequency |
| DI | Dependency Injection |
| LLM | Large Language Model |

### B. Tham số hệ thống

| Tham số | Giá trị | Ý nghĩa |
|---------|---------|---------|
| BM25 k1 | 1.2 | Term frequency saturation |
| BM25 b | 0.6 | Document length normalization |
| RRF k | 60 | Rank fusion parameter |
| Exact match bonus | 2.0 | Score bonus cho exact matches |
| Service match bonus | 0.03 | Score bonus cho cùng service |
| Domain match bonus | 0.02 | Score bonus cho cùng domain |
| Reranker top_n | 20 | Số candidates cho cross-encoder |
| Embedding dims | 384 | Số chiều vector embedding |
| Check confidence high | ≥ 0.70 | Ngưỡng high confidence cho checks |
| Check confidence medium | ≥ 0.35 | Ngưỡng medium confidence cho checks |
| Maturity confidence high | ≥ 0.60 | Ngưỡng high confidence cho maturity |
| Ambiguity gap (high→medium) | < 0.10 | Nếu gap nhỏ hơn → demote confidence |
| Ambiguity gap (→low) | < 0.03 | Nếu gap nhỏ hơn → confidence = low |

### C. API Endpoints

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/health` | GET | Health check cơ bản |
| `/ready` | GET | Readiness probe (lexical, vector, mapping, hybrid) |
| `/build-info` | GET | Build information và readiness details |
| `/v1/retrieve/checks` | POST | Tìm kiếm prowler checks |
| `/v1/retrieve/maturity` | POST | Tìm kiếm maturity capabilities |
| `/v1/resolve/mapping` | POST | Resolve check → capability mapping |
| `/v1/context/build` | POST | Build context cho agent consumer |
