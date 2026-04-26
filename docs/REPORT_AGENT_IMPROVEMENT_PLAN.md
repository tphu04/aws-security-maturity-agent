# Report Agent Quality Overhaul — Implementation Plan

**Version:** 2.0 (Revised after review)
**Status:** Draft — Pending final confirmation
**Scope:** Cải thiện **correctness** của Report Agent output trước khi xây Evaluation Framework
**Timeline:** ~7 ngày core + 2 ngày optional
**Bối cảnh:** Đồ án tốt nghiệp

---

## 0. Changelog vs v1

**v2 — Correctness-first rework** dựa trên feedback:

1. **NEW Phase 1: Scope Generalization (De-S3-bias)** — đặt lên ưu tiên số 1. Discovery lộ ra bias sâu hơn chỉ prompt: **`report_agent.py:637-682` hardcode `total_buckets`/`bucket_list`/`_looks_like_bucket`** — ảnh hưởng data aggregation, không chỉ prompt wording. Nếu scan IAM/EC2/CloudTrail, toàn bộ report lệch.

2. **NEW Phase 5: Output Validation Layer** — mandatory gate trước render. `FactValidator` hiện tại chỉ check numbers. Mở rộng thành `ReportValidator` check 4 tiêu chí: off-scope service, hallucinated numbers, wrong resource term, ungrounded capability.

3. **REVISED Success Metrics** — bỏ "13/15 prompts use RAG" (vanity). Center vào correctness: off-scope mention rate, hallucinated number rate, wrong-term rate, ungrounded recommendation rate.

4. **REPRIORITIZED Maturity RAG Integration** — chuyển từ Phase 4 core xuống Phase 7 OPTIONAL. Lý do: maturity prompts không phải nơi bias/hallucination xảy ra nhiều nhất. Exec summary + Fail analysis + Recommendations mới là critical path.

5. **REMOVED premature optimization** — Phase Prompt Optimization chuyển xuống OPTIONAL. Fix correctness trước, tune hiệu năng sau khi có evaluation baseline.

---

## 1. Nguyên tắc triển khai

1. **Correctness > Coverage** — Thà 7/15 prompt grounded đúng còn hơn 15/15 nhưng vẫn bịa
2. **Generalize first, specialize later** — Không hardcode service/resource giả định
3. **Gate before render** — Validation là hạng mục bắt buộc, không optional
4. **Fix từ gốc, không patch** — Sửa ở normalizer/aggregator thay vì workaround downstream
5. **Dependency-aware phasing** — Mỗi phase build trên kết quả phase trước
6. **Testable at every phase** — Không chờ cuối mới test
7. **Backward-safe schema changes** — Thêm field mới, không xóa; commit riêng để revert được

---

## 2. Discovery Findings

### 2.1 S3-Bias Scope (NEW trong v2)

Bias ăn sâu ở 2 layer:

**Prompt layer** (`llm_writer.py`):
- L196: "báo cáo đánh giá bảo mật Amazon S3"
- L209-210, L218, L228, L263-266, L276, L282, L284 — hardcoded "bucket"/"S3"

**Data aggregation layer** (`report_agent.py`):
- L637-682: Hàm `_compute_env_scope()` (hoặc tương đương) hardcode `total_buckets`, `bucket_list`, `_looks_like_bucket()` — đây mới là blocker chính

### 2.2 RAG Pipeline Issues

| # | Vấn đề | Nơi | Mức độ |
|---|--------|-----|--------|
| 1 | `Remediation.Recommendation.Text` bị drop trong normalizer | `app/ingestion/normalizers.py` | Critical |
| 2 | `recommended_practices` fallback ra text rác | `bundle_factory.py:210-239` | Critical |
| 3 | Truncation 200 chars cắt giữa câu | `bundle_factory.py:320` | High |
| 4 | `ReportBundle` không surface maturity capability details | `core/models.py:274` | High |
| 5 | `_build_rag_knowledge()` tạo blob phẳng cho 7 section khác nhau | `report_agent.py:580` | High |
| 6 | `_OUTPUT_CONSTRAINTS` append 15× mỗi report | `llm_writer.py:17,137` | Medium |
| 7 | `write_post_remediation_analysis` dump toàn bộ JSON | `llm_writer.py:608` | Medium |
| 8 | Format `[SEVERITY]` xung đột với `_PLACEHOLDER` regex | `report_agent.py:596` | Medium |
| 9 | Không filter `mapping_confidence` | `bundle_factory.py` | Medium |

### 2.3 Missing Validation

- `FactValidator` hiện tại chỉ check numbers
- Không chặn off-scope service mentions
- Không chặn wrong resource terminology
- Không chặn capability không có trong evidence

### 2.4 Tin tốt từ Discovery

- `MaturityCapabilityDoc` đã có đủ field rich (`risk_explanation`, `guidance`, `recommended_practices`)
- Helper `_extract_recommendation_text()` đã tồn tại, chỉ chưa wire
- Schema `BundleCapability` đã thiết kế đúng, chỉ là `ReportBundle` chưa dùng
- Field mới không cần rebuild embeddings

---

## 3. Kiến trúc Plan (v2)

