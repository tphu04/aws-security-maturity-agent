"""RAG view formatter — Phase 4.1

Takes the raw ``rag_context`` produced by the orchestrator (keys:
``key_findings``, ``control_themes``, ``recommended_practices``,
``capability_details``, ``primary_topics``, ``confidence``) and renders a
view tailored for a single LLM prompt. Each writer method in
``LLMWriter`` now consumes a pre-formatted string, so the view logic lives
in one place and stays out of the prompt templates themselves.

All views follow the same contract:

* Input: the original ``rag_context`` dict (never mutated) + scope info.
* Output: a Vietnamese text block ready to interpolate into a prompt.
* Empty ``rag_context`` → empty string (so callers don't emit a stray
  heading when RAG is unavailable).

Severity labels are rendered with parentheses (``(HIGH)``) instead of
square brackets. The downstream cleanup regex in ``LLMWriter._clean``
strips ``[...]`` patterns as stray placeholders, which silently ate
``[SEVERITY]`` tokens in previous revisions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "informational": 4,
    "info": 4,
}


def _severity_rank(sev: str) -> int:
    return _SEVERITY_RANK.get((sev or "").strip().lower(), 5)


def _clean(text: Any, max_len: int = 240) -> str:
    if text is None:
        return ""
    s = str(text).strip()
    if len(s) <= max_len:
        return s
    # Soft truncate at a sentence boundary to avoid mid-word cuts in the
    # LLM prompt.
    cut = s.rfind(". ", 0, max_len)
    if cut < max_len - 60:
        cut = s.rfind(" ", 0, max_len)
    return (s[:cut].rstrip() if cut > 0 else s[:max_len].rstrip()) + "…"


def _severity_label(sev: Any) -> str:
    return str(sev or "N/A").strip().upper() or "N/A"


class RAGViewFormatter:
    """Render ``rag_context`` for a specific section of the report.

    The formatter is stateless beyond the context passed in the
    constructor — each ``for_*`` call produces a fresh string. Views
    never mutate the underlying dicts, so the same formatter can be
    safely passed to multiple LLM calls.
    """

    def __init__(
        self,
        rag_context: Optional[Dict[str, Any]],
        scope_info: Optional[Dict[str, Any]] = None,
    ):
        self.ctx = rag_context or {}
        self.scope = scope_info or {}

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    @property
    def has_data(self) -> bool:
        return bool(
            self.ctx.get("key_findings")
            or self.ctx.get("control_themes")
            or self.ctx.get("recommended_practices")
            or self.ctx.get("capability_details")
            or self.ctx.get("capability_themes")
            or self.ctx.get("remediations")
        )

    def _sorted_findings(self) -> List[Dict[str, Any]]:
        findings = list(self.ctx.get("key_findings") or [])
        findings.sort(key=lambda f: _severity_rank(f.get("severity")))
        return findings

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------
    def for_executive(self, max_findings: int = 3,
                      max_themes: int = 3,
                      max_domains: int = 2) -> str:
        """Compact view for ``write_exec_summary``: top critical/high +
        Q1 control themes + Q2 domain narratives (one sentence each).
        Intentionally short — the C-level prompt should not drown in detail.

        Multi-query mode: adds Q2 domain narratives for grounded context.
        Legacy mode: Q1-only (backward compat when capability_themes=[]).
        """
        if not self.has_data:
            return ""

        parts: List[str] = []

        top = [f for f in self._sorted_findings()
               if _severity_rank(f.get("severity")) <= 1]  # critical/high
        top = top[:max_findings]
        if top:
            lines = [
                f"- ({_severity_label(f.get('severity'))}) "
                f"{_clean(f.get('title'), 140)}"
                for f in top if f.get("title")
            ]
            if lines:
                parts.append(
                    "RỦI RO NGHIÊM TRỌNG CẦN NÊU (từ cơ sở dữ liệu):\n"
                    + "\n".join(lines)
                )

        themes = (self.ctx.get("control_themes") or [])[:max_themes]
        if themes:
            lines = []
            for t in themes:
                name = t.get("capability_name") or t.get("capability_id")
                summary = _clean(
                    t.get("summary_short") or t.get("summary"), 160
                )
                if name:
                    lines.append(
                        f"- {name}: {summary}" if summary else f"- {name}"
                    )
            if lines:
                parts.append(
                    "CHỦ ĐỀ KIỂM SOÁT (chỉ nêu ngắn):\n" + "\n".join(lines)
                )

        # Q2 — one-sentence domain narrative per in-scope domain.
        # Gives C-level readers grounded context without technical detail.
        cap_themes = (self.ctx.get("capability_themes") or [])[:max_domains]
        if cap_themes:
            lines = []
            for t in cap_themes:
                domain = (t.get("domain") or "").upper()
                narrative = _clean(t.get("narrative"), 160)
                if domain and narrative:
                    lines.append(f"- [{domain}] {narrative}")
            if lines:
                parts.append(
                    "BỐI CẢNH BẢO MẬT THEO DOMAIN (Q2):\n" + "\n".join(lines)
                )

        return "\n\n".join(parts)

    def for_system_overview(self, max_domains: int = 3) -> str:
        """View for ``write_system_overview``: domain-level security scope
        and assessment baselines from Q2 capability_themes.

        Grounds the LLM's description of each service's security role and
        the standards used for assessment (CIS/Well-Architected).
        Legacy mode: returns "" when capability_themes=[].
        """
        cap_themes = (self.ctx.get("capability_themes") or [])[:max_domains]
        if not cap_themes:
            return ""

        parts: List[str] = []

        domain_lines: List[str] = []
        for t in cap_themes:
            domain = (t.get("domain") or "").upper()
            narrative = _clean(t.get("narrative"), 200)
            if domain and narrative:
                domain_lines.append(f"- [{domain}] {narrative}")
        if domain_lines:
            parts.append(
                "PHẠM VI BẢO MẬT THEO DOMAIN (từ cơ sở dữ liệu):\n"
                + "\n".join(domain_lines)
            )

        # Deduplicated baselines across all domains — ground assessment criteria.
        baseline_lines: List[str] = []
        seen_baselines: set = set()
        for t in cap_themes:
            for b in (t.get("baselines") or [])[:2]:
                b_clean = _clean(b, 120)
                if b_clean and b_clean not in seen_baselines:
                    baseline_lines.append(f"- {b_clean}")
                    seen_baselines.add(b_clean)
        if baseline_lines:
            parts.append(
                "TIÊU CHUẨN ĐÁNH GIÁ (tham chiếu):\n"
                + "\n".join(baseline_lines[:4])
            )

        return "\n\n".join(parts)

    def for_fail_analysis(self, max_findings: int = 8) -> str:
        """Richer view for ``write_fail_findings_overview``: severity +
        risk_summary for every finding, capability risk explanation,
        Q3 first remediation step per check, and Q2 domain pitfalls.

        Multi-query mode: adds Q3 authoritative fix steps + Q2 pitfalls.
        Legacy mode: Q1-only (backward compat when remediations/capability_themes=[]).
        """
        if not self.has_data:
            return ""

        parts: List[str] = []

        findings = self._sorted_findings()[:max_findings]
        if findings:
            lines = []
            for f in findings:
                sev = _severity_label(f.get("severity"))
                title = _clean(f.get("title"), 140)
                risk = _clean(f.get("risk_summary") or f.get("description"), 200)
                if not title:
                    continue
                if risk:
                    lines.append(f"- ({sev}) {title} — {risk}")
                else:
                    lines.append(f"- ({sev}) {title}")
            if lines:
                parts.append(
                    "RỦI RO CHI TIẾT TỪ KIẾN THỨC BẢO MẬT:\n"
                    + "\n".join(lines)
                )

        details = self.ctx.get("capability_details") or []
        if details:
            lines = []
            for d in details[:4]:
                name = d.get("capability_name") or d.get("capability_id")
                risk = _clean(d.get("risk_explanation"), 220)
                if name and risk:
                    lines.append(f"- {name}: {risk}")
            if lines:
                parts.append(
                    "NĂNG LỰC KIỂM SOÁT CÓ RỦI RO (capability risk):\n"
                    + "\n".join(lines)
                )

        # Q3 — first authoritative remediation step per failing check.
        # Gives the LLM a concrete fix anchor so it does not fabricate steps.
        remediations = self.ctx.get("remediations") or []
        if remediations:
            rem_lookup: Dict[str, Any] = {}
            for guide in remediations:
                cid = guide.get("check_id", "")
                steps = guide.get("steps") or []
                if cid and steps:
                    rem_lookup[cid] = steps[0]

            lines = []
            for f in self._sorted_findings()[:4]:
                cid = f.get("check_id", "")
                step = rem_lookup.get(cid)
                if not step or not step.get("snippet"):
                    continue
                snippet = _clean(step["snippet"], 180)
                stype = (step.get("type") or "").upper()
                tag = f"[{stype}]" if stype else ""
                lines.append(f"- {cid} {tag}: {snippet}")

            if lines:
                parts.append(
                    "BƯỚC KHẮC PHỤC TRỌNG TÂM (Q3 — authoritative):\n"
                    + "\n".join(lines[:3])
                )

        # Q2 — common pitfalls for domains that have FAIL findings.
        # Domain inferred from check_id prefix (s3_xxx → "s3").
        cap_themes = self.ctx.get("capability_themes") or []
        if cap_themes:
            failing_domains = {
                (f.get("check_id") or "").split("_")[0].lower()
                for f in self._sorted_findings()[:6]
                if f.get("check_id")
            }
            pitfall_lines: List[str] = []
            for t in cap_themes:
                domain = (t.get("domain") or "").lower()
                if domain not in failing_domains:
                    continue
                for p in (t.get("common_pitfalls") or [])[:2]:
                    p_clean = _clean(p, 120)
                    if p_clean:
                        pitfall_lines.append(f"- [{domain.upper()}] {p_clean}")

            if pitfall_lines:
                parts.append(
                    "SAI LẦM PHỔ BIẾN THEO DOMAIN (Q2):\n"
                    + "\n".join(pitfall_lines[:4])
                )

        return "\n\n".join(parts)

    def for_pass_analysis(self, max_themes: int = 5) -> str:
        """View for ``write_pass_findings_overview``.

        Multi-query mode: Q2 capability_themes (primary) + Q1 control_themes (fallback).
        Legacy mode: Q1 control_themes only (backward compat when capability_themes=[]).
        """
        if not self.has_data:
            return ""

        parts: List[str] = []

        # Q2 primary — domain narratives with pitfalls (multi-query mode)
        cap_themes = (self.ctx.get("capability_themes") or [])[:max_themes]
        if cap_themes:
            lines = []
            for t in cap_themes:
                domain = t.get("domain", "")
                narrative = _clean(t.get("narrative"), 240)
                pitfalls = (t.get("common_pitfalls") or [])[:2]
                if narrative:
                    entry = f"- [{domain.upper()}] {narrative}"
                    if pitfalls:
                        pitfall_text = "; ".join(_clean(p, 100) for p in pitfalls if p)
                        entry += f" (lưu ý: {pitfall_text})"
                    lines.append(entry)
            if lines:
                parts.append(
                    "NGỮ CẢNH NĂNG LỰC BẢO MẬT THEO DOMAIN (Q2):\n"
                    + "\n".join(lines)
                )

        # Q1 fallback — legacy control_themes (always append if present)
        themes = (self.ctx.get("control_themes") or [])[:max_themes]
        lines = []
        for t in themes:
            name = t.get("capability_name") or t.get("capability_id")
            summary = _clean(t.get("summary_short") or t.get("summary"), 180)
            if name:
                lines.append(f"- {name}: {summary}" if summary else f"- {name}")
        if lines:
            parts.append(
                "CHỦ ĐỀ KIỂM SOÁT LIÊN QUAN (nền tảng best practice):\n"
                + "\n".join(lines)
            )

        return "\n\n".join(parts)

    def for_recommendations(self, max_practices: int = 6,
                            max_caps: int = 4) -> str:
        """View for ``write_post_remediation_recommendations``.

        Multi-query mode: Q3 remediation steps (primary) + Q2 baselines +
        Q1 recommended_practices (secondary).
        Legacy mode: Q1 only (backward compat when remediations=[]).
        """
        if not self.has_data:
            return ""

        parts: List[str] = []

        # Q3 primary — structured remediation steps (multi-query mode)
        remediations = (self.ctx.get("remediations") or [])[:max_caps]
        if remediations:
            lines = []
            for guide in remediations:
                check_id = guide.get("check_id", "")
                steps = guide.get("steps") or []
                effort = guide.get("effort", "")
                for step in steps[:2]:  # max 2 steps per check to keep prompt tight
                    snippet = _clean(step.get("snippet"), 200)
                    step_type = step.get("type", "")
                    if snippet:
                        tag = f"[{step_type.upper()}]" if step_type else ""
                        lines.append(f"- {check_id} {tag}: {snippet}")
                if effort:
                    lines.append(f"  (effort: {effort})")
            if lines:
                parts.append(
                    "HƯỚNG DẪN KHẮC PHỤC CỤ THỂ (Q3 — authoritative steps):\n"
                    + "\n".join(lines)
                )

        # Q2 baselines — CIS/Well-Architected references
        cap_themes = (self.ctx.get("capability_themes") or [])[:3]
        baseline_lines = []
        for t in cap_themes:
            for b in (t.get("baselines") or [])[:2]:
                b_clean = _clean(b, 180)
                if b_clean:
                    baseline_lines.append(f"- {b_clean}")
        if baseline_lines:
            parts.append(
                "TIÊU CHUẨN THAM CHIẾU (Q2 baselines):\n"
                + "\n".join(baseline_lines[:5])
            )

        # Q1 fallback — recommended_practices + capability recommendations
        practices = (self.ctx.get("recommended_practices") or [])[:max_practices]
        clean_practices = [_clean(p, 220) for p in practices if p]
        if clean_practices:
            parts.append(
                "THỰC HÀNH KHUYẾN NGHỊ (authoritative):\n"
                + "\n".join(f"- {p}" for p in clean_practices)
            )

        details = self.ctx.get("capability_details") or []
        cap_lines = []
        for d in details[:max_caps]:
            name = d.get("capability_name") or d.get("capability_id")
            rec = _clean(d.get("recommendation"), 240)
            if name and rec:
                cap_lines.append(f"- {name}: {rec}")
        if cap_lines:
            parts.append(
                "KHUYẾN NGHỊ THEO NĂNG LỰC (capability recommendations):\n"
                + "\n".join(cap_lines)
            )

        return "\n\n".join(parts)

    def for_per_finding(self, check_id: str) -> Dict[str, str]:
        """Structured view for ``write_pass_remediation_detail`` /
        ``write_fail_remediation_detail`` / ``write_manual_guide``.

        Returns a dict with ``risk`` and ``recommendation`` strings —
        callers pick the field they need. Empty strings when the check
        is not in the bundle, so existing prompt fallbacks stay valid.
        """
        if not check_id:
            return {"risk": "", "recommendation": "", "title": ""}

        for f in self.ctx.get("key_findings") or []:
            if f.get("check_id") == check_id:
                return {
                    "risk": _clean(
                        f.get("risk_summary") or f.get("description"), 400
                    ),
                    "recommendation": _clean(f.get("remediation"), 400),
                    "title": _clean(f.get("title"), 180),
                }
        return {"risk": "", "recommendation": "", "title": ""}
