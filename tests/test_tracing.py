import pytest

from pdca.config import settings
from pdca.observability import tracing
from pdca.observability.context import run_with_context
from pdca.observability.tracing import NoopSpan, span, start_trace, traced, update_trace_metadata


class FakeObservation:
    def __init__(self, **payload):
        self.payload = payload
        self.updates = []
        self.events = []
        self.ended = False
        self.id = "obs-1"

    def update(self, **kwargs):
        self.updates.append(kwargs)

    def event(self, **kwargs):
        self.events.append(kwargs)

    def end(self):
        self.ended = True


class FakeClient:
    def __init__(self):
        self.spans = []
        self.traces = []
        self.flushed = False

    def span(self, **payload):
        obs = FakeObservation(**payload)
        self.spans.append(obs)
        return obs

    def trace(self, **payload):
        obs = FakeObservation(**payload)
        self.traces.append(obs)
        return obs

    def flush(self):
        self.flushed = True


class FakeManager:
    def __init__(self, obs):
        self.obs = obs

    def __enter__(self):
        return self.obs

    def __exit__(self, exc_type, exc, tb):
        self.obs.end()
        return False


class FakeV3Client:
    def __init__(self):
        self.spans = []
        self.trace_updates = []
        self.flushed = False

    def start_as_current_span(self, *, trace_context=None, name, input=None, metadata=None):
        obs = FakeObservation(
            trace_context=trace_context,
            name=name,
            input=input,
            metadata=metadata,
        )
        self.spans.append(obs)
        return FakeManager(obs)

    def update_current_trace(self, **payload):
        self.trace_updates.append(payload)

    def flush(self):
        self.flushed = True


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_flush_at_node", True)
    client = FakeClient()
    monkeypatch.setattr(tracing, "get_langfuse_client", lambda: client)
    monkeypatch.setattr("pdca.observability.langfuse_client.get_langfuse_client", lambda: client)
    yield client


def test_span_creates_observation_with_redacted_input_and_schema(reset):
    with run_with_context("run-1", lambda: span("x", input="arn:aws:s3:us-east-1:123456789012:bucket/company-prod-data", metadata={"a": "b"})) as sp:
        sp.update(output={"account": "123456789012"})

    obs = reset.spans[0]
    assert obs.payload["trace_id"] == "run-1"
    assert obs.payload["metadata"]["pdca.schema_version"] == "1.0"
    assert "123456789012" not in str(obs.payload)
    assert "123456789012" not in str(obs.updates)
    assert obs.ended


def test_span_exception_sets_error_and_reraises(reset):
    with pytest.raises(ValueError):
        with span("boom") as sp:
            assert sp.id == "obs-1"
            raise ValueError("arn:aws:iam::123456789012:role/Admin")

    assert reset.spans[0].updates[-1]["status"] == "error"
    assert "123456789012" not in reset.spans[0].updates[-1]["status_message"]


def test_span_noops_when_client_missing(monkeypatch):
    monkeypatch.setattr(tracing, "get_langfuse_client", lambda: None)

    with span("x") as sp:
        assert isinstance(sp, NoopSpan)


def test_traced_decorator_captures_return(reset):
    @traced("calc", capture_args=True, capture_return=True)
    def add(a, b):
        return a + b

    assert add(1, 2) == 3
    assert reset.spans[0].payload["name"] == "calc"
    assert reset.spans[0].updates[0]["output"] == 3


def test_start_trace_and_update_metadata(reset):
    with start_trace("run-2", user_request="scan s3") as trace:
        update_trace_metadata(account="123456789012")
        assert trace.trace_id == "run-2"

    assert reset.traces[0].payload["id"] == "run-2"
    assert "123456789012" not in str(reset.traces[0].updates)


def test_start_trace_context_is_cleared_after_exit(reset):
    with start_trace("run-3"):
        update_trace_metadata(inside=True)

    update_trace_metadata(after_exit=True)

    assert reset.traces[0].updates == [
        {"metadata": {"pdca.schema_version": "1.0", "inside": True}}
    ]


def test_v3_start_trace_uses_trace_context_and_nests_child(monkeypatch):
    client = FakeV3Client()
    monkeypatch.setattr(tracing, "get_langfuse_client", lambda: client)
    monkeypatch.setattr("pdca.observability.langfuse_client.get_langfuse_client", lambda: client)
    run_id = "12345678-1234-4abc-9def-1234567890ab"

    with start_trace(run_id, user_request="scan s3"):
        with span("child"):
            pass

    assert client.spans[0].payload["trace_context"] == {
        "trace_id": "1234567812344abc9def1234567890ab"
    }
    assert client.spans[0].payload["name"] == "pdca.run"
    assert client.spans[0].payload["metadata"]["pdca.run_id"] == run_id
    assert client.spans[1].payload["trace_context"] is None
    assert client.spans[0].ended
    assert client.spans[1].ended


def test_v3_span_without_active_trace_uses_run_id_trace_context(monkeypatch):
    client = FakeV3Client()
    monkeypatch.setattr(tracing, "get_langfuse_client", lambda: client)
    run_id = "12345678-1234-4abc-9def-1234567890ac"

    with run_with_context(run_id, lambda: span("standalone")):
        pass

    assert client.spans[0].payload["trace_context"] == {
        "trace_id": "1234567812344abc9def1234567890ac"
    }
