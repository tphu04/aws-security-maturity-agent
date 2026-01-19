import chromadb
from chromadb.config import Settings
import requests

OLLAMA_EMBED_MODEL = "nomic-embed-text"
OLLAMA_URL = "http://localhost:11434/api/embeddings"

CHROMA_DIR = "data/vector_db"
COLLECTION_NAME = "prowler_security_chunks"

def embed_query(text: str):
    r = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_EMBED_MODEL, "prompt": text}
    )
    return r.json()["embedding"]

client = chromadb.Client(
    Settings(persist_directory=CHROMA_DIR)
)

collection = client.get_collection(COLLECTION_NAME)

query = "Why is missing origin failover in CloudFront dangerous?"

results = collection.query(
    query_embeddings=[embed_query(query)],
    n_results=5
)

for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
    print("----")
    print(meta["chunk_type"], "|", meta["service"])
    print(doc)
