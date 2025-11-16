import json
import re
from .base_agent import BaseAgent

# (Không cần import tool)

# --- (SỬA) DANH SÁCH NÀY DÙNG ĐỂ KIỂM TRA (VALIDATE) SAU KHI AI TRẢ VỀ ---
ALLOWED_GROUPS_LIST = [
    "accessanalyzer",
    "account",
    "acm",
    "apigateway",
    "apigatewayv2",
    "appstream",
    "appsync",
    "athena",
    "autoscaling",
    "awslambda",
    "backup",
    "bedrock",
    "cloudformation",
    "cloudfront",
    "cloudtrail",
    "cloudwatch",
    "codeartifact",
    "codebuild",
    "cognito",
    "config",
    "datasync",
    "directconnect",
    "directoryservice",
    "dlm",
    "dms",
    "documentdb",
    "drs",
    "dynamodb",
    "ec2",
    "ecr",
    "ecs",
    "efs",
    "eks",
    "elasticache",
    "elasticbeanstalk",
    "elb",
    "elbv2",
    "emr",
    "eventbridge",
    "firehose",
    "fms",
    "fsx",
    "glacier",
    "glue",
    "guardduty",
    "iam",
    "inspector2",
    "kafka",
    "kinesis",
    "kms",
    "lightsail",
    "macie",
    "memorydb",
    "mq",
    "neptune",
    "networkfirewall",
    "opensearch",
    "organizations",
    "rds",
    "redshift",
    "resourceexplorer2",
    "route53",
    "s3",
    "sagemaker",
    "secretsmanager",
    "securityhub",
    "servicecatalog",
    "ses",
    "shield",
    "sns",
    "sqs",
    "ssm",
    "ssmincidents",
    "stepfunctions",
    "storagegateway",
    "transfer",
    "trustedadvisor",
    "vpc",
    "waf",
    "wafv2",
    "wellarchitected",
    "workspaces",
]


