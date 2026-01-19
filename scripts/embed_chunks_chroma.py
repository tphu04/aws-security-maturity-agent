import json
import requests
from pathlib import Path
from tqdm import tqdm
import chromadb
from chromadb.config import Settings

# -----------------------------
# CONFIG
# -----------------------------

OLLAMA_EMBED_MODEL = "nomic-embed-text"
OLLAMA_URL = "http://localhost:11434/api/embeddings"

INPUT_PATH = Path("data/chunked/prowler_chunks.json")
CHROMA_DIR = "data/vector_db"
COLLECTION_NAME = "prowler_security_chunks"

# -----------------------------
# LOAD DATA
# -----------------------------

with open(INPUT_PATH, "r", encoding="utf-8") as f:
    chunks = json.load(f)

print(f"📦 Loaded {len(chunks)} chunks")

# -----------------------------
# INIT CHROMA
# -----------------------------

client = chromadb.Client(
    Settings(
        persist_directory=CHROMA_DIR,
        anonymized_telemetry=False
    )
)

collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"source": "prowler", "embedding_model": OLLAMA_EMBED_MODEL}
)

# -----------------------------
# EMBEDDING FUNCTION
# -----------------------------

def embed_text(text: str) -> list[float]:
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_EMBED_MODEL,
            "prompt": text
        },
        timeout=60
    )
    response.raise_for_status()
    return response.json()["embedding"]

# -----------------------------
# EMBED & STORE
# -----------------------------

for chunk in tqdm(chunks, desc="🔗 Embedding chunks"):
    embedding = embed_text(chunk["text"])

    metadata = {
        "check_id": chunk["check_id"],
        "chunk_type": chunk["chunk_type"],
        "service": chunk.get("service"),
        "severity": chunk.get("severity"),
        "categories": ",".join(chunk.get("categories", [])),
        "check_type": ",".join(chunk.get("check_type", []))
    }

    collection.add(
        ids=[chunk["chunk_id"]],
        documents=[chunk["text"]],
        embeddings=[embedding],
        metadatas=[metadata]
    )

client.persist()

print("✅ Embedding completed")
print(f"📁 Vector DB saved to: {CHROMA_DIR}")
print(f"📚 Collection: {COLLECTION_NAME}")
