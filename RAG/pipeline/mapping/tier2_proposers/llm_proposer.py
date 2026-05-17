"""LLM proposer for Tier 2.

Two implementations live here:

  1. `LLMProposer` — production proposer that calls a chat model
     (Claude / OpenAI / any LangChain-compatible BaseChatModel) and asks it
     to pick top-K capabilities for a given check. The prompt is fixed and
     versioned via `proposer_id` so two runs of the same model + same prompt
     produce comparable consensus inputs.

  2. `EmbeddingProposer` — deterministic, offline proposer based on the
     existing reranker/embedding text on each capability. Used as a second
     independent voter when no LLM API key is configured, so the consensus
     pipeline can still be tested end-to-end and so CI runs don't require
     network access.

Both share the same `Proposer` protocol.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .base import Proposal


# ---------------------------------------------------------------------------
# Embedding / TF-IDF style offline proposer (deterministic, no network)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _tf(tokens: List[str]) -> Counter:
    return Counter(tokens)


def _cosine(a: Counter, b: Counter, idf: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) | set(b)
    num = 0.0
    na = 0.0
    nb = 0.0
    for k in keys:
        wa = a.get(k, 0) * idf.get(k, 1.0)
        wb = b.get(k, 0) * idf.get(k, 1.0)
        num += wa * wb
        na += wa * wa
        nb += wb * wb
    if na == 0 or nb == 0:
        return 0.0
    return num / math.sqrt(na * nb)


class EmbeddingProposer:
    """TF-IDF cosine over capability `embedding_text` / `reranker_text`.

    This is independent from the lexical proposer (which uses jaccard +
    weighted overlap + intent rules). Different feature spaces → independent
    voter, suitable for consensus.
    """

    proposer_id = "tfidf_embedding@v1"

    def __init__(
        self,
        capability_domain_index: Optional[Dict[str, Optional[str]]] = None,
    ) -> None:
        self._cap_domain_index = capability_domain_index or {}
        self._idf: Dict[str, float] = {}
        self._cap_tf: Dict[str, Counter] = {}
        self._cap_text: Dict[str, str] = {}
        self._built = False

    def _build_index(self, capabilities: List[Dict[str, Any]]) -> None:
        df: Counter = Counter()
        for cap in capabilities:
            cid = cap.get("capability_id")
            if not cid:
                continue
            text = " ".join(filter(None, [
                cap.get("capability_name") or "",
                cap.get("summary") or "",
                cap.get("embedding_text") or "",
                cap.get("reranker_text") or "",
                " ".join(cap.get("keywords") or []),
            ]))
            self._cap_text[cid] = text
            toks = _tokens(text)
            self._cap_tf[cid] = _tf(toks)
            for term in set(toks):
                df[term] += 1
        n = max(1, len(self._cap_tf))
        self._idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}
        self._built = True

    def propose(
        self,
        check: Dict[str, Any],
        capabilities: List[Dict[str, Any]],
        *,
        top_k: int = 5,
    ) -> List[Proposal]:
        if not self._built:
            self._build_index(capabilities)

        check_id = str(check.get("CheckID") or check.get("check_id") or "")
        check_domain = check.get("security_domain")
        check_text = " ".join(filter(None, [
            check.get("CheckID") or "",
            check.get("CheckTitle") or "",
            check.get("Description") or "",
            check.get("Risk") or "",
            " ".join(check.get("Categories") or []),
        ]))
        q_tf = _tf(_tokens(check_text))

        scored: List[tuple[str, float]] = []
        for cap in capabilities:
            cid = cap.get("capability_id")
            if not cid or cid not in self._cap_tf:
                continue
            if check_domain and self._cap_domain_index:
                cap_dom = self._cap_domain_index.get(cid)
                if cap_dom and cap_dom != check_domain:
                    continue
            sim = _cosine(q_tf, self._cap_tf[cid], self._idf)
            scored.append((cid, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:top_k]

        proposals: List[Proposal] = []
        for rank, (cid, score) in enumerate(top, start=1):
            proposals.append(Proposal(
                check_id=check_id,
                capability_id=cid,
                rank=rank,
                score=score,
                reason=(
                    f"TF-IDF cosine={score:.3f} between check text and "
                    f"capability '{cid}' (domain-narrowed={bool(check_domain)})."
                ),
                components={
                    "cosine": round(score, 4),
                    "narrowed_by_security_domain": bool(check_domain),
                },
            ))
        return proposals


# ---------------------------------------------------------------------------
# Real LLM proposer (LangChain BaseChatModel compatible)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a cloud security compliance expert. Given a Prowler security check
and a shortlist of maturity capabilities, choose the TOP {top_k} capabilities
this check most directly enforces.

Rules:
- Pick ONLY from the provided capability_id list. Never invent ids.
- Rank by direct enforcement strength, not generic relevance.
- Output strict JSON: {{"ranking": [{{"capability_id": "...", "score": 0..1,
  "reason": "<one short sentence>"}}, ...]}}
- No prose outside the JSON.
"""