```
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 0 — Baseline Capture                              (0.5 ngày) │
│   Snapshot output hiện tại cho before/after                        │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 1 — Scope Generalization (De-S3-bias)              (1 ngày) │ ★
│   Remove hardcoded S3/bucket terms; dynamic scope detection        │
│   CRITICAL: gốc của wrong-service reporting                        │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 2 — Data Pipeline Hardening                        (1 ngày) │
│   ProwlerCheckDoc + normalizer wire + regenerate                   │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 3 — Bundle Factory Rebuild                         (1 ngày) │
│   ReportBundle schema + utilities + rewrite                        │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 4 — Agent Layer Refactor                           (1 ngày) │
│   View-based RAG + SystemMessage + prompt hygiene                  │
│   Focus: exec_summary, fail_analysis, pass_analysis, recommend     │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 5 — Output Validation Layer                        (1 ngày) │ ★
│   ReportValidator gate trước render                                │
│   Chặn: off-scope, hallucinated, wrong-term, ungrounded            │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 6 — Testing & Before/After Validation              (1 ngày) │
│   Integration + Smoke + Manual review với rubric                   │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 7 — Maturity RAG Integration         [OPTIONAL]  (0.5 ngày) │
│   Chỉ làm sau khi core stable                                      │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 8 — Prompt Optimization              [OPTIONAL]  (0.5 ngày) │
│   Chỉ làm sau khi có evaluation baseline                           │
├─────────────────────────────────────────────────────────────────────┤
│ PHASE 9 — Documentation                                 (0.5 ngày) │
└─────────────────────────────────────────────────────────────────────┘
                                         Core: ~6.5 ngày
                                         Optional: +1 ngày
                                         Docs: +0.5 ngày
                                         Total: ~7-8 ngày
```

★ = Phase mới thêm/đổi thứ tự theo feedback v2

---

## 4. Chi tiết từng Phase

### Phase 0 — Baseline Capture

**Mục tiêu:** Snapshot output hiện tại để làm "before" cho so sánh + phát hiện bias.

#### Tasks
- [ ] Tạo `tests/fixtures/report_baseline/` với **7 scenario** (mở rộng so với v1):
  - **A:** S3-only all-pass
  - **B:** S3-only all-fail
  - **C:** S3-only mixed
  - **D:** S3 zero-findings (edge)
  - **E:** S3 multi-bucket intensive
  - **F (NEW):** IAM-only findings — test S3 bias
  - **G (NEW):** Multi-service mixed (S3 + IAM + EC2) — test scope detection
- [ ] Chạy Report Agent hiện tại trên mỗi fixture → lưu HTML output
- [ ] Log RAG response JSON cho mỗi fixture
- [ ] **Document quan sát bias:** cho mỗi fixture F và G, ghi rõ những chỗ report nhắc sai service/resource

#### Deliverables
- `tests/fixtures/report_baseline/input/{A..G}.json`
- `tests/fixtures/report_baseline/output_before/{A..G}.html`
- `tests/fixtures/report_baseline/rag_response/{A..G}.json`
- `tests/fixtures/report_baseline/observations_v0.md` — manual notes về bias
- `scripts/capture_baseline.py`

#### Acceptance Criteria
- ✅ 7 HTML baseline lưu thành công, không exception
- ✅ Với fixture F (IAM-only): observations ghi rõ chỗ output nhắc "S3"/"bucket" sai
- ✅ Với fixture G (multi-service): observations ghi rõ chỗ output nhắc 1 service trong khi data có nhiều
- ✅ Test runner reproducible (temperature=0)

**Thesis value:** Observations v0 + v1 (sau plan) sẽ là bằng chứng cải thiện cho chương Results.

---

### Phase 1 — Scope Generalization (De-S3-bias) ★

**Mục tiêu:** Report Agent phát hiện scope từ findings, không giả định service. Prompts và aggregation layer dùng dynamic terminology.

#### 1.1 — Scope detection utility

**File:** `pdca/agents/report_module/scope_detector.py` (MỚI)

```python
from collections import Counter
from typing import Optional

SERVICE_DISPLAY = {
    "s3": "Amazon S3",
    "iam": "AWS IAM",
    "ec2": "Amazon EC2",
    "cloudtrail": "AWS CloudTrail",
    "rds": "Amazon RDS",
    "lambda": "AWS Lambda",
    "kms": "AWS KMS",
    "cloudfront": "Amazon CloudFront",
    # thêm khi cần
}

RESOURCE_TERMS = {
    "s3": ("bucket", "buckets"),
    "iam": ("role/policy", "roles and policies"),
    "ec2": ("instance", "instances"),
    "cloudtrail": ("trail", "trails"),
    "rds": ("database instance", "database instances"),
    "lambda": ("function", "functions"),
    "kms": ("key", "keys"),
    "cloudfront": ("distribution", "distributions"),
}

GENERIC_FALLBACK = {
    "display": "AWS Infrastructure",
    "term_singular": "resource",
    "term_plural": "resources",
}

def detect_scope(findings: list, env: dict = None) -> dict:
    """Detect primary service and resource terminology from findings.

    Returns:
        {
            "primary_service": str | None,
            "service_list": List[str],
            "is_multi_service": bool,
            "service_display": str,          # "Amazon S3" | "AWS Infrastructure"
            "resource_term": str,             # "bucket" | "resource"
            "resource_term_plural": str,      # "buckets" | "resources"
        }
    """
    services = Counter()
    for f in findings or []:
        svc = f.get("service") or _infer_service_from_check_id(f.get("check_id"))
        if svc:
            services[svc.lower()] += 1

    if not services:
        return _empty_scope()

    primary = services.most_common(1)[0][0]
    service_list = list(services.keys())
    is_multi = len(service_list) > 1

    # Threshold: >70% findings thuộc 1 service → specific
    dominant = services[primary] / sum(services.values()) > 0.7

    if is_multi and not dominant:
        return {
            "primary_service": None,
            "service_list": service_list,
            "is_multi_service": True,
            "service_display": GENERIC_FALLBACK["display"],
            "resource_term": GENERIC_FALLBACK["term_singular"],
            "resource_term_plural": GENERIC_FALLBACK["term_plural"],
        }

    term_s, term_p = RESOURCE_TERMS.get(primary, ("resource", "resources"))
    return {
        "primary_service": primary,
        "service_list": service_list,
        "is_multi_service": is_multi,
        "service_display": SERVICE_DISPLAY.get(primary, f"AWS {primary.upper()}"),
        "resource_term": term_s,
        "resource_term_plural": term_p,
    }
```

