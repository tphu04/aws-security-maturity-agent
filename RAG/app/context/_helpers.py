"""
Shared utility helpers for context building modules.

Contains data extraction, normalization, and compression functions
used across ContextBuilder, CoverageSelector, and other modules.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def ensure_list_of_strings(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = maybe_str(item)
        if text:
            result.append(text)
    return result


def ensure_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: List[Dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            result.append(item)
    return result


def ensure_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def maybe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def maybe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        text = maybe_str(value)
        if text:
            return text
    return None


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def normalize_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = maybe_str(item)
        if text:
            result.append(text)
    return result


def normalize_warnings(warnings: Any) -> List[str]:
    result: List[str] = []
    if isinstance(warnings, list):
        for item in warnings:
            text = maybe_str(item)
            if text:
                result.append(text)
    elif warnings:
        text = maybe_str(warnings)
        if text:
            result.append(text)
    return result


from app.core.models import Confidence


def normalize_confidence(value: Any) -> Confidence:
    if isinstance(value, Confidence):
        return value
    text = str(value or "").strip().lower()
    if text == "high":
        return Confidence.high
    if text == "medium":
        return Confidence.medium
    return Confidence.low


def compress_text(value: Any, max_chars: int) -> str:
    text = normalize_whitespace(str(value or ""))
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."


def extract_check_title(item: Dict[str, Any]) -> Optional[str]:
    metadata = ensure_dict(item.get("metadata"))
    return first_non_empty(
        metadata.get("title"),
        metadata.get("name"),
        item.get("title"),
    )


def extract_capability_name(item: Dict[str, Any]) -> Optional[str]:
    metadata = ensure_dict(item.get("metadata"))
    return first_non_empty(
        metadata.get("capability_name"),
        metadata.get("title"),
        metadata.get("name"),
        item.get("capability_name"),
        item.get("title"),
        metadata.get("capability_id"),
        item.get("capability_id"),
    )


def compress_check_text(item: Dict[str, Any], max_chars: int) -> str:
    metadata = ensure_dict(item.get("metadata"))
    title = extract_check_title(item)

    description = first_non_empty(
        metadata.get("description"),
        metadata.get("risk"),
        metadata.get("remediation"),
        metadata.get("retrieval_text"),
    )

    title_norm = normalize_whitespace(title or "").lower()
    desc_norm = normalize_whitespace(description or "").lower()

    parts = []
    if title:
        parts.append(title)

    if description and desc_norm != title_norm:
        parts.append(description)

    if not parts and metadata.get("check_id"):
        parts.append(str(metadata["check_id"]))

    return compress_text(". ".join(parts), max_chars=max_chars)


def compress_capability_text(item: Dict[str, Any], max_chars: int) -> str:
    metadata = ensure_dict(item.get("metadata"))
    capability_name = extract_capability_name(item)

    summary = first_non_empty(
        metadata.get("summary"),
        metadata.get("risk_explanation"),
        metadata.get("guidance"),
        metadata.get("retrieval_text"),
    )

    parts = []
    if capability_name:
        parts.append(capability_name)
    if summary:
        parts.append(summary)

    return compress_text(". ".join(parts), max_chars=max_chars)
