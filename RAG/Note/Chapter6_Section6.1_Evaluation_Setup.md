# Chuong 6: Danh gia he thong RAG (RAG System Evaluation)

Chuong nay trinh bay qua trinh danh gia he thong RAG da xay dung o Chuong 5. Pham vi danh gia tap trung vao **retrieval subsystem** — thanh phan chiu trach nhiem truy hoi tai lieu tu knowledge base va cung cap context bundle cho cac agent xu ly phia sau. He thong khong bao gom lop sinh cau tra loi (generation layer); do do, cac chi so danh gia duoc thiet ke rieng cho bai toan information retrieval thay vi danh gia chat luong van ban dau ra.

---

## 6.1 Thiet lap danh gia (Evaluation Setup)

### 6.1.1 Kien truc pipeline duoc danh gia

Pipeline retrieval duoc danh gia bao gom cac giai doan xu ly tuan tu sau:

1. **Query Analysis & Routing** — `SemanticRouter` phan tich truy van dau vao, xac dinh loai tim kiem (`check_search`, `maturity_search`, `mapping_resolution`) va trich xuat thong tin service tu query token.

2. **Hybrid Retrieval** — He thong thuc hien dong thoi hai phuong thuc tim kiem:
   - *BM25 (Lexical search)*: Tim kiem dua tren tu khoa, phu hop voi truy van chinh xac.
   - *Vector search*: Tim kiem ngu nghia su dung mo hinh embedding `all-MiniLM-L6-v2` voi Chroma vector database.

3. **RRF Merge** — Ket qua tu hai nguon duoc hop nhat bang thuat toan Reciprocal Rank Fusion (RRF) voi tham so k = 60, nham ket hop uu diem cua ca tim kiem tu khoa va ngu nghia.

4. **Product Entity Gate** — Bo loc nhi phan loai bo cac tai lieu lien quan den dich vu dac thu (Bedrock, GuardDuty, Macie,...) neu truy van khong chua tin hieu phu hop. Co che nay dam bao ket qua tra ve dung pham vi dich vu duoc yeu cau.

5. **Cross-Encoder Reranking** — Mo hinh `cross-encoder/ms-marco-MiniLM-L-6-v2` danh gia lai do lien quan cua tung cap (query, document), cho diem so duoc chuan hoa trong khoang [0, 1] qua ham sigmoid.

6. **Metadata Bonus** — Cong them diem thuong cho tai lieu co service trung khop (+0.03) hoac domain trung khop (+0.02) voi truy van, nham uu tien ket qua dung ngu canh.

7. **Result Assembly** — Top-k tai lieu (k = 5) duoc tra ve cho ContextBuilder de dong goi thanh context bundle phuc vu cac agent phia sau.

### 6.1.2 Tap du lieu danh gia (Benchmark Dataset)

Tap du lieu benchmark duoc xay dung thu cong, bao gom **60 test case** chia thanh hai bo kiem tra tuong ung voi hai route chinh cua he thong:

| Bo kiem tra | So luong | Mo ta |
|---|---|---|
| **Check cases** | 41 | Truy van lien quan den cac security check cua AWS |
| **Maturity cases** | 19 | Truy van lien quan den cac maturity capability |
| **Tong** | **60** | |

Moi test case bao gom cac truong: `query` (cau truy van), `expected_doc_id` (tai lieu mong doi), `expected_service` (dich vu AWS), `forbidden_capability_ids` (danh sach capability khong duoc phep xuat hien), va `category` (phan loai muc do kho).

**Phan loai truy van theo muc do kho:**

| Loai truy van | Checks | Maturity | Tong | Mo ta |
|---|---|---|---|---|
| **exact** | 13 | 7 | 20 | Truy van chua chinh xac ten check/capability ID |
| **paraphrase** | 8 | 6 | 14 | Dien dat lai noi dung bang ngon ngu tu nhien |
| **risk** | 5 | 0 | 5 | Truy van mo ta rui ro hoac tinh huong bao mat |
| **semantic_hard** | 15 | 6 | 21 | Truy van ngu nghia phuc tap, khong chua tu khoa truc tiep |
| **Tong** | **41** | **19** | **60** | |

