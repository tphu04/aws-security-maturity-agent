"""Unit tests for ChatHistoryStore — pure SQLite, no LLM/RAG needed."""

from __future__ import annotations

import os
import tempfile

import pytest

from pdca.storage.chat_history import ChatHistoryStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "chat.db"
    return ChatHistoryStore(db_path=str(db))


class TestThreadLifecycle:
    def test_ensure_thread_creates_new(self, store):
        tid = store.ensure_thread(title="First")
        assert tid.startswith("thr_")
        threads = store.list_threads()
        assert len(threads) == 1
        assert threads[0].thread_id == tid
        assert threads[0].title == "First"

    def test_ensure_thread_idempotent(self, store):
        tid = store.ensure_thread()
        same = store.ensure_thread(thread_id=tid)
        assert same == tid
        assert len(store.list_threads()) == 1

    def test_ensure_thread_with_custom_id(self, store):
        tid = store.ensure_thread(thread_id="thr_custom_abc")
        assert tid == "thr_custom_abc"

    def test_delete_thread(self, store):
        tid = store.ensure_thread()
        store.append(tid, "user", "hi", "user_text")
        assert store.delete_thread(tid) is True
        assert store.list_threads() == []
        assert store.get_history(tid) == []

    def test_delete_unknown(self, store):
        assert store.delete_thread("thr_nope") is False


class TestMessages:
    def test_append_and_get(self, store):
        tid = store.ensure_thread()
        store.append(tid, "user", "what is s3?", "user_text")
        store.append(
            tid, "assistant", "S3 is …", "qa_answer",
            payload={"markdown": "S3 is …", "sources": []},
            intent_meta={"intent": "qa", "confidence": 0.9},
        )
        rows = store.get_history(tid)
        assert len(rows) == 2
        assert rows[0].role == "user"
        assert rows[1].role == "assistant"
        assert rows[1].message_type == "qa_answer"
        d = rows[1].to_dict()
        assert d["payload"]["markdown"] == "S3 is …"
        assert d["intent_meta"]["confidence"] == 0.9

    def test_append_rejects_bad_role(self, store):
        tid = store.ensure_thread()
        with pytest.raises(ValueError):
            store.append(tid, "system", "x", "user_text")

    def test_get_history_limit_keeps_most_recent(self, store):
        tid = store.ensure_thread()
        for i in range(10):
            store.append(tid, "user", f"msg {i}", "user_text")
        rows = store.get_history(tid, limit=3)
        assert len(rows) == 3
        # asc order = oldest of the last 3 first
        assert rows[0].content == "msg 7"
        assert rows[-1].content == "msg 9"

    def test_get_recent_for_context(self, store):
        tid = store.ensure_thread()
        store.append(tid, "user", "a", "user_text")
        store.append(tid, "assistant", "b", "qa_answer")
        store.append(tid, "user", "c", "user_text")
        ctx = store.get_recent_for_context(tid, limit=2)
        assert ctx == [{"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]

    def test_thread_preview_reflects_latest(self, store):
        tid = store.ensure_thread(title="X")
        store.append(tid, "user", "first user", "user_text")
        store.append(tid, "assistant", "last assistant content", "qa_answer")
        threads = store.list_threads()
        assert threads[0].last_role == "assistant"
        assert "last assistant" in threads[0].last_content
        assert threads[0].message_count == 2


class TestRunLinkage:
    def test_run_id_persisted(self, store):
        tid = store.ensure_thread()
        store.append(tid, "user", "scan s3", "user_text")
        store.append(tid, "assistant", "started", "run_started", run_id="run_xyz")
        threads = store.list_threads()
        assert threads[0].last_run_id == "run_xyz"
