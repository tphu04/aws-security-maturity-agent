"""Context propagation helpers for run_id-aware work."""

from __future__ import annotations

import contextvars
import functools
import inspect
from typing import Any, Callable, TypeVar

from pdca.observability.logger import get_run_id, set_run_id

T = TypeVar("T")


def run_with_context(run_id: str, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a callable inside a copied ContextVar context with `run_id` set."""
    ctx = contextvars.copy_context()

    def _runner() -> T:
        set_run_id(run_id)
        return fn(*args, **kwargs)

    return ctx.run(_runner)


def with_run_id(run_id_arg: str = "run_id") -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that sets `run_id` from a named argument while the function runs."""
    def _decorator(fn: Callable[..., T]) -> Callable[..., T]:
        signature = inspect.signature(fn)

        @functools.wraps(fn)
        def _wrapper(*args: Any, **kwargs: Any) -> T:
            bound = signature.bind_partial(*args, **kwargs)
            run_id = str(bound.arguments.get(run_id_arg, "") or "")
            return run_with_context(run_id, fn, *args, **kwargs)

        return _wrapper

    return _decorator


__all__ = ["get_run_id", "set_run_id", "run_with_context", "with_run_id"]
