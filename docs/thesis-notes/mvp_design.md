# MVP Design Rationale — Multi-query RAG for Report Agent

> **For:** LVTN thesis — System Design section
> **Date:** 2026-04-24
> **Status:** Final (Phase 1-4 complete)

---

## 1. Problem Statement

The original report agent called `POST /v1/context/build` once with a list of
check IDs. This single-query architecture had three failure modes observed in
Phase 1 baseline:

| Failure | Metric | Worst case |
|---|---|---|
| LLM fabricates remediation step counts | numerical_faithfulness | 0.80 (cases c4, c5) |
| Capability claims ungrounded when not in Q1 bundle | capability_grounding_rate | 0.7778 (cases c2) |
| Findings not re-sorted by severity | ndcg@5_severity | 0.7489 (case c3) |

---

## 2. Design Decisions

### 2.1 Single wrapper endpoint vs. client-side parallel calls

**Chosen: Single wrapper `POST /v1/retrieve/report_context`**

Rationale:
- Client sends 1 HTTP request; RAG service orchestrates Q1+Q2+Q3 via `asyncio.gather`
- Cache at server level (TTL 60s, keyed on check_ids+domains) — avoids redundant computation across requests
- Client code change is minimal: one new `RAGClient.build_report_context()` call
- Trade-off accepted: one more route on the RAG service

Alternative rejected: 3 parallel client calls → more HTTP overhead, cache harder to implement, complex client code.

### 2.2 Feature flag `MULTI_QUERY_MODE`

Default `False` to ensure zero behavior change for existing callers. The flag
allows the benchmark to run both modes in isolation for a clean A/B comparison.

The legacy code path (`_fetch_rag_for_report` in orchestrator.py) is preserved
until the multi-query path is validated stable (Post-MVP: see §14.2 of plan).

### 2.3 Q3 implementation: direct lookup vs. semantic retrieval

**Chosen: Direct lookup in `prowler_checks.json` (in-memory cache)**

Rationale:
- `check_id` is exact — no fuzzy search needed; direct dict lookup is O(1)
- 577 records × ~2KB = ~1.1MB in memory — negligible
- Avoids re-indexing after adding `remediation_code` structured field to BM25
- Parse remediation blob via `ast.literal_eval` (safe, handles Python dict literals)

Alternative rejected: HyDE + hybrid retrieval on remediation fields — adds latency,
non-deterministic, and unnecessary when exact check_id is known.

### 2.4 Q2 query construction

The maturity corpus uses capability IDs (`block_public_access`, `audit_api_calls`)
not service names (`s3`, `iam`). A bare domain name like `"s3"` fails BM25 retrieval
because it's too short and filtered as a near-stopword.

Fix: `_DOMAIN_QUERIES` dict maps domain → descriptive natural language query
(e.g. `"s3"` → `"S3 bucket public access block encryption data protection"`).
This achieves 5 results per domain with high relevance scores.

### 2.5 `RAGViewFormatter` backward compatibility

The formatter checks for `capability_themes` and `remediations` in `rag_context`:
- Present and non-empty → multi-query rendering (Q2/Q3 content injected)
- Empty or absent → legacy rendering (Q1-only, same as before)

No LLM prompt templates were modified — the formatter controls the *content* of
the string injected into existing prompt slots (`rag_knowledge`, `rag_pass`, etc.).

---

## 3. Architecture Diagram

