"""
RiskEvaluationAgent -- RAG Response & Context Inspection Tests
===============================================================
Hien thi DAY DU raw data tu RAG va context duoc xay dung truoc khi dua cho LLM scoring.
Muc tieu: nhan xet truc quan chat luong text tra ve tu RAG va context construction.

Chay:
    pytest tests/rag_evaluation/test_risk_rag_inspection.py -v -s
    (flag -s de hien thi print output)
"""

import json
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from pdca.agents.risk_evaluation_agent import (
    RiskEvaluationAgent,
    SYSTEM_PROMPT_SINGLE,
    _VALID_SEVERITIES,
)
from pdca.agents.shared.utils import extract_check_id


# ============================================================
# Helpers
# ============================================================

def _header(title: str):
    w = 80
    print(f"\n{'=' * w}")
    print(f"  {title}")
    print(f"{'=' * w}")


def _section(title: str):
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


def _json_pretty(data, label: str = ""):
    if label:
        print(f"\n  [{label}]")
    print(textwrap.indent(json.dumps(data, indent=2, ensure_ascii=False, default=str), "    "))


def _text_block(text: str, label: str = ""):
    if label:
        print(f"\n  [{label}]")
    for line in text.split("\n"):
        print(f"    {line}")


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def rag_client():
    client = MagicMock()
    client.build_context.return_value = None
    return client


@pytest.fixture
def agent(rag_client):
    with patch("pdca.agents.risk_evaluation_agent.ChatOllama") as MockLLM:
        mock_llm = MagicMock()
        MockLLM.return_value = mock_llm
        a = RiskEvaluationAgent(
            model_name="test-model",
            api_key="test-key",
            base_url="http://localhost:11434",
            rag_client=rag_client,
        )
        a.llm = mock_llm
        yield a


# ============================================================
# Mock Data
# ============================================================

RISK_BUILD_CONTEXT_RAW_RESPONSE = {
    "payload": {
        "risk_bundle": {
            "related_findings": [
                {
                    "check_id": "s3_bucket_public_access",
                    "severity": "critical",
                    "title": "Ensure the S3 Bucket does not have a bucket policy with public access",
                    "description": "Public bucket policies allow unrestricted access to S3 data.",
                },
                {
                    "check_id": "iam_user_mfa_enabled",
                    "severity": "critical",
                    "title": "Ensure MFA is enabled for all IAM users that have a console password",
                    "description": "MFA adds an extra layer of protection on top of username and password.",
                },
                {
                    "check_id": "s3_bucket_server_side_encryption",
                    "severity": "high",
                    "title": "Ensure S3 Buckets have server-side encryption (SSE) enabled",
                    "description": "Server-side encryption protects data at rest using AES-256 or KMS.",
                },
            ],
            "control_mapping": [
                {"check_id": "s3_bucket_public_access", "capability_id": "cis_aws_foundations_1.4_2.1.1",
                 "framework": "CIS AWS Foundations", "control_title": "Ensure S3 bucket policy denies public access"},
                {"check_id": "s3_bucket_public_access", "capability_id": "pci_dss_3.2.1_s3.1",
                 "framework": "PCI DSS", "control_title": "S3 buckets should not allow public access"},
                {"check_id": "s3_bucket_public_access", "capability_id": "nist_800_53_rev5_ac_3",
                 "framework": "NIST 800-53", "control_title": "Access Enforcement"},
                {"check_id": "iam_user_mfa_enabled", "capability_id": "cis_aws_foundations_1.4_1.10",
                 "framework": "CIS AWS Foundations", "control_title": "Ensure MFA is enabled for all IAM users"},
                {"check_id": "iam_user_mfa_enabled", "capability_id": "pci_dss_3.2.1_iam.4",
                 "framework": "PCI DSS", "control_title": "Require MFA for IAM users"},
                {"check_id": "s3_bucket_server_side_encryption", "capability_id": "nist_800_53_rev5_sc_13",
                 "framework": "NIST 800-53", "control_title": "Cryptographic Protection"},
            ],
        }
    },
    "diagnostics": {
        "retrieval_time_ms": 58,
        "check_ids_requested": 3,
        "findings_matched": 3,
        "mappings_found": 6,
    },
    "_meta": {
        "confidence": "high",
        "corpus_version": "prowler_3.12",
    },
}

