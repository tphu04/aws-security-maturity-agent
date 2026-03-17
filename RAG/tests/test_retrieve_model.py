# test_retrieval_modes.py
import json
import sys
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "http://localhost:8000"

CHECKS_ENDPOINT = f"{BASE_URL}/v1/retrieve/checks"
MATURITY_ENDPOINT = f"{BASE_URL}/v1/retrieve/maturity"


CHECK_CASES = [
    {
        "name": "checks_exact_check_id",
        "body": {
            "check_id": "s3_bucket_level_public_access_block",
            "top_k": 5,
            "debug": True,
        },
        "expected_any": [
            "s3_bucket_level_public_access_block",
        ],
    },
    {
        "name": "checks_paraphrase_public_access",
        "body": {
            "query": "prevent public access to s3 buckets",
            "top_k": 5,
            "debug": True,
        },
        "expected_any": [
            "s3_bucket_level_public_access_block",
            "s3_account_level_public_access_blocks",
        ],
    },
    {
        "name": "checks_semantic_private_by_default",
        "body": {
            "query": "make object storage private by default",
            "top_k": 5,
            "debug": True,
        },
        "expected_any": [
            "s3_bucket_level_public_access_block",
            "s3_account_level_public_access_blocks",
        ],
    },
]

MATURITY_CASES = [
    {
        "name": "maturity_exact_capability_phrase",
        "body": {
            "query": "block public access",
            "top_k": 5,
            "debug": True,
        },
        "expected_any": [
            "block-public-access",
            "1_quickwins_block_public_access",
        ],
    },
    {
        "name": "maturity_semantic_public_exposure",
        "body": {
            "query": "prevent public exposure of cloud resources",
            "top_k": 5,
            "debug": True,
        },
        "expected_any": [
            "block-public-access",
            "1_quickwins_block_public_access",
        ],
    },
]

MODES = ["lexical", "vector", "hybrid"]


def post_json(url: str, body: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
    resp = requests.post(url, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def extract_doc_ids(data: Dict[str, Any]) -> List[str]:
    results = data.get("data", {}).get("results", [])
    ids: List[str] = []
    for item in results:
        doc_id = item.get("doc_id")
        if doc_id:
            ids.append(doc_id)
            continue

        # fallback: check-specific or maturity-specific identifiers
        if item.get("check_id"):
            ids.append(item["check_id"])
        elif item.get("capability_id"):
            ids.append(item["capability_id"])
        else:
            ids.append("<unknown>")
    return ids


def extract_meta(data: Dict[str, Any]) -> Dict[str, Any]:
    # Support either envelope-style {meta:...} or service-style {data:{...meta...}}
    if "meta" in data and isinstance(data["meta"], dict):
        return data["meta"]
    if "data" in data and isinstance(data["data"], dict):
        inner = data["data"]
        if "meta" in inner and isinstance(inner["meta"], dict):
            return inner["meta"]
    return {}


def expected_hit(doc_ids: List[str], expected_any: Optional[List[str]]) -> bool:
    if not expected_any:
        return False
    lowered = [x.lower() for x in doc_ids]
    return any(exp.lower() in lowered for exp in expected_any)


def print_case_result(
    suite: str,
    case_name: str,
    mode: str,
    body: Dict[str, Any],
    payload: Dict[str, Any],
    expected_any: Optional[List[str]],
) -> None:
    meta = extract_meta(payload)
    diagnostics = meta.get("diagnostics", {}) if isinstance(meta, dict) else {}
    results = payload.get("data", {}).get("results", [])
    doc_ids = extract_doc_ids(payload)
    top1 = doc_ids[0] if doc_ids else None

    print("=" * 100)
    print(f"[{suite}] case={case_name} mode={mode}")
    print(f"query/check_id: {body.get('query') or body.get('check_id')}")
    print(f"top1: {top1}")
    print(f"top_ids: {doc_ids[:5]}")
    print(f"expected_hit_top5: {expected_hit(doc_ids[:5], expected_any)}")
    print(f"confidence: {meta.get('confidence')}")
    print(f"degraded: {meta.get('degraded')}")
    print(f"verification: {json.dumps(meta.get('verification', {}), ensure_ascii=False)}")

    print("--- diagnostics ---")
    print(f"retrieval_mode: {diagnostics.get('retrieval_mode')}")
    print(f"lexical_candidate_count: {diagnostics.get('lexical_candidate_count')}")
    print(f"vector_candidate_count: {diagnostics.get('vector_candidate_count')}")
    print(f"top_lexical_doc_ids: {diagnostics.get('top_lexical_doc_ids')}")
    print(f"top_vector_doc_ids: {diagnostics.get('top_vector_doc_ids')}")
    print(f"used_vector: {diagnostics.get('used_vector')}")
    print(f"used_hybrid: {diagnostics.get('used_hybrid')}")
    print(f"vector_error: {diagnostics.get('vector_error')}")

    if results:
        print("--- first result ---")
        print(json.dumps(results[0], ensure_ascii=False, indent=2))
    else:
        print("--- first result ---")
        print("No results returned")


def run_suite(
    suite_name: str,
    url: str,
    cases: List[Dict[str, Any]],
) -> int:
    failures = 0

    for case in cases:
        for mode in MODES:
            body = dict(case["body"])
            body["retrieval_mode"] = mode

            try:
                payload = post_json(url, body)
                print_case_result(
                    suite=suite_name,
                    case_name=case["name"],
                    mode=mode,
                    body=body,
                    payload=payload,
                    expected_any=case.get("expected_any"),
                )
            except requests.HTTPError as exc:
                failures += 1
                print("=" * 100)
                print(f"[{suite_name}] case={case['name']} mode={mode}")
                print(f"HTTP ERROR: {exc}")
                if exc.response is not None:
                    try:
                        print(exc.response.text)
                    except Exception:
                        pass
            except Exception as exc:
                failures += 1
                print("=" * 100)
                print(f"[{suite_name}] case={case['name']} mode={mode}")
                print(f"ERROR: {type(exc).__name__}: {exc}")

    return failures


def main() -> int:
    print(f"Testing against BASE_URL={BASE_URL}")
    total_failures = 0

    total_failures += run_suite("checks", CHECKS_ENDPOINT, CHECK_CASES)
    total_failures += run_suite("maturity", MATURITY_ENDPOINT, MATURITY_CASES)

    print("=" * 100)
    print(f"Done. failures={total_failures}")
    return 1 if total_failures else 0


if __name__ == "__main__":
    sys.exit(main())