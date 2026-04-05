"""
Unit Tests cho graph_orchestator.py refactored (SLICE-RS-4)
============================================================
Verify:
  - RETRIEVAL_API_URL đã xóa
  - ScannerModule → ScannerAgent (import fix)
  - planning_node tạo PlanningAgent thành công
  - risk_evaluation_node tạo RiskEvaluationAgent thành công
  - ScannerAgent nhận đúng constructor args
  - Comment port 8111 đã xóa
  - Không còn reference đến endpoint cũ
"""

import inspect
import re

import pytest


# ============================================================
# TC-1: Source code verification — dead code & imports
# ============================================================

class TestDeadCodeRemoval:
    """Verify dead code đã xóa và imports đúng."""

    @pytest.fixture(autouse=True)
    def load_source(self):
        """Load source code 1 lần cho tất cả tests."""
        with open("graph_orchestator.py", "r", encoding="utf-8") as f:
            self.source = f.read()

    def test_no_retrieval_api_url(self):
        """RETRIEVAL_API_URL đã xóa khỏi file (MUST)."""
        assert "RETRIEVAL_API_URL" not in self.source, \
            "RETRIEVAL_API_URL should be removed from graph_orchestator.py"

    def test_no_port_8111(self):
        """Không còn reference đến port 8111 (MUST)."""
        assert "8111" not in self.source, \
            "Port 8111 references should be removed"

    def test_no_scanner_module_import(self):
        """ScannerModule đã đổi thành ScannerAgent (MUST)."""
        assert "ScannerModule" not in self.source, \
            "ScannerModule should be renamed to ScannerAgent"

    def test_scanner_agent_import_exists(self):
        """Import ScannerAgent từ scanner_agent (MUST)."""
        assert "from agents.scanner_agent import ScannerAgent" in self.source

    def test_no_port_8111_comment(self):
        """Comment 'port 8111' đã xóa (SHOULD)."""
        assert "port 8111" not in self.source.lower(), \
            "Comment about port 8111 should be removed"

    def test_no_stale_comment_about_api_port(self):
        """Comment 'API nội bộ ở port 8111' đã xóa (SHOULD)."""
        assert "API nội bộ" not in self.source


# ============================================================
# TC-2: PlanningAgent wiring verification
# ============================================================

class TestPlanningNodeWiring:
    """Verify planning_node tạo PlanningAgent đúng constructor."""

    @pytest.fixture(autouse=True)
    def load_source(self):
        with open("graph_orchestator.py", "r", encoding="utf-8") as f:
            self.source = f.read()

    def test_planning_node_creates_agent(self):
        """planning_node gọi PlanningAgent constructor (MUST)."""
        assert "PlanningAgent(" in self.source

    def test_planning_agent_gets_model_name(self):
        """PlanningAgent nhận model_name param."""
        # Find the PlanningAgent constructor call
        pattern = r"PlanningAgent\([^)]*model_name\s*=\s*OLLAMA_MODEL"
        assert re.search(pattern, self.source), \
            "PlanningAgent should receive model_name=OLLAMA_MODEL"

    def test_planning_agent_gets_rag_client(self):
        """PlanningAgent nhận rag_client param (SLICE-1.1)."""
        pattern = r"PlanningAgent\([^)]*rag_client\s*=\s*rag_client"
        assert re.search(pattern, self.source), \
            "PlanningAgent should receive rag_client=rag_client"

    def test_planning_agent_gets_base_url(self):
        """PlanningAgent nhận base_url param."""
        pattern = r"PlanningAgent\([^)]*base_url\s*=\s*OLLAMA_BASE_URL"
        assert re.search(pattern, self.source), \
            "PlanningAgent should receive base_url=OLLAMA_BASE_URL"


# ============================================================
# TC-3: RiskEvaluationAgent wiring verification
# ============================================================