SAMPLE_FAIL_FINDINGS = [
    {
        "status": "FAIL",
        "event_code": "s3_bucket_public_access",
        "check_id": "s3_bucket_public_access",
        "service": "s3",
        "resource_id": "arn:aws:s3:::company-data-prod",
        "region": "us-east-1",
        "description": "S3 bucket company-data-prod has a bucket policy allowing public GetObject access. "
                       "Any unauthenticated user can read objects in this bucket.",
        "severity": "High",
        "remediation_text": "Remove the bucket policy statement that grants public access, "
                            "and enable S3 Block Public Access at the account level.",
    },
    {
        "status": "FAIL",
        "event_code": "iam_user_mfa_enabled",
        "check_id": "iam_user_mfa_enabled",
        "service": "iam",
        "resource_id": "arn:aws:iam::123456789012:user/admin-john",
        "region": "global",
        "description": "IAM user admin-john has console access but no MFA device configured. "
                       "This user has AdministratorAccess policy attached.",
        "severity": "Critical",
        "remediation_text": "Enable a virtual or hardware MFA device for this IAM user.",
    },
    {
        "status": "FAIL",
        "event_code": "s3_bucket_server_side_encryption",
        "check_id": "s3_bucket_server_side_encryption",
        "service": "s3",
        "resource_id": "arn:aws:s3:::company-logs-archive",
        "region": "us-west-2",
        "description": "S3 bucket company-logs-archive does not have default server-side encryption enabled. "
                       "Objects stored without specifying encryption will not be encrypted at rest.",
        "severity": "Medium",
        "remediation_text": "Enable default encryption using AES-256 (SSE-S3) or AWS KMS (SSE-KMS).",
    },
]


# ============================================================
# TEST 1: Hien thi RAG raw response -> parsed context_map -> LLM view cho moi finding
# ============================================================

class TestInspectRiskContextConstruction:
    """
    Hien thi toan bo data flow tu RAG response -> parsed context_map -> LLM view.

    Shows:
      1. Raw RAG response (risk_bundle)
      2. Parsed context_map (check_id -> {severity, title, mappings})
      3. LLM view cho TUNG finding (rag_context + finding info)
      4. System prompt (scoring rubric)
    """

    def test_inspect_full_context_per_finding(self, agent, rag_client):
        """Hien thi context construction cho moi finding truoc khi dua cho LLM."""

        _header("RISK AGENT -- FULL CONTEXT INSPECTION")

        # -- Step 1: Raw RAG Response --
        rag_client.build_context.return_value = RISK_BUILD_CONTEXT_RAW_RESPONSE

        _section("STEP 1: Raw RAG API Response (build_context consumer='risk')")
        _json_pretty(RISK_BUILD_CONTEXT_RAW_RESPONSE, "RAG build_context response")

        diag = RISK_BUILD_CONTEXT_RAW_RESPONSE["diagnostics"]
        meta = RISK_BUILD_CONTEXT_RAW_RESPONSE["_meta"]
        print(f"\n    Diagnostics:")
        print(f"      check_ids_requested : {diag['check_ids_requested']}")
        print(f"      findings_matched    : {diag['findings_matched']}")
        print(f"      mappings_found      : {diag['mappings_found']}")
        print(f"      retrieval_time      : {diag['retrieval_time_ms']}ms")
        print(f"      confidence          : {meta['confidence']}")

        # -- Step 2: Agent parses RAG response -> context_map --
        context_map = agent._fetch_rag_context(SAMPLE_FAIL_FINDINGS)

        _section("STEP 2: Parsed context_map (agent._fetch_rag_context)")
        _json_pretty(context_map, "context_map: check_id -> {severity, title, mappings}")

        print(f"\n    RAG confidence: {agent._rag_confidence}")
        print(f"    Cache size    : {len(agent._rag_cache)} entries")
        print(f"    Cache hits    : {agent._cache_hits}")
        print(f"    Cache misses  : {agent._cache_misses}")

        # -- Step 3: LLM view per finding --
        _section("STEP 3: LLM View per Finding (what LLM receives)")

        for idx, finding in enumerate(SAMPLE_FAIL_FINDINGS):
            check_id = extract_check_id(finding) or ""
            rag_data = context_map.get(check_id, {})
            rag_view = agent._build_rag_context_view(rag_data)

            llm_view = {
                "check_id": check_id,
                "service": finding.get("service"),
                "resource_id": finding.get("resource_id"),
                "region": finding.get("region"),
                "description": finding.get("description"),
                "original_severity": finding.get("severity"),
                "remediation_text": finding.get("remediation_text"),
                "rag_context": rag_view,
            }

            print(f"\n  {'=' * 56}")
            print(f"  Finding [{idx + 1}/{len(SAMPLE_FAIL_FINDINGS)}]: {check_id}")
            print(f"  {'=' * 56}")
            _json_pretty(llm_view, f"HumanMessage content for {check_id}")

            print(f"\n    RAG enrichment analysis:")
            if rag_data:
                print(f"      RAG severity   : {rag_data.get('severity', 'N/A')}")
                print(f"      Prowler sev    : {finding.get('severity')}")
                print(f"      RAG title      : {rag_data.get('title', 'N/A')}")
                print(f"      Compliance     : {rag_data.get('mappings', [])}")
                print(f"      Confidence     : {rag_view.get('rag_confidence', 'N/A')}")
                print(f"      Confidence hint: {rag_view.get('confidence_note', 'N/A')}")

                sev_match = rag_data.get("severity", "").lower() == finding.get("severity", "").lower()
                print(f"      Severity match : {'YES' if sev_match else 'DIFFERS (RAG vs Prowler)'}")
            else:
                print(f"      (No RAG context available for this check_id)")

        # -- Step 4: System Prompt --
        _section("STEP 4: System Prompt (SYSTEM_PROMPT_SINGLE)")
        _text_block(SYSTEM_PROMPT_SINGLE, "SystemMessage content")

        # Assertions
        assert len(context_map) >= 2
        assert agent._rag_confidence == "high"
        print(f"\n  [PASS] Context constructed for {len(context_map)} check_ids, "
              f"confidence={agent._rag_confidence}")


