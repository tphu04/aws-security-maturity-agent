"""
PlanningAgent -- RAG Response & Context Inspection Tests
========================================================
Hien thi DAY DU raw data tu RAG va context duoc xay dung truoc khi dua cho LLM.
Muc tieu: nhan xet truc quan chat luong text tra ve tu RAG va context construction.

Chay:
    pytest tests/rag_evaluation/test_planning_rag_inspection.py -v -s
    (flag -s de hien thi print output)
"""

import json
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from pdca.agents.planning_agent import PlanningAgent, RERANK_PROMPT, TRANSLATION_PROMPT
from pdca.agents.shared.rag_client import RAGClient


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
    client = MagicMock(spec=RAGClient)
    client.is_healthy.return_value = True
    return client


@pytest.fixture
def agent(rag_client):
    with patch("pdca.agents.planning_agent.ChatOllama") as MockLLM:
        mock_llm = MagicMock()
        MockLLM.return_value = mock_llm
        a = PlanningAgent(
            model_name="test-model",
            base_url="http://localhost:11434",
            rag_client=rag_client,
        )
        a.llm = mock_llm
        yield a


# ============================================================
# Mock RAG Responses (realistic data)
# ============================================================

S3_BUILD_CONTEXT_RAW_RESPONSE = {
    "payload": {
        "planning_bundle": {
            "related_findings": [
                {
                    "check_id": "s3_bucket_public_access",
                    "service": "s3",
                    "title": "Ensure the S3 Bucket does not have a bucket policy with public access",
                    "severity": "critical",
                    "description": "Checks if S3 buckets have policies that allow public access. "
                                   "Public access to S3 buckets can lead to data leakage.",
                },
                {
                    "check_id": "s3_account_level_public_access_blocks",
                    "service": "s3",
                    "title": "Ensure S3 Account Level Public Access Block is enabled",
                    "severity": "critical",
                    "description": "Check if account level S3 Block Public Access is configured.",
                },
                {
                    "check_id": "s3_bucket_server_side_encryption",
                    "service": "s3",
                    "title": "Ensure S3 Buckets have server-side encryption (SSE) enabled",
                    "severity": "high",
                    "description": "Server-side encryption protects data at rest in S3 buckets.",
                },
                {
                    "check_id": "s3_bucket_versioning",
                    "service": "s3",
                    "title": "Ensure S3 Bucket Versioning is enabled",
                    "severity": "medium",
                    "description": "Versioning helps recover from unintended user actions and application failures.",
                },
                {
                    "check_id": "s3_bucket_logging_enabled",
                    "service": "s3",
                    "title": "Ensure S3 bucket access logging is enabled on the S3 bucket",
                    "severity": "medium",
                    "description": "S3 access logging provides records for each request made to your S3 bucket.",
                },
                {
                    "check_id": "s3_bucket_policy_public_write_access",
                    "service": "s3",
                    "title": "Ensure the S3 Bucket does not have a bucket policy with write access",
                    "severity": "critical",
                    "description": "Checks if S3 bucket policies allow public write access.",
                },
            ],
            "control_mapping_ids": [
                "cis_aws_foundations_1.4_2.1.1",
                "cis_aws_foundations_1.4_2.1.2",
                "pci_dss_3.2.1_s3.1",
                "nist_800_53_rev5_sc_13",
                "aws_well_architected_sec_01",
            ],
            "maturity_capability_ids": [
                "data_protection_at_rest",
                "access_control_public_exposure",
                "encryption_management",
                "logging_and_monitoring",
                "secure_configuration",
            ],
        }
    },
    "diagnostics": {
        "retrieval_time_ms": 47,
        "total_candidates": 12,
        "returned": 6,
        "retrieval_mode": "hybrid",
        "lexical_hits": 8,
        "vector_hits": 10,
        "rrf_merged": 12,
    },
    "_meta": {
        "confidence": "high",
        "review_recommended": False,
        "corpus_version": "prowler_3.12",
    },
}

