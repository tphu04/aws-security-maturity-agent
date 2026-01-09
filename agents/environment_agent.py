import boto3
import os
from botocore.exceptions import NoCredentialsError, ClientError
from typing import Dict, Any


class EnvironmentAgent:
    def __init__(self):
        """Khởi tạo session AWS."""
        # boto3 sẽ tự động tìm credentials trong biến môi trường hoặc ~/.aws/credentials
        self.session = boto3.Session()

    def get_aws_context(self) -> Dict[str, Any]:
        """
        Lấy thông tin Account ID, Region và Identity ARN hiện tại.
        """
        try:
            # 1. Kết nối STS để lấy thông tin Identity (Who am I?)
            sts_client = self.session.client("sts")
            identity = sts_client.get_caller_identity()

            # 2. Xác định Region
            # Ưu tiên region của session, nếu không có thì fallback sang biến môi trường hoặc default
            region = self.session.region_name
            if not region:
                region = os.environ.get("AWS_REGION", "us-east-1")

            # Lấy danh sách S3 Buckets
            bucket_names = []
            try:
                s3_client = self.session.client("s3", region_name=region)
                response = s3_client.list_buckets()
                # Trích xuất danh sách tên bucket
                bucket_names = [b["Name"] for b in response.get("Buckets", [])]
                # print(f"   [EnvAgent] Found {len(bucket_names)} S3 Buckets.")
            except ClientError as e:
                print(f"   [EnvAgent] ⚠️ Warning: Không thể list S3 buckets (Thiếu quyền?).")

            # print(
            #     f"   [EnvAgent] Connected to AWS Account: {identity['Account']} ({region})"
            # )

            return {
                "account_id": identity["Account"],
                "region": region,
                "identity_arn": identity["Arn"],
            }

        except NoCredentialsError:
            print("   [EnvAgent] ❌ LỖI: Không tìm thấy AWS Credentials.")
            raise Exception(
                "AWS Credentials missing. Please run 'aws configure' or set env vars."
            )

        except ClientError as e:
            print(f"   [EnvAgent] ❌ LỖI: Không thể kết nối AWS. Chi tiết: {e}")
            raise e

        except Exception as e:
            print(f"   [EnvAgent] ❌ LỖI KHÔNG XÁC ĐỊNH: {e}")
            raise e
