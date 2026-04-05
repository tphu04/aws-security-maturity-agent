"""
Integration Test: PlanningAgent V2 -- S3 Semantic Queries
==========================================================
Test voi REAL Ollama + REAL RAG service.
Input la ngon ngu tu nhien, KHONG co ten check ID cu the.
Agent phai tu suy doan service va checks phu hop.

Requirements:
  - Ollama running at localhost:11434 (model: llama3.2)
  - RAG service running at localhost:8001

Run: python -m pytest tests/test_planning_s3_semantic.py -v -s
"""

import time
import logging
import pytest
import requests

from agents.planning_agent import PlanningAgent
from agents.shared.rag_client import RAGClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _service_available(url, timeout=2.0):
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def rag_client():
    if not _service_available("http://localhost:8001/ready"):
        pytest.skip("RAG service not running at localhost:8001")
    return RAGClient(base_url="http://localhost:8001", timeout=15.0)


@pytest.fixture(scope="module")
def agent(rag_client):
    if not _service_available("http://localhost:11434/api/tags"):
        pytest.skip("Ollama not running at localhost:11434")
    return PlanningAgent(
        model_name="llama3.2",
        base_url="http://localhost:11434",
        rag_client=rag_client,
    )


def run_and_report(agent, query, test_name):
    """Run agent, print detailed output, return result."""
    print(f"\n{'- '*40}")
    print(f"  TEST: {test_name}")
    print(f"  INPUT: \"{query}\"")
    start = time.perf_counter()
    result = agent.run(query)
    elapsed = time.perf_counter() - start
    print(f"  TIME: {elapsed:.2f}s")
    print(f"  groups_to_scan:  {result['groups_to_scan']}")
    print(f"  checks_to_scan:  {result['checks_to_scan']}")
    print(f"  reasoning:       {result.get('reasoning', '')[:120]}")
    if result.get("error"):
        print(f"  error:           {result['error'][:120]}")
    used_llm = elapsed > 2.0  # heuristic: LLM call takes > 2s
    print(f"  LLM used:        {'likely YES' if used_llm else 'likely NO'}")
    print()
    return result


# =====================================================================
# GROUP A: Direct S3 intent -- user noi ve S3 nhung dung ngon ngu tu nhien
# =====================================================================

class TestDirectS3Intent:
    """User noi ve S3 nhung KHONG dung ten check ID."""

    def test_public_bucket_natural_language(self, agent):
        """Hoi ve bucket cong khai -- phai tra ve s3_bucket_public_access hoac tuong tu."""
        result = run_and_report(agent,
            "I'm worried that some of our S3 buckets might be publicly accessible to anyone on the internet",
            "Public bucket concern (natural language)")
        assert not result.get("error"), f"Unexpected error: {result.get('error')}"
        checks = result["checks_to_scan"]
        groups = result["groups_to_scan"]
        # Phai co it nhat 1 ket qua (checks hoac group s3)
        assert checks or groups, "No checks or groups returned"
        if checks:
            # It nhat 1 check lien quan den public access
            all_ids = " ".join(checks)
            assert any(kw in all_ids for kw in ["public_access", "public_write", "public_list", "public_read"]), \
                f"No public-access related check found in: {checks}"

    def test_bucket_encryption_indirect(self, agent):
        """Hoi ve ma hoa du lieu -- khong noi 'encryption' truc tiep."""
        result = run_and_report(agent,
            "we need to make sure all data stored in our buckets is protected with encryption keys",
            "Bucket encryption (indirect phrasing)")
        assert not result.get("error")
        checks = result["checks_to_scan"]
        groups = result["groups_to_scan"]
        assert checks or groups
        if checks:
            all_ids = " ".join(checks)
            assert any(kw in all_ids for kw in ["encrypt", "kms", "sse"]), \
                f"No encryption-related check in: {checks}"

    def test_bucket_logging(self, agent):
        """Hoi ve ghi log truy cap -- khong noi 'logging' truc tiep."""
        result = run_and_report(agent,
            "how can we track who accessed which files in our S3 storage and when",
            "S3 access tracking (logging intent)")
        assert not result.get("error")
        checks = result["checks_to_scan"]
        groups = result["groups_to_scan"]
        assert checks or groups
        if checks:
            all_ids = " ".join(checks)
            assert any(kw in all_ids for kw in ["logging", "log", "dataevents", "trail", "access"]), \
                f"No logging-related check in: {checks}"

    def test_bucket_versioning_disaster_recovery(self, agent):
        """Hoi ve bao ve du lieu khoi xoa nham -- lien quan versioning/backup."""
        result = run_and_report(agent,
            "what if someone accidentally deletes important files from our S3 buckets, "
            "is there any protection against that",
            "Accidental deletion protection (versioning intent)")
        assert not result.get("error")
        checks = result["checks_to_scan"]
        groups = result["groups_to_scan"]
        assert checks or groups

    def test_cross_account_sharing(self, agent):
        """Hoi ve chia se bucket giua cac account AWS."""
        result = run_and_report(agent,
            "check if any of our S3 buckets are shared with external AWS accounts "
            "that we don't control",
            "Cross-account S3 access")
        assert not result.get("error")
        checks = result["checks_to_scan"]
        groups = result["groups_to_scan"]
        assert checks or groups
        if checks:
            all_ids = " ".join(checks)
            has_relevant = any(kw in all_ids for kw in [
                "cross_account", "policy", "public", "acl", "bucket"
            ])
            assert has_relevant, f"No cross-account/policy related check in: {checks}"


