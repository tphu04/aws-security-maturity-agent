"""
LLM-based query rewriting for semantic retrieval improvement.

Generates multiple technical query variants from a natural-language query
so that BM25 and vector search can find documents whose vocabulary differs
from the user's phrasing.

Example:
    Input:  "protect the most privileged aws credentials from unauthorized use"
    Output: [
        "avoid root account usage restrict root access",
        "root account protection mfa access key removal",
    ]

The original query is always kept — rewrites are *additional* search passes.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

from app.core.config import load_scoring_config

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Prompt template
# ------------------------------------------------------------------ #

_REWRITE_PROMPT = """\
You are an AWS security expert helping a retrieval system find Prowler \
security check documents.

Prowler checks have technical titles like:
- "Ensure no security groups allow ingress from 0.0.0.0/0 to all ports"
- "Avoid the use of the root accounts"
- "Ensure IAM password policy requires minimum length of 14"
- "CloudTrail trail logs management events in all regions"
- "Ensure there are no Public Accessible RDS instances"
- "Amazon EC2 launch templates should have IMDSv2 enabled"

The user query uses natural language. Rewrite it into {n} SHORT queries \
(5-12 words each) that match the technical style above.

Rules:
- Use exact AWS terms: security groups, IAM, root account, CloudTrail, \
RDS, IMDSv2, S3, EC2, VPC, public access, ingress, MFA, encryption.
- Focus on WHAT the check verifies, not WHY.
- Each variant should target a DIFFERENT aspect of the query.
- Output ONLY the numbered list.

User query: {query}

Rewritten queries:"""

# ------------------------------------------------------------------ #
# Generator (singleton, lazy-loaded)
# ------------------------------------------------------------------ #


class QueryRewriter:
    """Singleton wrapper around an Ollama LLM for query rewriting."""

    _instance: Optional["QueryRewriter"] = None

    def __init__(self, model: str, base_url: str) -> None:
        from langchain_ollama import ChatOllama

        logger.info("Initializing QueryRewriter: model=%s url=%s", model, base_url)
        self._llm = ChatOllama(
            model=model,
            base_url=base_url,
            temperature=0.3,
            num_predict=150,
        )
        self._model = model
        self._base_url = base_url

    @classmethod
    def get_instance(cls, model: str, base_url: str) -> "QueryRewriter":
        if (
            cls._instance is None
            or cls._instance._model != model
            or cls._instance._base_url != base_url
        ):
            cls._instance = cls(model, base_url)
        return cls._instance

    def rewrite(self, query: str, n: int = 2) -> List[str]:
        """Generate *n* technical query variants.

        Returns a list of rewritten queries (may be shorter than *n* on
        parse failure).  Returns empty list on LLM failure so the caller
        falls back to the original query only.
        """
        prompt = _REWRITE_PROMPT.format(query=query, n=n)
        t0 = time.perf_counter()

        try:
            response = self._llm.invoke(prompt)
            text = response.content.strip()
            elapsed_ms = (time.perf_counter() - t0) * 1000

            if not text:
                logger.warning("QueryRewriter returned empty for: %s", query[:80])
                return []

            variants = _parse_variants(text, max_variants=n)

            logger.debug(
                "QueryRewriter generated %d variants in %.0fms for: %s",
                len(variants), elapsed_ms, query[:80],
            )
            return variants

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "QueryRewriter failed (%.0fms): %s — using original query only",
                elapsed_ms, exc,
            )
            return []


def _parse_variants(text: str, max_variants: int) -> List[str]:
    """Parse numbered list from LLM output.

    Accepts formats like:
        1. query one
        2. query two
    or:
        1) query one
        2) query two
    or plain lines.
    """
    import re

    lines = text.strip().splitlines()
    variants: List[str] = []
    for line in lines:
        cleaned = re.sub(r"^\s*\d+[.):\-]\s*", "", line).strip()
        cleaned = cleaned.strip('"').strip("'").strip()
        if cleaned and len(cleaned.split()) >= 3:
            variants.append(cleaned)
        if len(variants) >= max_variants:
            break
    return variants


# ------------------------------------------------------------------ #
# Public helper
# ------------------------------------------------------------------ #


def maybe_rewrite_query(
    query: str,
    requires_exact_lookup: bool,
) -> List[str]:
    """Return technical query variants if rewriting is enabled.

    Returns empty list when:
    - Query rewriting is disabled in scoring config
    - The query is an exact-lookup (check_id / capability_id)
    - LLM generation fails (graceful fallback)
    """
    scoring = load_scoring_config()
    rw_cfg = scoring.get("query_rewrite", {})

    if not rw_cfg.get("enabled", False):
        return []

    if requires_exact_lookup:
        return []

    model = rw_cfg.get("model", "phi4-mini:latest")
    base_url = rw_cfg.get("base_url", "http://localhost:11434")
    n_variants = rw_cfg.get("n_variants", 2)

    rewriter = QueryRewriter.get_instance(model, base_url)
    return rewriter.rewrite(query, n=n_variants)
