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
        )

    def _sorted_findings(self) -> List[Dict[str, Any]]:
        findings = list(self.ctx.get("key_findings") or [])
        findings.sort(key=lambda f: _severity_rank(f.get("severity")))
        return findings

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------
    def for_executive(self, max_findings: int = 3,
                      max_themes: int = 3) -> str:
        """Compact view for ``write_exec_summary``: top critical/high +
        a few control themes. Intentionally short — the C-level prompt
        should not drown in detail.
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

        return "\n\n".join(parts)

    def for_fail_analysis(self, max_findings: int = 8) -> str:
        """Richer view for ``write_fail_findings_overview``: severity +
        risk_summary for every finding, plus capability risk explanation
        so the prompt can ground root-cause narration.
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

        return "\n\n".join(parts)

    def for_pass_analysis(self, max_themes: int = 5) -> str:
        """View for ``write_pass_findings_overview``: only control themes
        and their summaries — no finding list (PASS findings are already
        in the prompt's ``ctx``).
        """
        if not self.has_data:
            return ""

        themes = (self.ctx.get("control_themes") or [])[:max_themes]
        if not themes:
            return ""
        lines = []
        for t in themes:
            name = t.get("capability_name") or t.get("capability_id")
            summary = _clean(
                t.get("summary_short") or t.get("summary"), 180
            )
            if name:
                lines.append(
                    f"- {name}: {summary}" if summary else f"- {name}"
                )
        if not lines:
            return ""
        return "CHỦ ĐỀ KIỂM SOÁT LIÊN QUAN (nền tảng best practice):\n" + \
               "\n".join(lines)

    def for_recommendations(self, max_practices: int = 6,
                            max_caps: int = 4) -> str:
        """View for ``write_post_remediation_recommendations``: canonical
        practices + capability-level recommendations. The writer prompt
        already has the numeric outcome block, so this view focuses on
        the *what to do* knowledge.
        """
        if not self.has_data:
            return ""

        parts: List[str] = []

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
