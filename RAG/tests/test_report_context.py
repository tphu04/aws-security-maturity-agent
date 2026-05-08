"""Phase 2 MVP tests — ReportContextService + 3 new endpoints.

Run:
    pytest RAG/tests/test_report_context.py -v --import-mode=importlib
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAG_DIR = PROJECT_ROOT / "RAG"
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(RAG_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_DIR))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RAG_ROOT = PROJECT_ROOT / "RAG"
PROWLER_JSON = RAG_ROOT / "data" / "normalized" / "prowler_checks.json"
MATURITY_JSON = RAG_ROOT / "data" / "normalized" / "maturity_capabilities.json"


def _load_prowler() -> list[dict]:
    return json.loads(PROWLER_JSON.read_text(encoding="utf-8"))


def _load_maturity() -> list[dict]:
    return json.loads(MATURITY_JSON.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Unit: remediation parser
# ---------------------------------------------------------------------------

class TestRemediationParser:
    def test_parse_dict_blob(self):
        from app.services.report_context_service import ReportContextService
        blob = "{'CLI': 'aws s3api put-bucket-acl', 'NativeIaC': 'Resource: ...', 'Other': ''}"
        result = ReportContextService._parse_remediation_blob(blob)
        assert isinstance(result, dict)
        assert "CLI" in result
        assert "aws s3api" in result["CLI"]

    def test_parse_empty_cli_with_iac(self):
        from app.services.report_context_service import ReportContextService
        blob = "{'CLI': '', 'NativeIaC': 'Type: AWS::S3::Bucket', 'Other': ''}"
        result = ReportContextService._parse_remediation_blob(blob)
        assert result is not None
        assert result.get("CLI") == ""
        assert "AWS::S3::Bucket" in result.get("NativeIaC", "")

    def test_parse_invalid_returns_none(self):
        from app.services.report_context_service import ReportContextService
        assert ReportContextService._parse_remediation_blob("not a dict") is None
        assert ReportContextService._parse_remediation_blob("") is None
        assert ReportContextService._parse_remediation_blob(None) is None


# ---------------------------------------------------------------------------
# Unit: remediation corpus lookup
# ---------------------------------------------------------------------------

class TestRemediationCorpusLookup:
    def test_known_check_returns_guide(self):
        from app.services.report_context_service import ReportContextService
        svc = ReportContextService.__new__(ReportContextService)
        svc._prowler_cache = None
        svc._cache_lock = __import__("threading").Lock()

        corpus = svc._load_prowler_corpus()
        assert len(corpus) > 0, "prowler corpus must not be empty"

        # Pick first check with non-empty Remediation blob
        sample_id = None
        for cid, rec in corpus.items():
            blob = rec.get("Remediation") or rec.get("remediation") or ""
            if blob.startswith("'") or blob.startswith("{"):
                sample_id = cid
                break

        assert sample_id is not None, "need at least one check with blob remediation"
        guide = svc._build_remediation_guide(sample_id, "HIGH", corpus)
        assert guide is not None
        assert guide.check_id == sample_id
        assert len(guide.steps) > 0

    def test_unknown_check_returns_none(self):
        from app.services.report_context_service import ReportContextService
        svc = ReportContextService.__new__(ReportContextService)
        svc._prowler_cache = None
        svc._cache_lock = __import__("threading").Lock()
        corpus = svc._load_prowler_corpus()
        guide = svc._build_remediation_guide("nonexistent_check_id_xyz", None, corpus)
        assert guide is None

    def test_empty_cli_still_returns_guide_when_iac_present(self):
        from app.services.report_context_service import ReportContextService
        svc = ReportContextService.__new__(ReportContextService)
        svc._prowler_cache = None
        svc._cache_lock = __import__("threading").Lock()
        corpus = svc._load_prowler_corpus()

        # Find a check with empty CLI but non-empty NativeIaC
        for cid, rec in corpus.items():
            blob = rec.get("Remediation") or ""
            parsed = ReportContextService._parse_remediation_blob(blob)
            if parsed and not parsed.get("CLI") and parsed.get("NativeIaC"):
                guide = svc._build_remediation_guide(cid, "MEDIUM", corpus)
                assert guide is not None
                assert any(s.snippet for s in guide.steps)
                return
        pytest.skip("No check with empty CLI + non-empty IaC in corpus")


# ---------------------------------------------------------------------------
# Unit: domain backfill results
# ---------------------------------------------------------------------------

class TestDomainBackfill:
    def test_all_records_have_domain(self):
        data = _load_maturity()
        missing = [r.get("capability_id") for r in data if not r.get("domain")]
        assert missing == [], f"Records missing domain: {missing}"

    def test_block_public_access_is_s3(self):
        data = _load_maturity()
        rec = next((r for r in data if r.get("capability_id") == "block_public_access"), None)
        assert rec is not None
        assert rec["domain"] == "s3"

    def test_root_account_protection_is_iam(self):
        data = _load_maturity()
        rec = next((r for r in data if r.get("capability_id") == "root_account_protection"), None)
        assert rec is not None
        assert rec["domain"] == "iam"

    def test_audit_api_calls_is_cloudtrail(self):
        data = _load_maturity()
        rec = next((r for r in data if r.get("capability_id") == "audit_api_calls"), None)
        assert rec is not None
        assert rec["domain"] == "cloudtrail"

    def test_no_empty_string_domain(self):
        data = _load_maturity()
        empty = [r.get("capability_id") for r in data if r.get("domain") == ""]
        assert empty == []


# ---------------------------------------------------------------------------
# Integration: live RAG service (requires RAG running on :9005)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestLiveEndpoints:
    BASE = "http://localhost:9005"

    def _get(self, path: str) -> dict:
        import requests
        resp = requests.get(f"{self.BASE}{path}", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict) -> dict:
        import requests
        resp = requests.post(f"{self.BASE}{path}", json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def test_health(self):
        data = self._get("/health")
        assert data.get("status") == "ok"

    def test_q2_returns_capability_themes(self):
        result = self._post("/v1/retrieve/capability", {"domain": "s3", "top_k": 3})
        assert isinstance(result, list)
        if result:
            assert "domain" in result[0]
            assert "narrative" in result[0]

    def test_q3_returns_remediation_steps(self):
        result = self._post("/v1/retrieve/remediation", {
            "check_id": "s3_bucket_level_public_access_block",
            "severity": "HIGH",
            "top_k": 1,
        })
        assert isinstance(result, list)
        if result:
            guide = result[0]
            assert guide["check_id"] == "s3_bucket_level_public_access_block"
            assert isinstance(guide["steps"], list)

    def test_q3_empty_for_nonexistent_check(self):
        result = self._post("/v1/retrieve/remediation", {
            "check_id": "nonexistent_check_xyz_abc",
            "top_k": 1,
        })
        assert result == []

    def test_wrapper_returns_bundle(self):
        result = self._post("/v1/retrieve/report_context", {
            "check_ids": ["s3_bucket_level_public_access_block", "s3_account_level_public_access_blocks"],
            "domains": ["s3"],
            "include_q2": True,
            "include_q3": True,
        })
        assert "confidence" in result
        assert "diagnostics" in result
        assert isinstance(result.get("remediations"), list)
        assert isinstance(result.get("capability_themes"), list)

    def test_wrapper_cache_hit(self):
        import requests
        payload = {
            "check_ids": ["s3_bucket_level_public_access_block"],
            "domains": ["s3"],
            "include_q2": True,
            "include_q3": True,
        }
        self._post("/v1/retrieve/report_context", payload)
        result2 = self._post("/v1/retrieve/report_context", payload)
        assert result2.get("diagnostics", {}).get("cache_hit") is True
