"""
Generation benchmark metrics for Risk Evaluation Agent.

4 core metrics:
- Structured Output Compliance (deterministic, chi phi = 0)
- Faithfulness (rule-based heuristic, khong can LLM judge)
- Correctness (severity accuracy + QWK)
- Completeness (evidence checklist matching)

Dependencies: sklearn (chi cho QWK).
Khong import agent code hoac RAG code.
"""

import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_ORDER = ["Low", "Medium", "High", "Critical"]
VALID_SEVERITIES = set(SEVERITY_ORDER)

SEVERITY_SCORE_MAP = {
    "Critical": (9, 10),
    "High": (7, 8),
    "Medium": (4, 6),
    "Low": (1, 3),
}

# ---------------------------------------------------------------------------
# 1. Structured Output Compliance
# ---------------------------------------------------------------------------

def evaluate_structure(output: Dict[str, Any]) -> Dict[str, Any]:
    """Danh gia cau truc output cua Risk Agent. Hoan toan deterministic."""

    json_parseable = isinstance(output, dict)

    # Required fields — agent tra ve severity, risk_score, reasoning
    required_fields = {"severity", "risk_score", "reasoning"}
    has_all_fields = required_fields.issubset(output.keys()) if json_parseable else False

    severity = output.get("severity")
    severity_valid = severity in VALID_SEVERITIES

    score = output.get("risk_score")
    score_valid = isinstance(score, int) and 0 <= score <= 10

    reasoning = output.get("reasoning")
    reasoning_nonempty = isinstance(reasoning, str) and len(reasoning.strip()) > 0

    # Internal consistency: severity tuong ung dung khoang risk_score
    severity_score_consistent = False
    if severity_valid and score_valid:
        expected_range = SEVERITY_SCORE_MAP.get(severity, (0, 10))
        severity_score_consistent = expected_range[0] <= score <= expected_range[1]

    schema_valid = all([has_all_fields, severity_valid, score_valid, reasoning_nonempty])

    return {
        "json_parseable": json_parseable,
        "has_all_fields": has_all_fields,
        "severity_valid": severity_valid,
        "score_valid": score_valid,
        "reasoning_nonempty": reasoning_nonempty,
        "severity_score_consistent": severity_score_consistent,
        "schema_valid": schema_valid,
    }


# ---------------------------------------------------------------------------
# 2. Faithfulness (rule-based heuristic)
# ---------------------------------------------------------------------------

# Hallucination patterns pho bien trong security context
_HALLUCINATION_PATTERNS = [
    r"\b\d{4}\b.*breach",           # "breach nam 2023" — bia su kien
    r"\$\s*\d+",                     # "$1 million" — bia so lieu tai chinh
    r"theo báo cáo|according to report",  # trich dan nguon khong co trong context
]

_CONTRADICTION_SIGNALS = {
    "critical": [
        "low risk", "minor issue", "low severity", "not significant",
        "rui ro thap", "khong nghiem trong", "rủi ro thấp", "không nghiêm trọng",
    ],
    "high": [
        "low risk", "minor issue", "low severity",
        "rui ro thap", "khong nghiem trong", "rủi ro thấp", "không nghiêm trọng",
    ],
    "low": [
        "critical", "severe", "high risk",
        "nghiem trong", "rui ro cao", "nghiêm trọng", "rủi ro cao",
    ],
}


# ---------------------------------------------------------------------------
# Claim-based Faithfulness (embedding verification)
# ---------------------------------------------------------------------------

def _split_claims(reasoning: str) -> List[str]:
    """Tach reasoning thanh cac claims (cau don).
    Claim decomposition step theo RAGAS framework."""
    if not reasoning:
        return []
    # Split theo dau cham, cham phay, xuong dong
    raw = re.split(r'[.;。\n]+', reasoning)
    claims = [c.strip() for c in raw if len(c.strip()) > 10]
    return claims


