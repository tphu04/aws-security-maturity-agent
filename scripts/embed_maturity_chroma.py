import json
import os
import chromadb
from langchain_ollama import OllamaEmbeddings

# 1. Cấu hình đường dẫn
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHUNK_FILE = os.path.join(BASE_DIR, "data", "chunked", "maturity_model_chunks.json")
DB_PATH = os.path.join(os.path.dirname(BASE_DIR), "prowler_vector_kb")

def embed_maturity_model():
    if not os.path.exists(CHUNK_FILE):
        print(f"❌ Không tìm thấy file chunk tại: {CHUNK_FILE}")
        return

    print(f"🚀 Khởi tạo Embedding process cho Maturity Model...")

    # 2. Khởi tạo ChromaDB Client
    client = chromadb.PersistentClient(path=DB_PATH)
    embeddings_model = OllamaEmbeddings(model="nomic-embed-text")

    # 3. Tạo hoặc lấy Collection
    collection_name = "aws_maturity_model_kb"
    collection = client.get_or_create_collection(name=collection_name)
    print(f"📦 Collection: {collection_name} đã sẵn sàng.")

    # 4. Đọc dữ liệu chunks
    with open(CHUNK_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    # 5. Tiến hành Embedding và nạp vào DB
    batch_size = 50
    total_chunks = len(chunks)
    
    print(f"🧠 Đang xử lý {total_chunks} chunks...")

    for i in range(0, total_chunks, batch_size):
        batch = chunks[i : i + batch_size]
        
        ids = [c["chunk_id"] for c in batch]
        documents = [c["text"] for c in batch]
        
        batch_metadatas = []
        for c in batch:
            m = c.copy()
            # Xóa text để tránh trùng lặp
            if "text" in m:
                del m["text"]
            
            # --- BƯỚC SỬA LỖI QUAN TRỌNG ---
            # Duyệt qua các key trong metadata, nếu là list thì biến thành string
            for key, value in m.items():
                if isinstance(value, list):
                    # Ví dụ: ["A", "B"] -> "A, B"
                    m[key] = ", ".join(map(str, value))
            # -------------------------------
            
            batch_metadatas.append(m)
        
        # Nạp vào ChromaDB
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=batch_metadatas 
        )
        
        progress = min(i + batch_size, total_chunks)
        print(f"✅ Đã nạp: {progress}/{total_chunks} chunks...")

    print(f"\n✨ HOÀN TẤT! Toàn bộ 222 chunks đã được làm phẳng và nạp vào DB.")

if __name__ == "__main__":
    embed_maturity_model()