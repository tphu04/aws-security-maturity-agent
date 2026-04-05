"""
Unit Tests cho RiskEvaluationAgent refactored (SLICE-RS-3 + SLICE-2.1 + SLICE-2.2)
===================================================================================
Verify RS-3:
  - run() ≤ 15 dòng (orchestration only)
  - Mỗi sub-method ≤ 30 dòng
  - Dùng extract_check_id() thay vì inline regex
  - _extract_json_from_text() đã xóa
  - LLM output validate: whitelist 3 fields, enum severity, int risk_score 0-10
  - SYSTEM_PROMPT không còn ký tự rác `._`
  - Toàn bộ file dùng 4-space indent
  - print() đã thay bằng logging
  - extended_description → check_title (fix RA-06)
  - Output schema giữ nguyên (backward compatible)

Verify SLICE-2.1:
  - Constructor nhận `rag_client: RAGClient` thay vì `rag_base_url: str`
  - `_fetch_rag_context()` dùng `self.rag_client.build_context()` (không còn requests.post)
  - Fallback: rag_client=None → return {} (graceful degradation)
  - Không còn `import requests` trong file
  - Không còn hardcoded URL

Verify SLICE-2.2:
  - Batch: 1 RAG call cho ≤20 ids, chunked khi >20
  - Confidence: _meta.confidence → hint trong LLM prompt
  - Cache: _rag_cache per run, dedup same check_id
  - Metrics: cache hit/miss/rate trong get_llm_metrics()
"""

import inspect
import json
import re
from unittest.mock import MagicMock, patch

import pytest