def _build_context_text(finding: Dict, rag_snapshot: Dict) -> str:
    """Gop finding description + RAG snapshot thanh 1 context string de verify."""
    parts = []
    if finding.get("description"):
        parts.append(finding["description"])
    if finding.get("event_code"):
        parts.append(f"Check: {finding['event_code']}")
    if finding.get("severity"):
        parts.append(f"Prowler severity: {finding['severity']}")
    if rag_snapshot.get("official_severity"):
        parts.append(f"Official severity: {rag_snapshot['official_severity']}")
    if rag_snapshot.get("check_title"):
        parts.append(f"Check title: {rag_snapshot['check_title']}")
    for m in rag_snapshot.get("compliance_mappings", []):
        parts.append(f"Compliance: {m}")
    return ". ".join(parts)



_VERIFY_PROMPT = """You are a fact-checker for AWS security findings.

CONTEXT (ground truth):
{context}

CLAIM to verify:
"{claim}"

Rules:
- "supported": the claim restates, paraphrases, or logically follows from the CONTEXT. Translation between Vietnamese and English counts as paraphrase.
- "not_supported": the claim introduces specific facts NOT in the CONTEXT (specific dates, dollar amounts, report names, breach events, statistics).

Answer ONLY: {{"verdict": "supported"}} or {{"verdict": "not_supported"}}"""


