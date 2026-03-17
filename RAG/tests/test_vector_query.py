"""Quick script to validate that the vector index is built and used in retrieval."""

from RAG.app.retrieval.pipeline import RetrievalPipeline


def main():
    pipeline = RetrievalPipeline()
    print("vector index loaded?", pipeline.vector_index is not None)

    out = pipeline.search(query="s3 encryption", top_k=5)
    print("router:", out.get("router"))
    for i, res in enumerate(out.get("results", [])[:5], start=1):
        print(
            f"{i}. {res['doc_id']} (score={res['score']:.4f}) sources={res.get('sources')}"
        )


if __name__ == "__main__":
    main()