S3_RETRIEVE_CHECKS_FALLBACK = {
    "results": [
        {
            "doc_id": "check:s3_bucket_public_access",
            "score": 0.912,
            "metadata": {
                "service": "s3",
                "title": "S3 Bucket Public Access",
                "severity": "critical",
                "category": "security",
            },
        },
        {
            "doc_id": "check:s3_bucket_server_side_encryption",
            "score": 0.784,
            "metadata": {
                "service": "s3",
                "title": "S3 Server-Side Encryption",
                "severity": "high",
                "category": "encryption",
            },
        },
        {
            "doc_id": "check:iam_user_mfa_enabled",
            "score": 0.321,
            "metadata": {
                "service": "iam",
                "title": "IAM User MFA Enabled",
                "severity": "critical",
                "category": "identity",
            },
        },
    ],
}


# ============================================================
# TEST 1: Hien thi full build_context response + parsed candidates + maturity context
# ============================================================

class TestInspectBuildContextFlow:
    """
    Hien thi toan bo data flow khi PlanningAgent goi build_context(consumer="planning").

    Shows:
      1. Raw RAG API response (full JSON)
      2. Parsed candidates (what agent extracts)
      3. Maturity context string (what LLM re-ranking receives)
      4. Confidence level va branching decision
      5. RERANK_PROMPT final (context dua cho LLM)
    """

    def test_inspect_build_context_full_flow(self, agent, rag_client):
        """Hien thi day du: RAG raw -> parsed -> context -> LLM prompt."""

        user_request = "Check if any S3 buckets have public access enabled"
        target_service = "s3"

        _header("PLANNING AGENT -- build_context INSPECTION")
        print(f"  User Request : {user_request}")
        print(f"  Target Service: {target_service}")

        # -- Step 1: RAG Raw Response --
        rag_client.build_context.return_value = S3_BUILD_CONTEXT_RAW_RESPONSE
        _section("STEP 1: Raw RAG API Response (build_context)")
        _json_pretty(S3_BUILD_CONTEXT_RAW_RESPONSE, "RAG build_context(consumer='planning') response")

        # -- Step 2: Agent parses response --
        retrieval = agent._retrieve_candidates("s3 public access", target_service)

        _section("STEP 2: Agent Parsed Result (_retrieve_candidates)")
        _json_pretty({
            "source": retrieval["source"],
            "confidence": retrieval["confidence"],
            "num_candidates": len(retrieval["candidates"]),
        }, "Retrieval metadata")

        _json_pretty(retrieval["candidates"], "Parsed candidates (check_id, title, severity, service, score)")

        _text_block(retrieval["maturity_context"] or "(empty)", "Maturity context string (for LLM prompt)")

        # -- Step 3: Re-ranking prompt construction --
        _section("STEP 3: RERANK_PROMPT sent to LLM")

        candidates_json = json.dumps(retrieval["candidates"], indent=2, ensure_ascii=False)
        maturity_ctx = retrieval["maturity_context"]

        filled_prompt = RERANK_PROMPT.format(
            request=user_request,
            candidates=candidates_json,
            maturity_context=maturity_ctx,
        )
        _text_block(filled_prompt, "Full RERANK_PROMPT (what LLM receives)")

        # -- Step 4: Confidence branching --
        _section("STEP 4: Confidence Branching Decision")
        confidence = retrieval["confidence"]
        source = retrieval["source"]
        if confidence == "low" and source == "build_context":
            decision = "-> GROUP SCAN (low confidence from build_context)"
        elif not retrieval["candidates"]:
            decision = "-> GROUP SCAN (no candidates)"
        else:
            decision = f"-> PROCEED to LLM re-ranking ({len(retrieval['candidates'])} candidates)"

        print(f"    Confidence : {confidence}")
        print(f"    Source     : {source}")
        print(f"    Decision   : {decision}")

        # Assertions (minimal -- the point is visual inspection)
        assert retrieval["source"] == "build_context"
        assert retrieval["confidence"] == "high"
        assert len(retrieval["candidates"]) >= 3
        assert retrieval["maturity_context"] != ""
        print(f"\n  [PASS] build_context flow: {len(retrieval['candidates'])} candidates, "
              f"confidence={confidence}, maturity_context={len(retrieval['maturity_context'])} chars")


