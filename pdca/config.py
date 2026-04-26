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
# RAG System (FastAPI — default port 8000)
# ---------------------------------------------------------------------------
RAG_API_URL: str = os.environ.get("RAG_API_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Scanner API (Prowler — default port 8000, same as api_server.py)
# ---------------------------------------------------------------------------
SCANNER_API_URL: str = os.environ.get("SCANNER_API_URL", "http://127.0.0.1:8000")

# ---------------------------------------------------------------------------
# LLM (Ollama — default port 11434)
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
OLLAMA_API_KEY: str = os.environ.get("OLLAMA_API_KEY", "ollama")

# ---------------------------------------------------------------------------
# Multi-query RAG Mode (MVP Phase 3)
# ---------------------------------------------------------------------------
# False (default) = legacy single-query path (backward compat)
# True            = Q1+Q2+Q3 parallel queries via /v1/retrieve/report_context
MULTI_QUERY_MODE: bool = os.environ.get("MULTI_QUERY_MODE", "false").lower() in ("1", "true", "yes")
