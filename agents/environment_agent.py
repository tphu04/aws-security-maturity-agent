import datetime
from typing import Any, Dict, List, Optional
from typing import Tuple, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class EnvironmentAgent:
    """
    EnvironmentAgent
    -----------------
    Nhiệm vụ:
    - Nhận action_package từ RemediateAgent (tool_id, params, steps).
    - Thực thi từng step lên AWS (qua boto3).
    - Thực hiện pre-flight check nhẹ (check method tồn tại).
    - Bắt Exception (try/except) để không làm crash toàn hệ thống.
    - Trả về audit log chi tiết cho từng step.

    Action package structure (từ RemediateAgent.build_action_package):

    {
      "tool_id": "s3_public_access_block",
      "params": { "resource_id": "...", "region": "ap-southeast-1", ... },
      "steps": [
        {
          "service": "s3",
          "method": "put_public_access_block",
          "params": { ... }
        },
        ...
      ]
    }
    """

    def __init__(
        self,
        session: Optional[boto3.Session] = None,
        default_region: Optional[str] = None,
    ):
        # Có thể inject boto3.Session từ ngoài để hỗ trợ multi-account / assumeRole
        self.session = session or boto3.Session()
        self.default_region = default_region or "us-east-1"

        # cache identity (account_id, arn) cho audit
        self._identity_cache: Optional[Dict[str, Any]] = None

    # ==================================================
    # PUBLIC API
    # ==================================================
    def execute(
        self, action_package: Dict[str, Any], dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Thực thi MỘT action_package.

        :param action_package: dict {"tool_id", "params", "steps"}
        :param dry_run: nếu True -> không gọi AWS, chỉ log và giả lập.
        :return: dict kết quả + audit log.
        """
        started_at = datetime.datetime.utcnow().isoformat() + "Z"

        tool_id = action_package.get("tool_id", "UnknownTool")
        global_params = action_package.get("params", {}) or {}
        steps = action_package.get("steps", []) or []

        if not isinstance(steps, list) or not steps:
            return {
                "success": False,
                "tool_id": tool_id,
                "dry_run": dry_run,
                "error": "Action package missing or empty 'steps'.",
                "step_results": [],
                "started_at": started_at,
                "ended_at": datetime.datetime.utcnow().isoformat() + "Z",
            }

        # Lấy identity một lần cho audit (STS GetCallerIdentity)
        identity = self._get_identity_safe()

        step_results: List[Dict[str, Any]] = []
        overall_success = True

        for idx, step in enumerate(steps):
            step_result = self._execute_single_step(
                idx=idx,
                step=step,
                global_params=global_params,
                dry_run=dry_run,
            )
            step_results.append(step_result)
            if not step_result.get("success", False):
                overall_success = False

        ended_at = datetime.datetime.utcnow().isoformat() + "Z"

        return {
            "success": overall_success,
            "tool_id": tool_id,
            "dry_run": dry_run,
            "started_at": started_at,
            "ended_at": ended_at,
            "account_id": identity.get("Account") if identity else None,
            "caller_arn": identity.get("Arn") if identity else None,
            "step_results": step_results,
        }

    # ==================================================
    # STEP EXECUTION
    # ==================================================
    def _execute_single_step(
        self,
        idx: int,
        step: Dict[str, Any],
        global_params: Dict[str, Any],
        dry_run: bool,
    ) -> Dict[str, Any]:
        """
        Thực thi MỘT step:
        - Pre-flight check nhẹ (check method tồn tại).
        - Nếu dry_run: không gọi AWS, chỉ ghi log.
        - Nếu real: gọi AWS + bắt exception.
        """
        service = step.get("service")
        method_name = step.get("method")
        step_params = step.get("params", {}) or {}

        # Region: ưu tiên từ global_params, sau đó từ step params, cuối cùng default_region
        region = (
            global_params.get("region")
            or step_params.get("Region")
            or self.default_region
        )

        step_log: Dict[str, Any] = {
            "index": idx,
            "service": service,
            "method": method_name,
            "region": region,
            "dry_run": dry_run,
            "request_params": step_params,
            "stage": "preflight",
            "success": False,  # default
            "error": None,
            "response_summary": None,
        }

        # Validate cơ bản
        if not service or not method_name:
            step_log["error"] = "Step missing 'service' or 'method'."
            return step_log

        # Tạo client
        try:
            client = self._get_client(service, region)
        except Exception as e:
            step_log["error"] = (
                f"Failed to create client for {service} in {region}: {e}"
            )
            return step_log

        # 1) PRE-FLIGHT CHECK (MVP)
        preflight_ok, preflight_err = self._preflight_check(
            client, service, method_name, step_params
        )
        if not preflight_ok:
            step_log["error"] = f"Pre-flight check failed: {preflight_err}"
            step_log["stage"] = "preflight"
            return step_log

        # 2) DRY-RUN PATH
        if dry_run:
            # MVP: chỉ log, không gọi AWS
            step_log["success"] = True
            step_log["stage"] = "dry_run"
            step_log["response_summary"] = {
                "message": "Dry-run only. No AWS API call was made."
            }
            return step_log

        # 3) REAL EXECUTION
        step_log["stage"] = "execute"

        try:
            method = getattr(client, method_name)
        except AttributeError:
            step_log["error"] = (
                f"Client for service '{service}' does not have method '{method_name}'."
            )
            return step_log

        try:
            response = method(**step_params)

            # Lấy metadata cơ bản cho audit (HTTPStatusCode, RequestId nếu có)
            response_meta = {}
            if isinstance(response, dict):
                meta = response.get("ResponseMetadata", {})
                response_meta = {
                    "http_status": meta.get("HTTPStatusCode"),
                    "request_id": meta.get("RequestId"),
                }

            step_log["success"] = True
            step_log["response_summary"] = response_meta
            return step_log

        except ClientError as ce:
            err = ce.response.get("Error", {})
            step_log["error"] = {
                "type": "ClientError",
                "code": err.get("Code"),
                "message": err.get("Message"),
            }
            return step_log
        except BotoCoreError as be:
            step_log["error"] = {
                "type": "BotoCoreError",
                "message": str(be),
            }
            return step_log
        except Exception as e:
            step_log["error"] = {
                "type": "Exception",
                "message": str(e),
            }
            return step_log

    # ==================================================
    # PRE-FLIGHT CHECK (MVP)
    # ==================================================
    def _preflight_check(
        self,
        client: Any,
        service: str,
        method_name: str,
        params: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Pre-flight check nhẹ:

        - Kiểm tra client có method tương ứng không.
        - (MVP) Không gọi describe_*.
        - Nếu sau này cần, có thể mở rộng:
            + Với S3: gọi head_bucket / get_bucket_location / get_bucket_policy...
            + Với EC2: describe_instances / describe_security_groups...
        """
        if not hasattr(client, method_name):
            return (
                False,
                f"Method '{method_name}' not found in client for service '{service}'.",
            )

        # Có thể thêm logic check params cơ bản ở đây (ví dụ: không cho Bucket=None, Port <=0, ...)
        # Hiện tại để đơn giản, chỉ check method.
        return True, None

    # ==================================================
    # AWS CLIENT + IDENTITY
    # ==================================================
    def _get_client(self, service: str, region: Optional[str] = None):
        """
        Tạo boto3 client cho service + region.
        """
        region_name = region or self.default_region
        return self.session.client(service, region_name=region_name)

    def _get_identity_safe(self) -> Optional[Dict[str, Any]]:
        """
        Lấy identity (Account, Arn) qua STS.
        Cache lại để không gọi nhiều lần.
        Nếu lỗi (ví dụ không có quyền sts:GetCallerIdentity) -> trả về None.
        """
        if self._identity_cache is not None:
            return self._identity_cache

        try:
            sts_client = self.session.client("sts")
            resp = sts_client.get_caller_identity()
            self._identity_cache = resp
            return resp
        except Exception:
            self._identity_cache = None
            return None
