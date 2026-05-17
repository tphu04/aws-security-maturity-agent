# Check→Capability Mapping Pipeline (4-tier rebuild)

Replaces the legacy single-step `RAG/scripts/gen_maturity_mapping.py` with a
4-tier semi-automated pipeline whose output is defensible without a single
human reviewer.

## Quick start

```powershell
# Tier 1 — upstream signals (offline, ~1 s)
python -m RAG.pipeline.mapping.tier1_upstream_import

# Tier 2 — proposers (offline by default, ~5 s)
python -m RAG.pipeline.mapping.tier2_run

# Tier 2 with LLM proposer (requires API key, see below)
$env:ENABLE_LLM_PROPOSER = "1"
$env:ANTHROPIC_API_KEY   = "sk-ant-..."
python -m RAG.pipeline.mapping.tier2_run

# Tier 3 — consensus
python -m RAG.pipeline.mapping.tier3_consensus

# Tier 4 — build final artifact
python -m RAG.pipeline.mapping.tier4_build_artifact

# Tier 4 — validation
python -m RAG.pipeline.mapping.tier4_validation.invariant_tests
python -m RAG.pipeline.mapping.tier4_validation.precision_recall_eval

# CI gates
python -m pytest tests/mapping_pipeline/ -v
```

## What you need to provide

| Item | Required? | Where |
|---|---|---|
| `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` | Only if `ENABLE_LLM_PROPOSER=1` | Environment variable |
| Golden set verification | Manual | Paste `tier4_validation/golden_set_review_packet.md` into an external LLM (Claude.ai or ChatGPT), apply verdicts to `golden_set_additions_draft.json`, merge into `golden_set.json` |
| Capability `framework_refs` (optional) | For Tier 1 hard cross-references | Edit `RAG/data/normalized/maturity_capabilities.json` |

## LLM proposer setup

```powershell
# Option 1 — Claude (preferred for compliance domain)
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:ANTHROPIC_MODEL   = "claude-opus-4-7"   # default

# Option 2 — OpenAI
$env:OPENAI_API_KEY = "sk-..."
$env:OPENAI_MODEL   = "gpt-4o-mini"          # default

# Then enable and run:
$env:ENABLE_LLM_PROPOSER = "1"
python -m RAG.pipeline.mapping.tier2_run
python -m RAG.pipeline.mapping.tier3_consensus
python -m RAG.pipeline.mapping.tier4_build_artifact
```

Responses are cached in `.cache/llm_proposer_cache.json` keyed by
`(model_id, system, human)`. Re-runs are free; only changed prompts re-call
the API.

Expected effect:
- Cohen's kappa: 0.38 (2-proposer) → ~0.60-0.70 (3-proposer with LLM)
- Consensus rate: 40% → 55-65%
- Disputed rate: 14.6% → 5-8%

## Promotion policy

| Tier 3 consensus_status | Tier 4 status | review_status | Reaches agents? |
|---|---|---|---|
| `consensus` (unanimous top-1) | `active` | `auto_high` | ✓ |
| `majority` (strict majority) | `active_majority` | `review_required` | only after manual review |
| `weak` (top-K overlap, diff rank-1) | `proposed` | `review_required` | only after manual review |
| `disputed` (zero overlap) | **EXCLUDED** | — | never |

Disputed checks are written to `tier4_excluded_disputed.json` and disclosed
as known limitations — never silently promoted.

## CI gates (`tests/mapping_pipeline/test_pipeline_gates.py`)

Quality floors enforced on every PR:
- Tier 1 security_domain coverage ≥ 80%
- Tier 1 evidence_ref coverage ≥ 45%
- Tier 3 consensus rate ≥ 35%, disputed ≤ 20%
- Pairwise Cohen's kappa ≥ 0.30
- Invariant tests: 0 violations
- Golden consensus accuracy ≥ 30%
- Combined Recall@5 ≥ 0.40
- MappingService backward-compat load

Floors are intentionally permissive at the 2-proposer baseline. Ratchet up
when LLM proposer is wired (TODOs in test file).

## Files

```
RAG/pipeline/mapping/
├── tier1_upstream_import.py         # Prowler → evidence_refs + security_domain
├── capability_domain.py             # security_domain for each capability
├── tier2_proposers/
│   ├── base.py                      # Proposer Protocol + Proposal dataclass
│   ├── lexical_proposer.py          # Wraps legacy gen_maturity_mapping
│   ├── llm_proposer.py              # EmbeddingProposer + LLMProposer
│   └── llm_adapters.py              # Anthropic + OpenAI adapters + cache
├── tier2_run.py
├── tier3_consensus.py               # Borda + Cohen's kappa
├── tier4_build_artifact.py          # Promotion policy + new schema
└── tier4_validation/
    ├── golden_set.json              # 20 mappings (CIS/NIST citations)
    ├── golden_set_additions_draft.json
    ├── golden_set_review_packet.md  # Paste into external LLM
    ├── invariant_tests.py
    └── precision_recall_eval.py
```

## Outputs (`RAG/data/normalized/`)

- `tier1_upstream_signals.json`, `tier1_coverage_report.json`
- `tier2_proposals.json`, `tier2_coverage_report.json`
- `tier3_consensus.json`, `tier3_disputed.json`, `tier3_report.json`
- `maturity_mappings.v2.json` (the artifact; backward-compat for MappingService)
- `tier4_excluded_disputed.json`, `tier4_build_report.json`, `tier4_eval_report.json`
