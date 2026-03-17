import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

headers = {
    "Content-Type": "application/json"
}


def print_result(name, resp, start):
    latency = round((time.time() - start) * 1000, 2)

    print("\n==============================")
    print(f"TEST: {name}")
    print("status:", resp.status_code)
    print("latency:", latency, "ms")

    try:
        data = resp.json()
        print(json.dumps(data, indent=2))
    except:
        print(resp.text)


# -----------------------------
# health
# -----------------------------
def test_health():
    url = f"{BASE_URL}/health"

    start = time.time()
    resp = requests.get(url)

    print_result("health", resp, start)


# -----------------------------
# ready
# -----------------------------
def test_ready():
    url = f"{BASE_URL}/ready"

    start = time.time()
    resp = requests.get(url)

    print_result("ready", resp, start)


# -----------------------------
# build-info
# -----------------------------
def test_build_info():
    url = f"{BASE_URL}/build-info"

    start = time.time()
    resp = requests.get(url)

    print_result("build-info", resp, start)


# -----------------------------
# retrieve checks
# -----------------------------
def test_retrieve_checks():

    url = f"{BASE_URL}/v1/retrieve/checks"

    payload = {
        "query": "s3 public access",
        "top_k": 5
    }

    start = time.time()
    resp = requests.post(url, headers=headers, json=payload)

    print_result("retrieve-checks", resp, start)


# -----------------------------
# retrieve maturity
# -----------------------------
def test_retrieve_maturity():

    url = f"{BASE_URL}/v1/retrieve/maturity"

    payload = {
        "query": "block public access",
        "top_k": 5
    }

    start = time.time()
    resp = requests.post(url, headers=headers, json=payload)

    print_result("retrieve-maturity", resp, start)


# -----------------------------
# resolve mapping
# -----------------------------
def test_resolve_mapping():

    url = f"{BASE_URL}/v1/resolve/mapping"

    payload = {
        "check_id": "s3_bucket_public_access",
        "service": "s3"
    }

    start = time.time()
    resp = requests.post(url, headers=headers, json=payload)

    print_result("resolve-mapping", resp, start)


# -----------------------------
# build context
# -----------------------------
def test_build_context():

    url = f"{BASE_URL}/v1/build/context"

    payload = {
        "finding": {
            "check_id": "s3_bucket_public_access",
            "service": "s3",
            "status": "FAIL",
            "severity": "high",
            "resource_id": "example-bucket",
            "resource_type": "AwsS3Bucket"
        },
        "include_check_context": True,
        "include_mapping_context": True,
        "include_maturity_context": True
    }

    start = time.time()
    resp = requests.post(url, headers=headers, json=payload)

    print_result("build-context", resp, start)


# -----------------------------
# main
# -----------------------------
def run_all():

    print("\n========== RAG API TEST ==========")

    test_health()
    test_ready()
    test_build_info()

    test_retrieve_checks()
    test_retrieve_maturity()

    test_resolve_mapping()
    test_build_context()


if __name__ == "__main__":
    run_all()