# ============================================================
# TEST 2: Hien thi compliance mapping enrichment chi tiet
# ============================================================

class TestInspectComplianceEnrichment:
    """
    Hien thi chi tiet compliance mappings duoc RAG tra ve va cach chung enrichment findings.

    Shows:
      1. Raw control_mapping tu RAG
      2. Mapping grouping theo check_id
      3. Final compliance field trong scored finding
      4. So sanh finding co RAG vs khong co RAG
    """

    def test_inspect_compliance_mapping_detail(self, agent, rag_client):
        """Hien thi compliance mapping enrichment tu RAG vao scored finding."""

        _header("RISK AGENT -- COMPLIANCE MAPPING INSPECTION")

        # -- Step 1: Raw control mappings --
        raw_mappings = RISK_BUILD_CONTEXT_RAW_RESPONSE["payload"]["risk_bundle"]["control_mapping"]

        _section("STEP 1: Raw Control Mappings from RAG")
        _json_pretty(raw_mappings, "control_mapping array")

        # Group by check_id
        grouped = {}
        for m in raw_mappings:
            cid = m["check_id"]
            if cid not in grouped:
                grouped[cid] = []
            grouped[cid].append({
                "capability_id": m["capability_id"],
                "framework": m.get("framework", "N/A"),
                "control_title": m.get("control_title", "N/A"),
            })

        _section("STEP 2: Mappings Grouped by check_id")
        for cid, maps in grouped.items():
            print(f"\n    {cid}:")
            for m in maps:
                print(f"      [{m['framework']}] {m['capability_id']}")
                print(f"        -> {m['control_title']}")

        # -- Step 3: Parse + score --
        rag_client.build_context.return_value = RISK_BUILD_CONTEXT_RAW_RESPONSE
        context_map = agent._fetch_rag_context(SAMPLE_FAIL_FINDINGS)

        _section("STEP 3: Scored Finding -- WITH RAG vs WITHOUT RAG")

        finding_with_rag = SAMPLE_FAIL_FINDINGS[0]  # s3_bucket_public_access
        check_id = extract_check_id(finding_with_rag)
        rag_data = context_map.get(check_id, {})

        # Simulate LLM response
        mock_response_with = MagicMock()
        mock_response_with.content = json.dumps({
            "ai_severity": "Critical",
            "ai_risk_score": 9,
            "ai_reasoning": "Public S3 access violates CIS 2.1.1 and PCI DSS. "
                           "Data exposure risk is maximum."
        })
        agent.llm.invoke.return_value = mock_response_with
        scored_with_rag = agent._score_single_finding(finding_with_rag, rag_data)

        print(f"\n  [WITH RAG context]")
        _json_pretty(scored_with_rag, f"Scored finding: {check_id}")

        mock_response_without = MagicMock()
        mock_response_without.content = json.dumps({
            "ai_severity": "High",
            "ai_risk_score": 7,
            "ai_reasoning": "Public access to S3 is risky but without compliance context "
                           "cannot determine full severity."
        })
        agent.llm.invoke.return_value = mock_response_without
        scored_without_rag = agent._score_single_finding(finding_with_rag, {})

        print(f"\n  [WITHOUT RAG context]")
        _json_pretty(scored_without_rag, f"Scored finding: {check_id} (no RAG)")

        _section("STEP 4: Comparison")
        print("    | Aspect             | With RAG           | Without RAG        |")
        print("    |--------------------|--------------------|--------------------|")
        print(f"    | AI Severity        | {scored_with_rag['severity']:<18} | {scored_without_rag['severity']:<18} |")
        print(f"    | AI Risk Score      | {scored_with_rag['risk_score']:<18} | {scored_without_rag['risk_score']:<18} |")
        print(f"    | Compliance         | {len(scored_with_rag['compliance'])} mappings{'':<9} | {len(scored_without_rag['compliance'])} mappings{'':<9} |")
        print(f"    | Reasoning          | Has compliance ref | Generic{'':<12} |")

        print(f"\n    With RAG reasoning   : {scored_with_rag['reasoning']}")
        print(f"    Without RAG reasoning: {scored_without_rag['reasoning']}")

        assert len(scored_with_rag["compliance"]) > 0
        assert len(scored_without_rag["compliance"]) == 0
        print(f"\n  [PASS] RAG enriches finding with {len(scored_with_rag['compliance'])} compliance mappings")


