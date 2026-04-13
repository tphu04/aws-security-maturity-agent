"""
Auto-detect non-English queries and translate to English.

The RAG corpus is entirely in English (AWS Prowler checks, maturity
capabilities).  When a user submits a query in another language the
pipeline cannot match it against BM25 tokens or BGE embeddings.

This module:
1. Detects whether a query contains non-ASCII / non-English tokens.
2. If so, calls a local Ollama LLM to translate to concise English.
3. Returns the translated text (or the original if already English).

The translation happens **before** routing so the router can still
detect service names, check IDs, and query intent correctly.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from app.core.config import load_scoring_config

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Detection heuristic
# ------------------------------------------------------------------ #

# Vietnamese diacritics, CJK, Cyrillic, Arabic, Thai, etc.
_VIETNAMESE_DIACRITICS = re.compile(
    r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệ"
    r"ìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữự"
    r"ỳýỷỹỵđ"
    r"ÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆ"
    r"ÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰ"
    r"ỲÝỶỸỴĐ]"
)
_NON_LATIN_RE = re.compile(r"[^\x00-\x7F]")


def _needs_translation(query: str) -> bool:
    """Return True if the query likely contains non-English text.

    Detection strategy (ordered by specificity):
    1. Vietnamese diacritics (ắ, ề, ợ, đ, …) → immediate True
    2. High ratio of non-ASCII chars (>5%) → True (CJK, Cyrillic, etc.)
    3. Otherwise → False (English, even with occasional accents)
    """
    if not query:
        return False
    # Fast path: Vietnamese diacritics are unambiguous
    if _VIETNAMESE_DIACRITICS.search(query):
        return True
    # General non-ASCII ratio for other languages
    non_ascii = len(_NON_LATIN_RE.findall(query))
    ratio = non_ascii / len(query)
    return ratio > 0.05


# ------------------------------------------------------------------ #
# Prompt
# ------------------------------------------------------------------ #

_TRANSLATE_PROMPT = """\
Translate the following cloud security query into English.
Keep AWS service names (S3, IAM, EC2, RDS, etc.) unchanged.
Output ONLY the English translation, nothing else.

Query: {query}
English:"""

# ------------------------------------------------------------------ #
# Translator (singleton)
# ------------------------------------------------------------------ #


class QueryTranslator:
    """Singleton wrapper around Ollama for query translation."""

    _instance: Optional["QueryTranslator"] = None

    def __init__(self, model: str, base_url: str) -> None:
        from langchain_ollama import ChatOllama

        logger.info("Initializing QueryTranslator: model=%s url=%s", model, base_url)
        self._llm = ChatOllama(
            model=model,
            base_url=base_url,
            temperature=0,
            num_predict=100,
        )
        self._model = model
        self._base_url = base_url

    @classmethod
    def get_instance(cls, model: str, base_url: str) -> "QueryTranslator":
        if (
            cls._instance is None
            or cls._instance._model != model
            or cls._instance._base_url != base_url
        ):
            cls._instance = cls(model, base_url)
        return cls._instance

    def translate(self, query: str) -> str:
        """Translate query to English. Returns original on failure."""
        prompt = _TRANSLATE_PROMPT.format(query=query)
        t0 = time.perf_counter()

        try:
            response = self._llm.invoke(prompt)
            text = response.content.strip()
            elapsed_ms = (time.perf_counter() - t0) * 1000

            if not text:
                logger.warning("QueryTranslator returned empty for: %s", query[:80])
                return query

            # Strip quotes the LLM sometimes wraps around the output
            text = text.strip('"').strip("'").strip()

            logger.info(
                "QueryTranslator: '%s' -> '%s' (%.0fms)",
                query[:60], text[:60], elapsed_ms,
            )
            return text

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "QueryTranslator failed (%.0fms): %s — using original",
                elapsed_ms, exc,
            )
            return query


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #


def maybe_translate_query(query: str) -> tuple[str, bool]:
    """Translate query to English if non-English text is detected.

    Returns:
        Tuple of (effective_query, was_translated).
        If translation is disabled or the query is already English,
        returns (original_query, False).
    """
    if not _needs_translation(query):
        return query, False

    scoring = load_scoring_config()
    tr_cfg = scoring.get("query_translation", {})

    if not tr_cfg.get("enabled", True):
        return query, False

    model = tr_cfg.get("model", "phi4-mini:latest")
    base_url = tr_cfg.get("base_url", "http://localhost:11434")

    translator = QueryTranslator.get_instance(model, base_url)
    translated = translator.translate(query)

    if translated and translated != query:
        return translated, True

    return query, False