# ============================================================
# TEST 2: Hien thi fallback flow -- build_context fail -> retrieve_checks
# ============================================================

class TestInspectFallbackFlow:
    """
    Hien thi toan bo data flow khi build_context fail va agent fallback sang retrieve_checks.

    Shows:
      1. build_context returns None (failure)
      2. retrieve_checks raw response
      3. Service filtering (loai bo iam result khi query s3)
      4. Parsed candidates sau filtering
      5. So sanh candidates giua 2 paths
    """

    def test_inspect_fallback_to_retrieve_checks(self, agent, rag_client):
        """Hien thi day du fallback flow va service filtering."""

        user_request = "Scan S3 encryption settings"
        target_service = "s3"

        _header("PLANNING AGENT -- FALLBACK FLOW INSPECTION")
        print(f"  User Request : {user_request}")
        print(f"  Target Service: {target_service}")

        # -- Step 1: build_context fails --
        rag_client.build_context.return_value = None
        rag_client.retrieve_checks.return_value = S3_RETRIEVE_CHECKS_FALLBACK

        _section("STEP 1: build_context FAILED (returned None)")
        print("    -> Agent falls back to retrieve_checks()")

        # -- Step 2: retrieve_checks raw response --
        _section("STEP 2: Raw retrieve_checks Response")
        _json_pretty(S3_RETRIEVE_CHECKS_FALLBACK, "retrieve_checks() raw response")

        print(f"\n    Total results: {len(S3_RETRIEVE_CHECKS_FALLBACK['results'])}")
        print("    Services in results:")
        for r in S3_RETRIEVE_CHECKS_FALLBACK["results"]:
            svc = r["metadata"]["service"]
            score = r["score"]
            title = r["metadata"]["title"]
            marker = " <-- WILL BE FILTERED (wrong service)" if svc != target_service else ""
            print(f"      [{svc}] score={score:.3f} | {title}{marker}")

        # -- Step 3: Agent parses + filters --
        retrieval = agent._retrieve_candidates("s3 encryption", target_service)

        _section("STEP 3: Parsed Candidates (after service filtering)")
        _json_pretty(retrieval["candidates"], "Filtered candidates")
        _json_pretty({
            "source": retrieval["source"],
            "confidence": retrieval["confidence"],
            "maturity_context": retrieval["maturity_context"] or "(empty -- not available in fallback path)",
        }, "Retrieval metadata")

        # -- Step 4: Comparison --
        _section("STEP 4: Comparison -- build_context vs retrieve_checks")
        print("    | Aspect              | build_context     | retrieve_checks     |")
        print("    |---------------------|-------------------|---------------------|")
        print("    | Maturity context    | Yes (rich)        | No (empty)          |")
        print("    | Confidence          | From _meta        | Default 'medium'    |")
        print("    | Control mappings    | Yes               | No                  |")
        print("    | Service filtering   | By RAG server     | By agent (client)   |")
        print("    | Score source        | Fixed 1.0         | RAG relevance score |")

        filtered_count = len(retrieval["candidates"])
        raw_count = len(S3_RETRIEVE_CHECKS_FALLBACK["results"])
        print(f"\n    Raw results: {raw_count} -> After filtering: {filtered_count} "
              f"(removed {raw_count - filtered_count} wrong-service results)")

        assert retrieval["source"] == "retrieve_checks"
        assert retrieval["maturity_context"] == ""
        assert all(c["service"] == "s3" for c in retrieval["candidates"])
        print(f"\n  [PASS] Fallback flow: {filtered_count} candidates after service filtering, "
              f"no maturity context (expected)")


# ============================================================
# TEST 3: Hien thi low confidence -> group scan decision
# ============================================================

