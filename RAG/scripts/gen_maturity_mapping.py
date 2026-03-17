from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "to",
    "for",
    "in",
    "on",
    "by",
    "with",
    "from",
    "is",
    "are",
    "be",
    "as",
    "at",
    "that",
    "this",
    "it",
    "into",
    "can",
    "you",
    "your",
    "all",
    "not",
    "do",
    "does",
    "have",
    "has",
    "will",
    "if",
    "than",
    "then",
    "their",
    "there",
    "what",
    "when",
    "while",
    "how",
    "why",
    "about",
    "across",
    "per",
    "only",
    "also",
    "using",
    "use",
    "used",
    "ensure",
    "evaluate",
    "current",
    "should",
    "must",
}

# Có thể mở rộng dần theo domain của bạn
CANONICAL_SYNONYMS = {
    "public": "public",
    "internet": "internet",
    "exposed": "exposure",
    "exposure": "exposure",
    "bucket": "storage",
    "buckets": "storage",
    "s3": "storage",
    "encryption": "encrypt",
    "encrypted": "encrypt",
    "kms": "encrypt",
    "resilience": "resilience",
    "availability": "availability",
    "sla": "availability",
    "rto": "resilience",
    "rpo": "resilience",
    "backup": "recovery",
    "recovery": "recovery",
    "logging": "logging",
    "log": "logging",
    "monitoring": "monitoring",
    "detect": "detection",
    "detection": "detection",
    "iam": "identity",
    "identity": "identity",
    "access": "access",
    "policy": "policy",
    "policies": "policy",
    "network": "network",
    "publicly": "public",
    "acl": "access",
    "replica": "resilience",
    "multi-az": "resilience",
    "multi-region": "resilience",
    "confidentiality": "confidentiality",
    "integrity": "integrity",
    "cia": "confidentiality",
}

IMPORTANT_PHRASES = [
    "public access",
    "internet exposed",
    "block public access",
    "least privilege",
    "data protection",
    "security logging",
    "incident response",
    "backup recovery",
    "resilience posture",
    "availability targets",
    "recovery point objective",
    "recovery time objective",
    "encryption at rest",
    "encryption in transit",
]


@dataclass
class ScoredCandidate:
    maturity: Dict[str, Any]
    score: float
    overlap_terms: List[str]
    phrase_hits: List[str]
    service_bonus: float
    domain_bonus: float
    title_bonus: float


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_items(path: Path) -> List[Dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, dict) and "items" in payload:
        items = payload["items"]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError(f"Unsupported JSON format for {path}")

    if not isinstance(items, list):
        raise ValueError(f"'items' is not a list in {path}")
    return [x for x in items if isinstance(x, dict)]


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def textify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return normalize_space(value)
    if isinstance(value, list):
        return normalize_space(" ".join(textify(v) for v in value if textify(v)))
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            t = textify(v)
            if t:
                parts.append(f"{k} {t}")
        return normalize_space(" ".join(parts))
    return normalize_space(str(value))


def ensure_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [textify(v) for v in value if textify(v)]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if value.startswith("[") and value.endswith("]"):
            try:
                arr = json.loads(value)
                if isinstance(arr, list):
                    return [textify(v) for v in arr if textify(v)]
            except Exception:
                pass
        return [value]
    return [textify(value)]


def canonical_token(token: str) -> str:
    token = token.lower().strip("_- ")
    token = CANONICAL_SYNONYMS.get(token, token)
    return token


