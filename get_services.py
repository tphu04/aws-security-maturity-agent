import os
import json
import prowler

# Tìm đường dẫn đến thư mục chứa metadata của AWS trong thư viện Prowler
prowler_path = os.path.dirname(prowler.__file__)
aws_services_path = os.path.join(prowler_path, "providers", "aws", "services")

all_full_metadata = []

print(f"⏳ Đang quét metadata tại: {aws_services_path}")

for root, dirs, files in os.walk(aws_services_path):
    for file in files:
        if file.endswith(".metadata.json"):
            full_path = os.path.join(root, file)
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    all_full_metadata.append(metadata)
            except Exception as e:
                print(f"❌ Lỗi khi đọc {file}: {e}")

# Lưu kết quả ra file để nạp vào VectorDB
output_file = "all_checks_full_metadata.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(all_full_metadata, f, indent=4)

print(f"✅ Hoàn tất! Đã trích xuất {len(all_full_metadata)} checks vào {output_file}")