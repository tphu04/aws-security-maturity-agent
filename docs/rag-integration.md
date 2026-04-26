# RAG Integration — Phase 4

How the report agent consumes the RAG bundle: from the orchestrator
fetch, through the view formatter, into the LLM prompts, and finally
into the validator evidence. The goal is one clear dataflow — every
downstream consumer reads the same `rag_context` dict.

## 1. End-to-end flow

```
┌──────────────────────────────┐
│ orchestrator._fetch_rag_for_ │
│           report()           │
│  (calls RAG /retrieve)       │
└──────────────┬───────────────┘
               │  rag_context:
               │    primary_topics
               │    key_findings
               │    control_themes
               │    recommended_practices
               │    capability_details       ◀── added in Phase 4
               │    confidence
               ▼
┌──────────────────────────────┐
│      ReportAgent.run()       │
│  data["rag_context"] = ...    │
└──────────────┬───────────────┘
               │
     ┌─────────┴─────────┐
     ▼                   ▼
┌─────────────┐   ┌──────────────────────┐
│ RAGView     │   │ build_evidence(...)  │
│ Formatter   │   │  uses                │
│             │   │   capability_details │
│ for_exec    │   │   control_themes     │
│ for_fail    │   └──────────┬───────────┘
│ for_pass    │              │ evidence dict
│ for_reco    │              ▼
│ for_per_fnd │   ┌──────────────────────┐
└──────┬──────┘   │ ReportValidator      │
       │          │   gate output         │
       │          └──────────┬───────────┘
       ▼                     │
┌──────────────────────────────┐
│       LLMWriter              │
│  write_exec_summary(...)     │
│  write_pass_findings_over... │
│  write_fail_findings_over... │
│  write_post_remediation_...  │
│  write_post_remediation_reco │
└──────────────┬───────────────┘
               │ gated text
               ▼
        final_report.html
```

## 2. `rag_context` shape (post Phase 4)

```python
{
    "primary_topics":         List[str],                # ["iam", "s3"]
    "key_findings":           List[Dict],               # sorted critical→low
    "control_themes":         List[Dict],               # confidence ≥ medium
    "recommended_practices":  List[str],                # from remediation_recommendation
    "capability_details":     List[ReportCapabilityDetail],
    "confidence":             str,                      # "high" | "medium" | "low"
}
```

Each `capability_details` entry carries:

```python
{
    "capability_id":       str,
    "capability_name":     str,
    "domain":              Optional[str],
    "stage":               Optional[str],
    "summary":             str,                   # ≤500 chars, sentence-truncated
    "risk_explanation":    Optional[str],
    "recommendation":      Optional[str],
    "guidance_questions":  List[str],
    "url":                 Optional[str],
}
```

Full schema in [data-contracts.md](data-contracts.md).

## 3. `RAGViewFormatter` — one bundle, many views

Source:
[pdca/agents/report_module/rag_formatter.py](../pdca/agents/report_module/rag_formatter.py).

Before Phase 4, `_build_rag_knowledge(rag_context)` emitted one flat
blob that was stuffed into every prompt. The formatter replaces it with
five section-aware views:

| View method            | Used by prompt                         | Payload                                                           |
|------------------------|----------------------------------------|-------------------------------------------------------------------|
| `for_executive`        | `write_exec_summary`                   | Top 3 critical/high findings + top 3 control themes              |
| `for_fail_analysis`    | `write_fail_findings_overview`         | Up to 8 findings sorted by severity + capability risk explanations |
| `for_pass_analysis`    | `write_pass_findings_overview`         | Up to 5 control themes that passed                                |
| `for_recommendations`  | `write_post_remediation_recommendations`| Top `recommended_practices` + capability recommendations          |
| `for_per_finding`      | Per-finding remediation text enrichment| `{risk, recommendation}` for a single `check_id`                   |

Every view returns `""` when the underlying bundle is empty, so the
prompt drops the heading cleanly.

Severity labels use parentheses (`(HIGH)`) instead of brackets
(`[HIGH]`). The downstream placeholder scrubber in `LLMWriter._clean`
strips `[...]` as stray placeholders — brackets had been eating
severity tokens silently.

## 4. Prompt wiring

`LLMWriter` methods accept pre-rendered view text through the
`rag_knowledge=` kwarg. Example:

```python
exec_summary = llm.write_exec_summary(
    pre, system_data, scope, scope_info=scope_info,
    rag_knowledge=rag_views.for_executive(),
    fail_findings=fail_findings,
)
```

This keeps view logic out of the prompt templates — every template
interpolates a single `{rag_knowledge}` block whose content is the only
thing that changes per section.

## 5. SystemMessage constraints

Shared output constraints moved out of the prompt string and into a
single SystemMessage. `LLMWriter._ask` first tries to invoke the LLM
with `[SystemMessage(...), HumanMessage(prompt)]`; on
`TypeError`/`AttributeError` it falls back to string concatenation so
older `ChatOllama` versions keep working.

Net effect:

* `_OUTPUT_CONSTRAINTS` no longer appended 15× per report.
* Roughly 120 tokens × 15 calls ≈ **1800 tokens per report** saved.
* The `word_limit` knob is still per-call — stashed on the writer
  instance by `_with_constraints` so `_ask` can use it.

## 6. Compacted post-remediation prompt

