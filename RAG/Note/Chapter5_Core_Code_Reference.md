# Chương 5 — Core Code Reference cho Báo cáo

> File này ghi lại các đoạn code cốt lõi, dùng làm tài liệu tham khảo khi viết Chương 5.
> Mỗi đoạn code đã được rút gọn, chỉ giữ logic quan trọng nhất.

---

## 5.1 Tổng quan hiện thực

### 5.1.1 Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| Backend / API | FastAPI |
| Vector Database | ChromaDB (PersistentClient) |
| Lexical Search | BM25 (tự hiện thực) |
| Embedding | SentenceTransformer |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| Language | Python 3.x |

### 5.1.2 Kiến trúc triển khai

RAG service là module độc lập, giao tiếp với agent system qua REST API (FastAPI).
Service stack: `API Router → Service Layer → Retrieval Pipeline → Index Layer`

### 5.1.3 Luồng xử lý thực tế

```
Request → Router (phân loại query)
       → Parallel Retrieve (BM25 + Vector)
       → Merge (RRF) → Rerank (Cross-Encoder)
       → Mapping Resolution → Context Bundle
       → Response
```

---

## 5.2 Hiện thực xử lý dữ liệu (Offline Pipeline)

### 5.2.1 Chuẩn hóa dữ liệu (Normalization)

Hệ thống nhận 3 loại dữ liệu thô: Prowler checks, maturity capabilities, và mappings. Mỗi loại được chuẩn hóa qua pipeline chung:

```python
# File: RAG/app/ingestion/normalizers.py

# Pipeline chuẩn hóa text: Unicode NFKC → lowercase → clean whitespace
def normalize_query(text: str) -> str:
    return _normalize_for_index(text).lower()

# Chuẩn hóa identifier: "Data-Encryption" → "data_encryption"
def _normalize_identifier(value) -> str:
    # ... lowercase, replace hyphens/spaces with underscores, strip special chars ...
```

**Stopwords** — Loại bỏ từ không mang ý nghĩa phân biệt:

```python
_ENGLISH_STOPWORDS = frozenset(nltk_stopwords.words("english"))
_AWS_STOPWORDS = frozenset({
    "aws", "amazon", "service", "resource", "resources",
    "configuration", "setting", "ensure", "check", "account",
})
_STOPWORDS = _ENGLISH_STOPWORDS | _AWS_STOPWORDS
```

**Chuẩn hóa Prowler check** — Ví dụ cho 1 loại document:

```python
def normalize_prowler_doc(raw: dict) -> ProwlerCheckDoc:
    check_id = _normalize_identifier(raw.get("CheckID"))
    service = normalize_service(raw.get("ServiceName"))
    title = _normalize_for_index(raw.get("CheckTitle", ""))
    description = _normalize_for_index(raw.get("Description", ""))
    # ... các field khác tương tự ...

    # Tạo retrieval_text (text chính dùng cho indexing)
    retrieval_text = build_retrieval_text_prefixed([
        ("check", check_id),
        ("service", service),
        ("title", title),
        ("description", description),
        ("risk", risk),
        ("recommendation", recommendation_text),
        ("keywords", " ".join(enriched_keywords)),
        ("aliases", alias_text),
    ])
    return ProwlerCheckDoc(doc_id=f"check:{check_id}", ..., retrieval_text=retrieval_text)
```

> **Lưu ý**: `build_retrieval_text_prefixed()` tạo text có tiền tố field name (VD: `"check: s3_bucket_public_read_acl\nservice: s3\n..."`), giúp embedding model hiểu ngữ cảnh từng phần tốt hơn so với nối chuỗi đơn thuần.

### 5.2.2 Tạo metadata và cấu trúc document

Mỗi normalized document được chuyển thành **index document** — cấu trúc thống nhất cho cả BM25 và vector:

```python
# File: RAG/scripts/build_all.py

def _to_index_doc(doc: Dict) -> Dict:
    return {
        "doc_id": doc["doc_id"],           # VD: "check:s3_bucket_public_read_acl"
        "text": _document_text(doc),        # retrieval_text (text chính cho indexing)
        "metadata": {
            "doc_type": doc.get("doc_type"),      # "prowler_check" | "maturity_capability" | "maturity_mapping"
            "provider": doc.get("provider"),       # "aws"
            "service": doc.get("service"),         # VD: "s3"
            "domain": doc.get("domain"),           # VD: "Data Protection"
            "capability_id": doc.get("capability_id"),
            "check_id": doc.get("check_id"),
            "index_version": doc.get("index_version"),
            # ...
        },
    }
```

