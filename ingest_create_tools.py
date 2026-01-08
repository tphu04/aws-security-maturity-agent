# Script gợi ý để chạy 1 lần duy nhất
import json
import chromadb
from langchain_ollama import OllamaEmbeddings

client = chromadb.PersistentClient(path="./prowler_vector_kb")
collection = client.get_or_create_collection(name="aws_sdk_docs")
embeddings = OllamaEmbeddings(model="nomic-embed-text")

with open("services/s3/service-2.json", "r") as f:
    data = json.load(f)

ops = data.get("operations", {})
for op_name, info in ops.items():
    # Lọc bỏ HTML tag trong documentation để AI dễ đọc
    doc = info.get("documentation", "").replace("<p>", "").replace("</p>", "")
    content = f"Action: {op_name}\nDescription: {doc[:500]}"
    
    collection.add(
        ids=[f"s3_{op_name}"],
        documents=[content],
        metadatas=[{"service": "s3", "action": op_name}]
    )
print(f"✅ Đã nạp {len(ops)} hàm S3 vào thư viện kiến thức!")