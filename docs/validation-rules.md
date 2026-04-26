# Validation Rules — Phase 5

The report agent runs a mandatory validation gate between the LLM
writer and the Jinja template. Sections that fail validation are
replaced with a deterministic template string so the rendered HTML is
always grounded — the LLM cannot leak hallucinated numbers, wrong
services, or invented capability names past the gate.

Source:
[pdca/agents/report_module/validators.py](../pdca/agents/report_module/validators.py).

## 1. Check catalogue

| Kind                   | Trigger                                                                 |
|------------------------|-------------------------------------------------------------------------|
| `off_scope`            | Section mentions an AWS service **not** in `evidence.allowed_services`. |
| `hallucinated_number`  | Number (≥ 5) not in `evidence.allowed_numbers` and not the account id.  |
| `wrong_term`           | Uses a resource noun tied to a service other than `scope.primary_service`. |
| `ungrounded`           | Title-Case capability-style phrase not in `evidence.allowed_capabilities`.|

The four checks run on every LLM-written section. All four issues surface
as `ValidationIssue(section, kind, evidence, details)` in the result bag.

## 2. Evidence contract

`build_evidence(...)` assembles the evidence dict from already-validated
pipeline inputs:

```python
{
    "allowed_numbers":      Set[float],    # walked from pre + post + env counts
    "allowed_services":     Set[str],      # lower-cased service ids from scope
    "allowed_capabilities": Set[str],      # names from RAG bundle
    "account_id":           Optional[str], # 12-digit AWS account id
}
```

The validator accepts a missing key by **degrading gracefully** — an
empty `allowed_capabilities` disables the `ungrounded` check rather than
flagging every phrase. Rationale: the gate must not block sections just
because RAG is down.

Example for IAM-only scope:

```python
evidence = {
    "allowed_numbers":      {6.0, 4.0, 2.0, 1.0, 5.0, 3.0, 123456789012.0},
    "allowed_services":     {"iam"},
    "allowed_capabilities": {"Identity And Access Management",
                              "Access Lifecycle Management"},
    "account_id":           "123456789012",
}
```

## 3. `off_scope` — service token matching

`_iter_service_tokens(text)` yields every AWS service id from
`SERVICE_DISPLAY` found in the stripped text. Rules:

* Word-boundary regex against the lower-cased text — `"s3"` does not
  match `"s3_bucket"` (treated as one token) or `"hts3n"`.
* `iam` is special-cased: only flagged when uppercase (`IAM`) or adjacent
  to `aws`, `user`, `role`, `policy`, `entity`, `group`. Without the
  special case, ordinary Vietnamese prose would false-positive on the
  substring.

Services present in `evidence.allowed_services` are skipped. Everything
else produces an `off_scope` issue.

**Example:** fixture F (IAM scope) with LLM text

> Rà soát AWS IAM đã ghi nhận nhiều **S3 bucket** cấu hình sai.

→ `off_scope` issue, `evidence="s3"`.

## 4. `hallucinated_number` — data-claim gate

Number regex:

```python
_NUMBER_RE = re.compile(r"(?<![\w.])(\d+)(?:[.,](\d{1,2}))?\s*%?")
```

A single regex captures both integers and decimals / percentages. The
check ignores numbers below `ignore_number_below = 5` (default) — small
integers in Vietnamese prose are almost always quantifiers (`3 lỗi`,
`2 đề xuất`), not data claims.

Matching strategy:

1. Cast to `int` — if in `_allowed_int_set` (pre-expanded from
   `allowed_numbers` + rounding variants + account id), pass.
2. Otherwise, if any `allowed_number` is within
   `number_tolerance = 0.5`, pass.
3. Else flag as `hallucinated_number`.

The validator is tolerant of percentages (`75 %`) and decimals
(`75.5 %`) so the LLM can round values without tripping the gate.

**Example:** fixture F with LLM text

> Đã ghi nhận **9999** tài nguyên nghiêm trọng.

→ `hallucinated_number` issue, `evidence="9999"`.

## 5. `wrong_term` — resource-noun mismatch

Fires only when `scope.primary_service` is known (multi-service scope
uses generic nouns, so this check is skipped there).

`_SERVICE_TERMS` is derived from `RESOURCE_TERMS`. The validator checks
every term that belongs to a *different* service against the section
text. Word-boundary match; shared terms (a term that is valid for the
primary service too) are skipped.

**Example:** fixture F (primary = `iam`), LLM text mentions `bucket`
→ `wrong_term` issue, `evidence="bucket"`.

## 6. `ungrounded` — capability grounding

Capability candidates are Title-Case multi-word phrases
(`[A-ZĐ]\w+(\s+[A-ZĐ]\w+){1,5}`). A candidate passes when either:

* its lower-case form is in `allowed_capabilities` exactly, **or**
* it is a substring of an allowed capability (or vice versa), **or**
* it does not look like a capability — the heuristic
  `_looks_like_capability(phrase)` requires at least one security-domain
  noun from `_CAPABILITY_KEYWORDS`:

```
access, control, protection, encryption, logging, monitoring, backup,
identity, governance, management, detection, response, network, data,
security, configuration, compliance, audit, recovery
```

This keeps the check from screaming at every proper noun (country
names, product brands) while catching capability names the LLM
invented.

Stopwords (`_CAPABILITY_STOPWORDS`) cover common Title-Case phrases
that are never capabilities (`Amazon Web Services`, `Executive
Summary`, section headings).

**Example:** RAG bundle provided `Identity And Access Management`.
LLM text

> Đội bảo mật đề xuất áp dụng **Zero Trust Architecture**.

→ `ungrounded` issue, `evidence="Zero Trust Architecture"`.

## 7. Fallback policy

The plan offered three strategies. The implementation uses **(A)
Template fallback** — the safest, zero-token option:

```python
# pdca/agents/report_agent.py::_validate_section
result = validator.validate(text, section)
if result.ok:
    return text
self._validation_issues.extend(result.issues)
return fallback if fallback else text
```

Fallback strings are produced by `_make_section_fallbacks(pre, post,
scope_info)` — short, deterministic, scope-aware Vietnamese snippets
covering every LLM-written section. When the gate fires, the rendered
HTML always contains the fallback, never the offending text.

## 8. Validation report

At the end of each run, `ReportAgent._write_validation_report(path)`
serialises the collected issues to `{job_id}/validation_report.json`:

```json
{
  "sections_validated": ["executive_summary", "system_overview", ...],
  "issue_count": 2,
  "summary": {"off_scope": 1, "hallucinated_number": 1},
  "issues": [
    {
      "section": "executive_summary",
      "kind":    "off_scope",
      "evidence":"s3",
      "details": "Service 's3' is not in scan scope (['iam'])."
    },
    ...
  ]
}
```

The report is consumed by the Phase 6 acceptance tests
([tests/test_report_smoke_e2e.py](../tests/test_report_smoke_e2e.py))
and is thesis-usable evidence that the gate fires on drift.

## 9. Performance budget

The plan caps validator overhead at 50 ms / section. Achieved by:

* Pre-computing `_allowed_int_set` and `_allowed_caps_lower` once at
  construction.
* Using compiled regexes (`_TAG_RE`, `_NUMBER_RE`, `_CAP_PATTERN`).
* Skipping checks whose evidence is empty.

A sentinel test in
[tests/test_report_validator.py](../tests/test_report_validator.py)
asserts each check completes in well under the budget on a typical
section.
