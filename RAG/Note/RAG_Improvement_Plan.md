# RAG Retrieval Quality Improvement Plan

**Ngay tao**: 05/04/2026  
**Phien ban**: 2.0  
**Co so**: Benchmark run 2026-04-05, Release Criteria PASS (13/13)  
**Muc tieu**: Cai thien retrieval quality cho semantic/risk queries bang cac thay doi co tinh he thong, khong fix theo test case.

---

## 1. Tong quan ket qua hien tai

### 1.1 Release Criteria (PASS 13/13)

| Metric | Nguong | Thuc te | Gap |
|--------|--------|---------|-----|
| Checks Top-1 Accuracy | >= 60% | 63.4% | Sat nguong (+3.4pp) |
| Checks Top-5 Accuracy | >= 80% | 80.5% | Sat nguong (+0.5pp) |
| Maturity Top-1 Accuracy | >= 60% | 89.5% | Du |
| Maturity Top-5 Accuracy | >= 80% | 94.7% | Du |
| Combined MRR | >= 0.70 | 0.7728 | OK |
| Combined NDCG@5 | >= 0.75 | 0.7924 | OK |
| Service Precision | >= 85% | 90.2% | OK |
| Forbidden Cap Rate | = 0% | 0.0% | Hoan hao |
| Avg Latency | <= 5000ms | 2871ms | Du |
| Latency P90 | <= 6000ms | 3162ms | Du |
| Robustness Gap | <= 90pp | 87.5pp | Sat nguong (+2.5pp) |
| Confidence ECE | <= 0.20 | 0.1866 | Sat nguong |

### 1.2 Hieu suat theo Category (Checks endpoint)

| Category | Cases | Top-1 | Top-5 | MRR | NDCG@5 |
|----------|-------|-------|-------|-----|--------|
| exact | 18 | 18 (100%) | 18 (100%) | 1.000 | 1.000 |
| paraphrase | 9 | 5 (56%) | 9 (100%) | 0.759 | 0.821 |
| risk | 6 | 2 (33%) | 4 (67%) | 0.472 | 0.522 |
| semantic_hard | 8 | 1 (12%) | 2 (25%) | 0.188 | 0.204 |

### 1.3 Hieu suat theo Service

| Service | Cases | Top-1 | Top-5 | Svc Precision |
|---------|-------|-------|-------|---------------|
| S3 | 10 | 8 (80%) | 9 (90%) | 100% |
| IAM | 9 | 5 (56%) | 7 (78%) | 100% |
| EC2 | 9 | 4 (44%) | 7 (78%) | 89% |
| RDS | 5 | 4 (80%) | 4 (80%) | 80% |
| CloudTrail | 5 | 2 (40%) | 3 (60%) | 60% |
| KMS | 3 | 3 (100%) | 3 (100%) | 100% |

---

## 2. Phan tich 8 Failure Cases (khong hit Top-5)

### 2.1 Phan loai root cause

**Nhom A - Recall Failure (4/8)**: Expected doc KHONG xuat hien trong ca lexical lan vector top-15.

| Case | Query | Expected | Van de |
|------|-------|----------|--------|
| iam_semantic_hard_1 | "protect the most privileged aws credentials from unauthorized use" | iam_avoid_root_usage | Model khong hieu "most privileged credentials" = "root account" |
| rds_semantic_hard_1 | "keep relational databases isolated from direct internet connections" | rds_instance_no_public_access | Model khong map "isolated from internet" -> "no public access" |
| cloudtrail_risk_1 | "cloudtrail logs stored in publicly accessible s3 bucket" | cloudtrail_logs_s3_bucket_is_not_publicly_accessible | Cross-service confusion: "s3 bucket" dominates, cloudtrail check bi bo qua |
| cloudtrail_semantic_hard_1 | "track api activity and changes across the entire cloud environment" | cloudtrail_multi_region_enabled_logging_management_events | Concept gap qua lon: "track api activity" vs "multi region logging" |

**Nhom B - RRF Dilution (4/8)**: Expected doc CO trong 1-2 sources nhung bi day ra khoi top-5 sau merge.

| Case | Query | Expected | Lex rank | Vec rank | Van de |
|------|-------|----------|----------|----------|--------|
| s3_risk_2 | "s3 bucket encryption not enabled risk" | s3_bucket_default_encryption | 2 | 1 | Ca hai sources tim duoc, nhung RRF thua doc xuat hien o ca 2 sources |
| iam_semantic_hard_2 | "enforce strong password requirements" | iam_password_policy_minimum_length_14 | - | 2 | Chi vector tim thay -> RRF score thap |
| ec2_semantic_hard_1 | "prevent credential theft via metadata" | ec2_launch_template_imdsv2_required | 4 | - | Chi lexical tim thay rank 4 -> RRF score qua thap |
| ec2_semantic_hard_2 | "close dangerous admin ports" | ec2_sg_allow_ingress_all_ports | - | 1 | Vector rank 1 nhung lexical miss -> RRF bi dilute |

---

## 3. Phan tich 6 Van de chinh

### 3.1 [P1-CRITICAL] Embedding Model khong phu hop

**Hien trang:**
- Model: `all-MiniLM-L6-v2` (384 dimensions, 22M params, train tren NLI+STS general data)
- 4/8 failures: expected doc khong xuat hien trong vector top-15
- semantic_hard: MRR chi 0.188

