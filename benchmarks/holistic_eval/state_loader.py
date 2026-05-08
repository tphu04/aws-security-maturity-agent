"""Helper to fetch run-session state from the chatbot API + maturity KB.

Single source of truth: ``GET /v1/runs/{run_id}`` returns the rich session
view produced by ``pdca/api/state_adapter.to_run_session``. We use that
shape (not the raw ``PDCAState``) so the eval code stays decoupled from
internal field renames.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

CHATBOT_URL = (os.getenv("CHATBOT_API_URL") or "http://127.0.0.1:9002").rstrip("/")
KB_MATURITY_PATH = ROOT / "RAG" / "data" / "normalized" / "maturity_mappings.json"


def fetch_run_session(run_id: str, timeout: float = 30.0) -> dict[str, Any]:
    """Return the full RunSession dict for a given run_id.

    Raises ``httpx.HTTPStatusError`` if the API rejects the request.
    """
    with httpx.Client(timeout=timeout) as c:
        r = c.get(f"{CHATBOT_URL}/v1/runs/{run_id}")
        r.raise_for_status()
        return r.json()


def fetch_all_runs(run_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch each run sequentially. Returns dict keyed by run_id; missing
    runs are mapped to ``{"_error": str(exc)}`` so callers can decide.
    """
    out: dict[str, dict[str, Any]] = {}
    for rid in run_ids:
        try:
            out[rid] = fetch_run_session(rid)
        except Exception as exc:
            out[rid] = {"_error": f"{type(exc).__name__}: {exc}"}
    return out


def load_maturity_kb() -> dict[str, dict[str, Any]]:
    """Index ``RAG/data/normalized/maturity_mappings.json`` by check_id.

    Each entry stores the canonical mapping (highest-confidence + approved)
    used as ground truth for ``mapping_consistency`` checks.
    """
    if not KB_MATURITY_PATH.exists():
        raise FileNotFoundError(f"Maturity KB not found: {KB_MATURITY_PATH}")
    with open(KB_MATURITY_PATH, encoding="utf-8") as f:
        rows = json.load(f)

    by_check: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        cid = r.get("check_id")
        if not cid:
            continue
        by_check.setdefault(cid, []).append(r)

    canonical: dict[str, dict[str, Any]] = {}
    confidence_rank = {"high": 3, "medium": 2, "low": 1, None: 0, "": 0}
    for cid, entries in by_check.items():
        entries_sorted = sorted(
            entries,
            key=lambda e: (
                e.get("review_status") == "approved",
                confidence_rank.get(e.get("mapping_confidence"), 0),
                e.get("mapping_type") == "direct",
            ),
            reverse=True,
        )
        canonical[cid] = entries_sorted[0]
    return canonical


def load_run_ids(run_ids_file: Path | str, drop_warmup_first: bool = True) -> list[str]:
    """Load run IDs from a plaintext file (one per line). When
    ``drop_warmup_first`` is True the first entry is treated as warm-up
    and skipped — matching the convention used by ``run_d1_sessions.py``.
    """
    p = Path(run_ids_file)
    ids = [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    if drop_warmup_first and ids:
        ids = ids[1:]
    return ids


# Force UTF-8 stdout on Windows so prints with Vietnamese diacritics don't crash.
def configure_stdout_utf8() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
