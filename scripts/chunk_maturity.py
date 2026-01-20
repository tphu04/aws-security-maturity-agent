import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "../data/canonical/maturity_model_v3_canonical.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "../data/chunked/maturity_model_v3_chunks.json")

def clean_security_text(text):
    """Làm sạch sâu: Xử lý dính chữ, rác UI và định dạng văn bản"""
    if not text: return ""
    
    # 1. Xóa rác UI và thông báo video
    noise_patterns = [
        r"Your browser does not support the video tag\.",
        r"\(Free capability\)",
        r"\(paid capability\)",
        r"As part of the AWS Free Tier.*",
        r"The service has a 30-day trial period.*"
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    
    # 2. Sửa lỗi dính chữ (Ví dụ: 'pricingManagement' -> 'pricing Management')
    # Thêm khoảng trắng trước các từ viết hoa dính liền hoặc URL
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = re.sub(r'(?<!\s)https://', ' https://', text)
    
    # 3. Xóa các tiêu đề rỗng (How to check mà không có nội dung)
    text = re.sub(r'\*\*How to check:\*\*\s*$', '', text, flags=re.MULTILINE)
    
    # 4. Thu gọn khoảng trắng
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def split_long_text(text, max_chars=1500):
    """Nếu text quá dài, cắt thành các đoạn nhỏ hơn nhưng vẫn giữ ngữ cảnh"""
    if len(text) <= max_chars:
        return [text]
    
    # Cắt theo dấu câu gần nhất với max_chars
    parts = []
    while len(text) > max_chars:
        split_idx = text.rfind('. ', 0, max_chars)
        if split_idx == -1: split_idx = max_chars
        parts.append(text[:split_idx + 1].strip())
        text = text[split_idx + 1:].strip()
    if text: parts.append(text)
    return parts

def chunk_maturity_v3():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Không tìm thấy file: {INPUT_FILE}")
        return

    print(f"📦 Đang bắt đầu Chunking và Làm sạch dữ liệu chuyên sâu...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    chunks = []
    for item in data:
        common_meta = {
            "check_id": item["id"],
            "provider": "aws",
            "service": item["service"],
            "severity": item["severity"],
            "phase": item["metadata"]["phase"],
            "url": item["metadata"]["url"]
        }

        # --- 1. Chunk TỔNG QUAN ---
        summary = clean_security_text(item['content']['summary'])
        chunks.append({
            "chunk_id": f"{item['id']}::overview",
            "chunk_type": "overview",
            "text": f"{item['content']['title']}. {summary}",
            **common_meta
        })

        # --- 2. Chunk RỦI RO ---
        risk = clean_security_text(item['content']['risk_explanation'])
        if risk:
            chunks.append({
                "chunk_id": f"{item['id']}::risk",
                "chunk_type": "risk",
                "text": risk,
                **common_meta
            })

        # --- 3. Chunk KHUYẾN NGHỊ (Có xử lý đoạn dài) ---
        rec_raw = clean_security_text(item['content']['recommendation'])
        if item["metadata"].get("guidance"):
            rec_raw += "\n\n**Guidance for assessments:** " + item["metadata"]["guidance"]
        
        # Tách nhỏ nếu recommendation quá dài
        rec_sub_parts = split_long_text(rec_raw)
        for i, part in enumerate(rec_sub_parts):
            suffix = f"_{i}" if len(rec_sub_parts) > 1 else ""
            chunks.append({
                "chunk_id": f"{item['id']}::recommendation{suffix}",
                "chunk_type": "recommendation",
                "text": part,
                **common_meta
            })

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Xong! Đã tạo {len(chunks)} chunks 'tinh khiết' cho RAG.")

if __name__ == "__main__":
    chunk_maturity_v3()