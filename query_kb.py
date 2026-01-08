import chromadb
from langchain_ollama import OllamaEmbeddings

class ProwlerKnowledgeBase:
    def __init__(self):
        # 1. Đường dẫn phải chuẩn xác với file Ingest
        self.db_path = "./prowler_vector_kb"
        self.client = chromadb.PersistentClient(path=self.db_path)
        
        # 2. Model phải là nomic để ra đúng 768 dims
        self.embeddings_model = OllamaEmbeddings(model="nomic-embed-text")
        
        # 3. Tên Collection PHẢI KHỚP với file Ingest (prowler_checks_v2)
        try:
            self.collection = self.client.get_collection(name="prowler_checks_v2")
            print("✅ Đã kết nối thành công tới VectorDB (768 dims).")
        except Exception as e:
            print(f"❌ Lỗi: Không tìm thấy collection 'prowler_checks_v2'. Hãy chạy ingest_metadata.py trước!")
            raise e

    def query(self, user_input: str, n_results: int = 5):
        # Chuyển câu hỏi thành vector 768
        query_vector = self.embeddings_model.embed_query(user_input)
        
        # Thực hiện truy vấn
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=n_results
        )
        return results

if __name__ == "__main__":
    # Khởi tạo KB
    try:
        kb = ProwlerKnowledgeBase()
        
        # Thử nghiệm với câu hỏi thực tế
        user_question = "S3 bucket encryption with KMS keys"
        
        res = kb.query(user_question)
        
        print(f"\n🔍 Kết quả tìm kiếm cho: '{user_question}'")
        if res['ids'] and len(res['ids'][0]) > 0:
            for i in range(len(res['ids'][0])):
                check_id = res['ids'][0][i]
                doc_preview = res['documents'][0][i][:120].replace('\n', ' ')
                print(f"[{i+1}] ID: {check_id}")
                print(f"    Nội dung: {doc_preview}...")
        else:
            print("❓ Không tìm thấy kết quả nào phù hợp.")
            
    except Exception as e:
        print(f"💥 Crash: {e}")