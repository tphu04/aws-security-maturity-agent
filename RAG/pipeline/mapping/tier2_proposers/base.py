"""Proposer interface for Tier 2.

A proposer is one independent "voter" that emits ranked capability candidates
for a given Prowler check. Tier 3 combines proposals from multiple proposers
into a consensus decision.

Key contract:
- Proposers MUST be deterministic given the same inputs and version, so
  consensus is reproducible.
- Proposers MUST NOT set review_status / status — they only propose.
- Proposers return a fixed-shape `Proposal` carrying score, rank, and a
  per-proposer reason string (used for audit).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol


@dataclass
class Proposal:
    check_id: str
    capability_id: str
    rank: int                # 1-based rank within this proposer's output
    score: float             # proposer-internal score; comparable only within
                             # the same proposer/version
    reason: str
    # Optional structured signals used for downstream audit. Keep loose so
    # different proposer families can attach what makes sense.
    components: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "capability_id": self.capability_id,
            "rank": self.rank,
            "score": round(float(self.score), 4),
            "reason": self.reason,
            "components": self.components,
        }


@dataclass
class ProposerOutput:
    proposer_id: str         # e.g. "lexical@v1", "claude-opus-4.7@v1"
    proposals: List[Proposal]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposer_id": self.proposer_id,
            "proposals": [p.to_dict() for p in self.proposals],
        }


class Proposer(Protocol):
    proposer_id: str

    def propose(
        self,
        check: Dict[str, Any],
        capabilities: List[Dict[str, Any]],
        *,
        top_k: int = 5,
    ) -> List[Proposal]: ...
