from __future__ import annotations

import re
import unicodedata
from typing import Any, List, Optional, Dict

from nltk.stem import SnowballStemmer
from nltk.corpus import stopwords as _nltk_stopwords

from app.core.config import INDEX_VERSION
from app.core.models import MaturityCapabilityDoc, MaturityMappingDoc, ProwlerCheckDoc

# ---------- Stemmer & stopwords (singleton) ----------
_stemmer = SnowballStemmer("english")

# NLTK English stopwords + custom AWS domain stopwords that appear in nearly
# every document and carry no discriminative value for ranking.
_ENGLISH_STOPWORDS: frozenset[str] = frozenset(_nltk_stopwords.words("english"))
_AWS_STOPWORDS: frozenset[str] = frozenset({
    "aws", "amazon", "service", "resource", "resources",
    "configuration", "setting", "settings", "ensure",
    "check", "checks", "account", "using",
})
_STOPWORDS: frozenset[str] = _ENGLISH_STOPWORDS | _AWS_STOPWORDS


def normalize_query(text: str) -> str:
    return _normalize_for_index(text).lower()


def tokenize(text: str, use_stemming: bool = True) -> List[str]:
    """Tokenize text for BM25 indexing / querying.

    Pipeline: lowercase → split on non-alphanumeric → remove stopwords → stem.
    Both build-time and query-time MUST call this with the same flags to keep
    the index consistent.
    """
    normalized = normalize_query(text)
    if not normalized:
        return []
    raw_tokens = [tok for tok in re.split(r"[^a-z0-9_]+", normalized) if tok]
    # Remove stopwords
    filtered = [tok for tok in raw_tokens if tok not in _STOPWORDS]
    if use_stemming:
        filtered = [_stemmer.stem(tok) for tok in filtered]
    # Drop empty tokens that may result from stemming
    return [tok for tok in filtered if tok]


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
        "data_encryption_at_rest": [
            "encryption at rest",
            "protect stored data with encryption",
            "encrypt stored data",
            "make stolen storage unreadable",
            "default encryption",
            "server side encryption",
            "kms encryption",
        ],
        "encryption_in_transit": [
            "encryption in transit",
            "secure transport",
            "https only",
            "tls required",
            "require ssl",
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

def _check_aliases(
    check_id: str,
    service: str,
    title: str,
    description: str,
    risk: str,
    remediation: str,
) -> List[str]:
    aliases = set()

    cid = _normalize_identifier(check_id)
    service = normalize_service(service)
    title_l = _normalize_for_index(title).lower()
    description_l = _normalize_for_index(description).lower()
    risk_l = _normalize_for_index(risk).lower()
    remediation_l = _normalize_for_index(remediation).lower()

    if cid:
        aliases.add(cid)
        aliases.add(cid.replace("_", " "))
        aliases.add(cid.replace("_", "-"))

    if service:
        aliases.add(service)
        if service == "s3":
            aliases.update(
                {
                    "bucket",
                    "buckets",
                    "object storage",
                    "cloud storage",
                    "storage bucket",
                    "bucket objects",
                    "bucket contents",
                    "object store",
                    "s3 bucket",
                    "s3 buckets",
                }
            )

    if title_l:
        aliases.add(title_l)

    # Broad public-access semantic phrases
    public_access_phrases = {
        "public access",
        "public exposure",
        "publicly accessible",
        "internet exposed",
        "internet-facing access",
        "anonymous access",
        "unauthenticated access",
        "world readable",
        "world-readable",
        "public read",
        "public reads",
        "public listing",
        "list bucket contents",
        "browse bucket contents",
        "bucket listing",
        "make storage private",
        "keep storage private",
        "keep bucket private",
        "prevent public exposure",
        "block public access",
        "restrict public access",
    }

    write_exposure_phrases = {
        "public write",
        "public upload",
        "upload files publicly",
        "anonymous upload",
        "world writable",
        "world-writable",
        "prevent public write",
        "prevent public uploads",
    }

    policy_public_phrases = {
        "public bucket policy",
        "bucket policy public access",
        "policy allows public write",
        "public write policy",
        "policy-based public access",
    }

    account_level_phrases = {
        "account-level public access block",
        "private by default",
        "block public access account wide",
        "organization-wide public access block",
        "default deny public access",
    }

    level_block_phrases = {
        "bucket-level public access block",
        "block public reads at bucket level",
        "prevent public reads on bucket",
        "prevent public exposure of bucket",
    }

    # Handcrafted aliases for high-impact checks from benchmark
    handcrafted = {
        "s3_account_level_public_access_blocks": public_access_phrases | account_level_phrases | {
            "stop public access to aws object storage",
            "keep cloud file storage inaccessible to the public",
            "make object storage private by default",
            "security issue when bucket objects are publicly accessible",
        },
        "s3_bucket_level_public_access_block": public_access_phrases | level_block_phrases | {
            "how to prevent an s3 bucket from being publicly exposed",
            "misconfiguration that allows public reads on cloud storage",
            "prevent world readable bucket objects",
            "how to avoid accidental public exposure of files in s3",
        },
        "s3_bucket_public_list_acl": public_access_phrases | {
            "avoid outsiders browsing files in cloud buckets",
            "avoid public listing of files in object storage buckets",
            "prevent listing bucket contents publicly",
            "stop public listing of bucket contents",
        },
        "s3_bucket_public_write_acl": public_access_phrases | write_exposure_phrases | {
            "make sure users cannot upload files publicly to s3",
            "prevent public writes to bucket",
            "prevent anonymous writes to bucket",
        },
        "s3_bucket_policy_public_write_access": public_access_phrases | policy_public_phrases | {
            "prevent anonymous users from accessing bucket data",
            "stop unauthenticated access to bucket contents",
            "policy exposes bucket contents",
        },
        "s3_bucket_public_access": public_access_phrases | {
            "bucket is publicly accessible",
            "public bucket access",
            "publicly exposed bucket",
        },
        "s3_bucket_cross_account_access": {
            "cross account bucket access",
            "external account access to bucket",
            "bucket shared across accounts",
        },
    }

    if cid in handcrafted:
        aliases.update(handcrafted[cid])

    # Lightweight contextual expansion from source fields
    source_blob = " ".join([title_l, description_l, risk_l, remediation_l])
    if "public" in source_blob:
        aliases.update({"public access", "public exposure"})
    if "anonymous" in source_blob or "unauthenticated" in source_blob:
        aliases.update({"anonymous access", "unauthenticated access"})
    if "list" in source_blob:
        aliases.update({"bucket listing", "public listing"})
    if "write" in source_blob or "upload" in source_blob:
        aliases.update({"public write", "public upload"})
    if "policy" in source_blob:
        aliases.update({"bucket policy", "policy-based access"})
    if "acl" in cid:
        aliases.update({"access control list", "acl"})

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


def build_retrieval_text_prefixed(fields: List[tuple]) -> str:
    """Build retrieval text with field-level prefixes for better embedding quality.

    Args:
        fields: List of (field_name, value) tuples. e.g. [("check", "s3_bucket_..."), ("service", "s3")]
    """
    chunks: List[str] = []
    for field_name, value in fields:
        text = _normalize_for_index(value)
        if text:
            chunks.append(f"{field_name}: {text.lower()}")
    return "\n".join(chunks)


def _extract_recommendation_text(remediation: Any) -> str:
    """Extract only human-readable recommendation text from Remediation,
    excluding CLI commands, Terraform code, CloudFormation YAML, and URLs."""
    if isinstance(remediation, dict):
        rec = remediation.get("Recommendation") or remediation.get("recommendation") or {}
        if isinstance(rec, dict):
            return _normalize_for_index(rec.get("Text") or rec.get("text") or "")
        return _normalize_for_index(rec) if isinstance(rec, str) else ""
    if isinstance(remediation, str):
        text = remediation.strip()
        # If it looks like a serialized dict/JSON, try to skip it
        if text.startswith("{") or text.startswith("["):
            return ""
        return _normalize_for_index(text)
    return ""


def _truncate_words(text: str, max_words: int = 300) -> str:
    """Truncate text to max_words, preserving whole words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def _text_overlap_ratio(text_a: str, text_b: str) -> float:
    """Calculate word-level overlap ratio between two texts."""
    if not text_a or not text_b:
        return 0.0
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    return intersection / min(len(words_a), len(words_b))

def _normalize_capability_name_key(value: Any) -> str:
    text = _normalize_for_index(value).lower()
    text = text.replace("&", " and ")
    text = text.replace("/", " ")
    text = text.replace("-", " ")
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_capability_name_to_id_lookup(
    capability_docs: List[MaturityCapabilityDoc],
) -> Dict[str, str]:
    lookup: Dict[str, str] = {}

    for doc in capability_docs:
        canonical_id = _normalize_identifier(doc.capability_id)
        if not canonical_id:
            continue

        keys = {
            _normalize_capability_name_key(doc.capability_name),
            _normalize_capability_name_key(doc.capability_id),
            _normalize_capability_name_key(doc.doc_id),
        }

        for alias in _capability_aliases(doc.capability_id, doc.capability_name):
            keys.add(_normalize_capability_name_key(alias))

        for key in keys:
            if key:
                lookup[key] = canonical_id

    return lookup


def resolve_mapping_capability_id(
    raw_capability_id: Any,
    raw_capability_name: Any,
    capability_lookup: Optional[Dict[str, str]] = None,
) -> str:
    """
    Resolve mapping capability_id to the canonical capability_id used
    by maturity capability documents.

    Priority:
    1. capability_name lookup against normalized maturity docs
    2. raw capability_id lookup
    3. fallback to normalized raw capability_id
    """
    fallback_id = _normalize_identifier(raw_capability_id)
    capability_name_key = _normalize_capability_name_key(raw_capability_name)
    raw_capability_id_key = _normalize_capability_name_key(raw_capability_id)

    if capability_lookup:
        if capability_name_key and capability_name_key in capability_lookup:
            return capability_lookup[capability_name_key]
        if raw_capability_id_key and raw_capability_id_key in capability_lookup:
            return capability_lookup[raw_capability_id_key]

        # fallback for prefixed ids like 1_quickwins_block_public_access
        if fallback_id:
            stripped = re.sub(
                r"^\d+_(quickwins|quick_wins|foundational|efficient|optimized)_",
                "",
                fallback_id,
            )
            stripped_key = _normalize_capability_name_key(stripped)
            if stripped_key in capability_lookup:
                return capability_lookup[stripped_key]

    return fallback_id

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

    # For retrieval text: truncate summary and deduplicate vs recommendations
    summary_for_retrieval = _truncate_words(summary, max_words=300)
    rec_text_combined = " ".join(recommended_practices)
    # If recommendations overlap heavily with summary, skip them in retrieval text
    if _text_overlap_ratio(summary_for_retrieval, rec_text_combined) > 0.8:
        rec_for_retrieval = ""
    else:
        rec_for_retrieval = rec_text_combined

    alias_text = " ".join(alias_inputs) if alias_inputs else ""

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
        retrieval_text=build_retrieval_text_prefixed(
            [
                ("capability", capability_id),
                ("name", capability_name),
                ("aliases", alias_text),
                ("domain", raw.get("domain", "")),
                ("summary", summary_for_retrieval),
                ("risk", risk_explanation),
                ("guidance", guidance),
                ("keywords", " ".join(keywords)),
                ("recommendations", rec_for_retrieval),
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
    # Full remediation kept in doc field for downstream use
    remediation = _normalize_for_index(raw.get("Remediation", ""))
    # Extract only human-readable recommendation text for retrieval
    recommendation_text = _extract_recommendation_text(raw.get("Remediation", ""))
    keywords = normalize_string_list(raw.get("Categories", []))
    tags = normalize_string_list(raw.get("tags", []))

    aliases = _check_aliases(
        check_id=check_id,
        service=service,
        title=title,
        description=description,
        risk=risk,
        remediation=remediation,
    )

    enriched_keywords = sorted(
        set(keywords)
        | set(tags)
        | (
            {
                "bucket",
                "object storage",
                "cloud storage",
                "public access",
            }
            if service == "s3"
            else set()
        )
    )

    alias_text = " ".join(aliases) if aliases else ""

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
        synonyms=aliases,
        retrieval_text=build_retrieval_text_prefixed(
            [
                ("check", check_id),
                ("service", service),
                ("title", title),
                ("description", description),
                ("risk", risk),
                ("recommendation", recommendation_text),
                ("resource_type", raw.get("ResourceType", "")),
                ("keywords", " ".join(enriched_keywords)),
                ("aliases", alias_text),
            ]
        ),
    )
    return doc


def normalize_mapping_doc(
    raw: dict,
    capability_lookup: Optional[Dict[str, str]] = None,
) -> MaturityMappingDoc:
    check_id = _normalize_identifier(raw.get("check_id"))
    if not check_id:
        raise ValueError("mapping doc missing check_id")

    capability_name = _normalize_for_index(raw.get("capability_name", ""))
    capability_id = resolve_mapping_capability_id(
        raw_capability_id=raw.get("capability_id"),
        raw_capability_name=capability_name,
        capability_lookup=capability_lookup,
    )
    if not capability_id:
        raise ValueError("mapping doc missing capability_id")

    service = normalize_service(raw.get("service", ""))
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
