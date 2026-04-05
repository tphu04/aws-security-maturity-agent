"""
Thu thap RAG context snapshot cho moi test case.

Usage:
    python benchmark_llm_gen/collect_rag_snapshots.py

Requires: RAG server running at localhost:8001

Output: Cap nhat rag_context_snapshot trong benchmark_gen_cases.json
voi du lieu thuc te tu RAG (official_severity, compliance_mappings, confidence).
"""

import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

CASES_FILE = Path(__file__).resolve().parent / "benchmark_gen_cases.json"


def collect_snapshots():
    from agents.shared.rag_client import RAGClient
    from config import RAG_API_URL

    rag = RAGClient(base_url=RAG_API_URL)
    if not rag.is_healthy():
        logger.error("RAG service not healthy at %s", RAG_API_URL)
        sys.exit(1)

    logger.info("RAG service healthy at %s", RAG_API_URL)

    with open(CASES_FILE, encoding="utf-8") as f:
        data = json.load(f)

    cases = data["risk_cases"]
    updated = 0

    for i, case in enumerate(cases, 1):
        check_id = case["input"]["finding"]["event_code"]
        logger.info("[%d/%d] Fetching context for: %s", i, len(cases), check_id)

        try:
            result = rag.build_context(
                consumer="risk",
                check_ids=[f"check:{check_id}"],
                include_mappings=True,
                include_maturity=True,
            )
        except Exception as e:
            logger.error("  Failed: %s", e)
            continue

        if not result:
            logger.warning("  No result returned for %s", check_id)
            continue

        snapshot = _extract_snapshot(result, check_id)
        if snapshot:
            case["rag_context_snapshot"] = snapshot
            updated += 1
            logger.info("  -> severity=%s, mappings=%d, confidence=%s",
                        snapshot.get("official_severity", "?"),
                        len(snapshot.get("compliance_mappings", [])),
                        snapshot.get("confidence", "?"))
        else:
            logger.warning("  Could not extract snapshot for %s", check_id)

    # Save updated cases
    with open(CASES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info("Updated %d/%d cases. Saved to %s", updated, len(cases), CASES_FILE.name)


def _extract_snapshot(result: dict, check_id: str) -> dict:
    """Extract rag_context_snapshot tu RAG response."""

    snapshot = {}

    # Extract confidence
    meta = result.get("_meta", {})
    snapshot["confidence"] = meta.get("confidence", "unknown")

    # Extract from risk_bundle
    payload = result.get("payload", {})
    risk_bundle = payload.get("risk_bundle", {})

    # Official severity from related_findings
    related = risk_bundle.get("related_findings", [])
    for finding in related:
        fid = finding.get("check_id", "")
        if check_id in fid or fid in check_id:
            snapshot["official_severity"] = finding.get("severity", "")
            snapshot["check_title"] = finding.get("title", "")
            break

    # Fallback: primary_finding
    if "official_severity" not in snapshot:
        primary = risk_bundle.get("primary_finding", {})
        if primary:
            snapshot["official_severity"] = primary.get("severity", "")
            snapshot["check_title"] = primary.get("title", "")

    # Compliance mappings
    mappings = risk_bundle.get("control_mapping", [])
    snapshot["compliance_mappings"] = [m.get("capability_id", "") for m in mappings if m.get("capability_id")]

    # Maturity context
    maturity = risk_bundle.get("maturity_context", [])
    if maturity:
        snapshot["maturity_context"] = [
            {"capability_id": m.get("capability_id", ""), "capability_name": m.get("capability_name", "")}
            for m in maturity[:3]  # Max 3
        ]

    return snapshot if snapshot.get("official_severity") else snapshot


if __name__ == "__main__":
    collect_snapshots()
