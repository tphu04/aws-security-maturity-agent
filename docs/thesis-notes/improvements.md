# Thesis Notes — Report Agent Correctness Overhaul

A thesis-ready narrative of the six correctness phases. Use this as the
starting point for the Results chapter of the đồ án tốt nghiệp. Every
claim is anchored to a concrete file or test so examiners can verify.

## 1. Problem statement

The pre-refactor Report Agent had two correctness problems that made
the final HTML unreliable:

1. **Scope bias.** The agent assumed every scan was an S3 scan. Two
   layers of the code were biased:
   * *Prompt layer* — `llm_writer.py` hardcoded `"Amazon S3"` /
     `"bucket"` across 15 prompt templates.
   * *Aggregation layer* — `report_agent.py` exposed `total_buckets`,
     `bucket_list`, and `_looks_like_bucket` in the data dict fed to
     templates.
   Any IAM or multi-service scan came out *textually described* as S3.
2. **Hallucination vectors.** Nothing gated LLM output before render.
   `FactValidator` existed but checked only numbers. The LLM could
   invent:
   * services not in scope,
   * numbers not in the scan,
   * capability names not in the RAG evidence,
   * resource nouns (`bucket`) inappropriate for the primary service,
   and all four would reach the final HTML unchanged.

## 2. Objectives

Derived from
[REPORT_AGENT_IMPROVEMENT_PLAN.md](../../REPORT_AGENT_IMPROVEMENT_PLAN.md)
§5 (REVISED v2):

| Metric (primary)                                         | Target |
|----------------------------------------------------------|--------|
| Off-scope service mention rate (fixture F, G)            | 0 %    |
| Hallucinated number rate                                 | 0 %    |
| Wrong resource terminology rate                          | 0 %    |
| Ungrounded capability rate                               | ≤ 5 %  |
| Scope correctness Δ on rubric                            | +1     |
| Grounding Δ on rubric                                    | +1     |
| Recommended-practices valid rate                         | ≥ 90 % |
| Finding coverage                                         | ≥ 80 % |

## 3. Approach

Six sequential phases, each atomic and testable:

| Phase | Name                                  | Outcome (anchor)                                |
|-------|----------------------------------------|--------------------------------------------------|
| 1     | Scope Generalization                   | [`scope_detector.py`](../../pdca/agents/report_module/scope_detector.py) |
| 2     | Data Pipeline Hardening                | `ProwlerCheckDoc.remediation_recommendation`    |
| 3     | Bundle Factory Rebuild                 | [`ReportBundle.capability_details`](../../RAG/app/core/models.py) |
| 4     | Agent Layer Refactor                   | [`rag_formatter.py`](../../pdca/agents/report_module/rag_formatter.py) |
| 5     | Output Validation Layer                | [`validators.py`](../../pdca/agents/report_module/validators.py) |
| 6     | Testing & Before/After Validation      | 7 fixtures + 28 tests                           |

Phase details in [CHANGELOG.md](../../CHANGELOG.md).

## 4. Architecture — single scope dict, single evidence dict

```
        ┌────────────────────┐
        │ assessment_plan    │
        │ + findings         │
        │ + environment      │
        └──────────┬─────────┘
                   │
                   ▼
        ┌────────────────────┐
        │ detect_scope(...)  │
        │ (Phase 1)          │
        └──────────┬─────────┘
                   │  scope_info
    ┌──────────────┼─────────────────┐
    ▼              ▼                 ▼
templates     LLM prompts      build_evidence(...)
(labels,      (scope-aware)     (Phase 5)
cover page)                           │
                                       │  evidence
                                       ▼
                           ReportValidator.validate(text, section)
                                       │
                                       ▼
                           ok?  →  pass       fail?  →  template fallback
                                       │
                                       ▼
                                   validation_report.json
```

Single scope dict and single evidence dict — every downstream consumer
reads the same contract, so drift between layers can only happen at one
explicit boundary.

## 5. Results — quantitative

From
[tests/fixtures/report_baseline/metrics.json](../../tests/fixtures/report_baseline/metrics.json):

### Scope framing

| Fixture | Scope label in HTML    | `bucket` framing? | Expected | Verdict |
|---------|------------------------|-------------------|----------|---------|
| A (S3)  | Amazon S3              | no (all-pass)     | Amazon S3| ✓       |
| B (S3)  | Amazon S3              | data-only         | Amazon S3| ✓       |
| C (S3)  | Amazon S3              | data-only         | Amazon S3| ✓       |
| D (S3, empty) | Amazon S3        | no                | Amazon S3| ✓       |
| E (S3, 12)    | Amazon S3        | data-only         | Amazon S3| ✓       |
| **F (IAM)**   | **AWS IAM**     | **absent**        | AWS IAM  | ✓       |
| **G (multi)** | **AWS Infrastructure** | data-only (findings table) | Generic | ✓ |

Fixture F (IAM-only): **0** occurrences of `Amazon S3` in HTML and
**0** occurrences of the word `bucket`. Primary metric target met.

### Validator catch rate (violating-LLM path)