class TestRiskEvaluationNodeWiring:
    """Verify risk_evaluation_node tạo RiskEvaluationAgent đúng."""

    @pytest.fixture(autouse=True)
    def load_source(self):
        with open("graph_orchestator.py", "r", encoding="utf-8") as f:
            self.source = f.read()

    def test_risk_node_creates_agent(self):
        """risk_evaluation_node gọi RiskEvaluationAgent constructor (MUST)."""
        assert "RiskEvaluationAgent(" in self.source

    def test_risk_agent_gets_rag_client(self):
        """RiskEvaluationAgent nhận rag_client param (SLICE-2.1)."""
        pattern = r"RiskEvaluationAgent\([^)]*rag_client\s*=\s*rag_client"
        assert re.search(pattern, self.source), \
            "RiskEvaluationAgent should receive rag_client=rag_client"

    def test_risk_agent_gets_model(self):
        """RiskEvaluationAgent nhận OLLAMA_MODEL."""
        pattern = r"RiskEvaluationAgent\(\s*OLLAMA_MODEL"
        assert re.search(pattern, self.source), \
            "RiskEvaluationAgent should receive OLLAMA_MODEL as first arg"


# ============================================================
# TC-4: ScannerAgent wiring verification
# ============================================================

class TestScannerNodeWiring:
    """Verify scanning_node tạo ScannerAgent đúng constructor."""

    @pytest.fixture(autouse=True)
    def load_source(self):
        with open("graph_orchestator.py", "r", encoding="utf-8") as f:
            self.source = f.read()

    def test_scanner_receives_args(self):
        """ScannerAgent nhận constructor args (fix no-args bug)."""
        pattern = r"ScannerAgent\(OLLAMA_MODEL,\s*OLLAMA_API_KEY,\s*OLLAMA_BASE_URL\)"
        assert re.search(pattern, self.source), \
            "ScannerAgent should receive (OLLAMA_MODEL, OLLAMA_API_KEY, OLLAMA_BASE_URL)"

    def test_no_empty_scanner_constructor(self):
        """ScannerAgent() không còn gọi với 0 args."""
        # ScannerAgent() with no args inside parens — but not the import line
        lines = self.source.split("\n")
        for line in lines:
            stripped = line.strip()
            if "import" in stripped:
                continue
            if "ScannerAgent()" in stripped:
                pytest.fail(f"Found ScannerAgent() with no args: {stripped}")


# ============================================================
# TC-5: Config imports verification
# ============================================================

class TestConfigImports:
    """Verify all required config values are imported."""

    @pytest.fixture(autouse=True)
    def load_source(self):
        with open("graph_orchestator.py", "r", encoding="utf-8") as f:
            self.source = f.read()

    def test_imports_rag_api_url(self):
        assert "RAG_API_URL" in self.source

    def test_imports_ollama_model(self):
        assert "OLLAMA_MODEL" in self.source

    def test_imports_ollama_base_url(self):
        assert "OLLAMA_BASE_URL" in self.source

    def test_imports_ollama_api_key(self):
        assert "OLLAMA_API_KEY" in self.source


# ============================================================
# TC-6: Constructor compatibility — agents can be instantiated
# ============================================================

class TestConstructorCompatibility:
    """Verify refactored agents have compatible constructors."""

    def test_planning_agent_constructor(self):
        """PlanningAgent accepts the args used in planning_node."""
        sig = inspect.signature(
            __import__("agents.planning_agent", fromlist=["PlanningAgent"]).PlanningAgent.__init__
        )
        params = list(sig.parameters.keys())
        assert "model_name" in params
        assert "api_key" in params
        assert "base_url" in params
        assert "rag_client" in params

    def test_risk_evaluation_agent_constructor(self):
        """RiskEvaluationAgent accepts rag_client param (SLICE-2.1)."""
        sig = inspect.signature(
            __import__("agents.risk_evaluation_agent", fromlist=["RiskEvaluationAgent"]).RiskEvaluationAgent.__init__
        )
        params = list(sig.parameters.keys())
        assert "model_name" in params
        assert "api_key" in params
        assert "base_url" in params
        assert "rag_client" in params

    def test_scanner_agent_constructor(self):
        """ScannerAgent accepts the args used in scanning_node."""
        sig = inspect.signature(
            __import__("agents.scanner_agent", fromlist=["ScannerAgent"]).ScannerAgent.__init__
        )
        params = list(sig.parameters.keys())
        assert "model_name" in params
        assert "api_key" in params
        assert "base_url" in params