- **exact**: Danh gia kha nang khop chinh xac, ky vong he thong dat gan 100%.
- **paraphrase**: Danh gia kha nang hieu ngu nghia khi nguoi dung dien dat khac so voi ten ky thuat.
- **risk**: Danh gia kha nang lien ket tu mo ta rui ro den security check phu hop.
- **semantic_hard**: Loai kho nhat — truy van mo ta van de o muc truu tuong cao, khong chua tu khoa truc tiep. Day la thuoc do kha nang hieu ngu nghia sau cua he thong.

**Pham vi dich vu AWS:** Tap du lieu bao phu 6 dich vu AWS pho bien: S3, IAM, EC2, RDS, CloudTrail, KMS.

### 6.1.3 Cau hinh thuc nghiem

| Tham so | Gia tri | Mo ta |
|---|---|---|
| Top-k | 5 | So luong tai lieu tra ve cho moi truy van |
| Retrieval mode | hybrid | Ket hop BM25 va vector search |
| RRF k | 60 | Tham so Reciprocal Rank Fusion |
| Search multiplier | 3x | Truy hoi 3 x top_k ung vien truoc khi rerank |
| Embedding model | all-MiniLM-L6-v2 | Mo hinh vector embedding (384 chieu) |
| Reranker model | ms-marco-MiniLM-L-6-v2 | Cross-encoder cho giai doan reranking |
| Service match bonus | +0.03 | Diem thuong khi service khop |
| Domain match bonus | +0.02 | Diem thuong khi domain khop |

### 6.1.4 Bo tieu chi danh gia phat hanh (Release Criteria)

He thong dinh nghia **13 tieu chi release** thuoc 5 nhom. He thong chi dat trang thai "release-ready" khi tat ca tieu chi deu duoc thoa man.

| # | Tieu chi | Nguong | Nhom |
|---|---|---|---|
| 1 | checks_top1_accuracy_min | >= 0.60 | Retrieval Quality |
| 2 | checks_top5_accuracy_min | >= 0.80 | Retrieval Quality |
| 3 | maturity_top1_accuracy_min | >= 0.60 | Retrieval Quality |
| 4 | maturity_top5_accuracy_min | >= 0.80 | Retrieval Quality |
| 5 | combined_mrr_min | >= 0.70 | Retrieval Quality |
| 6 | combined_ndcg5_min | >= 0.75 | Retrieval Quality |
| 7 | forbidden_capability_rate_max | <= 0.00 | Safety |
| 8 | empty_bundle_rate_max | <= 0.00 | Safety |
| 9 | service_precision_min | >= 0.85 | Safety |
| 10 | average_latency_ms_max | <= 5000 ms | Performance |
| 11 | latency_p90_ms_max | <= 6000 ms | Performance |
| 12 | robustness_gap_pp_max | <= 90 pp | Robustness |
| 13 | confidence_ece_max | <= 0.20 | Calibration |

---

## 6.2 Chi so danh gia (Evaluation Metrics)

### 6.2.1 Chat luong truy hoi (Retrieval Quality)

- **Hit@k (Top-k Accuracy)**: Ty le truy van co tai lieu dung xuat hien trong top-k ket qua. Danh gia tai k = 1 (do chinh xac cao nhat) va k = 5 (do bao phu).

- **MRR (Mean Reciprocal Rank)**: Trung binh dao cua vi tri tai lieu dung dau tien. MRR = 1.0 khi tai lieu dung luon o vi tri 1; MRR giam khi tai lieu dung xuat hien o vi tri thap hon. Cong thuc:

  `MRR = (1/N) * sum(1/rank_i)` voi rank_i la vi tri dau tien cua tai lieu dung trong truy van thu i.