`write_post_remediation_analysis` used to `json.dumps(data, indent=2)`
the entire pipeline state — the LLM saw `tool_code`, `execution_output`,
and other fields that leaked into the output. Now the prompt sees only:

```python
{
  "outcome":        data["remediation_outcome"],
  "post_summary":   data["post_summary"],
  "maturity_delta": data["maturity_delta"]["overall"],
}
```

## 7. Validator consumption

`build_evidence(...)` reads the same `rag_context` to populate
`allowed_capabilities`:

```python
for t in rag_context.get("control_themes") or []:
    name = (t or {}).get("capability_name")
    if name:
        allowed_capabilities.add(str(name).strip())
for d in rag_context.get("capability_details") or []:
    name = (d or {}).get("capability_name")
    if name:
        allowed_capabilities.add(str(name).strip())
```

Because the same bundle drives both the view (what the LLM sees) and
the evidence (what the validator allows), a capability the LLM is
grounded on is automatically in the allowed set. The integration test
[tests/integration/test_report_rag_flow.py](../tests/integration/test_report_rag_flow.py)
exercises this round-trip.

## 8. Fallback when RAG is unavailable

Every layer degrades gracefully when `rag_context` is empty:

* `RAGViewFormatter.has_data` returns `False`; all `for_*` views return
  `""`.
* `build_evidence` returns an evidence dict with empty
  `allowed_capabilities`, which disables the `ungrounded` check.
* `ReportAgent` continues to render using just scan data — no exception,
  no RAG-required paths.

The orchestrator's own fallback (setting `confidence = "low"` when
retrieval returns nothing) is recorded in the rendered report's cover
page so the reader knows the section is ungrounded.

---

## 8. Multi-query RAG — MVP Phase 3 additions

### 8.1 New endpoint: `POST /v1/retrieve/report_context`

Single wrapper call replacing the legacy `/v1/context/build` for report
consumers. The RAG service orchestrates Q1+Q2+Q3 in parallel internally.

**Request schema** (`ReportContextRequest`):
```json
{
  "check_ids":          ["s3_bucket_level_public_access_block", "..."],
  "domains":            ["s3", "iam"],
  "severity_map":       {"s3_bucket_level_public_access_block": "HIGH"},
  "include_q2":         true,
  "include_q3":         true,
  "top_k_check":        10,
  "top_k_capability":   5,
  "top_k_remediation":  3
}
```

**Response schema** (`ReportContextBundle`):
```json
{
  "check_findings":      [ReportFinding],
  "control_themes":      [ReportCapability],
  "capability_details":  [ReportCapabilityDetail],
  "recommended_practices": ["..."],
  "primary_topics":      ["s3"],
  "capability_themes":   [CapabilityTheme],
  "remediations":        [RemediationGuide],
  "confidence":          "high",
  "diagnostics":         {"total_latency_ms": 120, "cache_hit": false}
}
```

### 8.2 New sub-schemas

**`CapabilityTheme`** (Q2 — domain security narrative):
```python
domain:         str          # "s3" | "iam" | "ec2" | ...
narrative:      str          # 2-3 sentence overview from risk_explanation
common_pitfalls: list[str]  # max 5, from how_to_check + risk fields
baselines:      list[str]   # CIS/Well-Architected references
citations:      list[Citation]
```

**`RemediationGuide`** (Q3 — structured how-to steps):
```python
check_id:    str
steps:       list[RemediationStep]  # {order, type, snippet, prerequisite}
rollback:    str | None
effort:      "low" | "medium" | "high"
side_effects: list[str]
citations:   list[Citation]
```

**`RemediationStep`**:
```python
order:        int
type:         "cli" | "iac" | "console" | "other"
snippet:      str   # actual CLI command or IaC block
prerequisite: str | None
```

### 8.3 Multi-query flow

```
MULTI_QUERY_MODE=true
        |
ReportAgent._fetch_rag_context()
        |
RAGQueryPlanner.plan(findings, scope_domains)
  - dedup check_ids (order-preserving)
  - build severity_map
  - dedup domains (fallback "general")
        |
RAGQueryPlanner.execute(req)
        |
RAGClient.build_report_context()  --> POST /v1/retrieve/report_context
        |
ReportContextService.build() [RAG side]
  - asyncio.gather(Q1, Q2, Q3)
  - graceful degradation: Q2/Q3 fail -> confidence="medium"
  - in-memory cache (TTL 60s)
        |
_normalize_bundle() -> rag_context dict
  {key_findings, control_themes, ..., capability_themes, remediations}
        |
RAGViewFormatter(rag_context)
  for_pass_analysis()      <- Q2 capability_themes (primary)
  for_recommendations()    <- Q3 remediations (primary)
```

### 8.4 Enabling multi-query mode

```bash
# In .env or shell:
MULTI_QUERY_MODE=true

# Start RAG service with auto-reload:
python RAG/start.py

# Verify:
curl http://localhost:8005/v1/retrieve/report_context \
  -d '{"check_ids":["s3_bucket_level_public_access_block"],"domains":["s3"]}'
```

### 8.5 Backward compatibility

- `MULTI_QUERY_MODE=false` (default): legacy `/v1/context/build` path unchanged
- `RAGViewFormatter`: `capability_themes=[]` and `remediations=[]` -> falls back to Q1-only behavior
- All existing tests pass in both modes (`pytest tests/ RAG/tests/ -q`)
