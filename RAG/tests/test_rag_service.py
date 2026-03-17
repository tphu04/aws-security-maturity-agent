"""Basic sanity tests for the RAG service.

This script is intended to be run from the repository root (where `RAG/` is located).
It performs a few sanity checks to ensure the core retrieval pipeline and service
layers are functioning.

Usage:
    python -m RAG.tests.test_rag_service
or
    python RAG/tests/test_rag_service.py

If you use `pytest`, it will also discover and run this file.
"""

import json
import os
import sys
import unittest

# Ensure repository root is on sys.path (when run directly)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestRAGService(unittest.TestCase):
    def test_build_pipeline_runs(self):
        """Ensure the build pipeline runs and produces normalized artifacts."""
        from RAG.scripts.build_all import main as build_main

        # Should not raise and should produce the normalized JSON files.
        build_main()

        from RAG.app.core.config import DATA_ROOT

        normalized_dir = DATA_ROOT / "normalized"
        self.assertTrue((normalized_dir / "prowler_checks.json").exists())
        self.assertTrue((normalized_dir / "maturity_capabilities.json").exists())
        self.assertTrue((normalized_dir / "maturity_mappings.json").exists())

    def test_check_service_returns_results(self):
        """Verify the check retrieval service returns results for a known query."""
        from RAG.app.services.check_service import CheckService
        from RAG.app.core.models import RetrieveChecksRequest

        svc = CheckService()
        resp = svc.search_checks(RetrieveChecksRequest(query="s3 encryption", top_k=3))

        # Basic envelope assertions
        self.assertEqual(resp.status, "success")
        data = resp.data
        self.assertIn("normalized_query", data)
        self.assertIn("results", data)
        self.assertIsInstance(data["results"], list)

        # At least one result should be returned from the built BM25 index
        self.assertGreaterEqual(len(data["results"]), 1)

    def test_maturity_service_returns_results(self):
        """Verify the maturity retrieval service can run and return a list."""
        from RAG.app.services.maturity_service import MaturityService
        from RAG.app.core.models import RetrieveMaturityRequest

        svc = MaturityService()
        resp = svc.search_maturity(RetrieveMaturityRequest(query="governance", top_k=2))

        self.assertEqual(resp.status, "success")
        self.assertIn("results", resp.data)
        self.assertIsInstance(resp.data["results"], list)

    def test_mapping_service_handles_missing(self):
        """Verify mapping service gracefully handles missing check IDs."""
        from RAG.app.services.mapping_service import MappingService
        from RAG.app.core.models import ResolveMappingRequest

        svc = MappingService()
        resp = svc.resolve_mapping(ResolveMappingRequest(check_id="not-a-real-check"))
        self.assertEqual(resp.status, "error")
        self.assertTrue(len(resp.errors) >= 1)

    def _assert_doc_id_in_results(self, results, expected_doc_id):
        self.assertTrue(
            any(r.get("doc_id") == expected_doc_id for r in results),
            msg=f"Expected doc_id '{expected_doc_id}' not found in results: {[r.get('doc_id') for r in results]}",
        )

    # --- Maturity / Capability retrieval accuracy tests ---

    def test_maturity_search_finds_root_account_protection(self):
        from RAG.app.services.maturity_service import MaturityService
        from RAG.app.core.models import RetrieveMaturityRequest

        svc = MaturityService()
        resp = svc.search_maturity(
            RetrieveMaturityRequest(query="root account", top_k=5)
        )
        results = resp.data["results"]
        self._assert_doc_id_in_results(results, "maturity:root-account-protection")

    def test_maturity_search_finds_critical_security_findings(self):
        from RAG.app.services.maturity_service import MaturityService
        from RAG.app.core.models import RetrieveMaturityRequest

        svc = MaturityService()
        resp = svc.search_maturity(
            RetrieveMaturityRequest(query="critical security findings", top_k=5)
        )
        results = resp.data["results"]
        self._assert_doc_id_in_results(
            results, "maturity:act-on-critical-security-findings"
        )

    def test_maturity_search_finds_multi_factor_authentication(self):
        from RAG.app.services.maturity_service import MaturityService
        from RAG.app.core.models import RetrieveMaturityRequest

        svc = MaturityService()
        resp = svc.search_maturity(
            RetrieveMaturityRequest(query="multi factor authentication", top_k=5)
        )
        results = resp.data["results"]
        self._assert_doc_id_in_results(results, "maturity:multi-factor-authentication")

    def test_maturity_search_finds_audit_api_calls(self):
        from RAG.app.services.maturity_service import MaturityService
        from RAG.app.core.models import RetrieveMaturityRequest

        svc = MaturityService()
        resp = svc.search_maturity(
            RetrieveMaturityRequest(query="audit api calls", top_k=5)
        )
        results = resp.data["results"]
        self._assert_doc_id_in_results(results, "maturity:audit-api-calls")

    def test_maturity_search_finds_detect_common_threats(self):
        from RAG.app.services.maturity_service import MaturityService
        from RAG.app.core.models import RetrieveMaturityRequest

        svc = MaturityService()
        resp = svc.search_maturity(
            RetrieveMaturityRequest(query="common threats", top_k=5)
        )
        results = resp.data["results"]
        self._assert_doc_id_in_results(results, "maturity:detect-common-threats")

    # --- Prowler check retrieval accuracy tests ---

    def test_check_search_finds_origin_failover_check(self):
        from RAG.app.services.check_service import CheckService
        from RAG.app.core.models import RetrieveChecksRequest

        svc = CheckService()
        resp = svc.search_checks(
            RetrieveChecksRequest(query="origin failover", top_k=5)
        )
        results = resp.data["results"]
        self._assert_doc_id_in_results(
            results,
            "check:cloudfront_distributions_multiple_origin_failover_configured",
        )

    def test_check_search_finds_s3_origin_non_existent_bucket(self):
        from RAG.app.services.check_service import CheckService
        from RAG.app.core.models import RetrieveChecksRequest

        svc = CheckService()
        resp = svc.search_checks(
            RetrieveChecksRequest(
                query="cloudfront distribution s3 origins reference existing buckets",
                top_k=10,
            )
        )
        results = resp.data["results"]
        self._assert_doc_id_in_results(
            results,
            "check:cloudfront_distributions_s3_origin_non_existent_bucket",
        )

    def test_check_search_finds_https_sni_enabled(self):
        from RAG.app.services.check_service import CheckService
        from RAG.app.core.models import RetrieveChecksRequest

        svc = CheckService()
        resp = svc.search_checks(RetrieveChecksRequest(query="https sni", top_k=5))
        results = resp.data["results"]
        self._assert_doc_id_in_results(
            results,
            "check:cloudfront_distributions_https_sni_enabled",
        )

    def test_check_search_finds_field_level_encryption(self):
        from RAG.app.services.check_service import CheckService
        from RAG.app.core.models import RetrieveChecksRequest

        svc = CheckService()
        resp = svc.search_checks(
            RetrieveChecksRequest(query="field level encryption", top_k=5)
        )
        results = resp.data["results"]
        self._assert_doc_id_in_results(
            results,
            "check:cloudfront_distributions_field_level_encryption_enabled",
        )

    def test_check_search_finds_origin_traffic_encrypted(self):
        from RAG.app.services.check_service import CheckService
        from RAG.app.core.models import RetrieveChecksRequest

        svc = CheckService()
        resp = svc.search_checks(
            RetrieveChecksRequest(query="origin traffic encrypted", top_k=5)
        )
        results = resp.data["results"]
        self._assert_doc_id_in_results(
            results,
            "check:cloudfront_distributions_origin_traffic_encrypted",
        )

    def test_vector_index_returns_results(self):
        """Ensure the Chroma vector index can return candidates for a query."""
        from RAG.app.indexing.vector_index import VectorIndex

        vi = VectorIndex()
        resp = vi.query(name="rag_docs", query_text="s3 encryption", top_k=3)
        self.assertIn("ids", resp)
        self.assertTrue(resp.get("ids"))


if __name__ == "__main__":
    unittest.main()