def tokenize(text: str) -> List[str]:
    text = text.lower()
    text = text.replace("/", " ").replace("-", " ").replace("_", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    raw_tokens = [t for t in text.split() if t]
    tokens = []
    for tok in raw_tokens:
        tok = canonical_token(tok)
        if len(tok) <= 1:
            continue
        if tok in STOPWORDS:
            continue
        tokens.append(tok)
    return tokens


def unique_preserve_order(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        if not item:
            continue
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def flatten_prowler_text(record: Dict[str, Any]) -> str:
    remediation = record.get("Remediation") or record.get("remediation") or ""
    parts = [
        record.get("CheckID"),
        record.get("CheckTitle"),
        record.get("CheckType"),
        record.get("ServiceName"),
        record.get("SubServiceName"),
        record.get("Severity"),
        record.get("ResourceType"),
        record.get("Description"),
        record.get("Risk"),
        remediation,
        record.get("Categories"),
        record.get("RelatedTo"),
        record.get("Notes"),
    ]
    return textify(parts)


def flatten_maturity_text(record: Dict[str, Any]) -> str:
    parts = [
        record.get("capability_id"),
        record.get("domain"),
        record.get("phase"),
        record.get("title"),
        record.get("summary"),
        record.get("risk_explanation"),
        record.get("recommendation"),
        record.get("guidance"),
        record.get("how_to_check"),
        record.get("keywords"),
    ]
    return textify(parts)


def infer_maturity_capability_id(record: Dict[str, Any]) -> str:
    raw_id = textify(record.get("capability_id"))
    if raw_id:
        return slugify(raw_id)
    phase = textify(record.get("phase"))
    title = textify(record.get("title")) or textify(record.get("capability_name"))
    return slugify(f"{phase}_{title}" if phase else title)


def infer_maturity_domain(record: Dict[str, Any]) -> str:
    direct = textify(record.get("domain"))
    if direct:
        return slugify(direct)

    text = " ".join(
        [
            textify(record.get("title")),
            textify(record.get("summary")),
            textify(record.get("risk_explanation")),
            textify(record.get("guidance")),
        ]
    ).lower()

    heuristics = [
        (
            "data_protection",
            [
                "data protection",
                "public access",
                "encrypt",
                "confidentiality",
                "storage",
            ],
        ),
        ("resilience", ["resilience", "rto", "rpo", "availability", "recovery"]),
        ("identity_access", ["identity", "iam", "privilege", "access", "mfa"]),
        ("logging_monitoring", ["logging", "monitoring", "detection", "log"]),
        ("network_security", ["network", "internet", "ingress", "egress", "exposure"]),
    ]
    for domain, markers in heuristics:
        if any(marker in text for marker in markers):
            return domain

    return "general"


def extract_prowler_keywords(record: Dict[str, Any]) -> List[str]:
    out = []
    out.extend(tokenize(textify(record.get("CheckID"))))
    out.extend(tokenize(textify(record.get("CheckTitle"))))
    out.extend(tokenize(textify(record.get("Description"))))
    out.extend(tokenize(textify(record.get("Risk"))))
    out.extend(tokenize(textify(record.get("ServiceName"))))
    out.extend(tokenize(textify(record.get("ResourceType"))))
    out.extend(tokenize(textify(record.get("Categories"))))
    out.extend(tokenize(textify(record.get("CheckType"))))
    return unique_preserve_order(out)


def extract_maturity_keywords(record: Dict[str, Any]) -> List[str]:
    out = []
    out.extend(tokenize(textify(record.get("capability_id"))))
    out.extend(tokenize(textify(record.get("domain"))))
    out.extend(tokenize(textify(record.get("phase"))))
    out.extend(tokenize(textify(record.get("title"))))
    out.extend(tokenize(textify(record.get("capability_name"))))
    out.extend(tokenize(textify(record.get("summary"))))
    out.extend(tokenize(textify(record.get("risk_explanation"))))
    out.extend(tokenize(textify(record.get("recommendation"))))
    out.extend(tokenize(textify(record.get("guidance"))))
    out.extend(tokenize(textify(record.get("how_to_check"))))
    out.extend(tokenize(textify(record.get("keywords"))))
    return unique_preserve_order(out)


def jaccard_score(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def weighted_overlap_score(a: List[str], b: List[str]) -> float:
    ca, cb = Counter(a), Counter(b)
    common = set(ca) & set(cb)
    if not common:
        return 0.0
    numerator = sum(min(ca[t], cb[t]) for t in common)
    denominator = sum(ca.values()) + sum(cb.values())
    if denominator == 0:
        return 0.0
    return (2.0 * numerator) / denominator


def phrase_hits(check_text: str, maturity_text: str) -> List[str]:
    c = check_text.lower()
    m = maturity_text.lower()
    hits = []
    for phrase in IMPORTANT_PHRASES:
        if phrase in c and phrase in m:
            hits.append(phrase)
    return hits


def service_domain_bonus(
    prowler: Dict[str, Any], maturity: Dict[str, Any]
) -> Tuple[float, float]:
    service = textify(prowler.get("ServiceName")).lower()
    maturity_domain = infer_maturity_domain(maturity).lower()
    check_text = flatten_prowler_text(prowler).lower()

    service_bonus = 0.0
    domain_bonus = 0.0

    if service == "s3" and any(
        k in maturity_domain for k in ["data_protection", "network_security"]
    ):
        service_bonus += 0.04
    if service == "iam" and "identity" in maturity_domain:
        service_bonus += 0.06
    if service in {"cloudtrail", "cloudwatch"} and "logging" in maturity_domain:
        service_bonus += 0.06

    if "public access" in check_text and maturity_domain in {
        "data_protection",
        "network_security",
    }:
        domain_bonus += 0.07
    if (
        any(x in check_text for x in ["rto", "rpo", "resilience", "availability"])
        and maturity_domain == "resilience"
    ):
        domain_bonus += 0.08
    if (
        any(x in check_text for x in ["encrypt", "kms"])
        and maturity_domain == "data_protection"
    ):
        domain_bonus += 0.07
    if (
        any(x in check_text for x in ["mfa", "privilege", "iam", "identity"])
        and maturity_domain == "identity_access"
    ):
        domain_bonus += 0.08
    if (
        any(x in check_text for x in ["logging", "log", "monitoring", "detect"])
        and maturity_domain == "logging_monitoring"
    ):
        domain_bonus += 0.08

    return service_bonus, domain_bonus


def title_alignment_bonus(prowler: Dict[str, Any], maturity: Dict[str, Any]) -> float:
    check_title_tokens = set(tokenize(textify(prowler.get("CheckTitle"))))
    maturity_title_tokens = set(
        tokenize(textify(maturity.get("title") or maturity.get("capability_name")))
    )
    if not check_title_tokens or not maturity_title_tokens:
        return 0.0
    overlap = len(check_title_tokens & maturity_title_tokens)
    return min(0.10, overlap * 0.015)


def score_candidate(
    prowler: Dict[str, Any], maturity: Dict[str, Any]
) -> ScoredCandidate:
    p_text = flatten_prowler_text(prowler)
    m_text = flatten_maturity_text(maturity)

    p_tokens = extract_prowler_keywords(prowler)
    m_tokens = extract_maturity_keywords(maturity)

    jac = jaccard_score(p_tokens, m_tokens)
    overlap = weighted_overlap_score(p_tokens, m_tokens)
    hits = phrase_hits(p_text, m_text)
    phrase_bonus = min(0.15, len(hits) * 0.04)

    service_bonus, domain_bonus = service_domain_bonus(prowler, maturity)
    title_bonus = title_alignment_bonus(prowler, maturity)

    score = (
        0.42 * jac
        + 0.38 * overlap
        + phrase_bonus
        + service_bonus
        + domain_bonus
        + title_bonus
    )
    score = max(0.0, min(1.0, score))

    overlap_terms = sorted(set(p_tokens) & set(m_tokens))[:12]

    return ScoredCandidate(
        maturity=maturity,
        score=score,
        overlap_terms=overlap_terms,
        phrase_hits=hits,
        service_bonus=service_bonus,
        domain_bonus=domain_bonus,
        title_bonus=title_bonus,
    )


def build_mapping_reason(prowler: Dict[str, Any], candidate: ScoredCandidate) -> str:
    parts = []

    if candidate.overlap_terms:
        parts.append("Shared concepts: " + ", ".join(candidate.overlap_terms[:8]))
    if candidate.phrase_hits:
        parts.append("Common phrases: " + ", ".join(candidate.phrase_hits[:4]))

    capability_name = textify(
        candidate.maturity.get("title") or candidate.maturity.get("capability_name")
    )
    if capability_name:
        parts.append(f"Matched against maturity capability '{capability_name}'.")

    if candidate.domain_bonus > 0:
        parts.append(
            f"Domain alignment bonus applied for inferred domain '{infer_maturity_domain(candidate.maturity)}'."
        )

    if candidate.service_bonus > 0:
        service = textify(prowler.get("ServiceName"))
        parts.append(f"Service-aware bonus applied for '{service}' context.")

    if not parts:
        parts.append("Auto-generated from lexical overlap and contextual similarity.")
    return " ".join(parts)


def confidence_from_score(score: float) -> str:
    if score >= 0.50:
        return "high"
    if score >= 0.33:
        return "medium"
    return "low"


def review_status_from_score(score: float, gap: float) -> str:
    if score >= 0.50 and gap >= 0.08:
        return "approved"
    if score >= 0.33:
        return "draft"
    return "review_required"


def mapping_type_from_score(score: float) -> str:
    if score >= 0.50:
        return "direct"
    if score >= 0.33:
        return "related"
    return "weak"


def build_mapping_item(
    prowler: Dict[str, Any],
    candidate: ScoredCandidate,
    score_gap: float,
) -> Dict[str, Any]:
    maturity = candidate.maturity
    capability_id = infer_maturity_capability_id(maturity)
    capability_name = textify(maturity.get("title") or maturity.get("capability_name"))
    domain = infer_maturity_domain(maturity)

    return {
        "provider": "aws",
        "service": textify(prowler.get("ServiceName")) or None,
        "domain": domain,
        "check_id": textify(prowler.get("CheckID")),
        "capability_id": capability_id,
        "capability_name": capability_name,
        "mapping_confidence": confidence_from_score(candidate.score),
        "mapping_reason": build_mapping_reason(prowler, candidate),
        "review_status": review_status_from_score(candidate.score, score_gap),
        "reviewed_by": None,
        "mapping_type": mapping_type_from_score(candidate.score),
        "score": round(candidate.score, 4),
        "score_gap_vs_second": round(score_gap, 4),
        "matched_terms": candidate.overlap_terms,
        "matched_phrases": candidate.phrase_hits,
    }


def best_candidates(
    prowler: Dict[str, Any],
    maturity_items: List[Dict[str, Any]],
    top_k: int,
) -> List[ScoredCandidate]:
    scored = [score_candidate(prowler, m) for m in maturity_items]
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_k]


def main() -> None:
    # Use the repository root as the base for relative paths so the script behaves
    # the same regardless of the current working directory.
    base_dir = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(
        description="Auto-generate raw maturity mappings from prowler and maturity raw datasets"
    )
    parser.add_argument(
        "--prowler",
        default=str(base_dir / "data" / "raw" / "prowler_checks.json"),
        help="Path to prowler raw JSON",
    )
    parser.add_argument(
        "--maturity",
        default=str(base_dir / "data" / "raw" / "maturity_capabilities.json"),
        help="Path to maturity raw JSON",
    )
    parser.add_argument(
        "--out",
        default=str(base_dir / "data" / "raw" / "maturity_mappings.json"),
        help="Output path for generated mappings",
    )
    parser.add_argument(
        "--candidates-out",
        default=str(base_dir / "data" / "raw" / "maturity_mapping_candidates.json"),
        help="Output path for review candidates",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of candidate matches to retain per check",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.20,
        help="Minimum score to emit a mapping item",
    )
    parser.add_argument(
        "--approved-threshold",
        type=float,
        default=0.50,
        help="Score threshold above which a mapping may be auto-approved",
    )
    args = parser.parse_args()

    prowler_path = Path(args.prowler)
    maturity_path = Path(args.maturity)
    out_path = Path(args.out)
    candidates_path = Path(args.candidates_out)

    if not prowler_path.is_absolute():
        prowler_path = base_dir / prowler_path
    if not maturity_path.is_absolute():
        maturity_path = base_dir / maturity_path
    if not out_path.is_absolute():
        out_path = base_dir / out_path
    if not candidates_path.is_absolute():
        candidates_path = base_dir / candidates_path

    prowler_items = load_items(prowler_path)
    maturity_items = load_items(maturity_path)

    generated_items: List[Dict[str, Any]] = []
    candidate_rows: List[Dict[str, Any]] = []

    for check in prowler_items:
        check_id = textify(check.get("CheckID") or check.get("check_id"))
        if not check_id:
            continue

        top = best_candidates(check, maturity_items, args.top_k)
        if not top:
            continue

        best = top[0]
        second_score = top[1].score if len(top) > 1 else 0.0
        score_gap = best.score - second_score

        if best.score >= args.min_score:
            item = build_mapping_item(check, best, score_gap)

            # vẫn tôn trọng threshold user truyền vào
            if (
                best.score < args.approved_threshold
                and item["review_status"] == "approved"
            ):
                item["review_status"] = "draft"

            generated_items.append(item)

        candidate_rows.append(
            {
                "check_id": check_id,
                "service": textify(check.get("ServiceName")),
                "top_candidates": [
                    {
                        "capability_id": infer_maturity_capability_id(c.maturity),
                        "capability_name": textify(
                            c.maturity.get("title") or c.maturity.get("capability_name")
                        ),
                        "domain": infer_maturity_domain(c.maturity),
                        "score": round(c.score, 4),
                        "matched_terms": c.overlap_terms,
                        "matched_phrases": c.phrase_hits,
                    }
                    for c in top
                ],
            }
        )

    generated_items.sort(key=lambda x: (x["check_id"], -x["score"]))
    candidate_rows.sort(key=lambda x: x["check_id"])

    mappings_payload = {
        "metadata": {
            "dataset": "maturity_mappings",
            "source_prowler": str(prowler_path),
            "source_maturity": str(maturity_path),
            "generated_at": utc_now(),
            "generator": "scripts/generate_maturity_mappings.py",
            "item_count": len(generated_items),
            "top_k": args.top_k,
            "min_score": args.min_score,
        },
        "items": generated_items,
    }

    candidates_payload = {
        "metadata": {
            "generated_at": utc_now(),
            "item_count": len(candidate_rows),
            "top_k": args.top_k,
        },
        "items": candidate_rows,
    }

    save_json(out_path, mappings_payload)
    save_json(candidates_path, candidates_payload)

    approved = sum(1 for x in generated_items if x["review_status"] == "approved")
    draft = sum(1 for x in generated_items if x["review_status"] == "draft")
    review_required = sum(
        1 for x in generated_items if x["review_status"] == "review_required"
    )

    print(f"[generate_maturity_mappings] Wrote mappings -> {out_path}")
    print(f"[generate_maturity_mappings] Wrote candidates -> {candidates_path}")
    print(
        f"[generate_maturity_mappings] total={len(generated_items)} "
        f"approved={approved} draft={draft} review_required={review_required}"
    )


if __name__ == "__main__":
    main()
