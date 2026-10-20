"""Phase 0 smoke tests.

These tests verify the three invariants that every later phase will rely on:

1. The configuration loads, validates and exposes the five required machines.
2. Logging configures idempotently (Streamlit-safe) and writes to app.log.
3. The `cognicnc` package imports cleanly.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from cognicnc import __version__
from cognicnc.config import AppConfig, get_project_root, load_config
from cognicnc.logging_config import configure_logging, get_logger


# ---------------------------------------------------------------------------
# Package import
# ---------------------------------------------------------------------------

def test_package_version_is_string():
    assert isinstance(__version__, str) and __version__


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def test_project_root_contains_config_dir():
    root = get_project_root()
    assert (root / "config").is_dir(), f"config/ not found under project root {root}"


def test_load_config_returns_appconfig():
    cfg = load_config()
    assert isinstance(cfg, AppConfig)
    assert cfg.app_name == "CogniCNC"
    assert cfg.random_seed == 42


def test_all_five_required_machines_present():
    cfg = load_config()
    ids = {m["id"] for m in cfg.machines}
    assert ids == {"TC-01", "MC-01", "DR-01", "GR-01", "VIS-01"}


def test_resolved_paths_are_absolute_and_exist():
    cfg = load_config()
    for key in ("logs", "artifacts_pm", "artifacts_anomaly",
                "data_raw", "data_processed", "data_simulated",
                "assets_machines"):
        p: Path = cfg.resolved_path(key)
        assert p.is_absolute(), f"{key} is not absolute: {p}"
        assert p.exists(), f"{key} path does not exist: {p}"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def test_configure_logging_is_idempotent():
    configure_logging()
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    # Simulate a Streamlit rerun calling configure_logging() again.
    configure_logging()
    configure_logging()
    handlers_after = list(root.handlers)
    assert len(handlers_before) == len(handlers_after), (
        "configure_logging() must not add duplicate root handlers on repeated calls."
    )


def test_app_log_file_is_written():
    logger = get_logger("cognicnc")
    marker = "phase0-test-marker"
    logger.info(marker)
    # Flush all handlers so the file content is up to date.
    for h in logging.getLogger().handlers + logging.getLogger("cognicnc").handlers:
        try:
            h.flush()
        except Exception:  # noqa: BLE001 - best-effort flush in tests
            pass

    cfg = load_config()
    app_log = cfg.resolved_path("logs") / "app.log"
    assert app_log.is_file(), f"app.log was not created at {app_log}"
    content = app_log.read_text(encoding="utf-8", errors="replace")
    assert marker in content, "Expected marker not found in app.log"


def test_subsystem_loggers_resolve():
    for name in ("cognicnc", "cognicnc.simulator", "cognicnc.ml", "cognicnc.database"):
        logger = get_logger(name)
        assert isinstance(logger, logging.Logger)
        assert logger.name == name