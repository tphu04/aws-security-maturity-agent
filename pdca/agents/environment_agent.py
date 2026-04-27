"""EnvironmentAgent — Lấy AWS account context.

Phase A4: Degrade thay vì raise khi thiếu credentials hoặc lỗi AWS;
trả thêm key `buckets` vào success branch.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from pdca.observability.logger import get_logger

logger = get_logger(__name__)


_DEGRADED_CONTEXT: Dict[str, Any] = {
    "account_id": "unknown",
    "region": "us-east-1",
    "identity_arn": "unknown",
    "buckets": [],
    "_degraded": True,
}


class EnvironmentAgent:
    def __init__(self) -> None:
        # boto3 sẽ tự động tìm credentials trong env vars hoặc ~/.aws/credentials
        self.session = boto3.Session()

    def get_aws_context(self) -> Dict[str, Any]:
        """Trả AWS context: account_id, region, identity_arn, buckets.

        Khi thiếu credentials hoặc lỗi AWS API, return dict có `_degraded=True`
        thay vì raise — graph có thể tiếp tục với context giả lập.
        """
        try:
            sts_client = self.session.client("sts")
            identity = sts_client.get_caller_identity()

            region = self.session.region_name or os.environ.get("AWS_REGION", "us-east-1")

            bucket_names = []
            try:
                s3_client = self.session.client("s3", region_name=region)
                response = s3_client.list_buckets()
                bucket_names = [b["Name"] for b in response.get("Buckets", [])]
            except (BotoCoreError, ClientError) as e:
                logger.warning(
                    "Cannot list S3 buckets — keeping empty list",
                    extra={"error_type": type(e).__name__, "error": str(e)},
                )

            logger.info(
                "Connected to AWS",
                extra={
                    "account_id": identity["Account"],
                    "region": region,
                    "bucket_count": len(bucket_names),
                },
            )
            return {
                "account_id": identity["Account"],
                "region": region,
                "identity_arn": identity["Arn"],
                "buckets": bucket_names,
            }

        except (BotoCoreError, ClientError) as e:
            # BotoCoreError bao trùm: NoCredentialsError, PartialCredentialsError,
            # EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError, ...
            # ClientError = lỗi từ AWS API (4xx/5xx).
            logger.warning(
                "AWS unavailable — degrading EnvironmentAgent",
                extra={"error_type": type(e).__name__, "error": str(e)},
            )
            return dict(_DEGRADED_CONTEXT)