@dataclass
class LLMInvokeAdapter:
    """Wraps any callable `(system: str, human: str) -> str` so callers can
    plug Claude, OpenAI, Bedrock, etc. without binding to a specific SDK."""
    invoke_fn: Callable[[str, str], str]


class LLMProposer:
    """Chat-model based proposer. Requires a pre-narrowed shortlist (we pass
    at most ~20 capabilities to keep prompt size predictable)."""

    def __init__(
        self,
        adapter: LLMInvokeAdapter,
        *,
        model_id: str,
        capability_domain_index: Optional[Dict[str, Optional[str]]] = None,
        shortlist_size: int = 20,
    ) -> None:
        self._adapter = adapter
        self.proposer_id = f"{model_id}@v1"
        self._cap_domain_index = capability_domain_index or {}
        self._shortlist_size = shortlist_size
        self._embedding_proposer = EmbeddingProposer(
            capability_domain_index=capability_domain_index,
        )

    def propose(
        self,
        check: Dict[str, Any],
        capabilities: List[Dict[str, Any]],
        *,
        top_k: int = 5,
    ) -> List[Proposal]:
        # Step 1: narrow with embedding proposer to a shortlist.
        shortlist_proposals = self._embedding_proposer.propose(
            check, capabilities, top_k=self._shortlist_size,
        )
        shortlist_ids = {p.capability_id for p in shortlist_proposals}
        shortlist = [c for c in capabilities
                     if c.get("capability_id") in shortlist_ids]

        check_id = str(check.get("CheckID") or check.get("check_id") or "")
        if not shortlist:
            return []

        # Step 2: ask LLM to rank.
        system = _SYSTEM_PROMPT.format(top_k=top_k)
        human = json.dumps({
            "check": {
                "check_id": check_id,
                "title": check.get("CheckTitle"),
                "service": check.get("ServiceName"),
                "description": check.get("Description"),
                "risk": check.get("Risk"),
                "categories": check.get("Categories"),
                "security_domain": check.get("security_domain"),
            },
            "capabilities": [
                {
                    "capability_id": c.get("capability_id"),
                    "name": c.get("capability_name"),
                    "summary": c.get("summary"),
                }
                for c in shortlist
            ],
        }, ensure_ascii=False)

        raw = self._adapter.invoke_fn(system, human)
        try:
            payload = json.loads(raw)
            ranking = payload.get("ranking", [])
        except Exception:
            return []

        valid_ids = {c.get("capability_id") for c in shortlist}
        proposals: List[Proposal] = []
        seen: set = set()
        for rank, item in enumerate(ranking, start=1):
            cid = item.get("capability_id")
            if not cid or cid not in valid_ids or cid in seen:
                continue
            seen.add(cid)
            score = float(item.get("score") or 0.0)
            score = max(0.0, min(1.0, score))
            proposals.append(Proposal(
                check_id=check_id,
                capability_id=cid,
                rank=rank,
                score=score,
                reason=str(item.get("reason") or "").strip(),
                components={
                    "llm_score": score,
                    "shortlist_size": len(shortlist),
                },
            ))
            if len(proposals) >= top_k:
                break
        return proposals
