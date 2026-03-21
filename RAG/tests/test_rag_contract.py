import unittest
import requests
import json
import os

RAG_API_URL = "http://localhost:8125/v1/context/build"

# Test scenarios representing the core consumers (using the correct API request format)
TEST_CASES = {
    "planning": {
        "consumer": "planning",
        "query": "how to secure IAM users and root account?",
        "service": "iam",
        "include_mappings": True,
        "include_maturity": True,
        "top_k": 5
    },
    "risk": {
        "consumer": "risk",
        "check_ids": ["s3_bucket_public_access"],
        "query": "Evaluate the risk of public S3 buckets in production.",
        "service": "s3",
        "include_mappings": True,
        "include_maturity": True,
        "top_k": 5
    },
    "report": {
        "consumer": "report",
        "check_ids": ["cloudtrail_multi_region_enabled"],
        "query": "Generate a security report for CloudTrail configuration.",
        "service": "cloudtrail",
        "include_mappings": True,
        "include_maturity": True,
        "top_k": 5
    }
}

class TestRAGContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Health check
        try:
            requests.get("http://localhost:8125/docs", timeout=3)
        except requests.exceptions.ConnectionError:
            raise unittest.SkipTest("RAG API is not running on localhost:8125. Please start it.")

    def _fetch_rag(self, test_case):
        response = requests.post(RAG_API_URL, json=test_case, timeout=30)
        self.assertEqual(response.status_code, 200, f"API failed: {response.text}")
        return response.json()

    def test_general_schema(self):
        """Test base schema valid for all consumers."""
        for name, payload_req in TEST_CASES.items():
            resp = self._fetch_rag(payload_req)
            self.assertIn("data", resp)
            
            data = resp["data"]
            self.assertIn("consumer", data)
            self.assertEqual(data["consumer"], payload_req["consumer"])
            self.assertIn("payload", data)
            self.assertIn("diagnostics", data)
            
            payload_str = json.dumps(data["payload"])
            self.assertNotIn('"score"', payload_str, f"Found 'score' in payload for {name}")
            self.assertNotIn('"confidence"', payload_str, f"Found 'confidence' in payload for {name}")
            self.assertNotIn('"prompt_ready_context"', payload_str, f"Found prompt_ready_context in payload for {name}")

    def test_planning_contract(self):
        resp = self._fetch_rag(TEST_CASES["planning"])
        payload = resp["data"]["payload"]
        
        self.assertIn("planning_bundle", payload)
        bundle = payload["planning_bundle"]
        
        self.assertIn("related_findings", bundle)
        self.assertIn("control_mapping_ids", bundle)
        self.assertIn("maturity_capability_ids", bundle)
        
        self.assertNotIn("primary_finding", bundle)
        
        # Check type
        self.assertIsInstance(bundle["control_mapping_ids"], list)
        if len(bundle["control_mapping_ids"]) > 0:
            self.assertIsInstance(bundle["control_mapping_ids"][0], str)

    def test_risk_contract(self):
        resp = self._fetch_rag(TEST_CASES["risk"])
        payload = resp["data"]["payload"]
        
        self.assertIn("risk_bundle", payload)
        bundle = payload["risk_bundle"]
        
        self.assertIn("primary_finding", bundle)
        self.assertIn("control_mapping", bundle)
        self.assertIn("maturity_context", bundle)
        
        if bundle["primary_finding"]:
            finding = bundle["primary_finding"]
            # Regression guard: all technical fields must be present as explicit keys
            self.assertIn("description", finding, "primary_finding must have 'description' key")
            self.assertIn("risk", finding, "primary_finding must have 'risk' key")
            self.assertIn("remediation", finding, "primary_finding must have 'remediation' key")
            # Hardcoded fallback guard: risk must never be the default placeholder
            self.assertNotEqual(
                finding.get("risk"),
                "Unknown Risk",
                "'Unknown Risk' is a hardcoded fallback - real data should flow through",
            )
            
        if bundle["control_mapping"]:
            mapping = bundle["control_mapping"][0]
            self.assertNotIn("rationale", mapping)
            self.assertIn("mapping_confidence", mapping)
            
        if bundle["maturity_context"]:
            cap = bundle["maturity_context"][0]
            self.assertNotIn("summary", cap)
            self.assertIn("short_text", cap)

    def test_report_contract(self):
        resp = self._fetch_rag(TEST_CASES["report"])
        payload = resp["data"]["payload"]
        
        self.assertIn("report_bundle", payload)
        bundle = payload["report_bundle"]
        
        self.assertIn("primary_topics", bundle)
        self.assertIn("key_findings", bundle)
        self.assertIn("control_themes", bundle)
        self.assertIn("recommended_practices", bundle)
        
        self.assertNotIn("control_mapping", bundle)
        
        self.assertIsInstance(bundle["primary_topics"], list)
        self.assertIsInstance(bundle["recommended_practices"], list)
        
        # Regression guard: report bundle must never be completely empty when input check is valid
        self.assertGreater(
            len(bundle["key_findings"]),
            0,
            "report_bundle.key_findings must not be empty when check input is valid",
        )
        
        if bundle["recommended_practices"]:
            self.assertIsInstance(bundle["recommended_practices"][0], str)

if __name__ == '__main__':
    unittest.main(verbosity=2)
