import requests
import time
import json
import os

RAG_API_URL = "http://localhost:8119/v1/context/build"

# Define 3 specific test scenarios for EACH agent
test_cases = [
    # ---------------- PLANNING AGENT ----------------
    {
        "name": "Planning 1: Find IAM security checks",
        "consumer": "planning",
        "payload": {
            "query": "how to secure IAM users and root account?",
            "service": "iam",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5
        }
    },
    {
        "name": "Planning 2: Find S3 encryption checks",
        "consumer": "planning",
        "payload": {
            "query": "s3 bucket encryption",
            "service": "s3",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5
        }
    },
    {
        "name": "Planning 3: Find RDS public access checks",
        "consumer": "planning",
        "payload": {
            "query": "rds public access and encryption",
            "service": "rds",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5
        }
    },

    # ---------------- RISK EVALUATION AGENT ----------------
    {
        "name": "Risk 1: Evaluate S3 public access finding",
        "consumer": "risk",
        "payload": {
            "check_ids": ["s3_bucket_public_access"],
            "service": "s3",
            "include_mappings": True,
            "include_maturity": True,
        }
    },
    {
        "name": "Risk 2: Evaluate IAM MFA finding",
        "consumer": "risk",
        "payload": {
            "check_ids": ["iam_user_mfa_enabled"],
            "service": "iam",
            "include_mappings": True,
            "include_maturity": True,
        }
    },
    {
        "name": "Risk 3: Evaluate CloudTrail finding",
        "consumer": "risk",
        "payload": {
            "check_ids": ["cloudtrail_multi_region_enabled"],
            "service": "cloudtrail",
            "include_mappings": True,
            "include_maturity": True,
        }
    },

    # ---------------- REPORT AGENT ----------------
    {
        "name": "Report 1: Generate report for S3 public access",
        "consumer": "report",
        "payload": {
            "check_ids": ["s3_bucket_public_access"],
            "service": "s3",
            "include_mappings": True,
            "include_maturity": True,
        }
    },
    {
        "name": "Report 2: Generate report for IAM MFA",
        "consumer": "report",
        "payload": {
            "check_ids": ["iam_user_mfa_enabled"],
            "service": "iam",
            "include_mappings": True,
            "include_maturity": True,
        }
    },
    {
        "name": "Report 3: Generate report for CloudTrail",
        "consumer": "report",
        "payload": {
            "check_ids": ["cloudtrail_multi_region_enabled"],
            "service": "cloudtrail",
            "include_mappings": True,
            "include_maturity": True,
        }
    }
]

def run_benchmarks():
    results = []
    
    # 1. Health check
    print("Checking if RAG API is running on http://localhost:8119...")
    try:
        requests.get("http://localhost:8119/docs", timeout=3)
    except requests.exceptions.ConnectionError:
        print("ERROR: RAG API on localhost:8119 is not running.")
        print("Please start the server first using: cd C:\\Users\\trung\\Desktop\\DoAn\\RAG && python -m uvicorn app.main:app --port 8119")
        return
        
    print(f"Starting Benchmark...\n")
        
    for case in test_cases:
        case_name = case["name"]
        consumer = case["consumer"]
        payload = case["payload"].copy()
        payload["consumer"] = consumer
        
        case_results = {"scenario": case_name, "consumer": consumer, "run_stats": {}}
        
        start_time = time.time()
        try:
            response = requests.post(RAG_API_URL, json=payload, timeout=20)
            latency = time.time() - start_time
            status_code = response.status_code
            
            if status_code == 200:
                data = response.json()
                resp_data = data.get("data", {})
                payload = resp_data.get("payload", {})
                diagnostics = resp_data.get("diagnostics", {})
                meta = data.get("meta", {})
                bundle_stats = diagnostics.get("bundle_stats", {})
                
                # Validate JSON size of the newly built custom bundles
                bundle_size = -1
                if consumer == "planning" and payload.get("planning_bundle"):
                    bundle_size = len(json.dumps(payload["planning_bundle"]))
                elif consumer == "risk" and payload.get("risk_bundle"):
                    bundle_size = len(json.dumps(payload["risk_bundle"]))
                elif consumer == "report" and payload.get("report_bundle"):
                    bundle_size = len(json.dumps(payload["report_bundle"]))
                    
                case_results["run_stats"] = {
                    "status": "success",
                    "latency_ms": round(latency * 1000, 2),
                    "confidence": meta.get("confidence", "low"),
                    "review_req": meta.get("review_recommended", True),
                    "checks_found": bundle_stats.get("check_count", 0),
                    "mappings_found": bundle_stats.get("mapping_count", 0),
                    "capabilities_found": bundle_stats.get("capability_count", 0),
                    "custom_bundle_bytes": bundle_size,
                    "text_prompt_bytes": len(str(diagnostics.get("prompt_ready_context", {}))),
                    "api_response_data": resp_data
                }
            else:
                case_results["run_stats"] = {
                    "status": f"failed_http_{status_code}",
                    "error": response.text
                }
        except Exception as e:
             case_results["run_stats"] = {
                  "status": "exception",
                  "error": str(e)
             }
             
        results.append(case_results)
        time.sleep(0.5) # rate limit slightly
        
    # Write output to file
    output_path = os.path.join(os.path.dirname(__file__), "rag_benchmark_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
        
    print(f"\n--- BENCHMARK SUMMARY ---")
    for res in results:
        stats = res.get("run_stats", {})
        if stats.get("status") == "success":
             print(f"[{res['consumer'].upper():<8}] {res['scenario']:<45} "
                   f"| {stats['latency_ms']:>6.2f}ms "
                   f"| Conf: {stats['confidence']:<6} "
                   f"| Found (C/M/Cap): {stats['checks_found']}/{stats['mappings_found']}/{stats['capabilities_found']} "
                   f"| JSON Bundle Size: {stats['custom_bundle_bytes']} bytes")
        else:
             print(f"[{res['consumer'].upper():<8}] {res['scenario']:<45} | FAILED -> {stats.get('error')}")
                
    print(f"\n[+] Detailed results with full API responses saved to: {output_path}")

if __name__ == "__main__":
    run_benchmarks()