> **Vai trò metadata**: Được dùng làm **filter** khi truy vấn (VD: chỉ tìm checks thuộc service "s3"), và cung cấp thông tin ngữ cảnh cho reranking/scoring.

Ba corpus document types:

| doc_type | doc_id format | Ví dụ |
|---|---|---|
| `prowler_check` | `check:{check_id}` | `check:s3_bucket_public_read_acl` |
| `maturity_capability` | `capability:{capability_id}` | `capability:encryption_in_transit` |
| `maturity_mapping` | `mapping:{check_id}:{capability_id}` | `mapping:s3_bucket_public_read_acl:encryption_in_transit` |

### 5.2.3 Xây dựng chỉ mục BM25

**Tokenization** — Pipeline đồng nhất giữa build-time và query-time:

```python
# File: RAG/app/ingestion/normalizers.py

def tokenize(text: str, use_stemming=True) -> List[str]:
    normalized = normalize_query(text)                           # lowercase + clean
    raw_tokens = re.split(r"[^a-z0-9_]+", normalized)          # split on non-alphanumeric
    filtered = [tok for tok in raw_tokens if tok not in _STOPWORDS]  # remove stopwords
    if use_stemming:
        filtered = [_stemmer.stem(tok) for tok in filtered]     # Snowball stemmer
    return [tok for tok in filtered if tok]
```

**Build index** — Gọi từ build script:

```python
# File: RAG/scripts/build_all.py

def _build_bm25_for_corpus(corpus_name, docs):
    bm25 = BM25Index(k1=1.5, b=0.75)
    bm25.add_documents(docs)            # tokenize + build TF/DF tables
    bm25.save(output_path)              # serialize bằng pickle
```

> BM25 index lưu dưới dạng pickle file, load lại khi server khởi động. Mỗi corpus có 1 index riêng.

### 5.2.4 Xây dựng vector index

```python
# File: RAG/app/indexing/vector_index.py — class VectorIndex

def build_collection(self, name, docs):
    ids, documents, metadatas = [], [], []
    for doc in docs:
        ids.append(doc["doc_id"])
        documents.append(doc["text"])                # retrieval_text → sẽ được embed
        metadatas.append(self._normalize_metadata(doc["metadata"]))

    collection = self.client.create_collection(
        name=name,
        embedding_function=self._embedding_fn         # SentenceTransformer
    )
    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    # ChromaDB tự động embed documents khi add
```

> ChromaDB quản lý embedding nội bộ — khi `add()`, text được embed bởi `SentenceTransformerEmbeddingFunction` và lưu vào persistent storage. Mỗi corpus tương ứng 1 Chroma collection.

### 5.2.5 Orchestration — Luồng build tổng thể

```python
# File: RAG/scripts/build_all.py — main()

def main():
    # 1) Normalize tất cả corpora
    prowler, maturity, mapping = _normalize_all()
    #    → normalize_prowler_doc(), normalize_maturity_doc(), normalize_mapping_doc()

    # 2) Validate document integrity (unique doc_ids)
    # 3) Persist normalized JSON artifacts

    # 4) Chuyển thành index documents
    index_docs = {corpus: [_to_index_doc(d) for d in docs] for corpus, docs in ...}

    # 5) Build BM25 per corpus → pickle files
    # 6) Build vector collections per corpus → ChromaDB
    # 7) Write manifest (index registry + stats)
```

**Output directory structure**:

```
data/
├── raw/                            ← Dữ liệu thô
│   ├── prowler_checks.json
│   ├── maturity_capabilities.json
│   └── maturity_mappings.json
├── normalized/                     ← Đã chuẩn hóa
│   ├── prowler_checks.json
│   ├── maturity_capabilities.json
│   └── maturity_mappings.json
└── indexes/                        ← Chỉ mục
    ├── bm25/
    │   ├── bm25_prowler_checks.pkl
    │   ├── bm25_maturity_capabilities.pkl
    │   └── bm25_maturity_mappings.pkl
    ├── chroma/                     ← Vector DB
    └── manifest.json               ← Index registry
```

---

