import json
from pathlib import Path

import requests

BASE_URL = "http://localhost:8000"

ROOT = Path(__file__).resolve().parents[1]
NORMALIZED_MATURITY_PATH = ROOT / "data" / "normalized" / "maturity_capabilities.json"
DEBUG_DIR = ROOT / "tests" / "debug_outputs"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


def print_section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def safe_get(dct, *keys, default=None):
    cur = dct
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def dump_json_file(filename: str, payload: dict) -> Path:
    out_path = DEBUG_DIR / filename
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def print_json(label: str, payload) -> None:
    print(f"\n[{label}]")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def load_normalized_capability(capability_id: str):
    if not NORMALIZED_MATURITY_PATH.exists():
        print(f"[ERROR] file not found: {NORMALIZED_MATURITY_PATH}")
        return None, []

    payload = json.loads(NORMALIZED_MATURITY_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        print("[ERROR] maturity_capabilities.json is not a list")
        return None, []

    found = None
    for item in payload:
        if item.get("capability_id") == capability_id:
            found = item
            break
    return found, payload


def test_normalized_file():
    print_section("1. CHECK NORMALIZED MATURITY FILE")

    capability_id = "block_public_access"
    found, payload = load_normalized_capability(capability_id)

    print(f"[INFO] total capability docs: {len(payload)}")

    if found:
        print("[OK] found capability in normalized file")
        print_json(
            "CAPABILITY",
            {
                "doc_id": found.get("doc_id"),
                "capability_id": found.get("capability_id"),
                "capability_name": found.get("capability_name"),
                "stage": found.get("stage"),
                "summary": found.get("summary"),
                "risk_explanation": found.get("risk_explanation"),
                "guidance": found.get("guidance"),
                "how_to_check": found.get("how_to_check"),
                "recommended_practices_count": len(
                    found.get("recommended_practices") or []
                ),
            },
        )
    else:
        print(f"[ERROR] capability_id='{capability_id}' not found in normalized file")


def test_retrieve_maturity():
    print_section("2. CALL /v1/retrieve/maturity DIRECTLY")

    url = f"{BASE_URL}/v1/retrieve/maturity"
    payload = {
        "query": "block_public_access",
        "capability_id": "block_public_access",
        "provider": "aws",
        "top_k": 5,
        "retrieval_mode": "hybrid",
        "debug": True,
    }

    print(f"[URL] {url}")
    print_json("REQUEST", payload)

    resp = requests.post(url, json=payload, timeout=60)
    print(f"[HTTP] status_code = {resp.status_code}")

    resp_json = resp.json()
    out_path = dump_json_file("debug_retrieve_maturity.json", resp_json)
    print(f"[DEBUG FILE] saved full response to: {out_path}")

    results = safe_get(resp_json, "data", "results", default=[]) or []
    diagnostics = safe_get(resp_json, "meta", "diagnostics", default={}) or {}

    print("\n[SUMMARY]")
    print(f"result_count = {len(results)}")
    print(f"requested_capability_id = {diagnostics.get('requested_capability_id')}")
    print(f"resolved_capability_ids = {diagnostics.get('resolved_capability_ids')}")
    print(
        f"exact_capability_match_found = {diagnostics.get('exact_capability_match_found')}"
    )

    if results:
        first = results[0]
        first_meta = first.get("metadata", {}) or {}
        print_json(
            "FIRST RESULT",
            {
                "doc_id": first.get("doc_id"),
                "score": first.get("score"),
                "matched_by": first.get("matched_by"),
                "metadata": {
                    "doc_id": first_meta.get("doc_id"),
                    "doc_type": first_meta.get("doc_type"),
                    "capability_id": first_meta.get("capability_id"),
                    "capability_name": first_meta.get("capability_name"),
                    "stage": first_meta.get("stage"),
                    "summary": first_meta.get("summary"),
                    "risk_explanation": first_meta.get("risk_explanation"),
                    "guidance": first_meta.get("guidance"),
                    "how_to_check": first_meta.get("how_to_check"),
                    "recommended_practices": first_meta.get("recommended_practices"),
                },
            },
        )
    else:
        print("[WARN] no results returned from /v1/retrieve/maturity")


def test_context_build():
    print_section("3. CALL /v1/context/build")

    url = f"{BASE_URL}/v1/context/build"
    payload = {
        "consumer": "risk",
        "provider": "aws",
        "service": "s3",
        "check_ids": ["s3_bucket_level_public_access_block"],
        "include_mappings": True,
        "include_maturity": True,
        "top_k": 5,
        "debug": True,
        "retrieval_mode": "hybrid",
    }

    print(f"[URL] {url}")
    print_json("REQUEST", payload)

    resp = requests.post(url, json=payload, timeout=60)
    print(f"[HTTP] status_code = {resp.status_code}")

    resp_json = resp.json()
    out_path = dump_json_file("debug_context_build.json", resp_json)
    print(f"[DEBUG FILE] saved full response to: {out_path}")

    data = safe_get(resp_json, "data", default={}) or {}
    diagnostics = safe_get(resp_json, "meta", "diagnostics", default={}) or {}

    selected_checks = data.get("selected_checks", []) or []
    selected_mappings = data.get("selected_mappings", []) or []
    selected_capabilities = data.get("selected_capabilities", []) or []
    prompt_ready_context = data.get("prompt_ready_context", {}) or {}

    print("\n[SUMMARY]")
    print(f"selected_check_count = {len(selected_checks)}")
    print(f"selected_mapping_count = {len(selected_mappings)}")
    print(f"selected_capability_count = {len(selected_capabilities)}")
    print(f"requested_capability_ids = {diagnostics.get('requested_capability_ids')}")
    print(f"resolved_capability_ids = {diagnostics.get('resolved_capability_ids')}")
    print(f"raw_maturity_result_count = {diagnostics.get('raw_maturity_result_count')}")
    print(f"maturity_result_count = {diagnostics.get('maturity_result_count')}")

    if selected_checks:
        first = selected_checks[0]
        meta = first.get("metadata", {}) or {}
        print_json(
            "FIRST SELECTED CHECK",
            {
                "check_id": first.get("check_id"),
                "doc_id": first.get("doc_id"),
                "service": first.get("service"),
                "title": first.get("title"),
                "short_text": first.get("short_text"),
                "score": first.get("score"),
                "confidence": first.get("confidence"),
                "matched_by": first.get("matched_by"),
                "metadata": {
                    "doc_type": meta.get("doc_type"),
                    "check_id": meta.get("check_id"),
                    "title": meta.get("title"),
                    "severity": meta.get("severity"),
                    "description": meta.get("description"),
                    "risk": meta.get("risk"),
                    "remediation": meta.get("remediation"),
                    "resource_type": meta.get("resource_type"),
                },
            },
        )
    else:
        print("\n[FIRST SELECTED CHECK]")
        print("No selected checks")

    if selected_mappings:
        first = selected_mappings[0]
        meta = first.get("metadata", {}) or {}
        print_json(
            "FIRST SELECTED MAPPING",
            {
                "check_id": first.get("check_id"),
                "capability_id": first.get("capability_id"),
                "capability_name": first.get("capability_name"),
                "mapping_confidence": first.get("mapping_confidence"),
                "mapping_type": first.get("mapping_type"),
                "review_status": first.get("review_status"),
                "rationale": first.get("rationale"),
                "metadata": {
                    "doc_id": meta.get("doc_id"),
                    "doc_type": meta.get("doc_type"),
                    "service": meta.get("service"),
                    "domain": meta.get("domain"),
                    "mapping_confidence": meta.get("mapping_confidence"),
                    "mapping_reason": meta.get("mapping_reason"),
                    "review_status": meta.get("review_status"),
                    "mapping_type": meta.get("mapping_type"),
                },
            },
        )
    else:
        print("\n[FIRST SELECTED MAPPING]")
        print("No selected mappings")

    if selected_capabilities:
        first = selected_capabilities[0]
        meta = first.get("metadata", {}) or {}
        print_json(
            "FIRST SELECTED CAPABILITY",
            {
                "capability_id": first.get("capability_id"),
                "doc_id": first.get("doc_id"),
                "capability_name": first.get("capability_name"),
                "domain": first.get("domain"),
                "short_text": first.get("short_text"),
                "score": first.get("score"),
                "confidence": first.get("confidence"),
                "metadata": {
                    "doc_type": meta.get("doc_type"),
                    "capability_id": meta.get("capability_id"),
                    "capability_name": meta.get("capability_name"),
                    "stage": meta.get("stage"),
                    "summary": meta.get("summary"),
                    "risk_explanation": meta.get("risk_explanation"),
                    "guidance": meta.get("guidance"),
                    "how_to_check": meta.get("how_to_check"),
                    "recommended_practices": meta.get("recommended_practices"),
                },
            },
        )
    else:
        print("\n[FIRST SELECTED CAPABILITY]")
        print("No selected capabilities")

    risk_bundle = data.get("risk_bundle")
    if risk_bundle:
        print_json("RISK BUNDLE", risk_bundle)
    else:
        print("\n[RISK BUNDLE]")
        print("No risk_bundle returned")
    print_json("PROMPT READY CONTEXT", prompt_ready_context)


if __name__ == "__main__":
    test_normalized_file()
    test_retrieve_maturity()
    test_context_build()
