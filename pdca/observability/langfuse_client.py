"""Lazy Langfuse client factory with best-effort failure isolation."""

from __future__ import annotations

import atexit
import hashlib
import inspect
import random
import re
import time
from typing import Any, Optional

from pdca.config import settings
from pdca.observability.logger import get_logger
from pdca.observability.redaction import safe_redact

logger = get_logger(__name__)

_langfuse: Optional[Any] = None
_handler: Optional[Any] = None
_init_warning_logged = False
_breaker_state: dict[str, Optional[float] | int] = {
    "failures": 0,
    "first_failure_at": None,
    "tripped_at": None,
}
_LANGFUSE_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _now() -> float:
    return time.monotonic()


def reset_breaker() -> None:
    _breaker_state["failures"] = 0
    _breaker_state["first_failure_at"] = None
    _breaker_state["tripped_at"] = None


def is_tripped() -> bool:
    tripped_at = _breaker_state.get("tripped_at")
    if not tripped_at:
        return False
    if _now() - float(tripped_at) >= settings.langfuse_circuit_breaker_window_s:
        reset_breaker()
        return False
    return True


def record_failure() -> None:
    now = _now()
    window = settings.langfuse_circuit_breaker_window_s
    first_failure_at = _breaker_state.get("first_failure_at")

    if not first_failure_at or now - float(first_failure_at) > window:
        _breaker_state["first_failure_at"] = now
        _breaker_state["failures"] = 1
    else:
        _breaker_state["failures"] = int(_breaker_state.get("failures") or 0) + 1

    if int(_breaker_state["failures"]) >= settings.langfuse_circuit_breaker_threshold:
        if not _breaker_state.get("tripped_at"):
            logger.warning("Langfuse circuit breaker tripped")
        _breaker_state["tripped_at"] = now


def _enabled_for_this_process() -> bool:
    if not settings.langfuse_enabled:
        return False
    if is_tripped():
        return False
    if settings.langfuse_sample_rate <= 0:
        return False
    if settings.langfuse_sample_rate < 1 and random.random() > settings.langfuse_sample_rate:
        return False
    return True


def _log_init_warning(message: str, exc: Exception | None = None) -> None:
    global _init_warning_logged
    if _init_warning_logged:
        return
    _init_warning_logged = True
    if exc is None:
        logger.warning(message)
    else:
        logger.warning("%s: %s", message, exc)


def _mask_for_langfuse(*, data: Any, **kwargs: Any) -> Any:
    return safe_redact(data)


def langfuse_trace_id(run_id: str) -> str:
    """Return the SDK v3 trace id used for a PDCA run id.

    Langfuse v3 requires 32 lowercase hex chars. PDCA run_id is usually a UUID
    string with hyphens, so we preserve the same 128-bit value via ``uuid.hex``.
    Non-UUID IDs are deterministically hashed.
    """
    candidate = (run_id or "").replace("-", "").lower()
    if _LANGFUSE_TRACE_ID_RE.match(candidate):
        return candidate
    return hashlib.md5((run_id or "").encode("utf-8")).hexdigest()


def get_langfuse_client() -> Optional[Any]:
    """Return a singleton Langfuse client, or None when disabled/unavailable."""
    global _langfuse
    if _langfuse is not None:
        return None if is_tripped() else _langfuse
    if not _enabled_for_this_process():
        return None

    try:
        from langfuse import Langfuse

        _langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            environment=settings.langfuse_environment,
            sample_rate=settings.langfuse_sample_rate,
            timeout=settings.langfuse_request_timeout_s,
            mask=_mask_for_langfuse,
        )
        return _langfuse
    except Exception as exc:
        record_failure()
        _log_init_warning("Langfuse init failed; observability disabled for this call", exc)
        return None


def get_langfuse_handler() -> Optional[Any]:
    """Return LangChain callback handler when Langfuse is available."""
    global _handler
    if _handler is not None:
        return None if is_tripped() else _handler
    if get_langfuse_client() is None or is_tripped():
        return None

    try:
        try:
            from langfuse.langchain import CallbackHandler
        except Exception:
            from langfuse.callback import CallbackHandler

        handler_kwargs: dict[str, Any] = {}
        params = inspect.signature(CallbackHandler).parameters
        if "public_key" in params:
            handler_kwargs["public_key"] = settings.langfuse_public_key
        if "secret_key" in params:
            handler_kwargs["secret_key"] = settings.langfuse_secret_key
        if "host" in params:
            handler_kwargs["host"] = settings.langfuse_host

        _handler = CallbackHandler(**handler_kwargs)
        return _handler
    except Exception as exc:
        record_failure()
        _log_init_warning("Langfuse CallbackHandler init failed", exc)
        return None


def score_safe(
    *,
    trace_id: Optional[str],
    name: str,
    value: float,
    comment: Optional[str] = None,
) -> None:
    """Best-effort score emission. No-op when Langfuse disabled or unavailable.

    Used by node-level quality signals (Phase I.6): planning_top_score,
    risk_severity_*, outcome_fixed_ratio, validation_issues, ...
    """
    if not trace_id:
        return
    client = get_langfuse_client()
    if client is None:
        return
    try:
        scorer = (
            getattr(client, "create_score", None)
            or getattr(client, "score", None)
        )
        if not callable(scorer):
            return
        params = inspect.signature(scorer).parameters
        payload: dict[str, Any] = {"name": name, "value": value}
        if "trace_id" in params:
            payload["trace_id"] = langfuse_trace_id(trace_id)
        if comment and "comment" in params:
            payload["comment"] = comment
        scorer(**payload)
    except Exception as exc:
        record_failure()
        logger.debug("Langfuse score emit failed (%s): %s", name, exc)


def flush_safe() -> None:
    """Flush buffered observations without letting Langfuse break the pipeline."""
    client = get_langfuse_client()
    if client is None:
        return
    try:
        flush = getattr(client, "flush", None)
        if callable(flush):
            flush()
    except Exception as exc:
        record_failure()
        logger.debug("Langfuse flush failed: %s", exc)


def shutdown() -> None:
    """Best-effort process shutdown hook."""
    client = get_langfuse_client()
    if client is None:
        return
    try:
        flush_safe()
        close = getattr(client, "shutdown", None) or getattr(client, "close", None)
        if callable(close):
            close()
    except Exception as exc:
        record_failure()
        logger.debug("Langfuse shutdown failed: %s", exc)


def _reset_for_tests() -> None:
    global _langfuse, _handler, _init_warning_logged
    _langfuse = None
    _handler = None
    _init_warning_logged = False
    reset_breaker()


atexit.register(shutdown)


__all__ = [
    "flush_safe",
    "get_langfuse_client",
    "get_langfuse_handler",
    "is_tripped",
    "langfuse_trace_id",
    "record_failure",
    "reset_breaker",
    "score_safe",
    "shutdown",
]