- **NDCG@5 (Normalized Discounted Cumulative Gain)**: Do luong chat luong xep hang co tinh den vi tri, phat nhung tai lieu dung o vi tri thap nang hon. Gia tri tu 0 den 1, voi 1.0 la xep hang hoan hao.

- **MAP@5 (Mean Average Precision)**: Trung binh do chinh xac tai moi vi tri co tai lieu lien quan. Ket hop ca do chinh xac va do bao phu vao mot chi so duy nhat.

### 6.2.2 Do ben (Robustness)

- **Per-category Accuracy**: Top-1 accuracy tinh rieng cho tung loai truy van (exact, paraphrase, risk, semantic_hard), giup nhan dien diem manh va diem yeu cua he thong theo muc do phuc tap cua truy van.

- **Robustness Gap**: Khoang cach giua accuracy cao nhat va thap nhat theo category, tinh bang diem phan tram (percentage points). Gap cang nho, he thong cang on dinh tren nhieu loai truy van.

  `gap_pp = (best_category_accuracy - worst_category_accuracy) * 100`

### 6.2.3 An toan (Safety)

- **Forbidden Capability Rate**: Ty le truy van ma ket qua tra ve chua capability bi cam (ngoai pham vi yeu cau). Yeu cau bang 0% de dam bao he thong khong tra ve thong tin sai lech.

- **Service Precision**: Ty le tai lieu top-1 co service trung voi service duoc hoi. Danh gia kha nang he thong phan biet dung dich vu AWS trong ket qua tra ve.

### 6.2.4 Hieu nang (Performance)

- **Latency Percentiles (p50, p90, p99)**: Phan bo thoi gian xu ly truy van. P50 la median, P90 cho biet 90% truy van duoc xu ly duoi nguong nay, P99 phan anh worst-case.

### 6.2.5 Do tin cay confidence (Calibration)

- **ECE (Expected Calibration Error)**: Do sai lech giua confidence score ma he thong tra ve va ty le truy hoi thanh cong thuc te. He thong chia confidence thanh 3 bin (high >= 0.8, medium 0.5-0.8, low < 0.5) va so sanh confidence voi accuracy thuc.

  `ECE = sum(|bin_size/N| * |accuracy_i - confidence_i|)` voi moi bin.

  ECE = 0 la hoan hao (confidence phan anh chinh xac xac suat thanh cong).

### 6.2.6 Danh gia reranker (Reranker Impact)

- **Reranker Lift**: So sanh MRR va NDCG truoc va sau khi ap dung cross-encoder reranking. Phan loai tung truy van thanh improved, degraded, hoac unchanged de danh gia hieu qua thuc te cua reranker tren toan bo dataset.

---

## 6.3 Ket qua thuc nghiem (Results)

### 6.3.1 Chat luong truy hoi tong the

**Ket qua tong hop (Combined):**

| Metric | Gia tri |
|---|---|
| Top-1 Accuracy | 71.67% (43/60) |
| Top-5 Accuracy | 85.00% (51/60) |
| MRR | 0.7728 |
| NDCG@5 | 0.7924 |
| MAP@5 | 0.7728 |

He thong dat ty le truy hoi dung tai vi tri dau tien la 71.67%, tang len 85% khi mo rong den top-5. Dieu nay cho thay da so cac tai lieu dung deu xuat hien trong top-5 ket qua, du diem moi mot so truong hop chua duoc xep hang o vi tri cao nhat.

**So sanh giua hai bo kiem tra:**

| Metric | Checks (41 cases) | Maturity (19 cases) | Chenh lech |
|---|---|---|---|
| Top-1 | 63.41% | 89.47% | +26.06 pp |
| Top-5 | 80.49% | 94.74% | +14.25 pp |
| MRR | 0.7114 | 0.9053 | +0.1939 |
| NDCG@5 | 0.7355 | 0.9151 | +0.1796 |

