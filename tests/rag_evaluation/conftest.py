"""
Shared Fixtures cho RAG Integration Quality Tests
===================================================
Cung cap mock data, fixtures, va helper functions dung chung
cho toan bo test suite danh gia chat luong RAG.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from pdca.agents.shared.rag_client import RAGClient


# ============================================================
# RAG Client Fixtures
# ============================================================

@pytest.fixture
def mock_rag_client():
    """RAGClient mock — khong goi HTTP that."""
    client = MagicMock(spec=RAGClient)
    client.is_healthy.return_value = True
    return client


@pytest.fixture
def mock_rag_client_unhealthy():
    """RAGClient mock — luon tra ve unhealthy."""
    client = MagicMock(spec=RAGClient)
    client.is_healthy.return_value = False
    client.build_context.return_value = None
    client.retrieve_checks.return_value = None
    client.retrieve_maturity.return_value = None
    client.resolve_mapping.return_value = None
    return client


# ============================================================
# PlanningAgent Fixtures
# ============================================================

@pytest.fixture
def planning_agent(mock_rag_client):
    """PlanningAgent with mocked LLM + RAGClient."""
    from pdca.agents.planning_agent import PlanningAgent
    with patch("pdca.agents.planning_agent.ChatOllama") as MockLLM:
        mock_llm = MagicMock()
        MockLLM.return_value = mock_llm
        agent = PlanningAgent(
            model_name="test-model",
            base_url="http://localhost:11434",
            rag_client=mock_rag_client,
        )
        agent.llm = mock_llm
        yield agent


@pytest.fixture
def planning_agent_no_rag():
    """PlanningAgent WITHOUT RAGClient (degraded mode)."""
    from pdca.agents.planning_agent import PlanningAgent
    with patch("pdca.agents.planning_agent.ChatOllama") as MockLLM:
        mock_llm = MagicMock()
        MockLLM.return_value = mock_llm
        agent = PlanningAgent(
            model_name="test-model",
            base_url="http://localhost:11434",
            rag_client=None,
        )
        agent.llm = mock_llm
        yield agent


# ============================================================
# RiskEvaluationAgent Fixtures
# ============================================================

@pytest.fixture
def risk_agent(mock_rag_client):
    """RiskEvaluationAgent with mocked LLM + RAGClient."""
    from pdca.agents.risk_evaluation_agent import RiskEvaluationAgent
    with patch("pdca.agents.risk_evaluation_agent.ChatOllama") as MockLLM:
        mock_llm = MagicMock()
        MockLLM.return_value = mock_llm
        agent = RiskEvaluationAgent(
            model_name="test-model",
            api_key="test-key",
            base_url="http://localhost:11434",
            rag_client=mock_rag_client,
        )
        agent.llm = mock_llm
        yield agent


@pytest.fixture
def risk_agent_no_rag():
    """RiskEvaluationAgent WITHOUT RAGClient (degraded mode)."""
    from pdca.agents.risk_evaluation_agent import RiskEvaluationAgent
    with patch("pdca.agents.risk_evaluation_agent.ChatOllama") as MockLLM:
        mock_llm = MagicMock()
        MockLLM.return_value = mock_llm
        agent = RiskEvaluationAgent(
            model_name="test-model",
            api_key="test-key",
            base_url="http://localhost:11434",
            rag_client=None,
        )
        agent.llm = mock_llm
        yield agent


# ============================================================
# Mock Data: RAG Responses
# ============================================================

@pytest.fixture
def planning_bundle_s3():
    """Mock PlanningBundle response cho S3 service."""
    return {
        "payload": {
            "planning_bundle": {
                "related_findings": [
                    {"check_id": "s3_bucket_public_access", "service": "s3",
                     "title": "Ensure S3 bucket public access is blocked", "severity": "critical"},
                    {"check_id": "s3_bucket_server_side_encryption", "service": "s3",
                     "title": "Ensure S3 bucket has server-side encryption enabled", "severity": "high"},
                    {"check_id": "s3_bucket_versioning", "service": "s3",
                     "title": "Ensure S3 bucket versioning is enabled", "severity": "medium"},
                    {"check_id": "s3_bucket_logging_enabled", "service": "s3",
                     "title": "Ensure S3 bucket access logging is enabled", "severity": "medium"},
                    {"check_id": "s3_bucket_policy_public_write_access", "service": "s3",
                     "title": "Ensure S3 bucket policy does not grant public write", "severity": "critical"},
                ],
                "control_mapping_ids": [
                    "cis_aws_1.4_2.1.1", "cis_aws_1.4_2.1.2",
                    "pci_dss_3.2.1_s3.1", "nist_800_53_sc_13",
                ],
                "maturity_capability_ids": [
                    "data_protection", "access_control",
                    "encryption_at_rest", "logging_monitoring",
                ],
            }
        },
        "diagnostics": {"retrieval_time_ms": 45, "total_results": 5},
        "_meta": {"confidence": "high", "review_recommended": False},
    }


@pytest.fixture
def planning_bundle_iam():
    """Mock PlanningBundle response cho IAM service."""
    return {
        "payload": {
            "planning_bundle": {
                "related_findings": [
                    {"check_id": "iam_user_mfa_enabled", "service": "iam",
                     "title": "Ensure MFA is enabled for all IAM users", "severity": "critical"},
                    {"check_id": "iam_root_mfa_enabled", "service": "iam",
                     "title": "Ensure MFA is enabled for root account", "severity": "critical"},
                    {"check_id": "iam_password_policy_minimum_length", "service": "iam",
                     "title": "Ensure IAM password policy requires minimum length", "severity": "medium"},
                    {"check_id": "iam_no_root_access_key", "service": "iam",
                     "title": "Ensure no root account access key exists", "severity": "high"},
                    {"check_id": "iam_user_accesskey_unused", "service": "iam",
                     "title": "Ensure unused IAM access keys are removed", "severity": "medium"},
                ],
                "control_mapping_ids": [
                    "cis_aws_1.4_1.5", "cis_aws_1.4_1.10",
                    "pci_dss_3.2.1_iam.1",
                ],
                "maturity_capability_ids": [
                    "identity_management", "access_control",
                    "credential_management",
                ],
            }
        },
        "diagnostics": {"retrieval_time_ms": 38, "total_results": 5},
        "_meta": {"confidence": "high", "review_recommended": False},
    }


@pytest.fixture
def planning_bundle_low_confidence():
    """Mock PlanningBundle voi low confidence."""
    return {
        "payload": {
            "planning_bundle": {
                "related_findings": [
                    {"check_id": "s3_bucket_versioning", "service": "s3",
                     "title": "Versioning", "severity": "medium"},
                ],
                "control_mapping_ids": [],
                "maturity_capability_ids": [],
            }
        },
        "diagnostics": {"retrieval_time_ms": 120, "total_results": 1},
        "_meta": {"confidence": "low", "review_recommended": True},
    }


@pytest.fixture
def risk_bundle_response():
    """Mock RiskBundle response cho Risk Agent."""
    return {
        "payload": {
            "risk_bundle": {
                "related_findings": [
                    {"check_id": "s3_bucket_public_access", "severity": "critical",
                     "title": "S3 Bucket Public Access Block"},
                    {"check_id": "iam_user_mfa_enabled", "severity": "critical",
                     "title": "IAM User MFA Enabled"},
                    {"check_id": "s3_bucket_server_side_encryption", "severity": "high",
                     "title": "S3 Server Side Encryption"},
                ],
                "control_mapping": [
                    {"check_id": "s3_bucket_public_access", "capability_id": "cis_aws_2.1.1"},
                    {"check_id": "s3_bucket_public_access", "capability_id": "pci_dss_s3.1"},
                    {"check_id": "iam_user_mfa_enabled", "capability_id": "cis_aws_1.10"},
                    {"check_id": "s3_bucket_server_side_encryption", "capability_id": "nist_sc_13"},
                ],
            }
        },
        "diagnostics": {"retrieval_time_ms": 55},
        "_meta": {"confidence": "high"},
    }


@pytest.fixture
def risk_bundle_medium_confidence():
    """Mock RiskBundle voi medium confidence."""
    return {
        "payload": {
            "risk_bundle": {
                "related_findings": [
                    {"check_id": "ec2_instance_public_ip", "severity": "high",
                     "title": "EC2 Instance Public IP"},
                ],
                "control_mapping": [],
            }
        },
        "diagnostics": {"retrieval_time_ms": 80},
        "_meta": {"confidence": "medium"},
    }


# ============================================================
# Mock Data: Normalized Findings (input cho Risk Agent)
# ============================================================

@pytest.fixture
def sample_fail_findings():
    """Tap hop FAIL findings da normalize — dung cho Risk Agent tests."""
    return [
        {
            "status": "FAIL",
            "event_code": "s3_bucket_public_access",
            "check_id": "s3_bucket_public_access",
            "service": "s3",
            "resource_id": "arn:aws:s3:::my-public-bucket",
            "region": "us-east-1",
            "description": "S3 bucket my-public-bucket has public access enabled, allowing anyone to read objects",
            "severity": "High",
            "remediation_text": "Enable S3 Block Public Access settings for the bucket",
        },
        {
            "status": "FAIL",
            "event_code": "iam_user_mfa_enabled",
            "check_id": "iam_user_mfa_enabled",
            "service": "iam",
            "resource_id": "arn:aws:iam::123456789012:user/admin",
            "region": "global",
            "description": "IAM user admin does not have MFA enabled, increasing risk of unauthorized access",
            "severity": "Critical",
            "remediation_text": "Enable MFA for the IAM user",
        },
        {
            "status": "FAIL",
            "event_code": "s3_bucket_server_side_encryption",
            "check_id": "s3_bucket_server_side_encryption",
            "service": "s3",
            "resource_id": "arn:aws:s3:::my-data-bucket",
            "region": "us-west-2",
            "description": "S3 bucket my-data-bucket does not have default encryption enabled",
            "severity": "Medium",
            "remediation_text": "Enable default encryption using AES-256 or AWS KMS",
        },
    ]


@pytest.fixture
def sample_mixed_findings(sample_fail_findings):
    """Mix FAIL + PASS findings — test filtering logic."""
    return sample_fail_findings + [
        {
            "status": "PASS",
            "event_code": "s3_bucket_versioning",
            "check_id": "s3_bucket_versioning",
            "service": "s3",
            "resource_id": "arn:aws:s3:::my-versioned-bucket",
            "region": "us-east-1",
            "description": "S3 bucket has versioning enabled",
            "severity": "Info",
        },
        {
            "status": "PASS",
            "event_code": "ec2_instance_public_ip",
            "check_id": "ec2_instance_public_ip",
            "service": "ec2",
            "resource_id": "i-0123456789abcdef0",
            "region": "us-east-1",
            "description": "EC2 instance does not have a public IP",
            "severity": "Info",
        },
    ]


@pytest.fixture
def large_fail_findings():
    """25 FAIL findings — test batch chunking (>20 ids)."""
    findings = []
    services = ["s3", "iam", "ec2", "rds", "vpc"]
    checks_per_service = {
        "s3": ["bucket_public_access", "bucket_versioning", "bucket_encryption",
               "bucket_logging", "bucket_policy_public"],
        "iam": ["user_mfa_enabled", "root_mfa_enabled", "password_policy",
                "no_root_access_key", "user_accesskey_unused"],
        "ec2": ["instance_public_ip", "security_group_open", "ebs_encryption",
                "instance_imdsv2", "security_group_ssh"],
        "rds": ["instance_encryption", "public_access", "backup_enabled",
                "multi_az", "minor_version_upgrade"],
        "vpc": ["flow_logs_enabled", "default_security_group", "subnet_auto_assign",
                "endpoint_exposed", "peering_dns_resolution"],
    }
    for svc in services:
        for check_name in checks_per_service[svc]:
            check_id = f"{svc}_{check_name}"
            findings.append({
                "status": "FAIL",
                "event_code": check_id,
                "check_id": check_id,
                "service": svc,
                "resource_id": f"arn:aws:{svc}:::test-resource-{check_name}",
                "region": "us-east-1",
                "description": f"Finding for {check_id}",
                "severity": "High",
                "remediation_text": f"Fix {check_id}",
            })
    return findings


# ============================================================
# Test Scenarios
# ============================================================

PLANNING_TEST_SCENARIOS = [
    {
        "id": "SC-P01",
        "name": "S3 Public Access Check",
        "request": "Check if any S3 buckets have public access enabled",
        "expected_service": "s3",
        "expected_check_ids": ["s3_bucket_public_access", "s3_bucket_policy_public_write_access"],
        "expected_min_candidates": 2,
    },
    {
        "id": "SC-P02",
        "name": "IAM MFA Verification",
        "request": "Verify MFA is enabled for all IAM users",
        "expected_service": "iam",
        "expected_check_ids": ["iam_user_mfa_enabled", "iam_root_mfa_enabled"],
        "expected_min_candidates": 2,
    },
    {
        "id": "SC-P03",
        "name": "S3 Encryption Audit",
        "request": "Audit encryption settings on S3 buckets",
        "expected_service": "s3",
        "expected_check_ids": ["s3_bucket_server_side_encryption"],
        "expected_min_candidates": 1,
    },
    {
        "id": "SC-P04",
        "name": "Group Scan Request",
        "request": "scan all s3 checks",
        "expected_service": "s3",
        "is_group_scan": True,
    },
    {
        "id": "SC-P05",
        "name": "Explicit Check IDs",
        "request": "run s3_bucket_public_access and iam_user_mfa_enabled",
        "expected_check_ids": ["s3_bucket_public_access", "iam_user_mfa_enabled"],
        "is_fast_track": True,
    },
]

RISK_TEST_SCENARIOS = [
    {
        "id": "SC-R01",
        "name": "Critical Public Access",
        "finding": {
            "status": "FAIL", "event_code": "s3_bucket_public_access",
            "check_id": "s3_bucket_public_access", "service": "s3",
            "resource_id": "my-public-bucket", "region": "us-east-1",
            "description": "S3 bucket has public access enabled",
            "severity": "High", "remediation_text": "Block public access",
        },
        "rag_context": {
            "severity": "critical", "title": "S3 Public Access Block",
            "mappings": ["cis_aws_2.1.1", "pci_dss_s3.1"],
        },
        "expected_severity_range": ["Critical", "High"],
        "expected_score_range": (7, 10),
    },
    {
        "id": "SC-R02",
        "name": "Medium Logging Issue",
        "finding": {
            "status": "FAIL", "event_code": "s3_bucket_logging_enabled",
            "check_id": "s3_bucket_logging_enabled", "service": "s3",
            "resource_id": "my-log-bucket", "region": "us-east-1",
            "description": "S3 bucket does not have access logging enabled",
            "severity": "Medium", "remediation_text": "Enable access logging",
        },
        "rag_context": {
            "severity": "medium", "title": "S3 Access Logging",
            "mappings": ["cis_aws_2.1.3"],
        },
        "expected_severity_range": ["Medium", "Low"],
        "expected_score_range": (3, 6),
    },
    {
        "id": "SC-R03",
        "name": "No RAG Context Available",
        "finding": {
            "status": "FAIL", "event_code": "custom_check_xyz",
            "check_id": "custom_check_xyz", "service": "custom",
            "resource_id": "some-resource", "region": "us-east-1",
            "description": "Custom check failed",
            "severity": "Medium", "remediation_text": "Fix custom issue",
        },
        "rag_context": {},
        "expected_severity_range": ["Critical", "High", "Medium", "Low"],
        "expected_score_range": (0, 10),
    },
]