```
[MULTI_QUERY_MODE=true]

Orchestrator
    │
    ├─ _fetch_rag_multi_query(findings, scope_info)
    │       │
    │       ├─ RAGQueryPlanner.plan(findings, scope_domains)
    │       │     dedup check_ids + build severity_map + dedup domains
    │       │
    │       └─ RAGQueryPlanner.execute(req)
    │               │
    │               └─ RAGClient.build_report_context()
    │                       POST /v1/retrieve/report_context
    │                               │
    │                       ReportContextService.build()
    │                         asyncio.gather:
    │                           Q1: ContextService (existing)
    │                           Q2: MaturityService (domain query)
    │                           Q3: prowler_checks lookup (ast.literal_eval)
    │                         -> ReportContextBundle
    │
ReportAgent.run(data)
    │
    ├─ _fetch_rag_context()  [if rag_context not in data]
    │     checks MULTI_QUERY_MODE, calls planner
    │
    ├─ RAGViewFormatter(rag_context)
    │     for_executive()          <- Q1 key_findings
    │     for_fail_analysis()      <- Q1 findings + capability_details
    │     for_pass_analysis()      <- Q2 capability_themes (primary) + Q1 control_themes
    │     for_recommendations()    <- Q3 remediations (primary) + Q2 baselines + Q1 practices
    │
    └─ LLMWriter (15 methods) -> final_report.{md,html,pdf}
```

---

## 4. Benchmark Results Summary

### 4.1 Deterministic metrics

| Condition | numerical_faithfulness | capability_grounding | ndcg@5 |
|---|---|---|---|
| Pure LLM (baseline) | 0.9867 | 0.9640 | 0.9125 |
| Q1-only (multi-query) | 1.0000 | 1.0000 | 0.9133 |
| Q1+Q2 | 1.0000 | 1.0000 | 0.9133 |
| Q1+Q3 | 1.0000 | 1.0000 | 0.9133 |
| Q1+Q2+Q3 (full MVP) | 1.0000 | 1.0000 | 0.9133 |

### 4.2 Interpretation

The main improvement driver is **RAG grounding (Q1)**, not specifically Q2 or Q3.
Once any RAG context is present, the two pathological cases (c4_post_remediation_delta,
c5_rag_empty_fallback) stop hallucinating the number "7" in recommendations.

Q2 and Q3 contributions are not captured by the 6 deterministic metrics (ceiling
effect at 1.0). The LLM-judge metrics (claim_support_rate, actionability_likert)
are expected to show Q2/Q3 value by measuring qualitative claim grounding and
actionability of recommendations.

### 4.3 Gap 3 (severity ordering, ndcg=0.7489 in worst case)

Unchanged across all conditions — not a RAG problem. Requires pre-sorting findings
by severity in `report_agent.py` before passing to LLM (§14.6 B2, 15-minute fix).

---

## 5. Implementation Files

| File | Role |
|---|---|
| [pdca/config.py](../../pdca/config.py) | `MULTI_QUERY_MODE` flag |
| [pdca/agents/report_module/rag_query_planner.py](../../pdca/agents/report_module/rag_query_planner.py) | Plan + execute multi-query |
| [pdca/agents/shared/rag_client.py](../../pdca/agents/shared/rag_client.py) | `build_report_context()` HTTP call |
| [pdca/agents/report_module/rag_formatter.py](../../pdca/agents/report_module/rag_formatter.py) | Q2/Q3 views in `for_pass_analysis`, `for_recommendations` |
| [pdca/agents/report_agent.py](../../pdca/agents/report_agent.py) | `_fetch_rag_context()` method |
| [pdca/orchestrator.py](../../pdca/orchestrator.py) | `_fetch_rag_multi_query()` + branch |
| [RAG/app/services/report_context_service.py](../../RAG/app/services/report_context_service.py) | Q1+Q2+Q3 orchestration |
| [RAG/app/api/routes/retrieve.py](../../RAG/app/api/routes/retrieve.py) | 3 new endpoints |
| [RAG/app/core/models.py](../../RAG/app/core/models.py) | New Pydantic schemas |
| [RAG/scripts/backfill_capability_domain.py](../../RAG/scripts/backfill_capability_domain.py) | Domain backfill script |

---

## 6. Test Coverage

| Suite | Tests | Status |
|---|---|---|
| `tests/test_rag_query_planner.py` | 12 | PASS |
| `tests/test_rag_view_formatter.py` | 26 | PASS |
| `tests/test_report_smoke_e2e.py` | 22 | PASS |
| `RAG/tests/test_report_context.py` | 16 | PASS |
| Total | **76** | **All PASS** |
