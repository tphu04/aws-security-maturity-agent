import os
import json
import prowler
from pathlib import Path


def collect_flat_metadata():
    """
    Collect ALL prowler *.metadata.json files
    and merge them into ONE flat JSON array.
    No filtering, no transformation, no wrapper.
    """

    prowler_root = Path(prowler.__file__).parent
    services_root = prowler_root / "providers" / "aws" / "services"

    all_metadata = []

    for root, _, files in os.walk(services_root):
        for file in files:
            if file.endswith(".metadata.json"):
                file_path = Path(root) / file

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)

                    # ⬅️ APPEND NGUYÊN OBJECT GỐC
                    all_metadata.append(metadata)

                except Exception as e:
                    print(f"❌ Failed to read {file_path}: {e}")

    return all_metadata


if __name__ == "__main__":
    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    data = collect_flat_metadata()

    output_file = output_dir / "prowler_all_metadata.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Collected {len(data)} metadata files")
    print(f"📄 Output: {output_file}")
