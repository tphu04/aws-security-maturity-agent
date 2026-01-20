import chromadb
from langchain_ollama import OllamaEmbeddings
import os

# Đường dẫn tới database của bạn
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(BASE_DIR), "prowler_vector_kb")

def verify_maturity_db():
    print(f"🔍 Đang kết nối tới database tại: {DB_PATH}...")
    
    # 1. Kết nối Client
    client = chromadb.PersistentClient(path=DB_PATH)
    
    # 2. Lấy Collection
    try:
        collection = client.get_collection(name="aws_maturity_model_kb")
        count = collection.count()
        print(f"✅ Kết nối thành công! Số lượng bản ghi (chunks) hiện có: {count}")
        
        if count == 0:
            print("⚠️ Cảnh báo: Collection trống rỗng.")
            return

        # 3. Thử truy vấn ngữ nghĩa (Semantic Search)
        # Giả sử chúng ta tìm về MFA - một mục quan trọng trong Maturity Model
        query_text = "MFA for root account security"
        print(f"\n🤖 Đang thử tìm kiếm với câu hỏi: '{query_text}'...")
        
        # Lưu ý: Cần dùng model embedding tương ứng để query
        # Nếu collection đã được nạp bằng nomic-embed-text thì query cũng phải dùng nó
        results = collection.query(
            query_texts=[query_text],
            n_results=2,
            include=["documents", "metadatas", "distances"]
        )

        # 4. Hiển thị kết quả
        print("\n--- KẾT QUẢ TRUY VẤN THỬ ---")
        for i in range(len(results['ids'][0])):
            print(f"\n[Kết quả {i+1}] (Khoảng cách vector: {results['distances'][0][i]:.4f})")
            print(f"ID: {results['ids'][0][i]}")
            print(f"Nội dung: {results['documents'][0][i]}")
            print(f"Metadata: {results['metadatas'][0][i]}")
            
    except Exception as e:
        print(f"❌ Lỗi: Không tìm thấy collection hoặc lỗi truy vấn: {e}")

if __name__ == "__main__":
    verify_maturity_db()