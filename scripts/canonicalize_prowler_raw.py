import json
import re
from pathlib import Path

# ---------- Helpers ----------


def clean_text(text: str) -> str:
    """
    Clean text for semantic usage:
    - remove markdown (** ` ``` )
    - remove HTML tags
    - normalize whitespace
    """
    if not text:
        return ""

    # remove markdown formatting
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`{1,3}", "", text)

    # remove HTML
    text = re.sub(r"<[^>]+>", "", text)

    # normalize whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_check_type(check_types):
    """
    Reduce verbose CheckType paths into human-meaningful labels
    """
    if not isinstance(check_types, list):
        return []

    simplified = set()
    for ct in check_types:
        if "AWS Security Best Practices" in ct:
            simplified.add("AWS Security Best Practices")
        elif "NIST" in ct:
            simplified.add("NIST 800-53")
        elif "Denial of Service" in ct:
            simplified.add("Denial of Service")
        else:
            simplified.add(ct.split("/")[-1])

    return sorted(simplified)


def extract_references(raw):
    urls = []

    if isinstance(raw.get("AdditionalURLs"), list):
        urls.extend(raw.get("AdditionalURLs"))

    if raw.get("RelatedUrl"):
        urls.append(raw.get("RelatedUrl"))

    # remove empty + deduplicate
    return sorted({u for u in urls if u})


# ---------- Main Canonicalization ----------

INPUT = Path("data/raw/prowler_all_metadata.json")
OUTPUT = Path("data/canonical/prowler_canonical.json")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

with open(INPUT, "r", encoding="utf-8") as f:
    raw_data = json.load(f)

canonical = []

for m in raw_data:
    canonical.append(
        {
            "id": m.get("CheckID"),
            "provider": m.get("Provider"),
            "service": m.get("ServiceName"),
            "resource_type": m.get("ResourceType"),
            "severity": (m.get("Severity") or "").lower(),
            "categories": m.get("Categories", []),
            "check_type": normalize_check_type(m.get("CheckType")),
            "content": {
                "title": clean_text(m.get("CheckTitle")),
                "summary": clean_text(m.get("Description")),
                "risk_explanation": clean_text(m.get("Risk")),
                "recommendation": clean_text(
                    m.get("Remediation", {}).get("Recommendation", {}).get("Text", "")
                ),
            },
            "remediation": {
                "cli": m.get("Remediation", {}).get("Code", {}).get("CLI", ""),
                "terraform": m.get("Remediation", {})
                .get("Code", {})
                .get("Terraform", ""),
                "cloudformation": m.get("Remediation", {})
                .get("Code", {})
                .get("NativeIaC", ""),
                "console": m.get("Remediation", {}).get("Code", {}).get("Other", ""),
            },
            "references": extract_references(m),
            "relations": {
                "depends_on": m.get("DependsOn", []),
                "related_to": m.get("RelatedTo", []),
            },
        }
    )

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(canonical, f, indent=2, ensure_ascii=False)

print(f"✅ Canonicalized {len(canonical)} findings")
print(f"📄 Output written to: {OUTPUT}")
