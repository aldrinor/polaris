"""
POLARIS v3 Logging Configuration

Centralized logging setup for all agents and components.
Supports structured logging, file output, and log rotation.
"""

import logging
import logging.handlers
import os
import sys
import json
from pathlib import Path
from datetime import UTC, datetime
from typing import Optional, Dict, Any


# =============================================================================
# Configuration
# =============================================================================

LOG_DIR = Path("logs")
LOG_LEVEL = os.getenv("POLARIS_LOG_LEVEL", "INFO")
LOG_FORMAT_CONSOLE = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
LOG_FORMAT_FILE = "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_LOG_SIZE_MB = 50
LOG_BACKUP_COUNT = 5


# =============================================================================
# Custom Formatters
# =============================================================================

class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields if present
        if hasattr(record, "vector_id"):
            log_obj["vector_id"] = record.vector_id
        if hasattr(record, "agent"):
            log_obj["agent"] = record.agent
        if hasattr(record, "iteration"):
            log_obj["iteration"] = record.iteration
        if hasattr(record, "duration_ms"):
            log_obj["duration_ms"] = record.duration_ms

        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


class ColoredFormatter(logging.Formatter):
    """Colored console output formatter."""

    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


# =============================================================================
# Logger Configuration
# =============================================================================

def setup_logging(
    level: str = None,
    console: bool = True,
    file: bool = True,
    structured: bool = False,
    log_dir: Path = None
) -> logging.Logger:
    """
    Configure logging for POLARIS.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console: Enable console output
        file: Enable file output
        structured: Use JSON structured logging for file
        log_dir: Custom log directory

    Returns:
        Root logger
    """
    level = level or LOG_LEVEL
    log_dir = log_dir or LOG_DIR

    # Create log directory
    log_dir.mkdir(parents=True, exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger("polaris")
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)

        # Use colored formatter if terminal supports it
        if sys.stdout.isatty():
            console_handler.setFormatter(
                ColoredFormatter(LOG_FORMAT_CONSOLE, LOG_DATE_FORMAT)
            )
        else:
            console_handler.setFormatter(
                logging.Formatter(LOG_FORMAT_CONSOLE, LOG_DATE_FORMAT)
            )

        root_logger.addHandler(console_handler)

    # File handler with rotation
    if file:
        log_file = log_dir / "polaris.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=MAX_LOG_SIZE_MB * 1024 * 1024,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)

        if structured:
            file_handler.setFormatter(StructuredFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(LOG_FORMAT_FILE, LOG_DATE_FORMAT)
            )

        root_logger.addHandler(file_handler)

    # Also configure standard library loggers
    for lib in ["src", "src.agents", "src.orchestration", "src.graph", "src.tools"]:
        lib_logger = logging.getLogger(lib)
        lib_logger.setLevel(getattr(logging, level.upper()))
        lib_logger.handlers.clear()
        lib_logger.parent = root_logger

    return root_logger


def get_agent_logger(agent_name: str) -> logging.Logger:
    """
    Get a logger for a specific agent.

    Args:
        agent_name: Name of the agent (e.g., "SearchAgent")

    Returns:
        Configured logger
    """
    logger = logging.getLogger(f"polaris.agents.{agent_name}")
    return logger


def get_component_logger(component_name: str) -> logging.Logger:
    """
    Get a logger for a specific component.

    Args:
        component_name: Name of the component (e.g., "graph_retriever")

    Returns:
        Configured logger
    """
    logger = logging.getLogger(f"polaris.{component_name}")
    return logger


# =============================================================================
# Logging Context
# =============================================================================

class LogContext:
    """
    Context manager for adding context to log records.

    Usage:
        with LogContext(vector_id="S1V1", agent="SearchAgent"):
            logger.info("Processing search")
    """

    def __init__(self, **kwargs):
        self.context = kwargs
        self.old_factory = None

    def __enter__(self):
        self.old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.setLogRecordFactory(self.old_factory)


def log_agent_action(
    logger: logging.Logger,
    action: str,
    vector_id: str = None,
    agent: str = None,
    details: Dict[str, Any] = None,
    level: int = logging.INFO
):
    """
    Log an agent action with context.

    Args:
        logger: Logger to use
        action: Action being performed
        vector_id: Current vector ID
        agent: Agent name
        details: Additional details
        level: Log level
    """
    msg_parts = [f"[{action}]"]

    if vector_id:
        msg_parts.append(f"vector={vector_id}")
    if agent:
        msg_parts.append(f"agent={agent}")
    if details:
        for key, value in details.items():
            msg_parts.append(f"{key}={value}")

    logger.log(level, " | ".join(msg_parts))


def log_performance(
    logger: logging.Logger,
    operation: str,
    duration_ms: float,
    success: bool = True,
    details: Dict[str, Any] = None
):
    """
    Log performance metrics.

    Args:
        logger: Logger to use
        operation: Operation name
        duration_ms: Duration in milliseconds
        success: Whether operation succeeded
        details: Additional details
    """
    status = "SUCCESS" if success else "FAILED"
    msg = f"[PERF] {operation} | {status} | {duration_ms:.2f}ms"

    if details:
        detail_str = " | ".join(f"{k}={v}" for k, v in details.items())
        msg += f" | {detail_str}"

    level = logging.INFO if success else logging.WARNING
    logger.log(level, msg)


# =============================================================================
# Initialize Default Logging
# =============================================================================

# Auto-initialize when module is imported
_initialized = False


def ensure_logging_initialized():
    """Ensure logging is initialized (idempotent)."""
    global _initialized
    if not _initialized:
        setup_logging()
        _initialized = True


# Initialize on import
ensure_logging_initialized()
