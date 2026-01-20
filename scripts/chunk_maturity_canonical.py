import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def chunk_maturity_full_sync():
    input_path = os.path.join(BASE_DIR, "data", "canonical", "maturity_model_canonical.json")
    output_path = os.path.join(BASE_DIR, "data", "chunked", "maturity_model_chunks.json")
    
    if not os.path.exists(input_path):
        print(f"❌ Không tìm thấy file: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    chunks = []
    for item in data:
        # Lấy các thông tin cơ bản để dùng chung cho các chunks
        common_meta = {
            "check_id": item["id"],
            "provider": "aws",
            "service": item["service"],
            "resource_type": "AwsAccount",
            "severity": item["severity"],
            "categories": [item["metadata"]["category"]],
            "check_type": ["AWS Security Maturity Model v2"]
        }

        # --- 1. Tạo chunk OVERVIEW ---
        chunks.append({
            "chunk_id": f"{item['id']}::overview",
            "chunk_type": "overview",
            "text": f"{item['content']['title']}. {item['content']['summary']}",
            **common_meta
        })

        # --- 2. Tạo chunk RISK ---
        if item['content'].get('risk_explanation'):
            chunks.append({
                "chunk_id": f"{item['id']}::risk",
                "chunk_type": "risk",
                "text": item['content']['risk_explanation'],
                **common_meta
            })

        # --- 3. Tạo chunk RECOMMENDATION (Cái Phát vừa tìm thấy đây) ---
        if item['content'].get('recommendation'):
            chunks.append({
                "chunk_id": f"{item['id']}::recommendation",
                "chunk_type": "recommendation",
                "text": item['content']['recommendation'],
                **common_meta
            })

    # Đảm bảo thư mục tồn tại và lưu file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Đã tạo {len(chunks)} chunks (Overview, Risk, Recommendation) đồng bộ Prowler!")

if __name__ == "__main__":
    chunk_maturity_full_sync()