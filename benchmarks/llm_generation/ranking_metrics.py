"""Ranking metrics for Report Agent Evaluation v3.

Single public function: :func:`ndcg_at_k`. The helper
:func:`extract_narrative_ranking` pulls the LLM-ordered finding list out
of a generated HTML report so the benchmark can score severity
prioritisation.

Why here (and not in ``report_metrics_v3.py``): ranking math is generic
and unit-testable without HTML or validator plumbing.
"""
from __future__ import annotations

import math
import re
from html import unescape
from typing import Dict, List, Optional, Sequence

_SEV_WEIGHT: Dict[str, float] = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
    "info": 0.0,
}

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return unescape(_TAG_RE.sub(" ", text or ""))


# The narrative sections that matter for prioritisation signal. These
# regexes anchor to exact template headings — kept in sync with
# ``report_metrics.py``.
_NARRATIVE_PATTERNS: List[str] = [
    r"<h1>1\. Tóm tắt điều hành</h1>\s*(.*?)\s*<h1>",
    r"<h3>Tổng quan các mục KHÔNG ĐẠT</h3>\s*(.*?)\s*<h1>",
    r"<h1>7\. Khuyến nghị[^<]*</h1>(.*?)(?:<hr\b|<h1>|</body>|$)",
]


def extract_narrative_text(html: str) -> str:
    """Concatenate the LLM narrative sections (stripped of HTML)."""
    chunks: List[str] = []
    for pat in _NARRATIVE_PATTERNS:
        m = re.search(pat, html, re.DOTALL)
        if m:
            chunks.append(_strip_html(m.group(1)))
    return " ".join(chunks)


def extract_narrative_ranking(
    html: str,
    findings: Sequence[Dict],
) -> List[str]:
    """Order ``findings`` by first mention position in the LLM narrative.

    ``findings`` items must carry ``finding_uid``. Each is located by its
    ``description`` or ``check_id``; items never mentioned are appended at
    the end in their original order so the list length is preserved.
    """
    narrative = extract_narrative_text(html).lower()
    if not narrative:
        return [f.get("finding_uid") for f in findings if f.get("finding_uid")]

    scored: List[tuple] = []
    unseen: List[str] = []
    for idx, f in enumerate(findings):
        uid = f.get("finding_uid")
        if not uid:
            continue
        probes = [
            (f.get("description") or "").strip().lower(),
            (f.get("check_id") or "").strip().lower(),
            (f.get("resource") or "").strip().lower(),
        ]
        pos: Optional[int] = None
        for probe in probes:
            if len(probe) < 4:
                continue
            p = narrative.find(probe)
            if p >= 0 and (pos is None or p < pos):
                pos = p
        if pos is None:
            unseen.append(uid)
        else:
            scored.append((pos, idx, uid))

    scored.sort()  # by pos asc, then by original index as tiebreak
    return [uid for _, _, uid in scored] + unseen


def ndcg_at_k(
    predicted: Sequence[str],
    relevance: Dict[str, float],
    k: int = 5,
) -> float:
    """Standard NDCG@k.

    ``relevance`` maps item id → gain (e.g. severity weight). Items not in
    ``relevance`` contribute zero gain. Returns 0.0 when the ideal DCG is
    zero (no relevant items).
    """
    if k <= 0:
        return 0.0

    def _dcg(items: Sequence[str]) -> float:
        total = 0.0
        for i, item in enumerate(items[:k]):
            rel = float(relevance.get(item, 0.0))
            if rel <= 0:
                continue
            total += rel / math.log2(i + 2)
        return total

    ideal_items = sorted(relevance.keys(), key=lambda x: -relevance[x])
    ideal = _dcg(ideal_items)
    if ideal <= 0:
        return 0.0
    return round(_dcg(predicted) / ideal, 4)


def severity_relevance(findings: Sequence[Dict]) -> Dict[str, float]:
    """Map ``finding_uid`` → severity weight (critical=4 … low=1)."""
    out: Dict[str, float] = {}
    for f in findings:
        uid = f.get("finding_uid")
        if not uid:
            continue
        sev = (f.get("severity") or "").strip().lower()
        out[uid] = _SEV_WEIGHT.get(sev, 0.0)
    return out