def _verify_claim_llm(claim: str, context_text: str, ollama_url: str, model: str) -> str:
    """Verify 1 claim bang LLM-as-Judge. Tra ve 'supported' hoac 'not_supported'."""
    import urllib.request
    import json as _json

    prompt = _VERIFY_PROMPT.format(context=context_text, claim=claim)
    payload = _json.dumps({
        "model": model, "prompt": prompt,
        "stream": False, "format": "json",
        "options": {"temperature": 0, "num_predict": 32},
    }).encode()
    req = urllib.request.Request(
        f"{ollama_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = _json.loads(resp.read())
        response_text = data.get("response", "").lower()
        parsed = _json.loads(response_text) if response_text.strip() else {}
        return parsed.get("verdict", "not_supported")
    except Exception as e:
        logger.warning("Claim verification failed: %s", e)
        return "not_supported"


def evaluate_faithfulness_claims(
    reasoning: str,
    finding: Dict,
    rag_snapshot: Dict,
    ollama_url: str = "http://localhost:11434",
    judge_model: str = "llama3.2:latest",
) -> Dict[str, Any]:
    """Claim-based faithfulness (LLM-as-Judge).

    Theo framework RAGAS (Es et al. 2023):
    1. Claim Decomposition: tach reasoning thanh cau don
    2. Verification: LLM judge kiem tra tung claim voi context
    3. Score = supported_claims / total_claims
    """
    if not reasoning:
        return {"score": 0.0, "claims": [], "method": "claim_llm_judge", "error": "empty reasoning"}

    claims = _split_claims(reasoning)
    if not claims:
        return {"score": 0.0, "claims": [], "method": "claim_llm_judge", "error": "no claims extracted"}

    context_text = _build_context_text(finding, rag_snapshot)
    if not context_text:
        return {"score": 0.0, "claims": claims, "method": "claim_llm_judge", "error": "empty context"}

    claim_results = []
    for claim in claims:
        verdict = _verify_claim_llm(claim, context_text, ollama_url, judge_model)
        supported = verdict == "supported"
        claim_results.append({"claim": claim, "verdict": verdict, "supported": supported})

    supported_count = sum(1 for c in claim_results if c["supported"])
    total = len(claim_results)
    score = supported_count / total if total > 0 else 0.0

    return {
        "score": round(score, 4),
        "supported": supported_count,
        "total": total,
        "claims": claim_results,
        "method": "claim_llm_judge",
        "judge_model": judge_model,
    }


def evaluate_faithfulness(
    reasoning: str,
    context: Dict[str, Any],
    finding: Optional[Dict] = None,
    ollama_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Faithfulness evaluation — chon method tuy theo available resources.

    - Neu co finding + ollama_url → claim-based (embedding verification)
    - Neu khong → rule-based heuristic (fallback)
    """
    # Claim-based: uu tien neu co du input
    if finding is not None and ollama_url:
        result = evaluate_faithfulness_claims(reasoning, finding, context, ollama_url)
        if result.get("error") is None:
            return result
        logger.info("Claim-based faithfulness failed (%s), falling back to rule-based",
                     result.get("error"))

    # Fallback: rule-based heuristic
    return _evaluate_faithfulness_rules(reasoning, context)


def _evaluate_faithfulness_rules(reasoning: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Faithfulness rule-based (fallback): kiem tra contradiction + hallucination patterns."""

    if not reasoning:
        return {"score": 0.0, "method": "rule_heuristic"}

    reasoning_lower = reasoning.lower()

    # 1. Kiem tra severity co mau thuan voi context khong
    official = context.get("official_severity", "").lower()
    severity_contradicted = False
    if official:
        for signal in _CONTRADICTION_SIGNALS.get(official, []):
            if signal in reasoning_lower:
                severity_contradicted = True
                break

    # 2. Kiem tra hallucination patterns
    hallucination_found = []
    for pattern in _HALLUCINATION_PATTERNS:
        if re.search(pattern, reasoning_lower):
            hallucination_found.append(pattern)

    # Score: bat dau tu 1.0, tru diem cho moi van de
    issues = int(severity_contradicted) + min(len(hallucination_found), 1)
    score = max(0.0, 1.0 - issues * 0.5)

    return {
        "score": round(score, 4),
        "severity_contradicted": severity_contradicted,
        "hallucination_patterns_found": hallucination_found,
        "method": "rule_heuristic",
    }


# ---------------------------------------------------------------------------
# 3. Correctness (severity accuracy + QWK)
# ---------------------------------------------------------------------------

def evaluate_risk_correctness(
    predicted_severity: Optional[str],
    expected_severity: str,
    predicted_score: Any = None,
    expected_score_range: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Correctness cho 1 Risk Agent case."""

    # Guard: predicted co the None neu agent fail
    if predicted_severity not in VALID_SEVERITIES:
        return {
            "severity_match": False,
            "severity_adjacent": False,
            "predicted_severity": predicted_severity,
            "expected_severity": expected_severity,
            "score_in_range": None,
            "error": f"invalid predicted severity: {predicted_severity}",
        }

    exact_match = predicted_severity == expected_severity
    pred_idx = SEVERITY_ORDER.index(predicted_severity)
    exp_idx = SEVERITY_ORDER.index(expected_severity)
    adjacent_match = abs(pred_idx - exp_idx) <= 1

    score_in_range = None
    if expected_score_range and isinstance(predicted_score, int):
        score_in_range = expected_score_range[0] <= predicted_score <= expected_score_range[1]

    return {
        "severity_match": exact_match,
        "severity_adjacent": adjacent_match,
        "predicted_severity": predicted_severity,
        "expected_severity": expected_severity,
        "score_in_range": score_in_range,
    }


def compute_accuracy(evaluated_cases: List[Dict]) -> float:
    """Tinh severity accuracy tong the."""
    if not evaluated_cases:
        return 0.0
    correct = sum(1 for c in evaluated_cases if c["correctness"]["severity_match"])
    return round(correct / len(evaluated_cases), 4)


def compute_qwk(evaluated_cases: List[Dict]) -> float:
    """Tinh Quadratic Weighted Kappa. Bo qua cases co predicted severity khong hop le."""
    valid = [
        c for c in evaluated_cases
        if c["correctness"].get("predicted_severity") in VALID_SEVERITIES
           and c["correctness"].get("expected_severity") in VALID_SEVERITIES
    ]

    if len(valid) < 2:
        return 0.0  # QWK can it nhat 2 samples

    y_true = [SEVERITY_ORDER.index(c["correctness"]["expected_severity"]) for c in valid]
    y_pred = [SEVERITY_ORDER.index(c["correctness"]["predicted_severity"]) for c in valid]

    try:
        from sklearn.metrics import cohen_kappa_score
        return round(cohen_kappa_score(y_true, y_pred, weights="quadratic"), 4)
    except ImportError:
        # Fallback: simple accuracy neu khong co sklearn
        correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
        return round(correct / len(valid), 4)


# ---------------------------------------------------------------------------
# 4. Completeness (evidence checklist)
# ---------------------------------------------------------------------------

def _strip_diacritics(text: str) -> str:
    """Xoa dau tieng Viet: ma hoa <- ma hoa, cong khai <- cong khai, duong <- duong.
    Giup keyword matching khong bi miss do agent viet co dau."""
    text = text.replace("\u0111", "d").replace("\u0110", "D")  # d/D
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def evaluate_completeness(reasoning: str, required_evidence: List[str]) -> Dict[str, Any]:
    """Completeness bang evidence checklist matching.

    Completeness tra loi: 'Agent co noi du thong tin khong?'
    (khac voi Faithfulness: 'Agent co bia dat gi khong?')

    Moi evidence item co the chua nhieu keywords cach boi ' hoac '.
    Vi du: 'encryption hoac ma hoa' -> match neu co 'encryption' HOAC 'ma hoa'.

    Matching duoc normalize: lowercase + strip Vietnamese diacritics,
    nen 'ma hoa' match ca 'ma hoa' lan 'mã hóa'.
    """

    if not required_evidence:
        return {"score": 1.0, "covered": 0, "total": 0, "details": []}

    # Normalize reasoning: lowercase + strip diacritics
    reasoning_norm = _strip_diacritics(reasoning.lower()) if reasoning else ""
    details = []

    for evidence in required_evidence:
        # Parse 'hoac' / 'or' separator
        alternatives = re.split(r"\s+hoac\s+|\s+or\s+", evidence.lower())
        alts_clean = [_strip_diacritics(a.strip()) for a in alternatives if a.strip()]

        found = any(alt in reasoning_norm for alt in alts_clean)

        details.append({
            "evidence": evidence,
            "found": found,
            "alternatives_checked": alts_clean,
        })

    covered = sum(1 for d in details if d["found"])
    total = len(details)

    return {
        "score": round(covered / total, 4) if total > 0 else 1.0,
        "covered": covered,
        "total": total,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Aggregate helpers
# ---------------------------------------------------------------------------

def mean_of(cases: List[Dict], section: str, field: str) -> float:
    """Tinh trung binh 1 field tu evaluated cases. Xu ly bool -> int."""
    values = []
    for c in cases:
        v = c.get(section, {}).get(field)
        if isinstance(v, bool):
            v = int(v)
        if v is not None:
            values.append(v)
    return round(sum(values) / len(values), 4) if values else 0.0


def check_release_criteria(summary: Dict, criteria: Dict) -> Dict[str, Any]:
    """Kiem tra summary co dat release criteria khong.

    criteria format: {"metric_path_min": 0.7, "metric_path_max": 5.0}
    Suffix _min -> actual >= threshold. Suffix _max -> actual <= threshold.
    """

    # Map criteria key -> actual value path in summary
    METRIC_MAP = {
        "json_parse_rate_min": ("structure", "json_parse_rate"),
        "schema_compliance_rate_min": ("structure", "schema_compliance_rate"),
        "faithfulness_mean_min": ("faithfulness", "mean"),
        "severity_accuracy_min": ("correctness", "severity_accuracy"),
        "severity_qwk_min": ("correctness", "severity_qwk"),
        "evidence_completeness_mean_min": ("completeness", "evidence_coverage_mean"),
    }

    checks = []
    all_passed = True

    for criterion, threshold in criteria.items():
        if criterion.startswith("_"):
            continue  # skip comments

        path = METRIC_MAP.get(criterion)
        if not path:
            continue

        section, field = path
        actual = summary.get(section, {}).get(field, 0.0)

        if criterion.endswith("_min"):
            passed = actual >= threshold
        elif criterion.endswith("_max"):
            passed = actual <= threshold
        else:
            passed = actual >= threshold

        if not passed:
            all_passed = False

        checks.append({
            "criterion": criterion,
            "threshold": threshold,
            "actual": actual,
            "passed": passed,
        })

    return {
        "verdict": "PASS" if all_passed else "FAIL",
        "checks": checks,
    }
