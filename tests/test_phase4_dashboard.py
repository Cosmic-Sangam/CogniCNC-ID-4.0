"""Phase 4 tests — dashboard module imports and smoke test."""

from __future__ import annotations

import pytest


def test_dashboard_styles_import():
    from cognicnc.dashboard.styles import DARK_THEME_CSS, get_status_badge, get_risk_badge
    assert "background" in DARK_THEME_CSS
    assert "RUNNING" in get_status_badge("RUNNING")
    assert "CRITICAL" in get_risk_badge("CRITICAL")


def test_dashboard_pages_import():
    from cognicnc.dashboard.pages import (
        render_overview,
        render_monitoring,
        render_maintenance,
        render_analytics,
        render_alerts,
        render_simulation,
    )
    # Just verify they are callable
    assert callable(render_overview)
    assert callable(render_simulation)


def test_app_smoke_test():
    """Run the non-interactive smoke test."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "app.py", "--smoke-test"],
        capture_output=True,
        text=True,
        cwd=str(pytest.importorskip("cognicnc").__path__[0] + "/.."),
    )
    # The smoke test should exit with 0
    assert result.returncode == 0, f"Smoke test failed:\n{result.stderr}"