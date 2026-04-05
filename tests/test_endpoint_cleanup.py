"""
Unit Tests cho Slice 0.4 — Dọn dẹp Endpoint cũ (RAG Side)
===========================================================
Verify: no old /retrieve endpoint, no localhost:8111, no RETRIEVAL_API_URL,
RAG API only exposes /v1/* + /health + /ready + /build-info + /.
"""

import os
import re
import unittest
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent          # DoAn/
RAG_DIR = ROOT_DIR / "RAG"
RAG_ROUTES_DIR = RAG_DIR / "app" / "api" / "routes"


def _collect_py_files(directory: Path, exclude_dirs=None):
    """Collect all .py files under *directory*, skipping exclude_dirs."""
    exclude_dirs = exclude_dirs or {"__pycache__", ".git", "venv", "node_modules"}
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            if fname.endswith(".py"):
                yield Path(root) / fname


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# TC-1: Grep /retrieve (without /v1/) in Python files → 0 results
# ---------------------------------------------------------------------------

class TestNoOldRetrieveEndpoint(unittest.TestCase):
    """TC-1: No bare /retrieve references (without /v1/ prefix) in .py files."""

    # Pattern: match '/retrieve' NOT preceded by '/v1'
    # Exclude comments (lines starting with #) and documentation strings
    OLD_RETRIEVE_RE = re.compile(r'(?<!/v1)/retrieve(?!/)')

    def test_agent_codebase_no_old_retrieve(self):
        """Agent System .py files should not reference old /retrieve endpoint."""
        violations = []
        for py_file in _collect_py_files(ROOT_DIR, exclude_dirs={
            "__pycache__", ".git", "venv", "node_modules", "RAG", "tests",
            ".claude", "Report",
        }):
            source = _read_source(py_file)
            for i, line in enumerate(source.splitlines(), 1):
                stripped = line.strip()
                # Skip comments and docstrings
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                if self.OLD_RETRIEVE_RE.search(line):
                    violations.append(f"{py_file.relative_to(ROOT_DIR)}:{i}: {stripped}")
        self.assertEqual(violations, [], f"Old /retrieve references found:\n" + "\n".join(violations))

    def test_rag_routes_no_old_retrieve_endpoint(self):
        """RAG route files should not define a bare /retrieve endpoint (without /v1 prefix)."""
        for route_file in RAG_ROUTES_DIR.glob("*.py"):
            source = _read_source(route_file)
            # Check for APIRouter without /v1 prefix that serves /retrieve
            if 'APIRouter(' in source:
                # Extract prefix
                prefix_match = re.search(r'APIRouter\(.*?prefix\s*=\s*["\']([^"\']*)["\']', source)
                if prefix_match:
                    prefix = prefix_match.group(1)
                    # /v1 prefix is OK
                    if prefix.startswith("/v1"):
                        continue
                    # Health router has no prefix — that's fine
                    if route_file.name == "health.py":
                        continue
                    # Any other router with /retrieve in its routes → violation
                    if '/retrieve' in source and '@router.' in source:
                        self.fail(
                            f"{route_file.name} defines /retrieve endpoint without /v1 prefix"
                        )


# ---------------------------------------------------------------------------
# TC-2: Grep localhost:8111 → 0 results
# ---------------------------------------------------------------------------

class TestNoLocalhost8111(unittest.TestCase):
    """TC-2: No references to localhost:8111 in the entire Python codebase."""

    def test_no_localhost_8111_in_python_files(self):
        violations = []
        for py_file in _collect_py_files(ROOT_DIR, exclude_dirs={
            "__pycache__", ".git", "venv", "node_modules", ".claude", "Report",
        }):
            # Skip test files themselves
            if "test_endpoint_cleanup" in py_file.name:
                continue
            source = _read_source(py_file)
            for i, line in enumerate(source.splitlines(), 1):
                if "localhost:8111" in line and not line.strip().startswith("#"):
                    violations.append(f"{py_file.relative_to(ROOT_DIR)}:{i}: {line.strip()}")
        self.assertEqual(violations, [], f"localhost:8111 references found:\n" + "\n".join(violations))


# ---------------------------------------------------------------------------
# TC-3: RETRIEVAL_API_URL removed from all .py files
# ---------------------------------------------------------------------------

