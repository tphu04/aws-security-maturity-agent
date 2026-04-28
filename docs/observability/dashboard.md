# Langfuse Dashboard — PDCA AWS Security Agent

> Audience: LVTN reviewer + on-call dev. Mô tả 5 view chính + filter recipes.
> Tham chiếu spec: [LANGFUSE_INTEGRATION_GUIDE.md §6](../LANGFUSE_INTEGRATION_GUIDE.md), [LANGFUSE_IMPLEMENTATION_PLAN.md §I9](../LANGFUSE_IMPLEMENTATION_PLAN.md).

---

## Trace topology (Phase I)

```
trace pdca.run [trace_id = run_id (UUID4 → 32-hex)]
├── node:environment
│   ├── aws:sts:get_caller_identity
│   └── aws:s3:list_buckets
├── node:planning
│   └── agent:PlanningAgent
│       └── (LLM generation auto-captured by Langfuse callback handler)
├── node:scan_submit
├── node:scan_poll[iter=1..N]                  # one span per poll iteration
│   └── scanner:check_job_status × pending_count
├── node:scan_collect
├── node:risk_evaluation
│   └── agent:RiskEvaluationAgent
│       ├── risk.pass1
│       └── risk.pass2_rag
├── node:operational_planning
│   └── agent:RemediationPlannerAgent
├── node:review_task                           # marker; real wait is hitl:wait
├── hitl:wait                                  # human latency captured
├── node:reset_index
├── node:execution
│   └── tool:<remediation_tool_name> × tasks   # ExecutionAgent.execute_task
├── node:verification
│   └── agent:AnalysisAgent
└── node:report
    ├── maturity:assess
    └── agent:ReportAgent
        └── report.section.<id> × ~15          # one span per LLM section
```

`rag:*` spans appear underneath whatever node owns the call (planning,
risk_eval, report) — driven by `RAGClient._post()`/`_post_raw()`.

---

## 5 Dashboard views

### 1. Run timeline

Filter: `name = pdca.run` and date window.

Open one trace → tree view shows all nested spans + timing. Use this for
drill-down on a specific assessment cycle.

### 2. Per-node latency

Filter: `name LIKE node:%`.

Aggregate `duration_ms` by `name`. Catches regressions in a single node
(e.g. scan_poll iteration creep).

### 3. Token usage by model

Filter: `type = generation`.

Group by `model` (currently `gemma3:4b`). Watch `usage_metadata.total_tokens`
trend per run. Spike = LLMWriter prompt regression.

### 4. Error explorer

Filter: `level = error` OR `status = error`.

Group by span `name`. Top entries point at the failing component (RAG
unavailable → `rag:*`, AWS denied → `aws:s3:*`, validation reject → `report.section.*`).

### 5. HITL latency distribution

Filter: `name = hitl:wait`.

Histogram of `output.latency_human_ms`. Tails > 5 min = workflow friction
or unattended sessions.

---

## Filter recipes

| Goal | Filter |
|---|---|
| Failed runs | `metadata.pdca.outcome.tag = "partial_failure"` |
| Degraded runs (no AWS creds) | `metadata.pdca.outcome.tag = "degraded"` |
| Specific account | `metadata.aws.account_id_redacted = "***1234"` |
| Risk-heavy runs | `metadata.pdca.risk.severity_dist.critical > 0` |
| Successful remediations | scores `outcome_fixed_ratio > 0.5` |
| Validator-flagged reports | scores `validation_issues > 0` |
| Single user request | `input` LIKE `%<keyword>%` (root span input) |

---

## Score schema

| Score name | Emitted by | Range | Meaning |
|---|---|---|---|
| `planning_top_score` | planning_node | 0–1 | RAG confidence × severity weighting at top of plan |
| `risk_severity_critical` | risk_eval_node | int ≥ 0 | Number of CRITICAL findings |
| `risk_severity_high` | risk_eval_node | int ≥ 0 | Number of HIGH findings |
| `outcome_fixed_ratio` | verification_node | 0–1 | Auto-fix success / total findings |
| `outcome_manual_count` | verification_node | int ≥ 0 | Findings that required manual handling |
| `validation_issues` | report_node | int ≥ 0 | LLM sections rejected by validator |

---

## Trace tagging

Every report node sets `metadata.pdca.outcome.tag` ∈ `{success, partial_failure, degraded}`.

Use this as the primary filter in dashboards — the value is set in
[pdca/graph/nodes/report.py](../../pdca/graph/nodes/report.py) by
`_outcome_tag()` based on `_degraded` flag and accumulated `errors`.

---

## Screenshot placeholder

Khi merge PR Phase I, attach 3 screenshot vào folder `docs/observability/screenshots/` (gitignored ngoài LVTN export):
- `01_trace_tree_full.png` — 1 trace E2E tree.
- `02_node_latency_chart.png` — bar chart per-node duration.
- `03_hitl_distribution.png` — histogram hitl:wait.

Reference các screenshot này trong LVTN slide.
