"""
Marcedit Structured Logging & Performance Monitoring  (Week 7 Day 4)

Usage:
    from .logging_utils import get_logger, monitor_performance

    log = get_logger(__name__)
    log.info("replace_text", page=3, target="foo", replacement="bar")

    @monitor_performance("replace_text")
    def replace_text_in_pdf(...):
        ...
"""

import json
import logging
import os
import time
from functools import wraps


# ── Log-level helpers ─────────────────────────────────────────────────────────

_LEVEL_MAP = {
    "debug":    logging.DEBUG,
    "info":     logging.INFO,
    "warning":  logging.WARNING,
    "error":    logging.ERROR,
    "critical": logging.CRITICAL,
}

_DEFAULT_LEVEL = os.environ.get("MARCEDIT_LOG_LEVEL", "info").lower()


# ── JSON formatter ────────────────────────────────────────────────────────────

class _JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: dict = {
            "ts":      round(record.created, 3),
            "level":   record.levelname,
            "logger":  record.name,
            "message": record.getMessage(),
        }
        # Attach any extra structured fields set via LogRecord.__dict__
        for key, val in record.__dict__.items():
            if key.startswith("_") or key in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "message", "module",
                "msecs", "pathname", "process", "processName", "relativeCreated",
                "stack_info", "taskName", "thread", "threadName", "exc_info",
                "exc_text",
            }:
                continue
            payload[key] = val
        if record.exc_info:
            import traceback
            payload["traceback"] = traceback.format_exception(*record.exc_info)
        return json.dumps(payload, default=str)


# ── Structured logger wrapper ─────────────────────────────────────────────────

class StructuredLogger:
    """
    Thin wrapper around a stdlib Logger that adds keyword-argument support,
    so callers can write::

        log.info("replace_text", page=3, duration_ms=42.1)

    instead of building dicts manually.
    """

    def __init__(self, inner: logging.Logger) -> None:
        self._inner = inner

    # ── level shortcuts ────────────────────────────────────────────────────

    def debug(self, message: str, **kwargs) -> None:
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs) -> None:
        self._log(logging.CRITICAL, message, **kwargs)

    # ── operation helper ───────────────────────────────────────────────────

    def operation(self, operation: str, status: str = "ok", **kwargs) -> None:
        """Log a structured operation event (always at INFO level)."""
        self._log(logging.INFO, operation, status=status, **kwargs)

    # ── internal ──────────────────────────────────────────────────────────

    def _log(self, level: int, message: str, **kwargs) -> None:
        if not self._inner.isEnabledFor(level):
            return
        record = self._inner.makeRecord(
            name=self._inner.name,
            level=level,
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        self._inner.handle(record)


# ── Logger registry ───────────────────────────────────────────────────────────

_loggers: dict[str, StructuredLogger] = {}
_configured = False


def _configure_root(log_file: str | None = None) -> None:
    global _configured
    if _configured:
        return

    root = logging.getLogger("marcedit")
    root.setLevel(_LEVEL_MAP.get(_DEFAULT_LEVEL, logging.INFO))
    root.propagate = False

    # Console handler (plain text, INFO+)
    if not root.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("[%(name)s] %(levelname)s %(message)s"))
        root.addHandler(ch)

    # File handler (JSON, all levels) — opt-in via MARCEDIT_LOG_FILE env var
    log_path = log_file or os.environ.get("MARCEDIT_LOG_FILE")
    if log_path:
        try:
            fh = logging.FileHandler(log_path, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(_JSONFormatter())
            root.addHandler(fh)
        except OSError as e:
            root.warning(f"Could not open log file {log_path!r}: {e}")

    _configured = True


def get_logger(name: str, log_file: str | None = None) -> StructuredLogger:
    """
    Return (or create) a StructuredLogger for *name*.

    All loggers share the ``marcedit.*`` hierarchy so a single file handler
    on the root captures everything.
    """
    _configure_root(log_file)
    qualified = f"marcedit.{name}" if not name.startswith("marcedit") else name
    if qualified not in _loggers:
        _loggers[qualified] = StructuredLogger(logging.getLogger(qualified))
    return _loggers[qualified]


# ── Performance monitor decorator ─────────────────────────────────────────────

#: Global stats accumulator: {operation_name -> {"calls", "total_ms", "errors"}}
_perf_stats: dict[str, dict] = {}

_perf_logger = None  # Lazy-init so we don't force configuration at import time


def _get_perf_logger() -> StructuredLogger:
    global _perf_logger
    if _perf_logger is None:
        _perf_logger = get_logger("perf")
    return _perf_logger


def monitor_performance(operation_name: str):
    """
    Decorator that times the wrapped function and logs structured metrics.

    Example::

        @monitor_performance("replace_text")
        def replace_text_in_pdf(...):
            ...

    Each call emits an INFO record like::

        {"message": "replace_text", "status": "success", "duration_ms": 123.4}

    and accumulates totals accessible via :func:`get_perf_stats`.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            exc_info = None
            try:
                result = func(*args, **kwargs)
                status = "success"
                # Treat result dicts with success=False as logical errors
                if isinstance(result, dict) and not result.get("success", True):
                    status = "failure"
                return result
            except Exception:
                import sys
                exc_info = sys.exc_info()
                status = "error"
                raise
            finally:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                entry = _perf_stats.setdefault(operation_name, {"calls": 0, "total_ms": 0.0, "errors": 0})
                entry["calls"] += 1
                entry["total_ms"] += duration_ms
                if status == "error":
                    entry["errors"] += 1
                _get_perf_logger().operation(
                    operation_name,
                    status=status,
                    duration_ms=round(duration_ms, 2),
                )
        return wrapper
    return decorator


def get_perf_stats() -> dict:
    """
    Return a snapshot of accumulated performance statistics.

    Returns:
        dict mapping operation_name → {"calls", "total_ms", "avg_ms", "errors"}
    """
    out = {}
    for op, entry in _perf_stats.items():
        calls = entry["calls"]
        out[op] = {
            "calls":    calls,
            "total_ms": round(entry["total_ms"], 2),
            "avg_ms":   round(entry["total_ms"] / calls, 2) if calls else 0.0,
            "errors":   entry["errors"],
        }
    return out


def reset_perf_stats() -> None:
    """Clear all accumulated performance statistics."""
    _perf_stats.clear()


# ── Health check ──────────────────────────────────────────────────────────────

def health_check() -> dict:
    """
    Return a lightweight health-check dict suitable for XPC polling.

    Returns:
        dict with:
          "status":       "ok" | "degraded"
          "perf_summary": dict  – per-operation stats snapshot
          "log_level":    str
          "log_file":     str | None
    """
    try:
        import fitz  # confirm PyMuPDF is available
        pymupdf_ok = True
        pymupdf_version = getattr(fitz, "version", ("?",))[0]
    except ImportError:
        pymupdf_ok = False
        pymupdf_version = "unavailable"

    stats = get_perf_stats()
    total_errors = sum(v["errors"] for v in stats.values())
    total_calls  = sum(v["calls"]  for v in stats.values())

    error_rate = (total_errors / total_calls) if total_calls else 0.0
    status = "degraded" if (not pymupdf_ok or error_rate > 0.1) else "ok"

    log_file = os.environ.get("MARCEDIT_LOG_FILE")

    return {
        "status":          status,
        "pymupdf_ok":      pymupdf_ok,
        "pymupdf_version": pymupdf_version,
        "error_rate":      round(error_rate, 4),
        "total_calls":     total_calls,
        "total_errors":    total_errors,
        "perf_summary":    stats,
        "log_level":       _DEFAULT_LEVEL,
        "log_file":        log_file,
    }
