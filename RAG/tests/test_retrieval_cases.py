import json
import time
from typing import Any, Dict, List

import requests

BASE_URL = "http://127.0.0.1:8000"
HEADERS = {"Content-Type": "application/json"}


CHECK_QUERIES_EXACT = [
    "s3 public access",
    "s3 bucket public access",
    "s3 block public access",
    "s3 public access block",
    "s3 bucket level public access block",
]

CHECK_QUERIES_PARAPHRASE = [
    "how to prevent an s3 bucket from being publicly exposed",
    "stop public access to aws object storage",
    "restrict internet access to s3 buckets",
    "make sure s3 data cannot be publicly read",
    "prevent anonymous users from accessing bucket data",
]

CHECK_QUERIES_RISK = [
    "risk of exposing storage buckets to everyone on the internet",
    "misconfiguration that allows public reads on cloud storage",
    "security issue when bucket objects are publicly accessible",
    "how to avoid accidental public exposure of files in s3",
    "protect sensitive bucket data from public access",
]

MATURITY_QUERIES = [
    "block public access",
    "prevent public exposure of cloud resources",
    "control internet-facing access to storage services",
    "reduce risk of public data exposure",
    "security control for blocking public access",
]


def call_api(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE_URL}{path}"
    started = time.perf_counter()
    resp = requests.post(url, headers=HEADERS, json=payload, timeout=60)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    try:
        body = resp.json()
    except Exception:
        body = {"raw_text": resp.text}

    return {
        "status_code": resp.status_code,
        "latency_ms": latency_ms,
        "body": body,
    }


def summarize_results(api_name: str, query: str, result: Dict[str, Any]) -> None:
    print("\n" + "=" * 100)
    print(f"API      : {api_name}")
    print(f"QUERY    : {query}")
    print(f"STATUS   : {result['status_code']}")
    print(f"LATENCY  : {result['latency_ms']} ms")

    body = result["body"]
    print(f"RESULT   : {body.get('status')}")
    print(f"CONF     : {body.get('meta', {}).get('confidence')}")
    print(f"REVIEW   : {body.get('meta', {}).get('review_recommended')}")

    diagnostics = body.get("meta", {}).get("diagnostics", {})
    verification = diagnostics.get("verification", {})
    print(f"VALID    : {verification.get('valid')}")
    print(f"WARNINGS : {verification.get('warnings', [])}")

    results = body.get("data", {}).get("results", [])
    if not results:
        print("TOP      : <no results>")
        return

    print("TOP RESULTS:")
    for idx, item in enumerate(results[:5], start=1):
        print(
            f"  {idx}. doc_id={item.get('doc_id')} | "
            f"score={item.get('score')} | "
            f"matched_by={item.get('matched_by')} | "
            f"service={item.get('metadata', {}).get('service')} | "
            f"capability_id={item.get('metadata', {}).get('capability_id')} | "
            f"check_id={item.get('metadata', {}).get('check_id')}"
        )


def test_retrieve_checks(query: str, top_k: int = 5) -> None:
    payload = {
        "query": query,
        "top_k": top_k,
    }
    result = call_api("/v1/retrieve/checks", payload)
    summarize_results("retrieve-checks", query, result)


def test_retrieve_maturity(query: str, top_k: int = 5) -> None:
    payload = {
        "query": query,
        "top_k": top_k,
    }
    result = call_api("/v1/retrieve/maturity", payload)
    summarize_results("retrieve-maturity", query, result)


def run_group(title: str, queries: List[str], fn) -> None:
    print("\n" + "#" * 100)
    print(f"# {title}")
    print("#" * 100)
    for q in queries:
        fn(q)


if __name__ == "__main__":
    run_group("CHECK RETRIEVAL - EXACT", CHECK_QUERIES_EXACT, test_retrieve_checks)
    run_group("CHECK RETRIEVAL - PARAPHRASE", CHECK_QUERIES_PARAPHRASE, test_retrieve_checks)
    run_group("CHECK RETRIEVAL - RISK/INTENT", CHECK_QUERIES_RISK, test_retrieve_checks)
    run_group("MATURITY RETRIEVAL - CAPABILITY PARAPHRASE", MATURITY_QUERIES, test_retrieve_maturity)