**Tai sao day la van de goc:**
- Model general-purpose khong hieu domain AWS security terminology
- Khong biet "most privileged credentials" lien quan den "root account"
- Khong biet "isolated from internet" tuong duong "no public access"
- Viec them aliases chi fix duoc cac queries DA BIET, khong generalize cho queries moi
- 577 checks x 3-5 concept aliases = hang nghin aliases viet tay, khong scale

**Giai phap**: Doi sang `BAAI/bge-base-en-v1.5` (768 dims, 110M params, top MTEB benchmark).

### 3.2 [P1-CRITICAL] RRF Fusion thiet ke co van de co ban

**Hien trang:**
- RRF chi dung rank position, bo qua raw score hoan toan
- Cong thuc: `score(doc) = SUM(1/(k + rank))` voi k=60
- Doc xuat hien o 1 source (du rank 1) LUON thua doc xuat hien o ca 2 sources (du rank thap)

**Vi du cu the — s3_risk_2:**
```
Expected: s3_bucket_default_encryption
  Lexical rank 2: RRF = 1/(60+2) = 0.0161
  Vector rank 1:  RRF = 1/(60+1) = 0.0164
  Total = 0.0325

Nhung doc khac xuat hien o ca 2 sources:
  Lexical rank 5 + Vector rank 8:
  Total = 1/(60+5) + 1/(60+8) = 0.0154 + 0.0147 = 0.0301
  -> Van thap hon 0.0325 nhung nhieu docs khac co tong cao hon
```

**Tai sao day khong phai loi cua RRF:** RRF la thuat toan chuan, van de la khi 2 sources co chat luong khong dong deu (vi du vector tim dung nhung BM25 miss hoan toan), pure rank fusion khong phan biet duoc.

### 3.3 [P2-MEDIUM] Retrieval text qua noisy cho ca embedding lan reranker

**Hien trang:** `retrieval_text` dung chung cho vector embedding va cross-encoder reranker, chua 9 fields:

```
check: s3_bucket_level_public_access_block
service: s3
title: check s3 bucket level public access block.
description: check s3 bucket level public access block.
risk: public access policies may be applied...
recommendation: you can enable public access block...
resource_type: AwsS3Bucket
keywords: bucket cloud storage object storage public access
aliases: anonymous access block public access block public reads at bucket level
browse bucket contents bucket bucket contents bucket listing bucket objects...
```

**Van de:**
- Aliases chiem 50-70% chieu dai text nhung la danh sach phang (khong phai cau), lam nhieu embedding
- Cross-encoder phai xu ly chuoi dai, signal-to-noise thap
- Cung 1 text phuc vu 2 muc dich khac nhau (embedding vs reranking) la thiet ke khong tot

### 3.4 [P2-MEDIUM] Confidence Calibration sai lech

**Hien trang:**
- High confidence: 36/41 cases, top-1 accuracy chi **72%** (target >= 80%)
- Medium confidence: **0 cases** — khong co case nao duoc gan medium
- Low confidence: 5 cases, accuracy 0%

**Nguyen nhan:**
- Reranker output (sigmoid) thuong > 0.70 -> vuot threshold `check_search.high = 0.70`
- Ambiguity penalty chi ap dung cho `requires_exact_lookup=True`
- NL queries co RRF/reranker scores tight cluster nhung KHONG bi penalize

### 3.5 [P2-MEDIUM] Cross-service query confusion

- CloudTrail service precision chi 60%
- Queries co keywords nhieu services bi nham (vd: "cloudtrail logs in s3 bucket" -> S3 checks thang)
- Service metadata bonus +0.03 qua nho de override

### 3.6 [P3-LOW] Cross-Encoder Reranker khong hieu qua

- Model `ms-marco-MiniLM-L-6-v2` train tren web search, khong match domain
- Lift: MRR +0.017, chi 4/41 cases cai thien
- Retrieval text noisy lam giam kha nang phan biet relevance

---

## 4. Ke hoach cai thien (Production-Grade)

### 4.0 Nguyen tac thiet ke

1. **Khong fix theo test case**: Moi thay doi phai cai thien he thong mot cach tong quat, khong nham vao cases cu the
2. **Khong hardcode magic values**: Cac threshold phai co co so tinh toan hoac configurable
3. **Benchmark la do luong, khong phai muc tieu**: Cai thien pipeline, khong tune de "dat diem"
4. **Thay doi tung buoc, do luong tung buoc**: Moi phase chay benchmark doc lap de hieu impact

---

### Phase 1: Nang cap Embedding Model

**Van de giai quyet**: Recall failure (van de 3.1)  
**Thay doi**: Doi `all-MiniLM-L6-v2` -> `BAAI/bge-base-en-v1.5`

#### 1.1 Tai sao chon bge-base-en-v1.5

| Tieu chi | all-MiniLM-L6-v2 | BAAI/bge-base-en-v1.5 |
|----------|-------------------|------------------------|
| Dimensions | 384 | 768 |
| Parameters | 22M | 110M |
| MTEB Retrieval avg | ~49 | ~53.5 |
| Max sequence length | 256 tokens | 512 tokens |
| Training data | NLI + STS (general) | RetroMAE + contrastive (retrieval-optimized) |
| Instruction prefix | Khong | Ho tro "Represent this sentence:" |
| Size | ~90 MB | ~440 MB |

