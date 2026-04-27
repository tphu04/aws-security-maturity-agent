"""JSON structured logger với `run_id` ContextVar.

Mỗi node của LangGraph set `run_id` qua `set_run_id(state["run_id"])`,
mọi log call sau đó tự động kèm trường này — về sau dùng làm Langfuse
trace_id để correlate logs ↔ trace.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar

_run_id_var: ContextVar[str] = ContextVar("run_id", default="")

# Các attribute mặc định của LogRecord — không in lại trong JSON payload
_RESERVED_LOGRECORD_KEYS = frozenset(
    {
        "msg", "args", "levelname", "levelno", "name", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
        "taskName",
    }
)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "run_id": _run_id_var.get(),
        }
        # Inject `extra={...}` fields người gọi truyền vào
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOGRECORD_KEYS and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(name: str) -> logging.Logger:
    """Return logger có JSON handler. Idempotent — không double-add handler."""
    logger = logging.getLogger(name)
    if not any(isinstance(h.formatter, _JsonFormatter) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def set_run_id(run_id: str) -> None:
    """Set run_id cho ContextVar — log tiếp theo cùng task/thread sẽ kèm field này."""
    _run_id_var.set(run_id or "")


def get_run_id() -> str:
    return _run_id_var.get()


__all__ = ["get_logger", "set_run_id", "get_run_id"]
