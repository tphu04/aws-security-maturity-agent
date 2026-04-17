"""
Planning Agent generation benchmark metrics.

4 core metrics (black-box evaluation):
- Structure: valid_output_rate (deterministic, chi phi = 0)
- Faithfulness: grounded_reasoning_rate (keyword-based, chi LLM-reasoning cases)
- Correctness: check_selection_f1 + service_accuracy + planning_correctness (composite)
- Completeness: check_selection_recall + action_type_accuracy

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

# Prowler check ID validation (mirrors planning_agent._extract_check_ids)
# Full Prowler service prefixes — extracted from RAG/data/raw/prowler_checks.json (577 checks, 82 prefixes)
_KNOWN_SERVICE_PREFIXES = (
    "accessanalyzer_", "account_", "acm_", "apigateway_", "apigatewayv2_",
    "appstream_", "appsync_", "athena_", "autoscaling_", "awslambda_",
    "backup_", "bedrock_",
    "cloudformation_", "cloudfront_", "cloudtrail_", "cloudwatch_",
    "codeartifact_", "codebuild_", "cognito_", "config_",
    "datasync_", "directconnect_", "directoryservice_", "dlm_", "dms_",
    "documentdb_", "drs_", "dynamodb_",
    "ec2_", "ecr_", "ecs_", "efs_", "eks_", "elasticache_",
    "elasticbeanstalk_", "elb_", "elbv2_", "emr_", "eventbridge_",
    "firehose_", "fms_", "fsx_",
    "glacier_", "glue_", "guardduty_",
    "iam_", "inspector2_",
    "kafka_", "kinesis_", "kms_",
    "lambda_", "lightsail_",
    "macie_", "memorydb_", "mq_",
    "neptune_", "networkfirewall_",
    "opensearch_", "organizations_",
    "rds_", "redshift_", "resourceexplorer2_", "route53_",
    "s3_", "sagemaker_", "secretsmanager_", "securityhub_",
    "servicecatalog_", "ses_", "shield_", "sns_", "sqs_", "ssm_",
    "ssmincidents_", "stepfunctions_", "storagegateway_",
    "transfer_", "trustedadvisor_",
    "vpc_", "waf_", "wafv2_", "wellarchitected_", "workspaces_",
)

ALLOWED_GROUPS = {
    "s3", "iam", "ec2", "rds", "cloudtrail", "eks", "vpc", "lambda", "kms",
}

# Correctness composite weights
W_SPECIFIC = 0.7
W_GROUP = 0.3


# ---------------------------------------------------------------------------
# 1. Structure — Valid Output Rate
# ---------------------------------------------------------------------------

def evaluate_structure(output: Dict[str, Any]) -> Dict[str, Any]:
    """Danh gia cau truc output cua Planning Agent.

    Gop kiem tra: schema valid, mutual exclusivity, reasoning nonempty,
    check ID format thanh 1 valid_output boolean duy nhat.
    """
    if not isinstance(output, dict):
        return {
            "valid_output": False,
            "schema_valid": False,
            "mutual_exclusivity": False,
            "reasoning_nonempty": False,
            "check_ids_valid": True,
            "issues": ["output is not a dict"],
        }

    issues = []

    # Schema: phai co groups_to_scan va checks_to_scan (lists)
    groups = output.get("groups_to_scan")
    checks = output.get("checks_to_scan")
    has_error = "error" in output

    schema_valid = (
        isinstance(groups, list)
        and isinstance(checks, list)
    )
    if not schema_valid:
        issues.append("missing or invalid groups_to_scan/checks_to_scan")

    # Mutual exclusivity: khong duoc ca 2 non-empty
    mutual_exclusivity = True
    if schema_valid and groups and checks:
        mutual_exclusivity = False
        issues.append("both groups_to_scan and checks_to_scan are non-empty")

    # Reasoning nonempty (tru error output)
    reasoning = output.get("reasoning", "")
    reasoning_nonempty = True
    if not has_error:
        reasoning_nonempty = isinstance(reasoning, str) and len(reasoning.strip()) > 0
        if not reasoning_nonempty:
            issues.append("reasoning is empty (non-error output)")

    # Check ID format validation (chi khi co checks)
    check_ids_valid = True
    if schema_valid and checks:
        for cid in checks:
            if not _is_valid_check_id(cid):
                check_ids_valid = False
                issues.append(f"invalid check_id format: {cid}")
                break  # 1 loi la du

    valid_output = all([schema_valid, mutual_exclusivity, reasoning_nonempty, check_ids_valid])

    return {
        "valid_output": valid_output,
        "schema_valid": schema_valid,
        "mutual_exclusivity": mutual_exclusivity,
        "reasoning_nonempty": reasoning_nonempty,
        "check_ids_valid": check_ids_valid,
        "issues": issues,
    }


def _is_valid_check_id(check_id: str) -> bool:
    """Validate Prowler check ID format."""
    if not isinstance(check_id, str):
        return False
    if len(check_id) < 12:
        return False
    parts = check_id.split("_")
    if len(parts) < 3:
        return False
    if not any(check_id.startswith(p) for p in _KNOWN_SERVICE_PREFIXES):
        return False
    return True


# ---------------------------------------------------------------------------
# 2. Faithfulness — Grounded Reasoning Rate
# ---------------------------------------------------------------------------

def _strip_diacritics(text: str) -> str:
    """Xoa dau tieng Viet de keyword matching khong miss."""
    text = text.replace("\u0111", "d").replace("\u0110", "D")
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def evaluate_faithfulness(
    reasoning: str,
    rag_context: Dict[str, Any],
    selected_checks: List[str],
) -> Dict[str, Any]:
    """Faithfulness evaluation — keyword grounding + negative checks.

    Scoring (0.0 - 1.0):
      Base: 1.0 neu co evidence tu context, 0.0 neu khong
      Penalties (tru diem cho moi violation):
        -0.3  check_id_fabrication: reasoning nhac check ID khong co trong RAG candidates
        -0.3  output_reasoning_mismatch: reasoning noi "no relevant" nhung output co checks (hoac nguoc lai)
        -0.2  phantom_reference: reasoning trich dan nguon khong co trong context (framework, report, standard)

    Hardcoded reasoning (FAST_TRACK, GROUP_SCAN, Deterministic) → auto score 1.0.
    """
    if not reasoning:
        return {"score": 0.0, "grounded": False, "evidence_found": [],
                "penalties": [], "method": "keyword"}

    reasoning_norm = _strip_diacritics(reasoning.lower())

    # Detect hardcoded reasoning (khong can do faithfulness)
    hardcoded_patterns = [
        "explicit check ids detected",
        "group scan requested",
        "deterministic selection",
    ]
    for pattern in hardcoded_patterns:
        if pattern in reasoning_norm:
            return {
                "score": 1.0,
                "grounded": True,
                "evidence_found": ["hardcoded_reasoning"],
                "penalties": [],
                "method": "hardcoded_skip",
            }

    # ---------------------------------------------------------------
    # Positive check: reasoning chua evidence tu context?
    # ---------------------------------------------------------------
    evidence_pool = set()

    for cid in selected_checks:
        evidence_pool.add(cid.lower())
        parts = cid.lower().split("_")
        if len(parts) >= 3:
            evidence_pool.add("_".join(parts[1:]))

    rag_check_ids = set()
    for finding in rag_context.get("related_findings", []):
        if finding.get("check_id"):
            cid_low = finding["check_id"].lower()
            evidence_pool.add(cid_low)
            rag_check_ids.add(cid_low)
        if finding.get("service"):
            evidence_pool.add(finding["service"].lower())
        if finding.get("severity"):
            evidence_pool.add(finding["severity"].lower())

    for mapping in rag_context.get("control_mapping_ids", []):
        evidence_pool.add(mapping.lower())
    for cap in rag_context.get("maturity_capability_ids", []):
        evidence_pool.add(cap.lower())

    evidence_found = []
    for ev in evidence_pool:
        ev_norm = _strip_diacritics(ev)
        if ev_norm and len(ev_norm) >= 2 and ev_norm in reasoning_norm:
            evidence_found.append(ev)

    grounded = len(evidence_found) > 0

    # ---------------------------------------------------------------
    # Negative checks: penalties
    # ---------------------------------------------------------------
    penalties = []

    # N1: Check ID fabrication — reasoning nhac check_id khong co trong RAG candidates
    check_id_pattern = re.compile(r'\b([a-z][a-z0-9]*(?:_[a-z0-9]+){2,})\b')
    mentioned_ids = set(check_id_pattern.findall(reasoning_norm))
    if mentioned_ids and rag_check_ids:
        fabricated = mentioned_ids - rag_check_ids - set(c.lower() for c in selected_checks)
        # Filter: chi tinh fabricated neu trong nhu Prowler check ID (>=12 chars, known prefix)
        fabricated = {cid for cid in fabricated if _is_valid_check_id(cid)}
        if fabricated:
            penalties.append({
                "type": "check_id_fabrication",
                "severity": 0.3,
                "detail": f"Reasoning mentions check IDs not in RAG candidates: {list(fabricated)[:3]}",
            })

    # N2: Output-reasoning mismatch
    no_result_phrases = [
        "no relevant", "no suitable", "cannot determine", "none of the candidates",
        "khong tim thay", "khong co ket qua", "khong phu hop",
    ]
    reasoning_says_no_result = any(p in reasoning_norm for p in no_result_phrases)
    output_has_checks = len(selected_checks) > 0

    if reasoning_says_no_result and output_has_checks:
        penalties.append({
            "type": "output_reasoning_mismatch",
            "severity": 0.3,
            "detail": "Reasoning says 'no relevant checks' but output contains checks",
        })
    elif not reasoning_says_no_result and not output_has_checks and reasoning_norm:
        # Reasoning giai thich binh thuong nhung output rong
        # Chi penalty neu reasoning ko noi ve error/failure
        error_phrases = ["fail", "error", "could not", "unable"]
        if not any(p in reasoning_norm for p in error_phrases):
            penalties.append({
                "type": "output_reasoning_mismatch",
                "severity": 0.3,
                "detail": "Reasoning provides explanation but output is empty (no error)",
            })

    # N3: Phantom reference — trich dan framework/report/standard khong co trong context
    phantom_patterns = [
        r"theo\s+(?:bao cao|report|gartner|forrester|nist|owasp)",
        r"according to\s+(?:report|survey|study|gartner|forrester)",
        r"(?:breach|incident|attack).*\b\d{4}\b|\b\d{4}\b.*(?:breach|incident|attack)",  # "breach 2023" or "2023 breach"
        r"\$\s*\d+",  # "$1 million"
    ]
    for pattern in phantom_patterns:
        if re.search(pattern, reasoning_norm):
            penalties.append({
                "type": "phantom_reference",
                "severity": 0.2,
                "detail": f"Reasoning contains unverifiable reference matching: {pattern}",
            })
            break  # 1 phantom la du

    # ---------------------------------------------------------------
    # Final score
    # ---------------------------------------------------------------
    base_score = 1.0 if grounded else 0.0
    total_penalty = sum(p["severity"] for p in penalties)
    score = max(0.0, base_score - total_penalty)

    return {
        "score": round(score, 4),
        "grounded": grounded,
        "evidence_found": evidence_found[:5],
        "evidence_pool_size": len(evidence_pool),
        "penalties": penalties,
        "method": "keyword_with_negative_checks",
    }


# ---------------------------------------------------------------------------
# 3. Correctness — F1 + Service Accuracy + Planning Correctness
# ---------------------------------------------------------------------------

def evaluate_check_selection(
    predicted_checks: List[str],
    relevant_checks: List[str],
    also_acceptable: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Check Selection F1 (khi agent tra specific checks).

    Precision: trong cac checks agent chon, bao nhieu la dung?
      - Checks trong ``also_acceptable`` cung duoc tinh la dung (khong phat FP).
    Recall: trong cac checks **bat buoc** (relevant_checks), agent tim duoc bao nhieu?
      - ``also_acceptable`` KHONG anh huong recall (chung la optional).
    F1: harmonic mean.
    """
    if not relevant_checks:
        # Khong co ground truth → khong the tinh F1
        return {
            "precision": None,
            "recall": None,
            "f1": None,
            "true_positives": 0,
            "false_positives": len(predicted_checks),
            "false_negatives": 0,
            "error": "no_ground_truth",
        }

    pred_set = set(c.lower() for c in predicted_checks)
    rel_set = set(c.lower() for c in relevant_checks)
    also_set = set(c.lower() for c in (also_acceptable or []))
    accepted_set = rel_set | also_set  # Tat ca checks hop le

    tp = len(pred_set & accepted_set)         # Dung: nam trong relevant HOAC also
    fp = len(pred_set - accepted_set)         # Sai: khong nam trong bat ky set nao
    fn = len(rel_set - pred_set)              # Thieu: chi tinh voi relevant (bat buoc)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
    }


