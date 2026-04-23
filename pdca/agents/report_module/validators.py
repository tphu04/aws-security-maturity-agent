"""Output validation layer for report sections — Phase 5.

``ReportValidator`` is a mandatory gate run between the LLM writer and
the Jinja template. It inspects the generated text for four failure
modes and returns a structured :class:`ValidationResult` the caller can
use to swap in a safe template fallback.

Failure modes
-------------
* ``off_scope``          — mentions an AWS service not in the scan scope.
* ``hallucinated_number``— uses a number that is not in the allowed set.
* ``wrong_term``         — uses a resource noun inappropriate for the
                           primary service (e.g. "bucket" in an IAM-only
                           report).
* ``ungrounded``         — names a capability that is not in the RAG
                           evidence.

Design notes
------------
* HTML is stripped before text analysis so asserts don't false-positive
  on attribute values (``class="critical"``) or hex colour codes.
* Numbers below 5 are ignored — small integers in Vietnamese are almost
  always quantifiers ("3 lỗi") rather than data claims. This matches
  :class:`FactValidator`'s behaviour so the two pipes agree.
* The capability heuristic matches multi-word Title-Case phrases (e.g.
  "Block Public Access"). Phrases present in the RAG evidence
  (``allowed_capabilities``) are allowed. Common English nouns that
  happen to be capitalised are not flagged.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from html import unescape
from typing import Any, Dict, Iterable, List, Optional, Set

from pdca.agents.report_module.scope_detector import (
    RESOURCE_TERMS,
    SERVICE_DISPLAY,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Public dataclasses
# ----------------------------------------------------------------------
@dataclass
class ValidationIssue:
    """Single violation detected in one section's output."""
    section: str
    kind: str              # off_scope | hallucinated_number | wrong_term | ungrounded
    evidence: str          # offending token / phrase
    details: str = ""      # human-readable explanation

    def to_dict(self) -> Dict[str, str]:
        return {
            "section": self.section,
            "kind": self.kind,
            "evidence": self.evidence,
            "details": self.details,
        }


@dataclass
class ValidationResult:
    ok: bool
    issues: List[ValidationIssue] = field(default_factory=list)

    def __bool__(self) -> bool:  # allow `if result: ...`
        return self.ok

    def summary(self) -> Dict[str, int]:
        by_kind: Dict[str, int] = {}
        for i in self.issues:
            by_kind[i.kind] = by_kind.get(i.kind, 0) + 1
        return by_kind


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
# Match any integer / decimal token. We deliberately allow long digit
# runs so an account id ("123456789012") arrives as a single match that
# can be checked against the allowed-int set in one shot rather than
# getting chopped into a handful of 5-digit fragments.
_NUMBER_RE = re.compile(r"(?<![\w.])(\d+)(?:[.,](\d{1,2}))?\s*%?")

# Resource nouns tied to one canonical service id. Used by the
# wrong-term check. Keys are Vietnamese / English lowercase forms the LLM
# is most likely to emit.
_SERVICE_TERMS: Dict[str, Set[str]] = {}
for _svc, (_s, _p) in RESOURCE_TERMS.items():
    _SERVICE_TERMS.setdefault(_svc, set())
    _SERVICE_TERMS[_svc].add(_s.lower())
    _SERVICE_TERMS[_svc].add(_p.lower())

# Full list of AWS service tokens the validator watches for. Derived
# from SERVICE_DISPLAY so the set stays in sync with scope_detector.
_AWS_SERVICE_TOKENS: Set[str] = {svc.lower() for svc in SERVICE_DISPLAY}
# "iam" also appears inside regular Vietnamese words — require it to be
# uppercased OR part of ``AWS IAM`` / ``iam user`` patterns. See
# ``_iter_service_tokens``.

# Stopwords for capability heuristic — common Title-Case phrases that
# are not capability names. Keeps the ungrounded check from screaming at
# every proper noun.
_CAPABILITY_STOPWORDS: Set[str] = {
    "amazon web services", "amazon", "aws", "executive summary",
    "system description", "assessment goals", "fail findings",
    "pass findings", "remediation plan", "khuyến nghị chiến lược",
    "data protection at rest", "identity and access management",  # keep if in evidence
}


