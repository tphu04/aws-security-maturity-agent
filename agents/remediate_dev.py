import json
import re
from typing import List, Dict, Any, Optional

from .base_agent import BaseAgent
from agents.template_loader import TemplateLibrary
from agents.environment_agent import EnvironmentAgent
from agents.template_renderer import render_template


class RemediateAgent(BaseAgent):
    """
    RemediateAgent v12
    ------------------
    Tối ưu cho pipeline:
        RiskEvaluationAgent v2 (clean + meta)
        -> AssessmentAgent v3 (smm_assessment)
        -> RemediateAgent v12

    Thay đổi chính so với v11:
    - KHÔNG dùng LLM để chọn tool nữa.
    - Tool selection hoàn toàn rule-based (deterministic).
    - Một số issue non-automated (ObjectLock, MFA Delete, Replication) luôn require manual remediation.
    - Nếu không có rule-match => không tạo remediation task tự động (manual review).
    """

    # Vẫn giữ prompt nếu sau này dùng LLM ở vai trò advisor (không dùng để chọn tool)
    SYSTEM_PROMPT = """
### Role
Bạn là **Remediation Advisor API**.
Nhiệm vụ: Phân tích Finding và mô tả remediation plan, KHÔNG lựa chọn tool hay thực thi hành động.
"""

    SERVICE_LIST = ["s3", "iam", "ec2"]

    SERVICE_ALIAS = {
        "AWS S3": "S3",
        "Amazon S3": "S3",
        "S3": "S3",
        "s3": "S3",
        "aws_s3": "S3",
        "IAM": "IAM",
        "iam": "IAM",
        "aws_iam": "IAM",
        "AWS IAM": "IAM",
        "EC2": "EC2",
        "ec2": "EC2",
        "aws_ec2": "EC2",
        "AWS EC2": "EC2",
    }

    # Những issue không muốn/không thể remediate tự động
    NON_AUTOMATED_ISSUES = {
        "MissingObjectLock",  # Không bật được sau khi bucket tạo
        "MissingMFADelete",  # MFA Delete cũng yêu cầu thiết kế lại
        "MissingCrossRegionReplication",  # Replication setup phức tạp, không auto
    }

    # RULE MATCH TABLE (issue_hint / issue_type / finding pattern → tool list)
    RULE_MATCH_TABLE = {
        # --- PUBLIC ACCESS / POLICY ---
        "s3_bucket_public_access_block": ["s3_public_access_block"],
        "s3_account_level_public_access_blocks": [
            "s3_enable_account_public_access_block"
        ],
        "prowler-aws-s3_account_level_public_access_blocks": [
            "s3_enable_account_public_access_block"
        ],
        "MissingPublicAccessBlockConfiguration": ["s3_public_access_block"],
        "InternetExposed": ["s3_public_access_block"],
        "PublicBucket": ["s3_block_public_access"],
        "s3_bucket_acl_prohibited": ["s3_block_acl"],
        "s3_bucket_acl_private": ["s3_force_private_acl"],
        "s3_bucket_policy_ssl_requests_only": ["s3_secure_transport"],
        "MissingSecureTransport": ["s3_secure_transport"],
        # --- ENCRYPTION ---
        "s3_bucket_default_encryption_enabled": ["s3_enable_kms_encryption"],
        "MissingEncryption": ["s3_enable_kms_encryption"],
        "MissingKMSEncryption": ["s3_enable_kms_encryption"],
        # --- VERSIONING & LOCK ---
        "s3_bucket_versioning_enabled": ["s3_enable_versioning"],
        "MissingVersioning": ["s3_enable_versioning"],
        # MissingObjectLock: non-automated, chỉ bật versioning chưa đủ fix nên KHÔNG auto-map
        # --- LOGGING ---
        "s3_bucket_server_access_logging_enabled": ["s3_enable_access_logging"],
        "s3_bucket_logging_enabled": ["s3_enable_access_logging"],
        "ServerAccessLoggingEnabled": ["s3_enable_access_logging"],
        "MissingLogging": ["s3_enable_access_logging"],
        # --- LIFECYCLE ---
        "s3_bucket_intelligent_tiering": ["s3_enable_intelligent_tiering"],
        "s3_bucket_lifecycle_expiration": ["s3_enable_lifecycle_7day_abort"],
        # --- NOTIFICATION ---
        "MissingEventNotifications": ["s3_enable_event_notifications"],
        # --- REPLICATION ---
        # "MissingCrossRegionReplication": ["s3_enable_replication"],
        # -> đã đưa vào NON_AUTOMATED_ISSUES nên không auto
        # TODO: Thêm rule cho IAM, EC2...
    }

    def __init__(self, model_name, api_key, base_url, executor=None):
        super().__init__(model_name, api_key, base_url)
        self.executor = executor or EnvironmentAgent()
        self.catalog: Dict[str, Dict[str, Any]] = {}

        # Load Templates từng service
        for svc in self.SERVICE_LIST:
            svc_upper = svc.upper()
            try:
                self.catalog[svc_upper] = TemplateLibrary.load_service(svc)
            except Exception as e:
                print(f"[RemediateAgent] ❌ Load template {svc} failed: {e}")

    # ==============================================================
    # MAIN EXECUTION FLOW
    # ==============================================================
    def recommend_fixes(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Input: danh sách findings đã qua RiskAgent v2 + AssessmentAgent v3
        Output: chỉ gồm các task có thể remediate tự động (rule-based, đủ params).

        Mỗi task:
        {
            "tool_id": "s3_enable_versioning",
            "params": { ... }
        }

        Những issue:
        - Non-automated (NON_AUTOMATED_ISSUES)
        - Không có rule-match
        - Thiếu params bắt buộc
        => Sẽ được log là "manual remediation" và KHÔNG sinh task tự động.
        """
        tasks: List[Dict[str, Any]] = []

        for f in findings:
            assessment = f.get("smm_assessment") or {}

            issue_type = assessment.get("issue_type")
            service_group = assessment.get("service_group") or f.get("service_group")
            issue_hint = f.get("issue_hint", "")
            finding_id = f.get("finding_id") or f.get("id") or ""
            short_description = f.get("short_description", "")
            severity = f.get("severity", "N/A")
            risk_score = f.get("risk_score", -1)

            if not service_group:
                print(
                    f"[RemediateAgent] ℹ️ Finding {finding_id}: missing service_group → skip."
                )
                continue

            # ---- 0. NON-AUTOMATED ISSUES: chỉ manual, không auto-fix ----
            if issue_type in self.NON_AUTOMATED_ISSUES:
                print(
                    f"[RemediateAgent] ℹ️ {finding_id} ({issue_type}) thuộc NON_AUTOMATED_ISSUES "
                    f"→ yêu cầu manual remediation (không auto-fix)."
                )
                continue

            # --- Normalize Service Group ---
            service_raw = service_group
            if isinstance(service_raw, list):
                # Ưu tiên S3, nếu không có thì lấy phần tử đầu
                if len(service_raw) > 0:
                    service_raw = next(
                        (x for x in service_raw if str(x).lower() == "s3"),
                        service_raw[0],
                    )
                else:
                    print(
                        f"[RemediateAgent] ℹ️ Finding {finding_id}: empty service_group list → skip."
                    )
                    continue

            service_raw = str(service_raw)
            service_norm = self.SERVICE_ALIAS.get(service_raw, service_raw.upper())
            tool_catalog = self.catalog.get(service_norm, {})

            if not tool_catalog:
                print(
                    f"[RemediateAgent] ℹ️ Finding {finding_id}: "
                    f"no tool catalog for service_group={service_norm} → skip (manual)."
                )
                continue

            # ======================================================
            # STEP 1. RULE-BASED MATCH (ONLY)
            # ======================================================
            rule_tool = self._rule_match(
                issue_hint=issue_hint,
                issue_type=issue_type,
                finding_id=finding_id,
                title=f.get("check_title"),
                tool_catalog=tool_catalog,
            )

            if not rule_tool:
                print(
                    f"[RemediateAgent] ℹ️ Finding {finding_id}: "
                    f"no rule-based remediation found for issue_type='{issue_type}', "
                    f"issue_hint='{issue_hint}' → manual remediation required."
                )
                continue

            print(
                f"[RULE-MATCH] Finding {finding_id}: "
                f"'{issue_hint or issue_type or finding_id}' → {rule_tool}"
            )

            # ======================================================
            # STEP 2. PARAM CHECK + BUILD TASK
            # ======================================================
            built = self._build_task(f, assessment, tool_catalog, rule_tool)
            if built:
                tasks.append(built)
            else:
                print(
                    f"[RemediateAgent] ℹ️ Finding {finding_id}: "
                    f"cannot auto-build task for tool {rule_tool} (missing params) → manual remediation."
                )

        return tasks

    # ==============================================================
    # HELPER METHODS
    # ==============================================================

    def _rule_match(
        self,
        issue_hint: str,
        issue_type: str,
        finding_id: str,
        title: Optional[str],
        tool_catalog: Dict[str, Any],
    ) -> Optional[str]:
        """
        Ưu tiên match theo thứ tự:
        1. Exact match trên issue_hint.
        2. Exact match trên issue_type.
        3. Substring match (issue_hint / finding_id / title) trong RULE_MATCH_TABLE key.
        4. Chỉ trả về tool nếu tool_id tồn tại trong tool_catalog.
        """
        title_l = (title or "").lower()
        hint_l = (issue_hint or "").lower()
        f_id_l = (finding_id or "").lower()
        itype_l = (issue_type or "").lower()

        # 1. Exact match trên issue_hint
        if issue_hint and issue_hint in self.RULE_MATCH_TABLE:
            for tid in self.RULE_MATCH_TABLE[issue_hint]:
                if tid in tool_catalog:
                    return tid

        # 2. Exact match trên issue_type
        if issue_type and issue_type in self.RULE_MATCH_TABLE:
            for tid in self.RULE_MATCH_TABLE[issue_type]:
                if tid in tool_catalog:
                    return tid

        # 3. Substring match trên tất cả key RULE_MATCH_TABLE (ưu tiên key dài hơn)
        sorted_keys = sorted(self.RULE_MATCH_TABLE.keys(), key=len, reverse=True)

        for key in sorted_keys:
            key_l = key.lower()
            if (
                key_l in hint_l
                or key_l in f_id_l
                or key_l in title_l
                or key_l in itype_l
            ):
                tools = self.RULE_MATCH_TABLE[key]
                for tid in tools:
                    if tid in tool_catalog:
                        return tid

        return None

    # def _filter_tools(self, finding, assessment, full_catalog):
    #     """
    #     (Hiện tại không dùng trong flow chính nữa, giữ lại nếu sau này cần filter
    #     trước khi hiển thị candidate cho user hoặc LLM advisor.)
    #     """
    #     issue = (assessment.get("issue_type") or "").lower()
    #     short_desc = (finding.get("short_description") or "").lower()
    #     impact = (assessment.get("impact") or "").lower()
    #     finding_id = str(finding.get("finding_id", "")).lower()

    #     search_text = f"{issue} {short_desc} {impact} {finding_id}"

    #     filtered_catalog = {}
    #     for tid, meta in full_catalog.items():
    #         anti_tags = [t.lower() for t in meta.get("anti_tags", [])]
    #         if any(t in search_text for t in anti_tags):
    #             continue
    #         filtered_catalog[tid] = meta

    #     return filtered_catalog if filtered_catalog else full_catalog

    def build_action_package(self, tool_id: str, params: Dict[str, Any]):
        """
        Build action_package hoàn chỉnh (tool_id + params + steps) dành cho EnvironmentAgent.
        """
        service_prefix = tool_id.split("_")[0].upper()

        template = self.catalog.get(service_prefix, {}).get(
            tool_id
        ) or TemplateLibrary.get_action_template(tool_id)

        if not template:
            raise ValueError(
                f"[RemediateAgent] ❌ No template found for tool: {tool_id}"
            )

        steps = []

        for act in template.get("actions", []):
            raw_json = json.dumps(act.get("params_template", {}))
            rendered_str = render_template(raw_json, params)
            rendered_params = json.loads(rendered_str)

            steps.append(
                {
                    "service": act["service"],
                    "method": act["method"],
                    "params": rendered_params,
                }
            )

        return {
            "tool_id": tool_id,
            "params": params,
            "steps": steps,
        }

    def _build_task(self, finding, assessment, tool_catalog, tool_id):
        """
        Điền tham số và tạo remediation task object:
        {
            "tool_id": "s3_enable_kms_encryption",
            "params": { ... }
        }
        """
        required_params = tool_catalog[tool_id].get("required_params", [])
        params, missing = self._fill_params(finding, assessment, required_params)

        if missing:
            print(f"[RemediateAgent] ⚠️ Tool {tool_id} missing params: {missing}")
            return None

        params["finding_id"] = finding.get("finding_id")
        return {"tool_id": tool_id, "params": params}

    def _fill_params(self, finding, assessment, required_params):
        """
        Điền các params bắt buộc từ finding (clean) + assessment + meta.
        Ưu tiên:
        - field phẳng: resource_id, region...
        - meta: original_* nếu có
        - alias map
        """
        params: Dict[str, Any] = {}
        missing: List[str] = []

        ALIAS_MAP = {
            "Bucket": ["resource_id", "bucket_name", "name"],
            "InstanceId": ["resource_id", "instance_id"],
            "Region": ["region", "aws_region"],
            "AccountId": ["account_id", "aws_account_id"],
        }

        # Gộp context: finding + assessment + meta (flatten)
        search_context = {**finding, **assessment}
        meta = finding.get("meta") or {}
        for k, v in meta.items():
            if k not in search_context:
                search_context[k] = v

        for req in required_params:
            val = search_context.get(req)

            # Alias mapping (vd: Bucket -> resource_id)
            if not val and req in ALIAS_MAP:
                for alias in ALIAS_MAP[req]:
                    if alias in search_context and search_context.get(alias):
                        val = search_context[alias]
                        break

            # Fallback: resources list (nếu dùng lại ASFF thô ở đâu đó)
            if not val:
                res = finding.get("resources", [])
                if res and isinstance(res, list) and len(res) > 0:
                    r0 = res[0]
                    if req == "resource_id":
                        val = r0.get("uid") or r0.get("name") or r0.get("id")
                    elif req == "region":
                        val = r0.get("region")
                    elif "account" in req:
                        val = r0.get("account_id")

            if val is not None:
                params[req] = val
            else:
                missing.append(req)

        return params, missing

    # def _clean_llm_json(self, content: str) -> Dict[str, Any]:
    #     """
    #     (Giữ lại phòng khi sau này cần dùng LLM ở vai trò advisor.
    #     Hiện tại không dùng để chọn tool.)
    #     """
    #     content = content.strip()
    #     if content.startswith("```"):
    #         match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    #         if match:
    #             content = match.group(1)
    #     try:
    #         return json.loads(content)
    #     except Exception:
    #         return {}