def evaluate_over_selection_rate(
    predicted_checks: List[str],
    relevant_checks: List[str],
    also_acceptable: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Over-selection rate: model chon du bao nhieu check.

    over_selection_rate = FP / |predicted|
    ``also_acceptable`` checks khong bi tinh la FP.
    """
    if not relevant_checks:
        return {
            "over_selection_rate": None,
            "false_positives": len(predicted_checks),
            "total_predicted": len(predicted_checks),
            "error": "no_ground_truth",
        }

    pred_set = set(c.lower() for c in predicted_checks)
    rel_set = set(c.lower() for c in relevant_checks)
    also_set = set(c.lower() for c in (also_acceptable or []))
    accepted_set = rel_set | also_set

    fp = len(pred_set - accepted_set)
    total_pred = len(pred_set)

    rate = fp / total_pred if total_pred > 0 else 0.0

    return {
        "over_selection_rate": round(rate, 4),
        "false_positives": fp,
        "total_predicted": total_pred,
    }


def evaluate_under_selection_rate(
    predicted_checks: List[str],
    relevant_checks: List[str],
) -> Dict[str, Any]:
    """Under-selection rate: model bo sot bao nhieu check quan trong.

    under_selection_rate = FN / |relevant|
    Lien quan truc tiep den risk he thong.
    """
    if not relevant_checks:
        return {
            "under_selection_rate": None,
            "false_negatives": 0,
            "total_relevant": 0,
            "error": "no_ground_truth",
        }

    pred_set = set(c.lower() for c in predicted_checks)
    rel_set = set(c.lower() for c in relevant_checks)

    fn = len(rel_set - pred_set)
    total_rel = len(rel_set)

    rate = fn / total_rel if total_rel > 0 else 0.0

    return {
        "under_selection_rate": round(rate, 4),
        "false_negatives": fn,
        "total_relevant": total_rel,
    }


def evaluate_exact_match(
    predicted_checks: List[str],
    relevant_checks: List[str],
) -> Dict[str, Any]:
    """Exact Match: predicted set == relevant set hoan toan.

    Binary (0 or 1). % case chon dung hoan toan.
    """
    if not relevant_checks:
        return {
            "exact_match": None,
            "error": "no_ground_truth",
        }

    pred_set = set(c.lower() for c in predicted_checks)
    rel_set = set(c.lower() for c in relevant_checks)

    return {
        "exact_match": pred_set == rel_set,
    }


def evaluate_service_accuracy(
    predicted_groups: List[str],
    expected_service: str,
) -> Dict[str, Any]:
    """Service Accuracy (khi agent tra group scan).

    Binary: agent chon dung service mong doi khong?
    """
    if not predicted_groups:
        return {
            "correct": False,
            "predicted_service": None,
            "expected_service": expected_service,
        }

    predicted = predicted_groups[0].lower()
    correct = predicted == expected_service.lower()

    return {
        "correct": correct,
        "predicted_service": predicted,
        "expected_service": expected_service,
    }


def evaluate_planning_correctness(
    output: Dict[str, Any],
    expected: Dict[str, Any],
) -> Dict[str, Any]:
    """Correctness tong hop cho 1 Planning Agent case.

    Tra ve F1 (khi specific checks), service_accuracy (khi group scan),
    hoac 0 (khi error output).
    """
    groups = output.get("groups_to_scan", [])
    checks = output.get("checks_to_scan", [])
    has_error = "error" in output
    relevant = expected.get("relevant_checks", [])
    also_acceptable = expected.get("also_acceptable", [])
    expected_service = expected.get("expected_service", "")
    acceptable_type = expected.get("acceptable_output_type", "")

    # Error output → correctness = 0
    if has_error and not groups and not checks:
        return {
            "output_type": "error",
            "f1": 0.0,
            "service_correct": None,
            "check_selection": None,
            "service_eval": None,
        }

    # Specific checks output
    if checks and not groups:
        check_result = evaluate_check_selection(checks, relevant, also_acceptable)
        return {
            "output_type": "specific_checks",
            "f1": check_result["f1"],
            "service_correct": None,
            "check_selection": check_result,
            "service_eval": None,
        }

    # Group scan output
    if groups and not checks:
        svc_result = evaluate_service_accuracy(groups, expected_service)
        return {
            "output_type": "group_scan",
            "f1": None,
            "service_correct": svc_result["correct"],
            "check_selection": None,
            "service_eval": svc_result,
        }

    # Unexpected: both empty but no error
    return {
        "output_type": "empty",
        "f1": 0.0,
        "service_correct": None,
        "check_selection": None,
        "service_eval": None,
    }


def evaluate_action_type(
    output: Dict[str, Any],
    expected: Dict[str, Any],
) -> Dict[str, Any]:
    """Action Type Accuracy — agent chon dung loai hanh dong khong?

    specific_checks khi can specific, group_scan khi can group.
    "either" chap nhan ca 2.
    """
    groups = output.get("groups_to_scan", [])
    checks = output.get("checks_to_scan", [])
    acceptable = expected.get("acceptable_output_type", "")

    if checks and not groups:
        actual_type = "specific_checks"
    elif groups and not checks:
        actual_type = "group_scan"
    elif "error" in output:
        actual_type = "error"
    else:
        actual_type = "empty"

    if acceptable == "either":
        correct = actual_type in ("specific_checks", "group_scan")
    elif acceptable == "error":
        correct = actual_type == "error"
    elif acceptable == "specific_checks":
        correct = actual_type == "specific_checks"
    elif acceptable == "group_scan":
        correct = actual_type == "group_scan"
    else:
        correct = False

    return {
        "correct": correct,
        "actual_type": actual_type,
        "acceptable_type": acceptable,
    }


# ---------------------------------------------------------------------------
# Aggregate helpers
# ---------------------------------------------------------------------------

def mean_of(cases: List[Dict], section: str, field: str) -> float:
    """Tinh trung binh 1 field tu evaluated cases. Bool -> int."""
    values = []
    for c in cases:
        v = c.get(section, {}).get(field)
        if isinstance(v, bool):
            v = int(v)
        if v is not None:
            values.append(v)
    return round(sum(values) / len(values), 4) if values else 0.0


def compute_planning_correctness(
    f1_cases: List[Dict],
    svc_cases: List[Dict],
) -> float:
    """Planning Correctness composite: 0.7 * F1_mean + 0.3 * service_accuracy.

    f1_cases: cases co output_type = specific_checks
    svc_cases: cases co output_type = group_scan
    """
    f1_values = [c["correctness"]["f1"] for c in f1_cases if c["correctness"].get("f1") is not None]
    svc_values = [int(c["correctness"]["service_correct"]) for c in svc_cases if c["correctness"].get("service_correct") is not None]

    f1_mean = sum(f1_values) / len(f1_values) if f1_values else 0.0
    svc_mean = sum(svc_values) / len(svc_values) if svc_values else 0.0

    # Adjust weights nếu 1 loại không có cases
    if not f1_values and not svc_values:
        return 0.0
    if not f1_values:
        return svc_mean
    if not svc_values:
        return f1_mean

    return round(W_SPECIFIC * f1_mean + W_GROUP * svc_mean, 4)


def check_release_criteria(summary: Dict, criteria: Dict) -> Dict[str, Any]:
    """Kiem tra summary co dat release criteria khong."""

    METRIC_MAP = {
        "valid_output_rate_min": ("structure", "valid_output_rate"),
        "grounded_reasoning_rate_min": ("faithfulness", "grounded_reasoning_rate"),
        "check_selection_f1_min": ("correctness", "check_selection_f1"),
        "service_accuracy_min": ("correctness", "service_accuracy"),
        "planning_correctness_min": ("correctness", "planning_correctness"),
        "action_type_accuracy_min": ("completeness", "action_type_accuracy"),
        "over_selection_rate_max": ("correctness", "over_selection_rate"),
        "under_selection_rate_max": ("correctness", "under_selection_rate"),
        "exact_match_rate_min": ("correctness", "exact_match_rate"),
    }

    checks = []
    all_passed = True

    for criterion, threshold in criteria.items():
        if criterion.startswith("_"):
            continue

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
            "actual": round(actual, 4),
            "passed": passed,
        })

    return {
        "verdict": "PASS" if all_passed else "FAIL",
        "checks": checks,
    }