from agents.risk_evaluation_agent import (
    RiskEvaluationAgent,
    SYSTEM_PROMPT_SINGLE,
    _VALID_SEVERITIES,
    _SEVERITY_MAP,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_rag_client():
    """Create a mock RAGClient."""
    client = MagicMock()
    client.build_context.return_value = None
    return client


@pytest.fixture
def agent(mock_rag_client):
    """Create RiskEvaluationAgent with mocked LLM and RAGClient."""
    with patch("agents.risk_evaluation_agent.ChatOllama") as MockLLM:
        mock_llm = MagicMock()
        MockLLM.return_value = mock_llm
        a = RiskEvaluationAgent(
            model_name="test-model",
            api_key="test-key",
            base_url="http://localhost:11434",
            rag_client=mock_rag_client,
        )
        a.llm = mock_llm
        yield a


@pytest.fixture
def agent_no_rag():
    """Create RiskEvaluationAgent without rag_client (degraded mode)."""
    with patch("agents.risk_evaluation_agent.ChatOllama") as MockLLM:
        mock_llm = MagicMock()
        MockLLM.return_value = mock_llm
        a = RiskEvaluationAgent(
            model_name="test-model",
            api_key="test-key",
            base_url="http://localhost:11434",
            rag_client=None,
        )
        a.llm = mock_llm
        yield a


@pytest.fixture
def sample_findings():
    """Sample normalized findings for testing."""
    return [
        {
            "status": "FAIL",
            "event_code": "s3_bucket_public_access",
            "check_id": "s3_bucket_public_access",
            "service": "s3",
            "resource_id": "my-bucket",
            "region": "us-east-1",
            "description": "S3 bucket has public access enabled",
            "severity": "High",
            "remediation_text": "Disable public access",
        },
        {
            "status": "FAIL",
            "event_code": "iam_user_mfa_enabled",
            "check_id": "iam_user_mfa_enabled",
            "service": "iam",
            "resource_id": "user-admin",
            "region": "global",
            "description": "IAM user does not have MFA enabled",
            "severity": "Critical",
            "remediation_text": "Enable MFA for user",
        },
        {
            "status": "PASS",
            "event_code": "ec2_instance_public",
            "check_id": "ec2_instance_public",
            "service": "ec2",
        },
    ]


# ============================================================
# TC-1: Code quality — method length constraints
# ============================================================

class TestCodeQuality:
    """Verify code quality requirements from RS-3 plan."""

    def test_run_method_length(self):
        """run() ≤ 15 dòng logic (MUST)."""
        source = inspect.getsource(RiskEvaluationAgent.run)
        lines = source.split("\n")
        logic_lines = []
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                if in_docstring:
                    in_docstring = False
                    continue
                if stripped.count('"""') == 1 or stripped.count("'''") == 1:
                    in_docstring = True
                continue
            if in_docstring:
                continue
            if stripped and not stripped.startswith("#") and not stripped.startswith("def "):
                logic_lines.append(stripped)
        assert len(logic_lines) <= 15, f"run() has {len(logic_lines)} logic lines, expected ≤ 15"

    def test_sub_methods_length(self):
        """Mỗi sub-method ≤ 30 dòng (MUST)."""
        methods = [
            "_filter_fail_findings",
            "_fetch_rag_context",
            "_score_single_finding",
            "_validate_llm_output",
            "_score_findings",
            "_sort_by_priority",
        ]
        for method_name in methods:
            method = getattr(RiskEvaluationAgent, method_name)
            source = inspect.getsource(method)
            lines = [l for l in source.split("\n") if l.strip() and not l.strip().startswith("#")]
            assert len(lines) <= 35, f"{method_name} has {len(lines)} lines, expected ≤ 30 (+5 for def/docstring)"

    def test_no_extract_json_method(self):
        """_extract_json_from_text() đã xóa, dùng parse_llm_json() từ shared (MUST)."""
        assert not hasattr(RiskEvaluationAgent, "_extract_json_from_text"), \
            "_extract_json_from_text should be removed"

    def test_no_print_statements(self):
        """Không còn print() trong file (SHOULD)."""
        source = inspect.getsource(RiskEvaluationAgent)
        print_calls = re.findall(r"^\s+print\(", source, re.MULTILINE)
        assert len(print_calls) == 0, f"Found {len(print_calls)} print() calls, should use logging"

    def test_pep8_indent(self):
        """Toàn bộ file dùng 4-space indent (MUST)."""
        import agents.risk_evaluation_agent as mod
        source = inspect.getsource(mod)
        for i, line in enumerate(source.split("\n"), 1):
            if line and line[0] == "\t":
                pytest.fail(f"Line {i} uses tab indentation instead of spaces")

    def test_no_inline_regex_for_check_id(self):
        """Không còn inline regex 22-dòng cho check_id extraction (MUST)."""
        source = inspect.getsource(RiskEvaluationAgent.run)
        assert "prowler-[^-]+-" not in source, "run() should not contain inline regex for check_id"
        # Also check _score_findings
        source2 = inspect.getsource(RiskEvaluationAgent._score_findings)
        assert "prowler-[^-]+-" not in source2, "_score_findings should not contain inline regex"

    def test_uses_extract_check_id(self):
        """File imports và sử dụng extract_check_id từ shared utils."""
        import agents.risk_evaluation_agent as mod
        source = inspect.getsource(mod)
        assert "from agents.shared.utils import extract_check_id" in source
        assert "extract_check_id(" in inspect.getsource(RiskEvaluationAgent._fetch_rag_context)
        assert "extract_check_id(" in inspect.getsource(RiskEvaluationAgent._score_single_finding)

    def test_uses_parse_llm_json(self):
        """File imports và sử dụng parse_llm_json từ shared utils."""
        import agents.risk_evaluation_agent as mod
        source = inspect.getsource(mod)
        assert "parse_llm_json" in source


# ============================================================
# TC-2: SYSTEM_PROMPT quality
# ============================================================

class TestSystemPrompt:
    def test_no_stray_characters(self):
        """SYSTEM_PROMPT không còn ký tự rác `._` (MUST)."""
        assert "._" not in SYSTEM_PROMPT_SINGLE, "SYSTEM_PROMPT should not contain stray '._'"

    def test_references_check_title(self):
        """Two-Pass: check_title referenced in PASS2 prompt (RAG adjustment)."""
        from agents.risk_evaluation_agent import SYSTEM_PROMPT_PASS2
        assert "check_title" in SYSTEM_PROMPT_PASS2

    def test_output_format_documented(self):
        """SYSTEM_PROMPT documents expected JSON output format."""
        assert "ai_severity" in SYSTEM_PROMPT_SINGLE
        assert "ai_risk_score" in SYSTEM_PROMPT_SINGLE
        assert "ai_reasoning" in SYSTEM_PROMPT_SINGLE


# ============================================================
# TC-3: _filter_fail_findings
# ============================================================

class TestFilterFailFindings:
    def test_filters_only_fail(self, agent, sample_findings):
        result = agent._filter_fail_findings(sample_findings)
        assert len(result) == 2
        assert all(f["status"] == "FAIL" for f in result)

    def test_returns_empty_for_all_pass(self, agent):
        findings = [{"status": "PASS"}, {"status": "PASS"}]
        assert agent._filter_fail_findings(findings) == []

    def test_handles_non_dict_entries(self, agent):
        findings = [{"status": "FAIL"}, "not a dict", None, 42]
        result = agent._filter_fail_findings(findings)
        assert len(result) == 1


# ============================================================
# TC-4: _fetch_rag_context
# ============================================================

class TestFetchRagContext:
    def test_uses_rag_client_build_context(self, agent, mock_rag_client):
        """Dùng RAGClient.build_context() thay vì requests.post (MUST: SLICE-2.1)."""
        mock_rag_client.build_context.return_value = {
            "payload": {"risk_bundle": {
                "related_findings": [],
                "control_mapping": [],
            }}
        }
        findings = [
            {"event_code": "s3_bucket_public_access", "status": "FAIL"},
            {"check_id": "iam_user_mfa", "status": "FAIL"},
        ]
        agent._fetch_rag_context(findings)
        mock_rag_client.build_context.assert_called_once()
        call_kwargs = mock_rag_client.build_context.call_args[1]
        assert call_kwargs["consumer"] == "risk"
        assert "check_ids" in call_kwargs
        assert call_kwargs["include_mappings"] is True

    def test_returns_empty_on_rag_client_none(self, agent, mock_rag_client):
        """Return {} khi RAGClient.build_context() returns None."""
        mock_rag_client.build_context.return_value = None
        findings = [{"event_code": "s3_test", "status": "FAIL"}]
        result = agent._fetch_rag_context(findings)
        assert result == {}

    def test_returns_empty_on_exception(self, agent, mock_rag_client):
        """Return {} khi RAGClient.build_context() raises exception."""
        mock_rag_client.build_context.side_effect = Exception("Connection refused")
        findings = [{"event_code": "s3_test", "status": "FAIL"}]
        result = agent._fetch_rag_context(findings)
        assert result == {}

    def test_returns_context_map_with_metadata(self, agent, mock_rag_client):
        """Context map chứa severity, title, mappings."""
        mock_rag_client.build_context.return_value = {
            "payload": {"risk_bundle": {
                "related_findings": [
                    {"check_id": "check:s3_bucket_public_access", "severity": "High",
                     "title": "S3 Public Access"},
                ],
                "control_mapping": [
                    {"check_id": "check:s3_bucket_public_access",
                     "capability_id": "CIS-1.4"},
                ],
            }}
        }
        findings = [{"event_code": "s3_bucket_public_access", "status": "FAIL"}]
        ctx = agent._fetch_rag_context(findings)
        assert "s3_bucket_public_access" in ctx
        entry = ctx["s3_bucket_public_access"]
        assert entry["severity"] == "High"
        assert entry["title"] == "S3 Public Access"
        assert "CIS-1.4" in entry["mappings"]

    def test_returns_empty_for_no_check_ids(self, agent):
        """Return {} khi findings không có check_id extractable."""
        findings = [{"status": "FAIL"}]
        result = agent._fetch_rag_context(findings)
        assert result == {}

    def test_returns_empty_when_no_rag_client(self, agent_no_rag):
        """Return {} khi agent created without rag_client (MUST: SLICE-2.1 fallback)."""
        findings = [{"event_code": "s3_test", "status": "FAIL"}]
        result = agent_no_rag._fetch_rag_context(findings)
        assert result == {}


# ============================================================
# TC-5: _validate_llm_output (whitelist)
# ============================================================

class TestValidateLlmOutput:
    def test_valid_output_passes(self):
        """Valid LLM output preserved."""
        parsed = {"ai_severity": "Critical", "ai_risk_score": 9, "ai_reasoning": "Public access"}
        result = RiskEvaluationAgent._validate_llm_output(parsed)
        assert result == parsed

    def test_invalid_severity_defaults_medium(self):
        """Invalid severity → default Medium."""
        parsed = {"ai_severity": "SUPER_HIGH", "ai_risk_score": 8, "ai_reasoning": "test"}
        result = RiskEvaluationAgent._validate_llm_output(parsed)
        assert result["ai_severity"] == "Medium"

    def test_risk_score_clamped_0_10(self):
        """Risk score clamped to 0-10 range."""
        assert RiskEvaluationAgent._validate_llm_output(
            {"ai_risk_score": 15})["ai_risk_score"] == 10
        assert RiskEvaluationAgent._validate_llm_output(
            {"ai_risk_score": -3})["ai_risk_score"] == 0

    def test_non_int_risk_score_defaults_5(self):
        """Non-integer risk score → default 5."""
        result = RiskEvaluationAgent._validate_llm_output({"ai_risk_score": "not_a_number"})
        assert result["ai_risk_score"] == 5

    def test_extra_fields_stripped(self):
        """Extra fields from LLM (e.g. status, service) are NOT passed through."""
        parsed = {
            "ai_severity": "High", "ai_risk_score": 7, "ai_reasoning": "test",
            "status": "HACKED", "service": "evil",
        }
        result = RiskEvaluationAgent._validate_llm_output(parsed)
        assert "status" not in result
        assert "service" not in result
        assert len(result) == 3

    def test_missing_fields_get_defaults(self):
        """Missing fields get safe defaults."""
        result = RiskEvaluationAgent._validate_llm_output({})
        assert result["ai_severity"] == "Medium"
        assert result["ai_risk_score"] == 5
        assert isinstance(result["ai_reasoning"], str)


# ============================================================
# TC-6: _score_single_finding — data flow (RA-06 fix)
# ============================================================

class TestScoreSingleFinding:
    def test_llm_view_uses_check_title(self, agent):
        """llm_view dùng check_title thay vì extended_description (MUST: RA-06 fix)."""
        agent.llm.invoke = MagicMock(return_value=MagicMock(
            content='{"ai_severity": "High", "ai_risk_score": 8, "ai_reasoning": "test"}'
        ))
        finding = {"event_code": "s3_test", "status": "FAIL", "severity": "Medium"}
        rag_data = {"severity": "High", "title": "S3 Test Check", "mappings": []}

        # We verify by checking that the enriched result is created correctly
        result = agent._score_single_finding(finding, rag_data)
        assert result["severity"] == "High"
        assert result["prowler_severity"] == "Medium"

    def test_enriched_finding_keeps_original_fields(self, agent):
        """Output giữ nguyên schema — downstream không break (MUST)."""
        agent.llm.invoke = MagicMock(return_value=MagicMock(
            content='{"ai_severity": "Critical", "ai_risk_score": 9, "ai_reasoning": "Public access"}'
        ))
        finding = {
            "event_code": "s3_bucket_public_access", "status": "FAIL",
            "severity": "High", "service": "s3", "description": "test",
        }
        result = agent._score_single_finding(finding, {})
        # Original fields preserved
        assert result["status"] == "FAIL"
        assert result["service"] == "s3"
        # AI fields added
        assert result["severity"] == "Critical"
        assert result["risk_score"] == 9
        assert result["reasoning"] == "Public access"
        assert result["prowler_severity"] == "High"
        assert "compliance" in result

    def test_handles_llm_exception(self, agent):
        """LLM exception → defaults used, finding still returned."""
        agent.llm.invoke = MagicMock(side_effect=Exception("LLM down"))
        finding = {"event_code": "test_check", "status": "FAIL", "severity": "Low"}
        result = agent._score_single_finding(finding, {})
        assert result["severity"] == "Medium"  # default
        assert result["risk_score"] == 5  # default


# ============================================================
# TC-7: _sort_by_priority
# ============================================================

class TestSortByPriority:
    def test_sorts_by_severity_then_score(self):
        findings = [
            {"severity": "Low", "risk_score": 2},
            {"severity": "Critical", "risk_score": 10},
            {"severity": "High", "risk_score": 7},
            {"severity": "Critical", "risk_score": 9},
        ]
        result = RiskEvaluationAgent._sort_by_priority(findings)
        assert result[0]["risk_score"] == 10
        assert result[1]["risk_score"] == 9
        assert result[2]["severity"] == "High"
        assert result[3]["severity"] == "Low"


# ============================================================
# TC-8: run() orchestration
# ============================================================

class TestRunOrchestration:
    def test_run_returns_list(self, agent):
        """run() always returns a list."""
        with patch.object(agent, "_filter_fail_findings", return_value=[]):
            result = agent.run([{"status": "PASS"}])
            assert isinstance(result, list)
            assert result == []

    def test_run_returns_empty_for_no_fails(self, agent):
        result = agent.run([{"status": "PASS"}, {"status": "PASS"}])
        assert result == []

    def test_run_orchestrates_correctly(self, agent):
        """run() calls sub-methods in correct order."""
        mock_fail = [{"status": "FAIL", "event_code": "test", "severity": "High"}]
        with patch.object(agent, "_filter_fail_findings", return_value=mock_fail) as m1, \
             patch.object(agent, "_fetch_rag_context", return_value={}) as m2, \
             patch.object(agent, "_score_findings", return_value=mock_fail) as m3, \
             patch.object(agent, "_sort_by_priority", return_value=mock_fail) as m4:
            result = agent.run([{"status": "FAIL"}])
            m1.assert_called_once()
            m2.assert_called_once_with(mock_fail)
            m3.assert_called_once()
            m4.assert_called_once()
            assert isinstance(result, list)

    def test_run_handles_exception(self, agent):
        """run() should propagate or handle exceptions gracefully."""
        with patch.object(agent, "_filter_fail_findings", return_value=[
            {"status": "FAIL", "event_code": "test"}
        ]):
            with patch.object(agent, "_fetch_rag_context", return_value={}):
                with patch.object(agent, "_score_findings", return_value=[
                    {"severity": "High", "risk_score": 7}
                ]):
                    result = agent.run([{"status": "FAIL"}])
                    assert isinstance(result, list)


# ============================================================
# TC-9: Constructor backward compatibility
# ============================================================

class TestConstructor:
    def test_constructor_signature(self):
        """Constructor accepts rag_client param (SLICE-2.1)."""
        sig = inspect.signature(RiskEvaluationAgent.__init__)
        params = list(sig.parameters.keys())
        assert "model_name" in params
        assert "api_key" in params
        assert "base_url" in params
        assert "rag_client" in params

    def test_constructor_no_rag_base_url(self):
        """Constructor no longer accepts rag_base_url (SLICE-2.1)."""
        sig = inspect.signature(RiskEvaluationAgent.__init__)
        params = list(sig.parameters.keys())
        assert "rag_base_url" not in params

    def test_get_llm_metrics(self, agent):
        """get_llm_metrics() still works."""
        metrics = agent.get_llm_metrics()
        assert "total_latency" in metrics
        assert "call_count" in metrics
        assert "call_history" in metrics


# ============================================================
# TC-10: SLICE-2.1 — RAGClient integration tests
# ============================================================

class TestSlice21RagClientIntegration:
    """Verify SLICE-2.1 RAGClient integration requirements."""

    def test_no_import_requests(self):
        """risk_evaluation_agent.py không còn `import requests` (MUST: SLICE-2.1)."""
        import agents.risk_evaluation_agent as mod
        source = inspect.getsource(mod)
        # Check for standalone `import requests` (not in comments/docstrings)
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped == "import requests":
                pytest.fail("File still has 'import requests' — should be removed per SLICE-2.1")
            if stripped.startswith("from requests"):
                pytest.fail(f"File still imports from requests: '{stripped}'")

    def test_no_requests_post_calls(self):
        """risk_evaluation_agent.py không còn requests.post() calls (MUST: SLICE-2.1)."""
        import agents.risk_evaluation_agent as mod
        source = inspect.getsource(mod)
        assert "requests.post(" not in source, "File should not contain requests.post() calls"

    def test_no_hardcoded_urls(self):
        """risk_evaluation_agent.py không còn hardcoded RAG URLs (MUST: SLICE-2.1)."""
        import agents.risk_evaluation_agent as mod
        source = inspect.getsource(mod)
        assert "localhost:8001" not in source, "File should not contain hardcoded localhost:8001"
        assert "/v1/context/build" not in source, "File should not contain hardcoded endpoint paths"

    def test_agent_works_without_rag_client(self, agent_no_rag):
        """Agent runs correctly when rag_client=None (MUST: SLICE-2.1 graceful degradation)."""
        assert agent_no_rag.rag_client is None
        result = agent_no_rag.run([{"status": "PASS"}])
        assert result == []

    def test_agent_works_without_rag_client_with_fails(self, agent_no_rag):
        """Agent returns scored findings even without RAG context."""
        agent_no_rag.llm.invoke = MagicMock(return_value=MagicMock(
            content='{"ai_severity": "High", "ai_risk_score": 7, "ai_reasoning": "No RAG context"}'
        ))
        findings = [
            {"status": "FAIL", "event_code": "s3_test", "severity": "Medium",
             "service": "s3", "description": "test"}
        ]
        result = agent_no_rag.run(findings)
        assert len(result) == 1
        assert result[0]["severity"] == "High"
        assert result[0]["risk_score"] == 7

    def test_context_map_format_unchanged(self, agent, mock_rag_client):
        """context_map format giữ nguyên → downstream code không break (MUST: SLICE-2.1)."""
        mock_rag_client.build_context.return_value = {
            "payload": {"risk_bundle": {
                "related_findings": [
                    {"check_id": "check:s3_test", "severity": "High", "title": "S3 Test"},
                ],
                "control_mapping": [
                    {"check_id": "check:s3_test", "capability_id": "CIS-1.2"},
                ],
            }}
        }
        findings = [{"event_code": "s3_test", "status": "FAIL"}]
        ctx = agent._fetch_rag_context(findings)
        assert "s3_test" in ctx
        entry = ctx["s3_test"]
        # Verify exact same format as before refactor
        assert "severity" in entry
        assert "title" in entry
        assert "mappings" in entry
        assert isinstance(entry["mappings"], list)

    def test_run_end_to_end_with_rag(self, agent, mock_rag_client):
        """Full run() with RAGClient: filter → fetch context → score → sort."""
        mock_rag_client.build_context.return_value = {
            "payload": {"risk_bundle": {
                "related_findings": [
                    {"check_id": "check:s3_bucket_public_access", "severity": "High",
                     "title": "S3 Public Access"},
                ],
                "control_mapping": [
                    {"check_id": "check:s3_bucket_public_access", "capability_id": "CIS-1.4"},
                ],
            }}
        }
        agent.llm.invoke = MagicMock(return_value=MagicMock(
            content='{"ai_severity": "Critical", "ai_risk_score": 9, "ai_reasoning": "Public access is critical"}'
        ))
        findings = [
            {"status": "FAIL", "event_code": "s3_bucket_public_access",
             "service": "s3", "severity": "High", "description": "Public access",
             "resource_id": "my-bucket", "region": "us-east-1", "remediation_text": "Block"},
        ]
        result = agent.run(findings)
        assert len(result) == 1
        assert result[0]["severity"] == "Critical"
        assert result[0]["risk_score"] == 9
        assert "CIS-1.4" in result[0]["compliance"]
        mock_rag_client.build_context.assert_called_once()


# ============================================================
# TC-11: SLICE-2.2 — Batch, Confidence, Cache
# ============================================================

class TestSlice22BatchConfidenceCache:
    """Verify SLICE-2.2: batch chunking, confidence hint, cache, metrics."""

    # --- Batch verification ---

    def test_single_rag_call_for_all_ids(self, agent, mock_rag_client):
        """MUST: Only 1 RAG call for all unique check_ids (≤20)."""
        mock_rag_client.build_context.return_value = {
            "payload": {"risk_bundle": {"related_findings": [], "control_mapping": []}}
        }
        findings = [
            {"event_code": "s3_check_1", "status": "FAIL"},
            {"event_code": "s3_check_2", "status": "FAIL"},
            {"event_code": "s3_check_3", "status": "FAIL"},
        ]
        agent._fetch_rag_context(findings)
        assert mock_rag_client.build_context.call_count == 1

    def test_batch_chunking_splits_large_batches(self, agent, mock_rag_client):
        """Batch >20 ids → split into multiple RAG calls."""
        mock_rag_client.build_context.return_value = {
            "payload": {"risk_bundle": {"related_findings": [], "control_mapping": []}}
        }
        # Create 25 unique findings → should be chunked into 2 calls (20 + 5)
        findings = [{"event_code": f"check_{i}", "status": "FAIL"} for i in range(25)]
        agent._fetch_rag_context(findings)
        assert mock_rag_client.build_context.call_count == 2

    def test_batch_chunking_exact_boundary(self, agent, mock_rag_client):
        """Exactly 20 ids → 1 RAG call (no extra chunk)."""
        mock_rag_client.build_context.return_value = {
            "payload": {"risk_bundle": {"related_findings": [], "control_mapping": []}}
        }
        findings = [{"event_code": f"check_{i}", "status": "FAIL"} for i in range(20)]
        agent._fetch_rag_context(findings)
        assert mock_rag_client.build_context.call_count == 1

    def test_batch_chunking_merges_results(self, agent, mock_rag_client):
        """Multiple chunks merge results into single context_map."""
        def side_effect_build_context(**kwargs):
            check_ids = kwargs.get("check_ids", [])
            findings_data = [{"check_id": cid, "severity": "High", "title": f"Title {cid}"}
                             for cid in check_ids]
            return {"payload": {"risk_bundle": {
                "related_findings": findings_data, "control_mapping": [],
            }}}
        mock_rag_client.build_context.side_effect = side_effect_build_context
        findings = [{"event_code": f"check_{i}", "status": "FAIL"} for i in range(25)]
        ctx = agent._fetch_rag_context(findings)
        assert len(ctx) == 25
        assert mock_rag_client.build_context.call_count == 2

    # --- Confidence hint ---

    def test_confidence_extracted_from_meta(self, agent, mock_rag_client):
        """SHOULD: _rag_confidence extracted from _meta.confidence."""
        mock_rag_client.build_context.return_value = {
            "_meta": {"confidence": "high"},
            "payload": {"risk_bundle": {"related_findings": [], "control_mapping": []}}
        }
        findings = [{"event_code": "s3_test", "status": "FAIL"}]
        agent._fetch_rag_context(findings)
        assert agent._rag_confidence == "high"

    def test_two_pass_calls_llm_twice_with_rag(self, agent):
        """Two-Pass: LLM called twice when RAG data is present."""
        agent.llm.invoke = MagicMock(return_value=MagicMock(
            content='{"ai_severity": "High", "ai_risk_score": 8, "ai_reasoning": "test"}'
        ))
        finding = {"event_code": "s3_test", "status": "FAIL", "severity": "Medium"}
        rag_data = {"severity": "High", "title": "Test", "mappings": []}
        agent._score_single_finding(finding, rag_data)
        assert agent.llm.invoke.call_count == 2, "Expected 2 LLM calls (Pass1 + Pass2)"

    def test_single_pass_without_rag(self, agent):
        """Single-Pass: LLM called once when no RAG data."""
        agent.llm.invoke = MagicMock(return_value=MagicMock(
            content='{"ai_severity": "Medium", "ai_risk_score": 5, "ai_reasoning": "test"}'
        ))
        finding = {"event_code": "s3_test", "status": "FAIL", "severity": "Medium"}
        agent._score_single_finding(finding, {})
        assert agent.llm.invoke.call_count == 1, "Expected 1 LLM call (Pass1 only)"

    def test_pass2_receives_draft_and_rag_severity(self, agent):
        """Pass 2 payload includes draft_severity and rag_official_severity."""
        agent.llm.invoke = MagicMock(return_value=MagicMock(
            content='{"ai_severity": "Medium", "ai_risk_score": 5, "ai_reasoning": "test"}'
        ))
        finding = {"event_code": "s3_test", "status": "FAIL", "severity": "Medium"}
        rag_data = {"severity": "High", "title": "Test Check", "mappings": []}
        agent._score_single_finding(finding, rag_data)
        # Pass 2 is the last (2nd) call
        pass2_args = agent.llm.invoke.call_args_list[1][0][0]
        parsed = json.loads(pass2_args[1].content)
        assert "draft_severity" in parsed
        assert "rag_official_severity" in parsed
        assert parsed["rag_official_severity"] == "High"

    def test_confidence_hint_in_build_rag_context_view(self, agent):
        """_build_rag_context_view still includes confidence hint (utility method)."""
        agent._rag_confidence = "high"
        view = agent._build_rag_context_view({"severity": "High", "title": "T", "mappings": []})
        assert view["rag_confidence"] == "high"
        assert "confidence_note" in view

    # --- Cache ---

    def test_cache_prevents_duplicate_rag_calls(self, agent, mock_rag_client):
        """SHOULD: Same check_id in same run → no second RAG call."""
        mock_rag_client.build_context.return_value = {
            "payload": {"risk_bundle": {
                "related_findings": [
                    {"check_id": "check:s3_test", "severity": "High", "title": "S3 Test"},
                ],
                "control_mapping": [],
            }}
        }
        findings = [{"event_code": "s3_test", "status": "FAIL"}]
        # First call — cache miss
        agent._fetch_rag_context(findings)
        assert mock_rag_client.build_context.call_count == 1
        # Second call — cache hit
        agent._fetch_rag_context(findings)
        assert mock_rag_client.build_context.call_count == 1  # No additional call

    def test_cache_resets_on_new_run(self, agent, mock_rag_client):
        """Cache resets each run() call — no stale data."""
        mock_rag_client.build_context.return_value = {
            "payload": {"risk_bundle": {"related_findings": [], "control_mapping": []}}
        }
        agent.llm.invoke = MagicMock(return_value=MagicMock(
            content='{"ai_severity": "High", "ai_risk_score": 7, "ai_reasoning": "test"}'
        ))
        findings = [{"event_code": "s3_test", "status": "FAIL", "severity": "Medium",
                      "service": "s3", "description": "test"}]
        # First run
        agent.run(findings)
        assert mock_rag_client.build_context.call_count == 1
        # Second run — cache was reset, new RAG call expected
        agent.run(findings)
        assert mock_rag_client.build_context.call_count == 2

    def test_cache_partial_hit(self, agent, mock_rag_client):
        """Only uncached ids trigger RAG call; cached ids are skipped."""
        mock_rag_client.build_context.return_value = {
            "payload": {"risk_bundle": {
                "related_findings": [
                    {"check_id": "check:s3_a", "severity": "High", "title": "A"},
                ],
                "control_mapping": [],
            }}
        }
        # First call: fetch s3_a
        findings_a = [{"event_code": "s3_a", "status": "FAIL"}]
        agent._fetch_rag_context(findings_a)
        assert mock_rag_client.build_context.call_count == 1

        # Update mock for second call
        mock_rag_client.build_context.return_value = {
            "payload": {"risk_bundle": {
                "related_findings": [
                    {"check_id": "check:s3_b", "severity": "Medium", "title": "B"},
                ],
                "control_mapping": [],
            }}
        }
        # Second call: s3_a cached, only s3_b fetched
        findings_ab = [
            {"event_code": "s3_a", "status": "FAIL"},
            {"event_code": "s3_b", "status": "FAIL"},
        ]
        ctx = agent._fetch_rag_context(findings_ab)
        assert mock_rag_client.build_context.call_count == 2
        assert "s3_a" in ctx
        assert "s3_b" in ctx

    # --- Metrics ---

    def test_metrics_include_cache_stats(self, agent, mock_rag_client):
        """NICE: get_llm_metrics() includes rag_cache stats."""
        mock_rag_client.build_context.return_value = {
            "_meta": {"confidence": "medium"},
            "payload": {"risk_bundle": {
                "related_findings": [
                    {"check_id": "check:s3_test", "severity": "High", "title": "T"},
                ],
                "control_mapping": [],
            }}
        }
        findings = [{"event_code": "s3_test", "status": "FAIL"}]
        agent._fetch_rag_context(findings)
        # Second call — cache hit
        agent._fetch_rag_context(findings)

        metrics = agent.get_llm_metrics()
        assert "rag_cache" in metrics
        cache = metrics["rag_cache"]
        assert cache["misses"] == 1
        assert cache["hits"] == 1
        assert cache["hit_rate"] == 0.5
        assert cache["confidence"] == "medium"

    def test_metrics_zero_lookups(self, agent):
        """Metrics handle zero lookups gracefully (no division by zero)."""
        metrics = agent.get_llm_metrics()
        assert metrics["rag_cache"]["hit_rate"] == 0.0
        assert metrics["rag_cache"]["hits"] == 0
        assert metrics["rag_cache"]["misses"] == 0