## 5.3 Hiện thực Pipeline truy hồi

### 5.3.1 Truy hồi BM25

**Indexing** — Xây dựng inverted index từ documents:

```python
# File: RAG/app/indexing/lexical_index.py — class BM25Index

def build(self, docs: List[Dict]) -> None:
    for doc in docs:
        text = doc.get("text", "")
        tokens = tokenize(text)
        self.doc_lengths[doc_id] = len(tokens)
        tf = Counter(tokens)                  # term frequency
        self.term_freq[doc_id] = tf
        for term in tf:
            self.doc_freq[term] += 1          # document frequency

    self.N = len(self.doc_texts)
    self.avgdl = total_length / self.N        # average document length
```

**Scoring** — Công thức BM25 (k1=1.5, b=0.75):

```python
def _idf(self, term: str) -> float:
    df = self.doc_freq.get(term, 0)
    return math.log(1 + (self.N - df + 0.5) / (df + 0.5))

def _score(self, query_terms: List[str], doc_id: str) -> float:
    score = 0.0
    # ... lấy tf, dl cho doc_id ...
    for term in query_terms:
        f = tf.get(term, 0)
        idf = self._idf(term)
        denom = f + self.k1 * (1 - self.b + self.b * (dl / self.avgdl))
        score += idf * ((f * (self.k1 + 1)) / denom)
    return score
```

### 5.3.2 Truy hồi Vector

**Khởi tạo ChromaDB + Embedding**:

```python
# File: RAG/app/indexing/vector_index.py — class VectorIndex

def __init__(self, persist_dir, embedding_model):
    self._embedding_fn = SentenceTransformerEmbeddingFunction(
        model_name=self.embedding_model
    )
    self.client = chromadb.PersistentClient(path=str(self.persist_dir))
```

**Query** — Truy vấn vector similarity:

```python
def query(self, name, query_text, top_k, filters):
    collection = self.get_collection(name)
    where = self._build_where(filters)      # metadata filter → Chroma $eq/$and

    raw = collection.query(
        query_texts=[query_text],            # Chroma tự embed query
        n_results=top_k,
        where=where,
    )
    # Chuyển distance → score
    # ...
    return [{"doc_id": ..., "score": self._distance_to_score(dist), ...}]

@staticmethod
def _distance_to_score(distance):
    return 1.0 / (1.0 + float(distance))    # distance thấp → score cao
```

### 5.3.3 Hybrid Retrieval

**Song song hóa BM25 + Vector**:

```python
# File: RAG/app/retrieval/pipeline.py — class RetrievalPipeline

# Chạy song song 2 nhánh truy hồi
with ThreadPoolExecutor(max_workers=2) as executor:
    lex_future = executor.submit(self._run_lexical, route, top_k)
    vec_future = executor.submit(self._run_vector, route, top_k)
    lexical_results = lex_future.result()
    vector_results = vec_future.result()

# Merge bằng RRF
merged = self._merge_results(lexical_results, vector_results, top_k, query)
```

**Reciprocal Rank Fusion (RRF)** — Thuật toán merge cốt lõi:

```python
def _rrf(self, rank: int) -> float:
    k = self._scoring["rrf"]["k"]            # k = 60 (default)
    return 1.0 / (k + rank)

def _merge_results(self, lexical_results, vector_results, top_k, query, ...):
    # Bước 1: Tính RRF score cho mỗi doc
    for doc_id in all_doc_ids:
        rrf_score = 0.0
        if doc_id in lexical_rank_map:
            rrf_score += self._rrf(lexical_rank_map[doc_id])
        if doc_id in vector_rank_map:
            rrf_score += self._rrf(vector_rank_map[doc_id])
        merged[doc_id] = {"doc_id": doc_id, "score": rrf_score, ...}

    # Bước 2: Tách exact matches (giữ nguyên, không rerank)
    # Bước 3: Product gate filter (loại candidates sai entity)
    # Bước 4: Hydrate candidates (load full metadata)
    # Bước 5: Cross-encoder rerank
    # Bước 6: Metadata bonus (service/domain match)
    # Bước 7: Kết hợp exact + semantic, truncate top_k
    return (exact_results + semantic_candidates)[:top_k]
```