[`tests/test_validation_e2e.py`](../../tests/test_validation_e2e.py) and
[`test_report_smoke_e2e.py::test_violating_llm_triggers_validator`](../../tests/test_report_smoke_e2e.py)
inject a deliberately drifting LLM on fixture F and assert:

| Injected violation             | Caught by kind          | Leaked to HTML? |
|--------------------------------|-------------------------|-----------------|
| Mentions "S3 bucket" in IAM scope | `off_scope`          | no              |
| Fabricates "9999 resources"    | `hallucinated_number`   | no              |
| Invents "Block Public Access" capability | `ungrounded`  | no              |

### Test footprint

| Suite                                       | New tests (Phases 1–6) |
|---------------------------------------------|-------------------------|
| `test_scope_detector.py`                    | 21                      |
| `test_report_scope_generalization.py`       | 4                       |
| `test_rag_view_formatter.py`                | 14                      |
| `test_report_validator.py`                  | 22                      |
| `test_validation_e2e.py`                    | 3 (live)                |
| `test_report_smoke_e2e.py`                  | 22                      |
| `tests/integration/test_report_rag_flow.py` | 6                       |
| **Total**                                   | **92 new tests**        |

Full suite: 356 passed, 3 skipped (live E2E requires RAG + Ollama up).
No pre-existing tests regressed.

## 6. Results — qualitative (rubric)

From
[tests/fixtures/report_baseline/improvement_report.md](../../tests/fixtures/report_baseline/improvement_report.md)
§4. Before scores are anchored to the plan's Discovery Findings (code
references cited); after scores reflect the post-Phase-5 implementation.

| Criterion                     | Before | After | Δ   |
|-------------------------------|--------|-------|------|
| 1. Scope correctness          | 2      | 5     | +3   |
| 2. Factual accuracy           | 3      | 5     | +2   |
| 3. Grounding                  | 2      | 4     | +2   |
| 4. Coverage                   | 3      | 4     | +1   |
| 5. Actionability              | 2      | 4     | +2   |

**Scope Δ = +3** and **Grounding Δ = +2** both comfortably exceed the
plan's Δ ≥ +1 target.

## 7. Limitations

Surfaced honestly in [improvement_report.md](../../tests/fixtures/report_baseline/improvement_report.md)
§7. Relevant for the thesis's Limitations / Future Work section:

1. **Phase 0 gap.** Physical "before" HTML snapshots were not captured
   before the refactor began. The before/after comparison is therefore
   code-reference anchored rather than HTML-diff anchored. A git
   checkout of the pre-Phase-1 commit + re-run of
   [`scripts/capture_baseline.py`](../../scripts/capture_baseline.py)
   would produce actual before HTML if needed for the thesis.
2. **Mock-LLM artifacts.** The captured "after" HTML uses a
   deterministic mock LLM. Real LLM quality is assessed separately via
   the live E2E tests in
   [`test_validation_e2e.py`](../../tests/test_validation_e2e.py) (RAG
   + Ollama required).
3. **Data-level `bucket` appearance in fixture G.** Multi-service
   fixtures still show the word `bucket` in HTML because it appears in
   finding descriptions (data). The thesis should clarify that the
   target is scope *framing*, not substring absence.
4. **Capability heuristic conservatism.** The `_looks_like_capability`
   filter requires at least one security-domain noun. Exotic domain
   terms (e.g. product brand names that are capability categories) may
   be missed. The validator degrades gracefully — false negatives log
   but do not replace.

## 8. Thesis chapter outline

Suggested structure for the thesis Results chapter:

1. **Problem statement** → §1 here + plan §2.
2. **Design principles** → plan §1 (Correctness > Coverage, Generalize
   first, Gate before render, Fix from root, Dependency-aware phasing,
   Testable at every phase, Backward-safe schema changes).
3. **Architecture diagram** → §4 here + plan §3 (phase map).
4. **Phase-by-phase implementation**
   (scope-detection, validation-rules, rag-integration, data-contracts).
5. **Evaluation**
   (improvement_report + metrics.json) + §6 rubric.
6. **Limitations & Future Work** → §7 here.

## 9. Deferred (optional) phases

| Phase | Plan status | Rationale for deferral                           |
|-------|-------------|--------------------------------------------------|
| 7     | OPTIONAL    | Maturity RAG prompts are not where bias/hallucination concentrates. Core critical path (exec / fail / pass / recommend) is already grounded via Phase 4. |
| 8     | OPTIONAL    | Prompt-token optimization should follow an evaluation baseline. Phase 5 validator provides the baseline; optimization is tuning, not correctness. |

## 10. Reproducibility

```bash
# Full test suite (356 pass, 3 live-skipped).
python -m pytest tests/ --ignore=tests/rag_evaluation

# Regenerate fixture inputs + after artifacts.
python scripts/capture_baseline.py

# Live E2E with real RAG + Ollama (requires both up on :8001 / :11434).
python -m pytest tests/test_validation_e2e.py -v
```

All paths are relative to the repo root; no ENV setup needed beyond the
existing `requirements.txt`.
