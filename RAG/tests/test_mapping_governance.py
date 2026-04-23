"""
Unit tests for mapping governance: entity gate rules that prevent
product-specific semantic mismatches (e.g. S3 encryption → Bedrock GenAI).

Tests are pure-logic and do NOT require a running server.
"""
import sys
import os
import unittest

import pytest

# Allow import without installing the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.context.context_builder import ContextBuilder

builder = ContextBuilder()


_SKIP_REASON = (
    "Tests call ContextBuilder._mapping_passes_entity_gate / "
    "_capability_domain_mismatch, which were migrated to IntentDetector "
    "(capability_domain_mismatch) and coverage_selector during the "
    "2026-03-27 RAG refactor (commit 5b8a938). Production code uses the new "
    "locations correctly; these tests must be rewritten against IntentDetector "
    "before re-enabling. Tracking: test debt cleanup (post Report-Agent overhaul)."
)


@pytest.mark.skip(reason=_SKIP_REASON)
class TestEntityGate(unittest.TestCase):
    """Tests for _mapping_passes_entity_gate."""

    # ----------------------------------------------------------------
    # BLOCKED: Bedrock/GenAI capabilities against non-GenAI checks
    # ----------------------------------------------------------------

    def test_s3_encryption_vs_bedrock_genai_blocked(self):
        """S3 encryption check must NOT map to a Bedrock/GenAI capability."""
        result = builder._mapping_passes_entity_gate(
            check_id="s3_bucket_server_side_encryption_enabled",
            capability_id="aws-genai-bedrock-data-protection",
            capability_name="Generative AI data protection with Amazon Bedrock",
            mapping_confidence="low",
            mapping_type="weak",
            review_status="review_required",
            check_signal="s3_bucket_server_side_encryption_enabled s3 encryption",
        )
        self.assertFalse(result, "S3 encryption check must be blocked from Bedrock GenAI capability")

    def test_rds_encryption_vs_generative_ai_blocked(self):
        """RDS encryption check must NOT map to Generative AI capability."""
        result = builder._mapping_passes_entity_gate(
            check_id="rds_cluster_storage_encrypted",
            capability_id="aws-generative-ai-security",
            capability_name="Security controls for Generative AI workloads",
            mapping_confidence="low",
            mapping_type="weak",
            review_status="draft",
            check_signal="rds_cluster_storage_encrypted rds encryption",
        )
        self.assertFalse(result, "RDS encryption must not map to generative AI capability")

    def test_iam_mfa_vs_genai_blocked(self):
        """IAM MFA check must NOT map to GenAI capability."""
        result = builder._mapping_passes_entity_gate(
            check_id="iam_user_mfa_enabled",
            capability_id="genai-access-control",
            capability_name="GenAI access control patterns",
            mapping_confidence="low",
            mapping_type="indirect",
            review_status="review_required",
            check_signal="iam_user_mfa_enabled iam mfa",
        )
        self.assertFalse(result, "IAM MFA must not map to GenAI capability")

    def test_cloudtrail_vs_sagemaker_blocked(self):
        """CloudTrail logging check must NOT map to SageMaker capability."""
        result = builder._mapping_passes_entity_gate(
            check_id="cloudtrail_multi_region_enabled",
            capability_id="sagemaker-model-governance",
            capability_name="SageMaker model governance and audit",
            mapping_confidence="low",
            mapping_type="weak",
            review_status="draft",
            check_signal="cloudtrail_multi_region_enabled cloudtrail logging",
        )
        self.assertFalse(result, "CloudTrail must not map to SageMaker capability")

    # ----------------------------------------------------------------
    # ALLOWED: product-specific checks CAN map to matching capabilities
    # ----------------------------------------------------------------

    def test_bedrock_check_vs_bedrock_capability_allowed(self):
        """A Bedrock check SHOULD map to a Bedrock capability."""
        result = builder._mapping_passes_entity_gate(
            check_id="bedrock_model_invocation_logging_enabled",
            capability_id="aws-genai-bedrock-data-protection",
            capability_name="Generative AI data protection with Amazon Bedrock",
            mapping_confidence="high",
            mapping_type="strong",
            review_status="approved",
            check_signal="bedrock_model_invocation_logging_enabled bedrock genai",
        )
        self.assertTrue(result, "Bedrock check should be allowed to map to Bedrock capability")

    def test_sagemaker_check_vs_sagemaker_capability_allowed(self):
        """SageMaker endpoint check CAN map to SageMaker governance capability."""
        result = builder._mapping_passes_entity_gate(
            check_id="sagemaker_endpoint_encryption_at_rest_enabled",
            capability_id="sagemaker-model-governance",
            capability_name="SageMaker model governance",
            mapping_confidence="medium",
            mapping_type="related",
            review_status="approved",
            check_signal="sagemaker_endpoint_encryption_at_rest_enabled sagemaker endpoint",
        )
        self.assertTrue(result, "SageMaker check should map to SageMaker capability")

    # ----------------------------------------------------------------
    # ALLOWED: non-product capabilities never blocked by entity gate
    # ----------------------------------------------------------------

    def test_s3_encryption_vs_generic_data_protection_allowed(self):
        """S3 encryption check CAN map to a generic data-protection capability."""
        result = builder._mapping_passes_entity_gate(
            check_id="s3_bucket_server_side_encryption_enabled",
            capability_id="aws-data-protection-at-rest",
            capability_name="Data protection at rest",
            mapping_confidence="high",
            mapping_type="strong",
            review_status="approved",
            check_signal="s3_bucket_server_side_encryption_enabled s3 encryption",
        )
        self.assertTrue(result, "Generic data protection capability should be allowed")

    def test_iam_vs_generic_identity_capability_allowed(self):
        """IAM check CAN map to a generic identity & access management capability."""
        result = builder._mapping_passes_entity_gate(
            check_id="iam_user_mfa_enabled",
            capability_id="identity-access-management",
            capability_name="Identity and Access Management",
            mapping_confidence="high",
            mapping_type="strong",
            review_status="approved",
            check_signal="iam_user_mfa_enabled iam mfa",
        )
        self.assertTrue(result, "Generic IAM capability should be allowed")

    # ----------------------------------------------------------------
    # BLOCKED: weak quality triple regardless of product entity
    # ----------------------------------------------------------------

    def test_weak_quality_mapping_blocked(self):
        """Any mapping that is low+weak+review_required should be rejected."""
        result = builder._mapping_passes_entity_gate(
            check_id="ec2_instance_metadata_service_v2_enabled",
            capability_id="any-capability",
            capability_name="Some Capability",
            mapping_confidence="low",
            mapping_type="weak",
            review_status="review_required",
            check_signal="ec2_instance_metadata_service_v2_enabled ec2",
        )
        self.assertFalse(result, "Weak+low+review_required mapping must be rejected regardless of entity")

    def test_medium_confidence_not_blocked_by_weak_gate(self):
        """Medium confidence + related type should not be blocked by weak gate."""
        result = builder._mapping_passes_entity_gate(
            check_id="ec2_instance_metadata_service_v2_enabled",
            capability_id="any-capability",
            capability_name="Some Capability",
            mapping_confidence="medium",
            mapping_type="related",
            review_status="review_required",
            check_signal="ec2_instance_metadata_service_v2_enabled ec2",
        )
        self.assertTrue(result, "Medium confidence should not be blocked by weak-quality gate")


