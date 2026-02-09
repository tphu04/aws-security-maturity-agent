import os
import requests
import chromadb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Literal

# --- CONFIG ---
OLLAMA_EMBED_MODEL = "nomic-embed-text"
OLLAMA_URL = "http://localhost:11434/api/embeddings"
CHROMA_DIR = "/home/vnpd/DoAn/aws-security-maturity-agent/prowler_vector_kb"

app = FastAPI(title="AWS Security Dual-RAG API (Port 8111)")
client = chromadb.PersistentClient(path=CHROMA_DIR)

# 1. Update the Model to accept 'service'
class QueryRequest(BaseModel):
    query: str
    service: Optional[str] = None  # Added: Target service (e.g., "s3", "iam")
    mode: Literal["maturity", "technical", "both"] = "both"
    top_k: int = 5

def get_embedding(text: str):
    r = requests.post(OLLAMA_URL, json={"model": OLLAMA_EMBED_MODEL, "prompt": text})
    return r.json()["embedding"]

def format_res(res):
    if not res or not res['ids'] or len(res['ids'][0]) == 0:
        return []
    return [{
        "id": res["ids"][0][i],
        "content": res["documents"][0][i],
        "metadata": res["metadatas"][0][i],
        "score": round(res["distances"][0][i], 4)
    } for i in range(len(res["ids"][0]))]

@app.post("/retrieve")
async def retrieve_knowledge(request: QueryRequest):
    print(f"🔎 Query: '{request.query}' | Service Filter: {request.service} | Mode: {request.mode}")
    try:
        query_vector = get_embedding(request.query)
        response = {"maturity": [], "technical": []}

        # --- Segment 1: Maturity Model (Usually doesn't need service filter) ---
        if request.mode in ["maturity", "both"]:
            coll = client.get_collection("aws_maturity_model_kb")
            res = coll.query(query_embeddings=[query_vector], n_results=request.top_k)
            response["maturity"] = format_res(res)

        # --- Segment 2: Prowler Technical (CRITICAL: Filter by Service) ---
        if request.mode in ["technical", "both"]:
            coll = client.get_collection("prowler_security_chunks")
            
            # Construct the metadata filter
            search_filter = None
            if request.service and request.service.lower() != "null":
                # Ensure this matches the key 'service' used during ingestion
                search_filter = {"service": request.service.lower()} 

            res = coll.query(
                query_embeddings=[query_vector], 
                n_results=request.top_k,
                where=search_filter  # <--- Filters out non-matching services
            )
            response["technical"] = format_res(res)

        return response
    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8111)