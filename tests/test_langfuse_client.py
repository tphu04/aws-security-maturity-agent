import types

import pytest

from pdca.config import settings
from pdca.agents.shared import callbacks
from pdca.observability import langfuse_client as lf


@pytest.fixture(autouse=True)
def reset_langfuse(monkeypatch):
    lf._reset_for_tests()
    monkeypatch.setattr(settings, "langfuse_enabled", False)
    monkeypatch.setattr(settings, "langfuse_public_key", None)
    monkeypatch.setattr(settings, "langfuse_secret_key", None)
    monkeypatch.setattr(settings, "langfuse_sample_rate", 1.0)
    monkeypatch.setattr(settings, "langfuse_circuit_breaker_threshold", 3)
    monkeypatch.setattr(settings, "langfuse_circuit_breaker_window_s", 60)
    yield
    lf._reset_for_tests()


def test_disabled_returns_none_without_init():
    assert lf.get_langfuse_client() is None
    assert lf.get_langfuse_handler() is None


def test_init_failure_returns_none_and_records_failure(monkeypatch):
    class FailingLangfuse:
        def __init__(self, **kwargs):
            raise RuntimeError("bad config")

    fake_module = types.SimpleNamespace(Langfuse=FailingLangfuse)

    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk")
    monkeypatch.setitem(__import__("sys").modules, "langfuse", fake_module)

    assert lf.get_langfuse_client() is None
    assert lf._breaker_state["failures"] == 1


def test_breaker_trips_after_threshold(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_circuit_breaker_threshold", 2)

    lf.record_failure()
    assert not lf.is_tripped()

    lf.record_failure()
    assert lf.is_tripped()
    assert lf.get_langfuse_handler() is None


def test_breaker_resets_after_window(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_circuit_breaker_threshold", 1)
    monkeypatch.setattr(settings, "langfuse_circuit_breaker_window_s", 1)

    lf.record_failure()
    assert lf.is_tripped()
    lf._breaker_state["tripped_at"] = lf._now() - 2

    assert not lf.is_tripped()


def test_flush_safe_records_failure(monkeypatch):
    class FailingClient:
        def flush(self):
            raise RuntimeError("network down")

    monkeypatch.setattr(lf, "_langfuse", FailingClient())

    lf.flush_safe()

    assert lf._breaker_state["failures"] == 1


def test_handler_is_added_when_client_and_callback_are_available(monkeypatch):
    class Handler:
        def __init__(self, *, public_key=None):
            self.kwargs = {"public_key": public_key}

    fake_module = types.SimpleNamespace(CallbackHandler=Handler)

    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk")
    monkeypatch.setattr(lf, "_langfuse", object())
    monkeypatch.setitem(__import__("sys").modules, "langfuse.langchain", fake_module)

    handler = lf.get_langfuse_handler()

    assert isinstance(handler, Handler)
    assert handler.kwargs["public_key"] == "pk"


def test_client_init_passes_redaction_mask_and_runtime_settings(monkeypatch):
    created = {}

    class Client:
        def __init__(self, **kwargs):
            created.update(kwargs)

    fake_module = types.SimpleNamespace(Langfuse=Client)

    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk")
    monkeypatch.setattr(settings, "langfuse_host", "http://lf")
    monkeypatch.setattr(settings, "langfuse_environment", "staging")
    monkeypatch.setattr(settings, "langfuse_sample_rate", 0.5)
    monkeypatch.setattr(lf.random, "random", lambda: 0.0)
    monkeypatch.setitem(__import__("sys").modules, "langfuse", fake_module)

    client = lf.get_langfuse_client()

    assert isinstance(client, Client)
    assert created["host"] == "http://lf"
    assert created["environment"] == "staging"
    assert created["sample_rate"] == 0.5
    assert created["timeout"] == 2
    assert created["mask"](data={"account": "123456789012"})["account"] == "***9012"


def test_get_callbacks_returns_timer_only_when_langfuse_disabled(monkeypatch):
    monkeypatch.setattr(callbacks, "get_langfuse_handler", lambda: None)

    result = callbacks.get_callbacks()

    assert len(result) == 1
    assert isinstance(result[0], callbacks.TimerCallback)


def test_get_callbacks_includes_langfuse_handler_and_extra(monkeypatch):
    handler = object()
    extra = object()
    monkeypatch.setattr(callbacks, "get_langfuse_handler", lambda: handler)

    result = callbacks.get_callbacks(extra=[extra])

    assert isinstance(result[0], callbacks.TimerCallback)
    assert result[1:] == [handler, extra]
