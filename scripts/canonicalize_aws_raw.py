import json
import os

def canonicalize_maturity():
    # Đường dẫn file (sửa theo cấu trúc thư mục của bạn)
    raw_path = "scripts/data/raw/maturity_model_raw.json"
    output_path = "scripts/data/canonical/maturity_model_canonical.json"
    
    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
        
    canonical_data = []
    for i, item in enumerate(raw_data):
        # Tạo ID duy nhất
        clean_name = item['recommendation'].lower().replace(" ", "_").replace("-", "_")
        check_id = f"mm_{item['category'].lower().split()[0]}_{clean_name}"[:50]

        # Xác định độ nghiêm trọng dựa trên Phase
        severity = "high" if "Phase 1" in item['phase'] else "medium"
        if "Phase 3" in item['phase'] or "Phase 4" in item['phase']:
            severity = "low"

        entry = {
            "id": check_id,
            "provider": "aws",
            "service": item['category'].lower().replace(" & ", "_").replace(" ", "_"),
            "severity": severity,
            "content": {
                "title": item['recommendation'],
                "summary": f"Maturity Level: {item['phase']}. Thuộc nhóm: {item['category']}.",
                "risk_explanation": f"Việc không thực hiện {item['recommendation']} làm giảm khả năng bảo mật của hệ thống ở cấp độ {item['phase']}.",
                "recommendation": item['recommendation'] # Bạn có thể bổ sung thêm text tư vấn ở đây
            },
            "metadata": {
                "phase": item['phase'],
                "category": item['category']
            }
        }
        canonical_data.append(entry)
        
    # Lưu file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(canonical_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Đã đồng bộ hóa Maturity Model sang cấu trúc Prowler tại: {output_path}")

if __name__ == "__main__":
    canonicalize_maturity()