class PlanningAgent(BaseAgent):

    # --- (SỬA) SYSTEM PROMPT MỚI THEO CẤU TRÚC CỦA BẠN ---
    SYSTEM_PROMPT = f"""
### Role
Bạn là một API JSON. Bạn KHÔNG phải là trợ lý. 
Vai trò của bạn là phân tích `User Request` và trả về MỘT ĐỐI TƯỢNG JSON duy nhất.

### Instruction
1. Đọc `User Request`.
2. Sử dụng `Bảng ánh xạ` để tìm các `Service Code` (mã dịch vụ) tương ứng.
3. Nếu người dùng hỏi chung chung (ví dụ: "kiểm tra bảo mật"), hãy trả về `["iam", "s3", "ec2", "vpc"]`.
4. Trả về đối tượng JSON theo định dạng trong `Output`.
5. KHÔNG GIẢI THÍCH. KHÔNG TRÒ CHUYỆN. KHÔNG SỬ DỤNG ```json.
6. Câu trả lời của bạn PHẢI BẮT ĐẦU bằng `{{` và KẾT THÚC bằng `}}`.

### Output
{{
    "groups_to_scan": ["<service_code_1>", "<service_code_2>", ...],
    "files_to_scan": ["<file_name_1>", ...]
}}

### Bảng ánh xạ
| Thuật ngữ người dùng (Keywords) | Service Code (Output) |
| :--- | :--- |
| "phân quyền", "người dùng", "truy cập trái phép", "mfa", "access key", "root" | "iam" |
| "tệp", "lưu trữ", "bucket", "truy cập internet", "public access" | "s3" |
| "máy ảo", "instance", "cổng", "ssh", "rdp" | "ec2" |
| "log", "giám sát", "lịch sử api" | "cloudtrail" |
| "mạng", "subnet", "acl", "tường lửa" | "vpc" |
"""

    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)
        self.tools_menu = None
        self.available_tools = {}

    def _extract_json_from_text(self, text: str) -> str:
        """
        Helper function to extract JSON from messy AI text.
        (SỬA) Tìm khối JSON cuối cùng (vì AI hay giải thích trước).
        """
        # 1. Tìm ưu tiên khối ```json ... ``` (lấy cái cuối cùng)
        matches = re.findall(r"```json\s*([\s\S]*?)\s*```", text)
        if matches:
            print("[PlanningAgent] ℹ️ (Đã trích xuất JSON từ khối ```json)")
            return matches[-1].strip()  # Lấy cái cuối

        # 2. Nếu không, tìm khối { ... } cuối cùng
        # Tìm kiếm tất cả các khối JSON object { ... }
        matches = re.findall(r"(\{[\s\S]*?\})", text)
        if matches:
            # Lặp ngược lại để tìm khối JSON đầu tiên hợp lệ (thường là cái cuối)
            for match in reversed(matches):
                try:
                    # Kiểm tra xem đây có phải là Kế hoạch (Plan) không
                    parsed_json = json.loads(match)
                    if (
                        "groups_to_scan" in parsed_json
                        or "files_to_scan" in parsed_json
                        or "groupsToScan" in parsed_json
                        or "groupsto(scan" in parsed_json
                    ):
                        print(
                            "[PlanningAgent] ℹ️ (Đã trích xuất JSON từ khối { ... } cuối cùng)"
                        )
                        return match.strip()  # Trả về Kế hoạch
                except json.JSONDecodeError:
                    continue  # Bỏ qua nếu không phải JSON

        print("[PlanningAgent] ⚠️ (Không tìm thấy khối JSON hợp lệ)")
        return text

    def run(self, user_prompt: str) -> dict:
        """
        Chạy agent và trả về một dictionary kế hoạch.
        """
        print(f"--------------------------------------------------")
        print(f"[PlanningAgent] 🤖 Đang phân tích yêu cầu: '{user_prompt}'")
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        response_message = self.call_llm(messages)

        if not response_message or not response_message.content:
            print("[PlanningAgent] ❌ AI không trả về kế hoạch.")
            return {"groups_to_scan": [], "files_to_scan": []}

        print(
            f"[PlanningAgent] 🤖 AI trả về kế hoạch (thô): {response_message.content}"
        )

        cleaned_json_string = self._extract_json_from_text(response_message.content)

        try:
            plan_raw = json.loads(cleaned_json_string)

            # --- (Logic Tự Sửa Lỗi và Chuẩn hóa Key) ---
            plan_fixed = {"groups_to_scan": [], "files_to_scan": []}

            def get_fixed_value(raw_data, keys):
                for key in keys:
                    if key in raw_data:
                        return raw_data[key]
                return []

            plan_fixed["groups_to_scan"] = get_fixed_value(
                plan_raw, ["groups_to_scan", "groupsToScan", "groupsto(scan"]
            )
            plan_fixed["files_to_scan"] = get_fixed_value(
                plan_raw, ["files_to_scan", "filesToScan", "filesto(scan"]
            )

            # --- (MỚI) KIỂM TRA (VALIDATE) KẾ HOẠCH ---
            validated_groups = []
            for group in plan_fixed["groups_to_scan"]:
                if group in ALLOWED_GROUPS_LIST:
                    validated_groups.append(group)
                else:
                    print(
                        f"[PlanningAgent] ⚠️ Cảnh báo: AI đã đề xuất group không hợp lệ '{group}' (đã loại bỏ)."
                    )

            plan_fixed["groups_to_scan"] = validated_groups

            # (Fallback nếu AI trả về plan rỗng nhưng user có hỏi)
            if not plan_fixed["groups_to_scan"] and not plan_fixed["files_to_scan"]:
                lowercased_prompt = user_prompt.lower()
                if any(
                    keyword in lowercased_prompt
                    for keyword in [
                        "bảo mật",
                        "an ninh",
                        "kiểm tra",
                        "phân quyền",
                        "tệp",
                    ]
                ):
                    print(
                        "[PlanningAgent] ⚠️ Cảnh báo: AI trả về plan rỗng, đang thử Fallback."
                    )
                    # Fallback: Tự ánh xạ
                    fallback_groups = []
                    if (
                        "iam" in lowercased_prompt
                        or "phân quyền" in lowercased_prompt
                        or "người dùng" in lowercased_prompt
                    ):
                        fallback_groups.append("iam")
                    if (
                        "s3" in lowercased_prompt
                        or "tệp" in lowercased_prompt
                        or "bucket" in lowercased_prompt
                    ):
                        fallback_groups.append("s3")

                    if fallback_groups:
                        print(
                            f"[PlanningAgent] ℹ️ (Fallback) Tự động thêm: {fallback_groups}"
                        )
                        plan_fixed["groups_to_scan"] = fallback_groups

            return plan_fixed

        except json.JSONDecodeError:
            print(
                f"[PlanningAgent] ❌ Lỗi: Kế hoạch trả về không phải JSON (ngay cả sau khi dọn dẹp). Output thô: {cleaned_json_string}"
            )
            return {"groups_to_scan": [], "files_to_scan": []}  # Fallback
