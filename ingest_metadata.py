import json
import chromadb
from langchain_ollama import OllamaEmbeddings

# 1. Cấu hình Model
MODEL_NAME = "nomic-embed-text"
embeddings_model = OllamaEmbeddings(model=MODEL_NAME)

# 2. Khởi tạo Client
client = chromadb.PersistentClient(path="./prowler_vector_kb")

# 3. ĐỊNH NGHĨA MAPPING MỐI ĐE DỌA (THREAT MAPPING)
# Đây là "bí kíp" để RAG hiểu được ý định của người dùng
THREAT_MAPPING = {
    "s3_bucket_object_lock": "ransomware protection, data immutability, prevent encryption by attackers, anti-deletion",
    "s3_bucket_no_mfa_delete": "ransomware, accidental deletion, unauthorized data destruction",
    "s3_bucket_public_access": "data leak, sensitive data exposure, data breach, external access",
    "s3_bucket_kms_encryption": "data protection, encryption at rest, compliance, data theft prevention",
    "iam_root_mfa_enabled": "account takeover, credential theft, ransomware entry point",
    "iam_user_accesskey_unused": "stale credentials, attack surface reduction",
    "ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22": "brute force attack, unauthorized access, server hijack"
}

def run_ingestion():
    try:
        client.delete_collection(name="prowler_checks_v2")
        print("🗑️ Đã xóa collection cũ.")
    except:
        pass

    collection = client.create_collection(name="prowler_checks_v2")

    print("⏳ Đang nạp và làm giàu tri thức (Enriching Data)...")
    with open("all_checks_full.json", "r", encoding="utf-8") as f:
        all_checks = json.load(f)

    documents = []
    metadatas = []
    ids = []

    for check in all_checks:
        check_id = check.get("CheckID")
        
        # Lấy từ khóa liên quan đến mối đe dọa từ mapping ở trên
        threat_keywords = THREAT_MAPPING.get(check_id, "general security check")
        
        # KỸ THUẬT QUAN TRỌNG: Gộp cả "Threats" vào nội dung để Vectorize
        content = f"""
        Service: {check.get('ServiceName')}
        Title: {check.get('CheckTitle')}
        Description: {check.get('Description')}
        Risk: {check.get('Risk')}
        Related Threats: {threat_keywords}
        """
        
        documents.append(content)
        ids.append(check_id)
        metadatas.append({
            "check_id": check_id,
            "severity": check.get("Severity"),
            "service": check.get("ServiceName")
        })

    # Nạp theo batch
    batch_size = 100 
    for i in range(0, len(documents), batch_size):
        end = i + batch_size
        batch_docs = documents[i:end]
        batch_embeddings = embeddings_model.embed_documents(batch_docs)
        
        collection.add(
            ids=ids[i:end],
            embeddings=batch_embeddings,
            metadatas=metadatas[i:end],
            documents=batch_docs
        )
        print(f"✅ Đã nạp xong {min(end, len(documents))}/{len(documents)}")

    print("🎉 Hoàn tất! Giờ đây RAG đã hiểu về Ransomware và Data Leak.")

if __name__ == "__main__":
    run_ingestion()