"""Test Chroma vector query filtering behavior (no shell interpolation issues)."""

import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `from RAG...` works when running this file directly.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from RAG.app.indexing.vector_index import VectorIndex


def main():
    v = VectorIndex()
    c = v.get_collection("rag_docs")

    query = "s3 encryption"
    # Build a filter that matches the same fields used by lexical retrieval
    where = {
        "$and": [
            {"doc_type": {"$eq": "prowler_check"}},
            {"provider": {"$eq": "aws"}},
            {"service": {"$eq": "s3"}},
        ]
    }

    resp = c.query(query_texts=[query], n_results=5, where=where)
    print("ids:", resp.get("ids"))
    print("distances:", resp.get("distances"))
    print("metadatas:", resp.get("metadatas")[:2])


if __name__ == "__main__":
    main()
