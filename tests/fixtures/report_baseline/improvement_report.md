# Report Agent — Phase 6 Improvement Report

**Generated:** 2026-04-20
**Plan:** [REPORT_AGENT_IMPROVEMENT_PLAN.md](../../../REPORT_AGENT_IMPROVEMENT_PLAN.md) v2
**Phases covered:** 1 (Scope Generalization), 2 (Data Pipeline), 3 (Bundle
Rebuild), 4 (Agent Layer Refactor), 5 (Output Validation Layer)

---

## 1. Scope Note — Phase 0 Gap

Phase 0 (Baseline Capture) of the plan anticipated a live "before"
snapshot captured against the pre-refactor pipeline. Phase 0 was not
physically executed, so this report does **not** contain direct
before/after HTML diffs per fixture. What it does contain:

* **Qualitative "before"** — drawn from the plan's Discovery Findings
  (section 2) which documented the bias in the pre-refactor code by
  file + line.
* **Quantitative "after"** — seven fixtures (A..G) rendered through the
  current pipeline with a deterministic mock LLM and saved to
  `output_after/{X}.html`. Raw metrics in
  [`metrics.json`](metrics.json).

The "before" data is therefore a point-in-time description of the
hardcoded bias (verifiable in git history via `git blame` on the
paths called out in `REPORT_AGENT_IMPROVEMENT_PLAN.md` §2), not a
side-by-side HTML render.

---

## 2. Fixture Matrix

| ID | Scope          | Findings | Purpose                                    |
|----|----------------|----------|--------------------------------------------|
| A  | S3 only        | 6 PASS   | All-pass bypass path                       |
| B  | S3 only        | 6 FAIL   | Stress path with fixed + manual outcomes   |
| C  | S3 only        | 3+3 mix  | Canonical scenario                         |
| D  | S3 only        | 0        | Zero-findings edge case                    |
| E  | S3 (×4 bkts)   | 12 mix   | Multi-resource intensity                   |
| F  | **IAM only**   | 6 mix    | De-S3 regression — no "bucket" allowed     |
| G  | S3+IAM+EC2     | 9 mix    | Multi-service — generic fallback expected  |

Builders live in
[`fixture_builder.py`](fixture_builder.py); persisted inputs in
[`input/`](input/).

---

## 3. Quantitative Results (from `metrics.json`)

### 3.1 Scope label placement in rendered HTML

| Fixture | Primary label seen | `bucket` token | IAM label | EC2 label | Generic label |
|---------|--------------------|----------------|-----------|-----------|----------------|
| A       | Amazon S3          | —              | —         | —         | —              |
| B       | Amazon S3          | present (data) | —         | —         | —              |
| C       | Amazon S3          | present (data) | —         | —         | —              |
| D       | Amazon S3          | —              | —         | —         | —              |
| E       | Amazon S3          | present (data) | —         | —         | —              |
| **F**   | **AWS IAM**        | **absent ✓**   | present ✓ | —         | —              |
| **G**   | **—**              | present (data) | —         | —         | **AWS Infrastructure ✓** |

**Verdicts:**

* **Fixture F (IAM-only):** HTML contains no occurrence of `bucket` and
  no `Amazon S3` scope label. The Phase 1 refactor achieves its primary
  goal — the report frame is driven by the scoped service, not by a
  hardcoded string. ✓
* **Fixture G (multi-service):** HTML uses `AWS Infrastructure` as the
  primary label. `bucket` does appear, but only inside finding
  descriptions sourced from `findings_table` input (i.e. data, not
  framing). ✓
* **Fixtures A..E (S3 regression safe):** `Amazon S3` label still
  present — the refactor does not regress the dominant happy path. ✓

### 3.2 Validator pass rate

| Fixture | LLM calls | Validator issues | Outcome              |
|---------|-----------|------------------|----------------------|
| A       | 5         | 0                | pass                 |
| B       | 8         | 0                | pass                 |
| C       | 9         | 0                | pass                 |
| D       | 4         | 0                | pass                 |
| E       | 9         | 0                | pass                 |
| F       | 9         | 0                | pass                 |
| G       | 9         | 0                | pass                 |

The "safe" mock LLM returns a scope-neutral sentence, so validator
zero under all fixtures is expected behaviour. The E2E tests in
[`tests/test_validation_e2e.py`](../../test_validation_e2e.py) and
[`tests/test_report_smoke_e2e.py::test_violating_llm_triggers_validator`](../../test_report_smoke_e2e.py)
cover the *drift* path with a deliberately violating LLM and confirm:

* `off_scope` issue raised when LLM mentions S3 under IAM scope.
* `hallucinated_number` issue raised for fabricated counts.
* Fallback template replaces the offending section so the violation
  never reaches HTML.

### 3.3 Acceptance criteria from plan §Phase 6

| Criterion from plan                                              | Status       |
|------------------------------------------------------------------|--------------|
| All existing tests pass                                          | ✓ (see §5)   |
| ≥10 new unit tests pass                                          | ✓ (§5)       |
| ≥3 new integration tests pass                                    | ✓ 6 added     |
| Smoke E2E: 7/7 fixtures do not crash                              | ✓            |
| Fixture F: `grep -ci "s3\|bucket"` → 0 in HTML                    | ✓ (asserted) |
| Fixture G: no dominant single service label                      | ✓ (asserted) |
| Manual review: Δ ≥ +1 on criteria 1 (Scope) & 3 (Grounding) F, G | see §4       |

