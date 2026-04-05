"""
Centralized Configuration — Single Source of Truth
=====================================================
Tất cả service URLs và configuration được quản lý tại đây.
Đọc từ biến môi trường (hoặc .env) với fallback defaults.

Tham chiếu: Integration_Implementation_Plan.md — SLICE-0.1
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# RAG System (FastAPI — default port 8001)
# ---------------------------------------------------------------------------
RAG_API_URL: str = os.environ.get("RAG_API_URL", "http://localhost:8001")

# ---------------------------------------------------------------------------
# Scanner API (Prowler — default port 8000)
# ---------------------------------------------------------------------------
SCANNER_API_URL: str = os.environ.get("SCANNER_API_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# LLM (Ollama — default port 11434)
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_API_KEY: str = os.environ.get("OLLAMA_API_KEY", "ollama")