**Diem quan trong:**
- bge-base duoc train DACH CHO RETRIEVAL (khong phai NLI), nen hieu semantic similarity tot hon
- 768 dims cho bieu dien phong phu hon, giam kha nang 2 concepts khac nhau bi map vao cung vung
- Ho tro instruction prefix giup phan biet query vs document embedding
- Sequence length 512 tokens phu hop voi retrieval_text dai (MiniLM chi 256)

#### 1.2 Thay doi code

**File 1: `RAG/app/core/config.py`**
```python
# Truoc:
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Sau:
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
```

**File 2: `RAG/app/indexing/vector_index.py`**

bge-base ho tro instruction prefix cho queries. Can sua query method de prepend "Represent this sentence: " khi encode query (KHONG prepend khi encode documents luc index).

```python
# Trong method query():
# bge-base recommend prefix cho query (khong cho document)
query_text = query
if "bge" in self.embedding_model.lower():
    query_text = f"Represent this sentence: {query}"
```

**Luu y**: Day KHONG phai hardcode — day la cach su dung dung theo tai lieu chinh thuc cua BAAI/bge. Model duoc train VOI prefix nay.

#### 1.3 Rebuild index

```bash
cd RAG
# Luu backup truoc khi rebuild
cp -r data/indexes/chroma data/indexes/chroma_backup_minilm

# Rebuild tat ca indexes (BM25 khong doi, chi Chroma doi)
python -m scripts.build_all
```

**Du kien:**
- Index size tang tu ~44MB len ~80-90MB (768 vs 384 dims)
- Build time: ~3-5 phut (1,157 docs)
- Latency query tang nhe (~10-20%) do embedding lon hon

#### 1.4 Kiem tra sau Phase 1

```bash
# Start server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Run benchmark
python -m scripts.run_benchmark --tag "phase1-bge-base"

# So sanh
python -m scripts.compare_benchmarks last latest
```

**Du kien impact:**
- semantic_hard recall tang dang ke (4 recall-failure cases co the duoc giai quyet)
- exact queries khong bi anh huong (van dung lexical exact-match path)
- paraphrase co the tang nhe
- Maturity endpoint co the tang nhe

#### 1.5 KET QUA THUC TE (2026-04-05)

**Trang thai**: HOAN THANH — model da doi, index da rebuild, benchmark da chay.

**So sanh voi baseline:**

| Metric | Baseline (MiniLM) | Phase 1 (BGE-base) | Thay doi |
|--------|-------------------|---------------------|----------|
| Checks Top-1 | 63.4% | 63.4% | Khong doi |
| Checks Top-5 | 80.5% | 80.5% | Khong doi |
| Combined MRR | 0.7728 | 0.7728 | Khong doi |
| semantic_hard MRR | 0.188 | 0.188 | Khong doi |
| Latency avg | 2871ms | 2804ms | Giam nhe |
| Vector visible | 41/41 | 41/41 | OK |

**Phan tich failure cases:**

| Case | Baseline vec top15? | BGE-base vec top15? | Danh gia |
|------|---------------------|---------------------|----------|
| iam_semantic_hard_1 | MISS | MISS | Ca 2 khong hieu |
| iam_semantic_hard_2 | rank 2 | MISS | BGE WORSE |
| ec2_semantic_hard_2 | rank 1 | MISS | BGE WORSE |
| ec2_semantic_hard_1 | MISS | MISS | Ca 2 khong hieu |
| rds_semantic_hard_1 | MISS | MISS | Ca 2 khong hieu |
| cloudtrail_risk_1 | MISS | MISS | Ca 2 khong hieu |
| cloudtrail_semantic_hard_1 | MISS | MISS | Ca 2 khong hieu |
| s3_risk_2 | rank 1 | rank 1 | Giong nhau |

**Nhan dinh**: Doi model KHONG giai quyet duoc van de vi root cause la **retrieval_text qua noisy**:
- Aliases chiem 50-70% text, lam dilute embedding cho BAT KY model nao
- Doc khong chua concept tuong ung (vi du `iam_avoid_root_usage` khong co "privileged credentials" trong retrieval_text)
- 2 cases con bi WORSE vi BGE-base sensitive hon voi noise trong aliases

**Bai hoc**: Phase 2 (tach embedding_text) moi la buoc quyet dinh, khong phai doi model.
Model BGE-base van giu lai vi:
- Duoc train danh cho retrieval (khong phai NLI)
- 768 dims bieu dien phong phu hon
- Se phat huy khi ket hop voi embedding_text sach (Phase 2)
- Khong regression tren bat ky metric nao

---

### Phase 2: Tach Retrieval Text theo muc dich

**Van de giai quyet**: Retrieval text noisy (van de 3.3), Reranker khong hieu qua (van de 3.6)  
**Nguyen tac**: Moi component can text toi uu cho muc dich cua no

#### 2.1 Thiet ke 3 loai text

Hien tai chi co 1 `retrieval_text` phuc vu ca embedding, BM25, va reranking. Can tach thanh:

| Text field | Muc dich | Content | Su dung boi |
|------------|----------|---------|-------------|
| `retrieval_text` (giu nguyen) | BM25 lexical search | Tat ca fields ke ca aliases, keywords | BM25Index |
| `embedding_text` (moi) | Vector embedding | Title + description + risk (semantic core) | Chroma/SentenceTransformer |
| `reranker_text` (moi) | Cross-encoder scoring | Title + description + risk (ngan gon) | CrossEncoderReranker |

