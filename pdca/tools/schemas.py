"""Pydantic input schemas cho LangChain @tool decorators (B13).

Tách khỏi `pdca/tools.py` (legacy) — chỉ giữ schemas còn được dùng.
`ScanFileInput` đã bỏ ở B18 (zero-usage trong pipeline).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScanGroupInput(BaseModel):
    group: str = Field(
        ...,
        description="Tên service AWS cần quét (ví dụ: 's3', 'iam', 'ec2').",
    )


class JobStatusInput(BaseModel):
    job_id: str = Field(..., description="ID của job cần kiểm tra trạng thái.")


class ScanChecksInput(BaseModel):
    check_ids: str = Field(
        ...,
        description=(
            "Danh sách Prowler Check IDs, cách nhau bởi dấu phẩy "
            "(vd: 's3_block_account_public_access,iam_root_mfa_enabled')."
        ),
    )