#### 1.2 — Generalize environment aggregation

**File:** `pdca/agents/report_agent.py:637-682`

Refactor từ bucket-specific sang service-aware:

```python
# TRƯỚC (hardcoded):
def _compute_env_facts(self, env, findings):
    total_buckets = ...
    bucket_list = ...
    return {"total_buckets": total_buckets, "bucket_list": bucket_list, ...}

# SAU (scope-aware):
def _compute_env_facts(self, env, findings, scope):
    term_plural = scope["resource_term_plural"]
    service = scope["primary_service"]

    distinct_resources = self._extract_distinct_resources(findings, service)
    env_resources = env.get(term_plural, []) or env.get("buckets", [])  # backward compat

    if env_resources:
        total = len(env_resources)
        resource_list = env_resources
        source = "env"
    elif distinct_resources:
        total = len(distinct_resources)
        resource_list = sorted(distinct_resources)
        source = "findings"
    else:
        total = 0
        resource_list = []
        source = "none"

    return {
        "total_resources": total,
        "resource_list": resource_list,
        "resource_term_plural": term_plural,
        "resource_count_source": source,
        # Backward compat (deprecated, remove sau khi confirm không còn chỗ dùng):
        "total_buckets": total if service == "s3" else 0,
        "bucket_list": resource_list if service == "s3" else [],
    }

def _extract_distinct_resources(self, findings, service):
    """Service-aware resource extraction."""
    resources = set()
    for f in findings:
        res = f.get("resource") or f.get("resource_id")
        if not res:
            continue
        if self._is_valid_resource(res, service):
            resources.add(res)
    return resources

def _is_valid_resource(self, res: str, service: str) -> bool:
    """Thay thế _looks_like_bucket với service-aware heuristic."""
    if service == "s3":
        # Account ID là số → không phải bucket
        return not res.isdigit() and not res.startswith("arn:")
    elif service == "iam":
        return res.startswith("arn:aws:iam") or "/" in res
    elif service == "ec2":
        return res.startswith("i-") or res.startswith("arn:aws:ec2")
    # Default: accept any non-empty
    return bool(res)
```

#### 1.3 — Parameterize prompts

**File:** `pdca/agents/report_module/llm_writer.py`

Thay tất cả hardcoded "Amazon S3"/"bucket" bằng scope variables:

```python
def write_exec_summary(self, pre, sysdata, meta, scope: dict,
                       rag_knowledge: str = "", fail_findings: list = None):
    service_display = scope["service_display"]
    resource_plural = scope["resource_term_plural"]

    prompt = f"""
Bạn là Senior Cloud Security Consultant.
Nhiệm vụ: viết **Executive Summary** cho báo cáo đánh giá bảo mật
{service_display} gửi lên C-Level (CTO/CISO).

===== DỮ LIỆU ĐẦU VÀO =====
- Bối cảnh hệ thống: {sysdata}
- Kết quả quét (Pre-remediation): {pre}
- Meta & User Notes: {meta}
{rag_block}
{fail_block}

===== ĐỊNH NGHĨA THUẬT NGỮ =====
- "Finding": kết quả kiểm tra cấu hình (bao gồm cả PASS và FAIL).
- "Lỗi" (Issue): CHỈ các finding có trạng thái FAIL.
- TUYỆT ĐỐI KHÔNG gọi tổng số findings là tổng số lỗi.
- TUYỆT ĐỐI KHÔNG gọi số findings là số {resource_plural} — một {resource_term} có thể có nhiều findings.
- Số {resource_plural} = sysdata.total_resources.

===== HARD CONSTRAINTS =====
- KHÔNG tạo tiêu đề báo cáo.
- KHÔNG nhắc dịch vụ AWS khác ngoài scope: {service_display}
  (nếu scope là multi-service thì dùng thuật ngữ generic "AWS resources").
...
"""
```

Tương tự cho:
- `write_system_overview` — thay "Amazon S3" bằng `{service_display}`, "bucket" bằng `{resource_term}`
- Tất cả 15 prompts khác — grep kỹ tìm hardcoded terms

#### 1.4 — Update orchestrator

**File:** `pdca/orchestrator.py` hoặc wherever report_node gọi agent

```python
# Detect scope TRƯỚC khi build prompts
scope = detect_scope(
    findings=raw_pre_findings,
    env=state.get("environment_profile"),
)
state["scope"] = scope

# Pass scope xuống report agent
report_agent.run(state, scope=scope)
```

#### 1.5 — Update templates

**File:** `pdca/agents/report_module/template.py`

Template HTML có thể hardcode "S3 Bucket" ở header/labels → thay bằng dynamic từ `scope`.

#### Acceptance Criteria
- ✅ Fixture F (IAM-only): output không chứa "S3" hoặc "bucket"
- ✅ Fixture G (multi-service): output dùng "AWS resources"/"AWS Infrastructure"
- ✅ Fixture A-E (S3): output vẫn đúng về S3 (regression safe)
- ✅ `_looks_like_bucket` đã được replace/deprecate
- ✅ Tất cả occurrence "Amazon S3" trong llm_writer.py đã parameterize
- ✅ Unit test `test_scope_detector.py` cover 5+ case (S3-only, IAM-only, multi, empty, edge)