# ============================================================
# TEST 3: Hien thi confidence injection vao LLM prompt
# ============================================================

class TestInspectConfidenceInjection:
    """
    Hien thi cach confidence level tu RAG anh huong den LLM prompt.

    Shows:
      1. rag_context_view cho HIGH confidence
      2. rag_context_view cho MEDIUM confidence
      3. rag_context_view cho LOW confidence
      4. rag_context_view khi KHONG co RAG
      5. So sanh hint text giua cac muc
    """

    def test_inspect_confidence_levels_in_llm_view(self, agent, rag_client):
        """Hien thi rag_context_view cho moi muc confidence."""

        _header("RISK AGENT -- CONFIDENCE INJECTION INSPECTION")

        rag_data = {
            "severity": "critical",
            "title": "S3 Bucket Public Access Block",
            "mappings": ["cis_aws_2.1.1", "pci_dss_s3.1", "nist_ac_3"],
        }

        confidence_levels = ["high", "medium", "low", "unknown"]

        _section("RAG data (same for all confidence levels)")
        _json_pretty(rag_data, "rag_data input")

        _section("Confidence-injected LLM views")

        views = {}
        for conf in confidence_levels:
            agent._rag_confidence = conf
            view = agent._build_rag_context_view(rag_data)
            views[conf] = view

            print(f"\n  {'=' * 50}")
            print(f"  Confidence = '{conf}'")
            print(f"  {'=' * 50}")
            _json_pretty(view, f"rag_context_view (confidence={conf})")

        _section("Comparison Table")
        print("    | Field              | high              | medium            | low               | unknown           |")
        print("    |--------------------|-------------------|-------------------|-------------------|-------------------|")

        for field in ["official_severity", "check_title", "rag_confidence", "confidence_note"]:
            vals = []
            for conf in confidence_levels:
                v = views[conf].get(field, "(absent)")
                if isinstance(v, str) and len(v) > 15:
                    v = v[:15] + "..."
                vals.append(f"{v:<17}")
            print(f"    | {field:<18} | {' | '.join(vals)} |")

        _section("Impact Analysis")
        print("    HIGH confidence:")
        print(f"      Hint: \"{views['high'].get('confidence_note', 'N/A')}\"")
        print("      -> LLM SHOULD trust compliance mappings strongly")
        print("      -> Score likely aligned with official_severity")

        print(f"\n    MEDIUM confidence:")
        print(f"      Hint: \"{views['medium'].get('confidence_note', 'N/A')}\"")
        print("      -> LLM uses compliance as supporting evidence, not primary")
        print("      -> Score based on finding details + compliance support")

        print(f"\n    LOW confidence:")
        print(f"      Hint: \"{views['low'].get('confidence_note', 'N/A')}\"")
        print("      -> LLM should rely MORE on finding description/context")
        print("      -> Compliance data may be wrong/incomplete")

        print(f"\n    UNKNOWN (no RAG):")
        print(f"      No confidence field injected")
        print("      -> LLM scores purely based on finding description")
        print("      -> No compliance context available")

        # Assertions
        assert "rag_confidence" in views["high"]
        assert "rag_confidence" in views["medium"]
        assert "rag_confidence" in views["low"]
        assert "rag_confidence" not in views["unknown"]
        assert "trust" in views["high"]["confidence_note"].lower()
        assert "incomplete" in views["low"]["confidence_note"].lower()
        print(f"\n  [PASS] 3 confidence levels inject correct hints, unknown = no injection")
