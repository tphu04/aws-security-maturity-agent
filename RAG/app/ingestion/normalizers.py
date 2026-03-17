from __future__ import annotations

import re
import unicodedata
from typing import Any, List, Optional

from app.core.config import INDEX_VERSION
from app.core.models import MaturityCapabilityDoc, MaturityMappingDoc, ProwlerCheckDoc


def normalize_query(text: str) -> str:
    return _normalize_for_index(text).lower()


def tokenize(text: str) -> List[str]:
    normalized = normalize_query(text)
    if not normalized:
        return []
    return [tok for tok in re.split(r"[^a-z0-9_]+", normalized) if tok]


def _normalize_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(str(v) for v in value.values() if v is not None)
    if isinstance(value, list):
        return " ".join(str(v) for v in value if v is not None)
    return str(value)


def _normalize_unicode(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize("NFKC", text)


def _clean_whitespace(text: str) -> str:
    text = _normalize_to_text(text)
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_for_index(value: Any) -> str:
    return _clean_whitespace(_normalize_unicode(_normalize_to_text(value)))


def _normalize_identifier(value: Any) -> str:
    text = _normalize_for_index(value).lower()
    text = text.replace("-", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def _slugify(text: str) -> str:
    text = _normalize_for_index(text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def _capability_aliases(capability_id: str, capability_name: str) -> List[str]:
    aliases = set()

    cid = _normalize_identifier(capability_id)
    cname = _normalize_for_index(capability_name).lower()

    if cid:
        aliases.add(cid)
        aliases.add(cid.replace("_", " "))
        aliases.add(cid.replace("_", "-"))

    if cname:
        aliases.add(cname)

    handcrafted = {
        "block_public_access": [
            "block public access",
            "prevent public exposure",
            "prevent anonymous access",
            "restrict public access",
            "keep storage private",
        ],
        "audit_api_calls": [
            "audit api calls",
            "record api activity",
            "monitor api activity",
            "track cloud api calls",
            "log api usage",
        ],
        "data_backups": [
            "data backups",
            "backup and restore",
            "recover from backup",
            "restore critical data",
            "backup recovery",
        ],
        "encryption_at_rest": [
            "encryption at rest",
            "protect stored data with encryption",
            "encrypt stored data",
            "make stolen storage unreadable",
        ],
        "network_segmentation": [
            "network segmentation",
            "separate network zones",
            "limit blast radius",
            "isolate network zones",
            "public private network separation",
        ],
    }

    normalized_cid = _normalize_identifier(cid)
    for key, values in handcrafted.items():
        if normalized_cid == key or normalized_cid.startswith(key):
            aliases.update(values)

    return sorted(a for a in aliases if a)


def normalize_provider(provider: Optional[str]) -> str:
    if not provider:
        return "aws"
    return _normalize_for_index(provider).lower()


def normalize_service(service: Optional[str]) -> str:
    if not service:
        return ""
    return _normalize_for_index(service).lower()


def normalize_severity(severity: Optional[str]) -> str:
    if not severity:
        return "informational"
    sev = _normalize_for_index(severity).lower()
    mapping = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
        "info": "informational",
        "informational": "informational",
    }
    return mapping.get(sev, sev)


def normalize_confidence(value: Optional[str]) -> str:
    if not value:
        return "low"
    v = _normalize_for_index(value).lower()
    mapping = {
        "high": "high",
        "medium": "medium",
        "low": "low",
    }
    return mapping.get(v, "low")


def normalize_string_list(values: Optional[List[Any]]) -> List[str]:
    if not values:
        return []
    cleaned = set()
    for item in values:
        text = _normalize_for_index(item)
        if text:
            cleaned.add(text.lower())
    return sorted(cleaned)


def build_retrieval_text(parts: List[Any]) -> str:
    chunks: List[str] = []
    for part in parts:
        text = _normalize_for_index(part)
        if text:
            chunks.append(text.lower())
    return "\n".join(chunks)


def normalize_maturity_doc(raw: dict) -> MaturityCapabilityDoc:
    capability_name = _normalize_for_index(
        raw.get("capability_name") or raw.get("title") or raw.get("name") or ""
    )
    if not capability_name:
        raise ValueError("maturity doc missing capability/title/name")

    # Canonical capability_id must always be underscore-normalized.
    capability_id = _normalize_identifier(raw.get("capability_id")) or _normalize_identifier(
        raw.get("id")
    ) or _normalize_identifier(capability_name)
    if not capability_id:
        raise ValueError("maturity doc missing resolvable capability_id")

    # IMPORTANT:
    # Always use canonical doc_id derived from canonical capability_id.
    # Do not trust raw doc_id from source as primary runtime key.
    source_doc_id = _normalize_for_index(raw.get("doc_id") or raw.get("id") or "")
    doc_id = f"capability:{capability_id}"

    raw_recommendations = raw.get("recommended_practices") or raw.get("recommendation")
    if isinstance(raw_recommendations, list):
        recommended_practices = [
            _normalize_for_index(v)
            for v in raw_recommendations
            if _normalize_for_index(v)
        ]
    elif isinstance(raw_recommendations, str) and raw_recommendations.strip():
        recommended_practices = [_normalize_for_index(raw_recommendations)]
    else:
        recommended_practices = []

    keywords = normalize_string_list(raw.get("keywords", []))
    tags = normalize_string_list(raw.get("tags", []))
    summary = _normalize_for_index(raw.get("summary", ""))
    risk_explanation = _normalize_for_index(raw.get("risk_explanation", ""))
    guidance = _normalize_for_index(raw.get("guidance", ""))
    how_to_check = _normalize_for_index(raw.get("how_to_check", ""))

    aliases = _capability_aliases(capability_id, capability_name)

    # Include both canonical and source aliases in retrieval text.
    alias_inputs = list(aliases)
    if source_doc_id:
        alias_inputs.append(source_doc_id)
        alias_inputs.append(source_doc_id.replace("-", "_"))
        alias_inputs.append(source_doc_id.replace("_", "-"))

    doc = MaturityCapabilityDoc(
        doc_id=doc_id,
        doc_type="maturity_capability",
        source_name=raw.get("source_name", "aws_security_maturity_model"),
        source_type=raw.get("source_type", "official_doc"),
        source_uri=raw.get("source_uri", ""),
        version=str(raw.get("version", "1.0")),
        created_at=raw.get("created_at", ""),
        updated_at=raw.get("updated_at", ""),
        language=raw.get("language", "en"),
        tags=tags,
        index_version=INDEX_VERSION,
        provider=normalize_provider(raw.get("provider")),
        domain=_normalize_for_index(raw.get("domain", "")),
        capability_id=capability_id,
        capability_name=capability_name,
        stage=_normalize_for_index(raw.get("phase") or raw.get("stage") or ""),
        summary=summary,
        risk_explanation=risk_explanation or None,
        guidance=guidance or None,
        how_to_check=how_to_check or None,
        recommended_practices=recommended_practices,
        keywords=keywords,
        retrieval_text=build_retrieval_text(
            [
                capability_id,
                capability_name,
                alias_inputs,
                raw.get("domain", ""),
                summary,
                risk_explanation,
                guidance,
                how_to_check,
                recommended_practices,
                keywords,
                tags,
            ]
        ),
    )
    return doc


def normalize_prowler_doc(raw: dict) -> ProwlerCheckDoc:
    check_id = _normalize_identifier(raw.get("CheckID"))
    if not check_id:
        raise ValueError("prowler doc missing CheckID")

    service = normalize_service(raw.get("ServiceName"))
    title = _normalize_for_index(raw.get("CheckTitle", ""))
    description = _normalize_for_index(raw.get("Description", ""))
    risk = _normalize_for_index(raw.get("Risk", ""))
    remediation = _normalize_for_index(raw.get("Remediation", ""))
    keywords = normalize_string_list(raw.get("Categories", []))
    tags = normalize_string_list(raw.get("tags", []))

    doc = ProwlerCheckDoc(
        doc_id=f"check:{check_id}",
        doc_type="prowler_check",
        source_name=raw.get("source_name", "prowler_checks"),
        source_type=raw.get("source_type", "official_check_metadata"),
        source_uri=raw.get("source_uri", ""),
        version=str(raw.get("version", "1.0")),
        created_at=raw.get("created_at", ""),
        updated_at=raw.get("updated_at", ""),
        language=raw.get("language", "en"),
        tags=tags,
        index_version=INDEX_VERSION,
        check_id=check_id,
        provider=normalize_provider(raw.get("Provider")),
        service=service,
        title=title,
        severity=normalize_severity(raw.get("Severity", "informational")),
        description=description,
        risk=risk,
        remediation=remediation,
        resource_type=_normalize_for_index(raw.get("ResourceType", "")) or None,
        keywords=keywords,
        synonyms=[],
        retrieval_text=build_retrieval_text(
            [
                check_id,
                service,
                title,
                description,
                risk,
                remediation,
                raw.get("ResourceType", ""),
                keywords,
                tags,
            ]
        ),
    )
    return doc


def normalize_mapping_doc(raw: dict) -> MaturityMappingDoc:
    check_id = _normalize_identifier(raw.get("check_id"))
    capability_id = _normalize_identifier(raw.get("capability_id"))
    if not check_id:
        raise ValueError("mapping doc missing check_id")
    if not capability_id:
        raise ValueError("mapping doc missing capability_id")

    service = normalize_service(raw.get("service", ""))
    capability_name = _normalize_for_index(raw.get("capability_name", ""))
    domain = _normalize_for_index(raw.get("domain", ""))
    mapping_reason = _normalize_for_index(raw.get("mapping_reason", ""))
    tags = normalize_string_list(raw.get("tags", []))

    mapping_type = _normalize_for_index(raw.get("mapping_type", "")) or None
    mapping_confidence = normalize_confidence(raw.get("mapping_confidence", "low"))

    doc = MaturityMappingDoc(
        doc_id=f"mapping:{check_id}:{capability_id}",
        doc_type="maturity_mapping",
        source_name=raw.get("source_name", "manual_mappings"),
        source_type=raw.get("source_type", "reviewed_internal_mapping"),
        source_uri=raw.get("source_uri", ""),
        version=str(raw.get("version", "1.0")),
        created_at=raw.get("created_at", ""),
        updated_at=raw.get("updated_at", ""),
        language=raw.get("language", "en"),
        tags=tags,
        index_version=INDEX_VERSION,
        check_id=check_id,
        provider=normalize_provider(raw.get("provider", "aws")),
        service=service,
        domain=domain,
        capability_id=capability_id,
        capability_name=capability_name,
        mapping_confidence=mapping_confidence,
        mapping_reason=mapping_reason,
        review_status=_normalize_for_index(
            raw.get("review_status", "unreviewed")
        ).lower(),
        reviewed_by=_normalize_for_index(raw.get("reviewed_by", "")) or None,
        mapping_type=mapping_type,
        assessment_weight_hint=raw.get("assessment_weight_hint"),
        report_note=_normalize_for_index(raw.get("report_note", "")) or None,
        retrieval_text=build_retrieval_text(
            [
                check_id,
                service,
                domain,
                capability_id,
                capability_name,
                mapping_reason,
                mapping_type or "",
                mapping_confidence,
                tags,
            ]
        ),
    )
    return doc
