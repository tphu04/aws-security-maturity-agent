"""Redaction helpers for Langfuse payloads.

The default mode is intentionally conservative. It may mask benign 12-digit
numbers as AWS account IDs; that false positive is acceptable for observability
payloads because leaking account identifiers is worse than losing detail.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Mapping, MutableMapping, Optional

from pdca.config import settings

_AWS_ACCESS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_AWS_SECRET_RE = re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])")
_ACCOUNT_ID_RE = re.compile(r"\b(\d{12})\b")
_ARN_RE = re.compile(r"\barn:aws(?P<partition>[-\w]*):(?P<service>[^:\s]+):(?P<region>[^:\s]*):(?P<account>\d{12})(?P<rest>:[^\s,;'\"}\]]*)")
_S3_URI_RE = re.compile(r"\bs3://(?P<bucket>[a-z0-9][a-z0-9.-]{1,61}[a-z0-9])\b")
_BUCKET_LIKE_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_MIN_BUCKET_LEN = 6

_DEFAULT_SENSITIVE_KEYS = (
    "aws_access_key_id",
    "aws_secret_access_key",
    "aws_session_token",
    "secret",
    "secret_key",
    "access_key",
    "password",
    "token",
)


def _hash_bucket(name: str) -> str:
    return f"bkt-{hashlib.sha256(name.encode('utf-8')).hexdigest()[:8]}"


def _looks_like_bucket(value: str) -> bool:
    if len(value) < _MIN_BUCKET_LEN:
        return False
    if _UUID_RE.match(value):
        return False
    if not _BUCKET_LIKE_RE.match(value):
        return False
    return "." in value or "-" in value


def _is_sensitive_key(key: Any, sensitive_keys: Iterable[str]) -> bool:
    key_s = str(key).lower()
    return any(pattern in key_s for pattern in sensitive_keys)


def redact_dict_keys(
    d: Mapping[str, Any],
    sensitive_keys: Iterable[str] = _DEFAULT_SENSITIVE_KEYS,
) -> dict[str, Any]:
    """Replace sensitive dictionary values before recursive redaction."""
    return {
        key: "<REDACTED-CREDENTIAL>" if _is_sensitive_key(key, sensitive_keys) else value
        for key, value in d.items()
    }


def _redact_string(value: str, mode: str) -> str:
    redacted = _AWS_ACCESS_KEY_RE.sub("<REDACTED-CREDENTIAL>", value)
    redacted = _AWS_SECRET_RE.sub("<REDACTED-CREDENTIAL>", redacted)

    if mode in {"internal", "off"}:
        return redacted

    def _arn_sub(m: re.Match[str]) -> str:
        rest = m.group("rest")
        service = m.group("service")
        if service == "s3" and rest.startswith(":"):
            segments = rest[1:].split("/")
            rest = ":" + "/".join(
                _hash_bucket(seg) if _looks_like_bucket(seg) else seg
                for seg in segments
            )
        return (
            f"arn:aws{m.group('partition')}:{service}:"
            f"{m.group('region')}:***{m.group('account')[-4:]}{rest}"
        )

    redacted = _ARN_RE.sub(_arn_sub, redacted)
    redacted = _ACCOUNT_ID_RE.sub(lambda m: f"***{m.group(1)[-4:]}", redacted)
    redacted = _S3_URI_RE.sub(lambda m: f"s3://{_hash_bucket(m.group('bucket'))}", redacted)

    if _looks_like_bucket(redacted):
        return _hash_bucket(redacted)
    return redacted


def redact(value: Any, mode: Optional[str] = None, _seen: Optional[set[int]] = None) -> Any:
    """Recursively redact strings, dicts, and lists before exporting telemetry."""
    selected_mode = mode or settings.langfuse_redact_mode
    if selected_mode not in {"full", "internal", "off"}:
        selected_mode = "full"

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _redact_string(value, selected_mode)

    seen = _seen if _seen is not None else set()
    obj_id = id(value)
    if obj_id in seen:
        raise ValueError("circular reference during redaction")
    seen.add(obj_id)

    if isinstance(value, Mapping):
        cleaned: MutableMapping[Any, Any] = redact_dict_keys(value)
        return {
            key: redact(item, selected_mode, seen)
            for key, item in cleaned.items()
        }
    if isinstance(value, list):
        return [redact(item, selected_mode, seen) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item, selected_mode, seen) for item in value)

    return value


def safe_redact(value: Any, mode: Optional[str] = None) -> Any:
    """Best-effort wrapper used at SDK boundaries."""
    try:
        return redact(value, mode=mode)
    except Exception:
        return "<redaction-error>"


__all__ = ["redact", "redact_dict_keys", "safe_redact"]
