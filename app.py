"""CogniCNC — Industry 4.0 Smart CNC Control Center.

Launch with:
    streamlit run app.py

This is the main Streamlit entry point. It initializes all shared
services (factory, inference, database, analytics) in session state
and dispatches to the appropriate page renderer.

For non-interactive use (Phase 0 smoke test), run:
    python app.py --smoke-test
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cognicnc import __version__
from cognicnc.config import load_config
from cognicnc.logging_config import configure_logging, get_logger
from cognicnc.simulator.factory import VirtualFactory
from cognicnc.services.inference import InferenceService
from cognicnc.services.decision_engine import DecisionEngine
from cognicnc.services.alert_service import AlertService
from cognicnc.database.repository import Repository
from cognicnc.analytics.production import ProductionAnalytics
from cognicnc.dashboard.styles import DARK_THEME_CSS
from cognicnc.dashboard.pages import (
    render_overview,
    render_monitoring,
    render_maintenance,
    render_analytics,
    render_alerts,
    render_simulation,
)


# ---------------------------------------------------------------------------
# Initialization (runs once per session)
# ---------------------------------------------------------------------------

@st.cache_resource
def init_services():
    """Load all services once and cache them across Streamlit reruns."""
    configure_logging()
    logger = get_logger("cognicnc")
    cfg = load_config()

    factory = VirtualFactory(cfg)
    repo = Repository(cfg)
    repo.init_db()

    inference = InferenceService(cfg)
    try:
        inference.load()
    except FileNotFoundError:
        logger.warning("Model artifacts not found. Inference will be unavailable.")

    decision_engine = DecisionEngine(cfg)
    alert_service = AlertService(cfg, repo)
    analytics = ProductionAnalytics(cfg, repo)

    logger.info("CogniCNC services initialized for dashboard.")
    return {
        "factory": factory,
        "repo": repo,
        "inference": inference,
        "decision_engine": decision_engine,
        "alert_service": alert_service,
        "analytics": analytics,
        "config": cfg,
    }


def main() -> None:
    st.set_page_config(
        page_title="CogniCNC",
        page_icon="🏭",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Inject dark theme CSS
    st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)

    # Initialize services (cached)
    services = init_services()

    # Store in session_state for page access
    for key, val in services.items():
        st.session_state[key] = val
    if "sim_running" not in st.session_state:
        st.session_state.sim_running = False

    # --- Sidebar --------------------------------------------------------
    st.sidebar.title(f"🏭 CogniCNC")
    st.sidebar.caption(f"v{__version__} | Industry 4.0 Platform")
    st.sidebar.divider()

    page = st.sidebar.radio(
        "Navigation",
        [
            "🏭 Factory Overview",
            "📊 Machine Monitoring",
            "🔧 Predictive Maintenance",
            "📈 Production Analytics",
            "🚨 Alerts & Events",
            "🎮 Simulation & What-If",
        ],
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    st.sidebar.caption(
        "⚠️ Simulated data only.\n"
        "AI4I 2020 dataset (UCI).\n"
        "Not a validated industrial system."
    )

    # --- Page dispatch --------------------------------------------------
    if "Overview" in page:
        render_overview()
    elif "Monitoring" in page:
        render_monitoring()
    elif "Maintenance" in page:
        render_maintenance()
    elif "Analytics" in page:
        render_analytics()
    elif "Alerts" in page:
        render_alerts()
    elif "Simulation" in page:
        render_simulation()


# ---------------------------------------------------------------------------
# Smoke test mode (non-interactive)
# ---------------------------------------------------------------------------

def smoke_test() -> int:
    """Quick verification that all imports and services work."""
    configure_logging()
    logger = get_logger("cognicnc")
    cfg = load_config()

    logger.info("Smoke test: loading services ...")
    factory = VirtualFactory(cfg)
    repo = Repository(cfg)
    repo.init_db()
    inference = InferenceService(cfg)
    try:
        inference.load()
        logger.info("Smoke test: inference loaded OK.")
    except FileNotFoundError:
        logger.warning("Smoke test: inference artifacts not found (OK if Phase 1 not run).")

    decision_engine = DecisionEngine(cfg)
    alert_service = AlertService(cfg, repo)
    analytics = ProductionAnalytics(cfg, repo)

    factory.start()
    samples = factory.tick()
    assert len(samples) == 5, f"Expected 5 samples, got {len(samples)}"

    repo.store_telemetry(samples)
    for s in samples:
        if inference.is_loaded:
            pred = inference.predict(s)
            assert "failure_probability" in pred
            decision = decision_engine.evaluate(s, pred)
            assert decision.risk_level in ("LOW", "WARNING", "CRITICAL")

    summary = analytics.compute_factory_summary()
    assert "factory_oee" in summary

    logger.info("Smoke test PASSED.")
    print("\n[OK] CogniCNC smoke test passed. All services initialized correctly.\n")
    return 0


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        sys.exit(smoke_test())
    else:
        main()