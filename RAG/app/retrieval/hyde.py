"""
HyDE (Hypothetical Document Embeddings) generator.

Generates a hypothetical document for a natural-language query so that
vector search matches in *document space* rather than *query space*.

Reference: Gao et al., "Precise Zero-Shot Dense Retrieval without
Relevance Labels" (2022).  https://arxiv.org/abs/2212.10496

Usage in the retrieval pipeline:
    - BM25 still uses the **original query** (keyword matching).
    - Vector search uses the **hypothetical document** text.
    - Exact-lookup queries bypass HyDE entirely.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from app.core.config import load_scoring_config

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Prompt template
# ------------------------------------------------------------------ #

_HYDE_PROMPT = """\
You are an AWS security expert. Given a user query about cloud security,
write a short technical description (3-5 sentences) of the security check
or capability that would best address this query.

Write as if you are describing an existing AWS security check entry.
Include specific AWS terminology, service names, and security concepts.
Do NOT include any preamble or explanation — output ONLY the description.

Query: {query}
Description:"""

# ------------------------------------------------------------------ #
# Generator (singleton, lazy-loaded)
# ------------------------------------------------------------------ #


class HyDEGenerator:
    """Singleton wrapper around an Ollama LLM for HyDE generation."""

    _instance: Optional["HyDEGenerator"] = None

    def __init__(self, model: str, base_url: str) -> None:
        from langchain_ollama import ChatOllama

        logger.info("Initializing HyDE generator: model=%s url=%s", model, base_url)
        self._llm = ChatOllama(
            model=model,
            base_url=base_url,
            temperature=0,
            num_predict=200,
        )
        self._model = model
        self._base_url = base_url

    @classmethod
    def get_instance(cls, model: str, base_url: str) -> "HyDEGenerator":
        if (
            cls._instance is None
            or cls._instance._model != model
            or cls._instance._base_url != base_url
        ):
            cls._instance = cls(model, base_url)
        return cls._instance

    def generate(self, query: str) -> Optional[str]:
        """Generate a hypothetical document for *query*.

        Returns the generated text, or ``None`` on any failure (so the
        caller can fall back to the original query).
        """
        prompt = _HYDE_PROMPT.format(query=query)
        t0 = time.perf_counter()

        try:
            response = self._llm.invoke(prompt)
            text = response.content.strip()
            elapsed_ms = (time.perf_counter() - t0) * 1000

            if not text:
                logger.warning("HyDE returned empty text for query: %s", query)
                return None

            logger.debug(
                "HyDE generated %d chars in %.0fms for: %s",
                len(text), elapsed_ms, query[:80],
            )
            return text

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "HyDE generation failed (%.0fms): %s — falling back to original query",
                elapsed_ms, exc,
            )
            return None


# ------------------------------------------------------------------ #
# Public helper
# ------------------------------------------------------------------ #


def maybe_generate_hyde(
    query: str,
    requires_exact_lookup: bool,
) -> Optional[str]:
    """Return a hypothetical document if HyDE is enabled and applicable.

    Returns ``None`` when:
    - HyDE is disabled in scoring config
    - The query is an exact-lookup (check_id / capability_id)
    - LLM generation fails (graceful fallback)
    """
    scoring = load_scoring_config()
    hyde_cfg = scoring.get("hyde", {})

    if not hyde_cfg.get("enabled", False):
        return None

    if requires_exact_lookup:
        return None

    model = hyde_cfg.get("model", "gemma3:4b")
    base_url = hyde_cfg.get("base_url", "http://localhost:11434")

    generator = HyDEGenerator.get_instance(model, base_url)
    return generator.generate(query)