#### Risks & Mitigation
| Risk | Mitigation |
|------|------------|
| Service không có trong `SERVICE_DISPLAY` dict | Default fallback "AWS {SERVICE}", log warning |
| `_is_valid_resource` heuristic không cover hết service | Default accept non-empty, iterative improvement |
| Template HTML break khi đổi label | Smoke test Phase 6 với fixture F, G |

---

### Phase 2 — Data Pipeline Hardening

**Mục tiêu:** `Remediation.Recommendation.Text` preserve qua normalization → bundle dùng được.

#### 2.1 — Extend ProwlerCheckDoc schema

**File:** `RAG/app/core/models.py`

```python
class ProwlerCheckDoc(BaseDoc):
    ...
    remediation: str                                    # giữ nguyên (code section)
    remediation_recommendation: Optional[str] = None    # MỚI: Recommendation.Text
    remediation_url: Optional[str] = None               # MỚI: Recommendation.Url
```

#### 2.2 — Wire normalizer helper

**File:** `RAG/app/ingestion/normalizers.py`

`_extract_recommendation_text()` đã tồn tại (line 593-607), chỉ cần gọi:

```python
# normalize_prowler_doc (~line 830)
remediation_dict = raw.get("Remediation", {})
remediation_code = _normalize_for_index(remediation_dict.get("Code", ""))
remediation_recommendation = _extract_recommendation_text(remediation_dict)
remediation_url = (remediation_dict.get("Recommendation") or {}).get("Url", "")

doc = ProwlerCheckDoc(
    ...
    remediation=remediation_code,
    remediation_recommendation=remediation_recommendation,
    remediation_url=remediation_url,
)
```

#### 2.3 — Surface trong metadata

**File:** `RAG/app/retrieval/pipeline.py` (`_extract_rich_metadata` ~L621)

```python
return {
    ...
    "remediation": doc.get("remediation"),
    "remediation_recommendation": doc.get("remediation_recommendation"),  # MỚI
    "remediation_url": doc.get("remediation_url"),                        # MỚI
}
```

#### 2.4 — Regenerate

```bash
cd c:/Users/trung/Desktop/DoAn/RAG
cp -r data/normalized data/normalized.backup-$(date +%Y%m%d)
python scripts/build_all.py
```

#### 2.5 — Validate tests

```bash
pytest tests/test_coverage_selector.py tests/test_context_build.py \
       tests/test_rag_contract.py tests/test_bundle_factory.py -v
```

#### Acceptance Criteria
- ✅ `normalized/prowler_checks.json` có `remediation_recommendation` không rỗng ≥ 90% checks
- ✅ Spot-check 5 checks: field chứa text actual ("Enable", "Apply"...), không phải stringified dict
- ✅ Existing tests pass
- ✅ Backup `data/normalized.backup-*` tồn tại để rollback

---

### Phase 3 — Bundle Factory Rebuild

**Mục tiêu:** `ReportBundle` surface `capability_details` + produce high-quality data.

#### 3.1 — Schema additions

**File:** `RAG/app/core/models.py`

```python
class ReportCapabilityDetail(BaseModel):
    capability_id: str
    capability_name: str
    domain: Optional[str] = None
    stage: Optional[str] = None
    summary: str                                # ≤500 chars sentence-truncated
    risk_explanation: Optional[str] = None
    recommendation: Optional[str] = None
    guidance_questions: List[str] = Field(default_factory=list)
    url: Optional[str] = None

class ReportBundle(BaseModel):
    primary_topics: List[str]
    key_findings: List[ReportFinding]
    control_themes: List[ReportCapability]
    recommended_practices: List[str]
    capability_details: List[ReportCapabilityDetail]  # MỚI
    confidence: Optional[str] = None
```

#### 3.2 — Utilities mới

**File:** `RAG/app/context/bundle_factory.py`

```python
def _truncate_at_sentence(text, max_chars=500):
    """Cắt tại . ; , gần nhất thay vì giữa từ."""

def _severity_rank(sev):
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
        (sev or "").lower(), 4
    )

def _filter_confident_mappings(mappings, min_level="medium"):
    """Filter theo mapping_confidence."""
```

#### 3.3 — Rewrite build_report_bundle

Key changes:
- `key_findings` sorted by severity desc
- `control_themes` filtered `confidence >= medium`
- `recommended_practices` từ `remediation_recommendation`, **không fallback ra mapping.rationale**
- `capability_details` populated với 4 field rich

#### 3.4 — Update confidence evaluation

`evaluate_bundle_confidence`:
- `capability_details` rỗng + consumer="report" → confidence=low
- `recommended_practices` < 3 → confidence=medium

#### 3.5 — Unit tests

**File:** `RAG/tests/test_bundle_factory.py` (extend)

- `test_severity_sorting`
- `test_confidence_filter`
- `test_sentence_truncation`
- `test_recommended_practices_no_rationale_leak`
- `test_capability_details_populated`

#### Acceptance Criteria
- ✅ `build_report_bundle()` validate pass `ReportBundle` pydantic
- ✅ `key_findings` sorted critical→low
- ✅ `control_themes` không chứa low-confidence mappings
- ✅ `recommended_practices` không chứa "Shared concepts:" hay "{'CLI':"
- ✅ `capability_details` có ≥ 80% items đầy đủ 3 field (risk, recommendation, guidance)
- ✅ ≥ 5 unit test mới pass

---

### Phase 4 — Agent Layer Refactor

**Mục tiêu:** Clean prompt injection + SystemMessage + compact.
**Focus:** exec_summary, pass_analysis, fail_analysis, recommendations (NOT maturity — để Phase 7).

#### 4.1 — View-based RAG formatter

**File:** `pdca/agents/report_module/rag_formatter.py` (MỚI)

