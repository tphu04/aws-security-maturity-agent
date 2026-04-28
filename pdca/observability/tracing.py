"""Manual tracing primitives used by Phase I instrumentation."""

from __future__ import annotations

import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional

from pdca.config import settings
from pdca.observability.langfuse_client import (
    flush_safe,
    get_langfuse_client,
    langfuse_trace_id,
    record_failure,
)
from pdca.observability.logger import get_logger, get_run_id
from pdca.observability.redaction import safe_redact

logger = get_logger(__name__)

SCHEMA_VERSION = "1.0"
_current_trace: ContextVar[Optional["TraceHandle"]] = ContextVar("langfuse_trace", default=None)


class NoopSpan:
    """No-op object returned when Langfuse is disabled or unavailable."""

    id: Optional[str] = None

    def update(self, output: Any = None, **kwargs: Any) -> None:
        return None

    def set_status(self, status: str, message: Optional[str] = None) -> None:
        return None

    def add_event(self, name: str, metadata: Optional[dict[str, Any]] = None) -> None:
        return None

    def end(self) -> None:
        return None


class SpanHandle(NoopSpan):
    def __init__(self, raw: Any = None) -> None:
        self._raw = raw
        self.id = getattr(raw, "id", None) or getattr(raw, "observation_id", None)

    def update(self, output: Any = None, **kwargs: Any) -> None:
        payload = dict(kwargs)
        if output is not None:
            payload["output"] = safe_redact(output)
        if "metadata" in payload:
            payload["metadata"] = safe_redact(payload["metadata"])
        updater = getattr(self._raw, "update", None)
        if callable(updater):
            updater(**payload)

    def set_status(self, status: str, message: Optional[str] = None) -> None:
        payload = {"status": status}
        if message:
            payload["status_message"] = safe_redact(message)
        updater = getattr(self._raw, "update", None)
        if callable(updater):
            updater(**payload)

    def add_event(self, name: str, metadata: Optional[dict[str, Any]] = None) -> None:
        event = getattr(self._raw, "event", None) or getattr(self._raw, "add_event", None)
        if callable(event):
            event(name=name, metadata=safe_redact(metadata or {}))

    def end(self) -> None:
        end = getattr(self._raw, "end", None)
        if callable(end):
            end()


class TraceHandle(SpanHandle):
    def __init__(
        self,
        raw: Any = None,
        trace_id: Optional[str] = None,
        manager: Any = None,
    ) -> None:
        super().__init__(raw)
        self.trace_id = trace_id
        self._manager = manager
        self._token = None

    def activate(self) -> "TraceHandle":
        if self._token is None:
            self._token = _current_trace.set(self)
        return self

    def __enter__(self) -> "TraceHandle":
        return self.activate()

    def __exit__(self, exc_type: Any, exc: Exception | None, tb: Any) -> bool:
        if exc is not None:
            self.set_status("error", f"{exc.__class__.__name__}: {exc}")
        end_trace(self)
        return False


def _metadata(metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    merged = {"pdca.schema_version": SCHEMA_VERSION}
    if metadata:
        merged.update(metadata)
    return merged


def _accepts_kw(params: Any, name: str) -> bool:
    return name in params or any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )


def _has_explicit_kw(params: Any, name: str) -> bool:
    return name in params


def _trace_context(run_id: str) -> dict[str, str]:
    return {"trace_id": langfuse_trace_id(run_id)}


@contextmanager
def _span_impl(
    name: str,
    input: Any,
    metadata: Optional[dict[str, Any]],
    kind: str,
    captured_run_id: str,
    parent_span_id: Optional[str] = None,
    trace_id: Optional[str] = None,
):
    client = get_langfuse_client()
    if client is None:
        yield NoopSpan()
        return

    payload = {
        "name": name,
        "input": safe_redact(input),
        "metadata": safe_redact(_metadata(metadata)),
    }

    raw = None
    manager = None
    try:
        if hasattr(client, "start_as_current_span"):
            params = inspect.signature(client.start_as_current_span).parameters
            if (
                (trace_id or captured_run_id)
                and (_current_trace.get() is None or parent_span_id)
                and _has_explicit_kw(params, "trace_context")
            ):
                payload["trace_context"] = _trace_context(trace_id or captured_run_id)
                if parent_span_id:
                    payload["trace_context"]["parent_span_id"] = parent_span_id
            elif captured_run_id and _accepts_kw(params, "trace_id"):
                payload["trace_id"] = captured_run_id
            manager = client.start_as_current_span(**payload)
            raw = manager.__enter__()
        elif hasattr(client, kind):
            params = inspect.signature(getattr(client, kind)).parameters
            if (trace_id or captured_run_id) and _has_explicit_kw(params, "trace_context"):
                payload["trace_context"] = _trace_context(trace_id or captured_run_id)
                if parent_span_id:
                    payload["trace_context"]["parent_span_id"] = parent_span_id
            elif captured_run_id and _accepts_kw(params, "trace_id"):
                payload["trace_id"] = captured_run_id
            raw = getattr(client, kind)(**payload)
        elif hasattr(client, "span"):
            params = inspect.signature(client.span).parameters
            if (trace_id or captured_run_id) and _has_explicit_kw(params, "trace_context"):
                payload["trace_context"] = _trace_context(trace_id or captured_run_id)
                if parent_span_id:
                    payload["trace_context"]["parent_span_id"] = parent_span_id
            elif captured_run_id:
                payload["trace_id"] = captured_run_id
            raw = client.span(**payload)
        else:
            yield NoopSpan()
            return
        handle = SpanHandle(raw)
    except Exception as exc:
        record_failure()
        logger.debug("Langfuse span init failed for %s: %s", name, exc)
        yield NoopSpan()
        return

    try:
        yield handle
    except Exception as exc:
        handle.set_status("error", f"{exc.__class__.__name__}: {exc}")
        raise
    finally:
        try:
            if manager is not None:
                manager.__exit__(None, None, None)
            else:
                handle.end()
        except Exception as exc:
            record_failure()
            logger.debug("Langfuse span close failed for %s: %s", name, exc)


