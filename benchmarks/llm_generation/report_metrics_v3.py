"""Deterministic metrics for Report Agent Evaluation v3.

7 deterministic metrics (the 8th `claim_support_rate` and the 9th
`actionability_likert` are LLM-judge, handled in ``report_judges.py``).

        # | Axis          | Metric                           | Kind
        --+---------------+----------------------------------+-------
        1 | Structure     | structure_pass_rate              | det
        2 | Scope         | off_scope_mention_rate           | det
        3 | Scope         | scope_accuracy                   | det
        4 | Faithfulness  | numerical_faithfulness           | det
        5 | Faithfulness  | capability_grounding_rate        | det
        6 | Correctness   | template_data_accuracy           | det
        7 | Correctness   | ndcg_at_5_severity               | det

Each metric function returns a ``dict`` with at least a ``score`` key so
the aggregator can treat them uniformly.

We reuse:
* ``benchmarks.llm_generation.report_metrics.evaluate_structure`` (hard_pass
  → structure_pass_rate) — mature, already tested.
* ``benchmarks.llm_generation.report_metrics.evaluate_correctness`` (four
  sub-scores are combined 1:1:1:1 into template_data_accuracy).
* ``pdca.agents.report_module.validators.ReportValidator`` +
  ``build_evidence`` for scope / numerical / grounding checks so we do
  not diverge from the production gate logic.
* ``pdca.agents.report_module.scope_detector.detect_scope`` to compute
  the observed scope from findings.
"""
from __future__ import annotations

import re
from html import unescape
from typing import Any, Dict, List, Optional, Sequence

from benchmarks.llm_generation.ranking_metrics import (
    extract_narrative_ranking,
    ndcg_at_k,
    severity_relevance,
)
from benchmarks.llm_generation.report_metrics import (
    evaluate_correctness,
    evaluate_structure,
)
from pdca.agents.report_module.scope_detector import detect_scope
from pdca.agents.report_module.validators import (
    ReportValidator,
    build_evidence,
    extract_capability_candidates,
)


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return unescape(_TAG_RE.sub(" ", text or ""))


# ---------------------------------------------------------------------------
# Narrative extraction (for the validator-based metrics)
# ---------------------------------------------------------------------------

# LLM-authored sections. We score these — not the template stats / tables.
# Kept compatible with ``report_metrics._LLM_SECTION_PATTERNS`` but named
# independently so we don't silently break if that list changes.
_LLM_SECTIONS: List[tuple] = [
    ("executive_summary", r"<h1>1\. Tóm tắt điều hành</h1>\s*(.*?)\s*<h1>"),
    ("assessment_goals", r"<h2>2\.2 Mục tiêu đánh giá</h2>\s*(.*?)\s*<h1>"),
    ("pass_overview", r"<h3>Tổng quan các mục ĐẠT</h3>\s*(.*?)\s*<h3>"),
    ("fail_overview", r"<h3>Tổng quan các mục KHÔNG ĐẠT</h3>\s*(.*?)\s*<h1>"),
    ("post_analysis", r"<h2>6\.3 Đánh giá của chuyên gia</h2>\s*(.*?)\s*<h1>"),
    ("recommendations",
     r"<h1>7\. Khuyến nghị[^<]*</h1>(.*?)(?:<hr\b|<h1>|</body>|$)"),
]


_HEADING_RE = re.compile(r"<h[1-6][^>]*>.*?</h[1-6]>", re.DOTALL | re.IGNORECASE)


def _extract_llm_sections(html: str) -> Dict[str, str]:
    """Extract the LLM narrative per section, stripped of HTML.

    Inner subsection headings (``<h2>7.1 Khuyến nghị</h2>`` etc.) are
    dropped *before* tag stripping so their numeric prefixes (``7.1``,
    ``7.2``, ``6.3``) don't leak into the numerical-faithfulness check
    as false-positive data claims.
    """
    out: Dict[str, str] = {}
    for name, pattern in _LLM_SECTIONS:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            inner = _HEADING_RE.sub(" ", m.group(1))
            out[name] = _strip_html(inner)
    return out


# ---------------------------------------------------------------------------
# Metric 1 — Structure pass rate
# ---------------------------------------------------------------------------