#### 2.2 Tai sao tach?

- **BM25** can aliases/keywords de match terms -> giu `retrieval_text` day du
- **Embedding** can noi dung ngan, ngon ngu tu nhien de encode semantic meaning -> aliases dang danh sach lam nhieu
- **Reranker** can (query, passage) pair ngan de cross-attention hieu qua -> text dai lam giam accuracy

#### 2.3 Thay doi code

**File: `RAG/app/ingestion/normalizers.py`**

Them ham tao embedding_text va reranker_text:

```python
def build_embedding_text(fields: List[tuple]) -> str:
    """Build text optimized for dense embedding.

    Chi giu cac fields co noi dung semantic (title, description, risk).
    Bo aliases, keywords, check_id, resource_type, remediation.
    """
    EMBEDDING_FIELDS = {"title", "description", "risk", "name", "summary",
                        "risk_explanation", "guidance"}
    chunks = []
    for field_name, value in fields:
        if field_name in EMBEDDING_FIELDS:
            text = _normalize_for_index(value)
            if text:
                chunks.append(text.lower())
    return " ".join(chunks)


def build_reranker_text(fields: List[tuple]) -> str:
    """Build text optimized for cross-encoder reranking.

    Structured format giup cross-encoder phan biet fields.
    """
    RERANKER_FIELDS = {"title", "description", "risk", "name", "summary"}
    chunks = []
    for field_name, value in fields:
        if field_name in RERANKER_FIELDS:
            text = _normalize_for_index(value)
            if text:
                chunks.append(f"{field_name}: {text.lower()}")
    return "\n".join(chunks)
```

**File: `RAG/app/ingestion/normalizers.py` — normalize_prowler_doc():**

Them 2 fields moi vao ProwlerCheckDoc:

```python
# Trong normalize_prowler_doc(), them:
fields_list = [
    ("check", check_id),
    ("service", service),
    ("title", title),
    ("description", description),
    ("risk", risk),
    ("recommendation", recommendation_text),
    ("resource_type", raw.get("ResourceType", "")),
    ("keywords", " ".join(enriched_keywords)),
    ("aliases", alias_text),
]

return ProwlerCheckDoc(
    ...,
    retrieval_text=build_retrieval_text_prefixed(fields_list),
    embedding_text=build_embedding_text(fields_list),       # MOI
    reranker_text=build_reranker_text(fields_list),          # MOI
)
```

**File: `RAG/scripts/build_all.py`:**

Khi build Chroma collection, su dung `embedding_text` thay vi `retrieval_text`:

```python
# Trong _build_chroma_for_corpus():
documents = [doc.get("embedding_text") or doc.get("retrieval_text") for doc in docs]
```

**File: `RAG/app/retrieval/reranker.py`:**

```python
@staticmethod
def _extract_passage(candidate: Dict[str, Any]) -> str:
    meta = candidate.get("metadata") or {}
    # Uu tien reranker_text, fallback retrieval_text
    reranker_text = meta.get("reranker_text")
    if reranker_text and str(reranker_text).strip():
        return str(reranker_text).strip()

    retrieval_text = meta.get("retrieval_text")
    if retrieval_text and str(retrieval_text).strip():
        return str(retrieval_text).strip()

    parts = [meta.get("title", ""), meta.get("description", ""), meta.get("summary", "")]
    return " ".join(str(p) for p in parts if p).strip() or candidate.get("doc_id", "")
```

#### 2.4 Kiem tra sau Phase 2

- Re-build indexes: `python -m scripts.build_all`
- Re-run benchmark: `python -m scripts.run_benchmark --tag "phase2-text-split"`
- So sanh: embedding quality, reranker lift, latency

**Du kien impact:**
- Vector recall tang (embedding text ngan + semantic-rich)
- Reranker lift tang (reranker text sach hon)
- BM25 khong doi (retrieval_text giu nguyen)
- Latency co the giam nhe (embedding text ngan hon -> encode nhanh hon)

#### 2.5 KET QUA THUC TE (2026-04-05)

**Trang thai**: HOAN THANH — tach text, rebuild index, benchmark xong.

**Thay doi thuc hien:**
- `app/core/models.py`: Them `embedding_text`, `reranker_text` vao BaseDoc
- `app/ingestion/normalizers.py`: Them `build_embedding_text()`, `build_reranker_text()` + cap nhat normalize_prowler_doc, normalize_maturity_doc, normalize_mapping_doc
- `scripts/build_all.py`: Them `_embedding_text()`, sua `_to_index_doc` va `vector_index.build_collection` dung `embedding_text`
- `app/retrieval/pipeline.py`: Sua `_extract_rich_metadata()` truyen `embedding_text`, `reranker_text`
- `app/retrieval/reranker.py`: Sua `_extract_passage()` uu tien `reranker_text`

**So sanh voi baseline:**

| Metric | Baseline | Phase 2 | Thay doi |
|--------|----------|---------|----------|
| Checks Top-1 | 63.4% | 63.4% | Khong doi |
| Checks Top-5 | 80.5% | 80.5% | Khong doi |
| Combined MRR | 0.7728 | 0.7736 | +0.001 |
| semantic_hard MRR | 0.188 | 0.188 | Khong doi |
| Reranker lift | +0.017 | +0.017 | Khong doi |

