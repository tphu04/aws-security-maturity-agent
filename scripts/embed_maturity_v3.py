import json
import os
import chromadb
from langchain_ollama import OllamaEmbeddings

# 1. Cấu hình đường dẫn
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# File Chunks V3 - Đã dọn dẹp URL dính và rác UI
CHUNK_FILE = os.path.join(BASE_DIR, "../data/chunked/maturity_model_v3_chunks.json")
# Thư mục lưu trữ Vector DB
DB_PATH = os.path.join(os.path.dirname(BASE_DIR), "prowler_vector_kb")

def embed_maturity_v3():
    if not os.path.exists(CHUNK_FILE):
        print(f"❌ Không tìm thấy file chunk tại: {CHUNK_FILE}")
        return

    print(f"🚀 Khởi tạo Embedding process cho Maturity Model V3...")

    # 2. Khởi tạo ChromaDB Client và Model
    client = chromadb.PersistentClient(path=DB_PATH)
    # Đảm bảo bạn đã chạy: ollama pull nomic-embed-text
    embeddings_model = OllamaEmbeddings(model="nomic-embed-text")

    # 3. Quản lý Collection
    collection_name = "aws_maturity_model_kb"
    
    # XÓA DỮ LIỆU CŨ: Đảm bảo chỉ dùng dữ liệu chi tiết mới nhất
    try:
        client.delete_collection(name=collection_name)
        print(f"🧹 Đã xóa collection cũ '{collection_name}' để làm mới.")
    except Exception:
        print(f"ℹ️ Tạo mới collection '{collection_name}' (chưa tồn tại).")
    
    collection = client.create_collection(name=collection_name)
    print(f"📦 Collection: {collection_name} đã sẵn sàng.")

    # 4. Đọc dữ liệu chunks v3
    with open(CHUNK_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    # 5. Tiến hành Embedding và nạp vào DB theo Batch
    batch_size = 50
    total_chunks = len(chunks)
    
    print(f"🧠 Đang mã hóa và nạp {total_chunks} chunks tri thức...")

    for i in range(0, total_chunks, batch_size):
        batch = chunks[i : i + batch_size]
        
        ids = [c["chunk_id"] for c in batch]
        documents = [c["text"] for c in batch]
        
        batch_metadatas = []
        for c in batch:
            m = c.copy()
            # Xóa text trong metadata để tiết kiệm dung lượng
            if "text" in m:
                del m["text"]
            
            # Làm phẳng metadata: Chuyển list/dict thành string để ChromaDB chấp nhận
            for key, value in m.items():
                if isinstance(value, (list, dict)):
                    m[key] = str(value)
            
            batch_metadatas.append(m)
        
        # Nạp vào ChromaDB
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=batch_metadatas 
        )
        
        progress = min(i + batch_size, total_chunks)
        print(f"✅ Đã nạp: {progress}/{total_chunks} chunks...")

    print(f"\n✨ HOÀN TẤT! Tri thức Maturity Model V3 đã được nạp thành công.")
    print(f"📍 Database hiện có {collection.count()} mảnh tri thức chuyên sâu.")

if __name__ == "__main__":
    embed_maturity_v3()