Maturity search dat hieu suat cao hon dang ke so voi check search tren tat ca cac chi so. Nguyen nhan chinh:
- Tap maturity co 19 tai lieu voi ngu nghia ro rang, it nham lan giua cac tai lieu.
- Tap checks co hon 400 tai lieu, nhieu tai lieu co noi dung tuong tu nhau (VD: nhieu check lien quan den public access cua S3), gay kho khan cho viec phan biet.

**Phan tich theo dich vu (Checks):**

| Service | Cases | Top-1 | Top-5 | Service Correct |
|---|---|---|---|---|
| S3 | 10 | 8 (80%) | 9 (90%) | 10/10 |
| IAM | 9 | 5 (56%) | 7 (78%) | 9/9 |
| EC2 | 9 | 4 (44%) | 7 (78%) | 8/9 |
| RDS | 5 | 4 (80%) | 4 (80%) | 4/5 |
| CloudTrail | 5 | 2 (40%) | 3 (60%) | 3/5 |
| KMS | 3 | 3 (100%) | 3 (100%) | 3/3 |

KMS va S3 dat hieu suat tot nhat. CloudTrail co hieu suat thap nhat (Top-1 chi 40%), phan anh su kho khan khi truy van ve audit logging thuong chua tu khoa chung chung, de nham lan voi cac dich vu khac.

### 6.3.2 Phan tich do ben (Robustness)

**Checks — theo loai truy van:**

| Category | Cases | Top-1 Rate | MRR | NDCG@5 |
|---|---|---|---|---|
| exact | 18 | 100.0% | 1.0000 | 1.0000 |
| paraphrase | 9 | 55.6% | 0.7593 | 0.8214 |
| risk | 6 | 33.3% | 0.4722 | 0.5218 |
| semantic_hard | 8 | 12.5% | 0.1875 | 0.2039 |

**Maturity — theo loai truy van:**

| Category | Cases | Top-1 Rate | MRR | NDCG@5 |
|---|---|---|---|---|
| exact | 7 | 100.0% | 1.0000 | 1.0000 |
| paraphrase | 6 | 100.0% | 1.0000 | 1.0000 |
| semantic_hard | 6 | 66.7% | 0.7000 | 0.7312 |

**Robustness Gap:** 87.5 percentage points (exact 100% --> semantic_hard 12.5% o checks).

He thong dat hieu suat tuyet doi voi exact query (100% tren ca hai bo), cho thay co che BM25 exact match hoat dong rat hieu qua. Tuy nhien, hieu suat giam manh theo muc do phuc tap cua truy van. Dac biet, semantic_hard trong checks chi dat 12.5% Top-1, cho thay mo hinh embedding `all-MiniLM-L6-v2` co han che trong viec hieu truy van truu tuong trong mien cloud security.

### 6.3.3 Danh gia an toan (Safety)

| Metric | Gia tri | Nguong | Ket qua |
|---|---|---|---|
| Forbidden capability rate | 0.00% | <= 0% | PASS |
| Empty bundle rate | 0.00% | <= 0% | PASS |
| Service precision | 90.2% | >= 85% | PASS |

He thong dat **0% vi pham forbidden** — khong co truy van nao tra ve tai lieu ngoai pham vi cho phep. Day la ket qua cua co che Product Entity Gate loc hieu qua cac tai lieu lien quan den dich vu khong duoc yeu cau.

Service precision dat 90.2%, vuot nguong 85%. Cac truong hop tai lieu top-1 khong dung service chu yeu xay ra voi truy van semantic_hard, khi he thong tra ve tai lieu dung ve noi dung nhung thuoc dich vu khac.

### 6.3.4 Hieu nang he thong (Performance)

| Percentile | Gia tri |
|---|---|
| Mean | 4,041 ms |
| P50 (Median) | 4,029 ms |
| P90 | 5,724 ms |
| P99 | 6,926 ms |

