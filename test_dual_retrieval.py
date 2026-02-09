import requests
import json

# ĐÃ ĐỔI SANG PORT 8111
API_URL = "http://localhost:8111/retrieve"

def test_dual_knowledge(question: str):
    print("\n" + "="*60)
    print(f"🤔 ĐANG TRUY VẤN: {question}")
    print("="*60)

    payload = {
        "query": question,
        "mode": "both",
        "top_k": 2
    }

    try:
        response = requests.post(API_URL, json=payload, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ Lỗi API ({response.status_code}): {response.text}")
            return

        data = response.json()

        print("\n📜 [KHO MATURITY - CHIẾN LƯỢC]")
        for item in data.get("maturity", []):
            print(f"  - {item['content'][:150]}... (Score: {item['score']})")

        print("\n🔧 [KHO PROWLER - KỸ THUẬT]")
        for item in data.get("technical", []):
            print(f"  - {item['content'][:150]}... (Score: {item['score']})")

    except Exception as e:
        print(f"❌ Lỗi kết nối: {e}")

if __name__ == "__main__":
    test_dual_knowledge("Should I use MFA for the root account?")
    test_dual_knowledge("iam_root_mfa_enabled")