```python
class RAGViewFormatter:
    def __init__(self, rag_context: dict, scope: dict):
        self.ctx = rag_context or {}
        self.scope = scope

    def for_executive(self) -> str:
        """Top 3 critical/high + 2-3 themes. Ngắn."""

    def for_fail_analysis(self) -> str:
        """Full findings + capability risk_explanation."""

    def for_pass_analysis(self) -> str:
        """Chỉ control_themes đã PASS."""

    def for_recommendations(self) -> str:
        """recommended_practices + capability recommendations."""

    def for_per_finding(self, check_id: str) -> dict:
        """Single finding's risk + remediation_recommendation."""
```

#### 4.2 — SystemMessage cho constraints

**File:** `llm_writer.py`

```python
SYSTEM_CONSTRAINTS = """Bạn tuân thủ các ràng buộc output:
- Không tạo tiêu đề mới (template đã có).
- Không ngôi thứ nhất (tôi, chúng tôi).
- Không placeholder [text ở đây].
- Không emoji.
- Nếu data = 0 hoặc rỗng: nêu sự thật và ngừng. Không suy đoán."""

def _ask(self, prompt, fallback, word_limit=300):
    try:
        res = self.llm.invoke([
            SystemMessage(content=SYSTEM_CONSTRAINTS +
                          f"\n- Tối đa {word_limit} từ."),
            HumanMessage(content=prompt),
        ])
    except (TypeError, AttributeError):
        # Fallback giữ pattern cũ nếu ChatOllama không support
        res = self.llm.invoke(SYSTEM_CONSTRAINTS + "\n\n" + prompt)
    ...
```

#### 4.3 — Fix bracket format

- `- [SEV]` → `- (SEV)` trong RAG block format
- `(ví dụ: "Báo Cáo...")` — đổi dấu quote tránh bracket

#### 4.4 — Compact write_post_remediation_analysis

```python
# TRƯỚC: json.dumps(data, indent=2) — dump tất cả
# SAU: extract chỉ field cần
compact = {
    "outcome": data.get("remediation_outcome", {}),
    "post_summary": data.get("post_summary", {}),
    "maturity_delta": (data.get("maturity_delta") or {}).get("overall", {}),
}
data_str = json.dumps(compact, indent=2, ensure_ascii=False)
```

#### 4.5 — Update rag_client + orchestrator

`rag_client.py` và `orchestrator._fetch_rag_for_report()` pass-through `capability_details`.

#### Acceptance Criteria
- ✅ Mỗi prompt giảm ≥ 100 tokens (SystemMessage dedup)
- ✅ Output không chứa `[CRITICAL]` bị eat
- ✅ Prompt `write_post_remediation_analysis` không có `tool_code`/`execution_output`
- ✅ 4 core prompt (exec/pass/fail/recommend) dùng RAG view khác nhau
- ✅ `RAGViewFormatter` có unit test riêng

---

### Phase 5 — Output Validation Layer ★

**Mục tiêu:** Mandatory gate trước render. Chặn output vi phạm scope/facts.

#### 5.1 — ReportValidator

**File:** `pdca/agents/report_module/validators.py` (MỚI, hoặc extend `llm_validator.py`)

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class ValidationIssue:
    section: str
    kind: str              # "off_scope", "hallucinated_number", "wrong_term", "ungrounded"
    evidence: str          # trích dẫn offending text
    details: str = ""

@dataclass
class ValidationResult:
    ok: bool
    issues: List[ValidationIssue] = field(default_factory=list)


class ReportValidator:
    """Validate LLM output trước render."""

    def __init__(self, scope: dict, evidence: dict):
        """
        scope: từ detect_scope() (service_list, primary_service, etc.)
        evidence: {
            "allowed_numbers": set,
            "allowed_services": set,
            "allowed_resource_terms": set,
            "allowed_capabilities": set,      # từ RAG capability_details
            "allowed_check_ids": set,
            "account_level_findings": set,    # check_ids là account-level
        }
        """
        self.scope = scope
        self.evidence = evidence

    def validate(self, text: str, section: str) -> ValidationResult:
        issues = []
        issues += self._check_off_scope_services(text, section)
        issues += self._check_hallucinated_numbers(text, section)
        issues += self._check_resource_terminology(text, section)
        issues += self._check_ungrounded_capabilities(text, section)
        return ValidationResult(ok=not issues, issues=issues)

    def _check_off_scope_services(self, text, section):
        """Flag if text mentions service not in scope."""
        allowed = self.evidence["allowed_services"]
        # AWS service names to watch for
        AWS_SERVICES = {
            "s3", "ec2", "iam", "rds", "lambda", "cloudtrail",
            "cloudfront", "kms", "sns", "sqs", "ecs", "eks",
            # ... full list
        }
        text_lower = text.lower()
        issues = []
        for svc in AWS_SERVICES:
            if svc not in allowed:
                # Use word boundary to avoid false positive
                pattern = r'\b' + re.escape(svc) + r'\b'
                if re.search(pattern, text_lower):
                    issues.append(ValidationIssue(
                        section=section,
                        kind="off_scope",
                        evidence=svc,
                        details=f"Service '{svc}' not in scope {allowed}",
                    ))
        return issues

    def _check_hallucinated_numbers(self, text, section):
        """Extend existing FactValidator logic."""
        # Reuse logic từ llm_validator.py FactValidator
        ...

    def _check_resource_terminology(self, text, section):
        """Flag 'bucket' if primary_service != s3, etc."""
        wrong_terms = {
            "bucket": self.scope.get("primary_service") != "s3",
            "instance": self.scope.get("primary_service") not in ("ec2", "rds"),
            "function": self.scope.get("primary_service") != "lambda",
            # ...
        }
        issues = []
        text_lower = text.lower()
        for term, is_wrong in wrong_terms.items():
            if is_wrong and re.search(r'\b' + term + r'\b', text_lower):
                issues.append(ValidationIssue(
                    section=section,
                    kind="wrong_term",
                    evidence=term,
                    details=f"Term '{term}' inappropriate for scope {self.scope['primary_service']}",
                ))
        return issues

    def _check_ungrounded_capabilities(self, text, section):
        """Flag capability names mentioned but not in RAG evidence."""
        allowed_caps = {c.lower() for c in self.evidence.get("allowed_capabilities", set())}
        # Look for capitalized multi-word phrases that look like capability names
        # Heuristic: "Block Public Access", "Zero Trust", etc.
        candidates = re.findall(
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\b', text
        )
        issues = []
        for cand in candidates:
            if cand.lower() not in allowed_caps and self._looks_like_capability(cand):
                issues.append(ValidationIssue(
                    section=section,
                    kind="ungrounded",
                    evidence=cand,
                    details=f"Capability '{cand}' not in RAG evidence",
                ))
        return issues