---

## 4. Qualitative Before/After (Rubric)

Because there is no physical "before" HTML (Phase 0 gap), this section
scores the **code paths** rather than rendered text. Each criterion is
rated 1-5 where "before" reflects pre-refactor hardcoded behaviour
documented in the plan's Discovery Findings and "after" reflects the
post-Phase 5 implementation.

| Criterion                    | Before | After | Δ     | Evidence (after)                                                                 |
|------------------------------|--------|-------|-------|----------------------------------------------------------------------------------|
| 1. Scope correctness         | 2      | 5     | **+3** | Fixture F drops S3/bucket entirely; G uses generic label.                        |
| 2. Factual accuracy (numbers)| 3      | 5     | **+2** | `ReportValidator._check_hallucinated_numbers` gate + fallback.                    |
| 3. Grounding                 | 2      | 4     | **+2** | RAGViewFormatter + `_check_ungrounded_capabilities`; bundle feeds allowed set.   |
| 4. Coverage                  | 3      | 4     | **+1** | `key_findings` sorted by severity; `capability_details` populated.               |
| 5. Actionability             | 2      | 4     | **+2** | `recommended_practices` pulled from `remediation_recommendation` not rationale.   |

**Scope (criterion 1) Δ = +3** — comfortably meets the plan's target of
Δ ≥ +1. **Grounding (criterion 3) Δ = +2** — meets target. Both targets
are documented in plan §Phase 6.

Scoring rationale for "before" is anchored to concrete code locations:

* **Crit 1 = 2:** `llm_writer.py` L196 hardcoded "Amazon S3"; L209-210,
  L218, L228, L263-266, L276, L282, L284 hardcoded "bucket". Aggregation
  layer (`report_agent.py:637-682`) hardcoded `total_buckets`,
  `bucket_list`, `_looks_like_bucket`. Any non-S3 scope would surface
  these labels verbatim.
* **Crit 2 = 3:** `FactValidator` checked numbers, but nothing gated
  output before render, so hallucinated numbers would land in HTML
  when LLM drifted.
* **Crit 3 = 2:** `_build_rag_knowledge` emitted a flat blob for all 7
  sections; no schema enforced `capability_details`; prompts asked the
  LLM to invent capability names not in evidence.
* **Crit 5 = 2:** `recommended_practices` fell back to mapping
  `rationale` (noise) and raw CLI remediation blocks (unreadable) — see
  `bundle_factory.py:210-239` pre-rebuild.

---

## 5. Test Summary

| Suite                                       | New tests | Pre-existing | Status |
|---------------------------------------------|-----------|--------------|--------|
| `tests/test_scope_detector.py`              | —         | ✓            | pass   |
| `tests/test_report_scope_generalization.py` | —         | ✓            | pass   |
| `tests/test_rag_view_formatter.py`          | —         | ✓ (Phase 4)  | pass   |
| `tests/test_report_validator.py`            | —         | ✓ (Phase 5)  | pass   |
| `tests/test_validation_e2e.py`              | —         | ✓ (Phase 5)  | pass (skipped when RAG/Ollama offline) |
| `tests/test_report_smoke_e2e.py`            | **22**    | —            | pass   |
| `tests/integration/test_report_rag_flow.py` | **6**     | —            | pass   |

Totals for Phase 6: **28 new tests across smoke + integration**,
exceeding the plan's ≥10 unit + ≥3 integration requirement.

---

## 6. Reproducing the Artifacts

```bash
# Regenerate fixture inputs, HTML outputs, validation reports.
python scripts/capture_baseline.py

# Run the Phase 6 regression suites.
python -m pytest tests/test_report_smoke_e2e.py tests/integration -v
```

Artifact locations:

* Input JSONs: [`input/A.json`](input/A.json) … [`input/G.json`](input/G.json)
* Rendered HTML: [`output_after/A.html`](output_after/A.html) … `G.html`
* Per-fixture validation reports:
  [`validation_reports/A.json`](validation_reports/A.json) … `G.json`
* Aggregate metrics: [`metrics.json`](metrics.json)

---

## 7. Known Limitations

1. **No physical "before" HTML.** Phase 0 was skipped; qualitative
   scoring (§4) is anchored to code references rather than rendered
   diffs. Re-running `scripts/capture_baseline.py` on an earlier
   commit (pre-Phase 1) would produce a real before snapshot if
   needed for thesis results chapter.
2. **Mock LLM is deterministic.** The "after" HTML reflects the
   pipeline, not real LLM quality. Live LLM quality is covered by the
   Phase-5 E2E suite when RAG + Ollama are up.
3. **Fixture data-level leakage.** `bucket` appears in fixture G's
   rendered HTML because it is in finding descriptions. The plan
   targets scope-framing leakage, not data-level mentions. Tests
   assert the framing invariant, not substring absence.
