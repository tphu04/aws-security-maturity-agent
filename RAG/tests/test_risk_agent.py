import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import requests

# =========================
# Config
# =========================

BASE_URL = os.getenv("RAG_BASE_URL", "http://localhost:8000")
CONTEXT_URL = f"{BASE_URL}/v1/context/build"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
OLLAMA_GENERATE_URL = f"{OLLAMA_URL}/api/generate"

# Set RUN_LLM=0 if you only want to inspect the built prompt
RUN_LLM = os.getenv("RUN_LLM", "1") == "1"

ROOT = Path(__file__).resolve().parents[1]
DEBUG_DIR = ROOT / "tests" / "debug_outputs"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


# =========================
# Helpers
# =========================

def print_section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def print_json(label: str, payload: Any) -> None:
    print(f"\n[{label}]")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def dump_json_file(filename: str, payload: Any) -> Path:
    out_path = DEBUG_DIR / filename
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def dump_text_file(filename: str, text: str) -> Path:
    out_path = DEBUG_DIR / filename
    out_path.write_text(text, encoding="utf-8")
    return out_path


def safe_json(resp: requests.Response) -> Optional[Dict[str, Any]]:
    try:
        return resp.json()
    except Exception:
        return None


# =========================
# Step 1: Build risk context
# =========================

def fetch_risk_context() -> Dict[str, Any]:
    payload = {
        "consumer": "risk",
        "provider": "aws",
        "service": "s3",
        "check_ids": [
            "s3_bucket_level_public_access_block"
        ],
        "include_mappings": True,
        "include_maturity": True,
        "top_k": 5,
        "debug": True,
        "retrieval_mode": "hybrid",
    }

    print_section("1. CALL /v1/context/build")
    print(f"[URL] {CONTEXT_URL}")
    print_json("REQUEST", payload)

    resp = requests.post(CONTEXT_URL, json=payload, timeout=90)
    print(f"[HTTP] status_code = {resp.status_code}")

    resp_json = safe_json(resp)
    if resp_json is None:
        raise RuntimeError(f"Context API did not return valid JSON:\n{resp.text[:3000]}")

    dump_path = dump_json_file("risk_agent_context_response.json", resp_json)
    print(f"[DEBUG FILE] saved full context response to: {dump_path}")

    if resp.status_code != 200:
        raise RuntimeError(json.dumps(resp_json, indent=2, ensure_ascii=False))

    return resp_json


# =========================
# Step 2: Build prompt
# =========================

def build_prompt(context_response: Dict[str, Any]) -> str:
    data = context_response.get("data", {}) or {}
    risk_bundle = data.get("risk_bundle")
    prompt_ready_context = data.get("prompt_ready_context")

    if not risk_bundle:
        raise RuntimeError("No risk_bundle found in /v1/context/build response")
    if not prompt_ready_context:
        raise RuntimeError("No prompt_ready_context found in /v1/context/build response")

    instruction = """You are a cloud security risk evaluation agent.

Your task is to produce a concise risk assessment for the primary finding.

Rules:
- Use the primary finding as the main subject under assessment.
- Use related findings only as supporting context.
- Do not assume related findings are confirmed failed findings unless explicitly stated.
- Use control mappings to connect the finding to maturity capabilities.
- Use maturity context to explain why the issue matters, what good practice looks like, and how the issue should be interpreted.
- Do not copy guidance questions verbatim.
- Acknowledge uncertainty where mapping confidence is medium or low.
- Be specific, grounded, and concise.
- Return valid JSON only.
- Do not wrap the JSON in markdown fences.

Return JSON in exactly this format:
{
  "risk_statement": "...",
  "impact": "...",
  "rationale": "...",
  "recommendation_summary": "..."
}
"""

    prompt = (
        f"{instruction}\n\n"
        f"[PROMPT READY CONTEXT]\n"
        f"{json.dumps(prompt_ready_context, indent=2, ensure_ascii=False)}\n\n"
        f"[RISK BUNDLE]\n"
        f"{json.dumps(risk_bundle, indent=2, ensure_ascii=False)}\n"
    )

    dump_json_file(
        "risk_agent_prompt_payload.json",
        {
            "prompt_ready_context": prompt_ready_context,
            "risk_bundle": risk_bundle,
            "instruction": instruction,
        },
    )
    dump_text_file("risk_agent_prompt.txt", prompt)

    print_section("2. PROMPT PREVIEW")
    primary = (risk_bundle or {}).get("primary_finding")
    if primary:
        print_json("PRIMARY FINDING", primary)
    print("[DEBUG FILE] saved prompt to tests/debug_outputs/risk_agent_prompt.txt")

    return prompt


# =========================
# Step 3: Call Ollama
# =========================

def call_ollama(prompt: str) -> Dict[str, Any]:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
        },
    }

    print_section("3. CALL OLLAMA")
    print(f"[URL] {OLLAMA_GENERATE_URL}")
    print_json("OLLAMA REQUEST META", {"model": OLLAMA_MODEL, "temperature": 0.2})

    resp = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=300)
    print(f"[HTTP] status_code = {resp.status_code}")

    resp_json = safe_json(resp)
    if resp_json is None:
        raise RuntimeError(f"Ollama did not return valid JSON:\n{resp.text[:3000]}")

    dump_path = dump_json_file("risk_agent_ollama_raw_response.json", resp_json)
    print(f"[DEBUG FILE] saved raw Ollama response to: {dump_path}")

    if resp.status_code != 200:
        raise RuntimeError(json.dumps(resp_json, indent=2, ensure_ascii=False))

    return resp_json


def extract_ollama_text(ollama_response: Dict[str, Any]) -> str:
    content = ollama_response.get("response")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama response field 'response' is empty")
    return content.strip()


def try_parse_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        cleaned = text.strip()

        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        return json.loads(cleaned)


# =========================
# Main
# =========================

def main() -> None:
    context_response = fetch_risk_context()
    prompt = build_prompt(context_response)

    if not RUN_LLM:
        print_section("3. SKIP OLLAMA CALL")
        print("RUN_LLM=0 -> only built and dumped the prompt.")
        return

    ollama_response = call_ollama(prompt)
    ollama_text = extract_ollama_text(ollama_response)

    dump_text_file("risk_agent_ollama_text.txt", ollama_text)

    print_section("4. OLLAMA RAW TEXT")
    print(ollama_text)

    try:
        parsed = try_parse_json(ollama_text)
        dump_json_file("risk_agent_output.json", parsed)
        print_json("PARSED RISK OUTPUT", parsed)
    except Exception as exc:
        print_section("5. JSON PARSE FAILED")
        print(f"Could not parse model output as JSON: {exc}")
        print("[INFO] Raw text was saved to tests/debug_outputs/risk_agent_ollama_text.txt")


if __name__ == "__main__":
    main()