def _strip_html(text: str) -> str:
    return unescape(_TAG_RE.sub(" ", text or ""))


def _iter_service_tokens(text: str) -> Iterable[str]:
    """Yield AWS service tokens found in ``text``.

    Matches on word boundaries, lower-cased. ``iam`` is only flagged when
    written in upper case or adjacent to ``aws``/``user``/``role`` so we
    don't false-positive on random three-letter substrings.
    """
    plain = _strip_html(text)
    lowered = plain.lower()

    for svc in _AWS_SERVICE_TOKENS:
        if svc == "iam":
            # Match "IAM" in original casing, or "aws iam" / "iam user"
            if re.search(r"\bIAM\b", plain) or re.search(
                r"\b(aws\s+iam|iam\s+(user|role|policy|polic|entit|grup|group))\b",
                lowered,
            ):
                yield svc
            continue
        if re.search(r"\b" + re.escape(svc) + r"\b", lowered):
            yield svc


def _extract_numbers(text: str, min_value: int = 5) -> List[float]:
    plain = _strip_html(text)
    out: List[float] = []
    for m in _NUMBER_RE.finditer(plain):
        whole, frac = m.group(1), m.group(2)
        try:
            val = float(whole) if not frac else float(f"{whole}.{frac}")
        except ValueError:
            continue
        if val >= min_value:
            out.append(val)
    return out


_CAP_PATTERN = re.compile(
    r"\b([A-ZĐ][\wÀ-ỹ]+(?:\s+[A-ZĐ][\wÀ-ỹ]+){1,5})\b"
)


def _extract_capability_candidates(text: str) -> List[str]:
    """Return multi-word Title-Case phrases — candidate capability names."""
    plain = _strip_html(text)
    found = []
    for m in _CAP_PATTERN.finditer(plain):
        phrase = m.group(1).strip()
        if phrase.lower() in _CAPABILITY_STOPWORDS:
            continue
        found.append(phrase)
    return found