> **Giải thích logic merge**: Hệ thống dùng RRF thay vì score normalization vì scores từ BM25 và vector search có scale khác nhau. RRF chỉ dựa vào **thứ hạng** (rank), không phụ thuộc vào giá trị score tuyệt đối. Nếu 1 document xuất hiện ở cả 2 nhánh, RRF score cộng dồn → ưu tiên cao hơn.

### 5.3.4 Reranking

```python
# File: RAG/app/retrieval/reranker.py — class CrossEncoderReranker
# Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (~22 MB, ~5 ms/pair)

def rerank(self, query, candidates, top_n=20):
    pairs = [(query, self._extract_passage(c)) for c in candidates]
    raw_scores = self._model.predict(pairs)

    # Sigmoid normalization → [0, 1]
    scores = 1.0 / (1.0 + np.exp(-np.asarray(raw_scores)))

    for candidate, score in zip(candidates, scores):
        candidate["score"] = float(score)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_n]
```

> Cross-encoder nhận cặp (query, passage) và cho score trực tiếp, chính xác hơn bi-encoder nhưng chỉ dùng cho reranking (top-N nhỏ) vì chi phí tính toán cao hơn.

---

## 5.4 Hiện thực Mapping và Context Construction

### 5.4.1 Mapping Resolution

```python
# File: RAG/app/services/mapping_service.py — class MappingService

def resolve(self, request):
    normalized_check_id = normalize_identifier(request.check_id)
    # Load mapping index (JSON artifact, indexed by check_id)
    mapping_index = self._get_mapping_index()
    candidates = mapping_index.get(normalized_check_id, [])

    # Lọc theo service/domain
    filtered = self._filter_candidates(candidates, service, domain)
    # Sắp xếp theo mapping_sort_key (confidence, review_status)
    ranked = sorted(filtered, key=mapping_sort_key, reverse=True)

    return {"mapping": ranked[0], "candidates": ranked[:5]}
```

**Cấu trúc mapping item**:
```json
{
    "check_id": "s3_bucket_public_access",
    "capability_id": "data_protection.encryption_at_rest",
    "capability_name": "Encryption at Rest",
    "mapping_confidence": "high",
    "review_status": "approved",
    "mapping_type": "direct",
    "domain": "security"
}
```

### 5.4.2 Context Selection

```python
# File: RAG/app/context/context_builder.py — class ContextBuilder

def build(self, bundle, consumer, options):
    # Chọn checks: tách requested vs related
    requested_checks, related_checks = self._coverage_selector.select_checks(
        check_results, consumer, confidence, ...
    )
    # Chọn mappings: entity gating (chỉ giữ mapping match service/domain)
    selected_mappings = self._coverage_selector.select_mappings(
        mapping_results, consumer, max_chars_per_item, check_signal
    )
    # Chọn capabilities: domain filtering
    selected_capabilities = self._coverage_selector.select_capabilities(
        maturity_results, consumer, confidence, ...
    )
    # ... tiếp tục build bundle theo consumer ...
```

### 5.4.3 Context Bundling theo Agent

```python
# File: RAG/app/context/bundle_factory.py — class BundleFactory

def build(self, consumer, requested_checks, related_checks, mappings, capabilities):
    if consumer == "risk":
        return self.build_risk_bundle(...)
    elif consumer == "planning":
        return self.build_planning_bundle(...)
    elif consumer == "report":
        return self.build_report_bundle(...)
```

**Risk bundle** — Context đầy đủ cho đánh giá rủi ro:
```python
def build_risk_bundle(self, ...):
    return {
        "primary_finding": {              # Finding chính (full details + remediation)
            "check_id": "...", "title": "...",
            "severity": "...", "remediation": "..."
        },
        "related_findings": [             # Findings liên quan (metadata only)
            {"check_id": "...", "service": "...", "severity": "..."}
        ],
        "control_mapping": [              # Mapping check → capability
            {"check_id": "...", "capability_id": "...", "mapping_confidence": "high"}
        ],
        "maturity_context": [             # Capability descriptions
            {"capability_id": "...", "capability_name": "...", "short_text": "..."}
        ],
    }
```

**Planning bundle** — Lightweight, chỉ IDs và severity:
```python
def build_planning_bundle(self, ...):
    return {
        "related_findings": [
            {"check_id": "...", "service": "...", "title": "...", "severity": "..."}
        ],
        "control_mapping_ids": ["capability_1", "capability_2"],
        "maturity_capability_ids": ["cap_a", "cap_b"],
    }
```

