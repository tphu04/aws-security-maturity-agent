"""Shared helpers cho tool layer — chuẩn hóa result + sanitize input (B15).

Invariant (decision #35):
- Mọi @tool LUÔN return `dict`. Không bao giờ `json.dumps()`, không bao giờ
  raise ra ngoài tool boundary.
- `sanitize_s3_bucket_name()` raise `ValueError` nếu bucket invalid; tool wrap
  trong try/except và convert sang `ToolResult.failed(...)`.

NOTE: `sanitize_s3_bucket_name` là S3-specific (regex theo S3 spec). Khi thêm
services khác (IAM, EC2, RDS), thêm sanitizer riêng — KHÔNG generic hóa.
"""

from __future__ import annotations

import re
from typing import Any

# S3 bucket naming rules: 3-63 chars, lowercase alpha-numeric / dash / dot,
# bắt đầu+kết thúc bằng alpha-numeric (RFC: aws docs s3 bucket-naming-rules).
_S3_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$")


def sanitize_s3_bucket_name(raw: str) -> str:
    """Strip ARN prefix + whitespace, validate against S3 bucket name spec.

    Raises:
        ValueError: nếu input không phải string hoặc không khớp S3 spec.
    """
    if not isinstance(raw, str):
        raise ValueError(f"bucket name phải là string, got {type(raw).__name__}")
    s = raw.strip()
    if s.startswith("arn:aws:s3:::"):
        s = s.split(":::", 1)[1].split("/", 1)[0]
    if not _S3_BUCKET_RE.match(s):
        raise ValueError(f"bucket name không hợp lệ: {raw!r}")
    return s


class ToolResult:
    """Builder cho dict result chuẩn — tool LUÔN return dict (decision #35)."""

    @staticmethod
    def success(*, resource: str, action: str, **extra: Any) -> dict:
        return {
            "success": True,
            "status": "remediated",
            "resource": resource,
            "action": action,
            **extra,
        }

    @staticmethod
    def already_compliant(*, resource: str, message: str = "") -> dict:
        return {
            "success": True,
            "status": "skipped",
            "resource": resource,
            "message": message,
        }

    @staticmethod
    def manual_required(
        *, resource: str, remaining: list[str], reason: str, **extra: Any
    ) -> dict:
        return {
            "success": False,
            "status": "manual_required",
            "manual_required": True,
            "resource": resource,
            "remaining_actions": remaining,
            "reason": reason,
            "verification": {"before": {}, "after": {}, "passed": False},
            **extra,
        }

    @staticmethod
    def failed(*, resource: str, error: str, **extra: Any) -> dict:
        return {
            "success": False,
            "status": "failed",
            "resource": resource,
            "error": error,
            **extra,
        }