def metric_structure_pass_rate(
    html: str, output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """1 if the four hard structure checks all pass, else 0."""
    result = evaluate_structure(html, output_dir=output_dir)
    return {
        "score": 1.0 if result["hard_pass"] else 0.0,
        "details": {
            "html_valid": result["html_valid"],
            "section_presence_rate": result["section_presence_rate"],
            "no_template_leak": result["no_template_leak"],
            "no_none_display": result["no_none_display"],
        },
    }


# ---------------------------------------------------------------------------
# Metric 2 — Off-scope mention rate
# ---------------------------------------------------------------------------

def metric_off_scope_mention_rate(
    html: str,
    expected: Dict[str, Any],
    report_data: Dict[str, Any],
    rag_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Fraction of LLM sections with at least one off_scope issue.

    Also counts any case-level forbidden term from ``expected.forbidden_terms``
    so adversarial cases (RAG noise injection) get scored even when the
    token is not one of ``scope_detector``'s AWS service ids.
    """
    sections = _extract_llm_sections(html)
    if not sections:
        return {"score": 0.0, "sections_with_issue": 0, "total_sections": 0,
                "note": "no LLM sections"}

    scope = detect_scope(
        findings=report_data.get("raw_pre_findings", []),
        services_hint=(report_data.get("scope") or {}).get("services"),
    )
    evidence = build_evidence(
        findings=report_data.get("raw_pre_findings", []),
        pre=report_data.get("pre"),
        post=report_data.get("post"),
        scope=scope,
        env=report_data.get("environment"),
        rag_context=rag_snapshot,
    )
    validator = ReportValidator(scope=scope, evidence=evidence)

    forbidden = [
        t.lower() for t in (expected.get("forbidden_terms") or [])
    ]

    bad = 0
    detail: List[Dict[str, Any]] = []
    for name, text in sections.items():
        v = validator.validate(text, section=name)
        off = [i for i in v.issues if i.kind == "off_scope"]
        plain = text.lower()
        forbidden_hits = [t for t in forbidden if re.search(
            r"\b" + re.escape(t) + r"\b", plain
        )]
        has_issue = bool(off) or bool(forbidden_hits)
        if has_issue:
            bad += 1
        detail.append({
            "section": name,
            "off_scope": [i.evidence for i in off],
            "forbidden_hits": forbidden_hits,
        })

    total = len(sections)
    return {
        "score": round(bad / total, 4) if total else 0.0,
        "sections_with_issue": bad,
        "total_sections": total,
        "details": detail,
    }


# ---------------------------------------------------------------------------
# Metric 3 — Scope accuracy
# ---------------------------------------------------------------------------

def metric_scope_accuracy(
    expected: Dict[str, Any],
    report_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare detected scope vs expected scope.

    Pass iff ``primary_service``, ``is_multi_service`` and ``service_list``
    (as a set) all match. This is a property of the scope detector +
    input data, independent of the LLM output — so it cleanly shows
    scope generalisation regardless of model behaviour.
    """
    detected = detect_scope(
        findings=report_data.get("raw_pre_findings", []),
        services_hint=(report_data.get("scope") or {}).get("services"),
    )
    exp_scope = expected.get("scope") or {}

    primary_ok = detected.get("primary_service") == exp_scope.get("primary_service")
    multi_ok = bool(detected.get("is_multi_service")) == bool(
        exp_scope.get("is_multi_service")
    )
    set_ok = set(detected.get("service_list") or []) == set(
        exp_scope.get("service_list") or []
    )
    passed = primary_ok and multi_ok and set_ok

    return {
        "score": 1.0 if passed else 0.0,
        "detected": {
            "primary_service": detected.get("primary_service"),
            "is_multi_service": detected.get("is_multi_service"),
            "service_list": detected.get("service_list"),
        },
        "expected": {
            "primary_service": exp_scope.get("primary_service"),
            "is_multi_service": exp_scope.get("is_multi_service"),
            "service_list": exp_scope.get("service_list"),
        },
    }


# ---------------------------------------------------------------------------
# Metric 4 — Numerical faithfulness
# ---------------------------------------------------------------------------

def metric_numerical_faithfulness(
    html: str,
    report_data: Dict[str, Any],
    rag_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Fraction of LLM sections with zero hallucinated-number issues.

    Uses ``ReportValidator._check_hallucinated_numbers`` under the hood —
    so benchmark and production agree on what counts as a data claim.
    """
    sections = _extract_llm_sections(html)
    if not sections:
        return {"score": 0.0, "clean_sections": 0, "total_sections": 0,
                "note": "no LLM sections"}

    scope = detect_scope(
        findings=report_data.get("raw_pre_findings", []),
        services_hint=(report_data.get("scope") or {}).get("services"),
    )
    evidence = build_evidence(
        findings=report_data.get("raw_pre_findings", []),
        pre=report_data.get("pre"),
        post=report_data.get("post"),
        scope=scope,
        env=report_data.get("environment"),
        rag_context=rag_snapshot,
    )
    validator = ReportValidator(scope=scope, evidence=evidence)

    clean = 0
    detail: List[Dict[str, Any]] = []
    for name, text in sections.items():
        v = validator.validate(text, section=name)
        halluc = [i for i in v.issues if i.kind == "hallucinated_number"]
        if not halluc:
            clean += 1
        detail.append({
            "section": name,
            "hallucinated_numbers": [i.evidence for i in halluc],
        })

    total = len(sections)
    return {
        "score": round(clean / total, 4) if total else 0.0,
        "clean_sections": clean,
        "total_sections": total,
        "details": detail,
    }


# ---------------------------------------------------------------------------
# Metric 5 — Capability grounding rate
# ---------------------------------------------------------------------------

def metric_capability_grounding_rate(
    html: str,
    expected: Dict[str, Any],
    rag_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """How much of the LLM's capability talk is grounded in RAG evidence?

    Precision-only formulation:

        score = 1 − ungrounded_count / candidate_count

    where *candidate* = a Title-Case multi-word phrase the validator
    considers a capability-name claim, and *ungrounded* = that phrase is
    not present in the RAG bundle's ``capability_details`` /
    ``control_themes``. Vacuous 1.0 when the narrative makes no
    capability claims at all (nothing to ground = no violation).

    Why not require the LLM to echo specific RAG capability names: the
    agent writes Vietnamese and paraphrases freely. Penalising it for
    not reproducing English labels like "Data Storage Protection"
    measures translation fidelity, not grounding. Instead we measure
    precision — of the capability-sounding claims the LLM *does* make,
    how many are warranted by the bundle.

    ``expected.required_capabilities`` is still reported as
    ``required_hits`` / ``required_total`` for LVTN discussion but does
    NOT feed into the score.
    """
    sections = _extract_llm_sections(html)
    if not sections:
        return {"score": 0.0, "note": "no LLM sections"}

    # Build a scope + evidence dict keyed on the RAG snapshot alone; we
    # want to know what's grounded in RAG, independent of findings.
    evidence = build_evidence(rag_context=rag_snapshot)
    validator = ReportValidator(scope={}, evidence=evidence)

    total_candidates = 0
    ungrounded_count = 0
    for name, text in sections.items():
        v = validator.validate(text, section=name)
        for issue in v.issues:
            if issue.kind == "ungrounded":
                ungrounded_count += 1
        total_candidates += len(extract_capability_candidates(text))

    if total_candidates == 0:
        score = 1.0
    else:
        score = 1.0 - (ungrounded_count / total_candidates)

    # Report (but do not score) required-capability coverage — useful
    # for discussion, not gating.
    narrative = " ".join(sections.values()).lower()
    required = [
        c.strip() for c in (expected.get("required_capabilities") or []) if c
    ]
    required_hits = sum(1 for c in required if c.lower() in narrative)

    return {
        "score": round(max(0.0, min(1.0, score)), 4),
        "ungrounded_count": ungrounded_count,
        "candidate_count": total_candidates,
        "required_hits": required_hits,
        "required_total": len(required),
    }


# ---------------------------------------------------------------------------
# Metric 6 — Template data accuracy (correctness bundle)
# ---------------------------------------------------------------------------

def metric_template_data_accuracy(
    html: str,
    report_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Mean of the four correctness sub-scores from the v1 evaluator.

    Bundled so LVTN has one "are the numbers/badges/tables right?" number
    per case. The component scores are exposed for per-case drill-down.
    """
    parts = evaluate_correctness(html, report_data)
    components = [
        parts.get("stats_accuracy", 0.0),
        parts.get("findings_table_accuracy", 0.0),
        parts.get("score_accuracy", 0.0),
        parts.get("status_color_accuracy", 0.0),
    ]
    score = sum(components) / len(components)
    return {
        "score": round(score, 4),
        "components": {
            "stats_accuracy": parts.get("stats_accuracy"),
            "findings_table_accuracy": parts.get("findings_table_accuracy"),
            "score_accuracy": parts.get("score_accuracy"),
            "status_color_accuracy": parts.get("status_color_accuracy"),
        },
    }


# ---------------------------------------------------------------------------
# Metric 7 — NDCG@5 severity
# ---------------------------------------------------------------------------

def metric_ndcg_at_5_severity(
    html: str,
    expected: Dict[str, Any],
    report_data: Dict[str, Any],
) -> Dict[str, Any]:
    """NDCG@5 over the finding order the LLM chose to mention.

    Applicable only when the case carries ``expected.severity_ranking_gt``
    (C3 cases). For other cases we return ``score=None`` and skip it in
    aggregation so we don't dilute the signal.
    """
    gt = expected.get("severity_ranking_gt")
    if not gt:
        return {"score": None, "note": "no ground-truth ranking"}

    findings = report_data.get("raw_pre_findings", []) or []
    predicted = extract_narrative_ranking(html, findings)
    relevance = severity_relevance(findings)

    score = ndcg_at_k(predicted, relevance, k=5)
    return {
        "score": score,
        "predicted_top5": predicted[:5],
        "ground_truth_top5": gt[:5],
    }


# ---------------------------------------------------------------------------
# Top-level per-case evaluator
# ---------------------------------------------------------------------------

def evaluate_case_deterministic(
    html: str,
    case: Dict[str, Any],
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Run all 7 deterministic metrics on a single case's HTML output."""
    report_data = case["input"]["report_data"]
    rag_snapshot = case["input"].get("rag_snapshot") or {}
    expected = case.get("expected") or {}

    return {
        "case_id": case["case_id"],
        "group": case.get("group"),
        "metrics": {
            "structure_pass_rate": metric_structure_pass_rate(html, output_dir),
            "off_scope_mention_rate": metric_off_scope_mention_rate(
                html, expected, report_data, rag_snapshot
            ),
            "scope_accuracy": metric_scope_accuracy(expected, report_data),
            "numerical_faithfulness": metric_numerical_faithfulness(
                html, report_data, rag_snapshot
            ),
            "capability_grounding_rate": metric_capability_grounding_rate(
                html, expected, rag_snapshot
            ),
            "template_data_accuracy": metric_template_data_accuracy(
                html, report_data
            ),
            "ndcg_at_5_severity": metric_ndcg_at_5_severity(
                html, expected, report_data
            ),
        },
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _scores(cases: Sequence[Dict], metric: str) -> List[float]:
    vals: List[float] = []
    for c in cases:
        m = c["metrics"].get(metric) or {}
        s = m.get("score")
        if s is None:
            continue
        vals.append(float(s))
    return vals


def aggregate(cases: Sequence[Dict]) -> Dict[str, Any]:
    """Aggregate per-case deterministic results into headline metrics."""
    metric_names = [
        "structure_pass_rate",
        "off_scope_mention_rate",
        "scope_accuracy",
        "numerical_faithfulness",
        "capability_grounding_rate",
        "template_data_accuracy",
        "ndcg_at_5_severity",
    ]
    out: Dict[str, Any] = {}
    for name in metric_names:
        vals = _scores(cases, name)
        out[name] = {
            "mean": round(sum(vals) / len(vals), 4) if vals else None,
            "n": len(vals),
        }

    # Group breakdown.
    groups: Dict[str, List[Dict]] = {}
    for c in cases:
        groups.setdefault(c.get("group") or "unknown", []).append(c)
    by_group: Dict[str, Dict[str, Any]] = {}
    for g, gcases in groups.items():
        by_group[g] = {
            "n": len(gcases),
            **{
                name: (
                    round(sum(_scores(gcases, name)) / len(_scores(gcases, name)), 4)
                    if _scores(gcases, name) else None
                )
                for name in metric_names
            },
        }

    return {"overall": out, "by_group": by_group}
