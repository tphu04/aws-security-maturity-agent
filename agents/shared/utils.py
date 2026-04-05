"""
Shared Utilities cho Agent System
==================================
Module chứa các functions dùng chung giữa PlanningAgent và RiskEvaluationAgent,
loại bỏ code duplicate và chuẩn hóa data flow.

Tham chiếu: Integration_Implementation_Plan.md — SLICE-RS-1
Issues: PA-04, RA-01, RA-02

Functions:
    extract_check_id  — Trích xuất Prowler check ID từ normalized finding
    parse_llm_json    — Parse JSON từ LLM output (robust, merge best logic)
    sanitize_check_id — Loại bỏ prefix/suffix rác khỏi check ID
"""

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def extract_check_id(finding: Dict[str, Any]) -> Optional[str]:
    """
    Trích xuất Prowler check ID từ một finding dict đã normalized.

    Ưu tiên (priority chain):
        1. finding["event_code"]  ← Normalizer đã extract sẵn (agents/shared/normalizer.py:38)
        2. finding["check_id"]    ← Tên field phổ biến
        3. Regex fallback từ finding_id/uid/id

    Args:
        finding: Dict chứa thông tin finding (output của Normalizer hoặc raw).

    Returns:
        Check ID string (e.g. "s3_bucket_public_access") hoặc None nếu không tìm được.
    """
    if not isinstance(finding, dict):
        return None

    # Priority 1: event_code (Normalizer đã extract — best source)
    event_code = finding.get("event_code")
    if event_code and isinstance(event_code, str) and event_code.strip():
        return event_code.strip()

    # Priority 2: check_id (common field name, case variations)
    for key in ("check_id", "CheckID", "checkId"):
        val = finding.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()

    # Priority 3: Regex fallback from finding_id / uid / id
    raw_str = (
        finding.get("finding_id")
        or finding.get("uid")
        or finding.get("id")
        or ""
    )
    if not raw_str:
        return None

    raw_str = str(raw_str)

    # Pattern: prowler-aws-s3_account_level_public_access_blocks-123456...
    match = re.search(r"prowler-[^-]+-([a-z0-9_]+)-\d+", raw_str)
    if match:
        return match.group(1)

    # Fallback: any underscore-separated identifier (min 2 segments)
    fallback_match = re.search(r"\b([a-z0-9]+_[a-z0-9_]+)\b", raw_str)
    if fallback_match:
        return fallback_match.group(1)

    return None


def parse_llm_json(text: str) -> Dict[str, Any]:
    """
    Parse JSON từ LLM output text — robust, không raise exception.

    Merge logic tốt nhất từ PlanningAgent._clean_json() và
    RiskEvaluationAgent._extract_json_from_text():
        1. Try ```json ... ``` block (markdown code block)
        2. Try regex {.*} (greedy, dotall)
        3. Remove control characters rồi try lại
        4. Return {} nếu tất cả fail

    Args:
        text: Raw text output từ LLM.

    Returns:
        Parsed dict, hoặc {} nếu parse thất bại.
    """
    if not text or not isinstance(text, str):
        return {}

    text = text.strip()

    # Step 1: Try ```json ... ``` block
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    # Step 2: Try regex {.*} (greedy, dotall)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            # Step 3: Remove control characters and retry
            cleaned = re.sub(r"[\x00-\x1F\x7F]", "", json_str)
            try:
                return json.loads(cleaned)
            except (json.JSONDecodeError, ValueError):
                pass

    # Step 4: Try parsing raw text as-is
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    logger.warning("parse_llm_json: failed to parse LLM output (length=%d)", len(text))
    return {}


def sanitize_check_id(raw_id: str) -> str:
    """
    Loại bỏ prefix và suffix rác khỏi check ID để trả về Prowler Check ID chuẩn.

    Xử lý:
        - Prefix: "check:", "capability:"
        - Suffix: "_overview", "_risk", "_recommendation", "_remediation"

    Args:
        raw_id: Raw check ID string (e.g. "check:s3_bucket_public_access_overview").

    Returns:
        Clean check ID (e.g. "s3_bucket_public_access").
        Trả về empty string nếu input invalid.
    """
    if not raw_id or not isinstance(raw_id, str):
        return ""

    clean_id = raw_id.strip()

    # Remove prefixes
    for prefix in ("check:", "capability:"):
        if clean_id.startswith(prefix):
            clean_id = clean_id[len(prefix):]
            break

    # Remove suffixes
    for suffix in ("_overview", "_risk", "_recommendation", "_remediation"):
        if clean_id.endswith(suffix):
            clean_id = clean_id[: -len(suffix)]
            break

    return clean_id
