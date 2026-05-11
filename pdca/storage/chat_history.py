"""ChatHistoryStore — SQLite persistence cho unified chat (Phase 2).

Thread = một cuộc hội thoại liền mạch. Mỗi turn (user hoặc assistant) là 1 row.
Run liên kết với thread khi user trigger scan trong thread đó (1 thread có thể
chứa 0..N run; 1 run thuộc về đúng 1 thread).

Schema cố ý phẳng và bất khả tri (JSON column cho intent_meta + payload) để
tránh phải migrate khi shape FE/BE đổi.

API:
    store = get_chat_store()
    thread_id = store.ensure_thread()             # tạo mới nếu None
    store.append(thread_id, role, content, ...)
    history = store.get_history(thread_id, limit=20)
    threads = store.list_threads(limit=50)
    store.delete_thread(thread_id)
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from pdca.observability.logger import get_logger

logger = get_logger(__name__)

DEFAULT_DB_PATH = "data/chat/chat_history.db"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class ChatRow:
    id: int
    thread_id: str
    run_id: Optional[str]
    role: str
    content: str
    message_type: str           # "user_text" | "qa_answer" | "suggest_action" | "run_started" | "text" | "error"
    payload_json: str = "{}"    # full payload echoed back to FE (sources, chips, etc.)
    intent_meta_json: Optional[str] = None
    created_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "run_id": self.run_id,
            "role": self.role,
            "content": self.content,
            "message_type": self.message_type,
            "payload": _safe_json_load(self.payload_json),
            "intent_meta": _safe_json_load(self.intent_meta_json) if self.intent_meta_json else None,
            "created_at": self.created_at,
        }


@dataclass
class ThreadInfo:
    thread_id: str
    title: str
    last_role: str
    last_content: str
    last_run_id: Optional[str]
    message_count: int
    created_at: float
    updated_at: float

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chat_threads (
    thread_id   TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id     TEXT NOT NULL,
    run_id        TEXT,
    role          TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content       TEXT NOT NULL,
    message_type  TEXT NOT NULL,
    payload_json  TEXT NOT NULL DEFAULT '{}',
    intent_meta_json TEXT,
    created_at    REAL NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES chat_threads(thread_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_thread ON chat_messages(thread_id, id);
CREATE INDEX IF NOT EXISTS idx_threads_updated ON chat_threads(updated_at DESC);
"""


class ChatHistoryStore:
    """Thread-safe SQLite store. Single writer lock; multiple reader threads OK.

    We open a fresh connection per call (sqlite3 default isolation is fine for
    this volume) — avoids passing connection between FastAPI worker threads.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._write_lock = threading.Lock()
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------

    def ensure_thread(self, thread_id: Optional[str] = None, title: str = "") -> str:
        """Return existing thread_id or create a new one."""
        if thread_id:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT thread_id FROM chat_threads WHERE thread_id = ?",
                    (thread_id,),
                ).fetchone()
                if row:
                    return row["thread_id"]
                # Caller asked for an unknown id → create with that id.
            new_id = thread_id
        else:
            new_id = f"thr_{uuid.uuid4().hex[:12]}"

        now = time.time()
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chat_threads (thread_id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (new_id, title or "New chat", now, now),
            )
            conn.commit()
        logger.info("chat thread created", extra={"thread_id": new_id})
        return new_id

    def update_thread_title(self, thread_id: str, title: str) -> None:
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "UPDATE chat_threads SET title = ?, updated_at = ? WHERE thread_id = ?",
                (title[:120], time.time(), thread_id),
            )
            conn.commit()

    def list_threads(self, limit: int = 50, offset: int = 0) -> List[ThreadInfo]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT t.thread_id, t.title, t.created_at, t.updated_at,
                       COUNT(m.id) AS msg_count,
                       COALESCE((SELECT role    FROM chat_messages WHERE thread_id = t.thread_id ORDER BY id DESC LIMIT 1), '') AS last_role,
                       COALESCE((SELECT content FROM chat_messages WHERE thread_id = t.thread_id ORDER BY id DESC LIMIT 1), '') AS last_content,
                       (SELECT run_id  FROM chat_messages WHERE thread_id = t.thread_id AND run_id IS NOT NULL ORDER BY id DESC LIMIT 1) AS last_run_id
                FROM chat_threads t
                LEFT JOIN chat_messages m ON m.thread_id = t.thread_id
                GROUP BY t.thread_id
                ORDER BY t.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [
            ThreadInfo(
                thread_id=r["thread_id"],
                title=r["title"],
                last_role=r["last_role"],
                last_content=_truncate(r["last_content"], 200),
                last_run_id=r["last_run_id"],
                message_count=int(r["msg_count"] or 0),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def delete_thread(self, thread_id: str) -> bool:
        with self._write_lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM chat_threads WHERE thread_id = ?", (thread_id,))
            conn.commit()
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def append(
        self,
        thread_id: str,
        role: str,
        content: str,
        message_type: str = "text",
        payload: Optional[Dict[str, Any]] = None,
        intent_meta: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> int:
        if role not in ("user", "assistant"):
            raise ValueError(f"invalid role: {role}")
        now = time.time()
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        intent_json = json.dumps(intent_meta, ensure_ascii=False) if intent_meta else None
        with self._write_lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO chat_messages "
                "(thread_id, run_id, role, content, message_type, payload_json, intent_meta_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (thread_id, run_id, role, content, message_type, payload_json, intent_json, now),
            )
            conn.execute(
                "UPDATE chat_threads SET updated_at = ? WHERE thread_id = ?",
                (now, thread_id),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_history(
        self,
        thread_id: str,
        limit: int = 20,
        order: str = "asc",
    ) -> List[ChatRow]:
        order_sql = "ASC" if order.lower() == "asc" else "DESC"
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM (
                    SELECT * FROM chat_messages WHERE thread_id = ?
                    ORDER BY id DESC LIMIT ?
                ) ORDER BY id {order_sql}
                """,
                (thread_id, limit),
            ).fetchall()
        return [
            ChatRow(
                id=r["id"], thread_id=r["thread_id"], run_id=r["run_id"],
                role=r["role"], content=r["content"], message_type=r["message_type"],
                payload_json=r["payload_json"] or "{}",
                intent_meta_json=r["intent_meta_json"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_recent_for_context(self, thread_id: str, limit: int = 4) -> List[Dict[str, str]]:
        """Return last N turns in {role, content} form for classifier context."""
        rows = self.get_history(thread_id, limit=limit, order="asc")
        return [{"role": r.role, "content": r.content} for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(s: Optional[str], n: int) -> str:
    if not s:
        return ""
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _safe_json_load(s: Optional[str]) -> Any:
    if not s:
        return {}
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_store_singleton: Optional[ChatHistoryStore] = None
_singleton_lock = threading.Lock()


def get_chat_store(db_path: Optional[str] = None) -> ChatHistoryStore:
    """Lazy singleton — created on first call, then reused per process."""
    global _store_singleton
    if _store_singleton is None:
        with _singleton_lock:
            if _store_singleton is None:
                _store_singleton = ChatHistoryStore(db_path or DEFAULT_DB_PATH)
    return _store_singleton


def _reset_singleton_for_tests() -> None:
    """Test-only: drop singleton so a fresh path can be used."""
    global _store_singleton
    with _singleton_lock:
        _store_singleton = None


__all__ = [
    "ChatHistoryStore", "ChatRow", "ThreadInfo",
    "get_chat_store", "DEFAULT_DB_PATH",
]