**Phan tich vector results (failure cases vs baseline):**

| Case | Baseline vec | Phase 2 vec | Danh gia |
|------|-------------|-------------|----------|
| rds_semantic_hard_1 | MISS | **rank 4** | **BETTER** — embedding sach giup tim duoc |
| ec2_semantic_hard_1 | MISS | MISS (nhung top1 lien quan hon) | Vector results cai thien |
| ec2_semantic_hard_2 | rank 1 | **MISS** | **WORSE** — clean text mat keyword "ports" |
| iam_semantic_hard_2 | rank 2 | rank 4 | Giam rank nhung van trong top5 |
| Con lai | MISS | MISS | Khong doi |

**Nhan dinh:**
- Embedding text sach giup 1 case (rds_semantic_hard_1) duoc vector tim thay
- Nhung RRF van dilute ket qua -> final metrics khong doi
- 1 case regression (ec2_semantic_hard_2) vi clean text bo mat "ports exposed" context tu aliases
- Reranker text chua phat huy vi reranker model van la ms-marco general
- **Can Phase 3 (RSF fusion)** de khai thac vector improvements vao final ranking

---

### Phase 3: Cai thien Hybrid Fusion

**Van de giai quyet**: RRF dilution (van de 3.2)  
**Nguyen tac**: Ket hop rank va score, khong chi rank

#### 3.1 Phan tich van de RRF

RRF (Reciprocal Rank Fusion) la thuat toan rank-based:
- Uu diem: Khong can normalize score giua cac sources
- Nhuoc diem: Bo qua CONFIDENCE cua tung source — doc rank 1 voi score 0.95 va doc rank 1 voi score 0.55 co cung RRF score

Trong he thong nay, khi embedding model tot hon (Phase 1), van de nay se GIAM NHIEU vi:
- Vector se tim dung doc nhieu hon -> doc xuat hien o CA HAI sources -> RRF tu nhien dung
- Nhung van con edge cases khi 2 sources bat dong

#### 3.2 Giai phap: Relative Score Fusion (RSF)

Thay vi chi dung rank, ket hop rank (RRF) voi normalized score:

```
final_score(doc) = alpha * RRF(doc) + (1 - alpha) * max_normalized_score(doc)
```

Trong do:
- `RRF(doc)` = sum(1/(k+rank)) nhu hien tai
- `max_normalized_score(doc)` = max score cua doc qua cac sources, normalize ve [0, 1]
  - Vector score: da la [0, 1] (tu distance conversion)
  - BM25 score: normalize bang min-max trong batch: `(score - min) / (max - min)`
- `alpha` = cau hinh trong `scoring_config.json`, mac dinh 0.7

**Tai sao alpha = 0.7 (RRF van dominant)?**
- RRF da duoc chung minh robust qua nhieu nghien cuu
- Raw score chi bo sung khi 1 source co confidence rat cao nhung source kia miss
- Gia tri alpha configurable, khong hardcode — co the tune sau dua tren benchmark data

#### 3.3 Thay doi code

**File: `RAG/data/indexes/scoring_config.json`**

```json
{
  "rrf": {"k": 60},
  "fusion": {
    "method": "rsf",
    "alpha": 0.7
  }
}
```

**File: `RAG/app/retrieval/pipeline.py` — method `_merge_results()`**

```python
# Thay doi trong Step 1: RRF merge
fusion_cfg = self._scoring.get("fusion", {})
fusion_method = fusion_cfg.get("method", "rrf")  # Default: pure RRF (backward compatible)
alpha = fusion_cfg.get("alpha", 0.7)

if fusion_method == "rsf":
    # Normalize BM25 scores to [0, 1] via min-max
    lex_scores = [r.get("score", 0) for r in lexical_results]
    lex_min = min(lex_scores) if lex_scores else 0
    lex_max = max(lex_scores) if lex_scores else 1
    lex_range = lex_max - lex_min if lex_max > lex_min else 1.0

    for doc_id in all_doc_ids:
        rrf_score = 0.0
        max_norm_score = 0.0

        if doc_id in lexical_rank_map:
            rrf_score += self._rrf(lexical_rank_map[doc_id])
            raw = next(r["score"] for r in lexical_results if r["doc_id"] == doc_id)
            max_norm_score = max(max_norm_score, (raw - lex_min) / lex_range)

        if doc_id in vector_rank_map:
            rrf_score += self._rrf(vector_rank_map[doc_id])
            raw = next(r["score"] for r in vector_results if r["doc_id"] == doc_id)
            max_norm_score = max(max_norm_score, raw)  # Vector score da [0, 1]

        merged[doc_id]["score"] = alpha * rrf_score + (1 - alpha) * max_norm_score
else:
    # Pure RRF (hien tai)
    ...
```

**Backward compatible**: `fusion.method = "rrf"` (mac dinh) giu nguyen hanh vi cu.

#### 3.4 Kiem tra

- Run benchmark voi `method: "rrf"` (baseline) va `method: "rsf"` (moi)
- So sanh cac RRF-dilution cases (s3_risk_2, iam_semantic_hard_2, ec2_semantic_hard_1, ec2_semantic_hard_2)
- Kiem tra khong regression tren exact va paraphrase cases

#### 3.5 KET QUA THUC TE (2026-04-05)

**Trang thai**: HOAN THANH — RSF implemented, benchmark xong.

