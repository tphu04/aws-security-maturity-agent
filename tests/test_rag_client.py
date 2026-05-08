"""
Unit Tests cho RAGClient — Slice 0.2 Verification
===================================================
Test cấu trúc class, error handling, và mock API responses.
Không yêu cầu RAG server chạy.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from pdca.agents.shared.rag_client import RAGClient
from pdca.config import RAG_API_URL


class TestRAGClientInit(unittest.TestCase):
    """Test constructor và configuration."""

    def test_default_base_url_from_config(self):
        """config.py cung cấp default URL khi không truyền base_url."""
        client = RAGClient()
        self.assertEqual(client.base_url, RAG_API_URL.rstrip("/"))

    def test_custom_base_url(self):
        client = RAGClient(base_url="http://rag-service:9000")
        self.assertEqual(client.base_url, "http://rag-service:9000")

    def test_trailing_slash_stripped(self):
        client = RAGClient(base_url="http://localhost:9005/")
        self.assertEqual(client.base_url, "http://localhost:9005")

    def test_custom_timeout(self):
        client = RAGClient(base_url="http://localhost:9005", timeout=30.0)
        self.assertEqual(client.timeout, 30.0)

    def test_session_created(self):
        client = RAGClient(base_url="http://localhost:9005")
        self.assertIsNotNone(client._session)


class TestRAGClientPublicMethods(unittest.TestCase):
    """Verify 5 public methods tồn tại và có type hints."""

    def setUp(self):
        self.client = RAGClient(base_url="http://localhost:9005")

    def test_has_is_healthy(self):
        self.assertTrue(callable(getattr(self.client, "is_healthy", None)))

    def test_has_retrieve_checks(self):
        self.assertTrue(callable(getattr(self.client, "retrieve_checks", None)))

    def test_has_retrieve_maturity(self):
        self.assertTrue(callable(getattr(self.client, "retrieve_maturity", None)))

    def test_has_build_context(self):
        self.assertTrue(callable(getattr(self.client, "build_context", None)))

    def test_has_resolve_mapping(self):
        self.assertTrue(callable(getattr(self.client, "resolve_mapping", None)))


class TestRAGClientErrorHandling(unittest.TestCase):
    """Test error handling — methods KHÔNG raise exception, return None."""

    def setUp(self):
        self.client = RAGClient(base_url="http://localhost:9005", timeout=1.0)

    @patch.object(RAGClient, "_post", return_value=None)
    def test_retrieve_checks_returns_none_on_error(self, mock_post):
        result = self.client.retrieve_checks(query="test")
        self.assertIsNone(result)

    @patch.object(RAGClient, "_post", return_value=None)
    def test_retrieve_maturity_returns_none_on_error(self, mock_post):
        result = self.client.retrieve_maturity(query="test")
        self.assertIsNone(result)

    @patch.object(RAGClient, "_post", return_value=None)
    def test_build_context_returns_none_on_error(self, mock_post):
        result = self.client.build_context(consumer="risk", check_ids=["check1"])
        self.assertIsNone(result)

    @patch.object(RAGClient, "_post", return_value=None)
    def test_resolve_mapping_returns_none_on_error(self, mock_post):
        result = self.client.resolve_mapping(check_id="s3_bucket_public_access")
        self.assertIsNone(result)


class TestRAGClientIsHealthy(unittest.TestCase):
    """Test is_healthy() với mock responses."""

    def setUp(self):
        self.client = RAGClient(base_url="http://localhost:9005", timeout=1.0)

    @patch("pdca.agents.shared.rag_client.requests.Session.get")
    def test_healthy_when_ready(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ready"}
        # Session.get is called on the instance, need to patch the instance
        self.client._session.get = MagicMock(return_value=mock_resp)

        self.assertTrue(self.client.is_healthy())

    @patch("pdca.agents.shared.rag_client.requests.Session.get")
    def test_unhealthy_when_not_ready(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "not_ready"}
        self.client._session.get = MagicMock(return_value=mock_resp)

        self.assertFalse(self.client.is_healthy())

    def test_unhealthy_on_connection_error(self):
        self.client._session.get = MagicMock(
            side_effect=ConnectionError("refused")
        )
        self.assertFalse(self.client.is_healthy())


class TestRAGClientPostHelper(unittest.TestCase):
    """Test _post() internal helper với mock responses."""

    def setUp(self):
        self.client = RAGClient(base_url="http://localhost:9005", timeout=1.0)

    def test_success_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "request_id": "test-123",
            "status": "success",
            "data": {"results": [{"check_id": "s3_test"}]},
            "meta": {"confidence": "high"},
            "errors": [],
        }
        mock_resp.raise_for_status = MagicMock()
        self.client._session.post = MagicMock(return_value=mock_resp)

        result = self.client._post("http://localhost:9005/v1/test", {}, "test")
        self.assertIsNotNone(result)
        self.assertIn("results", result)

    def test_error_status_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "request_id": "test-456",
            "status": "error",
            "data": None,
            "meta": {},
            "errors": [{"code": "NO_RESULTS", "message": "No results found"}],
        }
        mock_resp.raise_for_status = MagicMock()
        self.client._session.post = MagicMock(return_value=mock_resp)

        result = self.client._post("http://localhost:9005/v1/test", {}, "test")
        self.assertIsNone(result)

    def test_partial_status_returns_data(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "request_id": "test-789",
            "status": "partial",
            "data": {"results": [{"check_id": "s3_partial"}]},
            "meta": {},
            "errors": [{"code": "MATURITY_CONTEXT_MISSING", "message": "partial data"}],
        }
        mock_resp.raise_for_status = MagicMock()
        self.client._session.post = MagicMock(return_value=mock_resp)

        result = self.client._post("http://localhost:9005/v1/test", {}, "test")
        self.assertIsNotNone(result)
        self.assertIn("results", result)

    def test_timeout_returns_none(self):
        import requests as req
        self.client._session.post = MagicMock(
            side_effect=req.exceptions.Timeout("timeout")
        )
        result = self.client._post("http://localhost:9005/v1/test", {}, "test")
        self.assertIsNone(result)

    def test_connection_error_returns_none(self):
        import requests as req
        self.client._session.post = MagicMock(
            side_effect=req.exceptions.ConnectionError("refused")
        )
        result = self.client._post("http://localhost:9005/v1/test", {}, "test")
        self.assertIsNone(result)


class TestRAGClientBuildContext(unittest.TestCase):
    """Test build_context() response parsing — verify bundle extraction."""

    def setUp(self):
        self.client = RAGClient(base_url="http://localhost:9005", timeout=1.0)

    def _mock_context_response(self, consumer: str):
        """Helper tạo mock response cho build_context."""
        bundle_key = f"{consumer}_bundle"
        return {
            "consumer": consumer,
            "payload": {
                bundle_key: {
                    "related_findings": [
                        {"check_id": "s3_test", "severity": "High"}
                    ],
                    "control_mapping": [],
                }
            },
            "diagnostics": {
                "bundle_stats": {"check_count": 1}
            },
        }

    @patch.object(RAGClient, "_post")
    def test_build_context_risk_bundle(self, mock_post):
        mock_post.return_value = self._mock_context_response("risk")
        result = self.client.build_context(consumer="risk", check_ids=["s3_test"])
        self.assertIsNotNone(result)
        self.assertIn("risk_bundle", result["payload"])

    @patch.object(RAGClient, "_post")
    def test_build_context_planning_bundle(self, mock_post):
        mock_post.return_value = self._mock_context_response("planning")
        result = self.client.build_context(consumer="planning", query="s3 security")
        self.assertIsNotNone(result)
        self.assertIn("planning_bundle", result["payload"])

    @patch.object(RAGClient, "_post")
    def test_build_context_report_bundle(self, mock_post):
        mock_post.return_value = self._mock_context_response("report")
        result = self.client.build_context(consumer="report", check_ids=["s3_test"])
        self.assertIsNotNone(result)
        self.assertIn("report_bundle", result["payload"])

    @patch.object(RAGClient, "_post")
    def test_build_context_returns_none_on_failure(self, mock_post):
        mock_post.return_value = None
        result = self.client.build_context(consumer="risk", check_ids=["s3_test"])
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
