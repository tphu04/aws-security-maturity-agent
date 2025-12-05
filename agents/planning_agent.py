import re
from typing import List, Dict, Any, Optional
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from .base_agent import BaseAgent


# --- 1. WHITELIST ---
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


# --- 2. OUTPUT SCHEMA ---
class AssessmentPlanOutput(BaseModel):
    target_services: List[str] = Field(
        description="List of AWS services to scan (e.g. ['s3', 'iam'])"
    )
    reasoning: str = Field(description="Explanation of why these services were chosen")


class PlanningAgent(BaseAgent):

    SYSTEM_PROMPT = """### Role
Bạn là một **AWS Security Architect**. 
Nhiệm vụ: Chuyển đổi yêu cầu người dùng thành danh sách các AWS Services cần quét (Prowler groups).

### Quy trình tư duy:
1. **Phân tích từ khóa**:
   - "Bucket", "file" -> s3
   - "Máy ảo", "Server", "Compute" -> ec2
   - "Mạng", "IP", "Firewall" -> vpc
   - "User", "Admin", "Access Key" -> iam
   - "Database" -> rds, dynamodb

2. **Xác định phụ thuộc**:
   - ec2 thường đi kèm vpc, ebs.
   - s3 thường đi kèm kms (mã hóa).
   - "Toàn bộ" -> iam, s3, ec2, vpc, cloudtrail, securityhub.

### Output Format (JSON Only)
Trả về JSON đúng chuẩn với key `target_services` và `reasoning`.

{{{{
    "target_services": ["s3"],
    "reasoning": "Người dùng muốn kiểm tra lưu trữ, nên chọn S3 và KMS."
    
}}}}
"""

    def __init__(self, model_name: str, api_key: str, base_url: str):
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            # format="json",
        )

    def _validate_and_clean(self, raw_services: List[str]) -> List[str]:
        """Lọc bỏ các service không tồn tại trong Prowler"""
        valid_groups = []
        for group in raw_services:
            g_clean = str(group).lower().strip()
            if g_clean in ALLOWED_GROUPS_LIST:
                valid_groups.append(g_clean)
            else:
                print(f"   [PlanningAgent] ⚠️ Removing invalid service: '{g_clean}'")
        return list(set(valid_groups))

    def _heuristic_fallback(self, user_prompt: str) -> List[str]:
        """Logic Fallback thông minh dựa trên từ khóa"""
        print("   [PlanningAgent] ⚠️ AI returned empty plan. Using Keyword Fallback.")
        prompt_lower = user_prompt.lower()

        keyword_map = {
            "s3": ["s3"],
            "bucket": ["s3"],
            "file": ["s3"],
            "storage": ["s3"],
            "ec2": ["ec2", "vpc"],
            "vm": ["ec2"],
            "server": ["ec2"],
            "compute": ["ec2"],
            "network": ["vpc"],
            "vpc": ["vpc"],
            "ip": ["vpc"],
            "iam": ["iam"],
            "user": ["iam"],
            "permission": ["iam"],
            "access": ["iam"],
            "db": ["rds"],
            "rds": ["rds"],
            "monitor": ["cloudtrail", "cloudwatch", "config"],
            "all": ["iam", "s3", "ec2", "vpc", "cloudtrail"],
        }

        fallback_set = set()
        for key, services in keyword_map.items():
            if key in prompt_lower:
                fallback_set.update(services)

        return list(fallback_set)

    def run(self, user_request: str) -> Dict[str, Any]:
        print(f"   [PlanningAgent] 🧠 Thinking about: '{user_request}'")

        parser = JsonOutputParser(pydantic_object=AssessmentPlanOutput)
        partial_list = ", ".join(ALLOWED_GROUPS_LIST[:20])

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    self.SYSTEM_PROMPT,
                ),
                ("user", "{request}\n\n{format_instructions}"),
            ]
        )

        chain = prompt | self.llm | parser

        try:
            result = chain.invoke(
                {
                    "request": user_request,
                    "format_instructions": parser.get_format_instructions(),
                }
            )

            raw_services = result.get("target_services", [])
            reasoning = result.get("reasoning", "No reasoning provided.")

            # 1. Validation
            valid_services = self._validate_and_clean(raw_services)

            # 2. Fallback (Keyword Matching)
            if not valid_services:
                valid_services = self._heuristic_fallback(user_request)
                if valid_services:
                    reasoning += " (Auto-detected via keywords)"

            # 3. Final Check
            if not valid_services:
                error_msg = (
                    f"❌ KHÔNG THỂ XÁC ĐỊNH DỊCH VỤ: Yêu cầu '{user_request}' "
                    "không chứa từ khóa AWS service hợp lệ nào. Hệ thống dừng lại."
                )
                print(f"   [PlanningAgent] {error_msg}")
                # Raise lỗi để crash graph ngay lập tức
                raise ValueError(error_msg)

            return {"target_services": valid_services, "reasoning": reasoning}

        except Exception as e:
            # Nếu là lỗi ValueError do ta chủ động raise ở trên -> Ném tiếp ra ngoài
            print("LLM RAW OUTPUT:", e)
            if isinstance(e, ValueError):
                raise e

            # Nếu là lỗi hệ thống khác (Parsing lỗi, LLM down...) -> Cũng dừng luôn
            print(f"   [PlanningAgent] ❌ System Error: {e}")
            raise RuntimeError(f"Lỗi hệ thống trong quá trình Planning: {e}")