**Report bundle** — Aggregated themes cho narrative generation:
```python
def build_report_bundle(self, ...):
    return {
        "primary_topics": ["s3", "iam"],                   # services involved
        "key_findings": [
            {"check_id": "...", "title": "...", "severity": "...", "risk_summary": "..."}
        ],
        "control_themes": [                                # capability summaries
            {"capability_id": "...", "capability_name": "...", "summary_short": "..."}
        ],
        "recommended_practices": ["Enable encryption...", "Rotate keys..."],
    }
```

### 5.4.4 Prompt-ready Context

```python
# File: RAG/app/context/context_builder.py

# Format cho LLM — tạo evidence summary + prompt-ready text
evidence_summary = self._prompt_formatter.build_evidence_summary(
    selected_checks, selected_mappings, selected_capabilities, max_context_items
)
prompt_ready_context = self._prompt_formatter.format(
    consumer, query, requested_checks, related_checks,
    selected_mappings, selected_capabilities,
    confidence, review_recommended, warnings,
)
```

---

## 5.5 Hiện thực API hệ thống

### 5.5.1 API truy hồi

```python
# File: RAG/app/api/routes/retrieve.py

router = APIRouter(prefix="/v1", tags=["rag"])

@router.post("/retrieve/checks", response_model=ResponseEnvelope)
def retrieve_checks(
    payload: RetrieveChecksRequest,
    service: CheckService = Depends(get_check_service),
) -> ResponseEnvelope:
    return service.search(payload)

@router.post("/retrieve/maturity", response_model=ResponseEnvelope)
def retrieve_maturity(
    payload: RetrieveMaturityRequest,
    service: MaturityService = Depends(get_maturity_service),
) -> ResponseEnvelope:
    return service.search(payload)
```

### 5.5.2 API xây dựng Context

```python
@router.post("/context/build", response_model=ContextBuildResponse)
def build_context(
    payload: ContextBuildRequest,
    service: ContextService = Depends(get_context_service),
) -> ContextBuildResponse:
    return service.build(payload)
```

**ContextService orchestration** — Luồng xử lý bên trong:

```python
# File: RAG/app/services/context_service.py — class ContextService

def build(self, request: ContextBuildRequest) -> ContextBuildResponse:
    # 1) Retrieve checks
    check_outputs = self._retrieve_checks(request, normalized_check_ids)
    check_results = self._merge_result_lists(...)

    # 2) Resolve mappings (nếu include_mappings=True)
    mapping_results = self._resolve_mappings(...)

    # 3) Retrieve maturity (nếu include_maturity=True)
    maturity_results = self._retrieve_maturity(...)

    # 4) Build context packet theo consumer type
    context_data = self._builder.build(
        bundle={
            "check_results": check_results,
            "mapping_results": mapping_results,
            "maturity_results": maturity_results,
            "consumer": request.consumer,       # "planning" | "risk" | "report"
            # ...
        },
        consumer=request.consumer,
    )
    return ContextBuildResponse(...)
```

---

## Tóm tắt File References

| Component | File Path | Line refs |
|---|---|---|
| Normalizers | `RAG/app/ingestion/normalizers.py` | tokenize: 31-47, prowler: 608-687, maturity: 509-605 |
| Build Script | `RAG/scripts/build_all.py` | main: 323-440, _to_index_doc: 155-174 |
| BM25 Index | `RAG/app/indexing/lexical_index.py` | build: 88-113, score: 189-210 |
| Vector Index | `RAG/app/indexing/vector_index.py` | build_collection: 119-149, query: 155-207 |
| Retrieval Pipeline | `RAG/app/retrieval/pipeline.py` | merge: 590-737, parallel: 275-282 |
| Reranker | `RAG/app/retrieval/reranker.py` | rerank: 48-73 |
| Mapping Service | `RAG/app/services/mapping_service.py` | resolve: 38-198 |
| Context Builder | `RAG/app/context/context_builder.py` | build: 57-157 |
| Bundle Factory | `RAG/app/context/bundle_factory.py` | risk: 55-112, planning: 114-159, report: 161-251 |
| API Routes | `RAG/app/api/routes/retrieve.py` | endpoints: 51-77 |
| Context Service | `RAG/app/services/context_service.py` | build: 69-139 |
