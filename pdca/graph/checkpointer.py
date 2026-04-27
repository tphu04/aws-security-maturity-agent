"""Checkpointer factory — Phase C2.

`SqliteSaver.from_conn_string()` is a context manager — calling it directly
breaks. We construct the `sqlite3.Connection` ourselves and pass it to
`SqliteSaver(conn)`.

Caller must keep the returned saver alive for the lifetime of the graph
(typically as a module-level singleton or app lifespan resource).
"""

from __future__ import annotations

import os
import sqlite3
import warnings
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

DEFAULT_DB_PATH = "data/checkpoints/pdca_state.db"


def get_checkpointer(mode: str = "sqlite", db_path: str = DEFAULT_DB_PATH) -> Any:
    """Return a checkpointer suitable for the runtime.

    mode="sqlite" → SqliteSaver (state survives restart). Falls back to
    MemorySaver with a warning if the optional dependency is missing.
    mode="memory" → MemorySaver (tests, no file).
    """
    if mode == "memory":
        return MemorySaver()

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        warnings.warn(
            "SqliteSaver not available — falling back to MemorySaver. "
            "Install with: pip install langgraph-checkpoint-sqlite"
        )
        return MemorySaver()

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    # check_same_thread=False — FastAPI/uvicorn worker threads share the conn.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn)