Latency trung binh dat 4,041 ms, nam trong nguong 5,000 ms. P90 dat 5,724 ms, nam trong nguong 6,000 ms. Thoi gian xu ly tuong doi cao do pipeline bao gom nhieu giai doan (hybrid retrieval, reranking, metadata bonus), nhung van chap nhan duoc trong ngu canh su dung bat dong bo cua he thong agent — noi RAG cung cap context cho agent xu ly, khong yeu cau phan hoi tuc thoi.

### 6.3.5 Reranker Impact va Confidence Calibration

**Reranker Lift (Checks, 41 cases):**

| Metric | Truoc reranker | Sau reranker | Lift |
|---|---|---|---|
| MRR | 0.2549 | 0.2724 | +0.0175 |
| NDCG@5 | 0.2888 | 0.2965 | +0.0076 |

- Cases improved: 4/41 (9.8%)
- Cases degraded: 3/41 (7.3%)
- Cases unchanged: 34/41 (82.9%)

Reranker chi cai thien nhe voi MRR lift +0.0175. Phan lon truy van (82.9%) khong thay doi thu hang sau reranking, cho thay reranker co tac dong han che trong truong hop nay. Luu y: cac gia tri MRR truoc/sau reranker nay duoc tinh tren tap ung vien semantic (khong bao gom exact match), nen gia tri tuyet doi thap hon MRR tong the.

**Maturity:** Reranker khong co tac dong (0 cases improved), do phan lon truy van maturity da duoc xu ly tot boi exact match va RRF merge.

**Confidence Calibration:**

| Route | ECE | Calibrated? |
|---|---|---|
| Combined | 0.1133 | Chua hoan toan |
| check_search | 0.1866 | Chua hoan toan |
| maturity_search | 0.2132 | Chua hoan toan |

Phan tich chi tiet bin confidence (Combined):

| Bin | Count | Accuracy thuc | Ky vong | Calibrated? |
|---|---|---|---|---|
| High (>= 0.8) | 48 | 79.2% | >= 80% | Chua dat (sai lech nho) |
| Medium (0.5-0.8) | 1 | 100% | 50-80% | Over-confident |
| Low (< 0.5) | 11 | 36.4% | < 50% | Dat |

He thong co xu huong gan nhan "high confidence" cho da so truy van (48/60), nhung accuracy thuc o bin high chi dat 79.2% (thap hon nguong 80%). ECE tong the la 0.1133, dat nguong release (< 0.20), nhung cho thay he thong chua hoan toan calibrated — dac biet confidence scores chua phan anh chinh xac do kho cua truy van.

### 6.3.6 Ket luan theo tieu chi release

| # | Tieu chi | Nguong | Thuc te | Ket qua |
|---|---|---|---|---|
| 1 | checks_top1_accuracy_min | >= 0.60 | 0.6341 | PASS |
| 2 | checks_top5_accuracy_min | >= 0.80 | 0.8049 | PASS |
| 3 | maturity_top1_accuracy_min | >= 0.60 | 0.8947 | PASS |
| 4 | maturity_top5_accuracy_min | >= 0.80 | 0.9474 | PASS |
| 5 | combined_mrr_min | >= 0.70 | 0.7728 | PASS |
| 6 | combined_ndcg5_min | >= 0.75 | 0.7924 | PASS |
| 7 | forbidden_capability_rate_max | <= 0.00 | 0.0000 | PASS |
| 8 | empty_bundle_rate_max | <= 0.00 | 0.0000 | PASS |
| 9 | service_precision_min | >= 0.85 | 0.9020 | PASS |
| 10 | average_latency_ms_max | <= 5000 | 3997.34 | PASS |
| 11 | latency_p90_ms_max | <= 6000 | 4671.75 | PASS |
| 12 | robustness_gap_pp_max | <= 90 | 87.50 | PASS |
| 13 | confidence_ece_max | <= 0.20 | 0.1866 | PASS |