class TestNoRetrievalApiUrl(unittest.TestCase):
    """TC-3: RETRIEVAL_API_URL variable should not exist in any .py file."""

    def test_no_retrieval_api_url_variable(self):
        violations = []
        for py_file in _collect_py_files(ROOT_DIR, exclude_dirs={
            "__pycache__", ".git", "venv", "node_modules", ".claude", "Report",
        }):
            if "test_endpoint_cleanup" in py_file.name:
                continue
            source = _read_source(py_file)
            for i, line in enumerate(source.splitlines(), 1):
                if "RETRIEVAL_API_URL" in line and not line.strip().startswith("#"):
                    violations.append(f"{py_file.relative_to(ROOT_DIR)}:{i}: {line.strip()}")
        self.assertEqual(violations, [], f"RETRIEVAL_API_URL found:\n" + "\n".join(violations))


# ---------------------------------------------------------------------------
# TC-4: RAG API only exposes /v1/*, /health, /ready, /build-info, /
# ---------------------------------------------------------------------------

class TestRAGApiEndpoints(unittest.TestCase):
    """TC-4: Verify RAG API route definitions only expose allowed endpoints."""

    ALLOWED_PREFIXES = {"/v1", "/v1/resolve"}
    ALLOWED_NO_PREFIX_ROUTES = {"/health", "/ready", "/build-info", "/"}

    def test_rag_main_only_includes_known_routers(self):
        """main.py should only include health, retrieve, resolve routers."""
        main_source = _read_source(RAG_DIR / "app" / "main.py")
        # Extract all include_router calls
        includes = re.findall(r'app\.include_router\((\w+)', main_source)
        expected = {"health_router", "retrieve_router", "resolve_router"}
        self.assertEqual(set(includes), expected,
                         f"Unexpected routers included: {set(includes) - expected}")

    def test_retrieve_router_uses_v1_prefix(self):
        """retrieve.py router should use /v1 prefix."""
        source = _read_source(RAG_ROUTES_DIR / "retrieve.py")
        self.assertIn('prefix="/v1"', source)

    def test_resolve_router_uses_v1_prefix(self):
        """resolve.py router should use /v1/resolve prefix."""
        source = _read_source(RAG_ROUTES_DIR / "resolve.py")
        self.assertIn('prefix="/v1/resolve"', source)

    def test_health_router_no_versioned_prefix(self):
        """health.py router should NOT have a versioned prefix (it's infra)."""
        source = _read_source(RAG_ROUTES_DIR / "health.py")
        # Health router should be APIRouter(tags=["health"]) — no prefix
        self.assertNotIn('prefix="/v1', source)


# ---------------------------------------------------------------------------
# TC-5: Stale backup file removed
# ---------------------------------------------------------------------------

class TestNoStaleBackupFiles(unittest.TestCase):
    """TC-5: No stale backup copies of graph_orchestator.py."""

    def test_graph_orchestator_copy_deleted(self):
        """graph_orchestator copy.py should not exist."""
        backup = ROOT_DIR / "graph_orchestator copy.py"
        self.assertFalse(
            backup.exists(),
            "Stale backup 'graph_orchestator copy.py' still exists — should be deleted"
        )


# ---------------------------------------------------------------------------
# TC-6: graph_orchestator.py uses config imports (no hardcoded URLs)
# ---------------------------------------------------------------------------

class TestOrchestratorUsesConfig(unittest.TestCase):
    """TC-6: graph_orchestator.py imports from config, not hardcoded URLs."""

    def setUp(self):
        self.source = _read_source(ROOT_DIR / "graph_orchestator.py")

    def test_imports_from_config(self):
        """graph_orchestator.py should import RAG_API_URL from config."""
        self.assertIn("from config import", self.source)
        self.assertIn("RAG_API_URL", self.source)

    def test_no_retrieval_api_url_variable(self):
        """graph_orchestator.py should not define RETRIEVAL_API_URL."""
        self.assertNotIn("RETRIEVAL_API_URL", self.source)

    def test_no_hardcoded_8111(self):
        """graph_orchestator.py should not contain localhost:8111."""
        self.assertNotIn("localhost:8111", self.source)


if __name__ == "__main__":
    unittest.main()