# ----------------------------------------------------------------------
# ReportValidator
# ----------------------------------------------------------------------
class ReportValidator:
    """Validate a single LLM-authored section against scope + evidence.

    Parameters
    ----------
    scope : dict
        Result of :func:`detect_scope` — at minimum ``primary_service``,
        ``service_list`` and ``resource_term``/``resource_term_plural``.
    evidence : dict
        ``allowed_numbers`` : set[float]
            Numbers (counts, percentages, severity tallies) that may
            legitimately appear in the output. Populated from the raw
            report data upstream.
        ``allowed_services`` : set[str]
            Lower-cased service ids in scope. Mentions outside this set
            are flagged ``off_scope``.
        ``allowed_capabilities`` : set[str]
            Capability display names present in the RAG evidence
            (``capability_details`` + ``control_themes``). Candidate
            phrases not in this set trigger ``ungrounded``.
        ``account_id`` : str, optional
            Passed through so the number validator ignores the account
            number (it is always present and is not a data claim).
    number_tolerance : float
        Tolerance when matching floats against ``allowed_numbers``.
    ignore_number_below : int
        Numbers strictly less than this value are skipped.
    """

    def __init__(
        self,
        scope: Optional[Dict[str, Any]] = None,
        evidence: Optional[Dict[str, Any]] = None,
        number_tolerance: float = 0.5,
        ignore_number_below: int = 5,
    ):
        self.scope = scope or {}
        self.evidence = evidence or {}
        self.number_tolerance = number_tolerance
        self.ignore_number_below = ignore_number_below

        # Pre-compute allowed integer expansions for fast lookup.
        self._allowed_int_set: Set[int] = set()
        for v in self.evidence.get("allowed_numbers") or set():
            self._allowed_int_set.add(int(v))
            self._allowed_int_set.add(int(v + 0.5))
            self._allowed_int_set.add(int(v + 0.999))
        # Account id is not a data claim.
        acct = self.evidence.get("account_id")
        if acct and str(acct).strip().isdigit():
            try:
                self._allowed_int_set.add(int(str(acct).strip()))
            except ValueError:
                pass

        # Normalise allowed capabilities to lower-case, strip whitespace.
        self._allowed_caps_lower: Set[str] = {
            c.strip().lower() for c in
            (self.evidence.get("allowed_capabilities") or set())
            if c and isinstance(c, str)
        }
        self._allowed_services: Set[str] = {
            s.lower() for s in
            (self.evidence.get("allowed_services") or set())
            if s
        }

        # Primary service for wrong-term check.
        self._primary_service: Optional[str] = (
            self.scope.get("primary_service") or None
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def validate(self, text: str, section: str) -> ValidationResult:
        """Run all four checks on ``text`` and return a result bag."""
        if not text or not text.strip():
            return ValidationResult(ok=True)

        issues: List[ValidationIssue] = []
        issues += self._check_off_scope(text, section)
        issues += self._check_hallucinated_numbers(text, section)
        issues += self._check_wrong_term(text, section)
        issues += self._check_ungrounded(text, section)
        return ValidationResult(ok=not issues, issues=issues)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------
    def _check_off_scope(self, text: str, section: str) -> List[ValidationIssue]:
        if not self._allowed_services:
            return []  # no constraint known → skip
        seen: Set[str] = set()
        issues: List[ValidationIssue] = []
        for svc in _iter_service_tokens(text):
            if svc in self._allowed_services or svc in seen:
                continue
            seen.add(svc)
            issues.append(ValidationIssue(
                section=section,
                kind="off_scope",
                evidence=svc,
                details=(
                    f"Service '{svc}' is not in scan scope "
                    f"({sorted(self._allowed_services)})."
                ),
            ))
        return issues

    def _check_hallucinated_numbers(self, text: str,
                                    section: str) -> List[ValidationIssue]:
        allowed = self.evidence.get("allowed_numbers") or set()
        if not allowed:
            return []
        issues: List[ValidationIssue] = []
        seen: Set[float] = set()
        for n in _extract_numbers(text, min_value=self.ignore_number_below):
            if n in seen:
                continue
            seen.add(n)
            as_int = int(n)
            if as_int in self._allowed_int_set:
                continue
            if any(abs(n - a) <= self.number_tolerance for a in allowed):
                continue
            issues.append(ValidationIssue(
                section=section,
                kind="hallucinated_number",
                evidence=str(n if n != as_int else as_int),
                details=(
                    f"Number {n} is not derivable from scan data "
                    f"(allowed examples: {sorted(allowed)[:6]}...)."
                ),
            ))
        return issues

    def _check_wrong_term(self, text: str, section: str) -> List[ValidationIssue]:
        """Flag resource nouns that belong to a different service.

        Only fires when we know the primary service. Multi-service scope
        uses generic terms and cannot flag per-service terms.
        """
        primary = self._primary_service
        if not primary or primary not in _SERVICE_TERMS:
            return []

        allowed_terms = _SERVICE_TERMS[primary]
        plain_lower = _strip_html(text).lower()

        issues: List[ValidationIssue] = []
        seen: Set[str] = set()
        for svc, terms in _SERVICE_TERMS.items():
            if svc == primary:
                continue
            for term in terms:
                if term in allowed_terms:
                    continue  # term is valid for primary too
                if term in seen:
                    continue
                # Use word boundaries; the term is already lower-cased.
                if re.search(r"\b" + re.escape(term) + r"\b", plain_lower):
                    seen.add(term)
                    issues.append(ValidationIssue(
                        section=section,
                        kind="wrong_term",
                        evidence=term,
                        details=(
                            f"Term '{term}' belongs to service '{svc}' but "
                            f"primary service is '{primary}'."
                        ),
                    ))
        return issues

    def _check_ungrounded(self, text: str, section: str) -> List[ValidationIssue]:
        if not self._allowed_caps_lower:
            return []
        issues: List[ValidationIssue] = []
        seen: Set[str] = set()
        for phrase in _extract_capability_candidates(text):
            key = phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            if key in self._allowed_caps_lower:
                continue
            # Substring match — capability names may be rendered with
            # leading qualifiers ("the Block Public Access control");
            # accept when the core phrase is contained in an allowed
            # capability or vice versa.
            if any(key in allowed or allowed in key
                   for allowed in self._allowed_caps_lower):
                continue
            if not _looks_like_capability(phrase):
                continue
            issues.append(ValidationIssue(
                section=section,
                kind="ungrounded",
                evidence=phrase,
                details="Capability name not present in RAG evidence.",
            ))
        return issues


# ----------------------------------------------------------------------
# Helpers: capability heuristic
# ----------------------------------------------------------------------
_CAPABILITY_KEYWORDS = {
    "access", "control", "protection", "encryption", "logging",
    "monitoring", "backup", "identity", "governance", "management",
    "detection", "response", "network", "data", "security",
    "configuration", "compliance", "audit", "recovery",
}


# Public re-export: the benchmark suite needs the candidate extractor to
# score capability grounding against RAG evidence. Kept as an alias so the
# internal helper can evolve without breaking importers.
extract_capability_candidates = _extract_capability_candidates


def _looks_like_capability(phrase: str) -> bool:
    """A phrase looks like a security capability when at least one token
    is a security-domain noun. This filters out ordinary proper nouns
    (country names, product brands) that share Title-Case shape.
    """
    tokens = {t.lower() for t in re.split(r"\s+", phrase) if t}
    return bool(tokens & _CAPABILITY_KEYWORDS)


# ----------------------------------------------------------------------
# Evidence builder
# ----------------------------------------------------------------------
def build_evidence(
    *,
    findings: Optional[Iterable[Dict[str, Any]]] = None,
    pre: Optional[Dict[str, Any]] = None,
    post: Optional[Dict[str, Any]] = None,
    scope: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, Any]] = None,
    rag_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the ``evidence`` dict that :class:`ReportValidator` expects.

    Centralised here so the report agent does not need to know the
    evidence schema. Each input is optional — the validator degrades
    gracefully when an input is missing (``allowed_capabilities`` empty
    disables the ungrounded check, etc.).
    """
    allowed_numbers: Set[float] = set()

    def _walk_numbers(obj: Any) -> None:
        if isinstance(obj, (int, float)) and not isinstance(obj, bool):
            allowed_numbers.add(float(obj))
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk_numbers(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk_numbers(v)

    _walk_numbers(pre or {})
    _walk_numbers(post or {})
    # Resource counts — number of distinct resources in scope is a
    # legitimate claim.
    if env and isinstance(env, dict):
        for k in ("buckets", "resources"):
            vals = env.get(k)
            if isinstance(vals, list):
                allowed_numbers.add(float(len(vals)))

    # Services that may appear in prose. If scope is empty, fall back to
    # services observed in findings so the validator has something to
    # gate on.
    allowed_services: Set[str] = set()
    if scope:
        for s in scope.get("service_list") or []:
            if s:
                allowed_services.add(str(s).lower())
        if scope.get("primary_service"):
            allowed_services.add(str(scope["primary_service"]).lower())
    if not allowed_services and findings:
        for f in findings:
            svc = (f or {}).get("service")
            if svc:
                allowed_services.add(str(svc).lower())

    # Capabilities grounded by the RAG bundle.
    allowed_capabilities: Set[str] = set()
    rag_context = rag_context or {}
    for t in rag_context.get("control_themes") or []:
        name = (t or {}).get("capability_name")
        if name:
            allowed_capabilities.add(str(name).strip())
    for d in rag_context.get("capability_details") or []:
        name = (d or {}).get("capability_name")
        if name:
            allowed_capabilities.add(str(name).strip())

    account_id = None
    if isinstance(env, dict):
        account_id = env.get("account_id")

    return {
        "allowed_numbers": allowed_numbers,
        "allowed_services": allowed_services,
        "allowed_capabilities": allowed_capabilities,
        "account_id": account_id,
    }