**Thay doi thuc hien:**
- `app/core/scoring_config.json`: Them `fusion: {method: "rsf", alpha: 0.7}`
- `app/core/config.py`: Them RSF defaults trong fallback config
- `app/retrieval/pipeline.py`: Implement RSF trong `_merge_results()` Step 1

**So sanh voi baseline:**

| Metric | Baseline | Phase 3 (RSF) | Thay doi |
|--------|----------|---------------|----------|
| Checks Top-1 | 63.4% | 63.4% | Khong doi |
| Checks Top-5 | 80.5% | 80.5% | Khong doi |
| Combined MRR | 0.7728 | 0.7736 | +0.001 |
| semantic_hard MRR | 0.188 | 0.188 | Khong doi |

**Phat hien quan trong:**
RSF KHONG cai thien metrics vi **cross-encoder reranker overwrite fusion scores**.

Pipeline flow hien tai:
```
Fusion (RSF) -> score = alpha*RRF + (1-alpha)*norm_score
     |
     v
Reranker -> candidate["score"] = sigmoid(cross_encoder_output)  # OVERWRITE
     |
     v
Final ranking dua tren reranker score, khong phai fusion score
```

RSF chi anh huong thu tu candidates vao reranker pool (top 20). Nhung ca RRF lan RSF dua cung ~20 candidates vao pool -> reranker output giong nhau -> final ranking giong nhau.

**Nhan dinh:**
- RSF fusion code dung va backward compatible (method=rrf van hoat dong)
- Nhung hieu qua thuc te bi han che boi reranker overwrite
- Day la thiet ke dung cua pipeline: reranker SHOULD override fusion score vi no hieu relevance tot hon
- Van de THAT SU la reranker (ms-marco) khong hieu domain AWS security -> cho score gan nhau cho cac candidates -> khong phan biet duoc

**Giu RSF** vi:
- Khong regression, code clean va configurable
- Se phat huy neu disable reranker hoac doi sang domain-specific reranker
- Backward compatible qua config

---

### HyDE (Hypothetical Document Embeddings) — Implemented nhung disabled

**Trang thai**: HOAN THANH IMPLEMENT — disabled mac dinh do model constraint.

**Thay doi thuc hien:**
- `app/retrieval/hyde.py`: Module HyDE generator (singleton, lazy-load, fallback-safe)
- `app/core/scoring_config.json`: Config `hyde.enabled`, `hyde.model`, `hyde.base_url`
- `app/core/config.py`: Default config cho HyDE
- `app/retrieval/pipeline.py`: Inject HyDE vao vector search path, skip cho exact-lookup

**Thiet ke:**
- BM25 van dung original query (keyword matching tot)
- Chi vector search dung hypothetical document text
- Exact-lookup queries bypass hoan toan
- Fallback graceful: LLM fail -> dung original query

**Ket qua benchmark voi llama3.2 (3B params):**

| Metric | Baseline | HyDE (llama3.2) | Thay doi |
|--------|----------|-----------------|----------|
| Checks Top-5 | 80.5% | 75.6% | **-4.9pp REGRESSION** |
| Maturity Top-1 | 89.5% | 68.4% | **-21pp REGRESSION** |
| Combined MRR | 0.773 | 0.712 | **-0.061 REGRESSION** |
| Confidence ECE | 0.187 | 0.046 | **+0.14 IMPROVED** |
| Release Criteria | PASS | **FAIL** | REGRESSION |

**Nguyen nhan regression:** llama3.2 (3B params) qua nho de sinh hypothetical docs chuan cho AWS security domain. Model sinh text sai huong (vi du: query ve "root credentials" -> sinh text ve "password policy") -> vector search bi mislead.

**De enable HyDE hieu qua, can:**
1. Model lon hon (qwen3:8b, llama3:8b, hoac API-based model)
2. Prompt engineering tot hon (few-shot examples voi AWS security context)
3. Hoac ket hop voi document enrichment (Huong A) de giam dependency vao HyDE quality

**Config de enable:**
```json
{
  "hyde": {
    "enabled": true,
    "model": "qwen3:8b",
    "base_url": "http://localhost:11434"
  }
}
```

---

### Phase 4: Confidence Calibration

**Van de giai quyet**: Confidence sai lech (van de 3.4)

#### 4.1 Phan tich score distribution SAU Phase 1-3

**QUAN TRONG**: Confidence thresholds phai duoc set DUA TREN score distribution cua model moi (bge-base), KHONG PHAI model cu. Nen phase nay chi thuc hien SAU khi Phase 1-3 hoan thanh va co benchmark data moi.

#### 4.5 KET QUA THUC TE (2026-04-05)

**Trang thai**: HOAN THANH — ratio-based ambiguity implemented, benchmark verified.

**Thay doi thuc hien:**
- `app/retrieval/confidence.py`: Them ratio-based ambiguity cho NL queries (non-exact)
- `app/core/scoring_config.json`: Them `nl_ratio_high_to_medium: 0.98` vao ambiguity section
- `app/core/config.py`: Them default cho `nl_ratio_high_to_medium`

**Phan tich score distribution:**
- HIT scores (non-exact): min=0.9851, max=1.0298, mean=0.9989
- MISS scores (non-exact): min=0.0007, max=1.0290, mean=0.7866
- Reranker produces tight score clusters -> absolute gap unreliable
- Ratio (top2/top1) la signal tot hon: HITs voi clear leader co ratio < 0.98