```

#### 5.2 — Wire vào LLM writer

```python
def _ask_validated_full(self, prompt, fallback, section, validator):
    text = self._ask(prompt, fallback)
    if not text or text == fallback:
        return text
    result = validator.validate(text, section)
    if not result.ok:
        logger.warning(
            f"[{section}] Validation failed: {[(i.kind, i.evidence) for i in result.issues]}"
        )
        return fallback
    return text
```

#### 5.3 — Gate pre-render ở report agent

```python
# report_agent.py
def _build_validator(self, scope, rag_context, findings):
    evidence = {
        "allowed_numbers": self._collect_numbers(findings, ...),
        "allowed_services": set(scope["service_list"]),
        "allowed_resource_terms": {scope["resource_term"], scope["resource_term_plural"]},
        "allowed_capabilities": {
            c.get("capability_name", "") for c in rag_context.get("capability_details", [])
        },
        "allowed_check_ids": {f.get("check_id") for f in findings},
        "account_level_findings": {
            f.get("check_id") for f in findings
            if self._is_account_level(f)
        },
    }
    return ReportValidator(scope, evidence)

def _validate_sections_pre_render(self, sections: dict, validator):
    all_issues = {}
    for name, content in sections.items():
        result = validator.validate(content, name)
        if not result.ok:
            all_issues[name] = result.issues
            # Log hoặc fallback based on policy
    if all_issues:
        self._log_validation_summary(all_issues)
    return all_issues
```

#### 5.4 — Integration vào pipeline

```python
# Trong ReportAgent.run()
validator = self._build_validator(scope, rag_context, findings)

# Khi gọi LLM writer methods, pass validator
exec_summary = self.llm.write_exec_summary(..., validator=validator)

# Sau khi build xong sections
issues = self._validate_sections_pre_render(sections, validator)
if issues:
    # Strategy: log + use fallback for violating sections
    sections = self._apply_fallback_for_violations(sections, issues)

# Chỉ render khi validation OK (hoặc đã fallback)
return self._render_template(sections)
```

#### 5.5 — Violation reports

**File:** `job_outputs/{job_id}/validation_report.json` (MỚI)

Lưu tất cả issues phát hiện để:
- Debug khi report output lỗi
- Data cho evaluation phase sau
- Thesis material (chứng minh validator hoạt động)

#### Acceptance Criteria
- ✅ Fixture F (IAM-only): validator flag mọi occurrence "S3" hoặc "bucket"
- ✅ Fixture G (multi-service): validator flag mọi hardcoded single-service mention
- ✅ Số bịa trong output: flag 100% khi gặp
- ✅ Capability không trong evidence: flag khi gặp
- ✅ Validator performance: ≤ 50ms overhead per section
- ✅ `validation_report.json` lưu đúng format cho mọi fixture

---

### Phase 6 — Testing & Before/After Validation

**Mục tiêu:** Assert không regression + verify improvement định lượng.

#### 6.1 — Unit tests

- `test_scope_detector.py` — 5+ case (Phase 1)
- `test_bundle_factory.py` extend (Phase 3)
- `test_rag_view_formatter.py` — mỗi view method (Phase 4)
- `test_report_validator.py` — mỗi check type (Phase 5)

#### 6.2 — Integration test

**File:** `tests/integration/test_report_rag_flow.py` (MỚI)

```python
def test_full_rag_to_bundle_flow():
    # RAGClient → bundle → schema check
    # Quality asserts: no rác text, sorted severity, capability_details present
```

#### 6.3 — Smoke test E2E với tất cả 7 fixtures

```python
@pytest.mark.parametrize("fixture", ["A","B","C","D","E","F","G"])
def test_report_generation_e2e(fixture):
    html = agent.run(load_fixture(fixture))
    assert html
    # Save to output_after/{fixture}.html

    # Validator check: fixture F không được chứa "S3", G không nhắc 1 service riêng
    if fixture == "F":
        assert "S3" not in html
        assert "bucket" not in html.lower()
    if fixture == "G":
        # Multi-service: không được nhắc service riêng lẻ dominant
        ...
