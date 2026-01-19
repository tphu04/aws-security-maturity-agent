import json
from pathlib import Path

INPUT = Path("data/canonical/prowler_canonical.json")
OUTPUT = Path("data/chunked/prowler_chunks.json")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

with open(INPUT, "r", encoding="utf-8") as f:
    canonical_data = json.load(f)

chunks = []

for item in canonical_data:
    check_id = item["id"]

    base_metadata = {
        "check_id": check_id,
        "provider": item.get("provider"),
        "service": item.get("service"),
        "resource_type": item.get("resource_type"),
        "severity": item.get("severity"),
        "categories": item.get("categories", []),
        "check_type": item.get("check_type", []),
    }

    content = item.get("content", {})

    # ---------- OVERVIEW CHUNK ----------
    title = content.get("title", "").strip()
    summary = content.get("summary", "").strip()

    if title or summary:
        overview_text = ". ".join(t for t in [title, summary] if t)

        chunks.append(
            {
                "chunk_id": f"{check_id}::overview",
                "chunk_type": "overview",
                "text": overview_text,
                **base_metadata,
            }
        )

    # ---------- RISK CHUNK ----------
    risk_text = content.get("risk_explanation", "").strip()
    if risk_text:
        chunks.append(
            {
                "chunk_id": f"{check_id}::risk",
                "chunk_type": "risk",
                "text": risk_text,
                **base_metadata,
            }
        )

    # ---------- RECOMMENDATION CHUNK ----------
    recommendation_text = content.get("recommendation", "").strip()
    if recommendation_text:
        chunks.append(
            {
                "chunk_id": f"{check_id}::recommendation",
                "chunk_type": "recommendation",
                "text": recommendation_text,
                **base_metadata,
            }
        )


with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(chunks, f, indent=2, ensure_ascii=False)

print(f"✅ Chunking completed")
print(f"📦 Total findings: {len(canonical_data)}")
print(f"🧩 Total chunks: {len(chunks)}")
print(f"📄 Output file: {OUTPUT}")