class TestInspectLowConfidenceDecision:
    """
    Hien thi decision logic khi RAG tra ve low confidence.

    Shows:
      1. RAG response voi low confidence
      2. retrieval dict da parse
      3. _rerank_and_select decision (group scan vs re-ranking)
      4. Final output plan
    """

    def test_inspect_low_confidence_group_scan(self, agent, rag_client):
        """Hien thi day du flow low confidence -> group scan."""

        user_request = "check something on S3"
        target_service = "s3"

        _header("PLANNING AGENT -- LOW CONFIDENCE DECISION INSPECTION")
        print(f"  User Request : {user_request}")
        print(f"  Target Service: {target_service}")

        # RAG returns low confidence
        low_confidence_response = {
            "payload": {
                "planning_bundle": {
                    "related_findings": [
                        {
                            "check_id": "s3_bucket_versioning",
                            "service": "s3",
                            "title": "Ensure S3 Bucket Versioning is enabled",
                            "severity": "medium",
                            "description": "Versioning helps recover from unintended actions.",
                        },
                    ],
                    "control_mapping_ids": [],
                    "maturity_capability_ids": [],
                }
            },
            "diagnostics": {
                "retrieval_time_ms": 132,
                "total_candidates": 3,
                "returned": 1,
                "retrieval_mode": "hybrid",
                "lexical_hits": 1,
                "vector_hits": 2,
            },
            "_meta": {
                "confidence": "low",
                "review_recommended": True,
                "corpus_version": "prowler_3.12",
            },
        }

        _section("STEP 1: RAG Response (LOW confidence)")
        _json_pretty(low_confidence_response, "build_context response")

        print("\n    Key indicators of low confidence:")
        diag = low_confidence_response["diagnostics"]
        meta = low_confidence_response["_meta"]
        print(f"      - confidence      : {meta['confidence']}")
        print(f"      - review_recommended: {meta['review_recommended']}")
        print(f"      - retrieval_time  : {diag['retrieval_time_ms']}ms (higher than normal ~50ms)")
        print(f"      - total_candidates: {diag['total_candidates']} (few matches)")
        print(f"      - returned        : {diag['returned']} (out of {diag['total_candidates']})")

        # -- Step 2: Agent parses --
        rag_client.build_context.return_value = low_confidence_response
        retrieval = agent._retrieve_candidates("s3 something", target_service)

        _section("STEP 2: Parsed Retrieval Result")
        _json_pretty({
            "source": retrieval["source"],
            "confidence": retrieval["confidence"],
            "num_candidates": len(retrieval["candidates"]),
            "candidates": retrieval["candidates"],
            "maturity_context": retrieval["maturity_context"] or "(empty)",
        }, "retrieval dict")

        # -- Step 3: _rerank_and_select decision --
        _section("STEP 3: Re-rank Decision Logic")
        result = agent._rerank_and_select(user_request, retrieval, target_service)

        confidence = retrieval["confidence"]
        source = retrieval["source"]

        print(f"    if confidence == 'low' and source == 'build_context':")
        print(f"       confidence = '{confidence}' -> {'TRUE' if confidence == 'low' else 'FALSE'}")
        print(f"       source     = '{source}' -> {'TRUE' if source == 'build_context' else 'FALSE'}")
        print(f"       MATCH      = {confidence == 'low' and source == 'build_context'}")
        print(f"\n    Decision: {'GROUP SCAN (expand coverage)' if result['groups_to_scan'] else 'RE-RANKING'}")

        # -- Step 4: Final output --
        _section("STEP 4: Final Output Plan")
        _json_pretty(result, "PlanningAgent output")

        print("\n    Explanation:")
        if result["groups_to_scan"]:
            print(f"      RAG khong tu tin (confidence=low) -> Mo rong scan toan bo service '{target_service}'")
            print(f"      Thay vi chon 1 check cu the, scan tat ca checks cua service")
            print(f"      Day la trade-off: Recall cao hon (khong bo sot) nhung scan lau hon")
        else:
            print(f"      RAG tu tin -> Chon {len(result['checks_to_scan'])} checks cu the")

        assert result["groups_to_scan"] == [target_service]
        assert result["checks_to_scan"] == []
        print(f"\n  [PASS] Low confidence -> group scan for '{target_service}' (correct behavior)")
