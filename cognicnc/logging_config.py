"""Centralized logging configuration for CogniCNC.

Design goals
------------
* **Single source of truth.** Every module uses ``get_logger(__name__)``.
* **Streamlit-safe.** Streamlit re-executes scripts on every interaction.
  Naive ``logging.basicConfig`` calls would attach duplicate handlers on
  each rerun. We therefore attach handlers *once*, keyed by a sentinel
  attribute on the root logger, and we use named handlers so repeated
  calls become idempotent.
* **Rotating files.** Per-subsystem log files under ``logs/`` with size
  rotation so a long simulation never fills the disk.
* **Console + file.** Both configurable via ``settings.yaml``.

Public API
----------
* ``configure_logging()`` - idempotent, call once at application start.
* ``get_logger(name)``    - thin wrapper around ``logging.getLogger``.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Dict

from cognicnc.config import AppConfig, load_config


# Sentinel attribute used to detect repeated initialization (Streamlit reruns).
_CONFIGURED_FLAG = "_cognicnc_logging_configured"

# Named handler prefix - allows us to detect & reuse our own handlers only.
_HANDLER_PREFIX = "cognicnc::"

# Subsystem -> log filename. Phase 0 only needs app.log, but we define the
# full set up front so later phases can call get_logger(...) without having
# to touch this file again.
_SUBSYSTEM_FILES: Dict[str, str] = {
    "app": "app.log",
    "simulator": "simulator.log",
    "ml": "ml.log",
    "database": "database.log",
}


def _build_formatter(cfg: AppConfig) -> logging.Formatter:
    log_cfg = cfg.settings.get("logging", {})
    fmt = log_cfg.get("format", "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    datefmt = log_cfg.get("datefmt", "%Y-%m-%d %H:%M:%S")
    return logging.Formatter(fmt=fmt, datefmt=datefmt)


def _make_rotating_file_handler(
    log_dir: Path,
    filename: str,
    level: int,
    formatter: logging.Formatter,
    max_bytes: int,
    backup_count: int,
    handler_name: str,
) -> logging.Handler:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        delay=True,
    )
    handler.set_name(handler_name)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


def _make_console_handler(
    level: int, formatter: logging.Formatter, handler_name: str
) -> logging.Handler:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.set_name(handler_name)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


def _has_handler(logger: logging.Logger, handler_name: str) -> bool:
    return any(getattr(h, "name", None) == handler_name for h in logger.handlers)


def configure_logging() -> None:
    """Configure root + subsystem loggers. Safe to call multiple times.

    * Attaches a console handler to the root logger (once).
    * Attaches one RotatingFileHandler per subsystem logger (once each).
    * On subsequent calls (e.g. Streamlit reruns) the function detects the
      sentinel flag and existing named handlers and returns without
      duplicating them.
    """
    cfg = load_config()
    log_cfg = cfg.settings.get("logging", {})

    level_name = str(log_cfg.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    use_console = bool(log_cfg.get("console", True))
    use_file = bool(log_cfg.get("file", True))
    max_bytes = int(log_cfg.get("max_bytes", 1_048_576))
    backup_count = int(log_cfg.get("backup_count", 5))

    formatter = _build_formatter(cfg)
    log_dir = cfg.resolved_path("logs")

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # ---- Console handler on root (shared by all loggers) --------------------
    if use_console:
        console_name = f"{_HANDLER_PREFIX}console"
        if not _has_handler(root_logger, console_name):
            root_logger.addHandler(_make_console_handler(level, formatter, console_name))

    # ---- Per-subsystem rotating file handlers -------------------------------
    if use_file:
        for subsystem, filename in _SUBSYSTEM_FILES.items():
            logger_name = f"cognicnc.{subsystem}" if subsystem != "app" else "cognicnc"
            subsystem_logger = logging.getLogger(logger_name)
            subsystem_logger.setLevel(level)
            # Prevent double-emission: root console handler already prints these.
            subsystem_logger.propagate = True

            handler_name = f"{_HANDLER_PREFIX}file::{subsystem}"
            if not _has_handler(subsystem_logger, handler_name):
                subsystem_logger.addHandler(
                    _make_rotating_file_handler(
                        log_dir=log_dir,
                        filename=filename,
                        level=level,
                        formatter=formatter,
                        max_bytes=max_bytes,
                        backup_count=backup_count,
                        handler_name=handler_name,
                    )
                )

    # Silence overly chatty third-party loggers at WARNING by default.
    for noisy in ("urllib3", "matplotlib", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    setattr(root_logger, _CONFIGURED_FLAG, True)


def get_logger(name: str) -> logging.Logger:
    """Return a logger, ensuring logging has been configured first."""
    root_logger = logging.getLogger()
    if not getattr(root_logger, _CONFIGURED_FLAG, False):
        configure_logging()
    return logging.getLogger(name)