**Ket qua: 13/13 tieu chi dat PASS.** He thong dat trang thai san sang trien khai (release-ready) theo bo tieu chi da dinh nghia.

---

## 6.4 Thao luan (Discussion)

### 6.4.1 Diem manh

**Exact match hoat dong hoan hao.** He thong dat 100% Top-1 accuracy cho cac truy van exact tren ca hai bo kiem tra. Co che ket hop BM25 lexical search voi exact match bonus (2.0 diem) dam bao truy van chua dung ten ky thuat luon tra ve ket qua chinh xac. Day la dac tinh quan trong trong moi truong production, noi agent thuong truyen truc tiep check ID hoac capability ID.

**Maturity search dat hieu suat cao.** Voi MRR = 0.9053 va Top-5 = 94.7%, maturity route xu ly tot ca truy van paraphrase (100% Top-1). Tap tai lieu maturity co kich thuoc nho (19 capability) voi ngu nghia phan biet ro rang, giup vector search hoat dong hieu qua.

**An toan tuyet doi.** Forbidden capability rate = 0% va service precision = 90.2% cho thay Product Entity Gate va metadata verification hoat dong dung nhu thiet ke. He thong khong bao gio tra ve tai lieu ngoai pham vi cho phep.

### 6.4.2 Han che

**Robustness gap lon (87.5pp).** Day la han che lon nhat cua he thong. Semantic_hard queries trong checks chi dat 12.5% Top-1, cho thay mo hinh embedding `all-MiniLM-L6-v2` (384 chieu, general-purpose) co han che trong viec hieu truy van truu tuong trong mien cloud security chuyen biet. Vi du: truy van "prevent credential theft via instance metadata endpoint" khong tra ve dung check `ec2_launch_template_imdsv2_required` vi khong co su trung khop tu khoa truc tiep.

**Reranker cai thien han che.** Cross-encoder chi cai thien 4/41 case (MRR lift +0.0175). Nguyen nhan co the la mo hinh `ms-marco-MiniLM-L-6-v2` duoc huan luyen tren du lieu web search tong quat, khong du chuyen biet cho mien cloud security. Ngoai ra, khi bo ung vien tu giai doan truoc da khong chua tai lieu dung, reranker khong the cai thien ket qua.

**Calibration chua hoan toan.** He thong gan "high confidence" cho 80% truy van (48/60), nhung accuracy thuc chi 79.2%. Dac biet, maturity_search co ECE = 0.2132 (vuot nguong 0.20 o muc route), cho thay confidence score chua phan anh dung do kho cua truy van. Dieu nay co the gay hieu lam cho agent phia sau khi dua quyet dinh dua tren confidence.

### 6.4.3 Huong cai thien

**Tang cuong semantic retrieval:**
- Su dung mo hinh embedding chuyen biet cho mien cloud security (fine-tuned tren du lieu AWS documentation) thay vi mo hinh general-purpose.
- Bo sung query expansion — mo rong truy van voi cac tu dong nghia trong mien chuyen biet truoc khi thuc hien vector search.

**Cai thien ranking:**
- Fine-tune cross-encoder reranker tren du lieu (query, check) cua he thong de tang hieu qua reranking trong mien chuyen biet.
- Dieu chinh trong so metadata bonus dua tren phan tich loi de uu tien ket qua chinh xac hon.

**Cai thien calibration:**
- Ap dung Platt scaling hoac temperature scaling tren confidence score de giam ECE.
- Ket hop confidence score voi thong tin bo sung (so luong ung vien, khoang cach diem giua cac ket qua) de tang do tin cay.

**Mo rong tap danh gia:**
- Tang so luong test case, dac biet cho nhom semantic_hard va risk, de co danh gia tin cay hon ve thong ke.
- Bo sung test case cho cac dich vu AWS khac ngoai 6 dich vu hien tai.
