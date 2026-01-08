import chromadb
from langchain_ollama import OllamaEmbeddings
from agent_tools import REMEDIATION_TOOLS # Import danh sách tool bạn đã định nghĩa

# 1. Cấu hình
embeddings = OllamaEmbeddings(model="nomic-embed-text")
client = chromadb.PersistentClient(path="./prowler_vector_kb")

# 2. Xóa và tạo Collection mới cho Tools
try:
    client.delete_collection(name="remediation_tools_v2")
except:
    pass
collection = client.create_collection(name="remediation_tools_v2")

def ingest_tools():
    ids = []
    documents = []
    
    print(f"📦 Đang xử lý {len(REMEDIATION_TOOLS)} tools từ agent_tools.py...")

    for tool in REMEDIATION_TOOLS:
        # Lấy tên và mô tả (docstring) của tool
        name = tool.name
        description = tool.description
        
        # Làm giàu thêm từ khóa để RAG dễ tìm (Tương tự metadata enrichment)
        # Ví dụ: Nếu tool là s3_enable_object_lock, ta thêm từ khóa "ransomware"
        enrichment = ""
        if "object_lock" in name: enrichment = "ransomware protection, immutable"
        if "public_access" in name: enrichment = "data leak, exposure"
        
        content = f"Tool Name: {name}. Description: {description}. Keywords: {enrichment}"
        
        documents.append(content)
        ids.append(name)

    # Nạp vào database
    batch_embeddings = embeddings.embed_documents(documents)
    collection.add(
        ids=ids,
        embeddings=batch_embeddings,
        documents=documents
    )
    print("✅ Hoàn tất! Remediation Tools đã sẵn sàng trong VectorDB.")

if __name__ == "__main__":
    ingest_tools()