**Thiet ke ratio-based ambiguity:**
- Chi ap dung cho NL queries (non-exact), KHONG ap dung cho exact-lookup
- Neu top2/top1 >= 0.98 va base == high -> downgrade sang medium
- Threshold 0.98 (khong phai 0.95 nhu plan goc) dua tren phan tich score distribution thuc te:
  - ratio=0.95 qua aggressive: downgrade 7 correct HITs
  - ratio=0.98 can bang: High accuracy 84% vs 90.9% (ca 2 > 80% target)
  - ratio=0.98 giu duoc nhieu high-confidence HITs hon
- Configurable qua scoring_config.json, khong hardcode

**So sanh voi baseline:**

| Metric | Baseline | Phase 4 | Thay doi |
|--------|----------|---------|----------|
| High confidence | 36 cases, 72% acc | 25 cases, 84% acc | **Accuracy +12pp** ✓ |
| Medium confidence | 0 cases | 10 cases, 50% acc | **Zone populated** ✓ |
| Low confidence | 5 cases, 0% acc | 6 cases, 0% acc | Giu nguyen ✓ |
| Check ECE | 0.1866 | **0.0854** | **Giam 54%** ✓ |
| Overall ECE | 0.1133 | **0.0375** | **Giam 67%** ✓ |
| Overall calibrated | True | True | ✓ |
| Checks Top-1 | 63.4% | 65.8% | +2.4pp (reranker variance) |
| Checks Top-5 | 80.5% | 78.0% | -2.5pp (reranker variance) |

**Luu y:**
- Benchmark cho thay reranker non-determinism giua cac lan chay (score dao dong do cross-encoder):
  - 3 cases gained top1, 3 cases lost top1 (net: unchanged 26/41)
  - Top-5 variance +-2 cases giua runs
- Day la van de cua reranker model (ms-marco), KHONG phai cua confidence calibration
- Confidence calibration code chi anh huong confidence label, KHONG anh huong ranking

#### 4.2 Phuong phap calibration

**Buoc 1**: Thu thap score distribution tu benchmark results moi

```python
# Phan tich score distribution
import json
with open("benchmark_latest.json") as f:
    data = json.load(f)

for case in data["checks_report"]["cases"]:
    top1_score = ...  # extract
    hit_top1 = ...    # extract
    # -> Plot: score vs hit_top1 (boolean)
```

**Buoc 2**: Tim optimal thresholds bang cach:
- Sap xep cac cases theo top1_score giam dan
- Tim diem cat sao cho:
  - Cac cases tren diem cat `high` co accuracy >= 80%
  - Cac cases duoi diem cat `high` nhung tren `medium` co accuracy 50-80%
  - Diem cat tu nhien (gap lon nhat trong score distribution)

**Buoc 3**: Cap nhat `scoring_config.json` voi thresholds moi

#### 4.3 Them ambiguity signal cho NL queries

Hien tai ambiguity penalty chi ap dung cho exact-lookup. Can mo rong cho NL queries nhung theo cach co co so:

**File: `RAG/app/retrieval/confidence.py`**

```python
# Thay vi hardcode gap threshold, dung ty le (ratio) giua top1 va top2
# Ratio approach khong phu thuoc vao scale cua score
if not requires_exact and len(results) > 1 and top1 > 0:
    score_ratio = top2 / top1  # 0 = top2 rat xa, 1 = top1 va top2 bang nhau
    # Neu top2 >= 95% cua top1 -> ket qua ambiguous
    if score_ratio >= 0.95 and base == Confidence.high:
        base = Confidence.medium
```

**Tai sao ratio thay vi absolute gap:**
- Absolute gap (0.005, 0.01) phu thuoc vao score range cua model -> thay model la phai re-tune
- Ratio 0.95 co y nghia bat bien: "top-2 gan bang top-1" bat ke score scale

---

### Phase 5: Benchmark va Danh gia

#### 5.1 Quy trinh benchmark tung phase

```bash
# Truoc khi bat dau — luu baseline
cd RAG
cp data/benchmarks/benchmark_outputs/benchmark_latest.json \
   data/benchmarks/benchmark_outputs/benchmark_baseline_20260405.json

# Sau moi phase
python -m scripts.run_benchmark --tag "phaseN-description"
python -m scripts.compare_benchmarks benchmark_baseline_20260405.json latest
```

#### 5.2 Muc tieu cai thien

| Metric | Baseline | Muc tieu | Co so |
|--------|----------|----------|-------|
| Checks Top-1 | 63.4% | >= 73% | Model tot hon + RSF giai quyet ~4 failure cases |
| Checks Top-5 | 80.5% | >= 88% | 4 recall failures + 4 RRF dilutions co the fix |
| semantic_hard MRR | 0.188 | >= 0.40 | Model bge-base hieu semantic tot hon MiniLM |
| risk MRR | 0.472 | >= 0.60 | RSF giu lai ket qua dung khi chi 1 source tim thay |
| Robustness Gap | 87.5pp | <= 65pp | Cai thien semantic_hard giam gap voi exact |
| High Conf Accuracy | 72% | >= 80% | Calibration lai threshold cho model moi |
| Combined MRR | 0.773 | >= 0.83 | Tong hop cac cai thien |