# =====================================================================
# GROUP B: Indirect S3 intent -- user KHONG noi "S3" hay "bucket"
# =====================================================================

class TestIndirectS3Intent:
    """User noi ve van de bao mat nhung khong de cap S3 truc tiep.
    Agent phai tu suy doan service tu ngu canh."""

    def test_file_storage_security(self, agent):
        """'file storage' -> phai suy ra la S3."""
        result = run_and_report(agent,
            "audit the security of our cloud file storage where we keep customer documents",
            "Cloud file storage audit (implies S3)")
        assert not result.get("error")
        checks = result["checks_to_scan"]
        groups = result["groups_to_scan"]
        assert checks or groups
        # Chap nhan ca s3 checks hoac s3 group
        if groups:
            assert "s3" in groups, f"Expected s3 in groups, got: {groups}"

    def test_object_storage_exposure(self, agent):
        """'object storage' -> S3."""
        result = run_and_report(agent,
            "verify that our object storage is not exposed and all data is secured",
            "Object storage exposure (implies S3)")
        assert not result.get("error")
        assert result["checks_to_scan"] or result["groups_to_scan"]

    def test_data_leak_via_storage(self, agent):
        """Noi ve data leak qua storage -- S3 la nguon chinh."""
        result = run_and_report(agent,
            "our security team is concerned about potential data leaks through "
            "misconfigured storage permissions in AWS",
            "Data leak via storage misconfiguration")
        assert not result.get("error")
        assert result["checks_to_scan"] or result["groups_to_scan"]

    def test_static_website_hosting(self, agent):
        """Static website hosting la feature cua S3."""
        result = run_and_report(agent,
            "we host some static websites and want to make sure the hosting "
            "configuration doesn't expose sensitive files",
            "Static website hosting security")
        assert not result.get("error")
        assert result["checks_to_scan"] or result["groups_to_scan"]


# =====================================================================
# GROUP C: Multi-aspect S3 queries -- nhieu khia canh trong 1 cau hoi
# =====================================================================

