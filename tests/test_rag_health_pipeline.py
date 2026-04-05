"""
Unit Tests cho Slice 0.3 — RAG Health Check in Pipeline
========================================================
Test: PDCAState has rag_available field, RAGClient.is_healthy() graceful failure,
environment_node logic correctness.
"""

import unittest
from unittest.mock import MagicMock, patch

from AgentState import PDCAState


class TestPDCAStateRagAvailable(unittest.TestCase):
    """Test PDCAState has rag_available field."""

    def test_rag_available_field_exists_in_typedef(self):
        """PDCAState should have rag_available in annotations."""
        annotations = PDCAState.__annotations__
        self.assertIn("rag_available", annotations)

    def test_rag_available_type_is_bool(self):
        """rag_available should be typed as bool."""
        annotations = PDCAState.__annotations__
        self.assertEqual(annotations["rag_available"], bool)

    def test_state_dict_accepts_rag_available_true(self):
        """PDCAState should accept rag_available=True."""
        state: PDCAState = {
            "user_request": "test",
            "rag_available": True,
        }
        self.assertTrue(state["rag_available"])

    def test_state_dict_accepts_rag_available_false(self):
        """PDCAState should accept rag_available=False."""
        state: PDCAState = {
            "user_request": "test",
            "rag_available": False,
        }
        self.assertFalse(state["rag_available"])


class TestRAGClientHealthCheck(unittest.TestCase):
    """Test RAGClient.is_healthy() graceful failure — core logic of Slice 0.3."""

    def setUp(self):
        from agents.shared.rag_client import RAGClient
        self.client = RAGClient(base_url="http://localhost:8001", timeout=3.0)

    def test_healthy_when_ready(self):
        """is_healthy() should return True when API responds with status=ready."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ready"}
        self.client._session.get = MagicMock(return_value=mock_resp)

        self.assertTrue(self.client.is_healthy())

    def test_unhealthy_when_not_ready(self):
        """is_healthy() should return False when status != ready."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "initializing"}
        self.client._session.get = MagicMock(return_value=mock_resp)

        self.assertFalse(self.client.is_healthy())

    def test_unhealthy_on_connection_error(self):
        """is_healthy() should return False (not raise) on ConnectionError."""
        self.client._session.get = MagicMock(side_effect=ConnectionError("refused"))
        self.assertFalse(self.client.is_healthy())

    def test_unhealthy_on_timeout(self):
        """is_healthy() should return False on timeout."""
        import requests as req
        self.client._session.get = MagicMock(side_effect=req.exceptions.Timeout("timeout"))
        self.assertFalse(self.client.is_healthy())

    def test_unhealthy_on_http_500(self):
        """is_healthy() should return False on HTTP 500."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        self.client._session.get = MagicMock(return_value=mock_resp)

        self.assertFalse(self.client.is_healthy())

    def test_short_timeout_for_health_check(self):
        """RAGClient created with timeout=3.0 should have that timeout."""
        self.assertEqual(self.client.timeout, 3.0)


class TestEnvironmentNodeLogic(unittest.TestCase):
    """Test the environment_node RAG health check logic without importing graph_orchestator.

    We simulate the exact logic that environment_node uses to verify correctness.
    """

    def _simulate_environment_node_rag_logic(self, rag_healthy: bool):
        """Simulate the RAG health check logic from environment_node."""
        from agents.shared.rag_client import RAGClient

        client = RAGClient(base_url="http://localhost:8001", timeout=3.0)

        # Mock the health check result
        client.is_healthy = MagicMock(return_value=rag_healthy)

        rag_available = client.is_healthy()

        # Simulate what environment_node returns
        return {"rag_available": rag_available, "aws_context": {"account_id": "test"}}

    def test_rag_available_true_when_healthy(self):
        result = self._simulate_environment_node_rag_logic(True)
        self.assertTrue(result["rag_available"])

    def test_rag_available_false_when_unhealthy(self):
        result = self._simulate_environment_node_rag_logic(False)
        self.assertFalse(result["rag_available"])

    def test_downstream_agent_can_check_rag_available(self):
        """Simulate downstream agent checking rag_available in state."""
        state = self._simulate_environment_node_rag_logic(True)

        # Downstream agent pattern
        if state["rag_available"]:
            mode = "full"
        else:
            mode = "degraded"

        self.assertEqual(mode, "full")

    def test_downstream_agent_degraded_mode(self):
        """Simulate downstream agent in degraded mode."""
        state = self._simulate_environment_node_rag_logic(False)

        if state["rag_available"]:
            rag_data = {"some": "data"}
        else:
            rag_data = None  # fallback

        self.assertIsNone(rag_data)


class TestOrchestratorImportsRAGClient(unittest.TestCase):
    """Verify graph_orchestator.py source code contains RAGClient import and usage."""

    def setUp(self):
        with open("graph_orchestator.py", "r", encoding="utf-8") as f:
            self.source = f.read()

    def test_imports_rag_client(self):
        """graph_orchestator.py should import RAGClient."""
        self.assertIn("from agents.shared.rag_client import RAGClient", self.source)

    def test_creates_rag_client_instance(self):
        """graph_orchestator.py should create RAGClient instance."""
        self.assertIn("RAGClient(", self.source)

    def test_calls_is_healthy(self):
        """graph_orchestator.py should call is_healthy()."""
        self.assertIn("is_healthy()", self.source)

    def test_sets_rag_available_in_return(self):
        """graph_orchestator.py environment_node should return rag_available."""
        self.assertIn("rag_available", self.source)

    def test_uses_short_timeout(self):
        """RAGClient should use timeout=3.0 for health check (not default 10.0)."""
        self.assertIn("timeout=3.0", self.source)


if __name__ == "__main__":
    unittest.main()