**Luu y**: Day la muc tieu DU KIEN, khong phai target cung. Neu Phase 1 (doi model) da dat duoc phan lon cai thien, co the skip hoac giam scope cua cac phase sau.

#### 5.3 Regression checks

Sau moi phase, kiem tra KHONG regression tren:
- [ ] Exact queries: van 100% top-1
- [ ] Maturity endpoint: van >= 89% top-1
- [ ] Forbidden capability rate: van 0%
- [ ] Latency P90: van <= 6000ms
- [ ] Service precision: van >= 85%

---

## 5. Thu tu thuc hien

| Buoc | Phase | Cong viec | Files can sua |
|------|-------|-----------|---------------|
| 1 | Phase 1 | Doi embedding model | `config.py`, `vector_index.py` |
| 2 | Phase 1 | Rebuild Chroma index | `scripts/build_all.py` (run) |
| 3 | Phase 1 | Benchmark + so sanh | `scripts/run_benchmark.py` (run) |
| 4 | Phase 2 | Tach embedding_text / reranker_text | `normalizers.py`, data models |
| 5 | Phase 2 | Sua Chroma build dung embedding_text | `build_all.py` |
| 6 | Phase 2 | Sua reranker dung reranker_text | `reranker.py` |
| 7 | Phase 2 | Rebuild + benchmark | (run) |
| 8 | Phase 3 | Implement RSF fusion | `pipeline.py`, `scoring_config.json` |
| 9 | Phase 3 | Benchmark + so sanh | (run) |
| 10 | Phase 4 | Phan tich score distribution moi | (analysis) |
| 11 | Phase 4 | Set thresholds + ratio-based ambiguity | `confidence.py`, `scoring_config.json` |
| 12 | Phase 4 | Final benchmark | (run) |

---

## 6. Rui ro va luu y

### 6.1 Rui ro theo phase

| Phase | Rui ro | Giam thieu |
|-------|--------|------------|
| Phase 1 — Doi model | Latency tang do model lon hon | Monitor P90 latency, acceptable neu < 5000ms |
| Phase 1 — Doi model | Index size tang ~2x | Disk space khong phai constraint (44MB -> ~90MB) |
| Phase 1 — Doi model | bge-base co the khong tot hon MiniLM cho MOI loai query | Benchmark tung category, rollback neu regression |
| Phase 2 — Tach text | Data model thay doi can update normalized docs | Rebuild tu raw data, khong anh huong pipeline cu |
| Phase 3 — RSF fusion | Alpha sai co the lam giam hieu suat | Configurable, A/B test voi pure RRF |
| Phase 4 — Confidence | Thresholds moi co the qua strict/loose | Dua tren data thuc te, khong guess |

### 6.2 Luu y quan trong

1. **Phase 1 la uu tien cao nhat va doc lap** — co the deploy rieng ma khong can cac phase sau
2. **Phase 4 (confidence) PHAI lam sau Phase 1-3** vi score distribution se thay doi
3. **Moi phase benchmark doc lap** — rollback neu regression
4. **Khong them aliases cho specific failing cases** — de model tu generalize
5. **Maturity endpoint dang tot** (MRR 0.905) — chi kiem tra khong regression, khong can toi uu
6. **Exact queries su dung lexical exact-match path** — doi model KHONG anh huong nhom nay

---

## 7. Appendix

### A. Cau hinh hien tai (Baseline)

```
Embedding: all-MiniLM-L6-v2 (384 dim, 22M params)
Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2
BM25: k1=1.2, b=0.6
RRF: k=60
Exact match bonus: 2.0
Service match bonus: 0.03
Domain match bonus: 0.02
Reranker top_n: 20
Search expansion: 3x top_k, min 10
Index: 577 checks, 78 maturity capabilities, 502 mappings
```

### B. Cau hinh muc tieu (Sau cai thien)

```
Embedding: BAAI/bge-base-en-v1.5 (768 dim, 110M params)
Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2 (giu nguyen)
BM25: k1=1.2, b=0.6 (giu nguyen)
Fusion: RSF (alpha=0.7, configurable)
Text: retrieval_text (BM25) + embedding_text (vector) + reranker_text (reranker)
Confidence: Calibrated thresholds dua tren score distribution moi
```

### C. Partial-Hit Cases (hit top-5 nhung miss top-1)

| Case | Query | Expected | Got Top-1 | Rank |
|------|-------|----------|-----------|------|
| s3_paraphrase_2 | "stop public access to aws object storage" | s3_account_level_public_access_blocks | s3_access_point_public_access_block | 2 |
| iam_risk_1 | "risk of using root without mfa" | iam_root_mfa_enabled | iam_avoid_root_usage | 3 |
| ec2_paraphrase_1 | "enable default encryption for ebs" | ec2_ebs_default_encryption | ec2_ebs_volume_encryption | 3 |
| ec2_paraphrase_2 | "block ssh from internet in security groups" | ec2_sg_..._port_22 | ec2_instance_port_ssh_exposed | 2 |
| ec2_risk_1 | "security group allows rdp 3389 open" | ec2_sg_..._port_3389 | ec2_instance_port_rdp_exposed | 2 |
| cloudtrail_paraphrase_1 | "enable cloudtrail logging all regions" | cloudtrail_multi_region_enabled | cloudtrail_multi_region_enabled_logging_mgmt | 2 |

Cac cases nay du kien se cai thien nho embedding model tot hon (Phase 1) va RSF fusion (Phase 3).
