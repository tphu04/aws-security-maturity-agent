import json
import os
import re

# Cấu hình đường dẫn
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "../data/raw/maturity_model_v3_detailed.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "../data/canonical/maturity_model_v3_canonical.json")

def slugify(text):
    """Biến tiêu đề thành ID chuẩn (ví dụ: 'Avoid root' -> 'avoid_root')"""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[-\s]+', '_', text).strip('_')

def canonicalize_v3():
    # Kiểm tra file raw v3 có tồn tại không
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Không tìm thấy file nguồn: {INPUT_FILE}")
        return

    print(f"🛠️ Đang chuẩn hóa dữ liệu chuyên sâu V3...")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    canonical_list = []

    for item in raw_data:
        # 1. Xác định mức độ nghiêm trọng dựa trên Phase
        phase_str = item.get("phase", "").lower()
        if "quickwins" in phase_str:
            severity = "critical"
        elif "foundational" in phase_str:
            severity = "high"
        else:
            severity = "medium"

        # 2. Tạo ID duy nhất
        item_id = f"mm_{slugify(item['title'])}"

        # 3. Gom nội dung "xịn" vào các trường của Agent
        # Chúng ta đưa 'How to check' và 'Guidance' vào phần Recommendation để Agent tư vấn được cả cách kiểm tra
        full_recommendation = f"{item['recommendation']}\n\n**How to check:**\n{item['how_to_check']}"
        if item['code_examples']:
            full_recommendation += "\n\n**Example/Code:**\n" + "\n".join(item['code_examples'])

        entry = {
            "id": item_id,
            "provider": "aws",
            "service": "security_strategy",
            "resource_type": "AwsAccount",
            "severity": severity,
            "categories": ["Compliance", "Maturity Model"],
            "check_type": ["AWS Security Maturity Model v2"],
            "content": {
                "title": item["title"],
                "summary": item["summary"],
                "risk_explanation": item["risk_explanation"] if item["risk_explanation"] else "Rủi ro chưa được xác định cụ thể trong tài liệu.",
                "recommendation": full_recommendation
            },
            "metadata": {
                "phase": item["phase"],
                "url": item["url"],
                "guidance": item["guidance"][:500] if item["guidance"] else ""
            }
        }
        canonical_list.append(entry)

    # Đảm bảo thư mục lưu trữ tồn tại
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(canonical_list, f, indent=2, ensure_ascii=False)

    print(f"✅ HOÀN TẤT! File Canonical V3 đã sẵn sàng tại: {OUTPUT_FILE}")
    print(f"📊 Đã xử lý {len(canonical_list)} khuyến nghị chi tiết.")

if __name__ == "__main__":
    canonicalize_v3()