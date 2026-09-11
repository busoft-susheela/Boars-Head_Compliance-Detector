"""Logging configuration — structlog with JSON output and correlation ID support.

Call ``configure_logging()`` once at application startup, before any loggers
are created.

Output sinks:
- stdout              — newline-delimited JSON via basicConfig ``%(message)s``
- ``logs/bh_cv.log``  — same JSON, rotating (10 MB × 5 files)

Correlation ID
--------------
``structlog.contextvars.merge_contextvars`` is the first processor in the
chain so any value bound via ``structlog.contextvars.bind_contextvars()``
(e.g. ``correlation_id`` set by ``CorrelationIdMiddleware``) is automatically
merged into every log event for that request.
"""

import logging
import logging.handlers
import sys
from pathlib import Path

import structlog

LOGS_DIR = Path("logs")
LOG_FILE = LOGS_DIR / "bh_cv.log"
ACTION_LOG_FILE = LOGS_DIR / "action_log.log"
LOG_ROTATION_BYTES = 100 * 1024 * 1024  # 100 MB — large enough to avoid rotation during a run
LOG_BACKUP_COUNT = 3


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog and the stdlib root logger.

    Args:
        log_level: Minimum severity to emit.  Accepts stdlib level names
                   ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL").
    """
    LOGS_DIR.mkdir(exist_ok=True)

    # ------------------------------------------------------------------ #
    # stdlib base — format="%(message)s" lets structlog's JSONRenderer
    # own the full line format; basicConfig writes to stdout by default.
    # ------------------------------------------------------------------ #
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        stream=sys.stdout,
    )

    # ------------------------------------------------------------------ #
    # structlog configuration
    # ------------------------------------------------------------------ #
    def _ensure_correlation_id(logger, method, event_dict):
        # logger and method are required by the structlog processor interface.
        del logger, method
        event_dict.setdefault("correlation_id", "-")
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,   # pulls bound correlation_id, camera_id, frame_id
            _ensure_correlation_id,                    # fallback "-" when no context is bound
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ------------------------------------------------------------------ #
    # File handler — same %(message)s format; JSONRenderer already built
    # the full JSON string so the handler just writes it verbatim.
    # ------------------------------------------------------------------ #
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_ROTATION_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,  # defer file open to first write; reduces Windows file-lock conflicts
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger()
    root.handlers.clear()   # discard any handlers added before this call
    root.addHandler(logging.StreamHandler(sys.stdout))
    root.addHandler(file_handler)
    root.setLevel(log_level)

    # ------------------------------------------------------------------ #
    # Noise reduction for third-party libraries
    # ------------------------------------------------------------------ #
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def configure_action_log() -> None:
    """Set up the dedicated plain-text action log (logs/action_log.log).

    The action logger is completely independent of the root logger:
    - ``propagate=False`` prevents JSON bleed into bh_cv.log.
    - Lines are plain text (``%(message)s``), not JSON.
    - Both the file and stdout receive every entry.

    Call once at application startup, after ``configure_logging()``.
    """
    LOGS_DIR.mkdir(exist_ok=True)

    stdlib_logger = logging.getLogger("action_log")
    stdlib_logger.propagate = False
    stdlib_logger.setLevel(logging.INFO)

    # Clear any handlers left from a previous call (e.g. during tests).
    stdlib_logger.handlers.clear()

    file_handler = logging.handlers.RotatingFileHandler(
        ACTION_LOG_FILE,
        maxBytes=LOG_ROTATION_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter("\n[LOG] %(message)s"))

    stdlib_logger.addHandler(file_handler)
    stdlib_logger.addHandler(stdout_handler)
