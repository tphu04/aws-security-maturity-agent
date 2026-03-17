"""Run a set of sample RAG queries and print the top results.

Usage:
    python -m RAG.scripts.query_results_demo

This script demonstrates what the retrieval pipeline returns for a few
representative queries (both maturity and prowler check searches).
"""

import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `from RAG...` works when running this file directly.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from RAG.app.indexing.vector_index import VectorIndex

from typing import List, Dict

from RAG.app.core.models import RetrieveChecksRequest, RetrieveMaturityRequest
from RAG.app.services.check_service import CheckService
from RAG.app.services.maturity_service import MaturityService


def _print_results(title: str, results: List[Dict], max_items: int = 5) -> None:
    print(f"\n=== {title} ===")
    if not results:
        print("(no results)")
        return
    for i, r in enumerate(results[:max_items], start=1):
        doc_id = r.get("doc_id")
        score = r.get("score")
        meta = r.get("metadata") or {}
        label = meta.get("title") or meta.get("capability_name") or ""
        print(f"{i}. doc_id={doc_id} score={score:.4f} title={label}")


def main():
    check_srv = CheckService()
    maturity_srv = MaturityService()

    queries = [
        ("prowler: origin failover", "check", "origin failover"),
        ("prowler: field level encryption", "check", "field level encryption"),
        (
            "prowler: s3 origin non existent bucket",
            "check",
            "cloudfront distribution s3 origins reference existing buckets",
        ),
        ("maturity: root account", "maturity", "root account"),
        (
            "maturity: multi factor authentication",
            "maturity",
            "multi factor authentication",
        ),
    ]

    for label, qtype, query in queries:
        if qtype == "check":
            resp = check_srv.search_checks(RetrieveChecksRequest(query=query, top_k=5))
            _print_results(label, resp.data.get("results", []), max_items=5)
        else:
            resp = maturity_srv.search_maturity(
                RetrieveMaturityRequest(query=query, top_k=5)
            )
            _print_results(label, resp.data.get("results", []), max_items=5)


if __name__ == "__main__":
    main()
