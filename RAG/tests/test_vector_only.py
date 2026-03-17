import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.indexing.vector_index import VectorIndex
from app.core.config import CHROMA_DIR


def main():
    print("=== VECTOR SEARCH SMOKE TEST ===")
    print(f"[INFO] CHROMA_DIR = {CHROMA_DIR}")

    vector_index = VectorIndex()

    collections = vector_index.client.list_collections()
    print("[INFO] collections =", [c.name for c in collections])

    collection_name = "maturity_capabilities"

    collection = vector_index.get_collection(collection_name)
    print(f"[INFO] collection='{collection_name}' count={collection.count()}")

    query = "s3 public access block"
    print(f"[TEST QUERY] {query}")

    results = vector_index.query(
        name=collection_name,
        query_text=query,
        top_k=5,
        filters=None,
    )

    print(f"[RESULT COUNT] {len(results)}")
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['doc_id']} score={r['score']}")
        print(f"   metadata={r.get('metadata', {})}")


if __name__ == "__main__":
    main()
