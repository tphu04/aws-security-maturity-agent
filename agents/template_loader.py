import json
import os

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "remediation_templates")

class TemplateLibrary:
    cache = {}

    @classmethod
    def load_service(cls, service: str):
        """Load template JSON file for a service (e.g., s3.json)."""
        if service in cls.cache:
            return cls.cache[service]

        path = os.path.join(TEMPLATE_DIR, f"{service}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Template file not found: {path}")

        with open(path, "r") as f:
            data = json.load(f)

        cls.cache[service] = data
        return data

    @classmethod
    def get_action_template(cls, tool_id: str):
        """
        tool_id: e.g. "s3_public_access_block"
        service = prefix before first "_"
        """
        service = tool_id.split("_")[0]  # s3, iam, ec2...
        data = cls.load_service(service)
        return data.get(tool_id)