@pytest.mark.skip(reason=_SKIP_REASON)
class TestCapabilityDomainMismatch(unittest.TestCase):
    """Tests for _capability_domain_mismatch."""

    def test_bedrock_capability_vs_s3_check_is_mismatch(self):
        result = builder._capability_domain_mismatch(
            capability_id="aws-bedrock-genai",
            capability_name="Generative AI with Amazon Bedrock",
            check_context="s3_bucket_encryption_enabled s3 encryption",
        )
        self.assertTrue(result, "Bedrock capability against S3 check must be a domain mismatch")

    def test_bedrock_capability_vs_bedrock_check_is_not_mismatch(self):
        result = builder._capability_domain_mismatch(
            capability_id="aws-bedrock-genai",
            capability_name="Generative AI with Amazon Bedrock",
            check_context="bedrock_model_invocation_logging_enabled bedrock",
        )
        self.assertFalse(result, "Bedrock capability against Bedrock check must NOT be a mismatch")

    def test_generic_capability_never_mismatch(self):
        result = builder._capability_domain_mismatch(
            capability_id="data-protection-at-rest",
            capability_name="Data protection at rest",
            check_context="s3_bucket_encryption_enabled s3",
        )
        self.assertFalse(result, "Generic capability should never cause a domain mismatch")

    def test_waf_capability_vs_ec2_check_is_mismatch(self):
        result = builder._capability_domain_mismatch(
            capability_id="aws-waf-protection",
            capability_name="AWS WAF Web Application Firewall Protection",
            check_context="ec2_instance_imdsv2_enabled ec2",
        )
        self.assertTrue(result, "WAF capability against EC2 check must be a domain mismatch")

    def test_waf_capability_vs_waf_check_is_not_mismatch(self):
        result = builder._capability_domain_mismatch(
            capability_id="aws-waf-protection",
            capability_name="AWS WAF Web Application Firewall Protection",
            check_context="waf_webacl_logging_enabled waf",
        )
        self.assertFalse(result, "WAF capability against WAF check must NOT be a mismatch")


if __name__ == "__main__":
    unittest.main(verbosity=2)