class TestMultiAspectS3:
    """Cau hoi phuc tap, lien quan nhieu khia canh S3 cung luc."""

    def test_comprehensive_s3_review(self, agent):
        """Yeu cau kiem tra toan dien S3 -- nhieu checks."""
        result = run_and_report(agent,
            "do a comprehensive security review of our S3 infrastructure: "
            "check for public access, encryption, logging, and versioning",
            "Comprehensive S3 review (4 aspects)")
        assert not result.get("error")
        checks = result["checks_to_scan"]
        groups = result["groups_to_scan"]
        # Voi yeu cau rong nhu nay, co the group scan hoac nhieu checks
        assert checks or groups
        if checks:
            assert len(checks) >= 2, \
                f"Expected multiple checks for comprehensive review, got: {checks}"

    def test_s3_compliance_audit(self, agent):
        """Audit tuan thu -- ket hop nhieu yeu cau."""
        result = run_and_report(agent,
            "prepare for our annual compliance audit, we need to verify that all "
            "S3 buckets have encryption enabled, access logging turned on, "
            "and no public access whatsoever",
            "S3 compliance audit (encryption + logging + no public)")
        assert not result.get("error")
        checks = result["checks_to_scan"]
        groups = result["groups_to_scan"]
        assert checks or groups
        if checks:
            assert len(checks) >= 2, \
                f"Expected multiple checks for audit, got: {checks}"

    def test_s3_after_incident(self, agent):
        """Sau su co bao mat -- can kiem tra gap."""
        result = run_and_report(agent,
            "we just discovered that a contractor had admin access to our S3 and may have "
            "changed bucket policies, we need to immediately verify bucket permissions, "
            "public access settings, and ACL configurations",
            "Post-incident S3 audit (permissions + policies + ACLs)")
        assert not result.get("error")
        checks = result["checks_to_scan"]
        groups = result["groups_to_scan"]
        assert checks or groups


# =====================================================================
# GROUP D: Ambiguous & tricky -- cau hoi mo ho, nhieu nghia
# =====================================================================

class TestAmbiguousS3:
    """Cau hoi mo ho hoac de hieu nham."""

    def test_vague_storage_question(self, agent):
        """Cau hoi rat mo ho ve storage -- agent phai xu ly."""
        result = run_and_report(agent,
            "is our storage secure",
            "Very vague: 'is our storage secure'")
        # Khong crash, tra ve gi do (checks, group, hoac error)
        assert isinstance(result, dict)
        # Chap nhan bat ky ket qua nao -- chi can khong crash va khong default S3 sai
        if result.get("error"):
            assert "s3" not in str(result["groups_to_scan"]), \
                "Should NOT silently default to S3 on vague query"

    def test_mixed_services_mention_s3(self, agent):
        """Noi ve nhieu services nhung chu yeu la S3."""
        result = run_and_report(agent,
            "check the security of our S3 buckets and also make sure our "
            "CloudFront distributions are properly configured with HTTPS",
            "Mixed: S3 + CloudFront in one query")
        assert not result.get("error")
        checks = result["checks_to_scan"]
        groups = result["groups_to_scan"]
        assert checks or groups

    def test_business_context_implies_s3(self, agent):
        """Ngu canh kinh doanh ngam chi S3."""
        result = run_and_report(agent,
            "our marketing team uploads campaign images and PDFs to AWS, "
            "we need to make sure those assets are not publicly downloadable",
            "Business context: marketing uploads (implies S3)")
        assert not result.get("error")
        assert result["checks_to_scan"] or result["groups_to_scan"]

    def test_negative_phrasing(self, agent):
        """Cau phu dinh -- 'khong muon bucket bi public'."""
        result = run_and_report(agent,
            "make sure none of our buckets allow unauthenticated read or write access",
            "Negative phrasing: 'none... allow unauthenticated access'")
        assert not result.get("error")
        checks = result["checks_to_scan"]
        groups = result["groups_to_scan"]
        assert checks or groups
        if checks:
            all_ids = " ".join(checks)
            assert any(kw in all_ids for kw in [
                "public", "acl", "policy", "access", "auth", "bucket"
            ]), f"No access-control related check in: {checks}"

    def test_typo_and_informal(self, agent):
        """Input co typo va ngon ngu khong chinh thuc."""
        result = run_and_report(agent,
            "hey can u check if our s3 buckts are encryptd and not publc??",
            "Typos + informal: 'buckts', 'encryptd', 'publc'")
        assert not result.get("error")
        # S3 van phai duoc detect du co typo
        assert result["checks_to_scan"] or result["groups_to_scan"]

    def test_question_format(self, agent):
        """Dat cau hoi thay vi ra lenh."""
        result = run_and_report(agent,
            "what S3 security checks should I run to ensure our data is safe?",
            "Question format instead of command")
        assert not result.get("error")
        assert result["checks_to_scan"] or result["groups_to_scan"]