```

#### 6.4 — Before/After Manual Review

**Rubric (1-5 mỗi tiêu chí, FOCUSED on correctness):**
1. **Scope correctness** — không nhắc service/resource sai (1=nhắc sai rất nhiều; 5=không sai gì)
2. **Factual accuracy** — số, severity, check ID đúng
3. **Grounding** — nội dung phản ánh input/RAG (không bịa)
4. **Coverage** — finding quan trọng được nhắc đủ
5. **Actionability** — recommendation cụ thể, bám finding

**Process:**
- Review pair (before/after) cho cả 7 fixture
- Score mỗi pair theo rubric
- Tính Δ per criterion
- **Target:** Δ ≥ +1 trên tiêu chí 1 (Scope) và 3 (Grounding) với fixture F, G

#### 6.5 — Quantitative improvement report

Tự động đo:
- Off-scope service mention count (before vs after)
- Wrong resource term count
- Validator issues count
- Số lần fallback template dùng

Output: `tests/fixtures/report_baseline/improvement_report.md`

#### Acceptance Criteria
- ✅ Tất cả existing tests pass
- ✅ ≥ 10 unit test mới pass
- ✅ ≥ 3 integration test mới pass
- ✅ Smoke test E2E: 7/7 fixtures không crash
- ✅ Fixture F output: `grep -ci "s3\|bucket"` giảm về 0 (hoặc chỉ ở log, không trong HTML)
- ✅ Fixture G output: không dominant single service
- ✅ Manual review: Δ ≥ +1 trên criterion 1 và 3

---

### Phase 7 — Maturity RAG Integration [OPTIONAL]

**Mục tiêu:** Ground 5 maturity prompts bằng `capability_details`.
**Điều kiện để làm:** Phase 1-6 đã xong và validator pass rate ≥ 90%.

#### Tasks (như v1)
- 4.1: wire `capability_details` vào `write_maturity_overview`
- 4.2: filter theo domain cho `write_domain_assessment`
- 4.3: prioritize low-score caps cho `write_maturity_roadmap`
- 4.4: `write_post_remediation_analysis_v2` + `write_action_plan`

**Có thể defer** nếu timeline gắt — maturity prompts không phải nơi bias/hallucination critical.

#### Acceptance Criteria
- ✅ Maturity sections nhắc đúng tên capability từ RAG
- ✅ Domain assessment filter đúng
- ✅ Roadmap có RAG recommendation cho low-score caps
- ✅ **Không regression** validator pass rate

---

### Phase 8 — Prompt Optimization [OPTIONAL]

**Mục tiêu:** Reduce token + simplify cho gemma3:4b.
**Điều kiện để làm:** Sau khi có evaluation baseline từ Phase 6.

**Tasks:**
- Audit token count mỗi prompt
- Gộp constraint clauses
- Cân nhắc few-shot cho exec summary, recommendations
- Điều chỉnh word_limit

**Lý do defer:** Không tune trước khi biết baseline. Phase 5 validator đã bắt lỗi output → biết được chỗ nào cần tune.

---

### Phase 9 — Documentation

**Deliverables:**
- `CHANGELOG.md` per-phase
- `docs/data-contracts.md` — schema diff
- `docs/rag-integration.md` — view flow diagram
- `docs/scope-detection.md` — scope logic + SERVICE_DISPLAY/RESOURCE_TERMS
- `docs/validation-rules.md` — ReportValidator rules
- `docs/thesis-notes/improvements.md` — thesis material

---

## 5. Success Metrics (REVISED v2)

**Metrics PRIMARY — Correctness:**

| Metric | Baseline | Target | Method |
|--------|----------|--------|--------|
| Off-scope service mention rate (fixture F, G) | TBD (Phase 0) | **0%** | Grep/validator count |
| Hallucinated number rate | TBD | **0%** | FactValidator |
| Wrong resource terminology rate | TBD | **0%** | Term validator |
| Ungrounded capability rate | TBD | **≤ 5%** | Capability validator |
| Manual review — Scope correctness (criterion 1) | TBD | **+1 điểm** | Rubric |
| Manual review — Grounding (criterion 3) | TBD | **+1 điểm** | Rubric |

**Metrics SECONDARY — Quality:**

| Metric | Baseline | Target |
|--------|----------|--------|
| `recommended_practices` valid rate | ~0% | **≥ 90%** |
| Finding coverage (% mentioned) | TBD | **≥ 80%** |
| Validator overhead per section | N/A | **≤ 50ms** |
| Unit test coverage bundle_factory | hiện tại | **+5 test** |
| Integration tests | 0 | **≥ 3 test** |

**Bỏ khỏi metrics:**
- ~~RAG coverage (13/15 prompts)~~ — vanity
- ~~Avg prompt token size~~ — chuyển sang Phase 8 optional

---

## 6. Risk Matrix (v2)

| Phase | Risk | Likelihood | Impact | Mitigation |
|-------|------|-----------|--------|------------|
| 0 | Fixtures F, G không đại diện multi-service thực tế | Med | Med | Dùng data thật từ `job_outputs/` nếu có; hoặc compose từ IAM+EC2 fixtures |
| 1 | Service detection miss exotic services | Med | Low | Default fallback "AWS {SERVICE}"; iterative expand dict |
| 1 | Backward compat `total_buckets` — caller ngoài report agent cũng dùng | Med | High | Grep toàn codebase trước khi refactor; giữ deprecated alias |
| 1 | Template HTML break với label mới | Low | Med | Smoke test fixture F, G trong Phase 6 |
| 2 | `_extract_recommendation_text` empty cho edge case | Low | Med | Fallback None, bundle_factory handle |
| 2 | Rebuild hỏng indexes | Low | High | Backup `data/normalized.backup-*` |
| 3 | Schema change break consumer | Med | High | Backward-compat — chỉ thêm field |
| 4 | ChatOllama không hỗ trợ message list | Low | Med | Fallback pattern cũ |
| 5 | Validator false positive | Med | Med | Rubric test với fixture positive + negative |
| 5 | Validator perf kém | Low | Low | Precompile regex, cache allowed sets |
| 6 | Manual review subjective | High | Low | Rubric cố định, pair comparison |

---

## 7. Commit Strategy

Branch: `feat/report-agent-correctness-overhaul`

```
chore(test): capture baseline report output on 7 fixtures                   (Phase 0)
feat(agent): generalize scope detection, remove S3-first bias               (Phase 1) ★
feat(rag): extend ProwlerCheckDoc with remediation_recommendation field    (Phase 2)
feat(rag): rebuild ReportBundle with capability_details and sorting        (Phase 3)
refactor(agent): view-based RAG injection + SystemMessage constraints      (Phase 4)
feat(agent): ReportValidator output gate before render                      (Phase 5) ★
test(report): integration + smoke test + before/after comparison            (Phase 6)
feat(agent): wire capability_details into maturity prompts       [OPTIONAL] (Phase 7)
perf(agent): optimize prompt templates for small-model constraints [OPTIONAL] (Phase 8)
docs(report): data contracts, validation rules, thesis notes                (Phase 9)
```

★ = Phase mới theo feedback v2

---

## 8. Timeline

| Ngày | Phase | Focus |
|------|-------|-------|
| 1 (sáng) | Phase 0 | 7 fixtures + bias observations |
| 1 (chiều) | Phase 1.1-1.2 | scope_detector + env aggregation |
| 2 (sáng) | Phase 1.3-1.5 | Parameterize prompts + orchestrator + template |
| 2 (chiều) | Phase 2 | Pipeline hardening + regenerate |
| 3 (sáng) | Phase 3.1-3.3 | Bundle schema + utilities + rewrite |
| 3 (chiều) | Phase 3.4-3.5 | Confidence + unit tests |
| 4 (sáng) | Phase 4.1-4.3 | View formatter + SystemMessage + bracket |
| 4 (chiều) | Phase 4.4-4.5 | Compact prompt #9 + rag_client |
| 5 (sáng) | Phase 5.1-5.3 | ReportValidator + wire LLM writer |
| 5 (chiều) | Phase 5.4-5.5 | Pre-render gate + validation reports |
| 6 (sáng) | Phase 6.1-6.3 | Unit + integration + smoke |
| 6 (chiều) | Phase 6.4-6.5 | Manual review + improvement report |
| 7 | Phase 9 | Documentation |
| **OPT 8** | Phase 7 | Maturity RAG wiring |
| **OPT 9** | Phase 8 | Prompt optimization |

Core: ~6.5 ngày + 0.5 docs.
Optional: +1-2 ngày nếu timeline cho phép.

---

## 9. Câu hỏi cần confirm trước khi khởi động

1. **Phase 0 Fixtures F, G:** Bạn có data thật từ scan IAM/multi-service chưa? Nếu chưa tôi tạo synthetic từ public examples (sẽ ít realistic hơn).

2. **Phase 1 backward compat:** `total_buckets` có được dùng ngoài report agent không? Tôi cần grep toàn repo. Nếu có chỗ khác dùng → cần migration plan.

3. **Phase 5 strategy khi validator fail:**
   - (A) **Fallback template** (an toàn, mất nội dung LLM) ← đề xuất
   - (B) **Retry prompt** với instruction bổ sung (tốn token)
   - (C) **Log + pass through** (không khuyến nghị cho thesis)
   Chọn nào?

4. **Phase 7, 8 OPTIONAL:** Có muốn làm trong scope đồ án hay defer hẳn?

5. **Commit strategy:** OK với 9-10 commits riêng không?

6. **Rebuild indexes Phase 2:** `python scripts/build_all.py` đã chạy được trên máy bạn? Cần env setup thêm không?

---

## 10. File Inventory

### Agent layer (NEW priority)
- **`pdca/agents/report_module/scope_detector.py` — MỚI** (Phase 1)
- **`pdca/agents/report_module/validators.py` — MỚI** (Phase 5)
- `pdca/agents/report_module/rag_formatter.py` — MỚI (Phase 4)
- `pdca/agents/report_agent.py` — generalize aggregation + wire validator
- `pdca/agents/report_module/llm_writer.py` — parameterize prompts + SystemMessage + compact
- `pdca/agents/report_module/llm_validator.py` — extend FactValidator hoặc replace
- `pdca/agents/report_module/template.py` — dynamic labels
- `pdca/orchestrator.py` — scope detection + pass scope xuống agents

### RAG layer
- `RAG/app/core/models.py` — ProwlerCheckDoc, ReportBundle, ReportCapabilityDetail
- `RAG/app/ingestion/normalizers.py` — wire helper
- `RAG/app/retrieval/pipeline.py` — metadata extraction
- `RAG/app/context/bundle_factory.py` — rewrite + utilities
- `RAG/data/normalized/prowler_checks.json` — regenerate
- `RAG/tests/test_bundle_factory.py` — extend

### Shared
- `pdca/agents/shared/rag_client.py` — parse `capability_details`

### Tests & fixtures
- `tests/fixtures/report_baseline/` — MỚI (7 fixtures)
- `tests/unit/test_scope_detector.py` — MỚI
- `tests/unit/test_rag_view_formatter.py` — MỚI
- `tests/unit/test_report_validator.py` — MỚI
- `tests/integration/test_report_rag_flow.py` — MỚI
- `tests/integration/test_report_agent_e2e.py` — MỚI
- `scripts/capture_baseline.py` — MỚI

### Documentation
- `CHANGELOG.md` — update
- `docs/data-contracts.md` — MỚI
- `docs/rag-integration.md` — MỚI
- `docs/scope-detection.md` — MỚI
- `docs/validation-rules.md` — MỚI
- `docs/thesis-notes/improvements.md` — MỚI

---

**End of Plan v2.**

**Phản hồi mong đợi:**
- (A) Confirm plan v2 → tôi bắt đầu Phase 0
- (B) Điều chỉnh Phase X — nêu cụ thể
- (C) Thêm/cắt scope — nêu rõ
