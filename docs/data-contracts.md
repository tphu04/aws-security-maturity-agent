# Data Contracts — Schema Diffs Phases 1 → 5

Every schema change introduced by the overhaul is additive — fields
are added, not removed — so consumers that did not migrate still work.
This doc records the "before / after" deltas so thesis readers and
future contributors can see what moved.

## 1. `ProwlerCheckDoc` (Phase 2)

Source:
[RAG/app/core/models.py](../RAG/app/core/models.py) §`ProwlerCheckDoc`.

| Field                         | Before | After   | Phase |
|-------------------------------|--------|---------|-------|
| `check_id`                    | ✓      | ✓       | —     |
| `service`                     | ✓      | ✓       | —     |
| `title`                       | ✓      | ✓       | —     |
| `severity`                    | ✓      | ✓       | —     |
| `description`                 | ✓      | ✓       | —     |
| `risk`                        | ✓      | ✓       | —     |
| `remediation`                 | ✓      | ✓       | —     |
| **`remediation_recommendation`** | —    | ✓ (Optional) | **2** |
| **`remediation_url`**         | —      | ✓ (Optional) | **2** |
| `resource_type`               | ✓      | ✓       | —     |
| `keywords`                    | ✓      | ✓       | —     |

Phase 2 wired the existing `_extract_recommendation_text` helper
(already present in
[RAG/app/ingestion/normalizers.py](../RAG/app/ingestion/normalizers.py))
so `Remediation.Recommendation.Text` and `Recommendation.Url` no longer
drop during normalization.

## 2. `ReportCapabilityDetail` (Phase 3 — new model)

Source: [RAG/app/core/models.py](../RAG/app/core/models.py) §`ReportCapabilityDetail`.

```python
class ReportCapabilityDetail(BaseModel):
    capability_id:        str
    capability_name:      str = "Unknown capability"
    domain:               Optional[str] = None
    stage:                Optional[str] = None
    summary:              str
    risk_explanation:     Optional[str] = None
    recommendation:       Optional[str] = None
    guidance_questions:   List[str] = Field(default_factory=list)
    url:                  Optional[str] = None
```

Purpose: surface the rich payload from `MaturityCapabilityDoc` so report
prompts can ground wording against actual documentation instead of
fabricating.

## 3. `ReportBundle` (Phase 3)

| Field                       | Before | After |
|-----------------------------|--------|-------|
| `primary_topics`            | ✓      | ✓     |
| `key_findings`              | ✓      | ✓ (sorted critical→low) |
| `control_themes`            | ✓      | ✓ (filtered confidence ≥ medium) |
| `recommended_practices`     | ✓      | ✓ (sourced from `remediation_recommendation` only) |
| **`capability_details`**    | —      | **✓ (Phase 3)** |
| `confidence`                | ✓      | ✓     |

```python
class ReportBundle(BaseModel):
    primary_topics:        List[str]
    key_findings:          List[ReportFinding]
    control_themes:        List[ReportCapability]
    recommended_practices: List[str]
    capability_details:    List[ReportCapabilityDetail]   # NEW
    confidence:            Optional[str] = None
```

### `recommended_practices` — source change

| Source                                   | Before      | After                  |
|------------------------------------------|-------------|------------------------|
| `remediation_recommendation` (check)     | not wired   | ✓ primary source       |
| `capability.recommended_practices`       | ✓           | ✓                      |
| `mapping.rationale`                      | ✓ (fallback)| **removed** (noise leak) |
| Raw `remediation` CLI blocks             | ✓ (fallback)| **removed** (noise leak) |

Pre-Phase-3 outputs occasionally contained strings like `Shared
concepts:` or stringified dicts from `rationale`. Phase 3 closed that
source entirely.

## 4. `rag_context` dict (Phase 4)

Consumed by the report agent. Produced by `orchestrator._fetch_rag_for_report`.

```python
{
    "primary_topics":        List[str],                # NEW surfaced Phase 4
    "key_findings":          List[Dict],
    "control_themes":        List[Dict],
    "recommended_practices": List[str],
    "capability_details":    List[Dict],               # NEW surfaced Phase 4
    "confidence":            Optional[str],
}
```

Before Phase 4 the orchestrator stripped `primary_topics` and
`capability_details` from the bundle on the way to the agent, so the
`RAGViewFormatter` and the validator's `allowed_capabilities` could not
see them. Phase 4 passes both through unchanged.

## 5. `evidence` dict (Phase 5 — new)

Produced by
[`validators.build_evidence`](../pdca/agents/report_module/validators.py)
from already-validated pipeline inputs.

```python
{
    "allowed_numbers":       Set[float],
    "allowed_services":      Set[str],
    "allowed_capabilities":  Set[str],
    "account_id":            Optional[str],
}
```

### `allowed_numbers` population

`build_evidence` walks `pre`, `post`, and `env` recursively, collecting
every `int`/`float` value into the set. This covers:

* `pre.total`, `pre.pass`, `pre.fail`, `pre.severity.*`
* `post.initial_*`, `post.final_*`, `post.fixed`, `post.failed`, `post.manual`
* `len(env.buckets)` / `len(env.resources)` when present

Plus the account id (added separately — not a data claim but always
present in the rendered report).

### `allowed_services` population

Seeded from `scope.service_list` + `scope.primary_service`. Falls back
to services observed in the finding list if scope is empty, so the
validator always has something to gate on.

### `allowed_capabilities` population

Every `capability_name` from `rag_context.control_themes` +
`rag_context.capability_details`. Lower-cased in the validator for
comparison; the raw display-case names are stored so error messages
look right.

## 6. `scope_info` dict (Phase 1)

Produced by `scope_detector.detect_scope` — see
[scope-detection.md](scope-detection.md) §1 for the full shape. Phase 1
adds `scope_info` to the `template_ctx` passed into the Jinja template,
so the cover page renders `service_display` / `resource_term` without
a hardcoded label.

## 7. `validation_report.json` (Phase 5 — new)

Emitted next to the HTML output at `{output_dir}/validation_report.json`:

```json
{
  "sections_validated": ["executive_summary", "system_overview",
                          "assessment_goals", "pass_overview",
                          "fail_overview", "post_analysis",
                          "recommendations"],
  "issue_count": 0,
  "summary": {},
  "issues": []
}
```

Issue objects are serialised via `ValidationIssue.to_dict`:

```json
{
  "section": "executive_summary",
  "kind":    "off_scope" | "hallucinated_number" | "wrong_term" | "ungrounded",
  "evidence": "s3",
  "details":  "Service 's3' is not in scan scope (['iam'])."
}
```

## 8. Migration notes

Schema changes are backward compatible: every new field is `Optional`
(or defaulted via `Field(default_factory=...)`). Consumers that still
construct old-shape dicts continue to work — they just miss the new
signal.

Deprecated keys (Phase 1):

| Key              | Status       | Removal                                 |
|------------------|--------------|-----------------------------------------|
| `total_buckets`  | removed      | Replaced by `total_resources`           |
| `bucket_list`    | removed      | Replaced by `resource_list`             |
| `_looks_like_bucket` | removed  | Replaced by `is_valid_resource`         |

No caller outside the report agent used these — checked with a repo-
wide grep during Phase 1.

---

## 6. MVP Multi-query schemas (Phase 3)

Source: [RAG/app/core/models.py](../RAG/app/core/models.py)

### 6.1 `CapabilityQueryRequest`

```python
domain:  str                                   # "s3" | "iam" | "ec2" | ...
status:  Literal["pass","fail","mixed"] = "mixed"
top_k:   int = 5
```

### 6.2 `CapabilityTheme`

```python
domain:          str
narrative:       str          # 2-3 sentence domain security overview
common_pitfalls: list[str]   # max 5
baselines:       list[str]   # CIS/Well-Architected references
citations:       list[Citation]
```

### 6.3 `RemediationQueryRequest`

```python
check_id:      str
severity:      Optional[Literal["CRITICAL","HIGH","MEDIUM","LOW"]]
cloud_context: Optional[dict]
top_k:         int = 3
```

### 6.4 `RemediationStep`

```python
order:        int
type:         Literal["cli","iac","console","other"]
snippet:      str
prerequisite: Optional[str]
```

### 6.5 `RemediationGuide`

```python
check_id:    str
steps:       list[RemediationStep]
rollback:    Optional[str]
effort:      Literal["low","medium","high"] = "medium"
side_effects: list[str]
citations:   list[Citation]
```

### 6.6 `ReportContextRequest`

```python
check_ids:           list[str]          # deduplicated by RAGQueryPlanner
domains:             list[str]          # from scope_detector.service_list
severity_map:        dict[str,str]      # {check_id: "HIGH"|"CRITICAL"|...}
include_q2:          bool = True
include_q3:          bool = True
top_k_check:         int = 10
top_k_capability:    int = 5
top_k_remediation:   int = 3
```

### 6.7 `ReportContextBundle` — full schema

```python
# Q1 (existing shape — backward compat)
check_findings:       list[ReportFinding]
control_themes:       list[ReportCapability]
capability_details:   list[ReportCapabilityDetail]
recommended_practices: list[str]
primary_topics:       list[str]

# Q2 (NEW)
capability_themes:    list[CapabilityTheme]   # [] in legacy mode

# Q3 (NEW)
remediations:         list[RemediationGuide]  # [] in legacy mode

confidence:           str   # "high" | "medium" | "low"
diagnostics:          dict  # {total_latency_ms, cache_hit}
```

**Migration guide:** Consumers reading `rag_context` via `RAGViewFormatter`
get Q2/Q3 data automatically when `MULTI_QUERY_MODE=true`. No prompt
template changes required — the formatter injects new content into
existing string slots.
