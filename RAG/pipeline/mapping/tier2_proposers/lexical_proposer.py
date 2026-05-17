"""Lexical proposer for Tier 2.

Wraps the existing scoring engine in `RAG/scripts/gen_maturity_mapping.py`
(jaccard + weighted overlap + intent alignment + control-family adjustments)
and exposes it as a Tier 2 voter.

Key changes vs. the legacy script:
  - Capability candidates are pre-filtered by security_domain when both check
    and candidate expose one — reduces noise and avoids the historical
    s3-encryption-vs-bedrock-genai class of bug at the scoring layer.
  - We do NOT call `review_status_from_score` — auto-approve is removed.
    Outputs are always `Proposal` rows for consensus to decide on.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# Load gen_maturity_mapping.py without forcing a package rename — it lives
# at RAG/scripts/gen_maturity_mapping.py and pokes sys.path at import time.
_ROOT = Path(__file__).resolve().parents[3]
_GEN_PATH = _ROOT / "scripts" / "gen_maturity_mapping.py"
_RAG_ROOT = _ROOT.as_posix()
if _RAG_ROOT not in sys.path:
    sys.path.insert(0, _RAG_ROOT)

_spec = importlib.util.spec_from_file_location(
    "_legacy_gen_maturity_mapping", _GEN_PATH,
)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load legacy scorer at {_GEN_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
# Register before exec so @dataclass can resolve cls.__module__
sys.modules["_legacy_gen_maturity_mapping"] = _legacy
_spec.loader.exec_module(_legacy)  # type: ignore[union-attr]


from .base import Proposal


class LexicalProposer:
    proposer_id = "lexical@v1"

    def __init__(
        self,
        capability_domain_index: Optional[Dict[str, Optional[str]]] = None,
    ) -> None:
        self._cap_domain_index = capability_domain_index or {}

    def propose(
        self,
        check: Dict[str, Any],
        capabilities: List[Dict[str, Any]],
        *,
        top_k: int = 5,
    ) -> List[Proposal]:
        check_id = str(check.get("CheckID") or check.get("check_id") or "")
        check_domain = check.get("security_domain")  # injected by Tier1 join

        if check_domain and self._cap_domain_index:
            narrowed = [
                c for c in capabilities
                if self._cap_domain_index.get(c.get("capability_id"))
                in (check_domain, None)
            ]
            # If domain filter wipes out everything, fall back to full set
            # rather than emit nothing — better to propose weak matches and
            # let consensus reject them.
            candidates = narrowed or capabilities
            narrowed_by_domain = bool(narrowed)
        else:
            candidates = capabilities
            narrowed_by_domain = False

        scored = [
            _legacy.score_candidate(check, m) for m in candidates
        ]
        scored.sort(key=lambda x: x.score, reverse=True)
        top = scored[:top_k]

        proposals: List[Proposal] = []
        for rank, sc in enumerate(top, start=1):
            cap_id = _legacy.infer_maturity_capability_id(sc.maturity)
            if not cap_id:
                continue
            reason = _legacy.build_mapping_reason(check, sc)
            proposals.append(Proposal(
                check_id=check_id,
                capability_id=cap_id,
                rank=rank,
                score=sc.score,
                reason=reason,
                components={
                    "jaccard_and_overlap_score": round(sc.score, 4),
                    "overlap_terms": list(sc.overlap_terms),
                    "phrase_hits": list(sc.phrase_hits),
                    "service_bonus": sc.service_bonus,
                    "domain_bonus": sc.domain_bonus,
                    "title_bonus": sc.title_bonus,
                    "intent_bonus": sc.intent_bonus,
                    "intent_penalty": sc.intent_penalty,
                    "product_penalty": sc.product_penalty,
                    "control_bonus": sc.control_bonus,
                    "control_penalty": sc.control_penalty,
                    "narrowed_by_security_domain": narrowed_by_domain,
                    "narrow_pool_size": len(candidates),
                },
            ))
        return proposals