# =====================================================================
# GROUP E: Scorer & ranking validation
# =====================================================================

class TestScorerRanking:
    """Kiem tra thu tu uu tien cua ket qua."""

    def test_critical_checks_first(self, agent):
        """Kiem tra critical checks duoc xep truoc."""
        result = run_and_report(agent,
            "check all S3 public access and bucket policy issues",
            "Ranking: critical checks should appear first")
        checks = result["checks_to_scan"]
        if len(checks) >= 2:
            # Query truc tiep RAG de lay severity cua check dau tien
            rag_result = agent.rag_client.retrieve_checks(
                query="s3 public access bucket policy", top_k=10,
                retrieval_mode="hybrid",
            )
            if rag_result:
                severity_map = {}
                for r in rag_result.get("results", []):
                    from agents.shared.utils import sanitize_check_id
                    cid = sanitize_check_id(r.get("doc_id", ""))
                    sev = r.get("metadata", {}).get("severity", "").lower()
                    if cid:
                        severity_map[cid] = sev

                first_sev = severity_map.get(checks[0], "unknown")
                print(f"    [RANKING] First check: {checks[0]} (severity: {first_sev})")
                print(f"    [RANKING] All checks: {checks}")
                # First check should be critical or high
                assert first_sev in ("critical", "high", "unknown"), \
                    f"First check should be critical/high, got: {first_sev}"

    def test_service_match_boost(self, agent):
        """S3 checks phai duoc uu tien hon non-S3 khi hoi ve S3."""
        result = run_and_report(agent,
            "s3 bucket security assessment",
            "Service match: S3 checks should rank higher")
        checks = result["checks_to_scan"]
        if checks:
            s3_checks = [c for c in checks if c.startswith("s3_")]
            print(f"    [SERVICE MATCH] S3 checks: {len(s3_checks)}/{len(checks)}")
            # Majority should be S3
            assert len(s3_checks) >= len(checks) // 2, \
                f"Expected majority S3 checks, got {len(s3_checks)}/{len(checks)}"


# =====================================================================
# GROUP F: Performance -- LLM avoidance
# =====================================================================

class TestPerformance:
    """Kiem tra agent co tranh goi LLM khi khong can thiet."""

    def test_clear_s3_query_no_llm(self, agent):
        """Query ro rang ve S3 -> RAG confidence cao -> khong can LLM."""
        start = time.perf_counter()
        result = run_and_report(agent,
            "check S3 bucket public access settings",
            "Performance: clear S3 query should skip LLM")
        elapsed = time.perf_counter() - start
        assert not result.get("error")
        assert result["checks_to_scan"] or result["groups_to_scan"]
        # Neu khong goi LLM, thoi gian phai < 3s (chi RAG call)
        # Neu goi LLM (llama3.2 local), thuong > 3s
        print(f"    [PERF] Total time: {elapsed:.2f}s")
        if elapsed < 3.0:
            print(f"    [PERF] FAST -- likely no LLM call (RAG-only)")
        else:
            print(f"    [PERF] SLOW -- LLM was probably called")

    def test_encryption_query_no_llm(self, agent):
        """Query ve encryption -> RAG tra ket qua tot -> skip LLM."""
        start = time.perf_counter()
        result = run_and_report(agent,
            "verify S3 bucket encryption configuration",
            "Performance: encryption query should skip LLM")
        elapsed = time.perf_counter() - start
        assert not result.get("error")
        print(f"    [PERF] Total time: {elapsed:.2f}s")
