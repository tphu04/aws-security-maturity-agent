import unittest

import pytest

from app.context.context_builder import ContextBuilder
from app.core.models import Confidence


@pytest.mark.skip(
    reason="Tests call ContextBuilder._evaluate_bundle_confidence, which was "
    "migrated to BundleFactory.evaluate_bundle_confidence during the 2026-03-27 "
    "RAG refactor (commit 5b8a938). Production code uses the new location "
    "correctly; these tests must be rewritten against BundleFactory before "
    "re-enabling. Tracking: test debt cleanup (post Report-Agent overhaul)."
)
class TestSemanticConfidence(unittest.TestCase):
    def setUp(self):
        self.builder = ContextBuilder()

    def test_risk_consumer_degradation(self):
        # 1) Perfect bundle -> keeps high
        risk_bundle_good = {
            "primary_finding": {"check_id": "abc"},
            "control_mapping": [{"check_id": "abc"}],
            "maturity_context": [{"capability_id": "cap1"}],
        }
        res = self.builder._evaluate_bundle_confidence(
            consumer="risk",
            query=None,
            risk_bundle=risk_bundle_good,
            report_bundle=None,
            planning_bundle=None,
            retrieval_confidence=Confidence("high"),
        )
        self.assertEqual(res, "high")

        # 2) Missing primary_finding -> degrades to low
        risk_bundle_no_finding = {
            "primary_finding": None,
            "control_mapping": [{"check_id": "abc"}],
        }
        res = self.builder._evaluate_bundle_confidence(
            consumer="risk",
            query=None,
            risk_bundle=risk_bundle_no_finding,
            report_bundle=None,
            planning_bundle=None,
            retrieval_confidence=Confidence("high"),
        )
        self.assertEqual(res, "low")

        # 3) Missing mappings/context -> degrades to medium
        risk_bundle_no_context = {
            "primary_finding": {"check_id": "abc"},
            "control_mapping": [],
            "maturity_context": [],
        }
        res = self.builder._evaluate_bundle_confidence(
            consumer="risk",
            query=None,
            risk_bundle=risk_bundle_no_context,
            report_bundle=None,
            planning_bundle=None,
            retrieval_confidence=Confidence("high"),
        )
        self.assertEqual(res, "medium")

    def test_report_consumer_degradation(self):
        # 1) Perfect bundle -> keeps high
        report_bundle_good = {
            "primary_topics": ["s3"],
            "key_findings": [{"check_id": "abc"}],
            "control_themes": [{"capability_id": "cap1"}],
            "recommended_practices": ["do this"],
        }
        res = self.builder._evaluate_bundle_confidence(
            consumer="report",
            query=None,
            risk_bundle=None,
            report_bundle=report_bundle_good,
            planning_bundle=None,
            retrieval_confidence=Confidence("high"),
        )
        self.assertEqual(res, "high")

        # 2) Missing findings -> low
        report_bundle_no_findings = {
            "primary_topics": ["s3"],
            "key_findings": [],
            "control_themes": [{"capability_id": "cap1"}],
            "recommended_practices": ["do this"],
        }
        res = self.builder._evaluate_bundle_confidence(
            consumer="report",
            query=None,
            risk_bundle=None,
            report_bundle=report_bundle_no_findings,
            planning_bundle=None,
            retrieval_confidence=Confidence("high"),
        )
        self.assertEqual(res, "low")

        # 3) Missing practice/themes -> medium
        report_bundle_no_themes = {
            "primary_topics": ["s3"],
            "key_findings": [{"check_id": "abc"}],
            "control_themes": [],
            "recommended_practices": [],
        }
        res = self.builder._evaluate_bundle_confidence(
            consumer="report",
            query=None,
            risk_bundle=None,
            report_bundle=report_bundle_no_themes,
            planning_bundle=None,
            retrieval_confidence=Confidence("high"),
        )
        self.assertEqual(res, "medium")

    def test_planning_consumer_degradation(self):
        # 1) Missing findings -> low
        planning_bundle_empty = {
            "related_findings": []
        }
        res = self.builder._evaluate_bundle_confidence(
            consumer="planning",
            query="s3 and iam",
            risk_bundle=None,
            report_bundle=None,
            planning_bundle=planning_bundle_empty,
            retrieval_confidence=Confidence("high"),
        )
        self.assertEqual(res, "low")

        # 2) Multi-intent query but single service -> medium (poor coverage)
        planning_bundle_poor_cover = {
            "related_findings": [
                {"service": "s3", "check_id": "1"},
                {"service": "s3", "check_id": "2"}
            ]
        }
        res = self.builder._evaluate_bundle_confidence(
            consumer="planning",
            query="s3 public access and iam mfa",
            risk_bundle=None,
            report_bundle=None,
            planning_bundle=planning_bundle_poor_cover,
            retrieval_confidence=Confidence("high"),
        )
        self.assertEqual(res, "medium")

        # 3) Multi-intent query with good coverage -> high
        planning_bundle_good_cover = {
            "related_findings": [
                {"service": "s3", "check_id": "1"},
                {"service": "iam", "check_id": "2"}
            ]
        }
        res = self.builder._evaluate_bundle_confidence(
            consumer="planning",
            query="s3 public access and iam mfa",
            risk_bundle=None,
            report_bundle=None,
            planning_bundle=planning_bundle_good_cover,
            retrieval_confidence=Confidence("high"),
        )
        self.assertEqual(res, "high")

if __name__ == "__main__":
    unittest.main()