def span(
    name: str,
    *,
    input: Any = None,
    metadata: Optional[dict[str, Any]] = None,
    kind: str = "span",
    parent_span_id: Optional[str] = None,
    trace_id: Optional[str] = None,
):
    """Create a best-effort Langfuse span context manager.

    `run_id` is captured eagerly so callers can stage the span inside a
    `run_with_context()` block and still observe the right `trace_id` once
    the `with` clause actually enters the body.
    """
    return _span_impl(name, input, metadata, kind, get_run_id(), parent_span_id, trace_id)


def traced(name: str, capture_args: bool = False, capture_return: bool = False):
    """Decorator wrapper around `span()`."""
    def _decorator(fn):
        def _wrapper(*args: Any, **kwargs: Any):
            span_input = None
            if capture_args:
                visible_args = args[1:] if args else args
                span_input = {"args": visible_args, "kwargs": kwargs}
            with span(name, input=span_input) as sp:
                result = fn(*args, **kwargs)
                if capture_return:
                    sp.update(output=result)
                return result

        _wrapper.__name__ = getattr(fn, "__name__", name)
        _wrapper.__doc__ = getattr(fn, "__doc__", None)
        return _wrapper

    return _decorator


def start_trace(run_id: str, **metadata: Any) -> TraceHandle:
    """Open or reuse a Langfuse trace with `trace_id == run_id`."""
    client = get_langfuse_client()
    if client is None:
        return TraceHandle(trace_id=run_id).activate()

    raw = None
    manager = None
    try:
        payload = {
            "name": "pdca.run",
            "metadata": safe_redact(_metadata({"pdca.run_id": run_id, **metadata})),
        }
        if "user_request" in metadata:
            payload["input"] = safe_redact(metadata["user_request"])

        if hasattr(client, "start_as_current_span"):
            params = inspect.signature(client.start_as_current_span).parameters
            if _accepts_kw(params, "trace_context"):
                payload["trace_context"] = _trace_context(run_id)
            elif _accepts_kw(params, "trace_id"):
                payload["trace_id"] = run_id
            manager = client.start_as_current_span(**payload)
            raw = manager.__enter__()
        else:
            payload["id"] = run_id
            trace_factory = getattr(client, "trace", None)
            if callable(trace_factory):
                raw = trace_factory(**payload)
    except Exception as exc:
        record_failure()
        logger.debug("Langfuse trace init failed: %s", exc)
        raw = None
        manager = None

    handle = TraceHandle(raw, trace_id=run_id, manager=manager).activate()

    try:
        updater = getattr(client, "update_current_trace", None)
        if callable(updater) and raw is not None:
            update_payload = {
                "name": "pdca.run",
                "metadata": safe_redact(_metadata({"pdca.run_id": run_id, **metadata})),
            }
            if "user_request" in metadata:
                update_payload["input"] = safe_redact(metadata["user_request"])
            updater(**update_payload)
    except Exception as exc:
        record_failure()
        logger.debug("Langfuse trace metadata update failed: %s", exc)

    return handle


def end_trace(handle: TraceHandle) -> None:
    try:
        if handle._manager is not None:
            handle._manager.__exit__(None, None, None)
        else:
            handle.end()
    finally:
        try:
            flush_safe()
        finally:
            if handle._token is not None:
                _current_trace.reset(handle._token)
                handle._token = None


def update_trace_metadata(**kwargs: Any) -> None:
    handle = _current_trace.get()
    if handle is None:
        return
    handle.update(metadata=_metadata(kwargs))


def flush_at_node() -> None:
    if settings.langfuse_flush_at_node:
        flush_safe()


__all__ = [
    "NoopSpan",
    "SpanHandle",
    "TraceHandle",
    "end_trace",
    "flush_at_node",
    "span",
    "start_trace",
    "traced",
    "update_trace_metadata",
]
